# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейка: единицы, запись величин, точка по азимуту, профиль высот
и длина по рельефу. Без Qt.

Длина, площадь и окружность круга на эллипсоиде WGS84 считаются
в ui/measure.py через QgsDistanceArea из QGIS. Здесь - то, что
от QGIS не зависит.

Профиль и длина по рельефу считаются по точкам вдоль линии. Линия
сгущается по дуге большого круга с шагом в пиксель самого точного
уровня высот, но не больше PROFILE_POINTS точек. Длина по рельефу -
сумма отрезков между соседними точками на их высотах.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import A, ecef_to_geodetic, geodetic_to_ecef
    from .features import densify
    from .terrain import MAX_LEVEL as HEIGHT_LEVEL
    from .tiling import lonlat_to_tile
except ImportError:  # headless-тесты
    from ellipsoid import A, ecef_to_geodetic, geodetic_to_ecef
    from features import densify
    from terrain import MAX_LEVEL as HEIGHT_LEVEL
    from tiling import lonlat_to_tile

CIRCLE_POINTS = 128
PROFILE_POINTS = 2000  # точек вдоль линии, не больше
# Уклон меряется на отрезке не короче стольких пикселей тайла высот.
# Между соседними точками через пиксель шероховатость данных давала
# на Эльбрусе наибольший уклон 180 %, 30 сентября 2026 года.
SLOPE_PIXELS = 3
TILE_PIXELS = 256

Profile = namedtuple("Profile", "latlon distance height flat ground low high "
                                "gain loss mean_slope max_slope window",
                     defaults=(0.0,))
Profile.__doc__ = """Профиль высот вдоль линии.

latlon - точки (n, 2). distance - расстояние от начала по карте, м.
height - высоты, м. flat и ground - длина по карте и по рельефу.
low, high - наименьшая и наибольшая высота. gain, loss - набор
и потеря высоты. mean_slope - средний уклон, max_slope - наибольший,
в долях (0.1 - 10 %). window - длина отрезка для уклонов, м.
"""

# Единицы длины и площади: код, множитель от метров или квадратных
# метров. Названия для окна - в ui/measure.py, через перевод.
LENGTH_UNITS = (("m", 1.0), ("km", 1000.0), ("mi", 1609.344),
                ("nmi", 1852.0))
AREA_UNITS = (("m2", 1.0), ("ha", 1.0e4), ("km2", 1.0e6),
              ("mi2", 1609.344 ** 2))


def destination(lat, lon, bearing, distance):
    """Точка на расстоянии distance метров по азимуту bearing, сфера.

    Для проверок и грубых построений. Точная окружность круга строится
    на эллипсоиде в ui/measure.py.
    """
    phi = math.radians(lat)
    lam = math.radians(lon)
    theta = math.radians(bearing)
    delta = distance / A
    sin_phi = math.sin(phi) * math.cos(delta) \
        + math.cos(phi) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi)))
    lam2 = lam + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi),
        math.cos(delta) - math.sin(phi) * sin_phi)
    lon2 = (math.degrees(lam2) + 180.0) % 360.0 - 180.0
    return math.degrees(phi2), lon2


def convert(value, unit, units):
    """Величина в метрах или кв. метрах в единицах unit из units."""
    return value / dict(units)[unit]


def number(value):
    """Число для окна.

    От 1 до 1000 - две цифры после точки. От 1000 - одна цифра, тысячи
    разделены пробелом. Меньше 1 - три значащие цифры.
    """
    if value >= 1000.0:
        return "{:,.1f}".format(value).replace(",", " ")
    if value >= 1.0:
        return "{:.2f}".format(value)
    return "{:.3g}".format(value)


def pixel_size(lat, level=HEIGHT_LEVEL):
    """Размер пикселя тайла высот уровня level на широте lat, м."""
    return 2.0 * math.pi * A * math.cos(math.radians(lat)) \
        / (TILE_PIXELS * (1 << level))


def sphere_length(points):
    """Длина ломаной по дугам большого круга на сфере радиуса A, м."""
    pts = np.radians(np.asarray(points, dtype=np.float64).reshape(-1, 2))
    if len(pts) < 2:
        return 0.0
    lat, lon = pts[:, 0], pts[:, 1]
    cos_d = np.sin(lat[:-1]) * np.sin(lat[1:]) \
        + np.cos(lat[:-1]) * np.cos(lat[1:]) * np.cos(lon[1:] - lon[:-1])
    return float(np.arccos(np.clip(cos_d, -1.0, 1.0)).sum() * A)


def sample_line(points, limit=PROFILE_POINTS):
    """Точки вдоль линии для профиля, (n, 2).

    Шаг - пиксель самого точного уровня высот на средней широте,
    при длинной линии больше, чтобы точек было не больше limit.
    """
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    if len(pts) < 2:
        return pts.copy()
    total = sphere_length(pts)
    step = max(pixel_size(float(pts[:, 0].mean())), total / limit)
    return densify(pts, step=step, max_points=limit)


