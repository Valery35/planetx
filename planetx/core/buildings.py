# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-здания из слоя building векторных тайлов OpenFreeMap.

Расчёт без Qt и OpenGL. Слой building схемы OpenMapTiles несёт контуры
зданий и высоты render_height и render_min_height в метрах. Высота
в тайлах - высота OSM, иначе этажи × 3.66 м, иначе 5 м. Отдельные
здания есть с уровня LEVEL, на уровне 13 они слиты в кварталы без
высот.

Работа идёт в два шага. footprints - разбор тайла, обрезка по краю
тайла и нарезка крыш, от рельефа не зависит, идёт в рабочем потоке.
mesh - вершины по высотам рельефа, одними операциями NumPy, её можно
повторить, когда пришли точнее высоты.

Генератор тайлов сливает здания одной высоты в мультиполигон
и оставляет им запас за краем тайла. Кольца обрезаются по краю, стена
по краю тайла не ставится, остаток здания лежит в соседнем тайле.
Отметка дома - наивысшая точка рельефа под его контуром в этом тайле:
от низкой на склоне дом уходил под землю. У здания на стыке тайлов
на склоне половины могут разойтись по высоте на перепад рельефа.

Крыша плоская или скатная, форма из roof_shape Overture. Плоская
режется на треугольники в координатах тайла: выпуклый контур без
дворов - веером, одной операцией NumPy для всех таких зданий, прочие -
отсечением ушей, двор соединяется с контуром мостом. Отсечение ушей
из core.features шло 130-360 мс на тайл уровня 14, 29 сентября
2026 года.

Скатная крыша задана плоскостями h = a·u + b·v + c по эталону
maplibre-landmarks: контур режется по линиям перегиба, каждый кусок
поднимается на свою плоскость, карниз закрывается отвесной стенкой.
У вальмовой крыши на контуре вогнутом или длиннее четырёх вершин
плоскости дают неверный конёк, там работает прямой скелет bpypolyskel
из core/skeleton. Контур больше MAX_ROOF_AREA остаётся плоским: скат
на такой площади читается плитой.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .ellipsoid import (ecef_to_geodetic, geodetic_to_ecef,
                            surface_normal)
    from .features import centered
    from .places import (EXTENT, _fields, _packed, _unpack, _value,
                         _zigzag)
    from .skeleton import Vector, polygonize
    from .tiling import lat_of_row, lonlat_to_tile, tile_bounds
except ImportError:  # headless-тесты
    import ellipsoid
    from ellipsoid import (ecef_to_geodetic, geodetic_to_ecef,
                           surface_normal)
    from features import centered
    from places import EXTENT, _fields, _packed, _unpack, _value, _zigzag
    from skeleton import Vector, polygonize
    from tiling import lat_of_row, lonlat_to_tile, tile_bounds

LAYER = "building"
LEVEL = 14
# Высота этажа и здания без высоты и этажей, метры, - как у генератора
# тайлов OpenMapTiles. По ним считаются здания Overture Maps.
FLOOR = 3.66
DEFAULT_HEIGHT = 5.0
# Цвет здания без поля colour. Величину назначил помощник 29 сентября
# 2026 года, её утверждает автор.
DEFAULT_COLOR = (226, 222, 214)
# Формы крыш Overture Maps (roof_shape). 0 - плоская крыша, её несут
# и прочие значения: none, unknown, complex, many, mixed.
FLAT = 0
GABLED = 1
HIPPED = 2
PYRAMIDAL = 3
HALF_HIPPED = 4
SALTBOX = 5
GAMBREL = 6
MANSARD = 7
SKILLION = 8
ROUND = 9
BELLCAST_GABLE = 10
BUTTERFLY = 11
CROSSPITCHED = 12
SAWTOOTH = 13
DOME = 14
ONION = 15
CONE = 16
# Крыши по плоскостям профиля: контур режется по линиям перегиба.
PROFILE_SHAPES = (GABLED, HIPPED, HALF_HIPPED, PYRAMIDAL, SALTBOX,
                  GAMBREL, MANSARD, SKILLION, ROUND, BELLCAST_GABLE,
                  BUTTERFLY, CROSSPITCHED, SAWTOOTH)
# Крыши по телу вращения вокруг центра контура: купол, луковица, конус.
RADIAL_SHAPES = (DOME, ONION, CONE)
ROOF_SHAPES = {
    # Плоская: сама flat и то, что по эталону крыши не даёт.
    "flat": FLAT, "none": FLAT, "unknown": FLAT, "complex": FLAT,
    "many": FLAT, "mixed": FLAT, "mix": FLAT, "multi": FLAT,
    "gabled_row": FLAT,
    # Двускатные: gabled и его варианты, включая алиасы эталона.
    "gabled": GABLED, "saltbox": SALTBOX, "gambrel": GAMBREL,
    "mansard": MANSARD, "pitched": GABLED,
    "gabled_height_moved": GABLED, "gabled_irregular": GABLED,
    "double_saltbox": GABLED, "quadruple_saltbox": GABLED,
    "hipped": HIPPED, "side_hipped": HIPPED,
    "hipped_and_gabled": HIPPED,
    "half_hipped": HALF_HIPPED, "side_half_hipped": HALF_HIPPED,
    "pyramidal": PYRAMIDAL, "pyramid": PYRAMIDAL,
    # Односкатные: плоскость от карниза до верха стены.
    "skillion": SKILLION, "lean_to": SKILLION, "monopitch": SKILLION,
    "shed": SKILLION,
    # Кривые и пилообразные профили из эталона maplibre-landmarks.
    "round": ROUND, "bellcast_gable": BELLCAST_GABLE,
    "butterfly": BUTTERFLY, "crosspitched": CROSSPITCHED,
    "sawtooth": SAWTOOTH,
    # Тела вращения: купол (spherical - имя Overture), луковица, конус.
    "dome": DOME, "spherical": DOME, "onion": ONION, "cone": CONE,
}
# Крутизна ската по умолчанию, градусы. По ней оценивается высота крыши,
# когда в тайле нет roof_height. 30 - как в OSM Buildings и maplibre-landmarks.
ROOF_PITCH = 30.0
# Пила: желаемая ширина зуба, метры, и вынос почти отвесного остекления,
# метры. Величины эталона maplibre-landmarks, profiles.ts.
TOOTH_M = 8.0
GLAZING_M = 0.02
# Купол и луковица: колец по высоте и точек по кольцу, как в эталоне.
DOME_STEPS = 12
LATHE_POINTS = 48
# Профиль луковицы OSMBuildings: доля радиуса и доля высоты на кольцо.
ONION_PROFILE = ((0.8, 0.0), (0.9, 0.18), (0.9, 0.35), (0.8, 0.47),
                 (0.6, 0.59), (0.5, 0.65), (0.2, 0.82), (0.0, 1.0))
