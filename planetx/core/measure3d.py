# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-путь и 3D-многоугольник: попадание луча в здание и меры в
пространстве, без Qt.

Точка 3D-линейки ставится туда, куда смотрит луч из глаза: на крышу
или стену здания, если луч встречает его раньше рельефа. Путь меряется
прямыми отрезками между точками в ECEF. Площадь многоугольника - длина
векторной площади по Ньюэллу, у плоского многоугольника это его
настоящая площадь при любом наклоне. Наклон плоскости - угол между её
нормалью и вертикалью в середине многоугольника.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import ecef_to_geodetic, surface_normal
except ImportError:  # headless-тесты
    from ellipsoid import ecef_to_geodetic, surface_normal

EPSILON = 1e-9  # доля, ниже которой луч считается параллельным треугольнику


def ray_triangles(origin, direction, a, b, c):
    """Ближнее попадание луча в треугольники (a[i], b[i], c[i]).

    origin и direction - луч, direction не обязан быть единичным.
    Треугольники - массивы (n, 3) в тех же координатах. Возвращает
    параметр t точки origin + t·direction или None. Метод
    Мёллера-Трумбора, стороны треугольника не важны.
    """
    a = np.asarray(a, dtype=np.float64)
    if len(a) == 0:
        return None
    d = np.asarray(direction, dtype=np.float64)
    e1 = np.asarray(b, dtype=np.float64) - a
    e2 = np.asarray(c, dtype=np.float64) - a
    p = np.cross(d, e2)
    det = (e1 * p).sum(axis=1)
    scale = np.linalg.norm(e1, axis=1) * np.linalg.norm(e2, axis=1) \
        * np.linalg.norm(d)
    ok = np.abs(det) > EPSILON * np.maximum(scale, 1e-300)
    inv = np.zeros_like(det)
    inv[ok] = 1.0 / det[ok]
    s = np.asarray(origin, dtype=np.float64) - a
    u = (s * p).sum(axis=1) * inv
    q = np.cross(s, e1)
    v = (q * d).sum(axis=1) * inv
    t = (q * e2).sum(axis=1) * inv
    hit = ok & (u >= 0.0) & (v >= 0.0) & (u + v <= 1.0) & (t > 0.0)
    if not hit.any():
        return None
    return float(t[hit].min())


def ray_sphere(origin, direction, center, radius):
    """Задевает ли луч шар, быстрый отбор тайлов зданий."""
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    m = np.asarray(origin, dtype=np.float64) - np.asarray(center)
    b = float(m @ d)
    c = float(m @ m) - radius * radius
    return c <= 0.0 or (b <= 0.0 and b * b - c >= 0.0)


def path_length(points):
    """Длина ломаной в ECEF (n, 3) прямыми отрезками, метры."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(p) < 2:
        return 0.0
    return float(np.linalg.norm(p[1:] - p[:-1], axis=1).sum())


def vector_area(points):
    """Векторная площадь замкнутого многоугольника в ECEF по Ньюэллу.
    Направление - нормаль, длина - площадь плоского многоугольника."""
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(p) < 3:
        return np.zeros(3)
    p = p - p.mean(axis=0)
    return 0.5 * np.cross(p, np.roll(p, -1, axis=0)).sum(axis=0)


def polygon(points):
    """Периметр, площадь и наклон 3D-многоугольника (n, 3) в ECEF.

    Наклон - угол плоскости к горизонту в градусах, 0 - ровная крыша,
    90 - стена. Для двух точек и меньше площадь и наклон нулевые.
    """
    p = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    if len(p) < 2:
        return 0.0, 0.0, 0.0
    perimeter = path_length(np.vstack([p, p[:1]])) if len(p) >= 3 \
        else 2.0 * path_length(p)
    area_vector = vector_area(p)
    area = float(np.linalg.norm(area_vector))
    if area == 0.0:
        return perimeter, 0.0, 0.0
    lat, lon, _ = ecef_to_geodetic(p.mean(axis=0))
    up = np.asarray(surface_normal(float(lat), float(lon)), dtype=np.float64)
    cos_tilt = abs(float(area_vector @ up)) / area
    tilt = math.degrees(math.acos(min(1.0, cos_tilt)))
    return perimeter, area, tilt
