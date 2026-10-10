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

Падение QGIS журнал узнаёт при следующем запуске. Каждый процесс
QGIS с модулем держит файл PlanetX/sessions/<pid>.txt, обычный выход
и выгрузка его удаляют. Файл умершего процесса значит падение или
снятие задачи. Журнал получает строку о нём, стеки Python из файла
QGIS qgis-python-crash-info-<pid> во временной папке (его пишет
faulthandler, включённый самим QGIS) и имя дампа Windows этого
процесса. Ошибки рабочих потоков Python и «неподнимаемые» ошибки
(sys.unraisablehook, например из обратных вызовов ctypes) идут
в журнал так же, как ошибки главного потока. Раз в STATE_EVERY
секунд журнал получает память процесса и количество объектов GDI
и USER - их исчерпание роняет Qt. Просьба автора от 10 октября
2026 года после двух падений без следа в журнале.

Главный поток, молчащий дольше DUMP_AFTER секунд, - повод записать
дамп процесса со стеками всех потоков C++ (MiniDumpWriteDump,
без памяти кучи, около 300 КБ). Стеки Python взаимную блокировку внутри
QGIS не показывают - на рабочем компьютере автора главный поток
больше минуты стоял в QgsNetworkAccessManager.get(). Дамп пишет
отдельный процесс hangwatch.py: главный поток раз в секунду трогает
файл отметок PlanetX/beat-<pid>, процесс-сторож видит паузу, снимает
дамп снаружи, разбирает его и дописывает разбор в журнал. Поток Python
внутри QGIS этого не может, когда главный поток держит GIL, так
и было при зависании проверочного QGIS 10 октября 2026 года.
"""
import atexit
import ctypes
import faulthandler
import glob
import os
import platform
import sys
import tempfile
import threading
import time
import traceback

from qgis.core import Qgis, QgsApplication, QgsNetworkAccessManager
from qgis.PyQt.QtCore import (PYQT_VERSION_STR, QT_VERSION_STR, QProcess,
                              Qt, QTimer, QUrl)
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
STATE_EVERY = 900  # с между строками о памяти и объектах GDI
CRASH_TEXT = 20000  # знаков файла стеков падения в журнал, не больше
STILL_ACTIVE = 259  # код GetExitCodeProcess живого процесса
QUERY = 0x1000  # PROCESS_QUERY_LIMITED_INFORMATION
DUMP_AFTER = 30  # с без ответа главного потока до записи дампа

DIRECT = enum(Qt, "ConnectionType", "DirectConnection")
COMMON_NAME = enum(QSslCertificate, "SubjectInfo", "CommonName")

_state = {"file": None, "timer": None, "beat": 0.0, "hook": None,
          "prior": None, "ssl": False, "thread_prior": None,
          "unraisable_prior": None, "state_at": 0.0, "watch": None,
          }
_lock = threading.Lock()


def folder():
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")


def path():
    return os.path.join(folder(), NAME)


def sessions():
    return os.path.join(folder(), "sessions")


def note(text):
    """Строка журнала. Ошибка записи журнала работу модуля
    не останавливает. Пишут и рабочие потоки, поэтому под замком."""
    with _lock:
        fh = _state["file"]
        if fh is None:
            return
        try:
            fh.write("{}  {}\n".format(
                time.strftime("%Y-%m-%d %H:%M:%S"), text))
            fh.flush()
        except (OSError, ValueError):
            _state["file"] = None


def _kernel():
    """Своя копия kernel32 - типы её функций не меняют общую
    ctypes.windll другим модулям."""
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_ulong)]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    k.GetCurrentProcess.restype = ctypes.c_void_p
    return k


def alive(pid):
    """Жив ли процесс pid. В Windows os.kill завершил бы процесс,
    поэтому опрос через OpenProcess."""
    if os.name != "nt":
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return True
        return True
    k = _kernel()
    handle = k.OpenProcess(QUERY, 0, pid)
    if not handle:
        return False
    code = ctypes.c_ulong()
    try:
        ok = k.GetExitCodeProcess(handle, ctypes.pointer(code))
    finally:
        k.CloseHandle(handle)
    return bool(ok) and code.value == STILL_ACTIVE


def _mark():
    """Файл сеанса этого процесса."""
    os.makedirs(sessions(), exist_ok=True)
    name = os.path.join(sessions(), "{}.txt".format(os.getpid()))
    with open(name, "w", encoding="utf-8") as fh:
        fh.write(time.strftime("%Y-%m-%d %H:%M:%S"))


def _unmark():
    name = os.path.join(sessions(), "{}.txt".format(os.getpid()))
    try:
        os.remove(name)
    except FileNotFoundError:
        return
    except OSError as error:
        note("session file: {}".format(error))


def _crash_text(pid):
    """Стеки Python падения процесса pid из файла QGIS, пусто если
    файла нет или он пуст."""
    name = os.path.join(tempfile.gettempdir(),
                        "qgis-python-crash-info-{}".format(pid))
    try:
        with open(name, encoding="utf-8", errors="replace") as fh:
            text = fh.read(CRASH_TEXT + 1)
    except OSError:
        return ""
    text = text.strip()
    if len(text) > CRASH_TEXT:
        text = text[:CRASH_TEXT] + "\n…"
    return text


def _dumps(pid):
    """Дампы Windows процесса pid в LOCALAPPDATA/CrashDumps."""
    root = os.path.join(os.environ.get("LOCALAPPDATA", ""), "CrashDumps")
    found = []
    for name in glob.glob(os.path.join(root, "*.{}.dmp".format(pid))):
        try:
            size = os.path.getsize(name)
        except OSError:
            size = 0
        found.append(tr("{name} ({size} МБ)", name=name,
                        size=round(size / 1e6, 1)))
    return found


def harvest():
    """Сеансы умерших процессов QGIS - в журнал, их файлы удаляются.
    Возвращает номера найденных процессов."""
    found = []
    for name in glob.glob(os.path.join(sessions(), "*.txt")):
        stem = os.path.splitext(os.path.basename(name))[0]
        if not stem.isdigit():
            continue
        pid = int(stem)
        if pid == os.getpid() or alive(pid):
            continue
        try:
            with open(name, encoding="utf-8") as fh:
                began = fh.read().strip()
        except OSError:
            began = "?"
        note(tr("Прошлый сеанс QGIS (процесс {pid}, начат {began}) "
                "завершился без выгрузки модуля - падение или снятие "
                "задачи.", pid=pid, began=began))
        text = _crash_text(pid)
        if text:
            note(tr("Стеки Python в момент падения:") + "\n" + text)
        else:
            note(tr("Файла стеков Python этого процесса нет или он "
                    "пуст."))
        for dump in _dumps(pid):
            note(tr("Дамп Windows:") + " " + dump)
        try:
            os.remove(name)
        except OSError as error:
            note("session file: {}".format(error))
        found.append(pid)
    # Файл отметок умершего процесса сторож не удаляет - он видит
    # конец процесса и выходит сам.
    for name in glob.glob(os.path.join(folder(), "beat-*")):
        stem = os.path.basename(name)[len("beat-"):]
        if not stem.isdigit() or int(stem) == os.getpid() \
                or alive(int(stem)):
            continue
        try:
            os.remove(name)
        except OSError as error:
            note("beat file: {}".format(error))
    return found


def _resources():
    """Память процесса в МБ и объекты GDI и USER, только Windows."""
    if os.name != "nt":
        return None

    class Counters(ctypes.Structure):
        _fields_ = [("cb", ctypes.c_ulong),
                    ("PageFaultCount", ctypes.c_ulong),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t)]

    k = _kernel()
    me = k.GetCurrentProcess()
    psapi = ctypes.WinDLL("psapi")
    psapi.GetProcessMemoryInfo.argtypes = [
        ctypes.c_void_p, ctypes.POINTER(Counters), ctypes.c_ulong]
    user = ctypes.WinDLL("user32")
    user.GetGuiResources.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if not psapi.GetProcessMemoryInfo(me, ctypes.pointer(counters),
                                      counters.cb):
        return None
    return {"memory": round(counters.WorkingSetSize / 1e6),
            "committed": round(counters.PagefileUsage / 1e6),
            "gdi": user.GetGuiResources(me, 0),
            "user": user.GetGuiResources(me, 1)}


def beat_path():
    return os.path.join(folder(), "beat-{}".format(os.getpid()))


def _touch():
    """Отметка главного потока для процесса-сторожа."""
    try:
        with open(beat_path(), "a", encoding="utf-8"):
            os.utime(beat_path(), None)
    except OSError as error:
        note("beat: {}".format(error))


def _python():
    """Python из состава QGIS для процесса-сторожа: sys.executable
    внутри QGIS - qgis-bin.exe."""
    for name in ("pythonw.exe", "python.exe"):
        path = os.path.join(sys.prefix, name)
        if os.path.isfile(path):
            return path
    return ""


def _start_watch():
    """Процесс-сторож hangwatch.py, см. описание модуля."""
    python = _python()
    if os.name != "nt" or not python:
        return
    _touch()
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "hangwatch.py")
    header = tr("Главный поток QGIS не отвечает {seconds} с, дамп "
                "процесса со стеками потоков - {path}") + " " + tr(
        "Стеки потоков C++ по дампу, имена функций приблизительные:")
    ok = QProcess.startDetached(python, [
        "-I", script, str(os.getpid()), beat_path(), path(), folder(),
        str(DUMP_AFTER), header,
        tr("Главный поток"), tr("Поток"),
        tr("Потоков в ожидании без своих кадров")])
    ok = ok[0] if isinstance(ok, tuple) else ok
    _state["watch"] = bool(ok)
    if not ok:
        note("hang watch: not started")


def _stop_watch():
    """Без файла отметок процесс-сторож заканчивает работу сам."""
    _state["watch"] = None
    try:
        os.remove(beat_path())
    except FileNotFoundError:
        return
    except OSError as error:
        note("beat: {}".format(error))


def note_resources():
    found = _resources()
    if found is not None:
        note(tr("Память {memory} МБ, выделено {committed} МБ, объектов "
                "GDI {gdi}, USER {user}.", **found))


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
    if _state["watch"]:
        _touch()
    if now - _state["state_at"] > STATE_EVERY:
        _state["state_at"] = now
        note_resources()
    _arm()


def _owner(frames):
    """Модуль QGIS, в чьём файле последний кадр: имя папки после
    python/plugins, иначе пусто."""
    for frame in reversed(frames):
        parts = frame.filename.replace("\\", "/").split("/")
        lower = [p.lower() for p in parts]
        if "plugins" in lower:
            at = len(lower) - 1 - lower[::-1].index("plugins")
            if at + 1 < len(parts) - 1:
                return parts[at + 1]
    return ""


def _error(kind, value, trace, where=""):
    """Ошибка Python в журнал. Чужая помечается модулем, в чьём файле
    она случилась, where - поток или источник."""
    frames = traceback.extract_tb(trace)
    text = "".join(traceback.format_exception(kind, value, trace)).rstrip()
    if where:
        text = where + "\n" + text
    if any("planetx" in frame.filename.lower() for frame in frames):
        note(tr("Ошибка Python:") + "\n" + text)
    else:
        note(tr("Ошибка Python не PlanetX ({owner}):",
                owner=_owner(frames) or "QGIS") + "\n" + text)


def _hook(kind, value, trace):
    """Любая необработанная ошибка Python в QGIS - в журнал, дальше
    обработчику QGIS. Окно ошибки QGIS само может упасть, 10 октября
    2026 года так пропал текст ошибки конца отрисовки карты."""
    _error(kind, value, trace)
    prior = _state["prior"]
    if prior is not None:
        prior(kind, value, trace)


def _thread_hook(args):
    """Необработанная ошибка рабочего потока Python."""
    if args.exc_type is not SystemExit:
        name = args.thread.name if args.thread is not None else "?"
        _error(args.exc_type, args.exc_value, args.exc_traceback,
               tr("Поток {name}.", name=name))
    prior = _state["thread_prior"]
    if prior is not None:
        prior(args)


def _unraisable_hook(args):
    """Ошибка, которую некуда поднять - в __del__, обратном вызове
    ctypes, сборщике мусора."""
    where = args.err_msg or "Exception ignored in"
    if args.object is not None:
        where += " " + repr(args.object)[:200]
    _error(args.exc_type, args.exc_value, args.exc_traceback, where)
    prior = _state["unraisable_prior"]
    if prior is not None:
        prior(args)


def _exit():
    """Обычный выход Python - сеанс закрыт без падения."""
    if _state["file"] is not None:
        _unmark()
        note(tr("QGIS закрыт."))


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
    note("PlanetX {} - QGIS {}, Qt {}, PyQt {}, Python {}, {}, "
         "pid {}".format(version, Qgis.version(), QT_VERSION_STR,
                         PYQT_VERSION_STR, platform.python_version(),
                         platform.platform(), os.getpid()))
    try:
        harvest()
        _mark()
    except OSError as error:
        note("sessions: {}".format(error))
    note_resources()
    _state["prior"] = sys.excepthook
    _state["hook"] = _hook
    sys.excepthook = _hook
    _state["thread_prior"] = threading.excepthook
    threading.excepthook = _thread_hook
    _state["unraisable_prior"] = sys.unraisablehook
    sys.unraisablehook = _unraisable_hook
    atexit.register(_exit)
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
    _state["state_at"] = _state["beat"]
    _arm()
    _start_watch()


def stop():
    """Снять сторожа и закрыть журнал. Зовёт unload."""
    timer = _state["timer"]
    if timer is not None:
        timer.stop()
        _state["timer"] = None
        faulthandler.cancel_dump_traceback_later()
    if _state["watch"] is not None:
        _stop_watch()
    if sys.excepthook is _state["hook"]:
        sys.excepthook = _state["prior"]
    _state["hook"] = _state["prior"] = None
    if threading.excepthook is _thread_hook:
        threading.excepthook = _state["thread_prior"]
    if sys.unraisablehook is _unraisable_hook:
        sys.unraisablehook = _state["unraisable_prior"]
    _state["thread_prior"] = _state["unraisable_prior"] = None
    atexit.unregister(_exit)
    if _state["file"] is not None:
        _unmark()
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
