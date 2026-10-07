# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подземный режим: сетки стволов, горизонтов и разрезов. Без Qt.

Подшаг 4.2 плана фазы 3 (doc/PLAN_PHASE3.md). Всё подземное -
треугольники с нормалью и цветом в вершине, тот же формат вершины,
что у 3D-зданий (core/buildings.VERTEX). Точки приходят широтой,
долготой и высотой на экране: настоящая отметка, умноженная на
масштаб рельефа (решение автора от 2 октября 2026 года - масштаб
общий с рельефом). Центр сетки - в ECEF в double, вершины - смещения
от него в float32, как у тайлов.

- tube - трубка вдоль ломаной ствола, сечение SIDES-угольник.
- grid_surface - сетка горизонта по узлам растра, ячейка с пустым
  углом пропускается.
- wall - вертикальная стенка между верхней и нижней линией, стенка
  разреза между двумя поверхностями.
- inside - точки внутри многоугольника выреза.
"""
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .buildings import VERTEX
    from .ellipsoid import geodetic_to_ecef, surface_normal
except ImportError:  # headless-тесты
    import ellipsoid
    from buildings import VERTEX
    from ellipsoid import geodetic_to_ecef, surface_normal

SIDES = 8  # граней трубки ствола
BLOCK_FADE = 0.45  # насколько темнее стенка блока у низа, выбор помощника

Part = namedtuple("Part", "positions normals colors indices")
Part.__doc__ = """Кусок сетки в ECEF: positions (n, 3) float64, normals
(n, 3), colors (n, 4) uint8, indices (m, 3) - треугольники."""

Mesh = namedtuple("Mesh", "key center vertices indices")
Mesh.__doc__ = """Сетка для видеокарты, как core.buildings.Mesh."""


def ecef(lats, lons, alts):
    """Точки в ECEF (n, 3) по широтам, долготам и высотам."""
    xyz = geodetic_to_ecef(np.asarray(lats, dtype=np.float64),
                           np.asarray(lons, dtype=np.float64),
                           np.asarray(alts, dtype=np.float64))
    return np.stack(xyz, axis=-1) if isinstance(xyz, tuple) else xyz


def _unit(v):
    norm = np.linalg.norm(v, axis=-1, keepdims=True)
    return v / np.where(norm > 0.0, norm, 1.0)


def _rgba(color, count):
    color = tuple(color) + (255,) * (4 - len(color))
    return np.tile(np.array(color, dtype=np.uint8), (count, 1))


def tube(points, radius, color, sides=SIDES):
    """Трубка радиуса radius вдоль ломаной points (n, 3) ECEF.

    Сечение переносится вдоль ломаной без поворота (параллельный
    перенос), так грани не перекручиваются на изгибах ствола."""
    points = np.asarray(points, dtype=np.float64)
    n = len(points)
    if n < 2:
        return None
    tangents = np.empty_like(points)
    tangents[1:-1] = points[2:] - points[:-2]
    tangents[0] = points[1] - points[0]
    tangents[-1] = points[-1] - points[-2]
    tangents = _unit(tangents)
    # Начальная ось сечения - перпендикуляр к касательной.
    up = surface_normal(*_latlon(points[0]))
    axis = np.cross(tangents[0], up)
    if np.linalg.norm(axis) < 1e-6:
        axis = np.cross(tangents[0], [1.0, 0.0, 0.0])
    axis = axis / np.linalg.norm(axis)
    angles = np.arange(sides) * 2.0 * np.pi / sides
    positions = np.empty((n, sides, 3))
    normals = np.empty((n, sides, 3))
    for i in range(n):
        t = tangents[i]
        axis = axis - np.dot(axis, t) * t
        axis = axis / max(np.linalg.norm(axis), 1e-12)
        other = np.cross(t, axis)
        ring = (np.cos(angles)[:, None] * axis
                + np.sin(angles)[:, None] * other)
        normals[i] = ring
        positions[i] = points[i] + radius * ring
    a = np.arange(n - 1)[:, None] * sides
    k = np.arange(sides)[None, :]
    k1 = (k + 1) % sides
    quads = np.stack([a + k, a + k1, a + sides + k,
                      a + k1, a + sides + k1, a + sides + k], axis=-1)
    indices = quads.reshape(-1, 3)
    return Part(positions.reshape(-1, 3), normals.reshape(-1, 3),
                _rgba(color, n * sides), indices.astype(np.uint32))


def _latlon(point):
    """Широта и долгота точки ECEF по направлению из центра - для оси
    сечения трубки этого хватает."""
    x, y, z = point
    return (np.degrees(np.arctan2(z, np.hypot(x, y))),
            np.degrees(np.arctan2(y, x)))


def grid_triangles(valid):
    """Треугольники сетки узлов (rows, cols) по признаку valid: (k, 3)
    номеров узлов. Ячейка с четырьмя узлами - два треугольника, с тремя -
    один, так край растра идёт косой линией, а не ступенями."""
    rows, cols = valid.shape
    idx = np.arange(rows * cols).reshape(rows, cols)
    a, b = idx[:-1, :-1], idx[:-1, 1:]
    c, d = idx[1:, :-1], idx[1:, 1:]
    va, vb = valid[:-1, :-1], valid[:-1, 1:]
    vc, vd = valid[1:, :-1], valid[1:, 1:]
    full = va & vb & vc & vd
    count = va.astype(int) + vb + vc + vd
    three = count == 3
    pieces = [np.stack([a, b, c], -1)[full],
              np.stack([b, d, c], -1)[full],
              np.stack([a, b, c], -1)[three & ~vd],
              np.stack([b, d, c], -1)[three & ~va],
              np.stack([a, d, c], -1)[three & ~vb],
              np.stack([a, b, d], -1)[three & ~vc]]
    return np.concatenate(pieces).reshape(-1, 3)


def boundary_edges(valid):
    """Край треугольников сетки valid (grid_triangles): рёбра, которые
    принадлежат одному треугольнику, (m, 2) номеров узлов по росту."""
    tris = grid_triangles(valid)
    if not len(tris):
        return np.zeros((0, 2), dtype=np.int64)
    edges = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]],
                            tris[:, [2, 0]]]).astype(np.int64)
    # Направление ребра - обход треугольника, у всех треугольников
    # один, поэтому нормали стенок смотрят в одну сторону от данных.
    keys = np.sort(edges, axis=1)
    _, first, counts = np.unique(keys, axis=0, return_index=True,
                                 return_counts=True)
    return edges[np.sort(first[counts == 1])]


def grid_walls(top, bottom, valid, color, skip=None):
    """Боковые стенки пласта между поверхностями top и bottom (rows,
    cols, 3) ECEF на одной сетке узлов: по краю треугольников valid.
    Так пласт выглядит плитой с торцами по краю данных и по краю
    выреза. skip - рёбра (m, 2) без стенки: там стоит стенка блока."""
    edges = boundary_edges(valid)
    if skip is not None and len(skip) and len(edges):
        size = valid.size
        a, s = np.sort(edges, axis=1), np.sort(skip, axis=1)
        edges = edges[~np.isin(a[:, 0] * size + a[:, 1],
                               s[:, 0] * size + s[:, 1])]
    if not len(edges):
        return None
    return _edge_quads(top, bottom, edges, color)


def block_walls(surfaces, valid, colors):
    """Стенки блока по краю сетки valid: между поверхностями surfaces
    (k, rows, cols, 3) ECEF сверху вниз - пласты цветов colors (k - 1).
    Край блока закрывает вид сквозь прозрачную землю мимо гридов.
    Цвет темнеет с глубиной до доли 1 - BLOCK_FADE у низа блока."""
    edges = boundary_edges(valid)
    if not len(edges):
        return []
    flat = [s.reshape(-1, 3) for s in surfaces]
    depth = [np.linalg.norm(s - flat[0], axis=1) for s in flat]
    deepest = max(float(depth[-1].max()), 1e-6)
    shades = [1.0 - BLOCK_FADE * d / deepest for d in depth]
    return [_edge_quads(top, bottom, edges, color, (s0, s1))
            for top, bottom, color, s0, s1 in zip(
                surfaces[:-1], surfaces[1:], colors, shades[:-1],
                shades[1:])]


def _edge_quads(top, bottom, edges, color, shade=None):
    """Четырёхугольники между top и bottom по рёбрам edges. shade -
    множители цвета узлов верха и низа или None."""
    top = top.reshape(-1, 3)
    bottom = bottom.reshape(-1, 3)
    p0, p1 = top[edges[:, 0]], top[edges[:, 1]]
    q0, q1 = bottom[edges[:, 0]], bottom[edges[:, 1]]
    side = _unit(np.cross(p1 - p0, _unit(p0)))
    n = len(edges)
    positions = np.concatenate([p0, p1, q0, q1])
    normals = np.concatenate([side] * 4)
    i = np.arange(n)
    tris = np.concatenate([np.stack([i, n + i, 2 * n + i], -1),
                           np.stack([n + i, 3 * n + i, 2 * n + i], -1)])
    colors = _rgba(color, 4 * n)
    if shade is not None:
        a, b = edges[:, 0], edges[:, 1]
        k = np.concatenate([shade[0][a], shade[0][b], shade[1][a],
                            shade[1][b]])
        colors[:, :3] = (colors[:, :3] * k[:, None]).astype(np.uint8)
    return Part(positions, normals, colors, tris.astype(np.uint32))


def grid_surface(points, valid, colors):
    """Сетка поверхности по узлам points (rows, cols, 3) ECEF.

    valid (rows, cols) - есть ли значение в узле, colors (rows, cols, 4)
    или один цвет. Ячейка с пустым углом пропускается."""
    rows, cols = valid.shape
    if rows < 2 or cols < 2:
        return None
    flat = points.reshape(-1, 3)
    # Нормали по разностям соседей, наружу от центра Земли.
    d_row = np.gradient(points, axis=0)
    d_col = np.gradient(points, axis=1)
    normals = _unit(np.cross(d_col, d_row)).reshape(-1, 3)
    outward = np.einsum("ij,ij->i", normals, flat) < 0.0
    normals[outward] *= -1.0
    tris = grid_triangles(valid)
    if not len(tris):
        return None
    colors = np.asarray(colors, dtype=np.uint8)
    if colors.ndim == 1:
        colors = _rgba(colors, rows * cols)
    else:
        colors = colors.reshape(-1, colors.shape[-1])
        if colors.shape[1] == 3:
            colors = np.hstack([colors, np.full((len(colors), 1), 255,
                                                np.uint8)])
    return Part(flat, normals, colors, tris.astype(np.uint32))


def wall(lats, lons, tops, bottoms, color):
    """Вертикальная стенка вдоль линии точек (lats, lons) от высот tops
    до bottoms. Где top не выше bottom, стенки нет. Нормаль -
    горизонтальная, поперёк линии."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    tops = np.asarray(tops, dtype=np.float64)
    bottoms = np.asarray(bottoms, dtype=np.float64)
    n = len(lats)
    if n < 2:
        return None
    top = ecef(lats, lons, tops)
    bottom = ecef(lats, lons, bottoms)
    along = np.empty_like(top)
    along[1:-1] = top[2:] - top[:-2]
    along[0] = top[1] - top[0]
    along[-1] = top[-1] - top[-2]
    up = _unit(top)
    side = _unit(np.cross(along, up))
    positions = np.vstack([top, bottom])
    normals = np.vstack([side, side])
    i = np.arange(n - 1)
    # Ячейка есть, если стенка не нулевая хотя бы на одном краю.
    keep = (tops[i] > bottoms[i]) | (tops[i + 1] > bottoms[i + 1])
    i = i[keep]
    if not len(i):
        return None
    tris = np.concatenate([np.stack([i, i + 1, n + i], -1),
                           np.stack([i + 1, n + i + 1, n + i], -1)])
    # Где поверхности пересеклись, низ поднимается до верха.
    clipped = np.minimum(bottoms, tops)
    positions[n:] = ecef(lats, lons, clipped)
    return Part(positions, normals, _rgba(color, 2 * n),
                tris.astype(np.uint32))


