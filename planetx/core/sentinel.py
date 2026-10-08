# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки Sentinel-2 в точке: каталог сцен и выбор дня. Расчёт без Qt.

Просьба автора от 9 октября 2026 года - каталог s2-stac-geoparquet
(Taylor Geospatial) в меню на глобусе, снимок - слоем проекта QGIS.
Каталог - зеркало индекса Earth Search (Element 84) сцен Sentinel-2
Collection 1 L2A в файлах GeoParquet на source.coop, по файлу на год
(items.parquet) и хвост по месяцам текущего года (live-MM.parquet).
Строки внутри года отсортированы по тайлу MGRS и времени, GDAL читает
только нужные группы строк диапазонными запросами. Сама сцена -
файлы Cloud-Optimized GeoTIFF Element 84 на открытом хранилище AWS,
true color - ресурс visual, 10 м.

Тайл Sentinel-2 - зона UTM двумя цифрами, полоса и квадрат 100 км
MGRS, например 40VDK у Перми. Тайлы перекрываются, точка у края лежит
в двух-трёх тайлах, берётся тот, в котором она по сетке MGRS.

Модуль Qt не знает.
"""
import json
from collections import namedtuple

try:  # внутри плагина QGIS
    from .coords import to_mgrs
except ImportError:  # headless-тесты
    from coords import to_mgrs

CATALOG = ("https://data.source.coop/tge-labs/s2-stac-geoparquet/"
           "sentinel-2-c1-l2a/")
TERMS = "https://github.com/taylor-geospatial/s2-stac-geoparquet"
FIRST_YEAR = 2015
FIELDS = ("id", "datetime", "eo:cloud_cover", "thumbnail_url", "assets")
ATTRIBUTION = "Copernicus Sentinel-2, ESA, Element 84"

Scene = namedtuple("Scene", "id when cloud thumbnail visual tile")
Scene.__doc__ = """Сцена Sentinel-2: номер, время UTC строкой
«ГГГГ-ММ-ДД ЧЧ:ММ», облачность в процентах, адрес превью JPEG, адрес
true color COG, тайл MGRS."""


def tile_of(lat, lon):
    """Тайл Sentinel-2 точки: «40VDK». Вне зон UTM - None."""
    text = to_mgrs(lat, lon, 1)
    if text is None:
        return None
    zone_band, square = text.split()[:2]
    return zone_band[:-1].zfill(2) + zone_band[-1] + square


def year_files(year, current_year, current_month):
    """Адреса файлов года: годовой и, для текущего года, хвост по
    месяцам до текущего. Файла хвоста может не быть, его отсутствие -
    не ошибка."""
    base = CATALOG + "year={}/".format(int(year))
    files = [base + "items.parquet"]
    if int(year) == int(current_year):
        files += [base + "live-{:02d}.parquet".format(m)
                  for m in range(1, int(current_month) + 1)]
    return files


def tile_filter(tile):
    """Отбор строк тайла для OGR: имя столбца в кавычках, тайл -
    только буквы и цифры."""
    if not tile or not str(tile).isalnum():
        raise ValueError("bad tile")
    return "\"_tile\" = '{}'".format(tile)


def scene(row, tile):
    """Сцена из строки каталога: словарь с полями FIELDS. Строка без
    ресурса visual - None."""
    try:
        assets = json.loads(row.get("assets") or "{}")
    except ValueError:
        return None
    visual = (assets.get("visual") or {}).get("href")
    if not visual:
        return None
    when = str(row.get("datetime") or "")
    when = when.replace("/", "-")[:16]
    cloud = row.get("eo:cloud_cover")
    return Scene(str(row.get("id") or ""), when,
                 float(cloud) if cloud is not None else 100.0,
                 row.get("thumbnail_url") or
                 (assets.get("thumbnail") or {}).get("href") or "",
                 visual, tile)


def choose(scenes, max_cloud):
    """Сцены не облачнее max_cloud процентов, новые сверху, без
    повторов номера (сцена хвоста повторяет сцену года при слиянии)."""
    seen = set()
    out = []
    for s in sorted(scenes, key=lambda s: s.when, reverse=True):
        if s.id in seen or s.cloud > max_cloud:
            continue
        seen.add(s.id)
        out.append(s)
    return out


def layer_name(s):
    """Название слоя проекта: «Sentinel-2 40VDK 2025-07-14, 3 %» -
    тайл, день и облачность."""
    return "Sentinel-2 {} {}, {:.0f} %".format(s.tile, s.when[:10], s.cloud)
