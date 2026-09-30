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
    from . import ellipsoid
    from .tiling import MAX_LEVEL, skirt_depth
except ImportError:  # headless-тесты
    import ellipsoid
    from tiling import MAX_LEVEL, skirt_depth

THRESHOLD = 1.5  # пикселей
TEXELS = 256
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


def clear_cache():
    """Забыть границы тайлов: они зависят от размеров тела."""
    _cache.clear()


def _ecef(lat, lon):
    """geodetic_to_ecef для одной точки на math, без NumPy.

    Выбор тайлов считает границы новых тайлов в самом кадре. NumPy
    на одиночных числах тратит около 30 мкс на тайл, math - единицы.
    Совпадение с geodetic_to_ecef держит тест.
    """
    la, lo = math.radians(lat), math.radians(lon)
    sin_lat, cos_lat = math.sin(la), math.cos(la)
    n = ellipsoid.A / math.sqrt(1.0 - ellipsoid.E2 * sin_lat * sin_lat)
    return (n * cos_lat * math.cos(lo), n * cos_lat * math.sin(lo),
            n * (1.0 - ellipsoid.E2) * sin_lat)


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
    texel = (2.0 * math.pi * ellipsoid.A * math.cos(math.radians(nearest))
             / (TEXELS * n))
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
        b = ellipsoid.B
        self.horizon = math.acos(min(1.0, b / dist)) if dist > b else math.pi
        self.b = b

    def visible(self, z, info, low=0.0, high=0.0):
        """Может ли тайл попасть в кадр.

        low и high - наименьшая и наибольшая высота рельефа в тайле.
        Вершина высотой high видна из-за горизонта ещё на угол
        acos(B / (B + high)). Сфера тайла для пирамиды поднимается
        на середину слоя высот и раздувается на половину его толщины.
        """
        # Счёт развёрнут вручную: функция зовётся сотни раз за кадр.
        ex, ey, ez = self.eye_dir
        dx, dy, dz = info.direction
        cos = ex * dx + ey * dy + ez * dz
        angle = math.acos(-1.0 if cos < -1.0 else 1.0 if cos > 1.0 else cos)
        b = self.b
        beyond = math.acos(b / (b + high)) if high > 0.0 else 0.0
        if angle > self.horizon + info.alpha + beyond:
            return False
        if z <= 2:
            return True
        (cx, cy, cz), r = _lifted(info, low, high)
        px, py, pz = self.eye
        dx, dy, dz = cx - px, cy - py, cz - pz
        (rx, ry, rz), (ux, uy, uz), (bx, by, bz) = self.axes
        x = rx * dx + ry * dy + rz * dz
        y = ux * dx + uy * dy + uz * dz
        zc = bx * dx + by * dy + bz * dz
        if zc > r:
            return False
        for a, b, c in self.planes:
            if a * x + b * y + c * zc < -r:
                return False
        return True

    def error(self, info, low=0.0, high=0.0):
        center, radius = _lifted(info, low, high)
        d = math.dist(center, self.eye) - radius
        if d <= MIN_DISTANCE:
            return math.inf
        return info.texel * self.focal / d


def _lifted(info, low, high):
    """Сфера тайла с рельефом: центр на середине слоя высот, радиус
    больше на половину толщины слоя.

    Полная высота гор в радиусе дробила бы до уровня 19 все тайлы
    в пределах этой высоты от камеры. Толщина слоя в тайле в горах -
    сотни метров, а не километры.
    """
    if low == 0.0 and high == 0.0:
        return info.center, info.radius
    mid = 0.5 * (low + high)
    cx, cy, cz = info.center
    dx, dy, dz = info.direction
    return ((cx + dx * mid, cy + dy * mid, cz + dz * mid),
            info.radius + 0.5 * (high - low))


INFINITE_PRIORITY = 1.0e9  # приоритет тайла, внутри сферы которого глаз


def priority(error, z):
    """Приоритет загрузки - экранная ошибка, всегда конечная.

    У тайла, внутри сферы которого стоит глаз, ошибка бесконечна.
    Такие тайлы идут первыми, из них раньше грубые.
    """
    if math.isinf(error):
        return INFINITE_PRIORITY - z
    return error


class Memo:
    """Память ошибок и видимости узлов для неподвижной камеры.

    Ошибка тайла и то, виден ли он, зависят от камеры и высот, но не
    от готовности тайлов. Во время загрузки камера стоит, а кадры идут
    на каждый пришедший тайл. Память держит их между такими кадрами.
    Она сбрасывается, когда меняется ключ: камера, порог или версия
    высот, которую даёт вызывающий.
    """

    LIMIT = 100000

    def __init__(self):
        self.key = None
        self.values = {}

    def bind(self, camera, threshold, heights_version, added=()):
        """Словарь для select с этой камерой и этими высотами.

        added - ключи тайлов высот, пришедших с прошлого вызова. Если
        камера та же, забываются только узлы под этими тайлами: их
        размах высот мог измениться. Узлы грубее тайла высот берут
        высоты уровня выше и не меняются. Если версия выросла не на
        количество ключей в added, память сбрасывается целиком.
        """
        camera_key = (tuple(camera.eye), tuple(camera.rotation.ravel()),
                      camera.width, camera.height, camera.fov_y, threshold)
        if self.key is None or camera_key != self.key[0] \
                or len(self.values) > self.LIMIT \
                or heights_version - self.key[1] != len(added):
            self.values = {}
        elif added:
            for hz, hx, hy in added:
                for z, x, y in [k for k in self.values if k[0] >= hz]:
                    shift = z - hz
                    if (x >> shift, y >> shift) == (hx, hy):
                        del self.values[(z, x, y)]
        self.key = (camera_key, heights_version)
        return self.values


