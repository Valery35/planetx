# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложения тайлов поверх подложки. Без Qt.

Прозрачные картинки XYZ - морские знаки, пешие и велосипедные
маршруты. Список - по модулю
basemaps RustGIS, просьба автора от 18 октября 2026 года «делай».
Свободного текстурного блока в шейдере тайла нет, поэтому наложение -
слой тайлов XYZ QGIS в картинке наложения слоёв (ui/globe/layers.py,
_overlay_stack), как подводные кабели. Включать можно несколько сразу.

Адреса проверены тайлом у Перми (морские знаки - у Роттердама)
18 октября 2026 года. OpenRailwayMap не взят, решение автора того же
дня - железные дороги уже есть строкой векторной основы, а правила
OpenRailwayMap требуют свой User-Agent программы и разрешают
блокировать коммерческие проекты. Подписи и дороги Esri тоже не взяты -
они плоско в картинке повторяют надписи и линии векторной основы.
Условия - doc/SOURCES.md.
"""
from collections import namedtuple

Overlay = namedtuple("Overlay", "key url max_level attribution terms")
Overlay.__doc__ = """Наложение: ключ строки «Слоёв», шаблон адреса XYZ,
предельный уровень, подпись, ссылка на условия."""

WAYMARKED_TERMS = "https://hiking.waymarkedtrails.org/#help-legal"

OVERLAYS = {o.key: o for o in (
    Overlay("sea_marks",
            "https://tiles.openseamap.org/seamark/{z}/{x}/{y}.png", 18,
            "© OpenSeaMap contributors", "https://openseamap.org/"),
    Overlay("hiking",
            "https://tile.waymarkedtrails.org/hiking/{z}/{x}/{y}.png", 18,
            "© OpenStreetMap contributors, © waymarkedtrails.org (CC-BY-SA)",
            WAYMARKED_TERMS),
    Overlay("cycling",
            "https://tile.waymarkedtrails.org/cycling/{z}/{x}/{y}.png", 18,
            "© OpenStreetMap contributors, © waymarkedtrails.org (CC-BY-SA)",
            WAYMARKED_TERMS),
)}
KEYS = tuple(OVERLAYS)


def layer_source(key):
    """Строка источника слоя XYZ поставщика wms QGIS."""
    overlay = OVERLAYS[key]
    return "type=xyz&url={}&zmin=0&zmax={}".format(
        overlay.url.replace("&", "%26"), overlay.max_level)
