# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разрез вниз вдоль линии. Без Qt.

Шаг 4 плана «сверху вниз», 2 октября 2026 года. Вдоль пути из «Моих
меток» или линейки собирается вертикальный разрез Земли до заданной
глубины:

- кора CRUST1.0 по точкам линии (core/crust.py), без модели - слой
  PREM до Мохо 24.4 км;
- оболочки PREM ниже Мохо (core/cutaway.SHELLS);
- погружающиеся плиты Slab2 полосой с толщиной (core/slabs.band);
- очаги землетрясений в полосе шириной width по обе стороны линии,
  перенесённые на разрез по ближайшей точке линии.

Точки линии идут по дугам большого круга между вершинами, равномерно
по длине. Расстояния - по шару среднего радиуса Земли, на разрезах
в сотни и тысячи километров ошибка от сжатия меньше полупроцента.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .cutaway import (CRUST_COLORS, PREM_RADIUS, SHELLS, SLAB_COLOR,
                          crust_layers)
    from .slabs import band
    from .subsurface import merge, wall
except ImportError:  # headless-тесты
    import ellipsoid
    from cutaway import (CRUST_COLORS, PREM_RADIUS, SHELLS, SLAB_COLOR,
                         crust_layers)
    from slabs import band
    from subsurface import merge, wall

SAMPLES = 600  # точек вдоль линии
WALL_ALPHA = 220  # непрозрачность стенки на глобусе, выбор помощника
DEPTHS = (100.0, 300.0, 700.0, 2891.0, PREM_RADIUS)  # км, выбор окна
DEPTH = 700.0  # км, глубина по умолчанию - низ переходной зоны
WIDTH = 100.0  # км, полоса очагов по обе стороны линии вместе

Section = namedtuple(
    "Section", "distance lats lons bounds slab_top slab_bottom quakes depth")
Section.__doc__ = """Разрез: distance - км от начала линии, lats, lons -
точки линии, bounds - отметки границ коры CRUST1.0 (n, 9) в км или None,
slab_top, slab_bottom - плита в км глубины или NaN, quakes - список
(км вдоль линии, глубина км, магнитуда, событие), depth - глубина низа
разреза, км."""


def _unit(lats, lons):
    lat = np.radians(np.asarray(lats, dtype=np.float64))
    lon = np.radians(np.asarray(lons, dtype=np.float64))
    return np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon),
                     np.sin(lat)], axis=-1)


def _latlon(units):
    lats = np.degrees(np.arcsin(np.clip(units[:, 2], -1.0, 1.0)))
    lons = np.degrees(np.arctan2(units[:, 1], units[:, 0]))
    return lats, lons


def radius_km():
    """Средний радиус тела, км: (2a + b) / 3."""
    return (2.0 * ellipsoid.A + ellipsoid.B) / 3.0 / 1000.0


def along(points, count=SAMPLES):
    """Точки вдоль ломаной points [(широта, долгота)] по дугам большого
    круга: (км от начала, широты, долготы). Шаг одинаковый по длине."""
    if len(points) < 2:
        return None
    units = _unit([p[0] for p in points], [p[1] for p in points])
    angles = np.arccos(np.clip(np.einsum("ij,ij->i", units[:-1],
                                         units[1:]), -1.0, 1.0))
    total = float(angles.sum())
    if total <= 0.0:
        return None
    marks = np.concatenate([[0.0], np.cumsum(angles)])
    want = np.linspace(0.0, total, count)
    seg = np.clip(np.searchsorted(marks, want, side="right") - 1, 0,
                  len(angles) - 1)
    out = np.empty((count, 3))
    for k in range(len(angles)):
        pick = seg == k
        if not np.any(pick):
            continue
        a, b = units[k], units[k + 1]
        omega = angles[k]
        t = (want[pick] - marks[k]) / omega if omega > 0.0 \
            else np.zeros(int(pick.sum()))
        if omega < 1e-12:
            out[pick] = a
            continue
        sa = np.sin((1.0 - t) * omega) / math.sin(omega)
        sb = np.sin(t * omega) / math.sin(omega)
        out[pick] = sa[:, None] * a + sb[:, None] * b
    lats, lons = _latlon(out)
    return want * radius_km(), lats, lons


