# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Самолёты вживую по ADS-B сети adsb.lol. Просьба автора от
19 октября 2026 года.

Расчёт без Qt. Запрос - борта в круге у точки взгляда
(v2/point/{широта}/{долгота}/{радиус в морских милях}, не больше 250),
ответ в разметке readsb: hex, позывной, бортовой номер, тип, высота
по барометру и по GNSS в футах или «ground», путевая скорость в узлах,
путевой угол, курс, вертикальная скорость в футах в минуту, крен,
категория ADS-B, давность положения. Без ключа. Лицензия выдачи
у adsb.lol не названа, запрос о ней автор отправил 19 октября 2026
года. Над Россией сеть добровольцев почти пуста.

Модель - условный самолёт длиной 1 вдоль оси Y, его растягивает
масштаб по категории (unit_plane_parts, plane_size).
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .models import Part
    from .movers import FOOT, KNOT, Sample
except ImportError:  # headless-тесты
    from models import Part
    from movers import FOOT, KNOT, Sample

POINT_URL = "https://api.adsb.lol/v2/point/{lat:.4f}/{lon:.4f}/{radius}"
ATTRIBUTION = ("Aircraft: adsb.lol", "https://www.adsb.lol/")
MAX_RADIUS = 250  # морских миль, предел службы
MIN_RADIUS = 5
POLL = 10.0
EXTRAPOLATE = 30.0
STALE = 120.0
NM = 1852.0
# Категории ADS-B: группа, длина условной модели, м, цвет киля 0-1.
# Выбор помощника.
GROUPS = (("light", ("A1",), 9.0, (0.30, 0.75, 0.35)),
          ("small", ("A2", "A6"), 16.0, (0.15, 0.75, 0.85)),
          ("large", ("A3", "A4"), 38.0, (0.20, 0.45, 0.90)),
          ("heavy", ("A5",), 64.0, (0.62, 0.30, 0.85)),
          ("rotor", ("A7",), 14.0, (0.96, 0.58, 0.14)),
          ("other", (), 30.0, (0.75, 0.75, 0.75)))
WHITE = (0.93, 0.94, 0.95)
GREY = (0.70, 0.72, 0.75)


def group(category):
    for name, codes, _, _ in GROUPS:
        if category in codes:
            return name
    return "other"


def group_color(key):
    for name, _, _, color in GROUPS:
        if name == key:
            return color
    return GROUPS[-1][3]


def plane_size(category):
    """(размах, длина, высота) модели, м, по категории."""
    key = group(category)
    length = next(size for name, _, size, _ in GROUPS if name == key)
    return length, length, length


def point_url(lat, lon, radius_m):
    """Адрес бортов в круге radius_m метров у точки."""
    radius = int(min(max(math.ceil(radius_m / NM), MIN_RADIUS),
                     MAX_RADIUS))
    return POINT_URL.format(lat=lat, lon=lon, radius=radius)


def _number(value):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class Info:
    """Сведения о борте: позывной, бортовой номер, тип, категория,
    на земле ли он."""

    def __init__(self, flight="", reg="", kind="", category="",
                 ground=False, squawk=""):
        self.flight = flight
        self.reg = reg
        self.kind = kind
        self.category = category
        self.ground = ground
        self.squawk = squawk

    @property
    def group(self):
        return group(self.category)


def parse(data):
    """(список movers.Sample, {hex: Info}) из ответа adsb.lol. Высота
    борта на земле - NaN, его ставит на рельеф окно."""
    samples, info = [], {}
    if not isinstance(data, dict):
        return samples, info
    now = _number(data.get("now"))
    for ac in data.get("ac") or ():
        if not isinstance(ac, dict) or not ac.get("hex"):
            continue
        lat, lon = _number(ac.get("lat")), _number(ac.get("lon"))
        if lat is None or lon is None or now is None:
            continue
        seen = _number(ac.get("seen_pos"))
        if seen is None:
            seen = _number(ac.get("seen")) or 0.0
        key = str(ac["hex"]).strip().lower()
        ground = ac.get("alt_baro") == "ground"
        feet = _number(ac.get("alt_geom"))
        if feet is None:
            feet = _number(ac.get("alt_baro"))
        alt = math.nan if ground or feet is None else max(feet * FOOT, 0.0)
        rate = _number(ac.get("geom_rate"))
        if rate is None:
            rate = _number(ac.get("baro_rate")) or 0.0
        track = _number(ac.get("track"))
        heading = _number(ac.get("true_heading"))
        samples.append(Sample(
            key, now / 1000.0 - seen, lat, lon,
            (_number(ac.get("gs")) or 0.0) * KNOT,
            math.nan if track is None else track,
            math.nan if heading is None else heading, alt,
            0.0 if ground else rate * FOOT / 60.0,
            _number(ac.get("roll")) or 0.0))
        info[key] = Info((ac.get("flight") or "").strip(),
                         (ac.get("r") or "").strip(),
                         (ac.get("t") or "").strip(),
                         (ac.get("category") or "").strip(), ground,
                         (ac.get("squawk") or "").strip())
    return samples, info


def label(key, info):
    """Подпись борта: позывной, иначе бортовой номер, иначе hex."""
    if info is not None and info.flight:
        return info.flight
    if info is not None and info.reg:
        return info.reg
    return key.upper()


def _box(x0, x1, y0, y1, z0, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6),
             (1, 2, 6, 5), (3, 0, 4, 7))
    out = []
    for a, b, c, d in faces:
        out += [v[a], v[b], v[c], v[a], v[c], v[d]]
    return out


def unit_plane_parts(color):
    """Условный самолёт длиной 1 (ось Y, нос - +Y), размахом 1:
    фюзеляж, крыло, стабилизатор белые, киль цвета группы. Точка
    модели - середина фюзеляжа по высоте."""
    body = _box(-0.05, 0.05, -0.5, 0.42, -0.05, 0.05) \
        + _box(-0.03, 0.03, 0.42, 0.5, -0.03, 0.03)
    wings = _box(-0.5, 0.5, -0.06, 0.1, -0.012, 0.012) \
        + _box(-0.17, 0.17, -0.5, -0.41, 0.0, 0.015)
    fin = _box(-0.008, 0.008, -0.5, -0.38, 0.05, 0.2)
    parts = [(body, WHITE), (wings, GREY), (fin, color)]
    return [Part(np.asarray(points, dtype=np.float64), None, None, None,
                 tuple(rgba) + (1.0,)) for points, rgba in parts]
