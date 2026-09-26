# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетка тайлов Web Mercator и сетка вершин тайла.

Номер тайла (z, x, y) устроен как у OSM. Уровень z делит мир на 2^z
столбцов и 2^z строк. Столбец x идёт от долготы -180 на восток, строка y
от северной границы на юг. Сетка кончается на широте MAX_LAT.

Вершины тайла лежат равномерно в координатах Mercator, поэтому картинка
тайла ложится на них без пересчёта. Вершины хранятся в float32 как
смещение от центра тайла, центр хранится в float64. Устройство описано
в AGENTS.md, раздел «Координаты».
"""
import math
from collections import namedtuple
from functools import lru_cache

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import A, geodetic_to_ecef, surface_normal
except ImportError:  # headless-тесты
    from ellipsoid import A, geodetic_to_ecef, surface_normal

MAX_LAT = math.degrees(math.atan(math.sinh(math.pi)))
MAX_LEVEL = 19
MIN_SKIRT = 2.0

TileMesh = namedtuple(
    "TileMesh", "z x y segments center radius positions uv indices")
TileMesh.__doc__ = """Сетка вершин одного тайла.

center - центр в ECEF, float64. radius - радиус описанной сферы вокруг
центра. positions - смещения вершин от центра, float32, форма (N, 3).
uv - текстурные координаты, float32, v = 0 на северном краю. indices -
общий для всех тайлов с тем же segments буфер индексов, uint16.
"""


def segments(z):
    """Количество отрезков на сторону тайла уровня z.

    Мелкие уровни получают больше отрезков, чтобы край глобуса оставался
    круглым. Отрезок уровня 0 занимает 5.6° долготы.
    """
    return max(16, 64 >> z)


def lat_of_row(t):
    """Широта в градусах по доле высоты мира t, t = 0 на северной границе."""
    t = np.asarray(t, dtype=np.float64)
    return np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * t))))


def lonlat_to_tile(lat, lon, z):
    """Номер тайла уровня z, в котором лежит точка.

    Широта за пределами MAX_LAT прижимается к краю сетки, долгота 180
    попадает в последний столбец.
    """
    n = 1 << z
    lat = min(max(lat, -MAX_LAT), MAX_LAT)
    x = int(math.floor((lon + 180.0) / 360.0 * n))
    merc = math.asinh(math.tan(math.radians(lat)))
    y = int(math.floor((1.0 - merc / math.pi) / 2.0 * n))
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def tile_bounds(z, x, y):
    """Границы тайла в градусах, порядок запад, юг, восток, север."""
    n = 1 << z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = float(lat_of_row(y / n))
    south = float(lat_of_row((y + 1) / n))
    return west, south, east, north


def segment_sag(z):
    """Наибольший прогиб хорды отрезка уровня z под поверхностью, метры.

    Считается по экватору, где отрезок самый длинный.
    """
    angle = 2.0 * math.pi / ((1 << z) * segments(z))
    return A * (1.0 - math.cos(angle / 2.0))


def skirt_depth(z):
    """Глубина юбки тайла уровня z, метры.

    Юбка закрывает щель у соседа уровнем грубее. Его хорда проседает
    под поверхность на segment_sag(z - 1), юбка берётся вдвое глубже.
    """
    return max(MIN_SKIRT, 2.0 * segment_sag(max(z - 1, 0)))


def _ring(seg):
    """Номера краевых вершин сетки по кругу.

    Порядок - северный край с запада на восток, восточный с севера
    на юг, южный с востока на запад, западный с юга на север. Снаружи
    Земли этот обход идёт по часовой стрелке.
    """
    side = seg + 1
    north = [i for i in range(seg)]
    east = [j * side + seg for j in range(seg)]
    south = [seg * side + seg - i for i in range(seg)]
    west = [(seg - j) * side for j in range(seg)]
    return np.array(north + east + south + west, dtype=np.int64)


@lru_cache(maxsize=None)
def index_buffer(seg):
    """Треугольники сетки и юбки, обход против часовой стрелки снаружи."""
    side = seg + 1
    j, i = np.mgrid[0:seg, 0:seg]
    tl = (j * side + i).ravel()
    tr = tl + 1
    bl = tl + side
    br = bl + 1
    grid = np.stack([tl, bl, tr, tr, bl, br], axis=1).ravel()

    ring = _ring(seg)
    top = ring
    top_next = np.roll(ring, -1)
    low = side * side + np.arange(len(ring))
    low_next = np.roll(low, -1)
    skirt = np.stack([top, top_next, low, top_next, low_next, low],
                     axis=1).ravel()

    out = np.concatenate([grid, skirt]).astype(np.uint16)
    out.setflags(write=False)
    return out


def grid_latlon(z, x, y):
    """Широта и долгота узлов сетки тайла, два массива (seg+1, seg+1).

    Узлы считаются от общего целого номера узла на уровне. Поэтому общий
    край соседних тайлов получает одни и те же числа до бита, в том числе
    на линии смены дат.
    """
    seg = segments(z)
    total = (1 << z) * seg
    gi = x * seg + np.arange(seg + 1)
    gj = y * seg + np.arange(seg + 1)
    lon = (gi % total) / total * 360.0 - 180.0
    lat = lat_of_row(gj / total)
    return np.meshgrid(lat, lon, indexing="ij")


def grid_ecef(z, x, y):
    """Узлы сетки тайла в ECEF, float64, форма (seg+1, seg+1, 3)."""
    return geodetic_to_ecef(*grid_latlon(z, x, y))


def tile_mesh(z, x, y):
    """Сетка вершин тайла с юбкой."""
    seg = segments(z)
    lat_grid, lon_grid = grid_latlon(z, x, y)
    grid = geodetic_to_ecef(lat_grid, lon_grid).reshape(-1, 3)
    ring = _ring(seg)
    normals = surface_normal(lat_grid, lon_grid).reshape(-1, 3)[ring]
    skirt = grid[ring] - normals * skirt_depth(z)
    world = np.concatenate([grid, skirt])

    center = grid[(seg // 2) * (seg + 1) + seg // 2].copy()
    offsets = world - center
    radius = float(np.sqrt((offsets * offsets).sum(axis=1)).max())

    u, v = np.meshgrid(np.arange(seg + 1) / seg, np.arange(seg + 1) / seg)
    uv = np.stack([u.ravel(), v.ravel()], axis=1)
    uv = np.concatenate([uv, uv[ring]]).astype(np.float32)

    return TileMesh(z, x, y, seg, center, radius,
                    offsets.astype(np.float32), uv, index_buffer(seg))


def polar_cap_mesh(north, count=256):
    """Шапка над краем сетки у полюса, веер треугольников.

    Край шапки лежит на широте MAX_LAT, вершина веера на полюсе. Шапка
    закрашивается сплошным цветом, поэтому uv всех вершин нулевые.
    Возвращается в том же виде, что и тайл, с z = -1.
    """
    sign = 1.0 if north else -1.0
    lon = np.arange(count) / count * 360.0 - 180.0
    rim = geodetic_to_ecef(np.full(count, sign * MAX_LAT), lon)
    pole = geodetic_to_ecef(sign * 90.0, 0.0)
    world = np.concatenate([pole[None, :], rim])
    center = pole.copy()
    offsets = world - center
    radius = float(np.sqrt((offsets * offsets).sum(axis=1)).max())

    k = np.arange(count)
    k_next = (k + 1) % count
    # Долгота растёт на восток. Над северным полюсом обход против часовой
    # стрелки снаружи идёт в сторону роста долготы, над южным наоборот.
    if north:
        tri = np.stack([np.zeros(count, dtype=np.int64), k + 1, k_next + 1],
                       axis=1)
    else:
        tri = np.stack([np.zeros(count, dtype=np.int64), k_next + 1, k + 1],
                       axis=1)
    indices = tri.ravel().astype(np.uint16)
    indices.setflags(write=False)
    uv = np.zeros((len(world), 2), dtype=np.float32)
    return TileMesh(-1, 0, 0 if north else 1, count, center, radius,
                    offsets.astype(np.float32), uv, indices)
