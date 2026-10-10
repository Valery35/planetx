# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Стеки потоков дампа зависания QGIS без отладчика.

    $PY tools/hang_dump.py путь\\hang-<pid>-<время>.dmp [кадров]

Дамп пишет журнал модуля, когда главный поток QGIS молчит дольше
journal.DUMP_AFTER секунд. Имена функций берутся из файлов модулей
по путям в дампе, поэтому разбор точен на той же машине и той же
сборке QGIS. Журнал уже содержит такой разбор, сценарий нужен для
повторного с другим количеством кадров.
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                "..", "planetx", "core"))
import minidump  # noqa: E402


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    frames = int(sys.argv[2]) if len(sys.argv) > 2 else minidump.FRAMES
    print(minidump.report(sys.argv[1], frames=frames))
    return 0


if __name__ == "__main__":
    sys.exit(main())
