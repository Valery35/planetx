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
на 17° с. ш., 59° в. д.

Воздух задаётся множителем рассеяния к земному по каналам RGB. У Марса
пыльный воздух рассеивает красный сильнее синего, у Луны воздуха нет.
Земное рассеяние в синем вшестеро больше, чем в красном, поэтому
множитель Марса в синем мал: при (0.9, 0.55, 0.25) гало выходило
белёсо-голубым. Цвет подобран на снимке, его утверждает автор.
"""
try:  # внутри плагина QGIS
    from .ellipsoid import EARTH, MARS, MOON, body_by_key
except ImportError:  # headless-тесты
    from ellipsoid import EARTH, MARS, MOON, body_by_key

MARS_VIKING = ("https://s3-eu-west-1.amazonaws.com/whereonmars.cartodb.net/"
               "viking_mdim21_global/{z}/{x}/{-y}.png")
MOON_ALBEDO = ("https://s3.amazonaws.com/opmbuilder/301_moon/tiles/w/"
               "hillshaded-albedo/{z}/{x}/{-y}.png")
# Тайлы высот уровней 0-5 папками в хранилище planetx-terrain,
# по одному тайлу, как земной Terrarium. Собирает их
# tools/build_body_terrain.py из сеток PDS: MOLA MEGDR 32 точки
# на градус для Марса, LOLA GDR 64 точки на градус для Луны.
TERRAIN_TILES = ("https://raw.githubusercontent.com/Valery35/"
                 "planetx-terrain/main/%s/{z}/{x}/{y}.png")
TERRAIN_LEVEL = 5


class Planet:
    """Тело глобуса.

    body - размеры из core.ellipsoid. imagery - (название, адрес
    с {z}, {x}, {y} или {-y}, предельный уровень, подпись, ссылка).
    air - множитель рассеяния воздуха по R, G, B к земному, None -
    воздуха нет. home - (широта, долгота, расстояние) начального вида.
    earth - есть ли земные функции: поиск, векторная основа, здания,
    облака, температура, солнце, треки, слои проекта, координаты UTM.
    terrain - высоты тела: (название, адрес тайлов Terrarium с {z},
    {x}, {y}, предельный уровень, подпись) или None. У Земли высоты
    Terrarium задаёт окно, тайлы Марса и Луны собирает
    tools/build_body_terrain.py.
    """

    def __init__(self, body, imagery, air, home, earth=False,
                 terrain=None):
        self.body = body
        self.key = body.key
        self.imagery = imagery
        self.air = air
        self.home = home
        self.earth = earth
        self.terrain = terrain


EARTH_PLANET = Planet(EARTH, None, (1.0, 1.0, 1.0),
                      (58.0105, 56.2294, 2.0e7), earth=True)
MARS_PLANET = Planet(
    MARS,
    ("Mars Viking MDIM2.1", MARS_VIKING, 7,
     "NASA, USGS, Viking MDIM2.1, OpenPlanetaryMap",
     "https://www.openplanetary.org/opm-basemaps/"
     "global-viking-mdim2-1-colorized-mosaic"),
    (1.2, 0.3, 0.07),
    (18.65, -133.8, 1.2e7),  # Олимп
    terrain=("MOLA MEGDR", TERRAIN_TILES % "mars",
             TERRAIN_LEVEL, "Terrain: NASA MGS MOLA MEGDR"))
MOON_PLANET = Planet(
    MOON,
    ("Moon LOLA hillshaded albedo", MOON_ALBEDO, 6,
     "USGS, LRO LOLA, OpenPlanetaryMap",
     "https://github.com/openplanetary/opm/wiki/OPM-Basemaps"),
    None,
    (0.674, 23.473, 6.0e6),  # Море Спокойствия, посадка Аполлона-11
    terrain=("LOLA GDR", TERRAIN_TILES % "moon",
             TERRAIN_LEVEL, "Terrain: NASA LRO LOLA GDR"))

# Снимки прочих тел - тайлы JPEG из глобальных мозаик USGS Astrogeology
# и NASA Photojournal, общественное достояние. Нарезает их
# tools/build_body_imagery.py, лежат они в хранилище planetx-terrain
# рядом с высотами. Источники выбрал помощник 1 октября 2026 года
# по просьбе автора «бери все планеты», условия - в doc/SOURCES.md.
IMAGERY_TILES = ("https://raw.githubusercontent.com/Valery35/"
                 "planetx-terrain/main/imagery/%s/{z}/{x}/{y}.jpg")
USGS_MAPS = "https://astrogeology.usgs.gov/search"
PHOTOJOURNAL = "https://science.nasa.gov/photojournal/"
# Начальный вид - 3.5 радиуса от точки взгляда, как у Марса и Луны.
HOME_RADII = 3.5
# Ключ тела: название мозаики, уровень, подпись, ссылка, воздух,
# широта и долгота начальной точки. Воздух у Венеры и Титана - плотная
# дымка, цвет подобран помощником на снимке, его утверждает автор.
# Множитель синего мал, как у Марса: земное рассеяние в синем сильнее.
# Южная часть Харона и Тритона аппаратами не снята, начальная точка -
# на снятой стороне.
OTHER = (
    ("mercury", "MESSENGER MDIS MD3 color", 6,
     "NASA, JHU APL, Carnegie Institution, MESSENGER MDIS, USGS",
     USGS_MAPS, None, (30.5, -170.2)),
    ("venus", "Magellan C3-MDIR colorized topography", 5,
     "NASA, JPL, Magellan, USGS", USGS_MAPS, (1.3, 0.55, 0.1),
     (65.2, 3.3)),
    ("jupiter", "Cassini PIA07782", 4,
     "NASA, JPL, Space Science Institute, Cassini", PHOTOJOURNAL, None,
     (0.0, 0.0)),
    ("io", "Galileo SSI and Voyager color merge", 5,
     "NASA, JPL, Galileo SSI, Voyager, USGS", USGS_MAPS, None,
     (0.0, 0.0)),
    ("europa", "Voyager and Galileo SSI", 6,
     "NASA, JPL, Galileo SSI, Voyager, USGS", USGS_MAPS, None,
     (0.0, 0.0)),
    ("ganymede", "Voyager and Galileo SSI color", 5,
     "NASA, JPL, Galileo SSI, Voyager, USGS", USGS_MAPS, None,
     (0.0, 0.0)),
    ("callisto", "Voyager and Galileo SSI", 6,
     "NASA, JPL, Galileo SSI, Voyager, USGS", USGS_MAPS, None,
     (0.0, 0.0)),
    ("mimas", "Cassini PIA17214", 5,
     "NASA, JPL-Caltech, Space Science Institute, Cassini",
     PHOTOJOURNAL, None, (0.0, 0.0)),
    ("enceladus", "Cassini ISS", 5,
     "NASA, JPL, Space Science Institute, Cassini ISS, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("tethys", "Cassini ISS", 5,
     "NASA, JPL, Space Science Institute, Cassini ISS, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("dione", "Cassini ISS and Voyager", 6,
     "NASA, JPL, Space Science Institute, Cassini ISS, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("rhea", "Cassini ISS and Voyager", 5,
     "NASA, JPL, Space Science Institute, DLR, Cassini ISS, USGS",
     USGS_MAPS, None, (0.0, 0.0)),
    ("titan", "Cassini ISS", 4,
     "NASA, JPL-Caltech, Space Science Institute, Cassini ISS, USGS",
     USGS_MAPS, (1.3, 0.4, 0.06), (0.0, 0.0)),
    ("iapetus", "Cassini ISS and Voyager", 5,
     "NASA, JPL, Space Science Institute, Cassini ISS, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("triton", "Voyager 2 color", 5,
     "NASA, JPL, Voyager 2, P. Schenk (LPI), USGS", USGS_MAPS, None,
     (-30.0, 0.0)),
    ("ceres", "Dawn FC", 5,
     "NASA, JPL-Caltech, UCLA, MPS, DLR, IDA, Dawn FC, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("vesta", "Dawn FC HAMO", 6,
     "NASA, JPL-Caltech, UCLA, MPS, DLR, IDA, Dawn FC, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("pluto", "New Horizons LORRI and MVIC", 6,
     "NASA, JHU APL, SwRI, New Horizons, USGS", USGS_MAPS, None,
     (25.0, 175.0)),
    ("charon", "New Horizons LORRI and MVIC", 5,
     "NASA, JHU APL, SwRI, New Horizons, USGS", USGS_MAPS, None,
     (30.0, 0.0)),
)


def _other(key, name, level, credit, link, air, home):
    body = body_by_key(key)
    return Planet(body, (name, IMAGERY_TILES % key, level, credit, link),
                  air, (home[0], home[1], HOME_RADII * body.a))


OTHER_PLANETS = tuple(_other(*row) for row in OTHER)
PLANETS = (EARTH_PLANET, MARS_PLANET, MOON_PLANET) + OTHER_PLANETS
# Меню «Тело»: разделы и ключи тел по порядку.
MENU = (("", ("mercury", "venus", "earth", "moon", "mars")),
        ("jupiter", ("jupiter", "io", "europa", "ganymede", "callisto")),
        ("saturn", ("mimas", "enceladus", "tethys", "dione", "rhea",
                    "titan", "iapetus")),
        ("neptune", ("triton",)),
        ("dwarf", ("ceres", "vesta", "pluto", "charon")))


def planet_by_key(key):
    """Тело по ключу, неизвестный ключ - Земля."""
    for planet in PLANETS:
        if planet.key == key:
            return planet
    return EARTH_PLANET
