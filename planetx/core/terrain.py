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
# Самый подробный уровень высот внутри врезки своего рельефа: подложка
# доходит до уровня 19, высоты берутся на LEVEL_OFFSET грубее.
DEEP_LEVEL = 19 - LEVEL_OFFSET
# Уровень высот сетки, собранной без рельефа при выключенном рельефе.
# Он глубже любого тайла высот, поэтому новые высоты такую сетку
# не пересобирают.
FLAT_LEVEL = DEEP_LEVEL + 1

HeightTile = namedtuple("HeightTile", "z x y heights low high")
HeightTile.__doc__ = """Тайл высот: массив (256, 256) float32 в метрах,
наименьшая и наибольшая высота."""


def decode(rgba, floor=0.0):
    """Картинка Terrarium (h, w, 3 или 4) uint8 в высоты float32, метры.

    floor - нижний предел высот. У Земли 0: подложка рисует воду
    на уровне моря, дно под ней не нужно. У Марса и Луны None - впадины
    вроде равнины Эллада глубже нуля на километры и остаются.
    """
    rgb = np.asarray(rgba)[..., :3].astype(np.float32)
    heights = rgb[..., 0] * 256.0 + rgb[..., 1] + rgb[..., 2] / 256.0 \
        - 32768.0
    return heights if floor is None else np.maximum(heights, floor)


def make_tile(z, x, y, rgba, floor=0.0):
    heights = decode(rgba, floor)
    return HeightTile(z, x, y, heights, float(heights.min()),
                      float(heights.max()))


def height_level(z, top=MAX_LEVEL):
    """Уровень высот для тайла подложки уровня z, не глубже top."""
    return max(0, min(z - LEVEL_OFFSET, top))


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


def pixel_shares(z, x, y):
    """Доли мира u, v центров пикселей тайла высот (z, x, y), массивы
    (256, 256)."""
    total = float((1 << z) * SIZE)
    idx = np.arange(SIZE, dtype=np.float64) + 0.5
    return np.meshgrid((x * SIZE + idx) / total, (y * SIZE + idx) / total)


