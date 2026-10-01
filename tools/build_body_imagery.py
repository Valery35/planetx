# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Тайлы снимков тела в сетке Web Mercator из глобальной мозаики.

    $PY tools/build_body_imagery.py мозаика.tif папка 5 [--lon0 -180]

Мозаика - снимок всего шара в простой цилиндрической проекции: GeoTIFF,
ISIS cub или картинка JPG, PNG, TIF без привязки. У GeoTIFF границы
берутся из привязки, в метрах сферы тела или в градусах. У картинки
без привязки считается, что она покрывает долготы от --lon0 до
--lon0 + 360 слева направо и широты от 90 до -90 сверху вниз.

Тайл уровня z - JPEG 256×256, цвет пикселя в его центре, билинейно
из мозаики. Мозаика читается сразу в разрешении, которое нужно уровню
z, поэтому большие файлы не занимают память целиком. Значения
16 бит и дробные приводятся к 8 битам по 0.5 и 99.5 процентилям.
Пустые пиксели (nodata) - чёрные.

Пишутся уровни 0..z в папка/{z}/{x}/{y}.jpg. Папка кладётся
в хранилище planetx-terrain рядом с высотами, модуль читает тайлы
оттуда по одному (core/planets.py).
"""
import math
import os
import sys

import numpy as np
from PIL import Image

SIZE = 256
QUALITY = 85


def read_mosaic(path, level, lon0=-180.0):
    """Мозаика в разрешении уровня level: массив (строки, столбцы,
    каналы) uint8 и границы (запад, север, ширина и высота в градусах)."""
    from osgeo import gdal
    gdal.UseExceptions()
    ds = gdal.Open(path)
    cols, rows = ds.RasterXSize, ds.RasterYSize
    gt = ds.GetGeoTransform(can_return_null=True)
    srs = ds.GetSpatialRef()
    if gt is not None and srs is not None and (gt[1] != 1.0 or gt[0]):
        center = 0.0
        if srs.IsGeographic():
            per = 1.0
        else:
            radius = srs.GetSemiMajor()
            per = radius * math.pi / 180.0
            # У части мозаик USGS центральный меридиан 180°.
            center = srs.GetProjParm("central_meridian", 0.0)
        west = center + gt[0] / per
        north = gt[3] / per
        width = cols * gt[1] / per
        height = -rows * gt[5] / per
    else:
        west, north, width, height = lon0, 90.0, 360.0, 180.0
    # Столбцов нужно столько, сколько пикселей уровня на ширину мозаики.
    want = SIZE * (1 << level) * width / 360.0
    out_cols = int(min(cols, max(64, math.ceil(want * 1.25))))
    out_rows = max(32, int(round(rows * out_cols / cols)))
    bands = min(ds.RasterCount, 3)
    planes = []
    for b in range(1, bands + 1):
        band = ds.GetRasterBand(b)
        data = band.ReadAsArray(buf_xsize=out_cols, buf_ysize=out_rows,
                                resample_alg=gdal.GRIORA_Average)
        nodata = band.GetNoDataValue()
        planes.append(to_byte(data, nodata))
    image = np.stack(planes, axis=-1)
    return image, (west, north, width, height)


def to_byte(data, nodata):
    """Канал в uint8. Байты остаются как есть, прочее - по процентилям."""
    if data.dtype == np.uint8:
        return data
    data = data.astype(np.float64)
    valid = np.isfinite(data)
    if nodata is not None:
        valid &= data != nodata
    if not valid.any():
        return np.zeros(data.shape, np.uint8)
    low, high = np.percentile(data[valid], (0.5, 99.5))
    scaled = (data - low) / max(high - low, 1e-12) * 255.0
    scaled[~valid] = 0.0
    return np.clip(scaled, 0, 255).astype(np.uint8)


def tile_latlon(z, x, y):
    """Широта и долгота центров пикселей тайла, два массива 256×256."""
    n = 1 << z
    i = (np.arange(SIZE) + 0.5) / SIZE
    lon = (x + i) / n * 360.0 - 180.0
    merc = math.pi * (1.0 - 2.0 * (y + i) / n)
    lat = np.degrees(np.arctan(np.sinh(merc)))
    return np.meshgrid(lat, lon, indexing="ij")


def sample(image, bounds, lat, lon):
    """Цвет мозаики в точках, билинейно, долгота по кругу."""
    west, north, width, height = bounds
    rows, cols = image.shape[:2]
    c = ((lon - west) % 360.0) * cols / width - 0.5
    r = np.clip((north - lat) * rows / height - 0.5, 0.0, rows - 1.001)
    c0 = np.floor(c).astype(np.int64)
    r0 = np.floor(r).astype(np.int64)
    fc = (c - c0)[..., None]
    fr = (r - r0)[..., None]
    wrap = width >= 359.999
    if wrap:
        c0 %= cols
        c1 = (c0 + 1) % cols
    else:
        c0 = np.clip(c0, 0, cols - 1)
        c1 = np.minimum(c0 + 1, cols - 1)
    r1 = np.minimum(r0 + 1, rows - 1)
    # Во float переводятся только нужные пиксели, а не вся мозаика.
    def at(r, c):
        return image[r, c].astype(np.float32)
    top = at(r0, c0) * (1 - fc) + at(r0, c1) * fc
    low = at(r1, c0) * (1 - fc) + at(r1, c1) * fc
    return np.clip(top * (1 - fr) + low * fr + 0.5, 0, 255).astype(np.uint8)


def build(path, out, level, lon0=-180.0):
    image, bounds = read_mosaic(path, level, lon0)
    print(os.path.basename(path), image.shape, "границы", bounds)
    mode = "L" if image.shape[2] == 1 else "RGB"
    count = 0
    total = 0
    for z in range(level + 1):
        n = 1 << z
        for x in range(n):
            folder = os.path.join(out, str(z), str(x))
            os.makedirs(folder, exist_ok=True)
            for y in range(n):
                lat, lon = tile_latlon(z, x, y)
                rgb = sample(image, bounds, lat, lon)
                if mode == "L":
                    rgb = rgb[..., 0]
                name = os.path.join(folder, "%d.jpg" % y)
                Image.fromarray(rgb, mode).save(name, quality=QUALITY,
                                                optimize=True)
                count += 1
                total += os.path.getsize(name)
    print("тайлов %d, %.1f МБ" % (count, total / 1e6))


if __name__ == "__main__":
    args = sys.argv[1:]
    lon0 = -180.0
    if "--lon0" in args:
        i = args.index("--lon0")
        lon0 = float(args[i + 1])
        del args[i:i + 2]
    if len(args) != 3:
        sys.exit(__doc__)
    build(args[0], args[1], int(args[2]), lon0)
