# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тела глобуса: Земля, Марс, Луна. Данные без Qt.

Размеры тела лежат в core/ellipsoid.py. Здесь - снимки тела, воздух,
домашняя точка и то, какие земные функции у тела есть. Снимки Марса
и Луны - тайлы OpenPlanetaryMap в Web Mercator, как у земной
подложки. Марс - цветная мозаика Viking MDIM2.1 (NASA, USGS), тайлы
в разметке TMS до уровня 7, около 650 м на пиксель. Луна - альбедо
с отмывкой по рельефу LOLA (USGS), тоже TMS, до уровня 6, около
670 м на пиксель. Уровни проверены запросами 30 сентября 2026 года.
Разметку Луны показала мозаика уровня 2 1 октября 2026 года: в порядке
XYZ ряды не сходятся по краям, в порядке TMS Море Кризисов стоит
на 17° с. ш., 59° в. д. Высот
Марса и Луны тайлами нет, у них рельеф выключен.

Воздух задаётся множителем рассеяния к земному по каналам RGB. У Марса
пыльный воздух рассеивает красный сильнее синего, у Луны воздуха нет.
Земное рассеяние в синем вшестеро больше, чем в красном, поэтому
множитель Марса в синем мал: при (0.9, 0.55, 0.25) гало выходило
белёсо-голубым. Цвет подобран на снимке, его утверждает автор.
"""
try:  # внутри плагина QGIS
    from .ellipsoid import EARTH, MARS, MOON
except ImportError:  # headless-тесты
    from ellipsoid import EARTH, MARS, MOON

MARS_VIKING = ("https://s3-eu-west-1.amazonaws.com/whereonmars.cartodb.net/"
               "viking_mdim21_global/{z}/{x}/{-y}.png")
MOON_ALBEDO = ("https://s3.amazonaws.com/opmbuilder/301_moon/tiles/w/"
               "hillshaded-albedo/{z}/{x}/{-y}.png")


class Planet:
    """Тело глобуса.

    body - размеры из core.ellipsoid. imagery - (название, адрес
    с {z}, {x}, {y} или {-y}, предельный уровень, подпись, ссылка).
    air - множитель рассеяния воздуха по R, G, B к земному, None -
    воздуха нет. home - (широта, долгота, расстояние) начального вида.
    earth - есть ли земные функции: поиск, векторная основа, здания,
    облака, температура, солнце, треки, слои проекта, координаты UTM.
    """

    def __init__(self, body, imagery, air, home, earth=False):
        self.body = body
        self.key = body.key
        self.imagery = imagery
        self.air = air
        self.home = home
        self.earth = earth


EARTH_PLANET = Planet(EARTH, None, (1.0, 1.0, 1.0),
                      (58.0105, 56.2294, 2.0e7), earth=True)
MARS_PLANET = Planet(
    MARS,
    ("Mars Viking MDIM2.1", MARS_VIKING, 7,
     "NASA, USGS, Viking MDIM2.1, OpenPlanetaryMap",
     "https://www.openplanetary.org/opm-basemaps/"
     "global-viking-mdim2-1-colorized-mosaic"),
    (1.2, 0.3, 0.07),
    (18.65, -133.8, 1.2e7))  # Олимп
MOON_PLANET = Planet(
    MOON,
    ("Moon LOLA hillshaded albedo", MOON_ALBEDO, 6,
     "USGS, LRO LOLA, OpenPlanetaryMap",
     "https://github.com/openplanetary/opm/wiki/OPM-Basemaps"),
    None,
    (0.674, 23.473, 6.0e6))  # Море Спокойствия, место посадки Аполлона-11
PLANETS = (EARTH_PLANET, MARS_PLANET, MOON_PLANET)


def planet_by_key(key):
    """Тело по ключу, неизвестный ключ - Земля."""
    for planet in PLANETS:
        if planet.key == key:
            return planet
    return EARTH_PLANET
