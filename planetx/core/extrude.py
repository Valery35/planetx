# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выдавливание объектов слоя проекта по полю. Расчёт без Qt.

Просьба автора от 9 октября 2026 года. Многоугольник - призма от
рельефа на высоту из поля, точка - столбик-восьмиугольник, линия -
стенка без крыши. Всё собирается в запись зданий
(core.buildings.Footprint), сетку по высотам рельефа строит mesh,
рисует вид, как подземные сетки.

Кольца приводятся к обходу зданий тайла: в плоскости (долгота·cos φ,
-широта), это оси тайла Web Mercator, контур с положительной площадью,
дворы - с отрицательной. Наружу у стены тогда смотрит up × ребро.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import buildings
    from .buildings import VERTEX, Footprint, Mesh
    from .ellipsoid import geodetic_to_ecef, surface_normal
    from .features import centered
except ImportError:  # headless-тесты
    import buildings
    from buildings import VERTEX, Footprint, Mesh
    from ellipsoid import geodetic_to_ecef, surface_normal
    from features import centered

SIDES = 8  # сторон столбика точки
MAX_POINTS = 2000  # точек кольца, длиннее - прореживается
MAX_VERTICES = 600000  # вершин сетки всех выдавленных объектов слоя


def planar(latlon, lat0):
    """Кольцо (n, 2) широт и долгот в плоскость осей тайла."""
    return np.stack([latlon[:, 1] * math.cos(math.radians(lat0)),
                     -latlon[:, 0]], axis=1)


def _ring(latlon, lat0, outer):
    """Кольцо без повтора первой точки, прореженное до MAX_POINTS,
    в обходе контура (outer) или двора. None, если площади нет."""
    ring = np.asarray(latlon, dtype=np.float64)
    if len(ring) > 1 and np.all(ring[0] == ring[-1]):
        ring = ring[:-1]
    if len(ring) > MAX_POINTS:
        ring = ring[np.linspace(0, len(ring) - 1, MAX_POINTS).astype(int)]
    if len(ring) < 3:
        return None
    a = buildings.area(planar(ring, lat0))
    if a == 0.0:
        return None
    if (a > 0.0) != outer:
        ring = ring[::-1]
    return ring


def column(lat, lon, radius_m, radius):
    """Контур столбика точки - многоугольник SIDES сторон радиуса
    radius_m метров, широты и долготы (SIDES, 2)."""
    angles = np.arange(SIDES) * 2.0 * math.pi / SIDES
    dlat = math.degrees(radius_m / radius)
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    return np.stack([lat + dlat * np.sin(angles),
                     lon + dlon * np.cos(angles)], axis=1)


