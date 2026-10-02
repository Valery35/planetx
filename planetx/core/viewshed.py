# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Видимость из точки по рельефу. Расчёт без Qt.

Шаг 2 плана фазы 3 (doc/PLAN_PHASE3.md), решение автора от 2 октября
2026 года. Образец - «Показать зону видимости» у метки Google Earth.

Из точки наблюдения расходятся лучи по азимутам с равным шагом, вдоль
каждого луча - точки через шаг cell. Высоты берутся массивом функцией
heights(широты, долготы), настоящие, без масштаба вида. Глаз стоит на
высоте observer над рельефом. Точка луча видна, если угол на неё
с поправкой на кривизну тела не ниже наибольшего угла на рельеф перед
ней. Цель поднята на target над рельефом. Кривизна - опускание
d² / (2·R'), R' = R / (1 - k), k - коэффициент рефракции: у Земли
0.13, принятый в геодезии, у тел без плотной атмосферы 0.

Шаг cell и количество лучей подобраны так, чтобы клетка у края круга
была не крупнее cell: лучей не меньше 2πr / cell. Лучей не больше
MAX_RAYS, точек на луче не больше MAX_STEPS.

Результат - видимость по лучам и шагам. Картинка тайла глобуса
(tile_rgba) берёт для каждого пикселя ближайший луч и шаг.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .tiling import lonlat_to_tile
except ImportError:  # headless-тесты
    import ellipsoid
    from tiling import lonlat_to_tile

REFRACTION = 0.13  # коэффициент рефракции Земли
MAX_RAYS = 4096
MAX_STEPS = 1024
STEPS = 500  # шагов на радиус круга, шаг расчёта - радиус / STEPS
MAX_TILES = 64  # тайлов высот под кругом
TILE = 256  # пикселей тайла высот на сторону
VISIBLE = (40, 200, 60)
HIDDEN = (200, 40, 40)
OPACITY = 0.45  # непрозрачность раскраски поверх снимка


def destinations(lat, lon, bearings, distances, radius):
    """Точки по азимутам bearings (градусы, форма (a, 1)) на
    расстояниях distances (метры, форма (1, s)), сфера радиуса radius.
    Возвращает широты и долготы формы (a, s)."""
    phi = math.radians(lat)
    theta = np.radians(bearings)
    delta = np.asarray(distances, dtype=np.float64) / radius
    sin_phi2 = (math.sin(phi) * np.cos(delta)
                + math.cos(phi) * np.sin(delta) * np.cos(theta))
    phi2 = np.arcsin(np.clip(sin_phi2, -1.0, 1.0))
    lam2 = math.radians(lon) + np.arctan2(
        np.sin(theta) * np.sin(delta) * math.cos(phi),
        np.cos(delta) - math.sin(phi) * sin_phi2)
    lon2 = (np.degrees(lam2) + 180.0) % 360.0 - 180.0
    return np.degrees(phi2), lon2


def distance_bearing(lat, lon, lats, lons, radius):
    """Расстояние по дуге (м) и азимут (градусы) от точки к точкам."""
    phi1 = math.radians(lat)
    phi2 = np.radians(lats)
    dlam = np.radians(lons) - math.radians(lon)
    a = (np.sin((phi2 - phi1) / 2.0) ** 2
         + math.cos(phi1) * np.cos(phi2) * np.sin(dlam / 2.0) ** 2)
    dist = 2.0 * radius * np.arcsin(np.sqrt(np.clip(a, 0.0, 1.0)))
    y = np.sin(dlam) * np.cos(phi2)
    x = (math.cos(phi1) * np.sin(phi2)
         - math.sin(phi1) * np.cos(phi2) * np.cos(dlam))
    return dist, np.degrees(np.arctan2(y, x)) % 360.0


def circle_box(lat, lon, radius_m, radius):
    """Широты и долготы рамки круга: (юг, север, запад, восток).
    Рамка через 180° долготы заменяется всем поясом -180..180."""
    dlat = math.degrees(radius_m / radius)
    cos = math.cos(math.radians(min(abs(lat) + dlat, 89.9)))
    dlon = min(180.0, dlat / max(cos, 1e-6))
    west, east = lon - dlon, lon + dlon
    if west < -180.0 or east > 180.0:
        west, east = -180.0, 180.0
    return max(lat - dlat, -90.0), min(lat + dlat, 90.0), west, east


def height_tiles(lat, lon, radius_m, cell, radius, max_level):
    """Уровень и тайлы высот под кругом: (уровень, список ключей).
    Уровень - тот, у которого пиксель не крупнее шага cell, но не глубже
    max_level и не мельче, чем нужно, чтобы тайлов было не больше
    MAX_TILES."""
    ground = 2.0 * math.pi * radius * math.cos(math.radians(lat)) / TILE
    level = int(min(max_level, max(0, math.ceil(math.log2(
        max(ground, 1e-9) / cell)))))
    south, north, west, east = circle_box(lat, lon, radius_m, radius)
    while True:
        x0, y0 = lonlat_to_tile(north, west, level)
        x1, y1 = lonlat_to_tile(south, min(east, 179.999999), level)
        count = (x1 - x0 + 1) * (y1 - y0 + 1)
        if count <= MAX_TILES or level == 0:
            break
        level -= 1
    keys = [(level, x, y) for x in range(x0, x1 + 1)
            for y in range(y0, y1 + 1)]
    return level, keys


def layout(radius_m, cell):
    """Количество лучей и шагов и настоящий шаг для круга radius_m."""
    steps = int(min(MAX_STEPS, max(8, math.ceil(radius_m / cell))))
    step = radius_m / steps
    rays = int(min(MAX_RAYS, max(360, math.ceil(2.0 * math.pi
                                                * radius_m / step))))
    return rays, steps, step


class Viewshed:
    """Видимость из точки: visible - массив (лучи, шаги) bool."""

    def __init__(self, lat, lon, radius_m, step, visible):
        self.lat = lat
        self.lon = lon
        self.radius_m = radius_m
        self.step = step
        self.visible = visible

    @property
    def share(self):
        """Доля видимой площади круга. Шаг j - кольцо площадью
        пропорционально его радиусу."""
        weights = np.arange(1, self.visible.shape[1] + 1, dtype=np.float64)
        return float((self.visible * weights).sum()
                     / (weights.sum() * self.visible.shape[0]))

    def at(self, lats, lons, radius):
        """Видимость в точках: (видно, внутри круга), массивы bool."""
        dist, az = distance_bearing(self.lat, self.lon, lats, lons, radius)
        rays, steps = self.visible.shape
        ray = np.rint(az / 360.0 * rays).astype(np.int64) % rays
        index = np.rint(dist / self.step).astype(np.int64) - 1
        inside = dist <= self.radius_m
        near = index < 0  # клетка самой точки наблюдения
        index = np.clip(index, 0, steps - 1)
        seen = self.visible[ray, index] | near
        return seen & inside, inside


def compute(lat, lon, radius_m, cell, heights, observer=2.0, target=0.0,
            refraction=None, radius=None):
    """Видимость из точки (lat, lon) в круге radius_m метров.

    heights - функция настоящих высот массивов широт и долгот.
    refraction None - REFRACTION у Земли, 0 у других тел. radius -
    радиус тела, по умолчанию текущего (core.ellipsoid).
    """
    radius = radius or ellipsoid.A
    if refraction is None:
        refraction = REFRACTION if ellipsoid.BODY.key == "earth" else 0.0
    rays, steps, step = layout(radius_m, cell)
    bearings = (np.arange(rays) * 360.0 / rays)[:, None]
    dist = (np.arange(1, steps + 1) * step)[None, :]
    lats, lons = destinations(lat, lon, bearings, dist, radius)
    ground = np.asarray(heights(lats.ravel(), lons.ravel()),
                        dtype=np.float64).reshape(lats.shape)
    eye = float(np.asarray(heights(np.array([lat]),
                                   np.array([lon])))[0]) + observer
    drop = dist ** 2 / (2.0 * radius / (1.0 - refraction))
    slope_ground = (ground - drop - eye) / dist
    slope_target = (ground + target - drop - eye) / dist
    # Наибольший угол на рельеф перед точкой: накопленный максимум
    # со сдвигом на шаг, у первой точки впереди ничего нет.
    ahead = np.maximum.accumulate(slope_ground, axis=1)
    before = np.empty_like(ahead)
    before[:, 0] = -np.inf
    before[:, 1:] = ahead[:, :-1]
    return Viewshed(lat, lon, radius_m, step, slope_target >= before)


def tile_rgba(viewshed, lats, lons, radius):
    """Картинка тайла: видимое зелёное, скрытое красное, вне круга
    прозрачно. RGBA uint8 с премноженной альфой."""
    seen, inside = viewshed.at(lats, lons, radius)
    out = np.zeros(lats.shape + (4,), dtype=np.uint8)
    for mask, rgb in ((seen, VISIBLE), (inside & ~seen, HIDDEN)):
        out[mask, :3] = np.rint(np.array(rgb) * OPACITY)
        out[mask, 3] = round(OPACITY * 255)
    return out
