# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Землетрясения: разбор сводки USGS, цвет по глубине, размер по
магнитуде, точки очагов и эпицентров. Расчёт без Qt.

Второй пункт списка «непрерывной вертикали», просьба автора от 2 октября
2026 года. Источник - сводки каталога USGS в GeoJSON (FEED), данные
USGS в общественном достоянии США. Координаты события - долгота,
широта и глубина очага в километрах ниже уровня моря.

Очаг рисуется на своей глубине, высота на экране - как у подземного
режима (core.subsurface.display): отметка, умноженная на масштаб
рельефа. Эпицентр - точка рельефа над очагом, от неё к очагу идёт
линия. Цвет по глубине - шкала DEPTH_STOPS, мелкие очаги красные,
глубокие синие и лиловые, как на картах USGS. Размер точки растёт
с магнитудой.
"""
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import geodetic_to_ecef, surface_normal
    from .subsurface import display
except ImportError:  # headless-тесты
    from ellipsoid import geodetic_to_ecef, surface_normal
    from subsurface import display

FEED = ("https://earthquake.usgs.gov/earthquakes/feed/v1.0/summary/"
        "4.5_month.geojson")
ATTRIBUTION = ("Earthquakes: USGS",
               "https://earthquake.usgs.gov/earthquakes/feed/")
# Глубина очага, км - цвет. Выбор помощника, утверждает автор.
DEPTH_STOPS = ((0.0, (230, 40, 30)), (70.0, (255, 150, 0)),
               (150.0, (250, 225, 0)), (300.0, (60, 190, 80)),
               (500.0, (40, 120, 230)), (700.0, (120, 60, 200)))
DEPTH_TICKS = (0, 150, 300, 500, 700)  # подписи шкалы, км
MIN_MAG = 4.5  # магнитуда самой маленькой точки
MIN_SIZE = 4.0  # логических пикселей
SIZE_PER_MAG = 3.0  # логических пикселей на единицу магнитуды
MAX_SIZE = 22.0

Quake = namedtuple("Quake", "lat lon depth mag time place url")
Quake.__doc__ = """Событие: широта, долгота, глубина очага в км, магнитуда,
время в секундах UTC, название места, адрес страницы события."""


def parse(data):
    """События из GeoJSON сводки USGS. Событие без координат или
    магнитуды пропускается."""
    out = []
    for feature in (data or {}).get("features", []):
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        props = feature.get("properties") or {}
        values = _numbers(list(coords[:3]) + [props.get("mag")])
        if len(coords) < 3 or values is None:
            continue
        lon, lat, depth, mag = values
        time = props.get("time")
        out.append(Quake(lat, lon, depth, mag,
                         None if time is None else float(time) / 1000.0,
                         str(props.get("place") or ""),
                         str(props.get("url") or "")))
    return out


def _numbers(values):
    """Значения числами или None, если хоть одно не число."""
    out = []
    for value in values:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        out.append(float(value))
    return out


def depth_colors(depths):
    """Цвета очагов по глубине (n, 3) uint8, шкала DEPTH_STOPS."""
    depths = np.asarray(depths, dtype=np.float64)
    bounds = np.array([s[0] for s in DEPTH_STOPS])
    colors = np.array([s[1] for s in DEPTH_STOPS], dtype=np.float64)
    rgb = np.stack([np.interp(depths, bounds, colors[:, c])
                    for c in range(3)], axis=-1)
    return np.rint(rgb).astype(np.uint8)


def sizes(mags):
    """Размер точки в логических пикселях по магнитуде."""
    mags = np.asarray(mags, dtype=np.float64)
    return np.clip(MIN_SIZE + SIZE_PER_MAG * (mags - MIN_MAG), MIN_SIZE,
                   MAX_SIZE)


def points(quakes, scale, ground, depth_map=None):
    """Очаги и эпицентры в ECEF (n, 3). ground(lats, lons) - настоящие
    отметки рельефа, эпицентр лежит на рельефе, очаг - на глубине.
    depth_map(глубины в км) - глубины на экране, при выделении коры
    разреза (core.cutaway.stretch), иначе None."""
    lat = np.array([q.lat for q in quakes], dtype=np.float64)
    lon = np.array([q.lon for q in quakes], dtype=np.float64)
    depth = np.array([q.depth for q in quakes], dtype=np.float64)
    if depth_map is not None:
        depth = np.asarray(depth_map(depth), dtype=np.float64)
    g = np.asarray(ground(lat, lon), dtype=np.float64) if len(lat) \
        else np.zeros(0)
    focus = geodetic_to_ecef(lat, lon, display(-depth * 1000.0, scale, g))
    epicenter = geodetic_to_ecef(lat, lon, display(g, scale, g))
    return focus, epicenter


def times(quakes):
    """Времена событий, секунды UTC, массив. Без времени - NaN."""
    return np.array([np.nan if q.time is None else q.time
                     for q in quakes], dtype=np.float64)


def in_window(seconds, span):
    """Признак «событие в промежутке шкалы времени» span = (от, до)
    или None - шкала закрыта, видно всё. Событие без времени видно
    всегда, как метка без времени."""
    seconds = np.asarray(seconds, dtype=np.float64)
    if span is None:
        return np.ones(seconds.shape, dtype=bool)
    lo, hi = span
    known = ~np.isnan(seconds)
    inside = np.zeros(seconds.shape, dtype=bool)
    inside[known] = (seconds[known] >= lo) & (seconds[known] <= hi)
    return inside | ~known


def span(quakes):
    """Самое раннее и самое позднее время событий или None."""
    values = times(quakes)
    values = values[~np.isnan(values)]
    if not len(values):
        return None
    return float(values.min()), float(values.max())


def facing(eye, epicenters, lats, lons):
    """Признак «эпицентр на видимой стороне»: глаз над касательной
    плоскостью в эпицентре. Очаги за горизонтом не рисуются, иначе они
    просвечивали бы сквозь всю Землю."""
    up = surface_normal(lats, lons)
    to_eye = np.asarray(eye, dtype=np.float64) - epicenters
    return np.einsum("ij,ij->i", up, to_eye) > 0.0
