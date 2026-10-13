# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тайлы геоида EGM2008 для planetx-terrain/geoid.

    python-qgis.bat tools/build_geoid.py egm2008-5.pgm C:/Dev/planetx-terrain

Источник - сетка GeographicLib egm2008-5.pgm (EGM2008 NGA, шаг 5',
узлы с 90° с. ш. и 0° в. д.). Тайлы Web Mercator уровней
0-core.geoid.MAX_LEVEL в записи Terrarium, метры. Выборка и уровни -
как у tools/build_emag.py.
"""
import os
import sys

import numpy as np
from osgeo import gdal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "planetx", "core"))
import build_emag  # noqa: E402
import geoid  # noqa: E402

SIZE = build_emag.SIZE


def write(heights, path):
    rgb = geoid.encode(heights)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mem = gdal.GetDriverByName("MEM").Create("", SIZE, SIZE, 3,
                                             gdal.GDT_Byte)
    for band in range(3):
        mem.GetRasterBand(band + 1).WriteArray(rgb[..., band])
    gdal.GetDriverByName("PNG").CreateCopy(path, mem,
                                           options=["ZLEVEL=9"])


def main(source, terrain):
    gdal.UseExceptions()
    with open(source, "rb") as fh:
        grid, step = geoid.read_pgm(fh.read())
    # Узлы: столбец j - долгота j * step от 0°. Сдвиг к -180..180.
    shift = int(round(180.0 / step))
    grid = np.roll(grid.astype(np.float32), shift, axis=1)
    west, north = -180.0, 90.0
    out = os.path.join(terrain, "geoid")
    top = geoid.MAX_LEVEL
    level = {(x, y): build_emag.sample(grid, step, west, north, top, x, y)
             for x in range(2 ** top) for y in range(2 ** top)}
    count = 0
    for z in range(top, -1, -1):
        for (x, y), tile in level.items():
            write(tile, os.path.join(out, str(z), str(x), "%d.png" % y))
            count += 1
        if z == 0:
            break
        level = {(x, y): build_emag.shrink(
            {(dx, dy): level[(2 * x + dx, 2 * y + dy)]
             for dx in (0, 1) for dy in (0, 1)})
            for x in range(2 ** (z - 1)) for y in range(2 ** (z - 1))}
    print(out, count, float(np.nanmin(grid)), float(np.nanmax(grid)))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
