# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Врезка своего рельефа: растр высот проекта поверх Terrarium.

Решение автора от 5 октября 2026 года. Растр пересчитывается в Web
Mercator (EPSG:3857), его высоты заменяют Terrarium там, где у растра
есть данные. На полосе вдоль края данных высоты плавно переходят
от растра к Terrarium, ширина полосы - BAND_SHARE меньшей стороны
охвата. Внутри охвата уровни высот идут глубже terrain.MAX_LEVEL, до
пикселя растра, но не глубже terrain.DEEP_LEVEL. Расчёт без Qt и
GDAL: рамки тайлов, уровень, вес края, слияние.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .terrain import DEEP_LEVEL, MAX_LEVEL, SIZE
except ImportError:  # headless-тесты
    from terrain import DEEP_LEVEL, MAX_LEVEL, SIZE

HALF = 20037508.342789244  # полуширина мира Web Mercator, м
BAND_SHARE = 0.05  # полоса края - доля меньшей стороны охвата


def tile_bounds(z, x, y):
    """Рамка тайла (z, x, y) в EPSG:3857: (запад, юг, восток, север)."""
    size = 2.0 * HALF / (1 << z)
    west = -HALF + x * size
    north = HALF - y * size
    return west, north - size, west + size, north


def shares(west, south, east, north):
    """Рамка EPSG:3857 в долях мира: (u0, v0, u1, v1), v сверху вниз."""
    return ((west + HALF) / (2.0 * HALF), (HALF - north) / (2.0 * HALF),
            (east + HALF) / (2.0 * HALF), (HALF - south) / (2.0 * HALF))


def level_for(pixel):
    """Уровень высот, пиксель которого не крупнее pixel - пикселя
    растра в метрах EPSG:3857. Не мельче MAX_LEVEL и не глубже
    DEEP_LEVEL."""
    if pixel <= 0.0:
        return DEEP_LEVEL
    level = math.ceil(math.log2(2.0 * HALF / (SIZE * pixel)))
    return max(MAX_LEVEL, min(DEEP_LEVEL, level))


def band_width(west, south, east, north, share=BAND_SHARE):
    """Ширина полосы края в метрах EPSG:3857."""
    return share * min(east - west, north - south)


def smoothstep(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def edge_weight(distance, band):
    """Доля растра по расстоянию до края данных: 0 на краю, 1 дальше
    полосы band, между ними плавно."""
    if band <= 0.0:
        return (np.asarray(distance) > 0.0).astype(np.float32)
    return smoothstep(np.asarray(distance, dtype=np.float64)
                      / band).astype(np.float32)


def merge(base, dem, weight):
    """Высоты base, в которые врезан растр dem с весом weight.

    dem - высоты растра, NaN без данных. weight - доля растра от 0 до 1,
    NaN считается нулём. Возвращает новый массив float32."""
    base = np.asarray(base, dtype=np.float32)
    dem = np.asarray(dem, dtype=np.float32)
    w = np.nan_to_num(np.asarray(weight, dtype=np.float32), nan=0.0)
    valid = np.isfinite(dem)
    w = np.where(valid, np.clip(w, 0.0, 1.0), 0.0)
    out = base + w * (np.where(valid, dem, base) - base)
    return out.astype(np.float32)


def overlaps(box, west, south, east, north):
    """Пересекает ли рамка box (запад, юг, восток, север) другую."""
    return box[0] < east and west < box[2] and box[1] < north \
        and south < box[3]
