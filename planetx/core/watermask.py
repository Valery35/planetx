# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вода и суша ниже уровня моря по векторной основе. Расчёт без Qt.

Просьба автора от 20 октября 2026 года - «ставь на рельеф, если под ней
суша». С глубинами морей метки, пути и подписи стоят не ниже уровня
моря, иначе названия морей лежали бы на дне. Сухие впадины ниже нуля -
карьеры, Мёртвое море, Прикаспий - по высотам от моря не отличить:
метка на дне Лебединского карьера (-51 м) висела на нуле, в 50 м над
дном. Здесь суша - точка вне многоугольников слоя water тайлов
OpenMapTiles уровня LEVEL. Тайлы просит окно (ui/watermask.py), только
для точек с рельефом ниже нуля. Пока тайла нет, точка считается водой,
как прежде.

Модуль Qt не знает.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .buildings import _fields, _packed, _rings, _unpack
except ImportError:  # headless-тесты
    from buildings import _fields, _packed, _rings, _unpack

LAYER = "water"
LEVEL = 12  # уровень тайлов основы, около 10 км на сторону у 55° с. ш.
EXTENT = 4096


def tile_of(lat, lon, level=LEVEL):
    """Тайл уровня level под точкой и место в нём долями 0-1: (ключ,
    x, y), y растёт к югу."""
    n = 2 ** level
    lat = max(min(float(lat), 85.0511), -85.0511)
    fx = (float(lon) + 180.0) / 360.0 * n
    phi = math.radians(lat)
    fy = (1.0 - math.log(math.tan(phi) + 1.0 / math.cos(phi)) / math.pi) \
        / 2.0 * n
    x = min(max(int(fx), 0), n - 1)
    y = min(max(int(fy), 0), n - 1)
    return (level, x, y), fx - x, fy - y


def decode_water(data):
    """Многоугольники слоя water тайла: список объектов, объект -
    список колец, массивы (n, 2) долями тайла 0-1."""
    out = []
    for number, wire, layer in _fields(_unpack(data)):
        if number != 3 or wire != 2:
            continue
        fields = list(_fields(layer))
        title = next((bytes(v).decode("utf-8", errors="replace")
                      for n, w, v in fields if n == 1 and w == 2), None)
        if title != LAYER:
            continue
        extent = next((v for n, w, v in fields if n == 5 and w == 0),
                      EXTENT) or EXTENT
        for n, w, feature in fields:
            if n != 2 or w != 2:
                continue
            kind = 0
            geometry = []
            for fn, fw, fv in _fields(feature):
                if fn == 3 and fw == 0:
                    kind = fv
                elif fn == 4 and fw == 2:
                    geometry = _packed(fv)
            if kind != 3:
                continue
            rings = [ring / float(extent) for ring, _ in _rings(geometry)]
            if rings:
                out.append(rings)
    return out


def inside(rings, xs, ys):
    """Точки (xs, ys) внутри объекта из колец rings по правилу
    чёт-нечет: двор внутри контура не считается."""
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    odd = np.zeros(xs.shape, dtype=bool)
    for ring in rings:
        lo, hi = ring.min(axis=0), ring.max(axis=0)
        near = (xs >= lo[0]) & (xs <= hi[0]) & (ys >= lo[1]) & (ys <= hi[1])
        if not near.any():
            continue
        px, py = xs[near][:, None], ys[near][:, None]
        x0, y0 = ring[:, 0][None, :], ring[:, 1][None, :]
        x1 = np.roll(ring[:, 0], -1)[None, :]
        y1 = np.roll(ring[:, 1], -1)[None, :]
        crosses = (y0 > py) != (y1 > py)
        dy = np.where(y1 == y0, 1e-12, y1 - y0)
        at = x0 + (py - y0) * (x1 - x0) / dy
        flips = (crosses & (px < at)).sum(axis=1) % 2 == 1
        odd[near] ^= flips
    return odd


MASK_FROM = 10  # тайлы глобуса мельче не получают маски воды


def mask_parts(key):
    """Части тайла глобуса key = (z, x, y) по тайлам воды уровня LEVEL:
    список (ключ тайла воды, (x0, y0, сторона) части в долях тайла воды,
    (x0, y0, сторона) той же части в долях тайла глобуса). Тайл мельче
    MASK_FROM - пустой список, маски у него нет."""
    z, x, y = key
    if z < MASK_FROM:
        return []
    if z >= LEVEL:
        shift = z - LEVEL
        n = 2 ** shift
        wx, wy = x >> shift, y >> shift
        return [((LEVEL, wx, wy),
                 ((x - wx * n) / n, (y - wy * n) / n, 1.0 / n),
                 (0.0, 0.0, 1.0))]
    shift = LEVEL - z
    n = 2 ** shift
    return [((LEVEL, x * n + i, y * n + j), (0.0, 0.0, 1.0),
             (i / n, j / n, 1.0 / n))
            for j in range(n) for i in range(n)]


def mask_rings(key, tiles):
    """Кольца воды тайла глобуса key в его долях 0-1 по объектам: список
    объектов, объект - список колец (n, 2). None - тайлов воды под ним
    ещё нет. tiles - тайлы WaterMask.tiles."""
    parts = mask_parts(key)
    if not parts or any(water not in tiles for water, _, _ in parts):
        return None
    out = []
    for water, (sx, sy, ss), (dx, dy, ds) in parts:
        scale = ds / ss
        for rings in tiles[water]:
            out.append([(ring - (sx, sy)) * scale + (dx, dy)
                        for ring in rings])
    return out


class WaterMask:
    """Тайлы воды основы и проверка точек на сушу."""

    def __init__(self):
        self.tiles = {}  # ключ тайла - объекты decode_water
        # Растёт с каждым новым тайлом: по нему вид заново ставит метки
        # и подписи.
        self.gen = 0

    def add(self, key, features):
        self.tiles[key] = features
        self.gen += 1

    def clear(self):
        if self.tiles:
            self.tiles = {}
            self.gen += 1

    def missing(self, lats, lons):
        """Ключи тайлов под точками, которых ещё нет."""
        keys = {tile_of(lat, lon)[0] for lat, lon in zip(lats, lons)}
        return keys - set(self.tiles)

    def land(self, lats, lons):
        """Маска точек на суше: тайл есть и точка не в воде."""
        lats = np.atleast_1d(np.asarray(lats, dtype=np.float64))
        lons = np.atleast_1d(np.asarray(lons, dtype=np.float64))
        out = np.zeros(lats.shape, dtype=bool)
        if not self.tiles:
            return out
        groups = {}
        for n, (lat, lon) in enumerate(zip(lats, lons)):
            key, fx, fy = tile_of(lat, lon)
            if key in self.tiles:
                groups.setdefault(key, []).append((n, fx, fy))
        for key, items in groups.items():
            index = np.array([i for i, _, _ in items])
            xs = np.array([x for _, x, _ in items])
            ys = np.array([y for _, _, y in items])
            wet = np.zeros(len(items), dtype=bool)
            for rings in self.tiles[key]:
                wet |= inside(rings, xs, ys)
            out[index] = ~wet
        return out
