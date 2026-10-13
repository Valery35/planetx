# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Файл data/magnetic_poles.json из таблиц NOAA NCEI.

    $PY tools/build_poles.py NP.xy SP.xy

Таблицы «Wandering of the Geomagnetic Poles» - долгота 0-360, широта,
год, строка на год с 1590 года:
https://www.ngdc.noaa.gov/geomag/data/poles/NP.xy и SP.xy.
Долгота в файле модуля - от -180 до 180, по 3 знака после точки.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "planetx", "data", "magnetic_poles.json")


def read(path):
    rows = []
    with open(path, encoding="ascii") as fh:
        for line in fh:
            parts = line.split()
            if len(parts) != 3:
                continue
            lon, lat, year = (float(p) for p in parts)
            lon = (lon + 540.0) % 360.0 - 180.0
            rows.append([round(year, 3), round(lat, 3), round(lon, 3)])
    return sorted(rows)


def main(north, south):
    data = {"source": "NOAA NCEI, Wandering of the Geomagnetic Poles, "
                      "gufm1 and IGRF",
            "north": read(north), "south": read(south)}
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, separators=(",", ":"))
        fh.write("\n")
    print(OUT, os.path.getsize(OUT), len(data["north"]), len(data["south"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
