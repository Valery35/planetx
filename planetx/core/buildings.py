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
Низ здания стоит на наименьшей высоте рельефа под его контуром
в этом тайле, крыша плоская. У здания на стыке тайлов на склоне
половины могут разойтись по высоте на перепад рельефа.

Крыши режутся на треугольники в координатах тайла. Выпуклый контур
без дворов - веером, одной операцией NumPy для всех таких зданий.
Прочие - отсечением ушей, двор соединяется с контуром мостом.
Отсечение ушей из core.features шло 130-360 мс на тайл уровня 14,
29 сентября 2026 года.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import (A, ecef_to_geodetic, geodetic_to_ecef,
                            surface_normal)
    from .features import centered
    from .places import (EXTENT, _fields, _packed, _unpack, _value,
                         _zigzag)
    from .tiling import lat_of_row, lonlat_to_tile, tile_bounds
except ImportError:  # headless-тесты
    from ellipsoid import (A, ecef_to_geodetic, geodetic_to_ecef,
                           surface_normal)
    from features import centered
    from places import EXTENT, _fields, _packed, _unpack, _value, _zigzag
    from tiling import lat_of_row, lonlat_to_tile, tile_bounds

LAYER = "building"
LEVEL = 14
# Цвет здания без поля colour. Величину назначил помощник 29 сентября
# 2026 года, её утверждает автор.
DEFAULT_COLOR = (226, 222, 214)
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

Building = namedtuple("Building", "rings height base color")
Building.__doc__ = """Здание из тайла.

rings - кольца в единицах тайла, массивы (n, 2) без повтора первой
точки. Первое - контур с положительной площадью, дальше дворы
с отрицательной. height - высота крыши над землёй, base - высота
низа, метры. color - RGB 0-255 или None.
"""

Footprint = namedtuple("Footprint",
                       "key latlon next wall owner height base color roof")
Footprint.__doc__ = """Здания тайла без высот рельефа.

latlon - все точки колец (N, 2) в градусах. next - номер следующей
точки кольца. wall - ставится ли стена на ребре от точки к следующей.
owner - номер здания точки. height, base - по зданиям, метры. color -
по зданиям (B, 3) uint8. roof - треугольники крыш, номера точек uint32.
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
        if attrs.get("hide_3d"):
            continue
        height = float(attrs.get("render_height") or 0.0)
        base = float(attrs.get("render_min_height") or 0.0)
        if height <= base:
            continue
        color = parse_color(attrs.get("colour"))
        rings = []
        for ring, s in _rings(geometry):
            if s > 0.0:
                if rings:
                    out.append(Building(rings, height, base, color))
                rings = [ring]
            elif s < 0.0 and rings:
                rings.append(ring)
        if rings:
            out.append(Building(rings, height, base, color))
    return out


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
    fan = single & ~concave[ring_of_building]
    fan_rings = ring_of_building[fan]
    triangles = [_fans(starts[fan_rings], np.array(sizes)[fan_rings])]
    for b in np.nonzero(~fan)[0].tolist():
        first = int(ring_of_building[b])
        rings = [list(range(starts[r], starts[r] + sizes[r]))
                 for r in range(first, first + ring_count[b])]
        triangles.append(roof(xy, rings))
    color = np.array([b.color or DEFAULT_COLOR for b in kept],
                     dtype=np.uint8)
    return Footprint(key, tile_latlon(key, extent, xy), nxt, ~border, owner,
                     np.array([b.height for b in kept]),
                     np.array([b.base for b in kept]), color,
                     np.concatenate(triangles).astype(np.uint32))


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
    на эллипсоиде. Низ здания - наименьшая высота под его точками.
    """
    fp = footprint
    lat, lon = fp.latlon[:, 0], fp.latlon[:, 1]
    if heights_at is None:
        ground = np.zeros(len(lat))
    else:
        ground = np.asarray(heights_at(lat, lon), dtype=np.float64)
    low = np.full(len(fp.height), np.inf)
    np.minimum.at(low, fp.owner, ground)
    top = geodetic_to_ecef(lat, lon, (low + fp.height)[fp.owner])
    bottom = geodetic_to_ecef(lat, lon, (low + fp.base)[fp.owner])
    up = surface_normal(lat, lon)
    i = np.nonzero(fp.wall)[0]
    j = fp.next[i]
    # Кольцо контура идёт против часовой стрелки в координатах тайла,
    # это по часовой, если смотреть сверху. Наружу смотрит up × ребро.
    outward = np.cross(up[i], bottom[j] - bottom[i])
    corners = np.stack([bottom[i], bottom[j], top[j], top[i]], axis=1)
    positions = np.vstack([corners.reshape(-1, 3), top])
    center, offsets = centered(positions)
    count = len(i)
    vertices = np.zeros(len(positions), dtype=VERTEX)
    vertices["position"] = offsets
    vertices["normal"][:4 * count] = np.repeat(_normals(outward), 4, axis=0)
    vertices["normal"][4 * count:] = _normals(up)
    rgb = fp.color[fp.owner]
    vertices["color"][:4 * count, :3] = np.repeat(rgb[i], 4, axis=0)
    vertices["color"][4 * count:, :3] = rgb
    vertices["color"][:, 3] = 255
    quad = np.arange(count, dtype=np.uint32)[:, None] * 4
    walls = (quad + np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32)).ravel()
    indices = np.concatenate([walls, fp.roof + np.uint32(4 * count)])
    return Mesh(fp.key, center, vertices, indices.astype(np.uint32))