def resample(tile, key):
    """Высоты тайла key, более подробного, чем tile, по высотам tile -
    его предка. Выборка билинейная, массив (256, 256) float32."""
    u, v = pixel_shares(*key)
    return sample(tile, u, v).astype(np.float32)


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
    """Загруженные тайлы высот и выбор лучшего для точки или тайла.

    scale - вертикальный масштаб рельефа. Высоты и размахи отдаются
    умноженными на него, 0 - рельеф выключен, Земля гладкая.
    """

    RANGE_CACHE = 50000

    def __init__(self):
        self.tiles = {}
        self._ranges = {}
        self.scale = 1.0
        # Самый подробный уровень тайлов высот источника: у Terrarium 15,
        # у высот Марса и Луны 5. Глубже тайлы не просятся.
        self.max_level = MAX_LEVEL
        # Рамки врезок своего рельефа: (u0, v0, u1, v1, уровень) в долях
        # мира. Внутри рамки высоты идут глубже max_level, до уровня.
        self.deep = []
        # Растёт с каждым добавленным тайлом и со сменой масштаба. По ней
        # выбор тайлов понимает, что размахи высот могли измениться.
        self.version = 0
        # Ключи тайлов, добавленных после последнего take_added.
        self.added = []
        # Самая низкая высота загруженных тайлов, без масштаба, не выше
        # нуля. У Земли пол высот 0, у Марса и Луны впадины ниже нуля.
        self.low = 0.0

    def depth(self):
        """Насколько рельеф опускается ниже эллипсоида, метры, с масштабом.
        На эту глубину опускается подстилка (render/view.py)."""
        return -self.low * self.scale

    def set_scale(self, scale):
        """Новый вертикальный масштаб. Меняет все высоты сразу."""
        self.scale = float(scale)
        self.version += 1

    def clear(self):
        """Забыть все высоты: другое тело, у него свой рельеф или нет
        никакого."""
        self.tiles.clear()
        self._ranges.clear()
        self.added = []
        self.low = 0.0
        self.version += 1

    def add(self, tile):
        # Кэш размахов не сбрасывается. Размах помнит тайл высот, по
        # которому посчитан, и пересчитывается, когда лучший тайл другой.
        # Раньше каждый новый тайл высот сбрасывал весь кэш, и выбор
        # тайлов заново считал размахи всех тайлов кадра.
        self.tiles[(tile.z, tile.x, tile.y)] = tile
        self.low = min(self.low, float(tile.low))
        self.version += 1
        self.added.append((tile.z, tile.x, tile.y))

    def snapshot(self):
        """Копия для рабочего потока: тот же набор тайлов и масштаб.

        Главный поток добавляет тайлы в словарь, обход того же словаря
        в рабочем потоке мог бы оборваться. Тайлы не меняются, копия
        словаря стоит доли миллисекунды.
        """
        copy = HeightStore()
        copy.tiles = dict(self.tiles)
        copy.deep = list(self.deep)
        copy.max_level = self.max_level
        copy.scale = self.scale
        copy.low = self.low
        copy.version = self.version
        return copy

    def take_added(self):
        """Ключи тайлов, добавленных с прошлого вызова."""
        added, self.added = self.added, []
        return added

    def cap(self, key):
        """Предельный уровень высот для тайла key: max_level, внутри
        рамки врезки - уровень врезки."""
        top = self.max_level
        if self.deep:
            z, x, y = key
            n = float(1 << z)
            u0, v0, u1, v1 = x / n, y / n, (x + 1) / n, (y + 1) / n
            for a, b, c, d, level in self.deep:
                if u0 < c and a < u1 and v0 < d and b < v1:
                    top = max(top, level)
        return top

    def cap_at(self, u, v):
        """Предельный уровень высот в точке с долями мира u, v."""
        top = self.max_level
        for a, b, c, d, level in self.deep:
            if a <= u <= c and b <= v <= d:
                top = max(top, level)
        return top

    def best(self, key):
        """Самый точный готовый тайл высот для тайла подложки key.

        Идёт от уровня height_level(z) вверх к уровню 0. None, если
        не готов даже тайл уровня 0.
        """
        level = height_level(key[0], self.cap(key))
        for zh in range(level, -1, -1):
            tile = self.tiles.get(ancestor(key, zh))
            if tile is not None:
                return tile
        return None

    def for_mesh(self, key):
        """Тайл высот для сетки тайла подложки key и его уровень.

        Рельеф выключен - (None, FLAT_LEVEL). Высот нет - (None, -1).
        Сетка пересобирается, когда уровень больше уровня её сборки.
        """
        if not self.scale:
            return None, FLAT_LEVEL
        tile = self.best(key)
        return tile, -1 if tile is None else tile.z

    def wanted(self, key):
        """Ключ тайла высот, нужного тайлу подложки key."""
        return ancestor(key, height_level(key[0], self.cap(key)))

    def height_at(self, lat, lon):
        """Высота рельефа в точке по самому точному готовому тайлу."""
        if not self.scale:
            return 0.0
        u, v = mercator_share(lat, lon)
        for zh in range(DEEP_LEVEL, -1, -1):
            n = 1 << zh
            key = (zh, min(int(u * n), n - 1), min(int(v * n), n - 1))
            tile = self.tiles.get(key)
            if tile is not None:
                return float(sample(tile, u, v)) * self.scale
        return 0.0

    def heights_at(self, lats, lons, scaled=True):
        """Высоты рельефа в массиве точек, float64.

        То же, что height_at по каждой точке, но тайл подбирается
        для групп точек сразу. По одной точке в Python сборка 29
        провинций Афганистана шла 4.7 с, 28 сентября 2026 года.
        """
        lats = np.asarray(lats, dtype=np.float64)
        lons = np.asarray(lons, dtype=np.float64)
        out = np.zeros(lats.shape)
        if (scaled and not self.scale) or not lats.size:
            return out
        lat = np.clip(lats, -85.05112878, 85.05112878)
        u = ((lons + 180.0) / 360.0) % 1.0
        v = np.clip((1.0 - np.arcsinh(np.tan(np.radians(lat))) / math.pi)
                    / 2.0, 0.0, 1.0)
        left = np.ones(lats.shape, dtype=bool)
        levels = {key[0] for key in self.tiles}
        for zh in range(DEEP_LEVEL, -1, -1):
            if zh not in levels:
                continue
            n = 1 << zh
            idx = np.nonzero(left)[0]
            if not len(idx):
                break
            tx = np.minimum((u[idx] * n).astype(np.int64), n - 1)
            ty = np.minimum((v[idx] * n).astype(np.int64), n - 1)
            for x, y in set(zip(tx.tolist(), ty.tolist())):
                tile = self.tiles.get((zh, x, y))
                if tile is None:
                    continue
                pick = idx[(tx == x) & (ty == y)]
                out[pick] = sample(tile, u[pick], v[pick])
                left[pick] = False
        # scaled=False - настоящие высоты, для линейки и профиля. Они
        # нужны и при выключенном рельефе.
        return out * self.scale if scaled else out

    def range_for(self, key):
        """Наименьшая и наибольшая высота для тайла подложки key.

        Берутся из блока пикселей готового тайла высот, который тайл
        подложки накрывает. Блок расширен на пиксель с каждой стороны:
        выборка билинейная и берёт соседние пиксели. Без данных - (0, 0).

        Размах всего тайла высот уровня 15 в горах - сотни метров. Выбор
        тайлов раздувает сферу тайла на половину размаха, и с грубой
        оценкой мелкие тайлы у камеры дробились бы без нужды.
        """
        tile = self.best(key) if self.scale else None
        if tile is None:
            return (0.0, 0.0)
        low, high = self._range(key, tile)
        return (low * self.scale, high * self.scale)

    def _range(self, key, tile):
        """Размах высот тайла подложки key по тайлу высот, без масштаба."""
        cached = self._ranges.get(key)
        if cached is not None and cached[0] is tile:
            return cached[1]
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
        self._ranges[key] = (tile, result)
        return result