def merge(parts, key=None):
    """Куски в одну сетку для видеокарты: центр - середина рамки."""
    parts = [p for p in parts if p is not None and len(p.indices)]
    if not parts:
        return None
    positions = np.vstack([p.positions for p in parts])
    center = (positions.min(axis=0) + positions.max(axis=0)) / 2.0
    vertices = np.zeros(len(positions), dtype=VERTEX)
    vertices["position"] = (positions - center).astype(np.float32)
    normals = np.vstack([p.normals for p in parts])
    vertices["normal"][:, :3] = np.clip(np.rint(normals * 127.0),
                                        -127, 127).astype(np.int8)
    vertices["color"] = np.vstack([p.colors for p in parts])
    offset = 0
    indices = []
    for p in parts:
        indices.append(p.indices + offset)
        offset += len(p.positions)
    return Mesh(key, center, vertices,
                np.concatenate(indices).ravel().astype(np.uint32))


Grid = namedtuple("Grid", "x0 y0 dx dy z")
Grid.__doc__ = """Растр отметок: узел (0, 0) в точке (x0, y0) системы
координат растра, шаг dx по столбцам, dy по строкам (у растров
с севера на юг отрицательный), z (rows, cols), пусто - NaN."""


def display(z, scale, ground):
    """Высота на экране для отметки z. С рельефом - z, умноженная на
    масштаб, как у поверхности. Рельеф выключен (scale 0) - глубина
    под поверхностью: z - ground, ground - отметка рельефа."""
    z = np.asarray(z, dtype=np.float64)
    if scale:
        return z * scale
    return z - np.asarray(ground, dtype=np.float64)


