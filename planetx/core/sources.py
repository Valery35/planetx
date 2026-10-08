# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Источники данных: адреса по умолчанию и свои адреса рельефа
и векторной основы. Расчёт без Qt.

Окно «Источники данных» - решение автора от 30 сентября 2026 года,
состав утверждён 5 октября 2026 года. Свой адрес можно поставить там,
где формат общий: рельеф - шаблон тайлов {z}/{x}/{y} в записи Terrarium
или Mapbox Terrain-RGB, векторная основа - TileJSON в схеме
OpenMapTiles. Выбор хранится в настройках QGIS, пустое значение -
адрес по умолчанию.
"""

TERRAIN_URL = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
               "{z}/{x}/{y}.png")
VECTOR_TILEJSON = "https://tiles.openfreemap.org/planet"
ENCODINGS = ("terrarium", "mapbox")

PREFIX = "PlanetX/sources/"
TERRAIN_KEY = PREFIX + "terrain_url"
ENCODING_KEY = PREFIX + "terrain_encoding"
TERRAIN_CREDIT_KEY = PREFIX + "terrain_attribution"
VECTOR_KEY = PREFIX + "vector_tilejson"
VECTOR_CREDIT_KEY = PREFIX + "vector_attribution"
# Сервис маршрутов OSRM: шаблон адреса и флажок «через сервис».
ROUTER_KEY = PREFIX + "router_url"
ROUTER_ON_KEY = PREFIX + "router_on"


def template_ok(url):
    """Годится ли адрес шаблоном тайлов: http(s) или file с {z}, {x},
    {y}."""
    url = (url or "").strip()
    return url.startswith(("http://", "https://", "file:")) \
        and all(part in url for part in ("{z}", "{x}", "{y}"))


def tilejson_ok(url):
    """Годится ли адрес TileJSON: http(s) или file."""
    return (url or "").strip().startswith(("http://", "https://", "file:"))


def terrain(url, encoding):
    """Адрес и запись высот рельефа по настройкам: пустой или
    негодный адрес - адрес по умолчанию с Terrarium."""
    url = (url or "").strip()
    if not template_ok(url):
        return TERRAIN_URL, "terrarium"
    return url, encoding if encoding in ENCODINGS else "terrarium"


def vector(url):
    """Адрес TileJSON векторной основы по настройкам."""
    url = (url or "").strip()
    return url if tilejson_ok(url) else VECTOR_TILEJSON


def router(url):
    """Шаблон адреса сервиса маршрутов по настройкам: пустой или
    негодный - сервер FOSSGIS."""
    try:  # внутри плагина QGIS
        from . import routing
    except ImportError:  # headless-тесты
        import routing
    url = (url or "").strip()
    return url if routing.router_ok(url) else routing.ROUTER_URL


def tile_probe(template, z=0, x=0, y=0):
    """Адрес одного тайла шаблона - для проверки доступности."""
    return template.replace("{z}", str(z)).replace("{x}", str(x)) \
        .replace("{y}", str(y))
