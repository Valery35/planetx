# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Указатель руководств модулей линейки для бота: bot/data.

Руководства берутся из рабочих копий хранилищ рядом с planetx
(C:\\Dev\\<хранилище>), разделы режет core/manualindex.py.
manuals_<язык>.json - {"plugins": [хранилище на раздел],
"paths": {хранилище: путь файла}, "sections": [[заголовок, якорь,
текст]]}. После правки руководства любого модуля указатель собирается
заново, затем архив бота bot/make_bundle.py.
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEV = os.path.dirname(ROOT)
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))
import manualindex  # noqa: E402

# Хранилище - файл руководства по-русски и по-английски.
MANUALS = {
    "planetx": ("doc/MANUAL.md", "doc/MANUAL.en.md"),
    "qgis-isoliner": ("manual/manual.md", "manual/manual_en.md"),
    "qgis-isoliner3d": ("manual/manual.md", "manual/manual_en.md"),
    "topoliner": ("doc/MANUAL.md", "doc/MANUAL.en.md"),
    "routeliner": ("manual/manual.md", "manual/manual_en.md"),
    "repoliner": ("README_ru.md", "README.md"),
}


def folder(repo):
    return ROOT if repo == "planetx" else os.path.join(DEV, repo)


def main():
    out_dir = os.path.join(HERE, "data")
    os.makedirs(out_dir, exist_ok=True)
    for n, lang in enumerate(("ru", "en")):
        plugins, sections, paths = [], [], {}
        for repo, files in MANUALS.items():
            path = os.path.join(folder(repo), *files[n].split("/"))
            if not os.path.exists(path):
                print("нет файла", path)
                continue
            with open(path, encoding="utf-8") as f:
                found = manualindex.sections(f.read())
            paths[repo] = files[n]
            plugins.extend([repo] * len(found))
            sections.extend(found)
            print(lang, repo, len(found))
        out = os.path.join(out_dir, "manuals_{}.json".format(lang))
        with open(out, "w", encoding="utf-8") as f:
            json.dump({"plugins": plugins, "paths": paths,
                       "sections": sections}, f, ensure_ascii=False,
                      separators=(",", ":"))
        print(out, os.path.getsize(out))


if __name__ == "__main__":
    main()
