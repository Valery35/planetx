# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Демо «Карьер»: синтетическая съёмка карьера у Березников.

    $PY tools/make_quarry_demo.py

Пишет planetx/demo/quarry/quarry_dem.tif - растр высот 1 м в UTM 40N
(EPSG:32640), 2.4 × 2.4 км. Вокруг карьера высоты - рельеф Terrarium
уровня 15 той же местности, поэтому полоса края переходит без скачка.
Карьер - эллипс 1400 × 1000 м по верху, 10 уступов по 15 м с откосом
60° и бермой 25 м, дно на 150 м ниже бровки. К северо-востоку - отвал
высотой 40 м с двумя ярусами. Карьер и отвал выдуманы, место, размеры
и уступы - выбор помощника.
"""
import math
import os
import sys
import urllib.request

import numpy as np
from osgeo import gdal, osr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "planetx", "demo", "quarry", "quarry_dem.tif")
TERRARIUM = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
             "{z}/{x}/{y}.png")
AGENT = "PlanetX (+https://github.com/Valery35/planetx)"

CENTER = (59.490, 56.970)  # широта, долгота центра карьера
SIDE = 2400  # м, сторона растра
PIXEL = 1.0  # м
PIT = (700.0, 500.0)  # полуоси эллипса по верху, м
BENCHES = 10
BENCH_HEIGHT = 15.0  # м
FACE = math.radians(60.0)  # откос уступа
BERM = 25.0  # м
DUMP = (760.0, 640.0, 300.0, 40.0)  # отвал: сдвиг на восток и север,
# радиус основания, высота, м
LEVEL = 15

gdal.UseExceptions()


def terrarium(z, x, y):
    req = urllib.request.Request(TERRARIUM.format(z=z, x=x, y=y),
                                 headers={"User-Agent": AGENT})
    data = urllib.request.urlopen(req, timeout=60).read()
    path = "/vsimem/t.png"
    gdal.FileFromMemBuffer(path, data)
    ds = gdal.Open(path)
    rgb = np.stack([ds.GetRasterBand(b).ReadAsArray().astype(np.float64)
                    for b in (1, 2, 3)])
    ds = None
    gdal.Unlink(path)
    return rgb[0] * 256.0 + rgb[1] + rgb[2] / 256.0 - 32768.0


def ground(lats, lons):
    """Высоты Terrarium уровня LEVEL в точках, билинейно."""
    n = 1 << LEVEL
    u = (lons + 180.0) / 360.0 * n * 256.0 - 0.5
    v = (1.0 - np.arcsinh(np.tan(np.radians(lats))) / math.pi) / 2.0 \
        * n * 256.0 - 0.5
    x0, x1 = int(u.min() // 256), int(u.max() // 256) + 1
    y0, y1 = int(v.min() // 256), int(v.max() // 256) + 1
    mosaic = np.zeros(((y1 - y0 + 1) * 256, (x1 - x0 + 1) * 256))
    for ty in range(y0, y1 + 1):
        for tx in range(x0, x1 + 1):
            mosaic[(ty - y0) * 256:(ty - y0 + 1) * 256,
                   (tx - x0) * 256:(tx - x0 + 1) * 256] = \
                terrarium(LEVEL, tx, ty)
    px = np.clip(u - x0 * 256, 0, mosaic.shape[1] - 1.001)
    py = np.clip(v - y0 * 256, 0, mosaic.shape[0] - 1.001)
    ix, iy = px.astype(int), py.astype(int)
    fx, fy = px - ix, py - iy
    top = mosaic[iy, ix] * (1 - fx) + mosaic[iy, ix + 1] * fx
    bottom = mosaic[iy + 1, ix] * (1 - fx) + mosaic[iy + 1, ix + 1] * fx
    return top * (1 - fy) + bottom * fy


def pit_depth(d):
    """Понижение под бровкой на эллиптическом расстоянии d от оси, м:
    уступы с откосом и бермой от края к дну."""
    step = BENCH_HEIGHT / math.tan(FACE) + BERM
    inward = PIT[0] - d  # м от бровки внутрь
    inward = np.maximum(inward, 0.0)
    bench = np.floor(inward / step)
    within = inward - bench * step
    face = BENCH_HEIGHT / math.tan(FACE)
    drop = bench * BENCH_HEIGHT + np.minimum(within, face) * math.tan(FACE)
    return np.minimum(drop, BENCHES * BENCH_HEIGHT)


def main():
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(32640)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to_utm = osr.CoordinateTransformation(wgs, utm)
    cx, cy, _ = to_utm.TransformPoint(CENTER[1], CENTER[0])
    size = int(SIDE / PIXEL)
    west, north = cx - SIDE / 2.0, cy + SIDE / 2.0
    # Рельеф вокруг - на сетке 10 м, на сетку 1 м билинейно.
    coarse = size // 10 + 1
    gx = west + np.arange(coarse) * 10.0
    gy = north - np.arange(coarse) * 10.0
    xx, yy = np.meshgrid(gx, gy)
    back = osr.CoordinateTransformation(utm, wgs)
    pts = back.TransformPoints(np.column_stack([xx.ravel(), yy.ravel()]))
    pts = np.asarray(pts)
    base = ground(pts[:, 1], pts[:, 0]).reshape(coarse, coarse)
    idx = (np.arange(size) + 0.5) * PIXEL / 10.0
    i0 = np.minimum(idx.astype(int), coarse - 2)
    f = idx - i0
    rows = base[i0] * (1 - f)[:, None] + base[i0 + 1] * f[:, None]
    heights = rows[:, i0] * (1 - f)[None, :] + rows[:, i0 + 1] * f[None, :]
    # Карьер: бровка на высоте рельефа по контуру, дно на 150 м ниже.
    ex = (np.arange(size) + 0.5) * PIXEL - SIDE / 2.0
    ey = SIDE / 2.0 - (np.arange(size) + 0.5) * PIXEL
    ox, oy = np.meshgrid(ex, ey)
    d = np.sqrt((ox / PIT[0]) ** 2 + (oy / PIT[1]) ** 2) * PIT[0]
    rim = float(np.median(heights[d <= PIT[0]]))
    inside = d < PIT[0]
    heights = np.where(inside, np.minimum(heights, rim - pit_depth(d)),
                       heights)
    # Отвал: два яруса по 20 м с откосом 35°.
    dx, dy, radius, high = DUMP
    r = np.sqrt((ox - dx) ** 2 + (oy - dy) ** 2)
    slope = math.tan(math.radians(35.0))
    tier = np.minimum(np.maximum(radius - r, 0.0) * slope, high / 2.0)
    tier2 = np.minimum(np.maximum(radius - 120.0 - r, 0.0) * slope,
                       high / 2.0)
    heights = heights + tier + tier2
    heights = np.round(heights, 2).astype(np.float32)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    drv = gdal.GetDriverByName("GTiff")
    out = drv.Create(OUT, size, size, 1, gdal.GDT_Float32,
                     ["TILED=YES", "COMPRESS=DEFLATE", "PREDICTOR=3",
                      "ZLEVEL=9"])
    out.SetGeoTransform((west, PIXEL, 0.0, north, 0.0, -PIXEL))
    out.SetProjection(utm.ExportToWkt())
    band = out.GetRasterBand(1)
    band.WriteArray(heights)
    band.SetNoDataValue(-9999.0)
    out = None
    print(OUT, os.path.getsize(OUT), "rim", round(rim, 1),
          "low", float(heights.min()), "high", float(heights.max()))


if __name__ == "__main__":
    sys.exit(main())
