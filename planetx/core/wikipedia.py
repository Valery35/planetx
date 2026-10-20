# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Википедия рядом: статьи с координатами у точки взгляда.

Просьба автора от 19 октября 2026 года - географическая энциклопедия
вместо «баллонов» из пакета задач другой модели. Статьи даёт служба
geosearch API MediaWiki (list=geosearch) без ключа, рамкой gsbbox.
Рамка больше около 300 км² служба не принимает (ответ toobig, проверено
19 октября 2026 года), поэтому запрос идёт по тайлам Web Mercator уровня
ZOOM - у экватора около 9.8 км, севернее меньше. Ответ - до LIMIT статей
тайла, ближние к середине рамки первыми. Статьи на Луне и Марсе служба
по параметру gsglobe не нашла, слой только земной.

Первый абзац статьи даёт REST API страниц (page/summary). Тексты
Википедии - CC BY-SA 4.0, подпись - «Wikipedia».

Wikidata SPARQL с рамкой вида проверялся тем же днём - рамка Европы
отвечала дольше 20 с, поэтому слой виден только вблизи, ниже
MAX_ALTITUDE.
"""
import math
import re
from collections import namedtuple
from urllib.parse import quote

try:  # внутри плагина QGIS
    from .mining import tile_bounds, tile_of
except ImportError:  # headless-тесты
    from mining import tile_bounds, tile_of

ZOOM = 12
VIEW_TILES = 25  # тайлов вокруг точки взгляда, 5 × 5
MAX_ALTITUDE = 40000.0  # м, выше глаза статьи не просятся
LIMIT = 500  # статей в ответе службы на тайл, её предел
MAX_MARKS = 2000  # подписей на глобусе, важные и ближние первыми
GAP = 0.25  # с между запросами к службе, по одному запросу сразу
ATTRIBUTION = ("Wikipedia, CC BY-SA 4.0",
               "https://creativecommons.org/licenses/by-sa/4.0/")
API = "https://{lang}.wikipedia.org/w/api.php"
SUMMARY = "https://{lang}.wikipedia.org/api/rest_v1/page/summary/{title}"
PAGE = "https://{lang}.wikipedia.org/wiki/{title}"

# Важность статьи по виду объекта (поле type разметки координат
# Википедии): страны и области прежде городов, города прежде
# достопримечательностей. Меньше - важнее. Выбор помощника.
TYPE_RANK = {"country": 1, "adm1st": 2, "adm2nd": 3, "city": 3,
             "adm3rd": 4, "mountain": 4, "river": 4, "waterbody": 4,
             "isle": 4, "glacier": 4, "airport": 5, "landmark": 5,
             "railwaystation": 6, "edu": 6, "event": 6, "forest": 6}
OTHER_RANK = 7

Article = namedtuple("Article", "pageid title lat lon rank")
Article.__doc__ = """Статья с координатами: номер страницы, заголовок,
широта и долгота в градусах, важность (меньше - важнее)."""


def language(code):
    """Раздел Википедии по коду языка интерфейса, иначе английский."""
    code = (code or "").lower()
    return code if re.fullmatch(r"[a-z]{2,3}", code) else "en"


def view_tiles(lat, lon, altitude, limit=VIEW_TILES):
    """Тайлы уровня ZOOM вокруг точки взгляда, ближние первыми, не
    больше limit. Выше MAX_ALTITUDE - ни одного."""
    if altitude > MAX_ALTITUDE:
        return []
    cx, cy = tile_of(lat, lon, ZOOM)
    n = 2 ** ZOOM
    reach = int(math.ceil((math.sqrt(limit) - 1) / 2.0))
    tiles = [((cx + dx) % n, cy + dy)
             for dy in range(-reach, reach + 1)
             for dx in range(-reach, reach + 1)
             if 0 <= cy + dy < n]
    tiles.sort(key=lambda t: (t[0] - cx) ** 2 + (t[1] - cy) ** 2)
    return tiles[:limit]


def geosearch_url(lang, tile):
    """Адрес запроса статей в рамке тайла (x, y) уровня ZOOM."""
    south, west, north, east = tile_bounds(tile[0], tile[1], ZOOM)
    return (API.format(lang=language(lang))
            + "?action=query&list=geosearch&format=json"
            "&gsbbox={:.6f}|{:.6f}|{:.6f}|{:.6f}&gslimit={}&gsprop=type|dim"
            .format(north, west, south, east, LIMIT))


def parse_geosearch(data):
    """Статьи из ответа geosearch. Ответ с ошибкой службы -
    ValueError."""
    if not isinstance(data, dict):
        raise ValueError("not a geosearch answer")
    if "error" in data:
        error = data["error"]
        raise ValueError("{}: {}".format(error.get("code", ""),
                                         error.get("info", "")))
    found = []
    for item in (data.get("query") or {}).get("geosearch") or ():
        article = _article(item)
        if article is not None:
            found.append(article)
    return found


def _article(item):
    """Статья из записи ответа или None, если в записи нет точки,
    номера или заголовка."""
    title = str(item.get("title") or "").strip()
    try:
        lat = float(item["lat"])
        lon = float(item["lon"])
        pageid = int(item["pageid"])
    except (KeyError, TypeError, ValueError):
        title = ""
    if not title:
        return None
    return Article(pageid, title, lat, lon,
                   TYPE_RANK.get(item.get("type"), OTHER_RANK))


def _path(title):
    return quote(title.replace(" ", "_"), safe="")


def summary_url(lang, title):
    """Адрес первого абзаца статьи."""
    return SUMMARY.format(lang=language(lang), title=_path(title))


def page_url(lang, title):
    """Адрес статьи для браузера."""
    return PAGE.format(lang=language(lang), title=_path(title))


def parse_summary(data):
    """Первый абзац статьи текстом из ответа page/summary. Ответ без
    текста - ValueError."""
    if not isinstance(data, dict):
        raise ValueError("not a summary answer")
    # Википедия снимает из абзаца ударения и пояснения в скобках,
    # на их месте остаются двойные пробелы.
    text = re.sub(r"[^\S\n]{2,}", " ",
                  str(data.get("extract") or "")).strip()
    if not text:
        raise ValueError(str(data.get("title") or data.get("type")
                             or "no extract"))
    return text


def order(articles, lat, lon, limit=MAX_MARKS):
    """Статьи без повторов в порядке подписей: важные первыми, среди
    равных - ближние к точке взгляда. Не больше limit."""
    seen = {}
    for article in articles:
        seen.setdefault(article.pageid, article)
    cos = max(math.cos(math.radians(lat)), 1e-6)

    def key(a):
        dlon = (a.lon - lon + 180.0) % 360.0 - 180.0
        return (a.rank, (a.lat - lat) ** 2 + (dlon * cos) ** 2)
    return sorted(seen.values(), key=key)[:limit]
