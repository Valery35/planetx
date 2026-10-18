# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Суда Балтики вживую по AIS Digitraffic. Просьба автора от 19 октября
2026 года.

Расчёт без Qt. Положения - открытый ответ Fintraffic Digitraffic
ais/v1/locations (GeoJSON, MMSI, скорость и курс по земле, курс
корпуса, время), сведения - ais/v1/vessels (название, позывной, тип
AIS, назначение, размеры от точки антенны A, B, C, D). Условия -
CC BY 4.0, коммерческое использование разрешено, сверено 19 октября
2026 года. Охват - Финский и Ботнический заливы, Балтика у Финляндии.

Модель - условный корпус длиной 1 вдоль оси Y модели, его растягивает
масштаб по размерам судна (unit_ship_parts, ship_size).
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .models import Part
    from .movers import KNOT, Sample
except ImportError:  # headless-тесты
    from models import Part
    from movers import KNOT, Sample

LOCATIONS_URL = "https://meri.digitraffic.fi/api/ais/v1/locations"
VESSELS_URL = "https://meri.digitraffic.fi/api/ais/v1/vessels"
ATTRIBUTION = ("Ships: Fintraffic / digitraffic.fi, CC BY 4.0",
               "https://www.digitraffic.fi/en/marine-traffic/")
POLL = 20.0  # с между запросами положений
INFO_POLL = 600.0  # с между запросами сведений о судах
EXTRAPOLATE = 120.0  # с хода своим курсом после положения
STALE = 1800.0  # положение старше этого не показывается, с
NO_SPEED = 102.3  # sog AIS «нет данных»
NO_COURSE = 360.0
NO_HEADING = 511
# Группы типов AIS: ключ, цвет 0-1, длина по умолчанию, м. Цвета -
# привычные для карт AIS, выбор помощника.
GROUPS = (("passenger", (0.20, 0.50, 0.92), 150.0),
          ("cargo", (0.22, 0.68, 0.30), 120.0),
          ("tanker", (0.86, 0.20, 0.20), 150.0),
          ("fishing", (0.96, 0.58, 0.14), 25.0),
          ("service", (0.10, 0.78, 0.80), 30.0),
          ("fast", (0.96, 0.86, 0.20), 30.0),
          ("pleasure", (0.72, 0.36, 0.86), 12.0),
          ("other", (0.78, 0.78, 0.78), 30.0))
WHITE = (0.94, 0.94, 0.92)
DARK = (0.18, 0.19, 0.21)


def group(ship_type):
    """Группа по коду типа AIS."""
    code = int(ship_type or 0)
    if 60 <= code <= 69:
        return "passenger"
    if 70 <= code <= 79:
        return "cargo"
    if 80 <= code <= 89:
        return "tanker"
    if code == 30:
        return "fishing"
    if code in (31, 32, 33, 34, 35, 50, 51, 52, 53, 54, 55, 58, 59):
        return "service"
    if 40 <= code <= 49:
        return "fast"
    if code in (36, 37):
        return "pleasure"
    return "other"


def group_color(key):
    for name, color, _ in GROUPS:
        if name == key:
            return color
    return GROUPS[-1][1]


def default_length(key):
    for name, _, length in GROUPS:
        if name == key:
            return length
    return GROUPS[-1][2]


def _number(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def parse_locations(data):
    """Положения из GeoJSON ais/v1/locations: список movers.Sample."""
    out = []
    features = (data or {}).get("features") if isinstance(data, dict) \
        else None
    for feature in features if isinstance(features, list) else ():
        if not isinstance(feature, dict):
            continue
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates")
        mmsi = props.get("mmsi", feature.get("mmsi"))
        stamp = _number(props.get("timestampExternal"))
        if not coords or len(coords) < 2 or mmsi is None or stamp is None:
            continue
        lon, lat = _number(coords[0]), _number(coords[1])
        if lat is None or lon is None or not -90.0 <= lat <= 90.0:
            continue
        sog = _number(props.get("sog"))
        speed = 0.0 if sog is None or sog >= NO_SPEED else sog * KNOT
        cog = _number(props.get("cog"))
        course = math.nan if cog is None or cog >= NO_COURSE else cog
        head = _number(props.get("heading"))
        heading = math.nan if head is None or head >= 360.0 else head
        out.append(Sample(int(mmsi), stamp / 1000.0, lat, lon, speed,
                          course, heading))
    return out


class Info:
    """Сведения о судне: название, позывной, IMO, тип AIS, назначение,
    длина и ширина, м (0 - нет)."""

    def __init__(self, name="", call="", imo=0, ship_type=0,
                 destination="", length=0.0, width=0.0):
        self.name = name
        self.call = call
        self.imo = imo
        self.ship_type = ship_type
        self.destination = destination
        self.length = length
        self.width = width

    @property
    def group(self):
        return group(self.ship_type)


def parse_vessels(data):
    """{MMSI: Info} из ответа ais/v1/vessels."""
    out = {}
    for item in data if isinstance(data, list) else ():
        if not isinstance(item, dict) or item.get("mmsi") is None:
            continue
        a, b, c, d = (_number(item.get("referencePoint" + k)) or 0.0
                      for k in "ABCD")
        out[int(item["mmsi"])] = Info(
            (item.get("name") or "").strip(),
            (item.get("callSign") or "").strip(),
            int(item.get("imo") or 0), int(item.get("shipType") or 0),
            (item.get("destination") or "").strip(), a + b, c + d)
    return out


def label(key, info):
    """Подпись судна: название или MMSI."""
    if info is not None and info.name:
        return info.name
    return str(key)


def ship_size(info):
    """(ширина, длина, высота) модели в метрах: размеры AIS, без них -
    длина группы, ширина - шестая часть длины."""
    key = info.group if info is not None else "other"
    length = info.length if info is not None and 5.0 <= info.length <= 500.0 \
        else default_length(key)
    width = info.width if info is not None and 1.0 <= info.width <= 80.0 \
        else length / 6.0
    return width, length, width


def _prism(points, z0, z1):
    """Треугольники призмы над многоугольником points (против часовой
    стрелки) от z0 до z1, крышка веером."""
    out = []
    n = len(points)
    for k in range(1, n - 1):
        a, b, c = points[0], points[k], points[k + 1]
        out += [(a[0], a[1], z1), (b[0], b[1], z1), (c[0], c[1], z1)]
        out += [(a[0], a[1], z0), (c[0], c[1], z0), (b[0], b[1], z0)]
    for k in range(n):
        a, b = points[k], points[(k + 1) % n]
        out += [(a[0], a[1], z0), (b[0], b[1], z0), (b[0], b[1], z1),
                (a[0], a[1], z0), (b[0], b[1], z1), (a[0], a[1], z1)]
    return out


def unit_ship_parts(color):
    """Условное судно длиной 1 (ось Y, нос - +Y), шириной 1, высотой
    в долях ширины: корпус цвета группы с заострённым носом, надстройка
    белая у кормы, ватерлиния тёмная."""
    hull = [(-0.5, -0.5), (0.5, -0.5), (0.5, 0.28), (0.0, 0.5),
            (-0.5, 0.28)]
    parts = [(_prism(hull, 0.0, 0.08), DARK),
             (_prism(hull, 0.08, 0.35), color),
             (_prism([(-0.38, -0.46), (0.38, -0.46), (0.38, -0.22),
                      (-0.38, -0.22)], 0.35, 0.95), WHITE)]
    return [Part(np.asarray(points, dtype=np.float64), None, None, None,
                 tuple(rgba) + (1.0,)) for points, rgba in parts]
