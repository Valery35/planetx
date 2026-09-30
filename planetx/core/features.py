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
    from . import ellipsoid
    from .ellipsoid import geodetic_to_ecef
except ImportError:  # headless-тесты
    import ellipsoid
    from ellipsoid import geodetic_to_ecef

STEP = 100.0  # метров между точками сгущения
MAX_POINTS = 4000  # точек на линию или контур, не больше
# Точек на объект глобуса, не больше. У мелкого объекта шаг остаётся
# STEP, у крупного растёт. Сгущение до 4000 точек давало у 29 провинций
# Афганистана 112 тысяч вершин вместо 2.5 тысяч, 28 сентября 2026 года.
SHAPE_POINTS = 800

Shape = namedtuple("Shape",
                   "kind points color width fill name height extrude "
                   "icon alts",
                   defaults=((255, 255, 0, 255), 2.0, None, "", 0.0,
                             False, "dot", None))
Shape.__doc__ = """Объект глобуса.

kind - "point", "line" или "polygon". points - вершины (широта,
долгота) в градусах, у многоугольника без повтора первой. color -
цвет линии RGBA 0-255, width - толщина в логических пикселях, fill -
цвет заливки многоугольника RGBA или None. name - подпись. height -
подъём над рельефом в метрах, как «относительно земли» у Google Earth.
extrude - стена от объекта до земли, у точки - стойка. icon - значок
точки из core/icons.py, окрашенный цветом color. alts - высоты точек
над эллипсоидом в метрах или None. С ними объект 3D-линейки стоит
в пространстве, как «абсолютная высота» KML: отрезки прямые, на рельеф
не садятся, height не действует.
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
    total = float(angles.sum()) * ellipsoid.A
    step = max(step, total / max(1, max_points - len(ring)))
    out = []
    for i, (p, q, angle) in enumerate(zip(u[:-1], u[1:], angles)):
        n = max(1, int(math.ceil(angle * ellipsoid.A / step)))
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


def fill(points, step=STEP, max_points=MAX_POINTS):
    """Сгущённый контур многоугольника и треугольники заливки.

    Режутся только исходные вершины, номера переносятся на сгущённый
    контур: вершина i стоит в нём в начале своей стороны. Резка всего
    сгущённого контура шла 1.1 с на 800 точек при каждом движении мыши,
    у больших многоугольников - минуты, QGIS висел, 27 сентября 2026
    года. Точки между вершинами лежат на сторонах и в заливку не входят.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    ring = densify(pts, closed=True, step=step, max_points=max_points)
    starts = []
    position = 0
    for vertex in pts:
        # Вершины стоят в контуре по порядку, каждая - первой точкой
        # своей стороны, densify ставит их точно.
        while position < len(ring) and not np.array_equal(ring[position],
                                                          vertex):
            position += 1
        starts.append(position)
    tri = triangulate(plane(pts))
    return ring, np.asarray([starts[i] for i in tri], dtype=np.uint32)


def lift(latlon, height_at=None, offset=0.0, heights_at=None):
    """Точки (широта, долгота) на рельефе плюс offset метров в ECEF,
    float64 (n, 3).

    heights_at - высоты массива точек одним вызовом, у него приоритет
    перед height_at по одной точке.
    """
    latlon = np.asarray(latlon, dtype=np.float64).reshape(-1, 2)
    if heights_at is not None:
        h = np.asarray(heights_at(latlon[:, 0], latlon[:, 1]),
                       dtype=np.float64)
    elif height_at is None:
        h = np.zeros(len(latlon))
    else:
        h = np.array([height_at(float(a), float(b)) for a, b in latlon])
    return geodetic_to_ecef(latlon[:, 0], latlon[:, 1], h + offset)


MAX_HEIGHT = 100000.0  # метров подъёма метки, не больше


