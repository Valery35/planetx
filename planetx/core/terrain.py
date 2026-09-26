# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Высоты рельефа из тайлов Terrarium.

Тайл Terrarium - картинка 256×256 в сетке Web Mercator, уровни 0-15.
Высота пикселя в метрах равна R·256 + G + B/256 - 32768. Пиксель
покрывает квадрат, его значение относится к центру квадрата.

Отрицательные высоты - это дно моря и впадины суши. Подложка лежит
на уровне моря, поэтому высоты ниже нуля прижимаются к нулю. Впадины
суши вроде Мёртвого моря при этом тоже уходят на ноль.

Модуль Qt не знает.
"""
import math
from collections import namedtuple

import numpy as np

MAX_LEVEL = 15
SIZE = 256
# Уровень высот для тайла подложки уровня z. 256 пикселей высот на 16
# отрезков сетки дают 4 пикселя на отрезок уже при z - 2, поэтому
# высоты берутся на два уровня грубее. Загрузок высот так в 16 раз
# меньше, чем тайлов подложки.
LEVEL_OFFSET = 2

HeightTile = namedtuple("HeightTile", "z x y heights low high")
HeightTile.__doc__ = """Тайл высот: массив (256, 256) float32 в метрах,
наименьшая и наибольшая высота."""


def decode(rgba):
    """Картинка Terrarium (h, w, 3 или 4) uint8 в высоты float32, метры."""
    rgb = np.asarray(rgba)[..., :3].astype(np.float32)
    heights = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 \
        - 32768.0
    return np.maximum(heights, 0.0)


def make_tile(z, x, y, rgba):
    heights = decode(rgba)
    return HeightTile(z, x, y, heights, float(heights.min()),
                      float(heights.max()))


def height_level(z):
    """Уровень высот для тайла подложки уровня z."""
    return max(0, min(z - LEVEL_OFFSET, MAX_LEVEL))


def ancestor(key, level):
    """Предок тайла key на уровне level, level не глубже key."""
    z, x, y = key
    shift = z - level
    return (level, x >> shift, y >> shift)


def sample(tile, u, v):
    """Высоты в точках с долями мира u (запад - восток) и v (север - юг).

    u и v - массивы долей от 0 до 1 во всём мире Mercator. Выборка
    билинейная по центрам пикселей, за краем тайла берётся крайний
    пиксель. Возвращает float64.
    """
    n = 1 << tile.z
    px = (np.asarray(u, dtype=np.float64) * n - tile.x) * SIZE - 0.5
    py = (np.asarray(v, dtype=np.float64) * n - tile.y) * SIZE - 0.5
    px = np.clip(px, 0.0, SIZE - 1.0)
    py = np.clip(py, 0.0, SIZE - 1.0)
    x0 = np.minimum(np.floor(px).astype(np.int64), SIZE - 2)
    y0 = np.minimum(np.floor(py).astype(np.int64), SIZE - 2)
    fx = px - x0
    fy = py - y0
    h = tile.heights
    top = h[y0, x0] * (1.0 - fx) + h[y0, x0 + 1] * fx
    bottom = h[y0 + 1, x0] * (1.0 - fx) + h[y0 + 1, x0 + 1] * fx
    return top * (1.0 - fy) + bottom * fy


def grid_shares(z, x, y, segments, border=0):
    """Доли мира u, v узлов сетки тайла, с полосой border узлов вокруг.

    Узлы считаются от общего целого номера, как в tiling.grid_latlon.
    Поэтому у соседей с одной картой высот общий край получает одни
    и те же высоты до бита.
    """
    total = (1 << z) * segments
    idx = np.arange(-border, segments + border + 1)
    u = (x * segments + idx) / total
    v = (y * segments + idx) / total
    return np.meshgrid(u, v)


def mercator_share(lat, lon):
    """Доли мира u, v точки с широтой и долготой в градусах."""
    lat = max(-85.05112878, min(85.05112878, lat))
    u = (lon + 180.0) / 360.0
    v = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0
    return u % 1.0, min(max(v, 0.0), 1.0)


class HeightStore:
    """Загруженные тайлы высот и выбор лучшего для точки или тайла."""

    RANGE_CACHE = 50000

    def __init__(self):
        self.tiles = {}
        self._ranges = {}

    def add(self, tile):
        self.tiles[(tile.z, tile.x, tile.y)] = tile
        # Размахи считались по более грубым тайлам, новый точнее.
        self._ranges.clear()

    def best(self, key):
        """Самый точный готовый тайл высот для тайла подложки key.

        Идёт от уровня height_level(z) вверх к уровню 0. None, если
        не готов даже тайл уровня 0.
        """
        level = height_level(key[0])
        for zh in range(level, -1, -1):
            tile = self.tiles.get(ancestor(key, zh))
            if tile is not None:
                return tile
        return None

    def wanted(self, key):
        """Ключ тайла высот, нужного тайлу подложки key."""
        return ancestor(key, height_level(key[0]))

    def height_at(self, lat, lon):
        """Высота рельефа в точке по самому точному готовому тайлу."""
        u, v = mercator_share(lat, lon)
        for zh in range(MAX_LEVEL, -1, -1):
            n = 1 << zh
            key = (zh, min(int(u * n), n - 1), min(int(v * n), n - 1))
            tile = self.tiles.get(key)
            if tile is not None:
                return float(sample(tile, u, v))
        return 0.0

    def range_for(self, key):
        """Наименьшая и наибольшая высота для тайла подложки key.

        Берутся из блока пикселей готового тайла высот, который тайл
        подложки накрывает. Блок расширен на пиксель с каждой стороны:
        выборка билинейная и берёт соседние пиксели. Без данных - (0, 0).

        Размах всего тайла высот уровня 15 в горах - сотни метров. Выбор
        тайлов раздувает сферу тайла на половину размаха, и с грубой
        оценкой мелкие тайлы у камеры дробились бы без нужды.
        """
        cached = self._ranges.get(key)
        if cached is not None:
            return cached
        tile = self.best(key)
        if tile is None:
            return (0.0, 0.0)
        z, x, y = key
        shift = z - tile.z
        if shift <= 0:
            result = (tile.low, tile.high)
        else:
            size = SIZE >> shift if shift < 8 else 1
            span = 1 << shift
            col = (x - (tile.x << shift)) * SIZE // span
            row = (y - (tile.y << shift)) * SIZE // span
            block = tile.heights[max(row - 1, 0):row + size + 1,
                                 max(col - 1, 0):col + size + 1]
            result = (float(block.min()), float(block.max()))
        if len(self._ranges) > self.RANGE_CACHE:
            self._ranges.clear()
        self._ranges[key] = result
        return result