class Parts:
    """Собранные объекты: add_polygon, add_line, потом footprint."""

    def __init__(self):
        self.rings = []  # (широты-долготы, номер объекта, замкнуто)
        self.roofs = []  # (номер объекта, номера колец, широта)
        self.height = []
        self.base = []
        self.color = []

    def _object(self, height, base, color):
        self.height.append(float(height))
        self.base.append(float(base))
        self.color.append(tuple(int(c) for c in color[:3]))
        return len(self.height) - 1

    def add_polygon(self, rings, height, base=0.0, color=(200, 200, 200)):
        """Многоугольник: первое кольцо - контур, дальше дворы."""
        if not rings or height <= base:
            return False
        lat0 = float(np.mean(np.asarray(rings[0])[:, 0]))
        outer = _ring(rings[0], lat0, True)
        if outer is None:
            return False
        number = self._object(height, base, color)
        indices = [len(self.rings)]
        self.rings.append((outer, number, True))
        for hole in rings[1:]:
            hole = _ring(hole, lat0, False)
            if hole is not None:
                indices.append(len(self.rings))
                self.rings.append((hole, number, True))
        self.roofs.append((number, indices, lat0))
        return True

    def add_line(self, points, height, base=0.0, color=(200, 200, 200)):
        """Стенка вдоль линии без крыши."""
        line = np.asarray(points, dtype=np.float64)
        if len(line) < 2 or height <= base:
            return False
        number = self._object(height, base, color)
        self.rings.append((line, number, False))
        return True

    def follow(self):
        """По объектам: стенка ли линии, её низ идёт по рельефу."""
        out = np.zeros(len(self.height), dtype=bool)
        for _, number, closed in self.rings:
            if not closed:
                out[number] = True
        return out

    def footprint(self, key="extrude"):
        """Запись зданий всех объектов или None, если их нет."""
        if not self.rings:
            return None
        sizes = [len(r) for r, _, _ in self.rings]
        starts = np.cumsum([0] + sizes[:-1])
        latlon = np.vstack([r for r, _, _ in self.rings])
        index = np.arange(len(latlon))
        ends = np.repeat(starts + np.array(sizes), sizes)
        nxt = np.where(index + 1 < ends, index + 1,
                       np.repeat(starts, sizes)).astype(np.int64)
        wall = np.ones(len(latlon), dtype=bool)
        for (_, _, closed), start, size in zip(self.rings, starts, sizes):
            if not closed:
                # У линии нет ребра от последней точки к первой.
                wall[start + size - 1] = False
        owner = np.repeat([n for _, n, _ in self.rings], sizes)
        roofs = []
        for _, rings, lat0 in self.roofs:
            # Крыша режется по точкам своего объекта, номера - общие.
            idx = np.concatenate([np.arange(starts[r], starts[r] + sizes[r])
                                  for r in rings])
            lists, position = [], 0
            for r in rings:
                lists.append(list(range(position, position + sizes[r])))
                position += sizes[r]
            roofs.append(idx[buildings.roof(planar(latlon[idx], lat0),
                                            lists)])
        roof = np.concatenate(roofs).astype(np.uint32) if roofs \
            else np.zeros(0, dtype=np.uint32)
        return Footprint(key, latlon, nxt, wall, owner,
                         np.array(self.height), np.array(self.base),
                         np.array(self.color, dtype=np.uint8), roof)

    def vertex_count(self):
        """Вершин будущей сетки: по 4 на стену и по точке на крышу."""
        walls = sum(len(r) - (0 if closed else 1)
                    for r, _, closed in self.rings)
        return 4 * walls + sum(len(r) for r, _, _ in self.rings)


def mesh(fp, follow, heights_at=None):
    """Сетка выдавленных объектов по высотам рельефа.

    follow - по объектам: низ и верх идут по рельефу под каждой точкой
    (стенка линии). У прочих низ - самая низкая высота под точками
    объекта, крыша ровная, как у зданий (buildings.mesh).
    heights_at - высоты массивов широт и долгот, None - эллипсоид."""
    lat, lon = fp.latlon[:, 0], fp.latlon[:, 1]
    if heights_at is None:
        ground = np.zeros(len(lat))
    else:
        ground = np.asarray(heights_at(lat, lon), dtype=np.float64)
    low = np.full(len(fp.height), np.inf)
    np.minimum.at(low, fp.owner, ground)
    follow = np.asarray(follow, dtype=bool)
    under = np.where(follow[fp.owner], ground, low[fp.owner])
    top = geodetic_to_ecef(lat, lon, under + fp.height[fp.owner])
    bottom = geodetic_to_ecef(lat, lon, under + fp.base[fp.owner])
    up = surface_normal(lat, lon)
    i = np.nonzero(fp.wall)[0]
    j = fp.next[i]
    outward = np.cross(up[i], bottom[j] - bottom[i])
    corners = np.stack([bottom[i], bottom[j], top[j], top[i]], axis=1)
    positions = np.vstack([corners.reshape(-1, 3), top])
    center, offsets = centered(positions)
    count = len(i)
    vertices = np.zeros(len(positions), dtype=VERTEX)
    vertices["position"] = offsets
    vertices["normal"][:4 * count] = np.repeat(
        buildings._normals(outward), 4, axis=0)
    vertices["normal"][4 * count:] = buildings._normals(up)
    rgb = fp.color[fp.owner]
    vertices["color"][:4 * count, :3] = np.repeat(rgb[i], 4, axis=0)
    vertices["color"][4 * count:, :3] = rgb
    vertices["color"][:, 3] = 255
    quad = np.arange(count, dtype=np.uint32)[:, None] * 4
    walls = (quad + np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)).ravel()
    indices = np.concatenate([walls, fp.roof + np.uint32(4 * count)])
    return Mesh(fp.key, center, vertices, indices.astype(np.uint32))
