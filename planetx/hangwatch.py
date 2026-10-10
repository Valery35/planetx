# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сторож зависания QGIS отдельным процессом.

    pythonw hangwatch.py <pid> <файл отметок> <журнал> <папка> <секунд>
        <заголовок> <главный поток> <поток> <потоки ожидания>

Заголовок - строка с местами {seconds} и {path}, подписи - на языке
интерфейса, их передаёт журнал.

Журнал модуля (journal.py) запускает его при загрузке модуля и раз
в секунду трогает файл отметок из главного потока QGIS. Если отметки
нет дольше заданного числа секунд, сторож снимает дамп процесса QGIS
со стеками всех потоков (MiniDumpWriteDump снаружи), разбирает его
core/minidump.py и дописывает разбор в журнал. Один дамп на
зависание. Сторож внутри QGIS этого не может, когда главный поток
стоит в вызове C++, не отпустив GIL: 10 октября 2026 года так повис
проверочный QGIS в LayerOverlay.abort, и дампа не было.

Сторож заканчивает работу, когда процесса QGIS нет или файла отметок
нет - его удаляет выгрузка модуля. Только Windows, Qt не нужен.
"""
import ctypes
import importlib.util
import os
import sys
import time


def _load_minidump():
    """core/minidump.py рядом с файлом - сторож идёт отдельным процессом,
    вне пакета модуля."""
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "core", "minidump.py")
    spec = importlib.util.spec_from_file_location("planetx_minidump", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


minidump = _load_minidump()

STEP = 2.0  # с между проверками
KEPT = 3  # дампов зависаний в папке
STILL_ACTIVE = 259
DUMP_TYPE = 0x0000 | 0x1000 | 0x0020


def kernel():
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = ctypes.c_void_p
    k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
    k.GetExitCodeProcess.argtypes = [ctypes.c_void_p,
                                     ctypes.POINTER(ctypes.c_ulong)]
    k.CloseHandle.argtypes = [ctypes.c_void_p]
    return k


def alive(k, handle):
    code = ctypes.c_ulong()
    ok = k.GetExitCodeProcess(handle, ctypes.pointer(code))
    return bool(ok) and code.value == STILL_ACTIVE


def dump(handle, pid, name):
    import msvcrt
    write = ctypes.WinDLL("dbghelp", use_last_error=True).MiniDumpWriteDump
    write.argtypes = [ctypes.c_void_p, ctypes.c_ulong, ctypes.c_void_p,
                      ctypes.c_ulong, ctypes.c_void_p, ctypes.c_void_p,
                      ctypes.c_void_p]
    write.restype = ctypes.c_int
    with open(name, "wb") as fh:
        ok = write(handle, pid, msvcrt.get_osfhandle(fh.fileno()),
                   DUMP_TYPE, None, None, None)
    if not ok:
        os.remove(name)
    return bool(ok)


def note(log, text):
    with open(log, "a", encoding="utf-8") as fh:
        fh.write("{}  {}\n".format(time.strftime("%Y-%m-%d %H:%M:%S"), text))


def prune(folder):
    found = sorted((os.path.join(folder, n) for n in os.listdir(folder)
                    if n.startswith("hang-") and n.endswith(".dmp")),
                   key=os.path.getmtime)
    for name in found[:-KEPT]:
        os.remove(name)


def main(argv):
    pid, beat, log, folder, after = (int(argv[1]), argv[2], argv[3],
                                     argv[4], float(argv[5]))
    header, main_label, label, idle = (argv[6:10] + [
        "Main thread of QGIS silent {seconds} s, process dump {path}",
        "Main thread", "Thread", "Waiting threads"][len(argv[6:10]):])
    k = kernel()
    handle = k.OpenProcess(0x0400 | 0x0010, 0, pid)
    if not handle:
        return 1
    dumped = None
    while alive(k, handle) and os.path.exists(beat):
        time.sleep(STEP)
        try:
            stamp = os.path.getmtime(beat)
        except FileNotFoundError:
            return 0
        except OSError as error:
            note(log, "hang watch: {}".format(error))
            return 1
        silent = time.time() - stamp
        if silent < after or dumped == stamp:
            continue
        dumped = stamp
        name = os.path.join(folder, "hang-{}-{}.dmp".format(
            pid, time.strftime("%Y%m%d-%H%M%S")))
        try:
            if not dump(handle, pid, name):
                note(log, "hang watch: dump failed")
                continue
            note(log, header.format(seconds=round(silent), path=name)
                 + "\n" + minidump.report(name, main_label, label, idle))
            prune(folder)
        except (OSError, ValueError) as error:
            note(log, "hang watch: {}".format(error))
    k.CloseHandle(handle)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