# Крыша ниже этого не рисуется, метры: от низкой крыши одна рябь.
MIN_ROOF = 0.5
# Контур больше этого - плоская крыша, м². У огромных домов в Overture
# часто ошибочный скат, а подъём упирается в половину стены, и скат на
# 140x90 м читается плоской плитой. Просьба автора от 19 ноября 2026
# года: 5422 м² saltbox в его районе, 58.020797, 56.276039.
MAX_ROOF_AREA = 2000.0
# Цвет скатов по умолчанию, RGB: как в OSM Buildings. Фронтоны (торцы,
# вальмовые свесы) остаются цветом стены.
ROOF_COLOR = (185, 169, 154)
# Дальность показа от глаза, метры, и бюджет: тайлов и вершин в
# видеокарте. Величины помощника, автор утвердил их 29 сентября 2026
# года. Вершина - 20 байт, 1.5 млн вершин - около 30 МБ.
RANGE = 6000.0
MAX_TILES = 32
MAX_VERTICES = 1500000
# Пустой тайл: зданий нет. None у загрузчика значит ошибку разбора.
EMPTY = "empty"
# Вершина сетки: смещение от центра тайла, нормаль и цвет.
VERTEX = np.dtype([("position", "<f4", 3), ("normal", "i1", 4),
                   ("color", "u1", 4)])

Roof = namedtuple("Roof", "shape direction height")
Roof.__doc__ = """Крыша здания Overture.

shape - FLAT..CONE. direction - азимут конька в градусах или
None. height - высота ската в метрах или None, тогда оценивается по
ROOF_PITCH.
"""

Building = namedtuple("Building", "rings height base color roof")
Building.__doc__ = """Здание из тайла.

rings - кольца в единицах тайла, массивы (n, 2) без повтора первой
точки. Первое - контур с положительной площадью, дальше дворы
с отрицательной. height - высота крыши над землёй, base - высота
низа, метры. color - RGB 0-255 или None. roof - запись Roof.
"""

Footprint = namedtuple(
    "Footprint",
    "key latlon next wall owner height base color roof "
    "roof_h roof_xy roof_rise roof_tri roof_owner",
    defaults=(None, None, None, None, None))
Footprint.__doc__ = """Здания тайла без высот рельефа.

latlon - все точки колец (N, 2) в градусах. next - номер следующей
точки кольца. wall - ставится ли стена на ребре от точки к следующей.
owner - номер здания точки. height, base - по зданиям, метры. color -
по зданиям (B, 3) uint8. roof - треугольники плоских крыш, номера
точек uint32. roof_h - высота ската по зданиям, метры (0 - плоская).
roof_xy - точки скатных крыш (R, 2) в градусах, roof_rise - их подъём
0-1, roof_tri - треугольники (номера точек R), roof_owner - здание
точки. Поля скатных крыш есть только когда они есть в тайле.
"""

Mesh = namedtuple("Mesh", "key center vertices indices")
Mesh.__doc__ = """Сетка зданий тайла.

center - центр в ECEF, float64. vertices - массив VERTEX, смещения
от центра. indices - треугольники uint32.
"""


