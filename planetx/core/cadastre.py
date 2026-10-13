# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кадастр Росреестра - слой земельных участков НСПД поверх снимка.

Служба - WMS Национальной системы пространственных данных (nspd.gov.ru),
она заменила публичную кадастровую карту. Проверено 13 октября 2026
года у Перми:

- без заголовка Referer с адресом карты НСПД ответ 403;
- сертификат сервера выдан «Russian Trusted Sub CA» Минцифры, корневой
  «Russian Trusted Root CA» в Windows по умолчанию не входит. Он лежит
  в модуле (CA_FILE, отпечаток SHA-1 CA_SHA1, скачан с gu-st.ru,
  страницы Госуслуг) и действует только на запросы PlanetX к HOST,
  net/loader.py;
- на частые запросы подряд служба отвечает кодом 597, поэтому запросы
  идут по одному с паузой GAP, а тайлы мельче MIN_LEVEL не просятся;
- слой 36048 - земельные участки. Номера других слоёв не подтверждены,
  список слоёв (GetCapabilities) служба не отдала.

Модуль Qt не знает.
"""

import json
import math

HOST = "nspd.gov.ru"
LAYER = 36048  # земельные участки
URL = ("https://nspd.gov.ru/api/aeggis/v3/{layer}/wms?SERVICE=WMS"
       "&REQUEST=GetMap&VERSION=1.3.0&LAYERS={layer}&STYLES="
       "&FORMAT=image/png&TRANSPARENT=true&CRS=EPSG:3857&BBOX={{bbox}}"
       "&WIDTH=256&HEIGHT=256").format(layer=LAYER)
REFERER = "https://nspd.gov.ru/map"
ATTRIBUTION = ("Rosreestr NSPD", "https://nspd.gov.ru/")
MIN_LEVEL = 14  # мельче участки не просятся: их тысячи в тайле
MAX_LEVEL = 18  # глубже - часть картинки уровня 18
GAP = 0.5  # с между запросами к службе
CA_FILE = "russian_trusted_root_ca.pem"
CA_SHA1 = "8FF915CCAB7BC16F8C5C8099D53E0E115B3AEC2F"

# Сведения об участке - GetFeatureInfo той же службы, проверено
# 13 октября 2026 года. Без FORMAT служба отвечает 500 «invalid request»
# с кодом 1201. Окно запроса - INFO_PIXELS пикселей по INFO_METRES м,
# точка - середина окна.
INFO_URL = ("https://nspd.gov.ru/api/aeggis/v3/{layer}/wms?SERVICE=WMS"
            "&REQUEST=GetFeatureInfo&VERSION=1.3.0&LAYERS={layer}"
            "&QUERY_LAYERS={layer}&STYLES=&FORMAT=image/png"
            "&TRANSPARENT=true&INFO_FORMAT=application/json"
            "&FEATURE_COUNT=5&CRS=EPSG:3857&BBOX={bbox}"
            "&WIDTH={size}&HEIGHT={size}&I={middle}&J={middle}")
INFO_PIXELS = 256
INFO_METRES = 1.0  # метров местности на пиксель окна запроса
# Страница карты НСПД на точке со слоем участков.
MAP_LINK = ("https://nspd.gov.ru/map?zoom=18&coordinate_x={x:.0f}"
            "&coordinate_y={y:.0f}&theme_id=1&is_copy_url=true"
            "&active_layers={layer}")
# Поля сведений об участке по порядку: ключ ответа и единицы. Подписи
# полей - у окна (ui/window.py, parcel_labels).
FIELDS = (
    ("cad_num", ""),
    ("readable_address", ""),
    ("specified_area", "м²"),
    ("declared_area", "м²"),
    ("land_record_category_type", ""),
    ("permitted_use_established_by_document", ""),
    ("ownership_type", ""),
    ("right_type", ""),
    ("cost_value", "₽"),
    ("cost_index", "₽/м²"),
    ("cost_determination_date", ""),
    ("cost_application_date", ""),
    ("land_record_reg_date", ""),
    ("status", ""),
    ("quarter_cad_number", ""),
)
EARTH = 6378137.0  # радиус сферы Web Mercator, м


def mercator(lat, lon):
    """Точка в EPSG:3857, метры."""
    lat = max(min(lat, 85.0511), -85.0511)
    return (math.radians(lon) * EARTH,
            math.log(math.tan(math.pi / 4.0 + math.radians(lat) / 2.0))
            * EARTH)


def geographic(x, y):
    """Точка EPSG:3857 в (широта, долгота)."""
    return (math.degrees(2.0 * math.atan(math.exp(y / EARTH))
                         - math.pi / 2.0),
            math.degrees(x / EARTH))


def info_url(lat, lon):
    """Адрес сведений об участках под точкой."""
    x, y = mercator(lat, lon)
    # Метр Web Mercator на широте lat короче метра местности.
    half = INFO_PIXELS / 2.0 * INFO_METRES / math.cos(math.radians(lat))
    bbox = "{:.2f},{:.2f},{:.2f},{:.2f}".format(x - half, y - half,
                                                x + half, y + half)
    return INFO_URL.format(layer=LAYER, bbox=bbox, size=INFO_PIXELS,
                           middle=INFO_PIXELS // 2)


def map_link(lat, lon):
    """Карта НСПД на точке со слоем участков."""
    x, y = mercator(lat, lon)
    return MAP_LINK.format(x=x, y=y, layer=LAYER)


def _number(value):
    text = "{:,.2f}".format(value).replace(",", " ")
    return text[:-3] if text.endswith(".00") else text


def _text(value, unit):
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        value = _number(value)
    return "{} {}".format(value, unit) if unit else str(value)


def _rings(geometry):
    """Внешние кольца многоугольника GeoJSON в EPSG:3857 - списки
    (широта, долгота) без повтора первой точки."""
    kind = geometry.get("type") if isinstance(geometry, dict) else None
    coords = geometry.get("coordinates") if kind else None
    if kind == "Polygon":
        polygons = [coords]
    elif kind == "MultiPolygon":
        polygons = coords
    else:
        return []
    out = []
    for polygon in polygons or ():
        if not polygon:
            continue
        ring = [geographic(float(p[0]), float(p[1])) for p in polygon[0]]
        if len(ring) > 1 and ring[0] == ring[-1]:
            ring = ring[:-1]
        if len(ring) >= 3:
            out.append(ring)
    return out


def parse_info(data):
    """Ответ GetFeatureInfo (байты или dict) - список участков
    {"number", "values": [(ключ поля, текст)], "rings"}. ValueError, если
    ответ не FeatureCollection."""
    if isinstance(data, (bytes, bytearray)):
        data = json.loads(bytes(data).decode("utf-8"))
    if not isinstance(data, dict) or data.get("type") != "FeatureCollection":
        raise ValueError("not a FeatureCollection")
    parcels = []
    for feature in data.get("features") or ():
        props = feature.get("properties") or {}
        options = props.get("options") or {}
        number = options.get("cad_num") or props.get("label") or ""
        values = []
        for key, unit in FIELDS:
            text = _text(options.get(key), unit)
            if text is not None:
                values.append((key, text))
        parcels.append({"number": str(number), "values": values,
                        "rings": _rings(feature.get("geometry"))})
    return parcels
