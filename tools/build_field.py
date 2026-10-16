# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тайлы карты значений (core/fields.py) для planetx-terrain.

    python-qgis.bat tools/build_field.py <ключ> <сетка> C:/Dev/planetx-terrain

Сетка - любой растр GDAL в градусах, одна полоса. Долготы 0-360
сдвигаются к -180..180. «Нет данных» - значение NoData полосы или NaN.
Тайлы Web Mercator уровней 0-max_level карты, 256 пикселей, PNG в записи
Terrarium со множителем карты (fields.encode). Глубший уровень -
билинейная выборка сетки, мельче - среднее четырёх пикселей детей без
пустых. Пустой тайл не пишется.

Особые случаи источников - PREPARE: обрезка, своя привязка.
"""
import os
import sys

import numpy as np
from osgeo import gdal

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "planetx", "core"))
import build_emag  # noqa: E402
import fields  # noqa: E402


def load(path):
    """Сетка (строки с севера, долготы от -180), шаг, долгота и широта
    середины первого узла."""
    gdal.UseExceptions()
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    grid = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        grid[grid == np.float32(nodata)] = np.nan
    x0, dx, _, y0, _, dy = ds.GetGeoTransform()
    if dy > 0:
        grid = grid[::-1]
        y0 = y0 + dy * ds.RasterYSize
        dy = -dy
    return grid, dx, x0 + dx / 2.0, y0 + dy / 2.0, -dy


def heatflow(grid, step, west, north, step_y):
    """Сетка IHFC 2024 (кригинг, 720 × 360). Узлы файла - 720 долгот
    от -360° до 0° и 360 широт от -90° до 90° с концами включительно
    (переменные longitude и latitude), отсюда шаг 0.5007° и 0.5014°.
    Сетка пересчитывается билинейно на середины клеток 0.5° от -180°
    и от 90°. Отрицательные значения - след кригинга, они обрезаются."""
    rows, cols = grid.shape
    assert (rows, cols) == (360, 720), grid.shape
    # Строки load - с севера: широта строки r = 90 - r·180/359.
    lon_t = np.arange(cols) * 0.5 - 179.75
    lat_t = 89.75 - np.arange(rows) * 0.5
    fc = ((lon_t + 360.0) % 360.0) / 360.0 * (cols - 1)
    fr = (90.0 - lat_t) / 180.0 * (rows - 1)
    c0 = np.floor(fc).astype(int)
    r0 = np.clip(np.floor(fr).astype(int), 0, rows - 2)
    c1 = np.minimum(c0 + 1, cols - 1)
    dc = (fc - c0)[None, :]
    dr = (fr - r0)[:, None]
    a = grid[r0][:, c0]
    b = grid[r0][:, c1]
    c = grid[r0 + 1][:, c0]
    d = grid[r0 + 1][:, c1]
    out = (a * (1 - dc) * (1 - dr) + b * dc * (1 - dr)
           + c * (1 - dc) * dr + d * dc * dr).astype(np.float32)
    out = np.where(out < 0.0, 0.0, out)
    return out, 0.5, -179.75, 89.75, 0.5


PREPARE = {"heatflow": heatflow}


def normalize(grid, step, west, north, step_y):
    """Долготы к -180..180: сетка 0-360 сдвигается на половину."""
    if west > 0.0 and west + step * grid.shape[1] > 181.0:
        shift = int(round(180.0 / step))
        grid = np.roll(grid, shift, axis=1)
        west -= shift * step
    # Повтор долготы 180 у сетки по узлам - последний столбец лишний.
    if abs(west + step * (grid.shape[1] - 1) - 180.0) < step / 2.0 \
            and abs(west + 180.0) < step / 2.0:
        grid = grid[:, :-1]
    return grid, step, west, north, step_y


def write(field, tile, path):
    rgb = fields.encode(tile, field.scale)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    size = build_emag.SIZE
    mem = gdal.GetDriverByName("MEM").Create("", size, size, 3,
                                             gdal.GDT_Byte)
    for band in range(3):
        mem.GetRasterBand(band + 1).WriteArray(rgb[..., band])
    gdal.GetDriverByName("PNG").CreateCopy(path, mem,
                                           options=["ZLEVEL=9"])


def main(key, source, terrain):
    field = fields.FIELDS[key]
    data = load(source)
    if key in PREPARE:
        data = PREPARE[key](*data)
    grid, step, west, north, step_y = normalize(*data)
    # Выборка build_emag.sample - один шаг по широте и долготе.
    assert abs(step - step_y) < 1e-6 * step, (step, step_y)
    out = os.path.join(terrain, field.folder)
    top = field.max_level
    level = {}
    for x in range(2 ** top):
        for y in range(2 ** top):
            tile = build_emag.sample(grid, step, west, north, top, x, y)
            level[(x, y)] = None if np.all(np.isnan(tile)) else tile
    count = 0
    for z in range(top, -1, -1):
        for (x, y), tile in level.items():
            if tile is None:
                continue
            write(field, tile, os.path.join(out, str(z), str(x),
                                            "%d.png" % y))
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
                    parent[(x, y)] = build_emag.shrink(kids)
        level = parent
    print(out, count)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3])