def sample_grid(grid, x, y):
    """Отметки растра в точках (x, y) его системы, билинейно. Вне
    растра и у пустых узлов - NaN."""
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    rows, cols = grid.z.shape
    fx = (x - grid.x0) / grid.dx
    fy = (y - grid.y0) / grid.dy
    out = np.full(np.shape(x), np.nan)
    ok = (fx >= 0) & (fx <= cols - 1) & (fy >= 0) & (fy <= rows - 1)
    if not np.any(ok):
        return out
    fx, fy = fx[ok], fy[ok]
    j = np.minimum(fx.astype(np.int64), max(cols - 2, 0))
    i = np.minimum(fy.astype(np.int64), max(rows - 2, 0))
    ax, ay = fx - j, fy - i
    j1 = np.minimum(j + 1, cols - 1)
    i1 = np.minimum(i + 1, rows - 1)
    z = grid.z
    # Узел с нулевым весом не участвует: пустой сосед на краю ячейки
    # не делает точку пустой.
    total = np.zeros(len(fx))
    for value, weight in ((z[i, j], (1 - ax) * (1 - ay)),
                          (z[i, j1], ax * (1 - ay)),
                          (z[i1, j], (1 - ax) * ay),
                          (z[i1, j1], ax * ay)):
        total += np.where(weight > 0.0, value * weight, 0.0)
    out[ok] = total
    return out


