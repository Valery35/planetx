# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тела глобуса: Земля, Марс, Луна. Данные без Qt.

Размеры тела лежат в core/ellipsoid.py. Здесь - снимки тела, воздух,
домашняя точка и то, какие земные функции у тела есть. Снимки Марса
и Луны - тайлы Web Mercator в разметке XYZ уровней 0-7 из хранилища
planetx-bodies-imagery, общего с PlanetX Lite, решение автора
от 25 октября 2026 года. Марс - цветная мозаика Viking MDIM2.1 (NASA,
USGS) в тайлах OpenPlanetaryMap без перекодирования, ряды переведены
из TMS в XYZ, около 650 м на пиксель. Луна - мозаика LROC WAC 100 м
(NASA, GSFC, ASU, USGS), серые PNG, около 330 м на пиксель у экватора.
До 1.13.1 снимки брались с серверов OpenPlanetaryMap в разметке TMS,
Луна - альбедо LOLA с отмывкой, 670 м на пиксель.

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

BODY_IMAGERY = ("https://raw.githubusercontent.com/Valery35/"
                "planetx-bodies-imagery/main/%s/{z}/{x}/{y}.png")
# Тайлы высот уровней 0-7 папками в хранилище planetx-bodies-terrain,
# по одному тайлу, как земной Terrarium. Хранилище общее с PlanetX
# Lite, решение автора от 25 октября 2026 года. Нарезает их
# scripts/tiles.py того хранилища из мозаик USGS Astrogeology: MOLA
# 463 м для Марса над ареоидом, LOLA 118 м для Луны над сферой
# 1737.4 км. До 1.13.1 тайлы уровней 0-5 лежали в planetx-terrain.
TERRAIN_TILES = ("https://raw.githubusercontent.com/Valery35/"
                 "planetx-bodies-terrain/main/%s/{z}/{x}/{y}.png")
TERRAIN_LEVEL = 7


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
    ("Mars Viking MDIM2.1", BODY_IMAGERY % "mars", 7,
     "NASA, USGS, Viking MDIM2.1, OpenPlanetaryMap",
     "https://www.openplanetary.org/opm-basemaps/"
     "global-viking-mdim2-1-colorized-mosaic"),
    (1.2, 0.3, 0.07),
    (18.65, -133.8, 1.2e7),  # Олимп
    terrain=("MOLA DEM 463 m", TERRAIN_TILES % "mars",
             TERRAIN_LEVEL, "Terrain: NASA MGS MOLA, USGS"))
MOON_PLANET = Planet(
    MOON,
    ("Moon LROC WAC 100 m", BODY_IMAGERY % "moon", 7,
     "NASA, GSFC, Arizona State University, LRO LROC WAC, USGS",
     "https://astrogeology.usgs.gov/search/map/moon_lro_lroc_wac_"
     "global_morphology_mosaic_100m"),
    None,
    (0.674, 23.473, 6.0e6),  # Море Спокойствия, посадка Аполлона-11
    terrain=("LOLA DEM 118 m", TERRAIN_TILES % "moon",
             TERRAIN_LEVEL, "Terrain: NASA LRO LOLA, USGS"))

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
    ("ceres", "Dawn FC", 5,
     "NASA, JPL-Caltech, UCLA, MPS, DLR, IDA, Dawn FC, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
    ("vesta", "Dawn FC HAMO", 6,
     "NASA, JPL-Caltech, UCLA, MPS, DLR, IDA, Dawn FC, USGS", USGS_MAPS,
     None, (0.0, 0.0)),
)


def _other(key, name, level, credit, link, air, home):
    body = body_by_key(key)
    return Planet(body, (name, IMAGERY_TILES % key, level, credit, link),
                  air, (home[0], home[1], HOME_RADII * body.a))


OTHER_PLANETS = tuple(_other(*row) for row in OTHER)
PLANETS = (EARTH_PLANET, MARS_PLANET, MOON_PLANET) + OTHER_PLANETS
# Меню «Тело»: Земля, Луна и Марс сверху, прочие тела - подменю.
# Пустой заголовок - тела в самом меню после разделителя. Плутона,
# Харона и Тритона нет: 24-33 % их шара аппараты не сняли. Решение
# автора от 1 октября 2026 года - в меню только тела, снятые целиком.
MENU = (("", ("earth",)),
        ("", ("moon", "mars")),
        ("planets", ("mercury", "venus", "jupiter")),
        ("jupiter", ("io", "europa", "ganymede", "callisto")),
        ("saturn", ("mimas", "enceladus", "tethys", "dione", "rhea",
                    "titan", "iapetus")),
        ("asteroids", ("ceres", "vesta")))


def planet_by_key(key):
    """Тело по ключу, неизвестный ключ - Земля."""
    for planet in PLANETS:
        if planet.key == key:
            return planet
    return EARTH_PLANET
