# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поиск места по названию через Nominatim, геокодер OpenStreetMap.

Здесь адрес запроса и разбор ответа, без сети и без Qt. Правила
Nominatim соблюдает окно: запрос только по Enter, не чаще раза
в SEARCH_INTERVAL, заголовок PlanetX, ответы запоминаются.
https://operations.osmfoundation.org/policies/nominatim/
"""
from collections import namedtuple
from urllib.parse import urlencode

NOMINATIM = "https://nominatim.openstreetmap.org/search"
SEARCH_INTERVAL = 1.0  # секунд между запросами, требование Nominatim
SEARCH_LIMIT = 8  # мест в ответе, не больше

Place = namedtuple("Place", "name detail lat lon box")
Place.__doc__ = """Найденное место.

name - короткое название, detail - остаток полного названия, например
область и страна. lat, lon в градусах. box - охват (запад, юг,
восток, север) в градусах или None.
"""


def normalize(text):
    """Строка запроса без лишних пробелов, ключ памяти ответов."""
    return " ".join(text.split())


def search_url(text, language=None, limit=SEARCH_LIMIT):
    """Адрес запроса к Nominatim. language - код языка названий."""
    query = {"q": normalize(text), "format": "jsonv2",
             "limit": str(limit)}
    if language:
        query["accept-language"] = language
    return NOMINATIM + "?" + urlencode(query)


def _float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _box(item):
    """Охват из boundingbox Nominatim: юг, север, запад, восток."""
    values = [_float(v) for v in item.get("boundingbox") or ()]
    if len(values) != 4 or None in values:
        return None
    south, north, west, east = values
    return west, south, east, north


def parse_places(data):
    """Список Place из ответа Nominatim в формате jsonv2.

    Записи без координат пропускаются. Порядок - как в ответе,
    Nominatim ставит первыми важные места.
    """
    out = []
    for item in data if isinstance(data, list) else ():
        if not isinstance(item, dict):
            continue
        lat, lon = _float(item.get("lat")), _float(item.get("lon"))
        if lat is None or lon is None:
            continue
        full = str(item.get("display_name") or "")
        parts = [p.strip() for p in full.split(",") if p.strip()]
        name = str(item.get("name") or "") or (parts[0] if parts else "")
        if parts and parts[0] == name:
            parts = parts[1:]
        out.append(Place(name, ", ".join(parts), lat, lon, _box(item)))
    return out


def place_text(place):
    """Строка списка найденных мест."""
    if place.detail:
        return "{}, {}".format(place.name, place.detail)
    return place.name