def height_level(points, limit=PROFILE_POINTS):
    """Уровень тайлов высот, пиксель которого не мельче шага выборки."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 2)
    total = sphere_length(pts)
    lat = float(pts[:, 0].mean()) if len(pts) else 0.0
    step = max(pixel_size(lat), total / limit)
    level = HEIGHT_LEVEL
    while level > 0 and pixel_size(lat, level) < step:
        level -= 1
    return level


def tiles_along(latlon, level):
    """Ключи тайлов высот уровня level под точками, по порядку."""
    keys = []
    seen = set()
    for lat, lon in np.asarray(latlon, dtype=np.float64).reshape(-1, 2):
        x, y = lonlat_to_tile(float(lat), float(lon), level)
        key = (level, x, y)
        if key not in seen:
            seen.add(key)
            keys.append(key)
    return keys


def profile(latlon, heights, window=0.0):
    """Профиль по точкам вдоль линии и их высотам.

    window - длина отрезка для уклонов, м. Уклон в точке - перепад
    до первой точки не ближе window, делённый на расстояние до неё.
    """
    latlon = np.asarray(latlon, dtype=np.float64).reshape(-1, 2)
    heights = np.asarray(heights, dtype=np.float64)
    flat_xyz = geodetic_to_ecef(latlon[:, 0], latlon[:, 1], 0.0)
    ground_xyz = geodetic_to_ecef(latlon[:, 0], latlon[:, 1], heights)
    step = np.linalg.norm(np.diff(flat_xyz, axis=0), axis=1)
    distance = np.concatenate([[0.0], np.cumsum(step)])
    ground = float(np.linalg.norm(np.diff(ground_xyz, axis=0),
                                  axis=1).sum())
    rise = np.diff(heights)
    count = len(distance)
    index = np.arange(count)
    ahead = np.maximum(np.searchsorted(distance, distance + window), index + 1)
    valid = ahead < count
    run = distance[ahead[valid]] - distance[index[valid]]
    drop = np.abs(heights[ahead[valid]] - heights[index[valid]])
    slopes = drop[run > 0.0] / run[run > 0.0]
    flat = float(distance[-1]) if len(distance) else 0.0
    return Profile(
        latlon, distance, heights, flat, ground,
        float(heights.min()) if len(heights) else 0.0,
        float(heights.max()) if len(heights) else 0.0,
        float(rise[rise > 0].sum()), float(-rise[rise < 0].sum()),
        float(slopes.mean()) if len(slopes) else 0.0,
        float(slopes.max()) if len(slopes) else 0.0, float(window))


def ground_length(points, heights_at, limit=PROFILE_POINTS):
    """Длина по рельефу ломаной points, м. heights_at - настоящие
    высоты массива точек (широты, долготы)."""
    latlon = sample_line(points, limit)
    if len(latlon) < 2:
        return 0.0
    return profile(latlon, heights_at(latlon[:, 0], latlon[:, 1])).ground


def _ecef3(points):
    """Точки (широта, долгота, высота над эллипсоидом) в ECEF, (N, 3)."""
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    return geodetic_to_ecef(pts[:, 0], pts[:, 1], pts[:, 2])


def chord_length(points, closed=False):
    """Длина 3D-пути, м: сумма прямых отрезков в пространстве.

    points - (широта, долгота, высота над эллипсоидом). Отрезки идут
    по прямой между точками, а не по поверхности, как у 3D-пути,
    поставленного на крыши и склоны. closed - замкнуть на первую точку.
    """
    xyz = _ecef3(points)
    if len(xyz) < 2:
        return 0.0
    if closed:
        xyz = np.vstack([xyz, xyz[:1]])
    return float(np.linalg.norm(np.diff(xyz, axis=0), axis=1).sum())


def polygon_area_3d(points):
    """Площадь 3D-многоугольника в его плоскости, м².

    points - (широта, долгота, высота над эллипсоидом), без повтора
    первой точки. Площадь - длина векторной площади, половины суммы
    векторных произведений соседних вершин. У плоского многоугольника
    это его площадь при любом наклоне, в том числе у отвесной стены.
    У неплоского - площадь проекции на плоскость, где она наибольшая.
    Точки берутся от их среднего, так числа в пределах размера фигуры.
    """
    xyz = _ecef3(points)
    if len(xyz) < 3:
        return 0.0
    rel = xyz - xyz.mean(axis=0)
    vector = np.cross(rel, np.roll(rel, -1, axis=0)).sum(axis=0)
    return float(0.5 * np.linalg.norm(vector))


def bearing(lat1, lon1, lat2, lon2):
    """Начальный азимут с севера по часовой, градусы 0-360, сфера.

    Для точного курса на эллипсоиде окно берёт QgsDistanceArea, эта
    функция - для проверок.
    """
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) \
        * math.cos(dl)
    return math.degrees(math.atan2(y, x)) % 360.0


def nearest_vertex(pixels, front, px, py, radius):
    """Номер точки, ближайшей к пикселю (px, py) не дальше radius, или
    None. pixels - точки на экране (n, 2), front - перед камерой ли."""
    pixels = np.asarray(pixels, dtype=np.float64).reshape(-1, 2)
    if not len(pixels):
        return None
    d = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
    d[~np.asarray(front, dtype=bool)] = np.inf
    best = int(np.argmin(d))
    return best if d[best] <= radius else None


def segment_midpoints(points, closed=False):
    """Середины отрезков ломаной по дуге большого круга, (широта,
    долгота). closed - и отрезок от последней точки к первой."""
    pts = [tuple(p) for p in points]
    pairs = list(zip(pts, pts[1:]))
    if closed and len(pts) >= 3:
        pairs.append((pts[-1], pts[0]))
    out = []
    for a, b in pairs:
        # Середина хорды лежит под поверхностью, её геодезические широта
        # и долгота - середина дуги. Направление из центра Земли дало бы
        # геоцентрическую широту, она расходится с геодезической до 0.19°.
        middle = 0.5 * (geodetic_to_ecef(*a, 0.0) + geodetic_to_ecef(*b, 0.0))
        lat, lon, _ = ecef_to_geodetic(middle)
        out.append((float(lat), float(lon)))
    return out
