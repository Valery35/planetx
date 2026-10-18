# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Архив снимков Esri World Imagery Wayback.

Просьба автора от 18 октября 2026 года после плагина historical-imagery
RustGIS. Wayback - выпуски подложки Esri World Imagery с 20 февраля
2014 года, на 18 октября 2026 года их 197. Список выпусков - открытый
файл CONFIG_URL: номер выпуска, дата в названии, служба сведений
о снимках выпуска. Тайл выпуска - TILE_URL с номером, JPEG 256.

Выпуски, где в точке ничего не менялось, отдают тайл прежнего выпуска.
Служба tilemap отвечает, из какого выпуска тайл на самом деле (поле
select). Выпуски с изменениями в точке находятся цепочкой: новейший
выпуск, выпуск его тайла, выпуск старше него, и так до самого старого
- запросов столько, сколько изменений (changes_next).

Дата съёмки, источник и разрешение снимка в точке - запрос query
службы сведений выпуска, слой по уровню масштаба (metadata_url).

Расчёт без Qt. Тема строки и загрузка - core/themes.py, ui/globe.
"""
import calendar
import datetime
import json
import math
import re
from collections import namedtuple

CONFIG_URL = ("https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/"
              "waybackconfig.json")
ROOT = ("https://wayback.maptiles.arcgis.com/arcgis/rest/services/"
        "World_Imagery")
TILE_URL = ROOT + ("/WMTS/1.0.0/default028mm/MapServer/tile/{release}/"
                   "{{z}}/{{y}}/{{x}}")
# Нынешняя подложка - пока список выпусков не пришёл.
CURRENT_URL = ("https://services.arcgisonline.com/arcgis/rest/services/"
               "World_Imagery/MapServer/tile/{z}/{y}/{x}")
TILEMAP_URL = ROOT + "/MapServer/tilemap/{release}/{z}/{y}/{x}"
# Подпись - из accessInformation слоя выпуска в ArcGIS Online, условия -
# Esri Master License Agreement, как у World Imagery, сверено 18 октября
# 2026 года. В короткой подписи на карте остаётся «Wayback - Esri».
ATTRIBUTION = ("Wayback - Esri, Vantor, Earthstar Geographics, and the GIS "
               "User Community", "https://livingatlas.arcgis.com/wayback/")
MAX_LEVEL = 19
# Уровень тайла, по которому ищутся изменения в точке взгляда: квартал
# около 600 м на широте Перми. Выбор помощника, утверждает автор.
LOCAL_LEVEL = 16
# Слои службы сведений: 0 - 1.9 см (уровень 23) … 13 - 150 м (уровень 10).
META_TOP = 23
META_LAYERS = 14

Release = namedtuple("Release", "number day meta")
Release.__doc__ = """Выпуск: номер, дата (datetime.date), адрес службы
сведений о снимках или ""."""

_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")


def parse_config(data):
    """Выпуски из файла CONFIG_URL по возрастанию даты. Дата - из
    названия «World Imagery (Wayback YYYY-MM-DD)». Выпуски одного дня -
    один, с большим номером."""
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    raw = json.loads(data or "{}")
    by_day = {}
    for key, item in (raw.items() if isinstance(raw, dict) else ()):
        if not isinstance(item, dict):
            continue
        found = _DATE.search(str(item.get("itemTitle", "")))
        if found is None or not str(key).isdigit():
            continue
        number = int(key)
        day = datetime.date(*(int(part) for part in found.groups()))
        old = by_day.get(day)
        if old is None or number > old.number:
            by_day[day] = Release(number, day,
                                  str(item.get("metadataLayerUrl") or ""))
    return [by_day[day] for day in sorted(by_day)]


def intervals(releases):
    """Ряд дат в записи тем (core/themes.py): день на выпуск."""
    return [(r.day, r.day, 1, "D") for r in releases]


def by_day(releases):
    """Выпуск по дате YYYY-MM-DD."""
    return {r.day.isoformat(): r for r in releases}


def tile_url(number):
    """Шаблон адреса тайла выпуска для загрузчика: {z}, {x}, {y}."""
    return TILE_URL.format(release=number)


def search_level(width):
    """Уровень тайла поиска изменений по ширине вида width, м: тайл
    около половины ширины, не подробнее LOCAL_LEVEL."""
    share = 40075016.7 / max(float(width), 1.0)
    level = int(round(math.log2(share))) + 1
    return min(max(level, 2), LOCAL_LEVEL)


def tilemap_url(number, z, x, y):
    return TILEMAP_URL.format(release=number, z=z, x=x, y=y)


def tile_of(lat, lon, z=LOCAL_LEVEL):
    """Тайл (x, y) Web Mercator уровня z под точкой."""
    lat = max(min(lat, 85.0511), -85.0511)
    n = 1 << z
    x = int((lon + 180.0) / 360.0 * n)
    s = math.log(math.tan(math.radians(lat)) + 1.0
                 / math.cos(math.radians(lat)))
    y = int((1.0 - s / math.pi) / 2.0 * n)
    return min(max(x, 0), n - 1), min(max(y, 0), n - 1)


def parse_tilemap(data, number):
    """Выпуск, из которого тайл выпуска number на самом деле, или None -
    у выпуска тайла здесь нет."""
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    raw = json.loads(data or "{}")
    if not raw.get("data") or not raw["data"][0]:
        return None
    select = raw.get("select")
    if select and isinstance(select[0], int):
        return select[0]
    return number


def changes_next(releases, effective):
    """Следующий выпуск цепочки изменений: самый новый выпуск старше
    выпуска effective, или None - старше нет. effective - номер выпуска,
    откуда пришёл тайл."""
    days = {r.number: r.day for r in releases}
    day = days.get(effective)
    if day is None:
        return None
    older = [r for r in releases if r.day < day]
    return older[-1] if older else None


def metadata_layer(z):
    """Слой службы сведений для уровня масштаба z."""
    return min(max(META_TOP - int(z), 0), META_LAYERS - 1)


def metadata_url(release, lat, lon, z):
    """Запрос сведений о снимке выпуска в точке или None без службы."""
    if not release.meta:
        return None
    return ("{}/{}/query?geometry={:.7f},{:.7f}&geometryType="
            "esriGeometryPoint&inSR=4326&spatialRel="
            "esriSpatialRelIntersects&outFields=SRC_DATE2,NICE_DESC,"
            "SRC_DESC,SRC_RES,SRC_ACC&returnGeometry=false&f=json").format(
                release.meta.rstrip("/"), metadata_layer(z), lon, lat)


def parse_metadata(data):
    """Сведения о снимке: словарь date (YYYY-MM-DD или ""), provider,
    sensor, resolution (м или None), accuracy (м или None), или None."""
    if isinstance(data, (bytes, bytearray)):
        data = data.decode("utf-8", "replace")
    raw = json.loads(data or "{}")
    features = raw.get("features") or []
    if not features:
        return None
    attrs = features[0].get("attributes") or {}
    stamp = attrs.get("SRC_DATE2")
    date = ""
    if isinstance(stamp, (int, float)):
        date = datetime.datetime.fromtimestamp(
            0, datetime.timezone.utc) + datetime.timedelta(
                milliseconds=stamp)
        date = date.date().isoformat()

    def number(name):
        value = attrs.get(name)
        return float(value) if isinstance(value, (int, float)) else None
    return {"date": date, "provider": str(attrs.get("NICE_DESC") or ""),
            "sensor": str(attrs.get("SRC_DESC") or ""),
            "resolution": number("SRC_RES"),
            "accuracy": number("SRC_ACC")}


def moment(day):
    """Начало дня (datetime.date) в секундах UTC."""
    return float(calendar.timegm(day.timetuple()))
