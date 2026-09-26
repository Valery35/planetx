# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выбор тайлов для кадра по экранной ошибке.

Ошибка тайла уровня z - размер его текселя на местности,
e = 2πA·cos φ / (256·2^z). Экранная ошибка равна e·f / d, где f - фокусное
расстояние в пикселях, d - расстояние от глаза до ближайшей точки тайла.
Тайл делится на четыре, если экранная ошибка больше порога.

Тайл заменяется детьми только тогда, когда все его видимые дети готовы
к рисованию. До того рисуется он сам или его готовый предок. Поэтому
дыр в подложке нет по построению. Устройство описано в AGENTS.md,
раздел «Выбор уровня детализации».

Выбор идёт каждый кадр на Python, поэтому границы тайла считаются
один раз и кэшируются, а обход считает на числах Python без NumPy.
"""
import math
from collections import namedtuple

try:  # внутри плагина QGIS
    from .ellipsoid import A, B, E2
    from .tiling import MAX_LEVEL, skirt_depth
except ImportError:  # headless-тесты
    from ellipsoid import A, B, E2
    from tiling import MAX_LEVEL, skirt_depth

THRESHOLD = 1.5  # пикселей
TEXELS = 256
CIRCUMFERENCE = 2.0 * math.pi * A
# Запас к радиусу описанной сферы и к угловому радиусу тайла. Точки
# между девятью опорными могут лежать чуть дальше них.
MARGIN = 1.05
MIN_DISTANCE = 0.5
CACHE_LIMIT = 200000

TileInfo = namedtuple("TileInfo", "center radius direction alpha texel")
Selection = namedtuple("Selection", "draw want keep visited")
Selection.__doc__ = """Итог выбора.

