# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты палеогеографии для хранилища planetx-terrain.

    $PY tools/build_paleo.py СЕТКИ ХРАНИЛИЩЕ [ВОЗРАСТ ...]

СЕТКИ - папка распакованного архива
Scotese_Wright_2018_Maps_1-88_6minX6min_PaleoDEMS_nc.zip (PALEOMAP
PaleoDEM, Scotese & Wright 2018, CC BY 4.0, zenodo.org/records/5460860):
файлы netCDF *_<возраст>Ma.nc, сетка 3601 × 1801 через 0.1°, высоты
и глубины в метрах. Читаются через GDAL из Python QGIS.

На каждый возраст сетка красится по высотам с отмывкой
(core.paleo.picture), потом билинейно переводится в тайлы JPEG
Web Mercator 256 × 256 уровней 0..core.paleo.MAX_LEVEL:
ХРАНИЛИЩЕ/paleo/paleomap/<возраст>/{z}/{x}/{y}.jpg и указатель
ХРАНИЛИЩЕ/paleo/paleomap/index.json. Без списка возрастов нарезаются
все. Прежние маски суши Merdith 2021 модуль больше не читает, решение
автора от 5 октября 2026 года.
"""
import glob
import json
import math
import os
import re
import sys
import time

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "planetx", "core"))
import paleo  # noqa: E402

SIZE = 256
QUALITY = 82
STEP = 0.1  # градусов, шаг сетки


def grids(folder):
    """Файлы сеток по возрасту, млн лет."""
    out = {}
    for path in glob.glob(os.path.join(folder, "*.nc")):
        found = re.search(r"_(\d+(?:\.\d+)?)Ma\.nc$", path)
        if found:
            out[int(round(float(found.group(1))))] = path
    return out


def read(path):
    """Сетка высот (строки с севера, столбцы с долготы -180), float32."""
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(path)
    band = ds.GetRasterBand(1)
    z = band.ReadAsArray().astype(np.float32)
    nodata = band.GetNoDataValue()
    if nodata is not None:
        z[np.abs(z) >= abs(nodata) * 0.5] = 0.0
    origin_lat = ds.GetGeoTransform()[3]
    if origin_lat < 0.0:
        z = z[::-1]
    return z


def sample(image, lat, lon):
    """Цвет точек (lat, lon) из картинки сетки, билинейно. Узел (i, j)
    сетки стоит на широте 90 - i·STEP и долготе -180 + j·STEP."""
    rows, cols = image.shape[:2]
    fy = (90.0 - lat) / STEP
    fx = (lon + 180.0) / STEP
    y0 = np.clip(np.floor(fy).astype(int), 0, rows - 2)
    x0 = np.floor(fx).astype(int)
    wy = np.clip(fy - y0, 0.0, 1.0)[..., None]
    wx = (fx - x0)[..., None]
    # Узел 3600 повторяет узел 0, долгота замкнута.
    width = cols - 1
    x0 %= width
    x1 = (x0 + 1) % width
    top = image[y0, x0] * (1.0 - wx) + image[y0, x1] * wx
    low = image[y0 + 1, x0] * (1.0 - wx) + image[y0 + 1, x1] * wx
    return top * (1.0 - wy) + low * wy


def tile(image, z, x, y):
    """Тайл z/x/y: цвет в центрах пикселей."""
    n = 2 ** z
    px = (np.arange(SIZE) + 0.5) / SIZE
    lon = (x + px) / n * 360.0 - 180.0
    merc = math.pi * (1.0 - 2.0 * (y + px) / n)
    lat = np.degrees(np.arctan(np.sinh(merc)))
    lon_grid, lat_grid = np.meshgrid(lon, lat)
    rgb = sample(image, lat_grid, lon_grid)
    return np.clip(np.rint(rgb), 0, 255).astype(np.uint8)


def build(path, folder):
    """Тайлы одного возраста в папку folder."""
    picture = paleo.picture(read(path), STEP).astype(np.float32)
    count = 0
    for z in range(paleo.MAX_LEVEL + 1):
        for x in range(2 ** z):
            out = os.path.join(folder, str(z), str(x))
            os.makedirs(out, exist_ok=True)
            for y in range(2 ** z):
                Image.fromarray(tile(picture, z, x, y)).save(
                    os.path.join(out, "{}.jpg".format(y)),
                    quality=QUALITY, optimize=True)
                count += 1
    return count


def main(argv):
    if len(argv) < 2:
        print(__doc__)
        return 2
    source, store = argv[0], argv[1]
    found = grids(source)
    ages = [int(a) for a in argv[2:]] or sorted(found)
    base = os.path.join(store, "paleo", "paleomap")
    for age in ages:
        started = time.monotonic()
        count = build(found[age], os.path.join(base, str(age)))
        print("{} млн лет: тайлов {}, {:.1f} с".format(
            age, count, time.monotonic() - started), flush=True)
    index = {"source": "PALEOMAP PaleoDEM, Scotese & Wright 2018",
             "license": "CC BY 4.0",
             "doi": "10.5281/zenodo.5460860",
             "ages": sorted(int(a) for a in os.listdir(base)
                            if a.isdigit()),
             "max_level": paleo.MAX_LEVEL}
    with open(os.path.join(base, "index.json"), "w", encoding="utf-8",
              newline="\n") as stream:
        json.dump(index, stream, ensure_ascii=False, indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
