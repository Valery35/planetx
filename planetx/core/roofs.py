# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Крыши зданий для видимости из точки и инсоляции.

Просьба автора от 20 октября 2026 года - здания в инсоляции
и видимости. Здания - слой building тайлов OpenFreeMap уровня
buildings.LEVEL, тот же, что у 3D-зданий. Контуры зданий в круге
расчёта выжигаются в растр высот крыш над землёй (Roofs.burn,
чёт-нечет по рёбрам всех колец здания, дворы остаются землёй), расчёт
берёт высоту рельефа плюс крышу (Roofs.at). Растр - сетка широт
и долгот с клеткой около cell метров, не больше MAX_SIDE клеток по
стороне. Здание уже клетки растра может не попасть ни в одну клетку.
Высота здания - render_height тайла, у части зданий она условная.

Модуль Qt не знает.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .buildings import LEVEL, decode, tile_latlon
    from .tiling import lonlat_to_tile
except ImportError:  # headless-тесты
    import ellipsoid
    from buildings import LEVEL, decode, tile_latlon
    from tiling import lonlat_to_tile

MAX_SIDE = 4000  # клеток растра по стороне, не больше
MAX_TILES = 300  # тайлов зданий на расчёт, больше - без зданий
MIN_CELL = 1.0  # м, клетка растра не мельче


def tiles_around(lat, lon, reach):
    """Ключи тайлов зданий в квадрате со стороной 2 * reach метров
    вокруг точки, упорядочены от середины к краю."""
    dlat = math.degrees(reach / ellipsoid.A)
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    x0, y0 = lonlat_to_tile(lat + dlat, lon - dlon, LEVEL)
    x1, y1 = lonlat_to_tile(lat - dlat, lon + dlon, LEVEL)
    cx, cy = lonlat_to_tile(lat, lon, LEVEL)
    keys = [(LEVEL, x, y) for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)]
    keys.sort(key=lambda k: (k[1] - cx) ** 2 + (k[2] - cy) ** 2)
    return keys


class Roofs:
    """Растр высот крыш над землёй вокруг точки lat, lon: квадрат
    со стороной 2 * reach метров, клетка около cell метров."""

    def __init__(self, lat, lon, reach, cell):
        cell = max(cell, MIN_CELL, 2.0 * reach / MAX_SIDE)
        side = int(math.ceil(2.0 * reach / cell))
        self.dlat = math.degrees(cell / ellipsoid.A)
        self.dlon = self.dlat / max(math.cos(math.radians(lat)), 1e-6)
        self.lat0 = lat - side * self.dlat / 2.0
        self.lon0 = lon - side * self.dlon / 2.0
        self.top = np.zeros((side, side), dtype=np.float32)
        self.cell = cell
        self.count = 0  # зданий в растре

    def burn(self, rings, height):
        """Здание - кольца (n, 2) широт и долгот, первое - контур,
        дальше дворы. Клетки внутри - высота крыши, где она выше."""
        points = np.vstack(rings)
        rows = (points[:, 0] - self.lat0) / self.dlat
        cols = (points[:, 1] - self.lon0) / self.dlon
        side = self.top.shape[0]
        r0 = max(int(math.floor(rows.min())), 0)
        r1 = min(int(math.ceil(rows.max())), side)
        c0 = max(int(math.floor(cols.min())), 0)
        c1 = min(int(math.ceil(cols.max())), side)
        if r0 >= r1 or c0 >= c1:
            return
        y = np.arange(r0, r1) + 0.5
        x = np.arange(c0, c1) + 0.5
        py, px = (a.ravel() for a in np.meshgrid(y, x, indexing="ij"))
        # Рёбра всех колец: от точки к следующей, кольцо замкнуто.
        ends = np.cumsum([len(r) for r in rings])
        nxt = np.arange(1, len(points) + 1)
        nxt[ends - 1] = np.concatenate([[0], ends[:-1]])
        y1, x1 = rows[:, None], cols[:, None]
        y2, x2 = rows[nxt][:, None], cols[nxt][:, None]
        crosses = (y1 > py) != (y2 > py)
        with np.errstate(divide="ignore", invalid="ignore"):
            at = x1 + (py - y1) * (x2 - x1) / (y2 - y1)
        inside = (np.count_nonzero(crosses & (px < at), axis=0) % 2) == 1
        if not inside.any():
            return
        block = self.top[r0:r1, c0:c1]
        mask = inside.reshape(block.shape)
        block[mask] = np.maximum(block[mask], height)
        self.count += 1

    def add_tile(self, key, data):
        """Здания тайла key из байтов векторного тайла."""
        buildings, extent = decode(data)
        for building in buildings:
            rings = [tile_latlon(key, float(extent), ring)
                     for ring in building.rings]
            self.burn(rings, building.height)

    def at(self, lats, lons):
        """Высоты крыш над землёй в точках, вне растра и зданий - 0."""
        rows = np.floor((np.asarray(lats) - self.lat0) / self.dlat)
        cols = np.floor((np.asarray(lons) - self.lon0) / self.dlon)
        side = self.top.shape[0]
        ok = (rows >= 0) & (rows < side) & (cols >= 0) & (cols < side)
        out = np.zeros(np.shape(rows), dtype=np.float64)
        out[ok] = self.top[rows[ok].astype(int), cols[ok].astype(int)]
        return out
