# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Что лежит под щелчком по глобусу: метки «Моих меток». Без Qt.

Окно «Объекты» опрашивает не только слои проекта, но и метки, очаги
землетрясений и само место, просьба автора от 3 октября 2026 года.
Здесь - расстояние от точки щелчка до метки, пути и многоугольника
в метрах. Допуск задаёт окно в пикселях экрана, переведённых в метры
по удалению точки, как у слоёв проекта.

Расстояние считается в касательной плоскости у точки щелчка: широта
и долгота переходят в метры на шаре среднего радиуса. Для допуска
в несколько пикселей ошибка такой плоскости не важна, даже когда путь
длиной в тысячи километров: ближайший отрезок рядом с точкой.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
except ImportError:  # headless-тесты
    import ellipsoid


def _local(points, lat, lon):
    """Точки (широта, долгота) в метрах касательной плоскости у точки."""
    radius = (2.0 * ellipsoid.A + ellipsoid.B) / 3.0
    p = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    dlon = (p[:, 1] - lon + 180.0) % 360.0 - 180.0
    x = np.radians(dlon) * radius * math.cos(math.radians(lat))
    y = np.radians(p[:, 0] - lat) * radius
    return np.stack([x, y], axis=-1)


def _segments(xy, closed):
    """Расстояние от начала координат до ломаной xy, метры."""
    if len(xy) == 1:
        return float(np.hypot(*xy[0]))
    a = xy
    b = np.roll(xy, -1, axis=0)
    if not closed:
        a, b = a[:-1], b[:-1]
    d = b - a
    length2 = np.einsum("ij,ij->i", d, d)
    t = np.where(length2 > 0.0,
                 np.clip(np.einsum("ij,ij->i", -a, d)
                         / np.where(length2 > 0.0, length2, 1.0), 0.0, 1.0),
                 0.0)
    nearest = a + t[:, None] * d
    return float(np.min(np.hypot(nearest[:, 0], nearest[:, 1])))


def _inside(xy):
    """Начало координат внутри многоугольника xy - чётность пересечений."""
    x, y = xy[:, 0], xy[:, 1]
    x1, y1 = np.roll(x, -1), np.roll(y, -1)
    crosses = (y > 0.0) != (y1 > 0.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        at = x + (0.0 - y) * (x1 - x) / np.where(y1 != y, y1 - y, 1.0)
    return bool(np.sum(crosses & (at > 0.0)) % 2)


def distance(kind, points, lat, lon):
    """Расстояние от точки щелчка до объекта, метры. Внутри
    многоугольника - 0."""
    if not points:
        return float("inf")
    xy = _local(points, lat, lon)
    if kind == "polygon" and len(xy) >= 3:
        if _inside(xy):
            return 0.0
        return _segments(xy, True)
    if kind == "point":
        return float(np.hypot(*xy[0]))
    return _segments(xy, False)


def picked(shapes, lat, lon, metres):
    """Номера объектов (вид, точки) ближе metres к точке щелчка, от
    ближнего к дальнему."""
    found = []
    for n, (kind, points) in enumerate(shapes):
        gap = distance(kind, points, lat, lon)
        if gap <= metres:
            found.append((gap, n))
    return [n for _, n in sorted(found)]


def path_length(points, closed=False):
    """Длина ломаной по дугам большого круга на шаре среднего радиуса,
    метры. У многоугольника - периметр."""
    if len(points) < 2:
        return 0.0
    radius = (2.0 * ellipsoid.A + ellipsoid.B) / 3.0
    p = np.radians(np.asarray(points, dtype=np.float64))
    if closed:
        p = np.vstack([p, p[:1]])
    lat1, lon1 = p[:-1, 0], p[:-1, 1]
    lat2, lon2 = p[1:, 0], p[1:, 1]
    h = (np.sin((lat2 - lat1) / 2.0) ** 2 + np.cos(lat1) * np.cos(lat2)
         * np.sin((lon2 - lon1) / 2.0) ** 2)
    return float(np.sum(2.0 * radius * np.arcsin(np.sqrt(np.clip(h, 0.0,
                                                                 1.0)))))
