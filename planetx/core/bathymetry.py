# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Своя батиметрия: растр глубин водоёма в рельеф глобуса и вода на
уровне водоёма. Расчёт без Qt.

Просьба автора от 10 октября 2026 года - «батиметрию свою, чтобы
врезать можно было», выбор того же дня - растр глубин с уровнем воды
или растр отметок дна, полупрозрачная вода на уровне водоёма. Растр
врезается в высоты глобуса как врезка своего рельефа (ui/inset.py),
глубины перед этим пересчитываются в отметки дна (to_bed). Вода -
отдельная сетка на уровне водоёма над узлами, где дно ниже уровня
(water_part), её рисует вид после поверхности (render/subsurface.py,
glass): шейдер воды тайлов знает только уровень моря.

Глубина в растре бывает со знаком плюс или минус вниз, берётся её
модуль. Настройки слоёв - запись проекта строкой JSON
{номер слоя: {"kind": "depth" или "bed", "level": уровень, м}}.
"""
import json
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import subsurface
except ImportError:  # headless-тесты
    import subsurface

KINDS = ("depth", "bed")
# Цвет воды - как у моря в шейдере тайла (0.09, 0.30, 0.55), альфа
# 0.5. Выбор помощника, утверждает автор.
WATER_COLOR = (23, 77, 140, 128)
# Узел у берега с дном выше уровня на столько ещё под водой: нулевая
# глубина растра - берег, вода доходит до него.
SHORE = 0.05
# Узлов сетки воды по стороне, не больше.
WATER_SIDE = 256


def to_bed(values, kind, level):
    """Отметки дна из значений растра: у глубин - уровень минус модуль
    глубины, у отметок - сами значения. NaN остаётся NaN."""
    values = np.asarray(values, dtype=np.float64)
    if kind == "depth":
        return float(level) - np.abs(values)
    return values


def parse(text):
    """Настройки слоёв из строки JSON: {номер: (вид, уровень)}.
    Неверные записи пропускаются."""
    try:
        data = json.loads(text or "{}")
    except ValueError:
        return {}
    out = {}
    if not isinstance(data, dict):
        return out
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        kind = value.get("kind")
        level = value.get("level")
        if kind in KINDS and isinstance(level, (int, float)) \
                and math.isfinite(level):
            out[str(key)] = (kind, float(level))
    return out


def dump(settings):
    """Строка JSON настроек {номер: (вид, уровень)}."""
    return json.dumps({key: {"kind": kind, "level": level}
                       for key, (kind, level) in settings.items()},
                      sort_keys=True)


def mercator_latlon(x, y):
    """Широта и долгота точек EPSG:3857, градусы."""
    radius = 6378137.0
    lon = np.degrees(np.asarray(x, dtype=np.float64) / radius)
    lat = np.degrees(2.0 * np.arctan(np.exp(np.asarray(y, np.float64)
                                            / radius)) - math.pi / 2.0)
    return lat, lon


def water_part(lats, lons, bed, level, height, color=WATER_COLOR):
    """Поверхность воды на высоте height (уровень на экране) над узлами
    сетки (rows, cols), где дно ниже уровня level: subsurface.Part или
    None, если воды нет."""
    bed = np.asarray(bed, dtype=np.float64)
    wet = np.isfinite(bed) & (bed < float(level) + SHORE)
    if not wet.any():
        return None
    tris = subsurface.grid_triangles(wet)
    if not len(tris):
        return None
    positions = subsurface.ecef(np.ravel(lats), np.ravel(lons),
                                np.full(bed.size, float(height)))
    normals = subsurface._unit(positions)
    colors = subsurface._rgba(color, len(positions))
    return subsurface.Part(positions, normals, colors,
                           tris.astype(np.uint32))