def height_share(height):
    """Место ползунка высоты от 0 (земля) до 1 (MAX_HEIGHT), шкала
    логарифмическая, как ползунок «Поверхность земли - Космос» Google
    Earth. Метры у земли и километры в небе ставятся одинаково точно."""
    height = min(max(float(height), 0.0), MAX_HEIGHT)
    return math.log10(height + 1.0) / math.log10(MAX_HEIGHT + 1.0)


def share_height(share):
    """Высота по месту ползунка, обратная height_share."""
    share = min(max(float(share), 0.0), 1.0)
    return (MAX_HEIGHT + 1.0) ** share - 1.0


Geometry = namedtuple("Geometry", "ring lines triangles wall stem alts",
                      defaults=(None,))
Geometry.__doc__ = """Контур объекта для видеокарты, от высот не зависит.

ring - вершины (широта, долгота) после сгущения. lines, triangles,
wall - индексы отрезков, заливки и стены. У выдавленного объекта
вершины идут дважды: поднятые, потом на земле. stem - стойка точки.
alts - высоты вершин над эллипсоидом у 3D-объекта, иначе None.
"""


def has_alts(shape):
    """Стоит ли объект в пространстве по своим высотам."""
    alts = getattr(shape, "alts", None)
    return alts is not None and len(alts) == len(shape.points) \
        and len(alts) > 0


def geometry(shape):
    """Контур объекта или None для точки без стойки и пустого объекта."""
    height = float(shape.height or 0.0)
    raised = bool(shape.extrude) and height > 0.0
    empty = np.zeros(0, dtype=np.uint32)
    if shape.kind == "point":
        if not raised or not shape.points:
            return None
        ring = np.asarray(shape.points[:1], dtype=np.float64)
        return Geometry(ring, np.array([0, 1], dtype=np.uint32), empty,
                        empty, True)
    if len(shape.points) < 2:
        return None
    closed = shape.kind == "polygon" and len(shape.points) >= 3
    triangles = empty
    if has_alts(shape):
        # Прямые отрезки в пространстве, без сгущения по дуге.
        ring = np.asarray(shape.points, dtype=np.float64).reshape(-1, 2)
        if closed and shape.fill is not None:
            triangles = np.asarray(triangulate(plane(ring)),
                                   dtype=np.uint32).ravel()
        return Geometry(ring, segments(len(ring), closed=closed), triangles,
                        empty, False,
                        np.asarray(shape.alts, dtype=np.float64))
    if closed and shape.fill is not None:
        ring, triangles = fill(shape.points, max_points=SHAPE_POINTS)
    else:
        ring = densify(shape.points, closed=closed, max_points=SHAPE_POINTS)
    wall = walls(len(ring), closed=closed) if raised else empty
    return Geometry(ring, segments(len(ring), closed=closed), triangles,
                    wall, False)


def vertices(geo, height, heights_at=None):
    """Вершины контура в ECEF: поднятые, у стены и стойки ещё земля."""
    if geo.alts is not None:
        return geodetic_to_ecef(geo.ring[:, 0], geo.ring[:, 1], geo.alts)
    top = lift(geo.ring, offset=height, heights_at=heights_at)
    if len(geo.wall) or geo.stem:
        return np.vstack([top, lift(geo.ring, heights_at=heights_at)])
    return top


def walls(n, closed=False):
    """Треугольники стены между верхом и низом, uint32.

    Вершины 0..n-1 - поднятая линия, n..2n-1 - те же точки на земле.
    На отрезок - два треугольника.
    """
    if n < 2:
        return np.zeros(0, dtype=np.uint32)
    a = np.arange(n - 1, dtype=np.uint32)
    b = a + 1
    if closed:
        a = np.append(a, n - 1).astype(np.uint32)
        b = np.append(b, 0).astype(np.uint32)
    quads = np.stack([a, b, b + n, a, b + n, a + n], axis=1)
    return quads.astype(np.uint32).ravel()


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
    x = np.radians(dlon) * ellipsoid.A * math.cos(math.radians(lat0))
    y = np.radians(latlon[:, 0] - lat0) * ellipsoid.A
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