_MISSING = object()


def select(camera, ready, threshold=THRESHOLD, max_level=MAX_LEVEL,
           heights=None, memo=None):
    """Тайлы для кадра.

    ready(key) говорит, готов ли тайл к рисованию. Тайл уровня 0 должен
    быть готов всегда, иначе кадру нечем закрыть Землю. heights(key)
    даёт наименьшую и наибольшую высоту рельефа в тайле или осторожную
    оценку этих высот. Без рельефа - None. memo - словарь из Memo.bind
    для этой камеры и этих высот или None.
    """
    frame = _Frame(camera, threshold)
    want = {}
    keep = set()
    visited = [0]
    # Величины кадра в локальных переменных. Обход идёт по сотням узлов
    # каждый кадр, обращение к атрибутам и вызов на узел стоили
    # половину времени выбора. Счёт тот же, что в _Frame.visible,
    # _Frame.error и _lifted, совпадение держит test_lod.TestFastPath.
    px, py, pz = frame.eye
    ex, ey, ez = frame.eye_dir
    (rx, ry, rz), (ux, uy, uz), (bx, by, bz) = frame.axes
    planes = frame.planes
    horizon = frame.horizon
    focal = frame.focal
    acos = math.acos
    sqrt = math.sqrt
    cache = _cache
    polar = ellipsoid.B

    def probe(key, check):
        """Экранная ошибка тайла или None, если он точно не виден.

        Поднятая к слою высот сфера и расстояние до глаза считаются
        один раз и идут и на отсечение, и на ошибку.
        """
        info = cache.get(key)
        if info is None:
            info = tile_info(*key)
        if heights is None:
            low = high = 0.0
        else:
            low, high = heights(key)
        dx, dy, dz = info.direction
        if check:
            cos = ex * dx + ey * dy + ez * dz
            angle = acos(-1.0 if cos < -1.0 else 1.0 if cos > 1.0 else cos)
            beyond = acos(polar / (polar + high)) if high > 0.0 else 0.0
            if angle > horizon + info.alpha + beyond:
                return None
        cx, cy, cz = info.center
        r = info.radius
        if low != 0.0 or high != 0.0:
            mid = 0.5 * (low + high)
            cx += dx * mid
            cy += dy * mid
            cz += dz * mid
            r += 0.5 * (high - low)
        vx, vy, vz = cx - px, cy - py, cz - pz
        if check and key[0] > 2:
            zc = bx * vx + by * vy + bz * vz
            if zc > r:
                return None
            sx = rx * vx + ry * vy + rz * vz
            sy = ux * vx + uy * vy + uz * vz
            for a, b, c in planes:
                if a * sx + b * sy + c * zc < -r:
                    return None
        d = sqrt(vx * vx + vy * vy + vz * vz) - r
        if d <= MIN_DISTANCE:
            return math.inf
        return info.texel * focal / d

    def visit(key, error):
        """Возвращает тайлы для рисования и признак полного покрытия."""
        visited[0] += 1
        z, x, y = key
        keep.add(key)
        is_ready = ready(key)
        if not is_ready:
            want[key] = priority(error, z)
        if z < max_level and error > threshold:
            kids = []
            z1, x2, y2 = z + 1, 2 * x, 2 * y
            # Порядок детей тот же, что у children.
            for kid in ((z1, x2, y2), (z1, x2 + 1, y2), (z1, x2, y2 + 1),
                        (z1, x2 + 1, y2 + 1)):
                if memo is None:
                    kid_error = probe(kid, True)
                else:
                    kid_error = memo.get(kid, _MISSING)
                    if kid_error is _MISSING:
                        kid_error = memo[kid] = probe(kid, True)
                if kid_error is not None:
                    kids.append((kid, kid_error))
            if not kids:
                # Дети вместе покрывают тайл целиком, и каждое отсечение
                # осторожное. Раз не виден ни один ребёнок, не виден
                # и тайл. Его сфера задела пирамиду под землёй.
                keep.discard(key)
                want.pop(key, None)
                return [], True
            if not is_ready and not any(ready(kid) for kid, _ in kids):
                # Фронт загрузки. Ниже неготового тайла без готовых детей
                # рисовать нечего, а просить его потомков рано: они
                # понадобятся, только когда придёт он сам. Без этого
                # правила камера у самой земли просила тысячи тайлов
                # всех уровней сразу, начиная с самых глубоких.
                return [], False
            draws = []
            complete = True
            for kid, kid_error in kids:
                kid_draw, kid_complete = visit(kid, kid_error)
                draws.extend(kid_draw)
                complete = complete and kid_complete
            if complete:
                return draws, True
            return ([key], True) if is_ready else ([], False)
        return ([key], True) if is_ready else ([], False)

    root = (0, 0, 0)
    draw, _ = visit(root, probe(root, False))
    return Selection(draw, want, keep, visited[0])