def vertex_count(footprint):
    """Вершин в сетке тайла: по 4 на стену и по одной на точку крыши."""
    return 4 * int(np.count_nonzero(footprint.wall)) + len(footprint.latlon)


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
    dlat = math.degrees(radius / A)
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


Prepared = namedtuple("Prepared", "center a e1 e2")
Prepared.__doc__ = """Треугольники сетки для проверки луча: первая
вершина и два ребра, float64, смещения от center."""


def prepare(mesh):
    """Треугольники сетки для ray_hit_prepared. Выборка вершин по номерам
    - три четверти времени проверки, поэтому её держат готовой."""
    tri = mesh.indices.reshape(-1, 3)
    p = mesh.vertices["position"].astype(np.float64)
    a = p[tri[:, 0]]
    return Prepared(np.asarray(mesh.center, dtype=np.float64), a,
                    p[tri[:, 1]] - a, p[tri[:, 2]] - a)


def ray_hit(meshes, origin, direction):
    """Ближайшее попадание луча в здания: (расстояние, точка) или None.

    meshes - сетки Mesh, origin - начало луча в ECEF, direction -
    направление, длина любая. Расстояние - в метрах вдоль луча. Проверка
    идёт по тем же треугольникам, что рисует видеокарта, в float64
    от центра тайла, методом Мёллера-Трумбора. Треугольник попадает
    с обеих сторон, стены видны и изнутри двора.
    """
    return ray_hit_prepared([prepare(m) for m in meshes
                             if len(m.indices)], origin, direction)


def ray_hit_prepared(prepared, origin, direction):
    """То же, что ray_hit, по готовым треугольникам prepare."""
    origin = np.asarray(origin, dtype=np.float64)
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    best = None
    for item in prepared:
        a, e1, e2 = item.a, item.e1, item.e2
        if not len(a):
            continue
        o = origin - item.center
        h = np.cross(d, e2)
        det = np.einsum("ij,ij->i", e1, h)
        # Ребро треугольника - метры, порог отбрасывает луч в плоскости
        # треугольника.
        ok = np.abs(det) > 1e-9 * np.einsum("ij,ij->i", e1, e1)
        inv = np.where(ok, 1.0 / np.where(ok, det, 1.0), 0.0)
        s = o - a
        u = np.einsum("ij,ij->i", s, h) * inv
        q = np.cross(s, e1)
        v = (q @ d) * inv
        t = np.einsum("ij,ij->i", e2, q) * inv
        inside = ok & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > 0.0)
        if not inside.any():
            continue
        near = float(t[inside].min())
        if best is None or near < best:
            best = near
    if best is None:
        return None
    return best, origin + best * d