def parse_color(value):
    """Цвет «#rrggbb» или «#rgb» в тройку 0-255, иначе None."""
    if not isinstance(value, str):
        return None
    text = value.strip().lstrip("#")
    if len(text) == 3:
        text = "".join(c * 2 for c in text)
    if len(text) != 6:
        return None
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def area(ring):
    """Площадь кольца со знаком по формуле трапеций."""
    x, y = ring[:, 0], ring[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def _rings(geometry):
    """Кольца геометрии многоугольника MVT: пары (массив (n, 2), площадь).

    Площадь считается по ходу разбора. Через np.roll на каждое кольцо
    она занимала половину времени разбора тайла.
    """
    out = []
    ring = None
    twice = 0
    x = y = 0
    i = 0
    n = len(geometry)
    while i < n:
        command = geometry[i]
        i += 1
        kind, count = command & 7, command >> 3
        if kind == 1 or kind == 2:
            for _ in range(count):
                if i + 1 >= n:
                    return out
                px, py = x, y
                x += _zigzag(geometry[i])
                y += _zigzag(geometry[i + 1])
                i += 2
                if kind == 1:
                    ring = [(x, y)]
                    twice = 0
                elif ring is not None:
                    ring.append((x, y))
                    twice += px * y - x * py
        elif kind == 7:
            if ring is not None and len(ring) >= 3:
                x0, y0 = ring[0]
                twice += x * y0 - x0 * y
                out.append((np.array(ring, dtype=np.float64), 0.5 * twice))
            ring = None
        else:
            return out
    return out


def decode(data):
    """Здания тайла: список Building и extent слоя.

    Здания с hide_3d пропускаются, это части, которые OSM описывает
    ещё и целым зданием. Кольцо нулевой площади пропускается.
    """
    for number, wire, layer in _fields(_unpack(data)):
        if number != 3 or wire != 2:
            continue
        fields = list(_fields(layer))
        title = next((bytes(v).decode("utf-8", errors="replace")
                      for n, w, v in fields if n == 1 and w == 2), None)
        if title != LAYER:
            continue
        keys = [bytes(v).decode("utf-8", errors="replace")
                for n, w, v in fields if n == 3 and w == 2]
        raw = [v for n, w, v in fields if n == 4 and w == 2]
        extent = next((v for n, w, v in fields if n == 5 and w == 0),
                      EXTENT)
        return _buildings(fields, keys, raw), extent
    return [], EXTENT


def _buildings(fields, keys, raw):
    out = []
    for n, w, feature in fields:
        if n != 2 or w != 2:
            continue
        tags = []
        geometry = []
        kind = 0
        for fn, fw, fv in _fields(feature):
            if fn == 2 and fw == 2:
                tags = _packed(fv)
            elif fn == 3 and fw == 0:
                kind = fv
            elif fn == 4 and fw == 2:
                geometry = _packed(fv)
        if kind != 3:
            continue
        attrs = {}
        for k, v in zip(tags[0::2], tags[1::2]):
            if k < len(keys) and v < len(raw):
                attrs[keys[k]] = _value(raw[v])
        if attrs.get("hide_3d") or attrs.get("is_underground"):
            continue
        height, base = heights(attrs)
        if height <= base:
            continue
        color = parse_color(attrs.get("colour") or attrs.get("facade_color"))
        roof = roof_attrs(attrs)
        rings = []
        for ring, s in _rings(geometry):
            if s > 0.0:
                if rings:
                    out.append(Building(rings, height, base, color, roof))
                rings = [ring]
            elif s < 0.0 and rings:
                rings.append(ring)
        if rings:
            out.append(Building(rings, height, base, color, roof))
    return out


def heights(attrs):
    """Высота верха и низа здания, метры. Схема OpenMapTiles -
    render_height и render_min_height. Схема Overture Maps - height,
    min_height, иначе этажи num_floors и min_floor по FLOOR, иначе
    DEFAULT_HEIGHT, как делает генератор тайлов OpenMapTiles."""
    if "render_height" in attrs:
        return (float(attrs.get("render_height") or 0.0),
                float(attrs.get("render_min_height") or 0.0))
    height = attrs.get("height")
    if not height and attrs.get("num_floors"):
        height = float(attrs["num_floors"]) * FLOOR
    base = attrs.get("min_height")
    if not base and attrs.get("min_floor"):
        base = float(attrs["min_floor"]) * FLOOR
    return float(height or DEFAULT_HEIGHT), float(base or 0.0)


def roof_attrs(attrs):
    """Крыша Overture: форма, азимут конька, высота ската.

    Название формы по эталону (OSM2World/maplibre-landmarks) сверяется
    без учёта регистра, а "_" и "-" равнозначны: half-hipped и
    half_hipped - одно и то же. Незнакомые значения - плоская крыша,
    как и flat, many, mixed, gabled_row.
    """
    name = (attrs.get("roof_shape") or "").strip().lower()
    name = name.replace("-", "_").replace(" ", "_")
    shape = ROOF_SHAPES.get(name, FLAT)
    direction = attrs.get("roof_direction")
    if direction in (None, ""):
        direction = None
    else:
        try:
            direction = float(str(direction).replace(",", "."))
        except ValueError:
            direction = None
    height = attrs.get("roof_height")
    if height in (None, ""):
        height = None
    else:
        try:
            height = float(str(height).replace(",", "."))
        except ValueError:
            height = None
    return Roof(shape, direction, height)


def _clip_side(points, axis, limit, below):
    """Отсечение кольца полуплоскостью, алгоритм Сазерленда-Ходжмана."""
    value = points[:, axis]
    inside = value <= limit if below else value >= limit
    if inside.all():
        return points
    if not inside.any():
        return points[:0]
    out = []
    for i in range(len(points)):
        p, q = points[i - 1], points[i]
        if inside[i] != inside[i - 1]:
            t = (limit - p[axis]) / (q[axis] - p[axis])
            cut = p + (q - p) * t
            cut[axis] = limit
            out.append(cut)
        if inside[i]:
            out.append(q)
    return np.array(out, dtype=np.float64)


def clip(ring, extent):
    """Кольцо, обрезанное по квадрату тайла [0, extent], или None."""
    if ring.min() >= 0.0 and ring.max() <= extent:
        return ring
    points = ring
    for axis, limit, below in ((0, 0.0, False), (0, extent, True),
                               (1, 0.0, False), (1, extent, True)):
        points = _clip_side(points, axis, float(limit), below)
        if len(points) < 3:
            return None
    # Точки на углу тайла могут повториться подряд.
    keep = np.any(points != np.roll(points, 1, axis=0), axis=1)
    points = points[keep]
    if len(points) < 3 or area(points) == 0.0:
        return None
    return points


def _orient(a, b, c):
    return (b[..., 0] - a[..., 0]) * (c[..., 1] - a[..., 1]) \
        - (b[..., 1] - a[..., 1]) * (c[..., 0] - a[..., 0])


def ear_clip(points):
    """Треугольники кольца против часовой стрелки, список троек номеров.

    Ухо проверяется только по вогнутым вершинам, их у зданий
    единицы. Точки, совпавшие с вершинами уха, его не закрывают, так
    проходят мосты к дворам. Если ухо не нашлось, остаток режется
    веером.
    """
    n = len(points)
    if n < 3:
        return []
    xs = points[:, 0].tolist()
    ys = points[:, 1].tolist()
    prev = [n - 1] + list(range(n - 1))
    nxt = list(range(1, n)) + [0]

    def cross(a, b, c):
        return (xs[b] - xs[a]) * (ys[c] - ys[b]) \
            - (ys[b] - ys[a]) * (xs[c] - xs[b])

    def blocked(a, b, c):
        ax, ay, bx, by, cx, cy = xs[a], ys[a], xs[b], ys[b], xs[c], ys[c]
        left, right = min(ax, bx, cx), max(ax, bx, cx)
        low, high = min(ay, by, cy), max(ay, by, cy)
        for r in reflex:
            px, py = xs[r], ys[r]
            if px < left or px > right or py < low or py > high:
                continue
            if ((px == ax and py == ay) or (px == bx and py == by)
                    or (px == cx and py == cy)):
                continue
            if ((bx - ax) * (py - ay) - (by - ay) * (px - ax) >= 0
                    and (cx - bx) * (py - by) - (cy - by) * (px - bx) >= 0
                    and (ax - cx) * (py - cy) - (ay - cy) * (px - cx) >= 0):
                return True
        return False

    reflex = {i for i in range(n) if cross(prev[i], i, nxt[i]) <= 0}
    out = []
    remaining = n
    i = 0
    stall = 0
    while remaining > 3 and stall < remaining:
        a, c = prev[i], nxt[i]
        if i not in reflex and not blocked(a, i, c):
            out.append((a, i, c))
            nxt[a] = c
            prev[c] = a
            remaining -= 1
            for v in (a, c):
                if v in reflex and cross(prev[v], v, nxt[v]) > 0:
                    reflex.discard(v)
            i = c
            stall = 0
        else:
            i = nxt[i]
            stall += 1
    a = i
    b = nxt[a]
    c = nxt[b]
    while c != a:
        out.append((a, b, c))
        b = c
        c = nxt[c]
    return out


def _crosses(p, q, starts, ends):
    """Пересекает ли отрезок pq какой-нибудь из отрезков внутри или
    проходит ли через вершину, кроме своих концов.

    Мост через вершину двора ложится на его сторону, нарезка на таком
    кольце вставала. Так было у здания в Берлине, 29 сентября 2026 года.
    """
    d1 = _orient(starts, ends, p)
    d2 = _orient(starts, ends, q)
    d3 = _orient(p, q, starts)
    d4 = _orient(p, q, ends)
    if np.any((d1 * d2 < 0.0) & (d3 * d4 < 0.0)):
        return True
    along = (starts - p) @ (q - p)
    return bool(np.any((d3 == 0.0) & (along > 0.0)
                       & (along < float((q - p) @ (q - p)))))


def bridge(points, outer, holes):
    """Контур с дворами одним кольцом через мосты, список номеров точек.

    outer - номера точек контура против часовой стрелки, holes -
    номера точек дворов по часовой. Мост идёт от самой правой точки
    двора к ближайшей точке кольца, если он не пересекает стороны.
    Двор без такого моста пропускается, крыша тогда его закрывает.
    """
    ring = list(outer)
    holes = sorted(holes, key=lambda h: -points[h, 0].max())
    for number, hole in enumerate(holes):
        m = hole[int(np.argmax(points[hole, 0]))]
        edges = [np.array(ring)] + [np.array(h) for h in holes[number:]]
        starts = np.vstack([points[e] for e in edges])
        ends = np.vstack([points[np.roll(e, -1)] for e in edges])
        order = np.argsort(((points[ring] - points[m]) ** 2).sum(axis=1))
        for position in order.tolist():
            v = ring[position]
            if not _crosses(points[m], points[v], starts, ends):
                start = hole.index(m)
                loop = hole[start:] + hole[:start + 1]
                ring = ring[:position + 1] + loop + ring[position:]
                break
    return ring


def roof(points, rings):
    """Треугольники крыши, номера точек uint32.

    rings - списки номеров точек колец здания, первое - контур.
    Если с дворами вышел вывернутый треугольник, крыша режется по
    контуру без дворов и закрывает их. Вывернутый треугольник лёг бы
    за контур здания.
    """
    outer = rings[0]
    if len(rings) > 1:
        tri = _cut(points, bridge(points, outer, rings[1:]))
        t = points[tri.reshape(-1, 3)]
        if not np.any(_orient(t[:, 0], t[:, 1], t[:, 2]) < 0.0):
            return tri
    return _cut(points, outer)


def _cut(points, ring):
    triples = ear_clip(points[ring])
    return np.asarray([ring[k] for t in triples for k in t],
                      dtype=np.uint32)


def _centroid(points):
    """Центроид кольца без повтора первой точки."""
    x, y = points[:, 0], points[:, 1]
    cross = x * np.roll(y, -1) - np.roll(x, -1) * y
    twice = float(cross.sum())
    if twice == 0.0:
        return points.mean(axis=0)
    cx = float(np.dot(x + np.roll(x, -1), cross) / (3.0 * twice))
    cy = float(np.dot(y + np.roll(y, -1), cross) / (3.0 * twice))
    return np.array([cx, cy])


def _face(roof):
    """Куда смотрит главный скат, единичный вектор, или None."""
    if roof.direction is None:
        return None
    a = math.radians(roof.direction)
    return np.array([math.sin(a), -math.cos(a)])


def _roof_frame(points, direction):
    """Рамка крыши: центр, оси u (вдоль конька) и v, полуразмеры L, W.

    Без roof_direction ось конька - та, поперёк которой контур уже
    всего: конёк идёт вдоль длинной стороны.
    """
    if direction is not None:
        u = np.array([-direction[1], direction[0]], dtype=np.float64)
    else:
        best = None
        for deg in range(0, 180, 2):
            a = math.radians(deg)
            cand = np.array([math.cos(a), math.sin(a)])
            pv = points @ np.array([-cand[1], cand[0]])
            width = float(pv.max() - pv.min())
            if best is None or width < best[0] - 1e-9:
                best = (width, cand)
        u = best[1]
    norm = float(np.hypot(u[0], u[1]))
    if norm <= 0.0:
        return None
    u = u / norm
    v = np.array([-u[1], u[0]])
    pu = points @ u
    pv = points @ v
    cu = 0.5 * (float(pu.min()) + float(pu.max()))
    cv = 0.5 * (float(pv.min()) + float(pv.max()))
    half_l = 0.5 * float(pu.max() - pu.min())
    half_w = 0.5 * float(pv.max() - pv.min())
    return u * cu + v * cv, u, v, half_l, half_w


def _roof_profile(shape, height, half_l, half_w, scale=1.0):
    """Плоскости скатов: h = a*u + b*v + c; высота крыши - наименьшая.

    Профиль - как в maplibre-landmarks: крыша задана плоскостями, а
    контур лишь режется по линиям, где плоскости пересекаются. Список
    групп, высота крыши - наибольшая из низших плоскостей группы.
    scale - метров в единице тайла, по нему пила считает ширину зуба.
    """
    if half_l <= 0.0 or half_w <= 0.0:
        return None
    if shape == PYRAMIDAL:
        shape = HIPPED
    gable = [(0.0, -height / half_w, height),
             (0.0, height / half_w, height)]
    if shape == GABLED:
        return [gable]
    if shape == HIPPED:
        return [gable + [(-height / half_w, 0.0, height * half_l / half_w),
                         (height / half_w, 0.0, height * half_l / half_w)]]
    if shape == HALF_HIPPED:
        return [gable + [(-height / half_w, 0.0,
                          0.5 * height + height * half_l / half_w),
                         (height / half_w, 0.0,
                          0.5 * height + height * half_l / half_w)]]
    if shape == SALTBOX:
        # Конёк смещён на треть полуширины: скаты разной длины.
        r = half_w / 3.0
        lo, hi = half_w - r, half_w + r
        return [[(0.0, -height / lo, height * half_w / lo),
                 (0.0, height / hi, height * half_w / hi)]]

    def sides(s):
        # Бока gambrel/mansard: крутой низ до 0.6 H, пологий верх до H.
        return [(0.0, -s * 1.8 * height / half_w, 1.8 * height),
                (0.0, -s * 0.6 * height / half_w, height)]
    if shape == GAMBREL:
        return [sides(1) + sides(-1)]
    if shape == MANSARD:
        def ends(s):
            # Торцы с теми же уклонами, от карниза торца (u = +-L).
            return [(-s * 1.8 * height / half_w, 0.0,
                     1.8 * height * half_l / half_w),
                    (-s * 0.6 * height / half_w, 0.0,
                     0.4 * height + 0.6 * height * half_l / half_w)]
        return [sides(1) + sides(-1) + ends(1) + ends(-1)]
    if shape == SKILLION:
        # Односкатная: одна плоскость от карниза (v = -W) до верха
        # стены (v = +W). Низ - со стороны главного ската.
        return [[(0.0, height / (2.0 * half_w), 0.5 * height)]]
    if shape == ROUND:
        # Полукруг поперёк конька восемью плоскостями, как в эталоне.
        planes = []
        for k in range(8):
            v0 = -half_w + 2.0 * half_w * k / 8.0
            v1 = -half_w + 2.0 * half_w * (k + 1) / 8.0
            h0 = height * math.sqrt(max(0.0, 1.0 - (v0 / half_w) ** 2))
            h1 = height * math.sqrt(max(0.0, 1.0 - (v1 / half_w) ** 2))
            slope = (h1 - h0) / (v1 - v0)
            planes.append((0.0, slope, h0 - slope * v0))
        return [planes]
    if shape == BELLCAST_GABLE:
        def side(s):
            # Крутой верх до 0.2 H на 70 % прогона, затем пологий отлив.
            return [(0.0, -s * 0.8 * height / (0.7 * half_w), height),
                    (0.0, -s * 0.2 * height / (0.3 * half_w),
                     0.2 * height / 0.3)]
        return [[p, q] for p in side(1) for q in side(-1)]
    if shape == BUTTERFLY:
        # Буква V: карнизы по длинным сторонам, ложбина посередине.
        return [[(0.0, -height / half_w, 0.0)],
                [(0.0, height / half_w, 0.0)]]
    if shape == CROSSPITCHED:
        # Два конька крестом: фронтоны со всех четырёх сторон.
        return [gable,
                [(-height / half_l, 0.0, height),
                 (height / half_l, 0.0, height)]]
    if shape == SAWTOOTH:
        # Пила: у каждого зуба отвесное остекление и скат вниз.
        teeth = max(1, int(round(2.0 * half_w * scale / TOOTH_M)))
        width = 2.0 * half_w / teeth
        glazing = min(GLAZING_M / scale, 0.1 * width)
        groups = []
        for k in range(teeth):
            start = -half_w + k * width
            top = start if k == 0 else start + glazing
            run = start + width - top
            slope = (0.0, -height / run,
                     height * (start + width) / run)
            if k == 0:
                # Высокая сторона первого зуба - стена дома.
                groups.append([slope])
            else:
                groups.append([slope,
                               (0.0, height / glazing,
                                -height * start / glazing)])
        return groups
    return None


def _roof_pairs(shape, groups):
    """Плоскости, которым положено сходиться: у пилы только соседние."""
    if shape != SAWTOOTH or len(groups) < 2:
        return None
    pairs = []
    for k in range(1, len(groups)):
        slope = groups[k][0]
        glazing = groups[k][1]
        pairs.append((slope, glazing))
        pairs.append((groups[k - 1][0], glazing))
    return pairs


def _roof_at(groups, pu, pv):
    """Высота крыши в точке рамки: наибольшая из низших плоскостей."""
    best = 0.0
    for group in groups:
        low = min(a * pu + b * pv + c for a, b, c in group)
        if low > best:
            best = low
    return best


def _roof_creases(groups, box, pairs=None):
    """Линии перегиба: где две плоскости профиля равны."""
    if pairs is None:
        planes = [p for group in groups for p in group]
        pairs = [(planes[i], planes[j]) for i in range(len(planes))
                 for j in range(i + 1, len(planes))]
    out = []
    seen = set()
    for first, second in pairs:
        a = first[0] - second[0]
        b = first[1] - second[1]
        c = first[2] - second[2]
        norm = math.hypot(a, b)
        if norm < 1e-9:
            continue
        a, b, c = a / norm, b / norm, c / norm
        if a < -1e-9 or (abs(a) <= 1e-9 and b < 0.0):
            a, b, c = -a, -b, -c
        key = (round(a, 6), round(b, 6), round(c, 6))
        if key in seen:
            continue
        seen.add(key)
        corners = [(box[0], box[1]), (box[2], box[1]),
                   (box[2], box[3]), (box[0], box[3])]
        side = [a * u + b * v + c for u, v in corners]
        if all(x > 1e-9 for x in side) or all(x < -1e-9 for x in side):
            continue
        out.append((a, b, c))
    return out


def _cut_piece(piece, line, side):
    """Часть выпуклого куска по одну сторону прямой a*u + b*v + c = 0."""
    a, b, c = line
    out = []
    n = len(piece)
    for i in range(n):
        p = piece[i]
        q = piece[(i + 1) % n]
        sp = side * (a * p[0] + b * p[1] + c)
        sq = side * (a * q[0] + b * q[1] + c)
        if sp >= 0.0:
            out.append(p)
        if (sp > 0.0 and sq < 0.0) or (sp < 0.0 and sq > 0.0):
            t = sp / (sp - sq)
            out.append((p[0] + (q[0] - p[0]) * t,
                        p[1] + (q[1] - p[1]) * t))
    return out


def _roof_rise(roof, height, base, points, scale=1.0):
    """Высота ската крыши в метрах, 0.0 - крыша плоская.

    Явная roof_height берётся как есть, не выше высоты здания. Иначе
    ROOF_PITCH по полуширине поперёк конька, не выше половины высоты
    здания. У купола, луковицы и круглой крыши подъём по умолчанию
    равен полуширине - полусфера, как в эталоне. У пилы - по половине
    зуба. Ниже MIN_ROOF скат не рисуется: от него одна рябь.
    """
    wall = height - base
    if roof.shape == FLAT or wall <= 0.0:
        return 0.0
    if roof.height is not None and roof.height > 0.0:
        return min(max(roof.height, 0.0), wall)
    frame = _roof_frame(points, _face(roof))
    if frame is None:
        return 0.0
    half_l, half_w = frame[3], frame[4]
    if roof.shape in (ROUND, DOME, ONION):
        rise = min(half_l, half_w) * scale
    elif roof.shape == SAWTOOTH:
        teeth = max(1, int(round(2.0 * half_w * scale / TOOTH_M)))
        rise = math.tan(math.radians(ROOF_PITCH)) * half_w * scale / teeth
    else:
        rise = math.tan(math.radians(ROOF_PITCH)) * min(half_l, half_w) * scale
    rise = min(rise, 0.5 * wall)
    return rise if rise >= MIN_ROOF else 0.0


def roof_surface(points, kind, direction, rise=0.0, scale=1.0):
    """Скатная крыша по контуру: профиль, контур режется по перегибам.

    points - контур (n, 2) в осях тайла. kind - любая форма из
    PROFILE_SHAPES. direction - куда смотрит главный скат или None.
    rise - высота крыши в единицах тайла. scale - метров в единице
    тайла, по нему пила считает ширину зуба. Подъём вершины 0 - карниз,
    1 - конёк. Крыша покрывает сам контур и за стены не свисает. None -
    крыша остаётся плоской.
    """
    if kind not in PROFILE_SHAPES or rise <= 0.0:
        return None
    frame = _roof_frame(points, direction)
    if frame is None:
        return None
    centre, u, v, half_l, half_w = frame
    if half_l <= 0.25 or half_w <= 0.25:
        return None
    groups = _roof_profile(kind, float(rise), half_l, half_w, scale)
    if groups is None:
        return None
    rel = points - centre
    pu = rel @ u
    pv = rel @ v
    box = (float(pu.min()), float(pv.min()),
           float(pu.max()), float(pv.max()))
    lines = _roof_creases(groups, box, _roof_pairs(kind, groups))
    # Контур -> выпуклые треугольники -> разрезать по линиям перегиба.
    pieces = []
    for t in ear_clip(points):
        piece = [(float(pu[k]), float(pv[k])) for k in t]
        if _orient(np.array(piece[0]), np.array(piece[1]),
                   np.array(piece[2])) < 0.0:
            piece = [piece[0], piece[2], piece[1]]
        pieces.append(piece)
    for line in lines:
        cut = []
        for piece in pieces:
            cut.append(_cut_piece(piece, line, 1.0))
            cut.append(_cut_piece(piece, line, -1.0))
        pieces = [p for p in cut if len(p) >= 3]
    verts = []
    fractions = []
    tris = []

    def add(ux, vy, frac):
        verts.append(u * ux + v * vy + centre)
        fractions.append(frac)

    for piece in pieces:
        base = len(verts)
        for ux, vy in piece:
            add(ux, vy, _roof_at(groups, ux, vy) / float(rise))
        for k in range(1, len(piece) - 1):
            tris.extend([base, base + k, base + k + 1])
    # Щель между карнизом и краем крыши закрывается отвесной стенкой.
    n = len(pu)
    for i in range(n):
        j = (i + 1) % n
        ts = [0.0, 1.0]
        for a, b, c in lines:
            sp = a * pu[i] + b * pv[i] + c
            sq = a * pu[j] + b * pv[j] + c
            if sp * sq < 0.0:
                ts.append(sp / (sp - sq))
        ts.sort()
        for k in range(len(ts) - 1):
            t0, t1 = ts[k], ts[k + 1]
            u0 = pu[i] + (pu[j] - pu[i]) * t0
            v0 = pv[i] + (pv[j] - pv[i]) * t0
            u1 = pu[i] + (pu[j] - pu[i]) * t1
            v1 = pv[i] + (pv[j] - pv[i]) * t1
            h0 = _roof_at(groups, u0, v0)
            h1 = _roof_at(groups, u1, v1)
            if h0 < 1e-6 and h1 < 1e-6:
                continue
            base = len(verts)
            add(u0, v0, 0.0)
            add(u1, v1, 0.0)
            add(u1, v1, h1 / float(rise))
            add(u0, v0, h0 / float(rise))
            tris.extend([base, base + 1, base + 2,
                         base, base + 2, base + 3])
    if not tris:
        return None
    return (np.vstack(verts), np.asarray(fractions, dtype=np.float64),
            np.asarray(tris, dtype=np.uint32))


def _subdivide_ring(points, count):
    """Кольцо с длинными рёбрами, разбитыми примерно на count точек."""
    n = len(points)
    lengths = [float(np.linalg.norm(points[(i + 1) % n] - points[i]))
               for i in range(n)]
    perimeter = float(sum(lengths))
    if not perimeter > 0.0:
        return points
    out = []
    for i in range(n):
        p = points[i]
        q = points[(i + 1) % n]
        k = max(1, int(round(lengths[i] / perimeter * count)))
        for j in range(k):
            out.append(p + (q - p) * (j / k))
    return np.asarray(out, dtype=np.float64)


def _lathe_rings(outer, centre, radius, profile, rise):
    """Кольца тела вращения: вершины, подъём 0-1 и треугольники."""
    top = max(h for _, h in profile)
    dx = outer[:, 0] - centre[0]
    dz = outer[:, 1] - centre[1]
    distance = np.hypot(dx, dz)
    distance[distance == 0.0] = 1.0
    rings = []
    for share, h in profile:
        # Нижнее кольцо - сам контур, выше кольца тянутся к кругу радиуса R.
        roundness = min(1.0, 1.5 * h / top) if top > 0.0 else 1.0
        s = share * (1.0 - roundness + roundness * radius / distance)
        rings.append(np.stack([centre[0] + dx * s,
                               centre[1] + dz * s], axis=1))
    verts = np.vstack(rings)
    fractions = np.concatenate([np.full(len(outer), h / rise)
                                for _, h in profile])
    tris = []
    m = len(outer)
    for i in range(len(profile) - 1):
        low = i * m
        high = (i + 1) * m
        for k in range(m):
            k1 = (k + 1) % m
            tris.append([low + k, low + k1, high + k1])
            tris.append([low + k, high + k1, high + k])
    return verts, fractions, np.asarray(tris, dtype=np.uint32).reshape(-1)


def _radial_surface(points, rise, kind):
    """Купол, луковица или конус по контуру: вершины, подъём, треугольники.

    Купол и луковица - тело вращения: нижнее кольцо повторяет контур,
    верхние тянутся к кругу радиуса R = min(полуразмеров) и сходятся
    в вершине. Конус - треугольники от каждого ребра контура к вершине
    над центром: так покрывается и некруглый контур, без плоского
    остатка. None - контур или высота не годятся.
    """
    n = len(points)
    if n < 3 or rise <= 0.0:
        return None
    frame = _roof_frame(points, None)
    if frame is None:
        return None
    centre, _, _, half_l, half_w = frame
    if half_l <= 0.25 or half_w <= 0.25:
        return None
    radius = min(half_l, half_w)
    outer = _subdivide_ring(points, LATHE_POINTS)
    if kind == CONE:
        m = len(outer)
        verts = np.vstack([outer, centre[None, :]])
        fractions = np.concatenate([np.zeros(m), np.ones(1)])
        tris = np.array([[k, (k + 1) % m, m] for k in range(m)],
                        dtype=np.uint32).reshape(-1)
        return verts, fractions, tris
    if kind == DOME:
        # Полукруг по высоте: доля радиуса и подъём на кольцо.
        profile = [(math.cos(i / DOME_STEPS * 0.5 * math.pi),
                    rise * math.sin(i / DOME_STEPS * 0.5 * math.pi))
                   for i in range(DOME_STEPS + 1)]
    elif kind == ONION:
        # Кольцо у стены: профиль OSMBuildings начинается с 0.8 радиуса,
        # без него между стеной и луковицей остаётся щель до неба.
        profile = [(1.0, 0.0)] + [(share, share_h * rise)
                                  for share, share_h in ONION_PROFILE]
    else:
        return None
    return _lathe_rings(outer, centre, radius, profile, rise)


def _skeleton_surface(points, rise):
    """Вальмовая крыша по прямому скелету bpypolyskel.

    points - контур (n, 2) без дворов в осях тайла. rise - высота крыши
    в единицах тайла. Отдаёт тот же набор, что и roof_surface: (вершины
    (m,2), подъём 0-1, треугольники). None - скелет не вышел, зовущий
    оставляет плоскости. Скелет строит по одной грани на сторону, так
    что контур покрывается целиком и отвесные фронтоны не нужны.
    """
    n = len(points)
    if n < 3 or rise <= 0.0:
        return None
    # Контур должен идти против часовой стрелки, знаком как у _orient.
    if float(_orient(points[np.arange(n) - 1], points,
                     points[(np.arange(n) + 1) % n]).sum()) < 0.0:
        points = points[::-1]
    verts = [Vector((float(points[i, 0]), float(points[i, 1]), 0.0))
             for i in range(n)]
    try:
        faces = polygonize(verts, 0, n, None, float(rise), 0.0, None, None)
    except (AssertionError, AttributeError, ArithmeticError, IndexError,
            KeyError, RecursionError, RuntimeError, StopIteration,
            TypeError, ValueError):
        # Скелет сдаётся на плохом контуре - здание остаётся на плоскостях.
        # Ловится конкретное: порт бросает RuntimeError на кольце ссылок,
        # AssertionError на чужой вершине, ValueError и TypeError из
        # vector.py. Сторожа зацикливания бросают голое Exception
        # ('Endless loop in spike removal' в bpypolyskel.py и 'Endless
        # loop catched in poly2FacesGraph faces()' в poly2FacesGraph.py):
        # их не ловим, это чужой код, см. AGENTS.md.
        return None
    if not faces or len(verts) <= n:
        return None
    for face in faces:
        if len(face) < 3 or len(face) != len(set(face)):
            return None
    total = len(verts)
    coords = np.empty((total, 2), dtype=np.float64)
    fractions = np.empty(total, dtype=np.float64)
    for i, v in enumerate(verts):
        coords[i, 0] = v.x
        coords[i, 1] = v.y
        fractions[i] = min(max(v.z / float(rise), 0.0), 1.0)
    tris = []
    for face in faces:
        poly = coords[face]
        area = float(_orient(np.roll(poly, 1, axis=0), poly,
                             np.roll(poly, -1, axis=0)).sum())
        if area < 0.0:  # грань должна быть против часовой, как у ear_clip
            face = face[::-1]
        for t in ear_clip(coords[face]):
            tris.extend((face[t[0]], face[t[1]], face[t[2]]))
    if not tris:
        return None
    return (coords, fractions, np.asarray(tris, dtype=np.uint32))


def _fans(starts, counts):
    """Треугольники веером у колец с первой точкой starts и counts
    точками, одной операцией NumPy."""
    fans = counts - 2
    total = int(fans.sum())
    if total <= 0:
        return np.zeros(0, dtype=np.uint32)
    first = np.repeat(starts, fans)
    offsets = np.arange(total) - np.repeat(np.cumsum(fans) - fans, fans)
    tri = np.stack([first, first + offsets + 1, first + offsets + 2], axis=1)
    return tri.astype(np.uint32).ravel()


def tile_latlon(key, extent, xy):
    """Точки в единицах тайла key в широту и долготу, (n, 2)."""
    z, x, y = key
    n = 1 << z
    lon = (x + xy[:, 0] / extent) / n * 360.0 - 180.0
    lat = lat_of_row((y + xy[:, 1] / extent) / n)
    return np.stack([lat, lon], axis=1)


def footprints(key, data):
    """Здания тайла key из байтов тайла: Footprint или None без зданий."""
    buildings, extent = decode(data)
    extent = float(extent)
    if not buildings:
        return None
    # Какие кольца выходят за тайл, считается сразу для всех колец.
    every = [ring for b in buildings for ring in b.rings]
    first = np.cumsum([0] + [len(r) for r in every[:-1]])
    flat = np.vstack(every)
    outside = ((np.minimum.reduceat(flat.min(axis=1), first) < 0.0)
               | (np.maximum.reduceat(flat.max(axis=1), first) > extent))
    outside = outside.tolist()
    parts = []  # по зданиям: обрезанные кольца
    kept = []
    position = 0
    for building in buildings:
        rings = []
        flags = outside[position:position + len(building.rings)]
        position += len(building.rings)
        for number, ring in enumerate(building.rings):
            if flags[number]:
                ring = clip(ring, extent)
            if ring is None:
                if number == 0:
                    break
                continue
            rings.append(ring)
        if rings:
            parts.append(rings)
            kept.append(building)
    if not kept:
        return None
    sizes = [len(r) for rings in parts for r in rings]
    starts = np.cumsum([0] + sizes[:-1])
    xy = np.vstack([r for rings in parts for r in rings])
    ring_count = [len(rings) for rings in parts]
    owner_ring = np.repeat(np.arange(len(kept)), ring_count)
    owner = np.repeat(owner_ring, sizes)
    index = np.arange(len(xy))
    ends = np.repeat(starts + np.array(sizes), sizes)
    nxt = np.where(index + 1 < ends, index + 1,
                   np.repeat(starts, sizes)).astype(np.int64)
    prv = np.empty_like(nxt)
    prv[nxt] = index
    # Стена не ставится на ребре по краю тайла.
    q = xy[nxt]
    border = np.zeros(len(xy), dtype=bool)
    for axis in (0, 1):
        for limit in (0.0, extent):
            border |= (xy[:, axis] == limit) & (q[:, axis] == limit)
    # Выпуклые контуры без дворов режутся веером.
    turn = _orient(xy[prv], xy, xy[nxt])
    size = np.hypot(*(xy - xy[prv]).T) * np.hypot(*(xy[nxt] - xy).T)
    concave = np.logical_or.reduceat(turn < -1e-9 * size, starts)
    single = np.array(ring_count) == 1
    ring_of_building = np.cumsum([0] + ring_count[:-1])
    heights = np.array([b.height for b in kept])
    bases = np.array([b.base for b in kept])
    color = np.array([b.color or DEFAULT_COLOR for b in kept], dtype=np.uint8)
    # Метров в единице тайла: контур для ската - в единицах тайла, а
    # высота ската - в метрах.
    _, south, _, north = tile_bounds(*key)
    lat0 = math.radians(0.5 * (float(south) + float(north)))
    scale = 2.0 * math.pi * ellipsoid.A * math.cos(lat0) \
        / (1 << key[0]) / extent
    # Скатные крыши - у выпуклых контуров без дворов и с высотой ската.
    roof_h = np.zeros(len(kept))
    surfaces = []  # (номер здания, (вершины тайла, подъём, треугольники))
    for b in range(len(kept)):
        shape = kept[b].roof.shape
        if shape not in PROFILE_SHAPES + RADIAL_SHAPES or not single[b]:
            continue
        first = int(ring_of_building[b])
        ring = xy[starts[first]:starts[first] + sizes[first]]
        if abs(area(ring)) * scale * scale > MAX_ROOF_AREA:
            continue  # огромный контур: скат на нём читается плитой
        direction = _face(kept[b].roof)
        rise = _roof_rise(kept[b].roof, heights[b], bases[b], ring, scale)
        if rise <= 0.0:
            continue
        surface = None
        if shape in (HIPPED, PYRAMIDAL) and (sizes[first] > 4
                                             or concave[first]):
            # Сложный контур - вальмовая крыша по прямому скелету,
            # прямоугольник остаётся на плоскостях.
            surface = _skeleton_surface(ring, rise / scale)
        if surface is None and shape in RADIAL_SHAPES:
            surface = _radial_surface(ring, rise / scale, shape)
        if surface is None:
            surface = roof_surface(ring, shape, direction, rise / scale,
                                   scale)
        if surface is None:
            continue
        roof_h[b] = rise
        surfaces.append((b, surface))
    shaped = np.zeros(len(kept), dtype=bool)
    for b, _ in surfaces:
        shaped[b] = True
    # Плоские крыши - у прочих зданий.
    flat_mask = ~shaped
    fan = flat_mask & single & ~concave[ring_of_building]
    fan_rings = ring_of_building[fan]
    triangles = [_fans(starts[fan_rings], np.array(sizes)[fan_rings])]
    for b in np.nonzero(flat_mask & ~fan)[0].tolist():
        first = int(ring_of_building[b])
        rings = [list(range(starts[r], starts[r] + sizes[r]))
                 for r in range(first, first + ring_count[b])]
        triangles.append(roof(xy, rings))
    flat_roof = np.concatenate(triangles).astype(np.uint32) if triangles \
        else np.zeros(0, dtype=np.uint32)
    # Точки скатных крыш - в градусах, их подъём 0-1 и треугольники.
    roof_xy = []
    roof_rise = []
    roof_tri = []
    roof_owner = []
    offset = 0
    for b, (verts, rise, tris) in surfaces:
        roof_xy.append(tile_latlon(key, extent, verts))
        roof_rise.append(rise)
        roof_tri.append(tris.astype(np.uint32) + np.uint32(offset))
        roof_owner.append(np.full(len(verts), b, dtype=np.int64))
        offset += len(verts)
    if not roof_xy:
        roof_xy = roof_rise = roof_owner = None
        roof_tri = None
    else:
        roof_xy = np.vstack(roof_xy)
        roof_rise = np.concatenate(roof_rise)
        roof_tri = np.concatenate(roof_tri).astype(np.uint32)
        roof_owner = np.concatenate(roof_owner)
    return Footprint(key, tile_latlon(key, extent, xy), nxt, ~border, owner,
                     heights, bases, color, flat_roof, roof_h, roof_xy,
                     roof_rise, roof_tri, roof_owner)


def _normals(vectors):
    length = np.linalg.norm(vectors, axis=1)
    length[length == 0.0] = 1.0
    unit = vectors / length[:, None]
    out = np.zeros((len(vectors), 4), dtype=np.int8)
    out[:, :3] = np.round(unit * 127.0).astype(np.int8)
    return out


def mesh(footprint, heights_at=None):
    """Сетка зданий по высотам рельефа.

    heights_at - высоты массива точек (широты, долготы), None - земля
    на эллипсоиде. Отметка дома - наивысшая точка рельефа под его
    точками: от низкой на склоне дом уходил под землю. Стена
    поднимается до карниза (height - roof_h), скатная крыша лежит от
    карниза до конька.
    """
    fp = footprint
    lat, lon = fp.latlon[:, 0], fp.latlon[:, 1]
    ground = np.zeros(len(lat)) if heights_at is None \
        else np.asarray(heights_at(lat, lon), dtype=np.float64)
    high = np.full(len(fp.height), -np.inf)
    np.maximum.at(high, fp.owner, ground)
    roof_h = np.zeros(len(fp.height)) if fp.roof_h is None else fp.roof_h
    eave = (high + fp.height - roof_h)[fp.owner]
    top = (high + fp.height)[fp.owner]
    top_ecef = geodetic_to_ecef(lat, lon, top)
    eave_ecef = geodetic_to_ecef(lat, lon, eave)
    bottom = geodetic_to_ecef(lat, lon, (high + fp.base)[fp.owner])
    up = surface_normal(lat, lon)
    i = np.nonzero(fp.wall)[0]
    j = fp.next[i]
    # Кольцо контура идёт против часовой стрелки в координатах тайла,
    # это по часовой, если смотреть сверху. Наружу смотрит up × ребро.
    outward = np.cross(up[i], bottom[j] - bottom[i])
    corners = np.stack([bottom[i], bottom[j], eave_ecef[j], eave_ecef[i]],
                       axis=1)
    count = len(i)
    positions = [corners.reshape(-1, 3), top_ecef]
    normals = [np.repeat(_normals(outward), 4, axis=0), _normals(up)]
    rgb = fp.color[fp.owner]
    colors = [np.repeat(rgb[i], 4, axis=0), rgb]
    # Скатные крыши: по три вершины на треугольник, у каждой своя нормаль.
    if fp.roof_tri is not None and len(fp.roof_tri):
        rlat, rlon = fp.roof_xy[:, 0], fp.roof_xy[:, 1]
        owner = fp.roof_owner
        up_r = surface_normal(rlat, rlon)
        rtop = (high + fp.height - roof_h)[owner] \
            + fp.roof_rise * roof_h[owner]
        r_ecef = geodetic_to_ecef(rlat, rlon, rtop)
        tri = fp.roof_tri.reshape(-1, 3)
        t = r_ecef[tri]
        n = np.cross(t[:, 1] - t[:, 0], t[:, 2] - t[:, 0])
        up_t = up_r[tri].mean(axis=1)
        n = np.where((n * up_t).sum(axis=1)[:, None] < 0.0, -n, n)
        positions.append(t.reshape(-1, 3))
        normals.append(np.repeat(_normals(n), 3, axis=0))
        # Скаты - цветом крыши, торцы (фронтоны, вальмы) - цветом стены,
        # как в OSM Buildings: иначе фронтон выглядит ещё одним скатом.
        length = np.linalg.norm(n, axis=1)
        flat = np.abs((n * up_t).sum(axis=1)) > 0.25 * length
        roof_rgb = np.tile(np.asarray(ROOF_COLOR, dtype=np.uint8),
                           (len(tri), 1))
        wall_rgb = fp.color[owner[tri[:, 0]]]
        rgb = np.where(flat[:, None], roof_rgb, wall_rgb)
        colors.append(np.repeat(rgb, 3, axis=0))
    positions = np.vstack(positions)
    center, offsets = centered(positions)
    vertices = np.zeros(len(positions), dtype=VERTEX)
    vertices["position"] = offsets
    vertices["normal"] = np.vstack(normals)
    vertices["color"][:, :3] = np.vstack(colors)
    vertices["color"][:, 3] = 255
    quad = np.arange(count, dtype=np.uint32)[:, None] * 4
    walls = (quad + np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)).ravel()
    indices = [walls, fp.roof + np.uint32(4 * count)]
    if fp.roof_tri is not None and len(fp.roof_tri):
        shaped_base = 4 * count + len(fp.latlon)
        indices.append(np.arange(len(fp.roof_tri), dtype=np.uint32)
                       + np.uint32(shaped_base))
    indices = np.concatenate(indices).astype(np.uint32)
    return Mesh(fp.key, center, vertices, indices)


