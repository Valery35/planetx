# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тайлы магнитных аномалий EMAG2v3 для planetx-terrain/emag.

    python-qgis.bat tools/build_emag.py EMAG2_V3_UpCont_DataTiff.tif \
        C:/Dev/planetx-terrain

Источник - NOAA NCEI EMAG2v3, аномалия на высоте 4 км над эллипсоидом
(Upward Continued), сетка 2', долготы 0-360, нТл, float32, «нет
данных» - наименьшее float или 99999. Общественное достояние США.

Тайлы Web Mercator уровней 0-core.emag.MAX_LEVEL, 256 пикселей, PNG
в записи Terrarium - значение в нТл равно R * 256 + G + B / 256 - 32768,
«нет данных» - (0, 0, 0). Уровень MAX_LEVEL - билинейная выборка
сетки, мельче - среднее четырёх пикселей детей без пустых. Пустой
тайл не пишется.
"""
import math
import os
import sys

import numpy as np
from osgeo import gdal

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "planetx", "core"))
import emag  # noqa: E402

SIZE = 256


def load(path):
    """Сетка (строки с севера, долготы от -180), шаг, широта первой
    строки."""
    gdal.UseExceptions()
    ds = gdal.Open(path)
    x0, step, _, y0, _, _ = ds.GetGeoTransform()
    grid = ds.GetRasterBand(1).ReadAsArray().astype(np.float32)
    grid[(grid > 9e4) | (grid < -9e4)] = np.nan
    # Долготы 0-360 - сдвиг на половину столбцов к -180..180.
    shift = int(round(180.0 / step))
    grid = np.roll(grid, shift, axis=1)
    west = x0 + step / 2.0 - shift * step
    north = y0 - step / 2.0
    return grid, step, west, north


def sample(grid, step, west, north, z, x, y):
    """Тайл уровня z билинейной выборкой сетки, NaN вне данных."""
    world = SIZE * 2 ** z
    px = (np.arange(SIZE) + 0.5 + x * SIZE) / world
    py = (np.arange(SIZE) + 0.5 + y * SIZE) / world
    lon = px * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * py))))
    fj = (lon - west) / step
    fi = (north - lat) / step
    fj, fi = np.meshgrid(fj, fi)
    j0 = np.floor(fj).astype(int)
    i0 = np.clip(np.floor(fi).astype(int), 0, grid.shape[0] - 2)
    dj = fj - j0
    di = np.clip(fi - i0, 0.0, 1.0)
    cols = grid.shape[1]
    j0 %= cols
    j1 = (j0 + 1) % cols
    a = grid[i0, j0]
    b = grid[i0, j1]
    c = grid[i0 + 1, j0]
    d = grid[i0 + 1, j1]
    return (a * (1 - dj) * (1 - di) + b * dj * (1 - di)
            + c * (1 - dj) * di + d * dj * di).astype(np.float32)


def shrink(children):
    """Тайл родителя из четырёх детей (сз, св, юз, юв): среднее 2 × 2 без
    пустых пикселей."""
    big = np.full((2 * SIZE, 2 * SIZE), np.nan, np.float32)
    for (dx, dy), tile in children.items():
        if tile is not None:
            big[dy * SIZE:(dy + 1) * SIZE, dx * SIZE:(dx + 1) * SIZE] = tile
    blocks = big.reshape(SIZE, 2, SIZE, 2)
    count = np.sum(~np.isnan(blocks), axis=(1, 3))
    total = np.nansum(blocks, axis=(1, 3))
    out = np.full((SIZE, SIZE), np.nan, np.float32)
    has = count > 0
    out[has] = total[has] / count[has]
    return out


def write(tile, path):
    rgb = emag.encode(tile)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mem = gdal.GetDriverByName("MEM").Create("", SIZE, SIZE, 3,
                                             gdal.GDT_Byte)
    for band in range(3):
        mem.GetRasterBand(band + 1).WriteArray(rgb[..., band])
    gdal.GetDriverByName("PNG").CreateCopy(path, mem,
                                           options=["ZLEVEL=9"])


def main(source, terrain):
    grid, step, west, north = load(source)
    out = os.path.join(terrain, "emag")
    top = emag.MAX_LEVEL
    level = {}
    for x in range(2 ** top):
        for y in range(2 ** top):
            tile = sample(grid, step, west, north, top, x, y)
            level[(x, y)] = None if np.all(np.isnan(tile)) else tile
    count = 0
    for z in range(top, -1, -1):
        for (x, y), tile in level.items():
            if tile is None:
                continue
            write(tile, os.path.join(out, str(z), str(x), "%d.png" % y))
            count += 1
        if z == 0:
            break
        parent = {}
        for x in range(2 ** (z - 1)):
            for y in range(2 ** (z - 1)):
                kids = {(dx, dy): level.get((2 * x + dx, 2 * y + dy))
                        for dx in (0, 1) for dy in (0, 1)}
                if all(k is None for k in kids.values()):
                    parent[(x, y)] = None
                else:
                    parent[(x, y)] = shrink(kids)
        level = parent
    print(out, count)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
