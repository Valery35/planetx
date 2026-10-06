# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Маршрут по дорогам из векторных тайлов OpenFreeMap.

Просьба автора от 6 октября 2026 года - маршруты, как в Google Maps,
без новых сервисов. Дороги - слой transportation схемы OpenMapTiles
в тайлах уровня LEVEL, только там есть грунтовки и тропы. Условия
OpenFreeMap сверены 6 октября 2026 года - запросы без ограничения
количества, коммерческое использование разрешено, подпись
«OpenFreeMap © OpenMapTiles Data from OpenStreetMap» обязательна.

Координаты - целые единицы мировой сетки уровня LEVEL (тайл × EXTENT
+ точка в тайле). У тайлов одного уровня сетка общая, вершины соседних
тайлов совпадают точно, поэтому узел графа - просто одинаковая точка.
Генератор тайлов режет линии по краю тайла с запасом и упрощает их,
часть примыканий остаётся без общей вершины. Конец линии, который лежит
ближе SNAP метров к отрезку другой линии того же уровня (layer, мост
или тоннель), встаёт в этот отрезок новой вершиной. Пересечения отрезков
без общей вершины узлом не считаются - так мост не становится
перекрёстком.

Путь ищет A* по времени в пути. Скорость - по классу дороги, у пешехода
одна. Расчёт - генератор route_steps, окно гоняет его частями
в главном потоке: поток с Python отнимал бы у вида GIL, см. запись
журнала AGENTS «Расчёт в рабочем потоке отнимал у вида GIL».

Модуль Qt не знает.
"""
import heapq
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .places import _fields, _packed, _unpack, _value, _zigzag
except ImportError:  # headless-тесты
    import ellipsoid
    from places import _fields, _packed, _unpack, _value, _zigzag

LEVEL = 14
EXTENT = 4096
WORLD = (1 << LEVEL) * EXTENT  # единиц сетки на окружность мира
SNAP = 3.0  # м, допуск, с которым конец линии встаёт в чужой отрезок
# Клетка решётки поиска концов у чужих отрезков, единиц сетки. Отрезок
# записан во все клетки своей рамки. Новых вершин по длинным отрезкам
# нет: вершина на ровной сетке совпала бы у двух пересекающихся дорог
# и сделала бы из моста перекрёсток.
CELL = 64
# До точки дороги от точки маршрута не дальше, метры.
REACH = 1000.0
# Предел длины маршрута по прямой и коридор тайлов вокруг прямой:
# полуширина - доля длины, но не меньше CORRIDOR_MIN. Без пути коридор
# расширяется вдвое, до WIDEN раз. Тайлов не больше MAX_TILES.
MAX_DISTANCE = 50000.0
CORRIDOR_SHARE = 0.15
CORRIDOR_MIN = 1500.0
WIDEN = 2
MAX_TILES = 600
# Скорости, км/ч. Величины помощника, утверждает автор.
CAR_SPEED = {"motorway": 90.0, "trunk": 80.0, "primary": 60.0,
             "secondary": 50.0, "tertiary": 40.0, "minor": 30.0,
             "service": 15.0, "track": 15.0, "busway": 0.0}
FOOT_SPEED = 5.0
FOOT_NO = {"motorway", "rail", "transit", "ferry", "raceway",
           "bus_guideway"}
MODES = ("car", "foot")
STEP_POPS = 3000  # узлов A* за шаг генератора
# Множитель ключа клетки решётки: больше количества клеток по оси.
CELL_KEY = 1 << 21
# Оценка A* слегка занижена: масштаб Меркатора меняется с широтой.
HEURISTIC = 0.97

Line = namedtuple("Line", "points cls oneway brunnel layer access foot")
Line.__doc__ = """Линия дороги из тайла.