def vertex_count(footprint):
    """Вершин в сетке тайла: по 4 на стену, по точке на плоскую крышу
    и по три на треугольник скатной крыши."""
    shaped = 0 if footprint.roof_tri is None else len(footprint.roof_tri)
    return 4 * int(np.count_nonzero(footprint.wall)) \
        + len(footprint.latlon) + shaped


def near_tiles(eye, forward, ground=0.0, reach=RANGE, limit=MAX_TILES):
    """Тайлы зданий уровня LEVEL ближе reach к глазу, ближние первыми.

    eye - глаз в ECEF, forward - единичное направление взгляда, ground -
    высота земли под глазом. Расстояние - от глаза до ближайшей точки
    рамки тайла на высоте ground. Тайл целиком за спиной глаза
    пропускается. Возвращает не больше limit пар (ключ, расстояние).
    """
    eye = np.asarray(eye, dtype=np.float64)
    lat, lon, height = (float(v) for v in ecef_to_geodetic(eye))
    above = height - ground
    if above >= reach:
        return []
    radius = math.sqrt(reach * reach - max(above, 0.0) ** 2)
    dlat = math.degrees(radius / ellipsoid.A)
    dlon = dlat / max(math.cos(math.radians(lat)), 1e-6)
    n = 1 << LEVEL
    x0, y0 = lonlat_to_tile(min(lat + dlat, 85.0), lon - dlon, LEVEL)
    x1, y1 = lonlat_to_tile(max(lat - dlat, -85.0), lon + dlon, LEVEL)
    if x1 < x0:
        x1 += n  # через линию перемены дат
    keys = [(LEVEL, x % n, y) for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)]
    if not keys:
        return []
    bounds = np.array([tile_bounds(*key) for key in keys])
    west, south, east, north = bounds.T
    near_lat = np.clip(lat, south, north)
    shift = (lon - west + 180.0) % 360.0 - 180.0  # долгота от запада
    near_lon = west + np.clip(shift, 0.0, east - west)
    near = geodetic_to_ecef(near_lat, near_lon, ground)
    distance = np.linalg.norm(near - eye, axis=1)
    middle = geodetic_to_ecef(0.5 * (south + north), 0.5 * (west + east),
                              ground)
    corner = geodetic_to_ecef(north, west, ground)
    half = np.linalg.norm(corner - middle, axis=1)
    ahead = (middle - eye) @ np.asarray(forward, dtype=np.float64)
    keep = (distance < reach) & (ahead > -half)
    order = np.argsort(distance[keep], kind="stable")[:limit]
    chosen = np.nonzero(keep)[0][order]
    return [(keys[i], float(distance[i])) for i in chosen.tolist()]


def mesh_ok(mesh):
    """Можно ли отдать сетку видеокарте: треугольники целые, номера
    вершин в пределах массива, координаты конечные.

    Номер за пределами массива вершин драйвер не проверяет, чтение
    за буфером может испортить его память.
    """
    indices = mesh.indices
    if len(indices) % 3:
        return False
    if len(indices) and int(indices.max()) >= len(mesh.vertices):
        return False
    return bool(np.isfinite(mesh.vertices["position"]).all())
