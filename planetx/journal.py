# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Журнал работы модуля - файл PlanetX/planetx.log в профиле QGIS.

Строка журнала - время и событие: загрузка модуля, окно глобуса,
выбор карт и слоёв, подложка, тело, демо, ошибки Python модуля.
Сторож зависания каждую секунду переставляет срок
faulthandler.dump_traceback_later. Если главный поток QGIS не отвечает
дольше HANG секунд, faulthandler из своего потока пишет в журнал стеки
всех потоков Python, ему GIL не нужен. Когда поток оживает, журнал
получает строку о длительности паузы. Просьба автора от 9 октября
2026 года - QGIS 3.40.15 на рабочем компьютере зависал без сообщений.

Ошибки SSL любых запросов QGIS идут в журнал с владельцем сертификата.
QGIS 3.40.15 автора 7 октября 2026 года упал в окне ошибок SSL,
какой сервер его вызвал, неизвестно. Сигнал приходит и из рабочих
потоков, связь прямая - очередь Qt не передаёт QList<QSslError>.
"""
import faulthandler
import os
import platform
import sys
import time
import traceback

from qgis.core import Qgis, QgsApplication, QgsNetworkAccessManager
from qgis.PyQt.QtCore import (PYQT_VERSION_STR, QT_VERSION_STR, Qt,
                              QTimer, QUrl)
from qgis.PyQt.QtNetwork import QSslCertificate
from qgis.PyQt.QtGui import QDesktopServices

from .i18n import tr
from .qt_compat import enum

NAME = "planetx.log"
OLD = "planetx.1.log"
# Больше LIMIT байт - файл уходит в OLD, журнал начинается заново.
LIMIT = 1000000
HANG = 10  # с без ответа главного потока до записи стеков
BEAT = 1000  # мс, шаг сторожа

DIRECT = enum(Qt, "ConnectionType", "DirectConnection")
COMMON_NAME = enum(QSslCertificate, "SubjectInfo", "CommonName")

_state = {"file": None, "timer": None, "beat": 0.0, "hook": None,
          "prior": None, "ssl": False}


def folder():
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")


def path():
    return os.path.join(folder(), NAME)


def note(text):
    """Строка журнала. Ошибка записи журнала работу модуля
    не останавливает."""
    fh = _state["file"]
    if fh is None:
        return
    try:
        fh.write("{}  {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"),
                                   text))
        fh.flush()
    except (OSError, ValueError):
        _state["file"] = None


def _open():
    os.makedirs(folder(), exist_ok=True)
    name = path()
    if os.path.exists(name) and os.path.getsize(name) > LIMIT:
        os.replace(name, os.path.join(folder(), OLD))
    return open(name, "a", encoding="utf-8")


def _arm():
    faulthandler.cancel_dump_traceback_later()
    faulthandler.dump_traceback_later(HANG, file=_state["file"])


def _beat():
    now = time.monotonic()
    late = now - _state["beat"]
    _state["beat"] = now
    if _state["file"] is None:
        return
    if late > HANG:
        note(tr("Главный поток QGIS не отвечал {seconds} с.",
                seconds=round(late)))
    _arm()


def _hook(kind, value, trace):
    """Ошибка Python с кадром модуля - в журнал, дальше обработчику
    QGIS."""
    frames = traceback.extract_tb(trace)
    if any("planetx" in frame.filename.lower() for frame in frames):
        note(tr("Ошибка Python:") + "\n" + "".join(
            traceback.format_exception(kind, value, trace)).rstrip())
    prior = _state["prior"]
    if prior is not None:
        prior(kind, value, trace)


def _ssl(request, errors):
    """Ошибки SSL запроса QGIS. Может прийти из рабочего потока."""
    lines = []
    for error in errors:
        names = error.certificate().subjectInfo(COMMON_NAME)
        lines.append("{} ({})".format(error.errorString(),
                                      ", ".join(names) or "-"))
    note(tr("Ошибки SSL запроса {number}:", number=request) + " "
         + "; ".join(lines))


def start(version):
    """Открыть журнал и поставить сторожа. Зовёт initGui."""
    if _state["file"] is not None:
        return
    try:
        _state["file"] = _open()
    except OSError:
        return
    note("PlanetX {} - QGIS {}, Qt {}, PyQt {}, Python {}, {}".format(
        version, Qgis.version(), QT_VERSION_STR, PYQT_VERSION_STR,
        platform.python_version(), platform.platform()))
    _state["prior"] = sys.excepthook
    _state["hook"] = _hook
    sys.excepthook = _hook
    manager = QgsNetworkAccessManager.instance()
    if hasattr(manager, "requestEncounteredSslErrors"):
        manager.requestEncounteredSslErrors.connect(_ssl, DIRECT)
        _state["ssl"] = True
    # Сторож проверочных шагов (PLANETX_HANG_DUMP) уже держит общий
    # срок faulthandler, второй его сбил бы.
    if os.environ.get("PLANETX_HANG_DUMP", "0") != "0":
        return
    _state["beat"] = time.monotonic()
    timer = QTimer()
    timer.timeout.connect(_beat)
    timer.start(BEAT)
    _state["timer"] = timer
    _arm()


def stop():
    """Снять сторожа и закрыть журнал. Зовёт unload."""
    timer = _state["timer"]
    if timer is not None:
        timer.stop()
        _state["timer"] = None
        faulthandler.cancel_dump_traceback_later()
    if sys.excepthook is _state["hook"]:
        sys.excepthook = _state["prior"]
    _state["hook"] = _state["prior"] = None
    if _state["ssl"]:
        _state["ssl"] = False
        try:
            QgsNetworkAccessManager.instance() \
                .requestEncounteredSslErrors.disconnect(_ssl)
        except TypeError:
            note("ssl disconnect failed")
    note(tr("Модуль выгружен."))
    fh = _state["file"]
    _state["file"] = None
    if fh is not None:
        fh.close()


def open_journal():
    """Открыть журнал программой системы. Пустой журнал создаётся,
    чтобы было что открыть."""
    name = path()
    if not os.path.exists(name):
        try:
            os.makedirs(folder(), exist_ok=True)
            open(name, "a", encoding="utf-8").close()
        except OSError:
            return False
    return QDesktopServices.openUrl(QUrl.fromLocalFile(name))