points - вершины (n, 2) int64 в единицах мировой сетки. cls - класс
OpenMapTiles. oneway - 1 по ходу линии, -1 против, 0 в обе стороны.
brunnel - «bridge», «tunnel», «ford» или None. layer - уровень, 0 без
него. access, foot - значения тегов или None.
"""

Route = namedtuple("Route", "points length seconds")
Route.__doc__ = """Маршрут: точки (широта, долгота), длина в метрах по
эллипсоиду, время в пути в секундах."""


# Тайлы и координаты.

def to_grid(lat, lon):
    """Широта и долгота в единицы мировой сетки (float)."""
    lat = max(-85.05112878, min(85.05112878, float(lat)))
    x = (float(lon) + 180.0) / 360.0 * WORLD
    y = (1.0 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2.0 \
        * WORLD
    return x, y


def to_latlon(xy):
    """Единицы сетки (n, 2) в широты и долготы, массивы float64."""
    xy = np.asarray(xy, dtype=np.float64)
    lon = xy[..., 0] / WORLD * 360.0 - 180.0
    lat = np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * xy[..., 1]
                                                  / WORLD))))
    return lat, lon


def unit_metres(lat):
    """Метров в единице сетки на широте lat, вдоль параллели."""
    return 2.0 * math.pi * ellipsoid.A * math.cos(math.radians(lat)) / WORLD


def corridor(a, b, half):
    """Ключи тайлов (LEVEL, x, y), центр которых ближе half метров к
    отрезку от точки a до точки b (широта, долгота), по сетке Меркатора.
    Тайлы, задетые самими точками, входят всегда."""
    ax, ay = to_grid(*a)
    bx, by = to_grid(*b)
    lat = 0.5 * (a[0] + b[0])
    reach = half / unit_metres(lat) + EXTENT
    x0 = int(math.floor((min(ax, bx) - reach) / EXTENT))
    x1 = int(math.floor((max(ax, bx) + reach) / EXTENT))
    y0 = int(math.floor((min(ay, by) - reach) / EXTENT))
    y1 = int(math.floor((max(ay, by) + reach) / EXTENT))
    xs, ys = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
    cx = (xs.ravel() + 0.5) * EXTENT
    cy = (ys.ravel() + 0.5) * EXTENT
    d = _point_segment(np.stack([cx, cy], axis=1),
                       np.array([ax, ay]), np.array([bx, by]))
    keep = d <= half / unit_metres(lat) + EXTENT * 0.75
    n = 1 << LEVEL
    keys = {(LEVEL, int(x) % n, int(y)) for x, y in
            zip(xs.ravel()[keep], ys.ravel()[keep]) if 0 <= y < n}
    for x, y in ((ax, ay), (bx, by)):
        keys.add((LEVEL, int(x // EXTENT) % n, int(y // EXTENT)))
    return sorted(keys)


def _point_segment(p, a, b):
    """Расстояния от точек p (n, 2) до отрезка a-b."""
    ab = b - a
    t = np.clip(((p - a) @ ab) / max(float(ab @ ab), 1e-12), 0.0, 1.0)
    return np.hypot(*(p - a - t[:, None] * ab).T)


def decode(key, data):
    """Линии дорог тайла key: список Line. Тайл другого уровня
    или с другим extent пересчитывается в сетку уровня LEVEL."""
    z, tx, ty = key
    out = []
    for number, wire, layer in _fields(_unpack(data)):
        if number != 3 or wire != 2:
            continue
        fields = list(_fields(layer))
        title = next((bytes(v).decode("utf-8", errors="replace")
                      for n, w, v in fields if n == 1 and w == 2), None)
        if title != "transportation":
            continue
        keys = [bytes(v).decode("utf-8", errors="replace")
                for n, w, v in fields if n == 3 and w == 2]
        raw = [v for n, w, v in fields if n == 4 and w == 2]
        extent = next((v for n, w, v in fields if n == 5 and w == 0),
                      EXTENT)
        scale = EXTENT * (1 << (LEVEL - z)) / extent
        for n, w, feature in fields:
            if n != 2 or w != 2:
                continue
            tags, geometry, kind = [], [], 0
            for fn, fw, fv in _fields(feature):
                if fn == 2 and fw == 2:
                    tags = _packed(fv)
                elif fn == 3 and fw == 0:
                    kind = fv
                elif fn == 4 and fw == 2:
                    geometry = _packed(fv)
            if kind != 2:
                continue
            attrs = {}
            for k, v in zip(tags[0::2], tags[1::2]):
                if k < len(keys) and v < len(raw):
                    attrs[keys[k]] = _value(raw[v])
            oneway = attrs.get("oneway") or 0
            for part in _parts(geometry):
                points = np.rint((np.asarray(part, dtype=np.float64)
                                  + (tx * extent, ty * extent)) * scale)
                out.append(Line(points.astype(np.int64),
                                attrs.get("class"),
                                int(oneway) if oneway in (1, -1) else 0,
                                attrs.get("brunnel"),
                                int(attrs.get("layer") or 0),
                                attrs.get("access"), attrs.get("foot")))
    return out


def _parts(geometry):
    """Части линии MVT: списки точек в единицах тайла."""
    out, part = [], None
    x = y = 0
    i = 0
    n = len(geometry)
    while i < n:
        command = geometry[i]
        i += 1
        kind, count = command & 7, command >> 3
        if kind not in (1, 2):
            break
        for _ in range(count):
            if i + 1 >= n:
                break
            x += _zigzag(geometry[i])
            y += _zigzag(geometry[i + 1])
            i += 2
            if kind == 1:
                if part is not None and len(part) > 1:
                    out.append(part)
                part = [(x, y)]
            elif part is not None:
                part.append((x, y))
    if part is not None and len(part) > 1:
        out.append(part)
    return out


# Граф.

def speed(line, mode):
    """Скорость по линии, м/с, 0 - по линии нельзя."""
    cls = line.cls or ""
    if cls.endswith("_construction"):
        return 0.0
    if mode == "foot":
        if cls in FOOT_NO or line.foot == "no":
            return 0.0
        return FOOT_SPEED / 3.6
    if line.access == "no":
        return 0.0
    return CAR_SPEED.get(cls, 0.0) / 3.6


Graph = namedtuple("Graph", "nodes start target weight length seg_a seg_b "
                   "seg_cost seg_back seg_len")
Graph.__doc__ = """Граф дорог.