def stack(surfaces):
    """Поверхности сверху вниз (k, n) без пересечений: каждая не выше
    предыдущей, пустое значение - мощность пласта 0."""
    out = np.array(surfaces, dtype=np.float64)
    for i in range(1, len(out)):
        out[i] = np.where(np.isnan(out[i]), out[i - 1],
                          np.minimum(out[i], out[i - 1]))
    return out


def fence(lats, lons, surfaces, colors):
    """Стенки разреза вдоль линии: между поверхностями surfaces (k, n)
    высот на экране сверху вниз - пласты цветов colors (k - 1)."""
    parts = []
    for top, bottom, color in zip(surfaces[:-1], surfaces[1:], colors):
        parts.append(wall(lats, lons, top, bottom, color))
    return parts


def densify(points, step):
    """Точки ломаной (n, 2) через шаг не больше step, с вершинами."""
    points = np.asarray(points, dtype=np.float64)
    out = [points[:1]]
    for a, b in zip(points[:-1], points[1:]):
        count = max(1, int(np.ceil(np.hypot(*(b - a)) / step)))
        share = np.arange(1, count + 1)[:, None] / count
        out.append(a + (b - a) * share)
    return np.vstack(out)


def along(lats, lons):
    """Доля длины ломаной от начала до каждой точки, от 0 до 1. Длина -
    по шару радиуса эллипсоида, хватает для линий в километры."""
    lats = np.radians(np.asarray(lats, dtype=np.float64))
    lons = np.radians(np.asarray(lons, dtype=np.float64))
    if len(lats) < 2:
        return np.zeros(len(lats))
    dy = np.diff(lats)
    dx = np.diff(lons) * np.cos((lats[1:] + lats[:-1]) / 2.0)
    run = np.concatenate([[0.0], np.cumsum(np.hypot(dx, dy))])
    return run / run[-1] if run[-1] > 0.0 else np.zeros(len(lats))


# Вершина стенки с картинкой: смещение от центра и место в картинке.
IMAGE_VERTEX = np.dtype([("position", np.float32, 3),
                         ("uv", np.float32, 2)])


