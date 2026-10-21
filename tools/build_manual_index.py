# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разделы руководства для поиска в строке «Поиск».

doc/MANUAL.md и doc/MANUAL.en.md режутся по заголовкам
(core/manualindex.sections) в planetx/data/manual_ru.json
и manual_en.json. Запускается после правки руководства, сторож -
test_manualindex.test_data_matches_manual.

    $PY tools/build_manual_index.py
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))

import manualindex  # noqa: E402

PAIRS = (("MANUAL.md", "manual_ru.json"), ("MANUAL.en.md", "manual_en.json"))


def build(source):
    with open(source, encoding="utf-8") as handle:
        return manualindex.sections(handle.read())


def text_of(items):
    """Текст файла указателя: по разделу на строку, без лишних пробелов."""
    return "[\n" + ",\n".join(json.dumps(item, ensure_ascii=False)
                              for item in items) + "\n]\n"


def main():
    for manual, data in PAIRS:
        items = build(os.path.join(ROOT, "doc", manual))
        target = os.path.join(ROOT, "planetx", "data", data)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text_of(items))
        print(data, len(items), os.path.getsize(target))


if __name__ == "__main__":
    main()