def near(quakes, lats, lons, distance, width=WIDTH):
    """Очаги в полосе ширины width км вдоль точек линии: список
    (км вдоль линии, глубина, магнитуда, событие). Ближайшая точка
    линии ищется среди точек разреза, их шаг меньше ширины полосы на
    любой разумной линии."""
    if not quakes:
        return []
    line = _unit(lats, lons)
    events = _unit([q.lat for q in quakes], [q.lon for q in quakes])
    dots = events @ line.T
    nearest = np.argmax(dots, axis=1)
    gap = np.arccos(np.clip(dots[np.arange(len(quakes)), nearest], -1.0,
                            1.0)) * radius_km()
    # Очаг за концом линии не берётся: его ближайшая точка - конец, но
    # он лежит дальше конца на расстояние больше полосы.
    out = []
    for q, i, g in zip(quakes, nearest, gap):
        if g <= width / 2.0:
            out.append((float(distance[i]), float(q.depth), float(q.mag), q))
    return out


def build(points, crust=None, zones=(), quakes=(), depth=DEPTH,
          width=WIDTH, count=SAMPLES):
    """Разрез вдоль points или None, если точек меньше двух."""
    found = along(points, count)
    if found is None:
        return None
    distance, lats, lons = found
    bounds = crust.at(lats, lons).astype(np.float64) \
        if crust is not None else None
    if zones:
        top, bottom = band(list(zones), lats, lons)
    else:
        top = np.full(len(lats), np.nan)
        bottom = np.full(len(lats), np.nan)
    return Section(distance, lats, lons, bounds, top, bottom,
                   near(list(quakes), lats, lons, distance, width),
                   float(depth))


def moho(section):
    """Глубина Мохо вдоль линии, км: по CRUST1.0 или 24.4 км PREM."""
    if section.bounds is not None:
        return -section.bounds[:, -1]
    crust_top = [s for s in SHELLS if s[0] == "crust"][0]
    return np.full(len(section.distance), PREM_RADIUS - crust_top[1])


def shells_below(section):
    """Оболочки PREM ниже Мохо в пределах глубины разреза: (ключ,
    верх км, низ км, цвет), сверху вниз. У верхней мантии верх - Мохо,
    его даёт moho(section)."""
    out = []
    for key, low, high, color in reversed(SHELLS):
        if key == "crust":
            continue
        top, bottom = PREM_RADIUS - high, PREM_RADIUS - low
        if top >= section.depth:
            continue
        out.append((key, top, min(bottom, section.depth), color))
    return out


def wall_mesh(section, alpha=WALL_ALPHA):
    """Стенка разреза на глобусе: вертикальные полосы слоёв вдоль линии
    от поверхности до глубины разреза, core.subsurface.Mesh или None.
    Глубины настоящие, в метрах ниже уровня моря. Слой без толщины
    в точке пропускается."""
    n = len(section.distance)
    lats, lons = section.lats, section.lons
    limit = section.depth

    def part(top, bottom, color):
        # Глубины км вниз -> высоты м, обрезка по глубине разреза. Пустое
        # место - нулевая толщина, такую полосу wall пропускает.
        top = np.minimum(np.asarray(top, dtype=np.float64), limit)
        bottom = np.minimum(np.asarray(bottom, dtype=np.float64), limit)
        empty = ~(np.isfinite(top) & np.isfinite(bottom))
        top = np.where(empty, 0.0, top)
        bottom = np.where(empty, 0.0, bottom)
        return wall(lats, lons, -top * 1000.0, -bottom * 1000.0,
                    tuple(color) + (alpha,))

    parts = []
    base = moho(section)
    for key, top, bottom, color in shells_below(section):
        upper = base if key == "upper_mantle" else np.full(n, top)
        parts.append(part(upper, np.full(n, bottom), color))
    if section.bounds is not None:
        depths = -section.bounds
        for k, key in enumerate(crust_layers()):
            parts.append(part(depths[:, k], depths[:, k + 1],
                              CRUST_COLORS[key]))
    else:
        crust = [c for c in SHELLS if c[0] == "crust"][0]
        parts.append(part(np.zeros(n), base, crust[3]))
    parts.append(part(section.slab_top, section.slab_bottom, SLAB_COLOR))
    return merge(parts, key="section")