def image_wall(lats, lons, tops, bottoms):
    """Вертикальная стенка вдоль линии для картинки разреза: (центр
    в ECEF, вершины IMAGE_VERTEX, индексы). tops, bottoms - высоты верха
    и низа на экране в точках линии. Картинка ложится по длине линии
    слева направо, верх картинки - вверху стенки."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    top = ecef(lats, lons, np.broadcast_to(tops, lats.shape))
    bottom = ecef(lats, lons, np.broadcast_to(bottoms, lats.shape))
    points = np.vstack([top, bottom])
    center = points.mean(axis=0)
    n = len(lats)
    share = along(lats, lons)
    vertices = np.zeros(2 * n, dtype=IMAGE_VERTEX)
    vertices["position"] = (points - center).astype(np.float32)
    vertices["uv"][:n, 0] = share
    vertices["uv"][n:, 0] = share
    vertices["uv"][n:, 1] = 1.0
    i = np.arange(n - 1, dtype=np.uint32)
    indices = np.column_stack([i, i + n, i + 1, i + 1, i + n, i + n + 1])
    return center, vertices, indices.ravel()


def to_line(line_lats, line_lons, distance, lats, lons):
    """Точки (lats, lons) на разрезе вдоль линии с точками (line_lats,
    line_lons) и расстояниями distance от начала: (расстояние вдоль
    линии до ближайшей точки линии, удаление от неё) в единицах
    distance и метрах. Шаг точек линии меньше полосы разреза."""
    def unit(la, lo):
        la = np.radians(np.asarray(la, dtype=np.float64))
        lo = np.radians(np.asarray(lo, dtype=np.float64))
        return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                         np.sin(la)], axis=-1)
    line = unit(line_lats, line_lons)
    points = unit(lats, lons).reshape(-1, 3)
    dots = points @ line.T
    nearest = np.argmax(dots, axis=1)
    gap = np.arccos(np.clip(dots[np.arange(len(points)), nearest], -1.0,
                            1.0))
    radius = (2.0 * ellipsoid.A + ellipsoid.B) / 3.0
    return np.asarray(distance, dtype=np.float64)[nearest], gap * radius


def nearest_on_screen(pixels, front, px, py):
    """Ближайшая к пикселю (px, py) точка ломаной на экране: (расстояние
    в пикселях, номер отрезка, доля t вдоль него) или None. Отрезок
    с концом за камерой не берётся."""
    p = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    ok = np.asarray(front, dtype=bool)
    if len(p) == 1:
        return (float(np.hypot(p[0, 0] - px, p[0, 1] - py)), 0, 0.0) \
            if ok[0] else None
    a, b = p[:-1], p[1:]
    seg = ok[:-1] & ok[1:]
    if not np.any(seg):
        return None
    d = b - a
    length2 = np.maximum((d ** 2).sum(axis=1), 1e-12)
    t = np.clip(((px - a[:, 0]) * d[:, 0] + (py - a[:, 1]) * d[:, 1])
                / length2, 0.0, 1.0)
    gap = np.hypot(a[:, 0] + t * d[:, 0] - px, a[:, 1] + t * d[:, 1] - py)
    gap = np.where(seg, gap, np.inf)
    i = int(np.argmin(gap))
    return float(gap[i]), i, float(t[i])


def tunnel_z(ground, start, end, share):
    """Отметки оси тоннеля: под рельефом ground на глубину, которая
    меняется от start в начале линии до end в конце по доле длины
    share. Спуск к порталу - линия от 0 до глубины тоннеля."""
    depth = start + (end - start) * np.asarray(share, dtype=np.float64)
    return np.asarray(ground, dtype=np.float64) - depth


def floor_part(ring, alt, color):
    """Дно выреза: многоугольник ring (n, 2) широта, долгота на высоте
    alt, нормаль вверх."""
    try:  # внутри плагина QGIS
        from .features import plane, triangulate
    except ImportError:  # headless-тесты
        from features import plane, triangulate
    ring = np.asarray(ring, dtype=np.float64)
    tris = triangulate(plane(ring))
    if not len(tris):
        return None
    positions = ecef(ring[:, 0], ring[:, 1], np.full(len(ring), alt))
    normals = surface_normal(ring[:, 0], ring[:, 1])
    return Part(positions, normals, _rgba(color, len(ring)),
                np.asarray(tris, dtype=np.uint32).reshape(-1, 3))


def inside(lats, lons, ring):
    """Признак «внутри многоугольника» для точек. ring - (n, 2) широта,
    долгота, без повтора первой точки. Чётность пересечений луча."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    ring = np.asarray(ring, dtype=np.float64)
    result = np.zeros(lats.shape, dtype=bool)
    y0, x0 = ring[:, 0], ring[:, 1]
    y1, x1 = np.roll(y0, -1), np.roll(x0, -1)
    for a, b, c, d in zip(y0, x0, y1, x1):
        crosses = (a > lats) != (c > lats)
        if not np.any(crosses):
            continue
        x = b + (lats - a) * (d - b) / np.where(c != a, c - a, 1.0)
        result ^= crosses & (lons < x)
    return result
