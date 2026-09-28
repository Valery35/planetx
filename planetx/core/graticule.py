# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Координатная сетка: параллели и меридианы с подписями, без Qt.

Как «Вид - Сетка» Google Earth. Шаг сетки подбирается по ширине видимой
полосы, чтобы поперёк вида шло около LINES_ACROSS линий: из космоса
через 30°, у земли через минуты и секунды. Крупная сетка строится
на весь шар, мелкая - в окне вокруг точки взгляда. Параллель не дуга
большого круга, поэтому её вершины идут не реже SEGMENT градусов,
иначе сгущение по дуге выгнуло бы её к полюсу. Решение автора от
29 сентября 2026 года.
"""
import math

M_PER_DEGREE = 111320.0
LINES_ACROSS = 8  # линий поперёк видимой полосы, не меньше
# Шаги сетки в градусах, от крупного к мелкому.
STEPS = (30.0, 20.0, 10.0, 5.0, 2.0, 1.0, 0.5, 0.25,
         10 / 60.0, 5 / 60.0, 2 / 60.0, 1 / 60.0,
         30 / 3600.0, 15 / 3600.0, 10 / 3600.0, 5 / 3600.0, 2 / 3600.0,
         1 / 3600.0)
GLOBAL_STEP = 5.0  # с этого шага и крупнее сетка строится на весь шар
WINDOW = 3.0  # окно мелкой сетки - столько ширин видимой полосы
SEGMENT = 2.0  # градусов между вершинами параллели, не больше
MAX_LAT = 85.0  # сетка кончается там же, где тайлы
# Особые параллели, как в Google Earth: экватор, тропики и полярные
# круги. Наклон оси Земли на 2026 год - 23°26′10″, по IAU 2006.
TILT = 23.4362
CIRCLES = (("equator", 0.0), ("cancer", TILT), ("capricorn", -TILT),
           ("arctic", 90.0 - TILT), ("antarctic", TILT - 90.0))


def step_for(width):
    """Шаг сетки в градусах для видимой полосы шириной width метров."""
    wanted = width / LINES_ACROSS / M_PER_DEGREE
    fitting = [s for s in STEPS if s >= wanted]
    return min(fitting) if fitting else STEPS[0]


def _range(low, high, step):
    first = math.ceil(low / step - 1e-9)
    last = math.floor(high / step + 1e-9)
    return [n * step for n in range(first, last + 1)]


def extent(lat, lon, width, step):
    """Окно сетки (юг, север, запад, восток) в градусах. Крупный шаг -
    весь шар, мелкий - WINDOW ширин вокруг точки взгляда."""
    if step >= GLOBAL_STEP:
        return -MAX_LAT, MAX_LAT, -180.0, 180.0
    half = WINDOW * width / 2.0 / M_PER_DEGREE
    cos_lat = max(math.cos(math.radians(lat)), 0.05)
    south = max(-MAX_LAT, lat - half)
    north = min(MAX_LAT, lat + half)
    west, east = lon - half / cos_lat, lon + half / cos_lat
    if east - west >= 360.0:
        west, east = -180.0, 180.0
    return south, north, west, east


def lines(lat, lon, width):
    """Линии сетки: список (вид, значение, вершины (широта, долгота)).
    вид - "lat" у параллели и "lon" у меридиана."""
    step = step_for(width)
    south, north, west, east = extent(lat, lon, width, step)
    out = []
    # Экватор рисуется особой параллелью, см. circles.
    parallels = [v for v in _range(south, north, step)
                 if abs(v) <= MAX_LAT and abs(v) > 1e-9]
    seg = min(step, SEGMENT)
    lons = _lons(west, east, seg)
    for value in parallels:
        out.append(("lat", value, [(value, x) for x in lons]))
    lats = _range(south, north, seg)
    if not lats or lats[0] > south:
        lats = [south] + lats
    if lats[-1] < north:
        lats.append(north)
    # На весь шар меридиан 180° совпадает с -180°, он идёт один раз.
    stop = east if east - west < 360.0 else east - step / 2.0
    for value in _range(west, stop, step):
        out.append(("lon", value, [(y, value) for y in lats]))
    return step, out


def _lons(west, east, seg):
    """Долготы вершин параллели от west до east не реже seg."""
    lons = _range(west, east, seg)
    if not lons or lons[0] > west:
        lons = [west] + lons
    if lons[-1] < east:
        lons.append(east)
    return lons


def circles(lat, lon, width):
    """Особые параллели в окне сетки: (имя, широта, вершины).
    Подпись каждой стоит между меридианами возле точки взгляда."""
    step = step_for(width)
    south, north, west, east = extent(lat, lon, width, step)
    lons = _lons(west, east, min(step, SEGMENT))
    return [(name, value, [(value, x) for x in lons])
            for name, value in CIRCLES if south <= value <= north]


def circle_labels(lat, lon, width):
    """Подписи особых параллелей: (широта, долгота, имя)."""
    step = step_for(width)
    at_lon = (round(lon / step) + 0.5) * step
    return [(value, at_lon, name)
            for name, value, _ in circles(lat, lon, width)]


def labels(lat, lon, width):
    """Подписи: (широта, долгота, вид, значение). Параллели подписаны
    на меридиане возле точки взгляда, меридианы - на параллели."""
    step = step_for(width)
    south, north, west, east = extent(lat, lon, width, step)
    at_lon = round(lon / step) * step
    at_lat = min(MAX_LAT, max(-MAX_LAT, round(lat / step) * step))
    out = [(v, at_lon, "lat", v) for v in _range(south, north, step)
           if abs(v) <= MAX_LAT and abs(v) > 1e-9]
    # На весь шар меридиан 180° совпадает с -180°, он идёт один раз.
    stop = east if east - west < 360.0 else east - step / 2.0
    out += [(at_lat, v, "lon", v) for v in _range(west, stop, step)]
    return out


def key(lat, lon, width):
    """Ключ перестройки: сетка та же, пока ключ не меняется."""
    step = step_for(width)
    if step >= GLOBAL_STEP:
        return (step,)
    return step, round(lat / step), round(lon / step)


def angle_text(value, step):
    """Угол без знака: градусы, минуты и секунды по нужде шага.
    Полушарие подписывает окно, буквы зависят от языка."""
    value = abs(value)
    seconds = int(round(value * 3600.0))
    d, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    if step >= 1.0:
        return "{}°".format(d)
    if step >= 1 / 60.0 - 1e-12:
        return "{}°{:02d}′".format(d, m)
    return "{}°{:02d}′{:02d}″".format(d, m, s)


def normal_lon(value):
    """Долгота в пределах от -180 до 180."""
    return (value + 180.0) % 360.0 - 180.0