nodes - узлы (N, 2) float64 в единицах сетки. start, target, weight,
length - дуги со временем в секундах и длиной в метрах, сортированы по
start. seg_* - отрезки для привязки точек маршрута: концы (номера
узлов), время вперёд и назад (inf - нельзя) и длина.
"""


def build_steps(lines, mode):
    """Граф из линий: генератор, последнее значение - Graph или None,
    если дорог для mode нет. Промежуточные значения - None, шаг расчёта
    для цикла событий."""
    usable = [(ln, s) for ln in lines for s in (speed(ln, mode),) if s > 0]
    if not usable:
        yield None
        return
    # Отрезки: концы, скорость, направление, мост, уровень, линия.
    starts, ends, speeds, ways, bridge, levels, owner = \
        [], [], [], [], [], [], []
    for number, (ln, s) in enumerate(usable):
        pts = ln.points
        k = len(pts) - 1
        starts.append(pts[:-1])
        ends.append(pts[1:])
        speeds.append(np.full(k, s))
        ways.append(np.full(k, ln.oneway if mode == "car" else 0))
        bridge.append(np.full(k, _brunnel_code(ln.brunnel)))
        levels.append(np.full(k, ln.layer))
        owner.append(np.full(k, number))
    a = np.concatenate(starts)
    b = np.concatenate(ends)
    s = np.concatenate(speeds)
    way = np.concatenate(ways)
    brunnel = np.concatenate(bridge)
    level = np.concatenate(levels)
    line = np.concatenate(owner)
    keep = np.any(a != b, axis=1)
    a, b, s, way, brunnel, level, line = (v[keep] for v in (
        a, b, s, way, brunnel, level, line))
    yield None
    a, b, s, way, brunnel, level, line = _snap(a, b, s, way, brunnel,
                                               level, line)
    yield None
    points = np.concatenate([a, b])
    nodes, inverse = np.unique(points, axis=0, return_inverse=True)
    inverse = inverse.ravel()
    u, v = inverse[:len(a)], inverse[len(a):]
    lat, lon = to_latlon(nodes)
    length = _metres(lat[u], lon[u], lat[v], lon[v])
    cost = length / s
    forward = way >= 0
    backward = way <= 0
    start = np.concatenate([u[forward], v[backward]])
    target = np.concatenate([v[forward], u[backward]])
    weight = np.concatenate([cost[forward], cost[backward]])
    dist = np.concatenate([length[forward], length[backward]])
    order = np.argsort(start, kind="stable")
    yield Graph(nodes.astype(np.float64), start[order], target[order],
                weight[order], dist[order], u, v,
                np.where(forward, cost, np.inf),
                np.where(backward, cost, np.inf), length)


def _brunnel_code(value):
    return {"bridge": 1, "tunnel": 2}.get(value, 0)


def _snap(a, b, s, way, brunnel, level, line):
    """Концы линий, лежащие у чужого отрезка ближе SNAP, - в этот отрезок
    вершиной, отрезок делится в этой точке. Конец у вершины чужого
    отрезка переносится в эту вершину."""
    lat, _ = to_latlon(a[:1].astype(np.float64))
    tol = SNAP / unit_metres(float(lat[0]))
    # Свободные концы - точки, которые встречаются в отрезках один раз.
    points = np.concatenate([a, b])
    unique, inverse, counts = np.unique(points, axis=0, return_inverse=True,
                                        return_counts=True)
    inverse = inverse.ravel()
    loose = counts[inverse] == 1
    seg_of = np.concatenate([np.arange(len(a)), np.arange(len(a))])
    ends = points[loose]
    end_seg = seg_of[loose]
    if not len(ends):
        return a, b, s, way, brunnel, level, line
    # Решётка клеток CELL: отрезок записан во все клетки рамки с допуском.
    lo = np.floor((np.minimum(a, b) - tol) / CELL).astype(np.int64)
    hi = np.floor((np.maximum(a, b) + tol) / CELL).astype(np.int64)
    span = hi - lo + 1
    cells_per = span[:, 0] * span[:, 1]
    seg = np.repeat(np.arange(len(a)), cells_per)
    first = np.repeat(np.cumsum(cells_per) - cells_per, cells_per)
    k = np.arange(len(seg)) - first
    cx = lo[seg, 0] + k % span[seg, 0]
    cy = lo[seg, 1] + k // span[seg, 0]
    cell = cx * CELL_KEY + cy
    order = np.argsort(cell, kind="stable")
    cell, seg = cell[order], seg[order]
    ecell = (np.floor(ends[:, 0] / CELL).astype(np.int64) * CELL_KEY
             + np.floor(ends[:, 1] / CELL).astype(np.int64))
    left = np.searchsorted(cell, ecell, "left")
    right = np.searchsorted(cell, ecell, "right")
    many = right - left
    end_i = np.repeat(np.arange(len(ends)), many)
    first = np.repeat(np.cumsum(many) - many, many)
    cand = seg[left[end_i] + np.arange(len(end_i)) - first]
    own = end_seg[end_i]
    p = ends[end_i].astype(np.float64)
    pa = a[cand].astype(np.float64)
    pb = b[cand].astype(np.float64)
    d = pb - pa
    t = np.einsum("ij,ij->i", p - pa, d) / np.maximum(
        np.einsum("ij,ij->i", d, d), 1e-12)
    t = np.clip(t, 0.0, 1.0)
    dist = np.hypot(*(p - pa - t[:, None] * d).T)
    same = (brunnel[cand] == brunnel[own]) & (level[cand] == level[own])
    ok = (dist <= tol) & same & (line[cand] != line[own])
    if not ok.any():
        return a, b, s, way, brunnel, level, line
    end_i, cand, t, dist = end_i[ok], cand[ok], t[ok], dist[ok]
    # Конец - в ближайший отрезок.
    order = np.lexsort((dist, end_i))
    end_i, cand, t = end_i[order], cand[order], t[order]
    first = np.r_[True, end_i[1:] != end_i[:-1]]
    end_i, cand, t = end_i[first], cand[first], t[first]
    # Ближайшая точка - вершина отрезка: конец переносится в неё.
    at_vertex = (t <= 0.0) | (t >= 1.0)
    a, b = a.copy(), b.copy()
    for i, j, tt in zip(end_i[at_vertex], cand[at_vertex], t[at_vertex]):
        q = a[j] if tt <= 0.0 else b[j]
        k = end_seg[i]
        if (a[k] == ends[i]).all():
            a[k] = q
        else:
            b[k] = q
    end_i, cand, t = end_i[~at_vertex], cand[~at_vertex], t[~at_vertex]
    if not len(cand):
        return _proper(a, b, s, way, brunnel, level, line)
    # Деление отрезков: точки по порядку вдоль отрезка.
    order = np.lexsort((t, cand))
    cand, end_i = cand[order], end_i[order]
    split = np.zeros(len(a), dtype=bool)
    split[cand] = True
    new_a, new_b, keep_attr = [], [], []
    bounds = np.r_[0, np.flatnonzero(cand[1:] != cand[:-1]) + 1, len(cand)]
    for i0, i1 in zip(bounds[:-1], bounds[1:]):
        j = cand[i0]
        chain = np.concatenate([a[j:j + 1], ends[end_i[i0:i1]],
                                b[j:j + 1]])
        new_a.append(chain[:-1])
        new_b.append(chain[1:])
        keep_attr.append(np.full(len(chain) - 1, j))
    if new_a:
        extra = np.concatenate(keep_attr)
        whole = ~split
        a = np.concatenate([a[whole]] + new_a)
        b = np.concatenate([b[whole]] + new_b)
        s, way, brunnel, level, line = (np.concatenate([v[whole], v[extra]])
                                        for v in (s, way, brunnel, level,
                                                  line))
    return _proper(a, b, s, way, brunnel, level, line)


def _proper(a, b, *rest):
    """Отрезки без нулевой длины."""
    keep = np.any(a != b, axis=1)
    return (a[keep], b[keep]) + tuple(v[keep] for v in rest)


def _metres(lat1, lon1, lat2, lon2):
    """Длина по большому кругу шара среднего радиуса, метры. На отрезках
    дорог в десятки метров отличие от эллипсоида - доли процента."""
    radius = (2.0 * ellipsoid.A + ellipsoid.B) / 3.0
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dl = np.radians(lon2 - lon1)
    h = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) \
        * np.sin(dl / 2) ** 2
    return 2.0 * radius * np.arcsin(np.sqrt(np.clip(h, 0.0, 1.0)))


# Поиск пути.

def attach(graph, lat, lon):
    """Ближайшая точка дороги графа к точке (lat, lon): номер отрезка,
    доля вдоль него, расстояние в метрах. None - дальше REACH."""
    if graph is None or not len(graph.seg_a):
        return None
    p = np.array(to_grid(lat, lon))
    pa = graph.nodes[graph.seg_a]
    pb = graph.nodes[graph.seg_b]
    d = pb - pa
    t = np.clip(np.einsum("ij,ij->i", p - pa, d)
                / np.maximum(np.einsum("ij,ij->i", d, d), 1e-12), 0.0, 1.0)
    dist = np.hypot(*(p - pa - t[:, None] * d).T) * unit_metres(lat)
    i = int(np.argmin(dist))
    if dist[i] > REACH:
        return None
    return i, float(t[i]), float(dist[i])


def route_steps(graph, a, b, mode="car"):
    """Путь от точки a до точки b (широта, долгота): генератор, шаги -
    None, последнее значение - Route или None, если пути нет."""
    start = attach(graph, *a)
    end = attach(graph, *b)
    if start is None or end is None:
        yield None
        return
    n = len(graph.nodes)
    source, sink = n, n + 1
    # Дуги от точки старта к концам её отрезка и от концов отрезка
    # финиша к точке финиша, по доле пути вдоль отрезка.
    extra = {}
    si, st, _ = start
    ei, et, _ = end
    sa, sb = int(graph.seg_a[si]), int(graph.seg_b[si])
    ea, eb = int(graph.seg_a[ei]), int(graph.seg_b[ei])
    forward, back = graph.seg_cost[si], graph.seg_back[si]
    slen = graph.seg_len[si]
    extra.setdefault(source, []).extend([
        (sb, (1.0 - st) * forward, (1.0 - st) * slen),
        (sa, st * back, st * slen)])
    forward, back = graph.seg_cost[ei], graph.seg_back[ei]
    elen = graph.seg_len[ei]
    extra.setdefault(ea, []).append((sink, et * forward, et * elen))
    extra.setdefault(eb, []).append((sink, (1.0 - et) * back,
                                     (1.0 - et) * elen))
    if si == ei:
        # Обе точки на одном отрезке: прямо по нему, если можно.
        cost = (et - st) * graph.seg_cost[si] if et >= st \
            else (st - et) * graph.seg_back[si]
        extra[source].append((sink, cost, abs(et - st) * slen))
    # Оценка A*: прямая до финиша на наибольшей скорости.
    top = (max(CAR_SPEED.values()) if mode == "car" else FOOT_SPEED) / 3.6
    goal = np.array(to_grid(*b))
    per_unit = unit_metres(0.5 * (a[0] + b[0]))
    first = np.searchsorted(graph.start, np.arange(n + 1))
    best = {source: 0.0}
    came = {}
    heap = [(0.0, 0.0, source)]
    done = set()
    pops = 0
    while heap:
        _, cost, node = heapq.heappop(heap)
        if node in done:
            continue
        done.add(node)
        if node == sink:
            break
        pops += 1
        if pops % STEP_POPS == 0:
            yield None
        arcs = list(extra.get(node, ()))
        if node < n:
            lo, hi = first[node], first[node + 1]
            arcs += zip(graph.target[lo:hi].tolist(),
                        graph.weight[lo:hi].tolist(),
                        graph.length[lo:hi].tolist())
        for nxt, w, _ in arcs:
            if not math.isfinite(w):
                continue
            total = cost + w
            if total < best.get(nxt, math.inf):
                best[nxt] = total
                came[nxt] = node
                if nxt < n:
                    gap = math.hypot(*(graph.nodes[nxt] - goal)) * per_unit
                else:
                    gap = 0.0
                heapq.heappush(heap, (total + HEURISTIC * gap / top,
                                          total, nxt))
    if sink not in done:
        yield None
        return
    chain = [sink]
    while chain[-1] != source:
        chain.append(came[chain[-1]])
    chain.reverse()
    xy = [np.array(to_grid(*a))]
    xy.append(graph.nodes[sa] + st * (graph.nodes[sb] - graph.nodes[sa]))
    xy += [graph.nodes[i] for i in chain[1:-1]]
    xy.append(graph.nodes[ea] + et * (graph.nodes[eb] - graph.nodes[ea]))
    xy.append(np.array(to_grid(*b)))
    lat, lon = to_latlon(np.array(xy))
    points = _clean(list(zip(lat.tolist(), lon.tolist())))
    # Подходы от точек к дороге не входят в время, входят в длину.
    lats = np.array([p[0] for p in points])
    lons = np.array([p[1] for p in points])
    length = float(_metres(lats[:-1], lons[:-1], lats[1:], lons[1:]).sum())
    yield Route(points, length, float(best[sink]))


def _clean(points):
    """Точки без повторов подряд."""
    out = []
    for p in points:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 \
                or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    return out


def run(steps):
    """Прогнать генератор до конца, вернуть последнее значение."""
    result = None
    for result in steps:
        pass
    return result
