# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Указатель файлов AlphaEarth Foundations по зонам UTM для
planetx-terrain/aef (core/aef.py).

У Google указатель - aef_index.parquet, около 70 МБ на все годы, модулю
он велик. Сценарий читает его GDAL (драйвер Parquet есть в QGIS 4)
и пишет по файлу на зону: квадраты 81 920 м западным и северным краем
и имена файлов по годам. Запуск - Python из состава QGIS 4 с GDAL:

    python-qgis.bat tools/build_aef_index.py aef_index.parquet ВЫХОД

Без GDAL принимается и CSV без геометрии (ogr2ogr -f CSV ... -select
path,year,utm_zone,utm_west,utm_north).
"""
import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "planetx", "core"))
import aef  # noqa: E402

FIELDS = ("path", "year", "utm_zone", "utm_west", "utm_north")


def rows_from(path):
    if path.lower().endswith(".csv"):
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                yield (row["path"], int(row["year"]), row["utm_zone"],
                       float(row["utm_west"]), float(row["utm_north"]))
        return
    from osgeo import ogr
    source = ogr.Open(path)
    layer = source.GetLayer(0)
    for feature in layer:
        yield tuple(feature.GetField(name) for name in FIELDS)


def main(source, out):
    zones = aef.build_index(rows_from(source))
    os.makedirs(out, exist_ok=True)
    total = 0
    for zone, doc in sorted(zones.items()):
        path = os.path.join(out, zone + ".json")
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            json.dump(doc, f, ensure_ascii=False, separators=(",", ":"))
        total += os.path.getsize(path)
    print("zones", len(zones), "bytes", total)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
