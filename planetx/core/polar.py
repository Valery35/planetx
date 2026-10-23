# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Полярные шапки снимком. Модуль не знает про Qt.

Web Mercator кончается на широте MAX_LAT (85.05°), выше глобус рисует
шапку. До 23 октября 2026 года шапка красилась одним цветом края тайла
0/0/0, и середина Антарктиды на снимках была синей. Решение автора того
же дня - шапки снимками полярных служб Esri: Arctic Imagery (EPSG:5936,
стереографическая проекция с центром на долготе -150°, масштаб 0.994,
сдвиг 2 000 000 м) и Antarctic Imagery (EPSG:3031, стандартная
параллель -71°). Обе - снимки Earthstar Geographics на условиях Esri,
как World Imagery.

Шапка - одна текстура на полюс: мозаика тайлов уровня LEVEL под
квадратом вокруг полюса (layout, mosaic), вершины сетки шапки получают
координаты в этой мозаике (cap_uv). Формулы проекций - Snyder, «Map
Projections - A Working Manual», 1987, полярная стереографическая на
эллипсоиде. Сверка с GDAL 3.13 - тест test_polar.
"""
import math

import numpy as np

A = 6378137.0
F = 1.0 / 298.257223563
E = math.sqrt(F * (2.0 - F))
MAX_LAT = 85.0511287798066
RES0 = 238810.813354  # м на пиксель уровня 0 обеих служб
SIDE = 256
# Уровень 8 - 933 м на пиксель, 36 тайлов на полюс. Шапку видно
# издалека, у самого полюса снимок размыт - выбор помощника.
LEVEL = 8
MARGIN = 1.02  # запас квадрата мозаики за краем шапки
URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/Polar/{}/"
       "MapServer/tile/{{z}}/{{y}}/{{x}}")
# north: служба, начало сетки тайлов (x, y), центральная долгота,
# масштаб или стандартная параллель, сдвиг.
SERVICES = {
    True: {"name": "Arctic_Imagery", "origin": (-28567784.109255,
                                                 32567784.109255),
           "lon0": -150.0, "k0": 0.994, "lat_ts": None,
           "shift": (2000000.0, 2000000.0)},
    False: {"name": "Antarctic_Imagery", "origin": (-33699550.99203,
                                                     33699551.01703),
            "lon0": 0.0, "k0": None, "lat_ts": -71.0, "shift": (0.0, 0.0)},
}
CREDIT = "Earthstar Geographics, Esri"
TERMS = "https://www.esri.com/en-us/legal/terms/full-master-agreement"


def _t(phi):
    """t Снайдера (15-9) для широты phi в радианах, полюс - север."""
    s = np.sin(phi)
    return np.tan(np.pi / 4 - phi / 2) / ((1 - E * s) / (1 + E * s)) \
        ** (E / 2)


def project(lat, lon, north):
    """Широта и долгота в метрах проекции службы полюса north."""
    srv = SERVICES[north]
    lat = np.asarray(lat, dtype=np.float64)
    lon = np.asarray(lon, dtype=np.float64)
    sign = 1.0 if north else -1.0
    t = _t(np.radians(sign * lat))
    if srv["k0"] is not None:
        rho = 2 * A * srv["k0"] * t / math.sqrt(
            (1 + E) ** (1 + E) * (1 - E) ** (1 - E))
    else:
        phc = math.radians(abs(srv["lat_ts"]))
        mc = math.cos(phc) / math.sqrt(1 - (E * math.sin(phc)) ** 2)
        rho = A * mc * t / _t(phc)
    turn = np.radians(lon - srv["lon0"])
    fx, fy = srv["shift"]
    x = fx + rho * np.sin(turn)
    y = fy - sign * rho * np.cos(turn)
    return x, y


class Layout:
    """Мозаика шапки: тайлы col0..col1, row0..row1 уровня level,
    левый верхний угол (x0, y0) и сторона в метрах (width, height)."""

    __slots__ = ("north", "level", "col0", "col1", "row0", "row1", "x0",
                 "y0", "width", "height")

    def __init__(self, north, level=LEVEL):
        srv = SERVICES[north]
        cx, cy = project(90.0 if north else -90.0, 0.0, north)
        ex, ey = project(MAX_LAT if north else -MAX_LAT, 0.0, north)
        half = math.hypot(float(ex - cx), float(ey - cy)) * MARGIN
        span = RES0 / (1 << level) * SIDE
        ox, oy = srv["origin"]
        self.north = north
        self.level = level
        self.col0 = int(math.floor((cx - half - ox) / span))
        self.col1 = int(math.floor((cx + half - ox) / span))
        self.row0 = int(math.floor((oy - (cy + half)) / span))
        self.row1 = int(math.floor((oy - (cy - half)) / span))
        self.x0 = ox + self.col0 * span
        self.y0 = oy - self.row0 * span
        self.width = (self.col1 - self.col0 + 1) * span
        self.height = (self.row1 - self.row0 + 1) * span

    def tiles(self):
        """(ряд, столбец, адрес) тайлов мозаики."""
        url = URL.format(SERVICES[self.north]["name"])
        return [(row, col, url.replace("{z}", str(self.level))
                 .replace("{y}", str(row)).replace("{x}", str(col)))
                for row in range(self.row0, self.row1 + 1)
                for col in range(self.col0, self.col1 + 1)]

    def uv(self, lat, lon):
        """Координаты в мозаике, v = 0 у верхнего края."""
        x, y = project(lat, lon, self.north)
        return (x - self.x0) / self.width, (self.y0 - y) / self.height

    def mosaic(self, images):
        """Картинка RGBA из тайлов {(ряд, столбец): массив 256×256×4}.
        Тайла нет - тёмно-серый, как заглушка снимка."""
        rows = self.row1 - self.row0 + 1
        cols = self.col1 - self.col0 + 1
        out = np.full((rows * SIDE, cols * SIDE, 4), 40, dtype=np.uint8)
        out[:, :, 3] = 255
        for (row, col), image in images.items():
            if image is None or image.shape[:2] != (SIDE, SIDE):
                continue
            r, c = (row - self.row0) * SIDE, (col - self.col0) * SIDE
            out[r:r + SIDE, c:c + SIDE] = image[:, :, :4]
        return out


def needed(lat, altitude):
    """Полюса, шапку которых видно: глаз выше 2000 км видит оба, ближе -
    тот, к которому ближе широта точки взгляда."""
    if altitude > 2.0e6:
        return (True, False)
    if lat > 55.0:
        return (True,)
    if lat < -55.0:
        return (False,)
    return ()
