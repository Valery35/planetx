# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горные разработки: контуры по снимкам и шахты и карьеры OSM. Без Qt.

Просьба автора от 11 октября 2026 года - других источников, кроме
USGS, «делай оба»:

- Контуры горных разработок мира, Maus и др. 2022, версия 2 -
  44 929 многоугольников карьеров, отвалов, хвостохранилищ и площадок
  по мозаике Sentinel-2 2019 года, CC BY-SA 4.0. Файл GeoPackage
  24.7 МБ скачивается один раз в профиль QGIS, рисуется в картинке
  тайлов слоем QGIS (ui/window.py).
- Шахты и карьеры OpenStreetMap - man_made=mine и mineshaft,
  landuse=quarry, industrial=mine. Запрос Overpass по тайлам уровня
  ZOOM вокруг точки взгляда, только при глазе ниже MAX_ALTITUDE
  и не больше MAX_TILES тайлов за раз. Тайл просится один раз за сеанс.
  Правила Overpass - разумная частота, свой User-Agent, ODbL.

Точки OSM складываются в core.deposits.Deposits: цвет - та же группа
полезного ископаемого (тег resource или product), так шкала
месторождений годится и для них.
"""
import math

try:  # внутри плагина QGIS
    from . import deposits
except ImportError:  # headless-тесты
    import deposits

POLYGONS_URL = ("https://download.pangaea.de/dataset/942325/files/"
                "global_mining_polygons_v2.gpkg")
POLYGONS_FILE = "global_mining_polygons_v2.gpkg"
POLYGONS_ATTRIBUTION = ("Mining areas: Maus et al. 2022, CC BY-SA 4.0",
                        "https://doi.org/10.1594/PANGAEA.942325")
OSM_QUERY_URL = "https://overpass-api.de/api/interpreter"
# Серверы Overpass по очереди: при отказе запрос идёт на следующий.
# Основной сервер в часы нагрузки отвечает 504, 11 октября 2026 года.
# Запрос - POST с полем data: kumi.systems на GET отвечает 500,
# private.coffee отвечал 500 и на POST, в список не входит.
# Зеркала Overpass: главный сервер первым, выбор - core/mirrors.py.
OSM_SERVERS = (OSM_QUERY_URL,
               "https://overpass.kumi.systems/api/interpreter",
               "https://overpass.private.coffee/api/interpreter")
OSM_ATTRIBUTION = ("Mines: © OpenStreetMap contributors",
                   "https://www.openstreetmap.org/copyright")
OSM_PAGE = "https://www.openstreetmap.org/{}/{}"
ZOOM = 10  # тайл около 39 км у экватора
MAX_TILES = 9
MAX_ALTITUDE = 150000.0  # м, выше глаза шахты OSM не просятся
GAP = 2.0  # с между запросами Overpass
TIMEOUT = 60  # с, предел запроса на сервере Overpass
# Виды объектов OSM: тег, значение, ключ подписи.
KINDS = (("man_made", "mine", "mine"), ("man_made", "mineshaft", "shaft"),
         ("landuse", "quarry", "quarry"), ("industrial", "mine", "mine"))


def tile_of(lat, lon, zoom=ZOOM):
    """Тайл Web Mercator (x, y) уровня zoom под точкой."""
    n = 2 ** zoom
    lat = max(min(lat, 85.0511), -85.0511)
    x = int((lon + 180.0) / 360.0 * n) % n
    rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(rad)) / math.pi) / 2.0 * n)
    return x, min(max(y, 0), n - 1)


def tile_bounds(x, y, zoom=ZOOM):
    """Рамка тайла (юг, запад, север, восток) в градусах."""
    n = 2 ** zoom

    def lat_of(row):
        return math.degrees(math.atan(math.sinh(math.pi
                                                * (1.0 - 2.0 * row / n))))
    return (lat_of(y + 1), x / n * 360.0 - 180.0, lat_of(y),
            (x + 1) / n * 360.0 - 180.0)


def view_tiles(lat, lon, altitude, zoom=ZOOM, limit=MAX_TILES):
    """Тайлы вокруг точки взгляда: ближние первыми, не больше limit.
    Выше MAX_ALTITUDE - ни одного."""
    if altitude > MAX_ALTITUDE:
        return []
    cx, cy = tile_of(lat, lon, zoom)
    n = 2 ** zoom
    reach = 1 if limit <= 9 else 2
    tiles = [((cx + dx) % n, cy + dy)
             for dy in range(-reach, reach + 1)
             for dx in range(-reach, reach + 1)
             if 0 <= cy + dy < n]
    tiles.sort(key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
    return tiles[:limit]


def union(boxes):
    """Общая рамка (юг, запад, север, восток) нескольких тайлов - один
    запрос Overpass вместо запроса на каждый тайл. Тайлы через линию
    перемены дат не объединяются - берётся первый."""
    boxes = list(boxes)
    south = min(b[0] for b in boxes)
    north = max(b[2] for b in boxes)
    west = min(b[1] for b in boxes)
    east = max(b[3] for b in boxes)
    if east - west > 180.0:
        return boxes[0]
    return south, west, north, east


def query(bounds):
    """Текст запроса Overpass QL для рамки (юг, запад, север, восток):
    шахты, рудники и карьеры с серединой и тегами."""
    box = "({:.5f},{:.5f},{:.5f},{:.5f})".format(*bounds)
    parts = "".join('nwr["{}"="{}"]{};'.format(key, value, box)
                    for key, value, _ in KINDS)
    return "[out:json][timeout:{}];({});out center tags;".format(
        TIMEOUT, parts)


def kind_of(tags):
    """Ключ вида объекта OSM или пустая строка."""
    for key, value, name in KINDS:
        if tags.get(key) == value:
            return name
    return ""


def parse(answer):
    """Объекты ответа Overpass (JSON) списком словарей: lat, lon, name,
    resource, kind, operator, osm (тип/номер)."""
    out = []
    for element in (answer or {}).get("elements", ()):
        center = element.get("center") or element
        lat, lon = center.get("lat"), center.get("lon")
        tags = element.get("tags") or {}
        if lat is None or lon is None:
            continue
        resource = tags.get("resource") or tags.get("product") or ""
        out.append({"lat": float(lat), "lon": float(lon),
                    "name": tags.get("name:ru") or tags.get("name") or "",
                    "resource": resource.replace(";", ", "),
                    "kind": kind_of(tags),
                    "operator": tags.get("operator") or "",
                    "osm": "{}/{}".format(element.get("type"),
                                          element.get("id"))})
    return out


def to_deposits(items):
    """Объекты OSM в core.deposits.Deposits. Поля записи - как у рудников
    мира: название, страна (пусто), ископаемые, вид, стадия (пусто),
    номер (пусто), оператор, мощность (пусто), точность (пусто), объект
    OSM. Повторы одного объекта из соседних тайлов отбрасываются."""
    seen = set()
    out = deposits._Builder()
    for item in items:
        if item["osm"] in seen:
            continue
        seen.add(item["osm"])
        out.add(item["lat"], item["lon"], item["resource"], False, 0,
                (item["name"], "", item["resource"], item["kind"], "", "",
                 item["operator"], "", "", item["osm"]))
    return out.result()
