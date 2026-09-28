# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Файл звёзд planetx/data/stars.npy из каталога ярких звёзд BSC5.

    python tools/build_stars.py bsc5.dat.gz

Каталог - Yale Bright Star Catalogue, 5-е издание (Hoffleit, Warren,
1991), CDS V/50, копия http://tdc-www.harvard.edu/catalogs/bsc5.dat.gz.
Строка каталога - 197 символов, поля по описанию ReadMe CDS V/50.
В файл идут звёзды до величины stars.MAX_MAG: прямое восхождение
и склонение J2000 в радианах, видимая величина, B-V. Нет B-V - NaN.
"""
import gzip
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))

import stars  # noqa: E402

TARGET = os.path.join(ROOT, "planetx", "data", "stars.npy")


def field(line, first, last):
    """Поле по номерам символов ReadMe, с единицы, включительно."""
    return line[first - 1:last].strip()


def parse(line):
    """(ra, dec, mag, bv) или None, если у строки нет координат."""
    if not field(line, 76, 77) or not field(line, 103, 107):
        return None
    ra = (int(field(line, 76, 77)) + int(field(line, 78, 79)) / 60.0
          + float(field(line, 80, 83)) / 3600.0) * 15.0
    dec = (int(field(line, 85, 86)) + int(field(line, 87, 88)) / 60.0
           + int(field(line, 89, 90)) / 3600.0)
    if field(line, 84, 84) == "-":
        dec = -dec
    bv = field(line, 110, 114)
    return (math.radians(ra), math.radians(dec),
            float(field(line, 103, 107)), float(bv) if bv else math.nan)


def main(source):
    rows = []
    with gzip.open(source, "rt", encoding="ascii") as lines:
        for line in lines:
            row = parse(line.rstrip("\n").ljust(197))
            if row is not None and row[2] <= stars.MAX_MAG:
                rows.append(row)
    table = np.array(rows, dtype=np.float32)
    os.makedirs(os.path.dirname(TARGET), exist_ok=True)
    np.save(TARGET, table, allow_pickle=False)
    print("звёзд %d, ярче 1-й величины %d, файл %.0f КБ"
          % (len(table), int((table[:, 2] < 1.0).sum()),
             os.path.getsize(TARGET) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
