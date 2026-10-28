# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тени на момент - карта «солнце или тень» участка по рельефу
и крышам зданий. Расчёт без Qt.

Задача автора от 28 октября 2026 года - окно «Тени» подменю «Анализ
участка», тени на момент шкалы времени. Сетка и горизонт - те же, что
у инсоляции (core/insolation.py): квадратная сетка высот с полем для
теней гор, тангенс угла горизонта внутренних узлов по AZIMUTHS
азимутам. Горизонт считается один раз (Horizon), карта на момент -
сравнение высоты солнца с горизонтом по его азимуту, между соседними
азимутами - линейно. Так движение шкалы времени даёт новую карту за
миллисекунды без новой загрузки высот.

Узел в тени, если солнце ниже горизонта по своему азимуту или падает
на поверхность с обратной стороны. Солнце ниже горизонта места - тень
везде. Направление на солнце одно для всей сетки, по середине.
Рефракция не учитывается.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from . import insolation
    from .subsurface import inside as in_ring
    from .viewshed import distance_bearing
except ImportError:  # headless-тесты
    import ellipsoid
    import insolation
    from subsurface import inside as in_ring
    from viewshed import distance_bearing

SUN, SHADE, OUTSIDE = 1, 0, 255  # значения растра
# Цвета карты: тень - тёмная синеватая, солнце - лёгкая тёплая дымка.
SHADE_RGBA = (18, 22, 46, 150)
SUN_RGBA = (255, 214, 120, 30)


class Horizon:
    """Горизонт и нормали внутренней сетки участка. Строки с юга на
    север, центр сетки - точка (lat, lon)."""

    def __init__(self, lat, lon, radius_m, cell, hor, normal, radius,
                 ring=None):
        self.lat = lat
        self.lon = lon
        self.radius_m = radius_m
        self.cell = cell
        self.hor = hor
        self.normal = normal
        self.radius = radius
        self.ring = list(ring) if ring else None

    def at(self, moment):
        """Карта на момент moment (секунды UTC): Shadows."""
        e, n, u = insolation.sun_enu(self.lat, self.lon, [moment])[0]
        return Shadows(self, moment, lit_map(self.hor, self.normal,
                                             (e, n, u)),
                       math.degrees(math.atan2(u, math.hypot(e, n))))


def lit_map(hor, normal, sun):
    """Освещённые узлы при направлении на солнце sun (восток, север,
    верх): массив bool (n, n)."""
    e, n, u = sun
    if u <= 0.0:
        return np.zeros(hor.shape[1:], dtype=bool)
    level = math.hypot(e, n)
    tan_el = u / level if level > 0.0 else np.inf
    count = hor.shape[0]
    k = (math.atan2(e, n) / (2.0 * math.pi) * count) % count
    k0 = int(math.floor(k)) % count
    k1 = (k0 + 1) % count
    f = k - math.floor(k)
    line = hor[k0] * (1.0 - f) + hor[k1] * f
    nx, ny, nz = normal
    return (line < tan_el) & (nx * e + ny * n + nz * u > 0.0)


class Shadows:
    """Тени на момент: lit (n, n) bool - солнце, строки с юга на север.
    elevation - высота солнца над горизонтом места, градусы."""

    def __init__(self, horizon, moment, lit, elevation):
        self.horizon = horizon
        self.moment = moment
        self.lit = lit
        self.elevation = elevation
        self.lat = horizon.lat
        self.lon = horizon.lon
        self.radius_m = horizon.radius_m
        self.cell = horizon.cell
        self.ring = horizon.ring
        self.dlat = math.degrees(horizon.cell / horizon.radius)
        self.dlon = math.degrees(horizon.cell / (
            horizon.radius * math.cos(math.radians(horizon.lat))))

    def at(self, lats, lons, radius):
        """Солнце в точках (bool) и признак «внутри участка»."""
        n = self.lit.shape[0]
        row = np.rint((np.asarray(lats) - self.lat) / self.dlat
                      + (n - 1) / 2.0).astype(np.int64)
        col = np.rint((np.asarray(lons) - self.lon) / self.dlon
                      + (n - 1) / 2.0).astype(np.int64)
        dist, _ = distance_bearing(self.lat, self.lon, lats, lons, radius)
        inside = (dist <= self.radius_m) & (row >= 0) & (row < n) \
            & (col >= 0) & (col < n)
        if self.ring:
            inside &= in_ring(lats, lons, self.ring)
        values = self.lit[np.clip(row, 0, n - 1), np.clip(col, 0, n - 1)]
        return values & inside, inside

    def share(self):
        """Доля участка на солнце, 0-1."""
        _, _, _, _, grid = raster(self)
        inside = grid != OUTSIDE
        count = int(np.count_nonzero(inside))
        return float(np.count_nonzero(grid == SUN)) / count if count else 0.0


