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
    from .buildings import VERTEX
    from .ellipsoid import geodetic_to_ecef, surface_normal
except ImportError:  # headless-тесты
    from buildings import VERTEX
    from ellipsoid import geodetic_to_ecef, surface_normal

SIDES = 8  # граней трубки ствола

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
    idx = np.arange(rows * cols).reshape(rows, cols)
    a, b = idx[:-1, :-1], idx[:-1, 1:]
    c, d = idx[1:, :-1], idx[1:, 1:]
    cell = valid[:-1, :-1] & valid[:-1, 1:] & valid[1:, :-1] & valid[1:, 1:]
    tris = np.concatenate([np.stack([a, b, c], -1)[cell],
                           np.stack([b, d, c], -1)[cell]])
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
