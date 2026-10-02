# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Правка вершин пути и многоугольника на экране.

Вершины и середины отрезков приходят уже в пикселях кадра. Модуль
решает, что под курсором, куда встаёт новая вершина и когда щелчок
по вершине завершает рисование. Попадание курсора в сохранённый объект
считается здесь же, в пикселях.
"""
import numpy as np

VERTEX = "vertex"
MIDDLE = "middle"
CLOSE = "close"  # щелчок по первой вершине: фигура замыкается
FINISH = "finish"  # щелчок по последней вершине: путь завершён


def _nearest(pixels, front, px, py, radius):
    pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    if not len(pixels):
        return None, np.inf
    d = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
    d[~np.asarray(front, dtype=bool)] = np.inf
    best = int(np.argmin(d))
    if d[best] > radius:
        return None, np.inf
    return best, float(d[best])


def pick(vertices, vertex_front, middles, middle_front, px, py, radius):
    """Что под курсором: (VERTEX, номер), (MIDDLE, номер отрезка) или
    None. Вершина старше середины, если обе в радиусе."""
    index, _ = _nearest(vertices, vertex_front, px, py, radius)
    if index is not None:
        return VERTEX, index
    index, _ = _nearest(middles, middle_front, px, py, radius)
    if index is not None:
        return MIDDLE, index
    return None


def inserted(points, alts, segment, point, alt=None):
    """Точки и высоты с новой вершиной на отрезке segment. Отрезок
    segment идёт от вершины segment к следующей, последний отрезок
    замкнутой фигуры - к первой."""
    at = segment + 1
    return (list(points[:at]) + [tuple(point)] + list(points[at:]),
            list(alts[:at]) + [alt] + list(alts[at:]))


def removed(points, alts, index):
    """Точки и высоты без вершины index."""
    return (list(points[:index]) + list(points[index + 1:]),
            list(alts[:index]) + list(alts[index + 1:]))


def click_result(mode, count, index, finished):
    """Чем кончается щелчок по вершине index без перетаскивания:
    CLOSE, FINISH или None. mode - "path" или "polygon", count -
    количество вершин."""
    if finished or mode not in ("path", "polygon"):
        return None
    if index == 0 and count >= 3:
        return CLOSE
    if mode == "path" and count >= 2 and index == count - 1:
        return FINISH
    return None


def segment_distance(pixels, front, px, py, closed=False):
    """Расстояние в пикселях от курсора до ломаной. Отрезок с концом
    за камерой не считается."""
    p = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    f = np.asarray(front, dtype=bool)
    if len(p) < 2:
        return np.inf
    a, b = p[:-1], p[1:]
    ok = f[:-1] & f[1:]
    if closed and len(p) >= 3:
        a = np.vstack([a, p[-1:]])
        b = np.vstack([b, p[:1]])
        ok = np.append(ok, f[-1] and f[0])
    if not ok.any():
        return np.inf
    a, b = a[ok], b[ok]
    ab = b - a
    length = (ab ** 2).sum(axis=1)
    length[length == 0.0] = 1.0
    cursor = np.array([px, py], dtype=np.float64)
    t = np.clip(((cursor - a) * ab).sum(axis=1) / length, 0.0, 1.0)
    nearest = a + ab * t[:, None]
    return float(np.hypot(nearest[:, 0] - px, nearest[:, 1] - py).min())


def inside(pixels, px, py):
    """Лежит ли курсор внутри многоугольника на экране, правило
    чётности."""
    p = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    if len(p) < 3:
        return False
    x1, y1 = p[:, 0], p[:, 1]
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    cross = (y1 > py) != (y2 > py)
    dy = np.where(y2 == y1, 1.0, y2 - y1)
    x = x1 + (py - y1) * (x2 - x1) / dy
    return bool(np.count_nonzero(cross & (px < x)) % 2)


def hit(kind, pixels, front, px, py, radius):
    """Попал ли курсор в объект вида kind: "point", "line", "polygon"."""
    front = np.asarray(front, dtype=bool)
    if not len(front) or not front.any():
        return False
    if kind == "point":
        return _nearest(pixels[:1], front[:1], px, py, radius)[0] is not None
    if kind == "line":
        return segment_distance(pixels, front, px, py) <= radius
    if segment_distance(pixels, front, px, py, closed=True) <= radius:
        return True
    return bool(front.all()) and inside(pixels, px, py)
