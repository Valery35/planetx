# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек лидара по сети: плитки COPC у точки из каталогов IGN
LiDAR HD (Франция) и USGS 3DEP (США). Расчёт без Qt.

IGN - слой WFS IGNF_LIDAR-HD_METADONNEE:metadata Géoplateforme, у плитки
1 км поле url_npl - файл COPC, без ключа, Licence Ouverte 2.0. USGS 3DEP -
коллекция 3dep-lidar-copc STAC Planetary Computer, файлы в Azure по ключу
SAS без учётной записи, общественное достояние США. Сверено 25 октября
2026 года, doc/SOURCES.md. Файлы читает PDAL частями по HTTP
(ui/pointcloud.py), целиком они не скачиваются.
"""
import json
import math
from collections import namedtuple
from urllib.parse import urlencode

IGN = "ign"
USGS = "3dep"
IGN_WFS = "https://data.geopf.fr/wfs/ows"
IGN_LAYER = "IGNF_LIDAR-HD_METADONNEE:metadata"
PC_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
PC_COLLECTION = "3dep-lidar-copc"
# Ключ SAS хранилища файлов 3DEP: учётная запись и контейнер Azure.
PC_SAS = ("https://planetarycomputer.microsoft.com/api/sas/v1/token/"
          "usgslidareuwest/usgs-3dep-copc")
PC_HOST = "usgslidareuwest.blob.core.windows.net"
CREDITS = {IGN: ("LiDAR HD © IGN, Licence Ouverte 2.0",
                 "https://geoservices.ign.fr/lidarhd"),
           USGS: ("USGS 3DEP, public domain",
                  "https://www.usgs.gov/3d-elevation-program")}
SIDE = 1500.0  # м, сторона участка поиска у точки
MAX_TILES = 4  # плиток у точки в проект
# Сервер IGN 25 октября 2026 года отвечал 429 уже на одном процессе PDAL,
# плитки IGN 1 км и плотные - у точки их две.
SOURCE_TILES = {IGN: 2}
SEARCH_LIMIT = 50  # записей каталога на запрос

Tile = namedtuple("Tile", "source name url box points date")
Tile.__doc__ = """Плитка облака: source - IGN или USGS, url - файл COPC
без ключа, box - (запад, юг, восток, север) в градусах, points -
количество точек, date - дата или год съёмки строкой."""


def box_around(lat, lon, side=SIDE):
    """Квадрат стороны side метров вокруг точки, градусы."""
    half = 0.5 * side / 111320.0
    across = half / max(math.cos(math.radians(lat)), 1e-6)
    return lon - across, lat - half, lon + across, lat + half


def ign_url(box):
    """Запрос WFS плиток IGN в рамке box. В WFS 2.0 у EPSG:4326 порядок
    осей - широта, долгота."""
    west, south, east, north = box
    return IGN_WFS + "?" + urlencode({
        "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature",
        "TYPENAMES": IGN_LAYER, "OUTPUTFORMAT": "application/json",
        "COUNT": str(SEARCH_LIMIT),
        "BBOX": "{:.6f},{:.6f},{:.6f},{:.6f},urn:ogc:def:crs:EPSG::4326"
                .format(south, west, north, east)})


def _ring_box(geometry):
    points = []

    def walk(node):
        if node and isinstance(node[0], (int, float)):
            points.append(node)
        else:
            for part in node or ():
                walk(part)
    walk((geometry or {}).get("coordinates"))
    if not points:
        return None
    lons = [p[0] for p in points]
    lats = [p[1] for p in points]
    return min(lons), min(lats), max(lons), max(lats)


def parse_ign(data):
    """Плитки IGN из ответа WFS GeoJSON."""
    doc = json.loads(data) if isinstance(data, (bytes, str)) else data
    out = []
    for feature in (doc or {}).get("features") or ():
        props = feature.get("properties") or {}
        url = props.get("url_npl") or ""
        box = _ring_box(feature.get("geometry"))
        if not url.endswith(".copc.laz") or box is None:
            continue
        if url.startswith("http://"):
            url = "https://" + url[len("http://"):]
        date = str(props.get("date_debut_acquisition") or "")[:10]
        out.append(Tile(IGN, "LiDAR HD " + str(props.get(
            "coordonnees_nw") or url.rsplit("/", 1)[-1]), url, box,
            int(props.get("nombre_points") or 0), date))
    return out


def pc_body(box):
    """Тело поиска STAC плиток 3DEP в рамке box, словарь JSON."""
    west, south, east, north = box
    ring = [[west, south], [east, south], [east, north], [west, north],
            [west, south]]
    return {"collections": [PC_COLLECTION], "limit": SEARCH_LIMIT,
            "intersects": {"type": "Polygon", "coordinates": [ring]}}


def parse_pc(data):
    """Плитки 3DEP из ответа поиска STAC. Рамка записи - шесть чисел,
    с отметками."""
    doc = json.loads(data) if isinstance(data, (bytes, str)) else data
    out = []
    for item in (doc or {}).get("features") or ():
        href = ((item.get("assets") or {}).get("data") or {}).get("href")
        bbox = item.get("bbox") or []
        if not href or not href.startswith("https://") or len(bbox) < 4:
            continue
        box = (bbox[0], bbox[1], bbox[3], bbox[4]) if len(bbox) == 6 \
            else tuple(bbox[:4])
        props = item.get("properties") or {}
        date = str(props.get("start_datetime") or props.get("datetime")
                   or "")[:4]
        out.append(Tile(USGS, str(item.get("id") or href.rsplit("/", 1)[-1]),
                        href, box, int(props.get("pc:count") or 0), date))
    return out


def needs_key(url):
    """Файлу нужен ключ SAS Planetary Computer."""
    return url.partition("://")[2].split("/")[0].lower() == PC_HOST


def with_key(url, key):
    """Адрес файла с ключом SAS вместо прежнего."""
    base = url.split("?")[0]
    return base + "?" + key if key and needs_key(base) else base


def choose(tiles, lat, lon, limit=MAX_TILES):
    """Плитки у точки: накрывающие точку первыми, затем по расстоянию до
    середины, не больше limit, повторы одного файла - один раз. У 3DEP
    один участок бывает снят несколько раз - остаются все съёмки."""
    def rank(tile):
        west, south, east, north = tile.box
        inside = west <= lon <= east and south <= lat <= north
        x = (0.5 * (west + east) - lon) * math.cos(math.radians(lat))
        y = 0.5 * (south + north) - lat
        return (not inside, x * x + y * y)
    seen = set()
    out = []
    for tile in sorted(tiles, key=rank):
        if tile.url in seen:
            continue
        if sum(t.source == tile.source for t in out) \
                >= SOURCE_TILES.get(tile.source, limit):
            continue
        seen.add(tile.url)
        out.append(tile)
        if len(out) >= limit:
            break
    return out