def parts(lat, lon, radius_m, heights, radius=None, ring=None):
    """Горизонт участка по частям. Генератор: после каждой части отдаёт
    долю сделанного 0-1, результат Horizon - значение StopIteration.
    heights - функция настоящих высот массивов широт и долгот или
    готовые высоты узлов insolation.grid_points, крыши уже прибавлены."""
    radius = radius or ellipsoid.A
    cell, margin, inner = insolation.layout(radius_m)
    if callable(heights):
        grid_lat, grid_lon = insolation.grid_points(lat, lon, radius_m,
                                                    radius)
        heights = heights(grid_lat.ravel(), grid_lon.ravel())
    h = np.asarray(heights, dtype=np.float64).reshape(insolation.GRID,
                                                     insolation.GRID)
    total = sum(len(p) for p in insolation.shifts(cell, margin)) + 1
    done = 0
    hor = np.empty((insolation.AZIMUTHS, inner, inner), dtype=np.float32)
    for _ in insolation.horizon_parts(h, cell, margin, radius, hor):
        done += 1
        yield done / total
    normal = insolation.normals(h, cell, margin, inner)
    return Horizon(lat, lon, radius_m, cell, hor, normal, radius, ring)


def compute(lat, lon, radius_m, heights, radius=None, ring=None):
    """Горизонт участка целиком: Horizon."""
    work = parts(lat, lon, radius_m, heights, radius, ring)
    while True:
        try:
            next(work)
        except StopIteration as stop:
            return stop.value


def raster(result):
    """Сетка широт и долгот для растра: (север, запад, шаг широты, шаг
    долготы, байты - строки с севера, SUN, SHADE, вне участка OUTSIDE)."""
    n = result.lit.shape[0]
    north = result.lat + (n - 1) / 2.0 * result.dlat
    west = result.lon - (n - 1) / 2.0 * result.dlon
    lats = north - np.arange(n) * result.dlat
    lons = west + np.arange(n) * result.dlon
    grid_lat, grid_lon = np.meshgrid(lats, lons, indexing="ij")
    dist, _ = distance_bearing(result.lat, result.lon, grid_lat, grid_lon,
                               result.horizon.radius)
    out = np.where(result.lit[::-1], SUN, SHADE).astype(np.uint8)
    out[dist > result.radius_m] = OUTSIDE
    if result.ring:
        out[~in_ring(grid_lat, grid_lon, result.ring)] = OUTSIDE
    return north, west, result.dlat, result.dlon, out


def tile_rgba(result, lats, lons, radius):
    """Картинка тайла: тень SHADE_RGBA, солнце SUN_RGBA, вне участка
    прозрачно. RGBA uint8 с премноженной альфой."""
    lit, inside = result.at(lats, lons, radius)
    out = np.zeros(np.shape(lats) + (4,), dtype=np.uint8)
    for mask, rgba in ((inside & ~lit, SHADE_RGBA), (lit, SUN_RGBA)):
        alpha = rgba[3] / 255.0
        out[mask] = (round(rgba[0] * alpha), round(rgba[1] * alpha),
                     round(rgba[2] * alpha), rgba[3])
    return out
