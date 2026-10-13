# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Магнитные аномалии EMAG2v3 - тайлы значений и раскраска.

Сетка NOAA NCEI EMAG2v3 (2017), аномалия полного поля на высоте 4 км
над эллипсоидом, шаг 2', общественное достояние США. Тайлы уровней
0-MAX_LEVEL режет tools/build_emag.py в planetx-terrain/emag в записи
Terrarium: нТл = R * 256 + G + B / 256 - 32768, «нет данных» -
(0, 0, 0). Модуль раскрашивает тайл в рабочем потоке (rgba), значение
под щелчком берёт из того же тайла (value_at).

Модуль Qt не знает.
"""
import math

import numpy as np

MAX_LEVEL = 5
TILE_URL = ("https://raw.githubusercontent.com/Valery35/planetx-terrain/"
            "main/emag/{z}/{x}/{y}.png")
ATTRIBUTION = ("EMAG2v3, NOAA NCEI", "https://www.ncei.noaa.gov/products/"
               "earth-magnetic-model-anomaly-grid-2")
EMPTY = -32768.0
# Раскраска, нТл: синие - поле слабее нормального, красные - сильнее.
# Пределы по 1-му и 99-му процентилям сетки, -223 и +294 нТл. Цвета -
# выбор помощника, утверждает автор.
STOPS = ((-250.0, (40, 60, 150)), (-120.0, (70, 130, 210)),
         (-40.0, (165, 205, 235)), (0.0, (245, 245, 235)),
         (40.0, (245, 205, 165)), (120.0, (225, 115, 70)),
         (250.0, (160, 30, 35)))
OPACITY = 0.8
SIZE = 256


def encode(values):
    """Массив нТл (NaN - нет данных) в RGB uint8 записи Terrarium."""
    values = np.asarray(values, dtype=np.float64)
    code = np.clip(np.round(values) + 32768.0, 1.0, 65535.0)
    code = np.where(np.isnan(values), 0.0, code).astype(np.int64)
    rgb = np.zeros(values.shape + (3,), np.uint8)
    rgb[..., 0] = code >> 8
    rgb[..., 1] = code & 255
    return rgb


def decode(rgb):
    """RGB (строки, столбцы, 3+) в нТл, NaN - нет данных."""
    rgb = np.asarray(rgb)
    values = rgb[..., 0].astype(np.float32) * 256.0 \
        + rgb[..., 1].astype(np.float32) \
        + rgb[..., 2].astype(np.float32) / 256.0 + EMPTY
    values[values <= EMPTY + 0.5] = np.nan
    return values


def colors(values):
    """нТл в RGBA uint8 с премноженной альфой OPACITY, пусто -
    прозрачно."""
    values = np.asarray(values, dtype=np.float64)
    at = np.array([s for s, _ in STOPS])
    out = np.zeros(values.shape + (4,), np.uint8)
    clean = np.nan_to_num(values, nan=0.0)
    for k in range(3):
        channel = np.interp(clean, at, [c[k] for _, c in STOPS])
        out[..., k] = np.round(channel * OPACITY).astype(np.uint8)
    out[..., 3] = int(round(255 * OPACITY))
    out[np.isnan(values)] = 0
    return out


def rgba(tile_rgba):
    """Тайл записи Terrarium (RGBA загрузчика) в раскраску."""
    return colors(decode(tile_rgba))


def pixel_of(lat, lon, z=MAX_LEVEL):
    """Тайл (x, y) уровня z и пиксель (столбец, строка) точки."""
    lat = max(min(lat, 85.0511), -85.0511)
    world = SIZE * 2 ** z
    gx = (lon + 180.0) / 360.0 * world
    gy = (1.0 - math.log(math.tan(math.radians(lat))
                         + 1.0 / math.cos(math.radians(lat))) / math.pi) \
        / 2.0 * world
    gx = min(max(gx, 0.0), world - 1e-6)
    gy = min(max(gy, 0.0), world - 1e-6)
    return ((int(gx // SIZE), int(gy // SIZE)),
            (int(gx % SIZE), int(gy % SIZE)))


def value_at(tile_rgb, column, row):
    """Значение пикселя тайла, нТл, или None."""
    value = float(decode(np.asarray(tile_rgb)[row:row + 1,
                                               column:column + 1])[0, 0])
    return None if math.isnan(value) else value
