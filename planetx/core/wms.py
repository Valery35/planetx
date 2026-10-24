# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подложка из службы WMS. Модуль не знает про Qt.

Просьба автора от 23 октября 2026 года со службой ортофото PASDA
DVRPC 2020 - окно «Новый источник тайлов» принимает адрес любой службы
WMS. Окно читает GetCapabilities (parse), даёт выбрать слой и пишет
источник в настройку PlanetX/wms_sources (entries_text). Картинка
тайла - GetMap рамкой тайла в EPSG:3857 (getmap_template, место
{bbox} - core.basemap.WmsSource).

Многие службы покрывают только свой район. Вне охвата слоя тайл берётся
у подложки по умолчанию, на краю охвата картинка WMS с прозрачностью
ложится поверх неё (core.basemap.RegionalWms).

Служба ArcGIS PASDA не называет EPSG:3857 в списке систем, но отдаёт
картинки в ней, проверено 23 октября 2026 года. Поэтому без кода
Меркатора в списке берётся EPSG:3857.
"""
import json
import math
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit

try:  # внутри плагина QGIS
    from . import basemap, kml
except ImportError:  # headless-тесты
    import basemap
    import kml

# Параметры запроса, которые окно ставит само и снимает с адреса.
OWN_PARAMS = {"service", "request", "version", "layers", "styles", "crs",
              "srs", "bbox", "width", "height", "format", "transparent"}
MERCATOR_CODES = ("EPSG:3857", "EPSG:900913", "EPSG:102100", "EPSG:102113")
# Порядок выбора формата: с прозрачностью первыми.
FORMATS = ("image/png", "image/png32", "image/png24", "image/png8",
           "image/jpeg", "image/jpg")
SIDE = 256  # пикселей тайла
LAT_LIMIT = 85.0511287798  # край Web Mercator
MERCATOR_HALF = 20037508.342789244
# Охват шире этого по долготе и широте - весь мир, без подложки снизу.
WORLD_LON = 350.0
WORLD_LAT = 160.0
SETTINGS_KEY = "PlanetX/wms_sources"
# Тайл района не больше этого количества охватов: у всех слоёв PASDA
# DVRPC (около 200 км) с уровня 6, у одной Филадельфии - с уровня 8.
LEVEL_SPAN = 2.0


class WmsError(ValueError):
    """Ответ не разбирается как GetCapabilities службы WMS."""


class Layer:
    """Слой выбора: names - имена для LAYERS (у группы - имена её
    слоёв), title - название, box - охват (запад, юг, восток, север)
    в градусах или None, crs - системы координат, group - группа."""

    __slots__ = ("names", "title", "box", "crs", "group")

    def __init__(self, names, title, box, crs, group=False):
        self.names = tuple(names)
        self.title = title
        self.box = box
        self.crs = frozenset(crs)
        self.group = group


class Capabilities:
    __slots__ = ("version", "title", "formats", "layers", "attribution")

    def __init__(self, version, title, formats, layers, attribution):
        self.version = version
        self.title = title
        self.formats = formats
        self.layers = layers
        self.attribution = attribution


def is_wms(text):
    """Адрес службы WMS: параметр service=WMS, запрос GetCapabilities
    или путь, оканчивающийся на WMSServer или /wms."""
    parts = urlsplit(text.strip())
    query = parts.query.lower()
    path = parts.path.lower().rstrip("/")
    return ("service=wms" in query or "request=getcapabilities" in query
            or path.endswith("wmsserver") or path.endswith("/wms"))


def base_url(text):
    """Адрес службы без параметров, которые окно ставит само."""
    parts = urlsplit(text.strip())
    kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
            if k.lower() not in OWN_PARAMS]
    return urlunsplit((parts.scheme, parts.netloc, parts.path,
                       urlencode(kept), ""))


def _join(base, query):
    return base + ("&" if "?" in base else "?") + query


def capabilities_url(base):
    return _join(base, "SERVICE=WMS&REQUEST=GetCapabilities")


def _child(node, tag):
    for child in node:
        if child.tag == tag:
            return child
    return None


def _text(node, tag):
    child = _child(node, tag)
    return child.text.strip() if child is not None else ""


def _number(text):
    try:
        return float(text)
    except ValueError:
        return None


def _box(node):
    """Охват слоя в градусах: EX_GeographicBoundingBox (1.3.0) или
    LatLonBoundingBox (1.1.1)."""
    geo = _child(node, "EX_GeographicBoundingBox")
    if geo is not None:
        values = [_number(_text(geo, t)) for t in (
            "westBoundLongitude", "southBoundLatitude",
            "eastBoundLongitude", "northBoundLatitude")]
    else:
        old = _child(node, "LatLonBoundingBox")
        if old is None:
            return None
        values = [_number(old.get(k, "")) for k in
                  ("minx", "miny", "maxx", "maxy")]
    if any(v is None for v in values):
        return None
    w, s, e, n = values
    if w >= e or s >= n:
        return None
    return w, s, e, n


def _union(boxes):
    boxes = [b for b in boxes if b]
    if not boxes:
        return None
    return (min(b[0] for b in boxes), min(b[1] for b in boxes),
            max(b[2] for b in boxes), max(b[3] for b in boxes))


def _layers(node, crs, box, out):
    """Слои дерева. Системы и охват наследуются от родителя. Группа
    с именованными слоями внутри даёт строку «все слои группы»."""
    crs = set(crs) | {c.text.strip().upper() for c in node
                      if c.tag in ("CRS", "SRS") and c.text.strip()}
    box = _box(node) or box
    name = _text(node, "Name")
    title = _text(node, "Title") or name
    start = len(out)
    if name:
        out.append(Layer((name,), title, box, crs))
    for child in node:
        if child.tag == "Layer":
            _layers(child, crs, box, out)
    inner = [layer for layer in out[start:] if not layer.group]
    if not name and len(inner) > 1:
        names = [n for layer in inner for n in layer.names]
        out.insert(start, Layer(names, title,
                                _union([layer.box for layer in inner]) or box,
                                crs, group=True))


def parse(data):
    """Capabilities по байтам ответа GetCapabilities или WmsError."""
    try:
        root = kml._parse(data)
    except kml.KmlError as error:
        raise WmsError(str(error)) from error
    if root.tag not in ("WMS_Capabilities", "WMT_MS_Capabilities"):
        if root.tag in ("ServiceExceptionReport", "ExceptionReport"):
            raise WmsError(" ".join(n.text.strip() for n in root.iter()
                                    if n.text.strip()) or "exception")
        raise WmsError("not WMS capabilities: " + root.tag)
    service = _child(root, "Service")
    title = _text(service, "Title") if service is not None else ""
    capability = _child(root, "Capability")
    if capability is None:
        raise WmsError("no Capability")
    formats = []
    request = _child(capability, "Request")
    getmap = _child(request, "GetMap") if request is not None else None
    if getmap is not None:
        formats = [f.text.strip().lower() for f in getmap
                   if f.tag == "Format" and f.text.strip()]
    layers = []
    attribution = ""
    for node in capability:
        if node.tag == "Layer":
            _layers(node, set(), None, layers)
            credit = _child(node, "Attribution")
            if credit is not None:
                attribution = _text(credit, "Title")
            title = title or _text(node, "Title")
    if not layers:
        raise WmsError("no named layers")
    return Capabilities(root.get("version", "1.3.0"), title, formats,
                        layers, attribution)


def mercator_code(crs):
    """Код Web Mercator из списка систем слоя, без него EPSG:3857."""
    for code in MERCATOR_CODES:
        if code in crs:
            return code
    return MERCATOR_CODES[0]


def pick_format(formats):
    for fmt in FORMATS:
        if fmt in formats:
            return fmt
    return FORMATS[0]


def getmap_template(base, version, names, crs, fmt):
    """Адрес GetMap с местом {bbox} - рамкой тайла в метрах EPSG:3857."""
    key = "CRS" if version.startswith("1.3") else "SRS"
    query = "&".join((
        "SERVICE=WMS", "VERSION=" + version, "REQUEST=GetMap",
        "LAYERS=" + quote(",".join(names), safe=","), "STYLES=",
        "FORMAT=" + quote(fmt, safe=""), "TRANSPARENT=TRUE",
        "WIDTH=%d" % SIDE, "HEIGHT=%d" % SIDE, key + "=" + crs,
        "BBOX={bbox}"))
    return _join(base, query)


def mercator(lon, lat):
    """Точка в метрах EPSG:3857."""
    lat = max(-LAT_LIMIT, min(LAT_LIMIT, lat))
    x = math.radians(lon) * MERCATOR_HALF / math.pi
    y = math.log(math.tan(math.pi / 4 + math.radians(lat) / 2)) \
        * MERCATOR_HALF / math.pi
    return x, y


def mercator_box(box):
    """Охват в градусах - рамка в метрах EPSG:3857."""
    w, s = mercator(box[0], box[1])
    e, n = mercator(box[2], box[3])
    return w, s, e, n


def is_world(box):
    return box is None or (box[2] - box[0] >= WORLD_LON
                           and box[3] - box[1] >= WORLD_LAT)


def preview_bbox(box):
    """Квадрат предпросмотра вокруг охвата, метры EPSG:3857."""
    w, s, e, n = mercator_box(box if box else (-180, -LAT_LIMIT,
                                               180, LAT_LIMIT))
    half = max(e - w, n - s) / 2.0
    x, y = (w + e) / 2.0, (s + n) / 2.0
    return x - half, y - half, x + half, y + half


def bbox_text(box):
    return ",".join("{:.2f}".format(v) for v in box)


def entries_parse(text):
    """Источники WMS из настройки: список словарей с полями name, base,
    template, box, level, credit."""
    try:
        items = json.loads(text or "[]")
    except ValueError:
        return []
    out = []
    for item in items if isinstance(items, list) else []:
        if isinstance(item, dict) and item.get("name") \
                and "{bbox}" in str(item.get("template", "")):
            box = item.get("box")
            item["box"] = tuple(box) if box and len(box) == 4 else None
            out.append(item)
    return out


def entries_text(items):
    return json.dumps(items, ensure_ascii=False)


# Категория «Локальные данные» каталога «Добавить данные» - службы WMS
# с подробными снимками и картами отдельных районов, просьба автора от
# 24 октября 2026 года. Поля: ключ, название по-русски и по-английски,
# описание по-русски и по-английски, адрес службы, слои, охват
# в градусах, подпись. PASDA (Pennsylvania Spatial Data Access) -
# ортофото DVRPC весны 2020 года, Nearmap, 9 округов вокруг Филадельфии,
# GetCapabilities от 23 октября 2026 года.
PASDA_DVRPC = ("https://imagery.pasda.psu.edu/arcgis/services/pasda/"
               "DVRPC2020/MapServer/WMSServer")
LOCAL = (
    ("pasda_dvrpc2020", "PASDA DVRPC 2020, Филадельфия",
     "PASDA DVRPC 2020, Philadelphia",
     "Ортофото весны 2020 года девяти округов вокруг Филадельфии (США), "
     "служба Pennsylvania Spatial Data Access. Служба медленная, "
     "картинки приходят за несколько секунд.",
     "Spring 2020 orthophoto of nine counties around Philadelphia (USA), "
     "the Pennsylvania Spatial Data Access service. The service is slow, "
     "pictures arrive in a few seconds.",
     PASDA_DVRPC, tuple(str(n) for n in range(9)),
     (-76.145206, 39.514075, -74.385339, 40.608742),
     "PASDA, DVRPC, Nearmap 2020"),
)
LOCAL_KEYS = tuple(row[0] for row in LOCAL)


def local_entry(key, russian=True):
    """Запись настройки PlanetX/wms_sources для строки LOCAL."""
    for row in LOCAL:
        if row[0] == key:
            _, ru, en, _, _, base, layers, box, credit = row
            return {"name": ru if russian else en, "base": base,
                    "layers": list(layers),
                    "template": getmap_template(base, "1.3.0", layers,
                                                MERCATOR_CODES[0],
                                                "image/png"),
                    "box": list(box), "level": basemap.MAX_LEVEL,
                    "credit": credit, "local": key}
    raise KeyError(key)


def local_about(key, russian=True):
    for row in LOCAL:
        if row[0] == key:
            return row[3] if russian else row[4]
    raise KeyError(key)


def source(entry):
    """Подложка по записи настройки. Под районом службы - Esri World
    Imagery, её подпись идёт следом за подписью службы."""
    box = entry.get("box")
    world = is_world(box)
    credit = entry.get("credit") or entry["name"]
    under = basemap.esri_imagery()
    if not world:
        credit = credit + "; " + under.attribution[0]
    return basemap.RegionalWms(
        entry["name"], entry["template"],
        None if world else mercator_box(box), "" if world else under.url,
        int(entry.get("level") or basemap.MAX_LEVEL), (credit, ""),
        entry=entry, min_level=0 if world else first_level(box))


def first_level(box):
    """Уровень, с которого тайл не больше LEVEL_SPAN охватов района."""
    w, s, e, n = mercator_box(box)
    span = max(e - w, n - s, 1.0) * LEVEL_SPAN
    level = math.floor(math.log2(2.0 * MERCATOR_HALF / span))
    return max(0, min(basemap.MAX_LEVEL, level))