draw - тайлы для рисования, без перекрытий. want - тайлы для загрузки
с приоритетом. keep - все нужные кадру тайлы, их нельзя вытеснять
из памяти. visited - количество просмотренных узлов дерева.
"""

_cache = {}


def _ecef(lat, lon):
    """geodetic_to_ecef для одной точки на math, без NumPy.

    Выбор тайлов считает границы новых тайлов прямо в кадре. NumPy
    на одиночных числах тратит около 30 мкс на тайл, math - единицы.
    Совпадение с geodetic_to_ecef держит тест.
    """
    la, lo = math.radians(lat), math.radians(lon)
    sin_lat, cos_lat = math.sin(la), math.cos(la)
    n = A / math.sqrt(1.0 - E2 * sin_lat * sin_lat)
    return (n * cos_lat * math.cos(lo), n * cos_lat * math.sin(lo),
            n * (1.0 - E2) * sin_lat)


def tile_info(z, x, y):
    """Границы тайла: описанная сфера, направление и угловой радиус.

    texel - наибольший размер текселя на местности, по широте, ближайшей
    к экватору.
    """
    key = (z, x, y)
    info = _cache.get(key)
    if info is not None:
        return info
    n = 1 << z
    lats = [math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * (y + f)
                                                        / n))))
            for f in (0.0, 0.5, 1.0)]
    lons = [(x + f) / n * 360.0 - 180.0 for f in (0.0, 0.5, 1.0)]
    points = [_ecef(la, lo) for la in lats for lo in lons]
    center = points[4]
    radius = max(math.dist(center, p) for p in points)
    radius = radius * MARGIN + skirt_depth(z)
    norm = math.sqrt(sum(c * c for c in center))
    direction = tuple(c / norm for c in center)
    alpha = 0.0
    for p in points:
        pn = math.sqrt(sum(c * c for c in p))
        cos = sum(d * c for d, c in zip(direction, p)) / pn
        alpha = max(alpha, math.acos(max(-1.0, min(1.0, cos))))
    alpha = min(math.pi, alpha * MARGIN)
    north, south = lats[0], lats[2]
    nearest = 0.0 if south <= 0.0 <= north else min(abs(north), abs(south))
    texel = CIRCUMFERENCE * math.cos(math.radians(nearest)) / (TEXELS * n)
    info = TileInfo(center, radius, direction, alpha, texel)
    if len(_cache) > CACHE_LIMIT:
        _cache.clear()
    _cache[key] = info
    return info


def children(key):
    z, x, y = key
    return [(z + 1, 2 * x + dx, 2 * y + dy)
            for dy in (0, 1) for dx in (0, 1)]


class _Frame:
    """Величины камеры, общие для всех тайлов кадра."""

    def __init__(self, camera, threshold):
        self.eye = tuple(float(c) for c in camera.eye)
        rot = camera.rotation
        # Строки - оси камеры в ECEF: вправо, вверх, назад.
        self.axes = [tuple(float(v) for v in rot[:, i]) for i in range(3)]
        t = math.tan(math.radians(camera.fov_y) / 2.0)
        tx, ty = t * camera.aspect, t
        self.focal = camera.height / (2.0 * t)
        self.threshold = threshold
        sx = 1.0 / math.sqrt(1.0 + tx * tx)
        sy = 1.0 / math.sqrt(1.0 + ty * ty)
        # Плоскости боков пирамиды в осях камеры, нормали внутрь.
        self.planes = [(sx, 0.0, -tx * sx), (-sx, 0.0, -tx * sx),
                       (0.0, sy, -ty * sy), (0.0, -sy, -ty * sy)]
        dist = math.sqrt(sum(c * c for c in self.eye))
        self.eye_dir = tuple(c / dist for c in self.eye)
        # Угол от точки под камерой до горизонта, на сфере радиуса B.
        # Меньший радиус даёт больший угол, отсечение остаётся осторожным.
        self.horizon = math.acos(min(1.0, B / dist)) if dist > B else math.pi

    def visible(self, z, info):
        # Счёт развёрнут вручную: функция зовётся сотни раз за кадр.
        ex, ey, ez = self.eye_dir
        dx, dy, dz = info.direction
        cos = ex * dx + ey * dy + ez * dz
        angle = math.acos(-1.0 if cos < -1.0 else 1.0 if cos > 1.0 else cos)
        if angle > self.horizon + info.alpha:
            return False
        if z <= 2:
            return True
        cx, cy, cz = info.center
        px, py, pz = self.eye
        dx, dy, dz = cx - px, cy - py, cz - pz
        (rx, ry, rz), (ux, uy, uz), (bx, by, bz) = self.axes
        x = rx * dx + ry * dy + rz * dz
        y = ux * dx + uy * dy + uz * dz
        zc = bx * dx + by * dy + bz * dz
        r = info.radius
        if zc > r:
            return False
        for a, b, c in self.planes:
            if a * x + b * y + c * zc < -r:
                return False
        return True

    def error(self, info):
        d = math.dist(info.center, self.eye) - info.radius
        if d <= MIN_DISTANCE:
            return math.inf
        return info.texel * self.focal / d


def select(camera, ready, threshold=THRESHOLD, max_level=MAX_LEVEL):
    """Тайлы для кадра.

    ready(key) говорит, готов ли тайл к рисованию. Тайл уровня 0 должен
    быть готов всегда, иначе кадру нечем закрыть Землю.
    """
    frame = _Frame(camera, threshold)
    want = {}
    keep = set()
    visited = [0]

    def visit(key, info):
        """Возвращает тайлы для рисования и признак полного покрытия."""
        visited[0] += 1
        z = key[0]
        keep.add(key)
        error = frame.error(info)
        is_ready = ready(key)
        if not is_ready:
            want[key] = error
        if z < max_level and error > threshold:
            kids = []
            for kid in children(key):
                kid_info = tile_info(*kid)
                if frame.visible(kid[0], kid_info):
                    kids.append((kid, kid_info))
            if not kids:
                # Дети вместе покрывают тайл целиком, и каждое отсечение
                # осторожное. Раз не виден ни один ребёнок, не виден
                # и тайл. Его сфера задела пирамиду под землёй.
                keep.discard(key)
                want.pop(key, None)
                return [], True
            draws = []
            complete = True
            for kid, kid_info in kids:
                kid_draw, kid_complete = visit(kid, kid_info)
                draws.extend(kid_draw)
                complete = complete and kid_complete
            if complete:
                return draws, True
            return ([key], True) if is_ready else ([], False)
        return ([key], True) if is_ready else ([], False)

    root = (0, 0, 0)
    draw, _ = visit(root, tile_info(*root))
    return Selection(draw, want, keep, visited[0])
