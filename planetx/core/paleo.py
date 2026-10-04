# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Палеогеография: карты Земли в прошлом по PaleoDEM PALEOMAP.

Источник - Scotese & Wright 2018, PALEOMAP Paleodigital Elevation
Models, сетки высот и глубин 0.1° на возрасты AGES, CC BY 4.0. Выбран
автором 5 октября 2026 года вместо масок суши службы GPlates: маска
всей Земли раскодировалась и грузилась в видеокарту целиком, и вид
вставал на каждом возрасте. Карта возраста - тайлы JPEG Web Mercator
с раскраской высот и отмывкой, их нарезает tools/build_paleo.py в
хранилище planetx-terrain. Окно ставит карту возраста подложкой.
Расчёт без Qt: возрасты, адрес тайлов, название периода.
"""
import math

import numpy as np

MAX_AGE = 540  # млн лет, охват набора
# Возрасты карт набора 6 минут, млн лет: 109 сеток через 5 млн лет.
AGES = tuple(range(0, MAX_AGE + 1, 5))
MAX_LEVEL = 4  # уровень тайлов, пиксель около 0.09° у экватора
TILE_URL = ("https://raw.githubusercontent.com/Valery35/planetx-terrain/"
            "main/paleo/paleomap/{age}/{z}/{x}/{y}.jpg")
ATTRIBUTION = ("Paleogeography: PALEOMAP PaleoDEM, Scotese & Wright 2018, "
               "CC BY 4.0", "https://doi.org/10.5281/zenodo.5460860")
# Нижние границы периодов, млн лет, шкала ICS.
PERIODS = ((2.58, "quaternary"), (23.03, "neogene"), (66.0, "paleogene"),
           (145.0, "cretaceous"), (201.4, "jurassic"), (251.9, "triassic"),
           (298.9, "permian"), (358.9, "carboniferous"),
           (419.2, "devonian"), (443.8, "silurian"), (485.4, "ordovician"),
           (538.8, "cambrian"))
PRECAMBRIAN = "precambrian"
# Раскраска высот: отметка в метрах и цвет. Ниже нуля - море, от светлого
# шельфа к тёмной глубине, выше - суша от низменности к снегу вершин.
# Цвета подобрал помощник, утверждает автор.
COLOR_STOPS = ((-9000.0, (8, 28, 66)), (-6000.0, (16, 48, 102)),
               (-4000.0, (28, 72, 136)), (-2000.0, (48, 108, 168)),
               (-200.0, (92, 160, 200)), (-0.5, (138, 196, 222)),
               (0.0, (96, 140, 82)), (300.0, (132, 162, 96)),
               (1000.0, (186, 176, 118)), (2000.0, (166, 132, 94)),
               (3500.0, (146, 118, 108)), (5000.0, (236, 236, 236)))
SUN_AZIMUTH = 315.0  # градусов, свет с северо-запада
SUN_ALTITUDE = 45.0  # градусов над горизонтом
# Подъём отмывки: на сетке 11 км уклоны малы, без подъёма горы плоские.
# У моря подъём меньше, дно не спорит с сушей.
LAND_RELIEF = 30.0
SEA_RELIEF = 8.0


def colors(heights):
    """Цвет высот: массив (..., 3) uint8 по COLOR_STOPS."""
    z = np.asarray(heights, dtype=np.float64)
    marks = np.array([stop[0] for stop in COLOR_STOPS])
    table = np.array([stop[1] for stop in COLOR_STOPS], dtype=np.float64)
    out = np.empty(z.shape + (3,))
    for channel in range(3):
        out[..., channel] = np.interp(z, marks, table[:, channel])
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)


def hillshade(heights, step, radius=6371008.8):
    """Отмывка сетки высот через step градусов, север в строке 0:
    множитель яркости, на равнине около 1."""
    z = np.asarray(heights, dtype=np.float64)
    rows = z.shape[0]
    lat = 90.0 - (np.arange(rows) + 0.5) * 180.0 / rows
    dy = math.radians(step) * radius
    dx = np.maximum(np.cos(np.radians(lat)), 0.01)[:, None] * dy
    relief = np.where(z < 0.0, SEA_RELIEF, LAND_RELIEF)
    # Долгота замкнута, края сетки по широте повторяют соседа.
    east = (np.roll(z, -1, axis=1) - np.roll(z, 1, axis=1)) / (2.0 * dx)
    north = np.empty_like(z)
    north[1:-1] = (z[:-2] - z[2:]) / (2.0 * dy)
    north[0] = north[1]
    north[-1] = north[-2]
    east *= relief
    north *= relief
    azimuth = math.radians(SUN_AZIMUTH)
    altitude = math.radians(SUN_ALTITUDE)
    sun = np.array([math.sin(azimuth) * math.cos(altitude),
                    math.cos(azimuth) * math.cos(altitude),
                    math.sin(altitude)])
    length = np.sqrt(east * east + north * north + 1.0)
    light = (-east * sun[0] - north * sun[1] + sun[2]) / length
    return np.clip(light / sun[2], 0.35, 1.4)


def picture(heights, step):
    """Карта возраста: цвет высот с отмывкой, массив (..., 3) uint8."""
    shade = hillshade(heights, step)[..., None]
    return np.clip(np.rint(colors(heights) * shade), 0, 255).astype(
        np.uint8)


def period(age):
    """Ключ периода для возраста age млн лет."""
    for base, key in PERIODS:
        if age < base:
            return key
    return PRECAMBRIAN


def nearest(age, ages=None):
    """Ближайший к age возраст из набора."""
    ages = ages or AGES
    return min(ages, key=lambda value: (abs(value - age), value))
