# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки чрезвычайных событий Vantor и Planet: каталоги STAC, снимки
дня, тайл глобуса из облачных GeoTIFF. Модуль не знает про Qt.

Просьба автора от 25 октября 2026 года после разбора RustGIS 0.4.0 -
«делай снимки Vantor и Planet». Оба каталога открыты, без ключа,
лицензия снимков CC BY-NC 4.0, сверено 25 октября 2026 года.

- Vantor Open Data (прежде Maxar) - каталог событий, у события
  коллекция, у снимка - полоса WorldView одним COG в EPSG:4326 и
  признак phase («pre», «post»).
- Planet Disaster Data на Source Cooperative - каталог событий, внутри
  pre-event и post-event, коллекции по дням и местам, сцены PlanetScope,
  SkySat и Pelican в UTM, до события - квадраты мозаики Planet в
  EPSG:3857.

Тайл глобуса на день - снимки не позже дня, новые поверх старых,
core/cog.py читает их части, раскодирует вызывающий (decode).
"""
import calendar
import datetime
import math
import re
from urllib.parse import urljoin

import numpy as np

try:  # внутри плагина QGIS
    from . import cog
except ImportError:  # headless-тесты
    import cog

VANTOR = "vantor"
PLANET = "planet"
ROOTS = {
    VANTOR: "https://vantor-opendata.s3.amazonaws.com/events/catalog.json",
    PLANET: "https://data.source.coop/planet/disasterdata/catalog.json"}
NAMES = {VANTOR: "Vantor", PLANET: "Planet"}
CREDITS = {
    VANTOR: ("Vantor Open Data, CC BY-NC 4.0",
             "https://vantor.com/company/open-data-program/"),
    PLANET: ("Planet Labs PBC, CC BY-NC 4.0",
             "https://www.planet.com/disasterdata/")}
LICENSE = "https://creativecommons.org/licenses/by-nc/4.0/"
PRE, POST = "pre", "post"
SIDE = 256
RADIUS = 6378137.0
MAX_LEVEL = 19
MAX_DEPTH = 6  # вложенность каталогов события, ниже не идём
_DATE = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_PREFIX = re.compile(r"^Planet Crisis Response\s*[—\-:]\s*")


class Event:
    """Событие каталога: ключ (источник/id), источник, адрес документа,
    название, описание, день (YYYY-MM-DD или ""), рамка (запад, юг,
    восток, север) или None до прихода снимков."""

    __slots__ = ("key", "source", "url", "title", "description", "day",
                 "box")

    def __init__(self, source, url, ident, title, description, day,
                 box=None):
        self.key = "{}/{}".format(source, ident)
        self.source = source
        self.url = url
        self.title = title
        self.description = description
        self.day = day
        self.box = box


class Item:
    """Снимок события: id, источник, день YYYY-MM-DD, момент в секундах
    UTC, этап (PRE, POST или ""), рамка, адрес COG, размер пикселя, м,
    название спутника или мозаики."""

    __slots__ = ("ident", "source", "day", "time", "phase", "box", "href",
                 "gsd", "platform")

    def __init__(self, ident, source, day, time, phase, box, href, gsd,
                 platform):
        self.ident = ident
        self.source = source
        self.day = day
        self.time = time
        self.phase = phase
        self.box = box
        self.href = href
        self.gsd = gsd
        self.platform = platform


def links(doc, base):
    """Ссылки документа STAC: (rel, абсолютный адрес, название)."""
    out = []
    for link in doc.get("links") or ():
        href = link.get("href")
        if isinstance(href, str) and href:
            out.append((link.get("rel", ""), urljoin(base, href),
                        link.get("title") or ""))
    return out


def children(doc, base):
    """Адреса дочерних каталогов и снимков документа."""
    return [(rel, href) for rel, href, _ in links(doc, base)
            if rel in ("child", "item")]


def parse_events(doc, base):
    """Заготовки событий из корневого каталога: (адрес, название из
    ссылки). Описание и день приходят с документом события."""
    return [(href, title) for rel, href, title in links(doc, base)
            if rel == "child"]


def parse_event(doc, url, source):
    """Событие из документа события (коллекция Vantor или каталог
    Planet) или None."""
    if doc.get("type") not in ("Catalog", "Collection"):
        return None
    ident = str(doc.get("id") or url)
    title = _PREFIX.sub("", str(doc.get("title") or "").strip())
    if not title or title == ident:
        title = ident.replace("-", " ").replace("_", " ")
    description = str(doc.get("description") or "").strip()
    day = ""
    box = None
    extent = doc.get("extent") or {}
    interval = ((extent.get("temporal") or {}).get("interval") or [[]])[0]
    if interval and interval[0]:
        day = str(interval[0])[:10]
    found = _DATE.search(ident)
    if not day and found:
        day = found.group(0)
    bbox = ((extent.get("spatial") or {}).get("bbox") or [None])[0]
    if bbox and len(bbox) >= 4:
        box = tuple(float(v) for v in bbox[:4])
    return Event(source, url, ident, title, description, day, box)


def phase_of(url):
    """Этап по пути документа Planet: pre-event, post-event."""
    if "/pre-event/" in url:
        return PRE
    if "/post-event/" in url:
        return POST
    return ""


def parse_item(doc, url, source, phase=""):
    """Снимок из документа Feature STAC или None, если в нём нет
    картинки visual в COG."""
    if doc.get("type") != "Feature":
        return None
    assets = doc.get("assets") or {}
    asset = assets.get("visual")
    if not asset or "tiff" not in str(asset.get("type", "")):
        return None
    href = urljoin(url, str(asset.get("href", "")))
    props = doc.get("properties") or {}
    stamp = props.get("datetime") or props.get("start_datetime")
    moment = _moment(stamp)
    if moment is None:
        return None
    bbox = doc.get("bbox") or ()
    if len(bbox) < 4:
        return None
    gsd = props.get("gsd") or props.get("pan_gsd") \
        or props.get("pl:pixel_resolution") or 0.0
    platform = str(props.get("pl:mosaic") and "Planet basemap"
                   or props.get("vehicle_name")
                   or props.get("constellation") or "")
    return Item(str(doc.get("id") or href), source, str(stamp)[:10],
                moment, str(props.get("phase") or phase or ""),
                tuple(float(v) for v in bbox[:4]), href, float(gsd),
                platform)


def _moment(stamp):
    if not stamp:
        return None
    found = re.match(r"(\d{4})-(\d{2})-(\d{2})(?:T(\d{2}):(\d{2}):(\d{2}))?",
                     str(stamp))
    if found is None:
        return None
    parts = [int(v) if v else 0 for v in found.groups()]
    return float(calendar.timegm(datetime.datetime(*parts).timetuple()))


def box_of(items):
    """Рамка всех снимков или None."""
    if not items:
        return None
    return (min(i.box[0] for i in items), min(i.box[1] for i in items),
            max(i.box[2] for i in items), max(i.box[3] for i in items))


def intervals(items):
    """Ряд дат темы: каждый день снимков - отдельный промежуток, как
    у выпусков Wayback (core/themes.py)."""
    out = []
    for day in sorted({i.day for i in items}):
        date = datetime.date(*(int(v) for v in day.split("-")))
        out.append((date, date, 1, "D"))
    return out


def pre_day(items):
    """Последний день снимков до события или None."""
    days = [i.day for i in items if i.phase == PRE]
    return max(days) if days else None


def post_day(items):
    """Последний день снимков события: после события, без этапа - все."""
    days = [i.day for i in items if i.phase != PRE] \
        or [i.day for i in items]
    return max(days) if days else None


def shown(items, day):
    """Снимки на день: не позже дня, новые первыми - они лягут сверху."""
    return sorted((i for i in items if i.day <= day),
                  key=lambda i: (i.time, i.gsd and -i.gsd), reverse=True)


def max_level(items):
    """Уровень тайлов, пиксель которого не мельче самого подробного
    снимка."""
    best = [i.gsd for i in items if i.gsd > 0]
    if not best:
        return MAX_LEVEL
    lat = (box_of(items)[1] + box_of(items)[3]) / 2.0
    ground = 2.0 * math.pi * RADIUS * max(math.cos(math.radians(lat)),
                                          0.05) / SIDE
    return int(min(MAX_LEVEL, max(0, math.ceil(math.log2(
        ground / min(best))))))


def tile_box(z, x, y):
    """Рамка тайла XYZ (запад, юг, восток, север) в градусах."""
    n = 1 << z

    def lat(row):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row
                                                           / n))))
    return (x / n * 360.0 - 180.0, lat(y + 1), (x + 1) / n * 360.0 - 180.0,
            lat(y))


def touches(a, b):
    return a[0] <= b[2] and b[0] <= a[2] and a[1] <= b[3] and b[1] <= a[3]


def paint(items, z, x, y, open_cog, decode):
    """Тайл z/x/y RGBA uint8 (SIDE, SIDE, 4) из снимков items по порядку
    сверху вниз. open_cog(адрес) - core.cog.Cog, decode - раскодирование
    тайла TIFF. Снимок, который open_cog не открыл (None), и снимок
    с непонятной системой координат пропускаются, ошибки сети идут
    вызывающему."""
    out = np.zeros((SIDE, SIDE, 4), dtype=np.float32)
    box = tile_box(z, x, y)
    lon = lat = None
    for item in items:
        if not touches(item.box, box):
            continue
        if lon is None:
            lon, lat = cog.tile_points(z, x, y, SIDE)
        image = open_cog(item.href)
        if image is None or not cog.known_crs(image.epsg):
            continue
        xs, ys = cog.to_crs(image.epsg, lon, lat)
        step = float(np.median(np.hypot(np.diff(xs, axis=1),
                                        np.diff(ys, axis=1))))
        part = image.sample_rgba(xs, ys, image.level_for(step),
                                 decode).astype(np.float32)
        # Нижний снимок ложится под уже собранные, «под» по прозрачности.
        rest = 1.0 - out[..., 3:4] / 255.0
        alpha = part[..., 3:4] / 255.0 * rest
        out[..., :3] += part[..., :3] * alpha
        out[..., 3:4] += alpha * 255.0
        if (out[..., 3] >= 254.5).all():
            break
    color = out[..., :3] / np.maximum(out[..., 3:4] / 255.0, 1e-6)
    out[..., :3] = np.where(out[..., 3:4] > 0, color, 0.0)
    return np.clip(np.rint(out), 0, 255).astype(np.uint8)
