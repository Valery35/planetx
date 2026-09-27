# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои объекты глобуса: точки, линии и многоугольники по рельефу.

Расчёт без Qt и OpenGL. Объект задаётся широтой и долготой вершин.
Линия и контур многоугольника сгущаются по дуге большого круга, чтобы
длинный отрезок шёл по поверхности, а не под ней. Точки садятся
на рельеф и переводятся в ECEF. В видеокарту уходят смещения от центра
объекта в float32, центр остаётся в float64, как у тайлов (AGENTS.md,
раздел «Координаты»).

Заливка многоугольника режется на треугольники отсечением ушей
в касательной плоскости у его середины. Треугольники проходят
по высотам вершин контура. В горах середина большого многоугольника
может уйти под рельеф, облегание рельефа заливкой не сделано.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import A, geodetic_to_ecef
except ImportError:  # headless-тесты
    from ellipsoid import A, geodetic_to_ecef

STEP = 100.0  # метров между точками сгущения
MAX_POINTS = 4000  # точек на линию или контур, не больше

Shape = namedtuple("Shape", "kind points color width fill name",
                   defaults=((255, 255, 0, 255), 2.0, None, ""))
Shape.__doc__ = """Объект глобуса.

kind - "point", "line" или "polygon". points - вершины (широта,
долгота) в градусах, у многоугольника без повтора первой. color -
цвет линии RGBA 0-255, width - толщина в логических пикселях, fill -
цвет заливки многоугольника RGBA или None. name - подпись.
"""


def _unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                     np.sin(la)], axis=-1)


def _latlon(u):
    lat = np.degrees(np.arctan2(u[..., 2], np.hypot(u[..., 0], u[..., 1])))
    lon = np.degrees(np.arctan2(u[..., 1], u[..., 0]))
    return np.stack([lat, lon], axis=-1)


def densify(points, closed=False, step=STEP, max_points=MAX_POINTS):
    """Вершины со вставками по дуге большого круга, массив (n, 2).

    Шаг step метров. Если точек вышло бы больше max_points, шаг растёт.
    closed - контур, последняя вершина соединяется с первой.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        return pts.copy()
    ring = np.vstack([pts, pts[:1]]) if closed else pts
    u = _unit(ring[:, 0], ring[:, 1])
    angles = np.arccos(np.clip((u[:-1] * u[1:]).sum(axis=1), -1.0, 1.0))
    total = float(angles.sum()) * A
    step = max(step, total / max(1, max_points - len(ring)))
    out = []
    for i, (p, q, angle) in enumerate(zip(u[:-1], u[1:], angles)):
        n = max(1, int(math.ceil(angle * A / step)))
        t = np.arange(n)[:, None] / n
        if angle < 1e-12:
            part = np.repeat(p[None], n, axis=0)
        else:
            s = math.sin(angle)
            part = (np.sin((1.0 - t) * angle) * p
                    + np.sin(t * angle) * q) / s
        part = _latlon(part)
        part[0] = ring[i]  # исходная вершина точно, без перевода туда-обратно
        out.append(part)
    if not closed:
        out.append(ring[-1:])
    return np.vstack(out)


def lift(latlon, height_at=None):
    """Точки (широта, долгота) на рельефе в ECEF, float64 (n, 3)."""
    latlon = np.asarray(latlon, dtype=np.float64).reshape(-1, 2)
    if height_at is None:
        h = np.zeros(len(latlon))
    else:
        h = np.array([height_at(float(a), float(b)) for a, b in latlon])
    return geodetic_to_ecef(latlon[:, 0], latlon[:, 1], h)


def centered(xyz):
    """Центр в float64 и смещения от него в float32."""
    xyz = np.asarray(xyz, dtype=np.float64)
    center = 0.5 * (xyz.min(axis=0) + xyz.max(axis=0))
    return center, (xyz - center).astype(np.float32)


def segments(n, closed=False):
    """Индексы отрезков ломаной из n точек для GL_LINES, uint32."""
    if n < 2:
        return np.zeros(0, dtype=np.uint32)
    a = np.arange(n - 1, dtype=np.uint32)
    pairs = np.stack([a, a + 1], axis=1)
    if closed:
        pairs = np.vstack([pairs, [[n - 1, 0]]]).astype(np.uint32)
    return pairs.ravel()


def _area2(p):
    x, y = p[:, 0], p[:, 1]
    return float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def plane(latlon):
    """Точки в касательной плоскости у середины, метры (n, 2)."""
    latlon = np.asarray(latlon, dtype=np.float64)
    lat0 = float(latlon[:, 0].mean())
    lon0 = float(latlon[:, 1].mean())
    dlon = (latlon[:, 1] - lon0 + 180.0) % 360.0 - 180.0
    x = np.radians(dlon) * A * math.cos(math.radians(lat0))
    y = np.radians(latlon[:, 0] - lat0) * A
    return np.stack([x, y], axis=1)


def _inside(p, a, b, c):
    """Лежит ли точка p в треугольнике abc против часовой стрелки."""
    def side(u, v, w):
        return (v[0] - u[0]) * (w[1] - u[1]) - (v[1] - u[1]) * (w[0] - u[0])
    return side(a, b, p) >= 0 and side(b, c, p) >= 0 and side(c, a, p) >= 0


def triangulate(points):
    """Треугольники простого многоугольника отсечением ушей, uint32 (m*3).

    points - вершины на плоскости (n, 2) без повтора первой, в любом
    обходе. Многоугольник без дыр и самопересечений.
    """
    p = np.asarray(points, dtype=np.float64)
    n = len(p)
    if n < 3:
        return np.zeros(0, dtype=np.uint32)
    order = list(range(n)) if _area2(p) > 0 else list(range(n))[::-1]
    out = []
    guard = 0
    while len(order) > 3 and guard < 2 * n * n:
        guard += 1
        m = len(order)
        cut = False
        for i in range(m):
            ia, ib, ic = order[i - 1], order[i], order[(i + 1) % m]
            a, b, c = p[ia], p[ib], p[ic]
            cross = (b[0] - a[0]) * (c[1] - a[1]) \
                - (b[1] - a[1]) * (c[0] - a[0])
            if cross <= 0:
                continue  # вогнутая вершина или вырожденная
            if any(_inside(p[j], a, b, c) for j in order
                   if j not in (ia, ib, ic)):
                continue
            out.extend((ia, ib, ic))
            del order[i]
            cut = True
            break
        if not cut:
            break  # многоугольник неправильный, остаток не режется
    if len(order) == 3:
        out.extend(order)
    return np.asarray(out, dtype=np.uint32)
