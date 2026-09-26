# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Прогон плагина в QGIS 3 на Qt 5. Запускается сценарием при старте QGIS.

    qgis.bat --profiles-path %TEMP%\\planetx_qt5 --code tools\\qt5_check.py

Сценарий берёт плагин из рабочей копии, открывает окно глобуса, ждёт
загрузки, считает дыры и тайлы высот, делает перелёт в Пермь, открывает
окно «О модуле» и пишет итог в
%TEMP%\\planetx_qt5.json. Потом закрывает QGIS. Профиль отдельный,
профиль пользователя не трогается.
"""
import json
import os
import sys
import time
import traceback

ROOT = r"C:\Dev\planetx"
OUT = os.path.join(os.environ.get("TEMP", "."), "planetx_qt5.json")
sys.path.insert(0, ROOT)
# При падении QGIS стек Python всех потоков уходит в этот файл. Журнал
# QGIS после падения пуст, другого следа не остаётся.
import faulthandler  # noqa: E402

CRASH = open(os.path.join(os.environ.get("TEMP", "."),
                          "planetx_qt5_crash.txt"), "w", encoding="utf-8")
faulthandler.enable(CRASH, all_threads=True)

from qgis.core import Qgis, QgsApplication, QgsMessageLog  # noqa: E402
from qgis.PyQt.QtCore import QT_VERSION_STR, QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

result = {"qgis": Qgis.version(), "qt": QT_VERSION_STR,
          "python": sys.version.split()[0], "errors": [], "probe": False}


def _listen(message, tag, level, *extra):
    if tag == "PlanetX проверка журнала":
        result["probe"] = True
    elif "Python" in tag or "Ошибка" in tag:
        result["errors"].append(message.strip().splitlines()[-1])


_log = QgsApplication.messageLog()
_signal = getattr(_log, "messageReceivedWithFormat", None) \
    or _log.messageReceived
_signal.connect(_listen)
QgsMessageLog.logMessage("проба", "PlanetX проверка журнала",
                         Qgis.MessageLevel.Info)
_state = {}


def _write():
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)


def _finish():
    _write()
    # PLANETX_KEEP=1 оставляет QGIS открытым, чтобы прочитать сообщения.
    if os.environ.get("PLANETX_KEEP") != "1":
        QgsApplication.instance().exit(0)


def _step(name, function, then=None, delay=0):
    def run():
        CRASH.write("step %s\n" % name)
        CRASH.flush()
        try:
            function()
        except (AttributeError, ImportError, KeyError, OSError,
                RuntimeError, TypeError, ValueError):
            # Сценарий обязан дописать итог и закрыть QGIS.
            result["errors"].append("%s: %s" % (name, traceback.format_exc()
                                                .strip().splitlines()[-1]))
            _finish()
            return
        if then is not None:
            QTimer.singleShot(delay, then)
    return run


def open_globe():
    from planetx.plugin import PlanetXPlugin
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    _state["plugin"] = plugin
    window = plugin.window
    window.showNormal()
    window.raise_()


def check_view():
    window = _state["plugin"].window
    view = window.view
    view.hole_check = True
    view.hole_counts = []
    view.grabFramebuffer()
    view.hole_check = False
    result["gl"] = view.gl_info.get("gl")
    result["version"] = list(view.gl_info.get("version", ()))
    result["ready"] = view.ready()
    result["drawn"] = view.drawn
    result["holes"] = view.hole_counts[-1][2] if view.hole_counts else None
    result["gl_errors"] = dict(view.gl_errors)
    result["load_errors"] = len(window.errors)
    result["user_agent"] = window.loader.last_user_agent
    image = view.grabFramebuffer()
    image.save(os.path.join(os.environ.get("TEMP", "."),
                            "planetx_qt5.png"))
    window.place.setText("58.0105, 56.2294")
    window.fly()
    _state["flight"] = time.monotonic()


def check_flight():
    view = _state["plugin"].window.view
    pose = view.navigator.pose
    result["flight_end"] = [pose.lat, pose.lon, pose.distance]
    result["flying"] = view.navigator.flight is not None
    result["frames"] = view.frame
    result["heights"] = len(view.store.tiles)
    result["sources"] = [s.name for s in _state["plugin"].window.sources]
    from planetx.ui.about import AboutDialog
    dialog = AboutDialog(_state["plugin"].window)
    dialog.show()
    result["about"] = dialog.windowTitle()
    dialog.close()
    _state["plugin"].unload()


QTimer.singleShot(
    3000, _step("open", open_globe,
                _step("view", check_view,
                      _step("flight", check_flight, _finish, 500),
                      9000),
                20000))
QTimer.singleShot(90000, _finish)
