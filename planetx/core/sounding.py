# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Батиметрия по промерам эхолота: точки глубин в грид. Расчёт без Qt.

Просьба автора от 10 октября 2026 года - «батиметрия с эхолота».
Промеры - точечный слой проекта с глубиной в поле или в Z точки,
обычно галсы - линии точек через метры вдоль хода и через десятки
метров между галсами. Грид строит триангуляция GDAL (gdal.Grid,
linear) в метрах зоны UTM середины промеров, ячейки дальше предела от
ближайшего промера пустые - так грид не заливает берег и заливы без
промеров. Готовый грид глубин ложится своей батиметрией
(core/bathymetry.py) с уровнем воды водоёма.

Шаг грида по умолчанию - корень из площади промеров на точку, округлённый
до 1, 2 или 5 × 10ⁿ м: у галсов через 20 м с точкой через метр это
около 5 м. Предел - MAX_GAP_CELLS шагов. Выбор помощника, утверждает
автор.
"""
import math

import numpy as np

MIN_CELL = 0.5  # м, мельче шаг не бывает
MAX_CELLS = 4000 * 4000  # ячеек грида, не больше
MAX_GAP_CELLS = 10  # предел от ближайшего промера, шагов грида
NODATA = -9999.0


def nice_step(value):
    """Ближайшее сверху из 1, 2, 2.5, 5 × 10ⁿ."""
    if not value > 0.0:
        return 1.0
    power = 10.0 ** math.floor(math.log10(value))
    for base in (1.0, 2.0, 2.5, 5.0, 10.0):
        if base * power >= value * (1.0 - 1e-9):
            return base * power
    return 10.0 * power


def auto_cell(xs, ys):
    """Шаг грида в метрах по рамке и количеству точек (x, y в метрах)."""
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    if len(xs) < 3:
        return 1.0
    width = float(xs.max() - xs.min())
    height = float(ys.max() - ys.min())
    area = max(width * height, 1.0)
    # Площадь промеров - занятые клетки вдвое крупнее среднего шага по
    # рамке: у вытянутого озера рамка в основном пустая.
    coarse = 2.0 * math.sqrt(area / len(xs))
    cells = np.unique(np.stack([np.floor((xs - xs.min()) / coarse),
                                np.floor((ys - ys.min()) / coarse)]),
                      axis=1).shape[1]
    cell = math.sqrt(min(area, cells * coarse * coarse) / len(xs))
    # Грид не больше MAX_CELLS ячеек.
    cell = max(cell, math.sqrt(area / MAX_CELLS), MIN_CELL)
    return nice_step(cell)


def grid_frame(xs, ys, cell):
    """Рамка грида (запад, юг, восток, север) по точкам с полями в шаг
    и размеры (столбцов, строк). Края кратны шагу."""
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    west = math.floor(xs.min() / cell) * cell - cell
    south = math.floor(ys.min() / cell) * cell - cell
    east = math.ceil(xs.max() / cell) * cell + cell
    north = math.ceil(ys.max() / cell) * cell + cell
    cols = int(round((east - west) / cell))
    rows = int(round((north - south) / cell))
    return (west, south, east, north), (cols, rows)


def clean(xs, ys, zs):
    """Точки с конечными координатами и глубиной, глубина - модуль:
    у эхолотов она бывает и со знаком минус."""
    xs = np.asarray(xs, dtype=np.float64)
    ys = np.asarray(ys, dtype=np.float64)
    zs = np.asarray(zs, dtype=np.float64)
    ok = np.isfinite(xs) & np.isfinite(ys) & np.isfinite(zs)
    return xs[ok], ys[ok], np.abs(zs[ok])


def masked(depths, distance, limit):
    """Глубины грида с NODATA там, где до промера дальше limit или
    глубины нет."""
    depths = np.array(depths, dtype=np.float32)
    distance = np.asarray(distance, dtype=np.float64)
    bad = ~np.isfinite(depths) | (depths == NODATA) | (distance > limit)
    depths[bad] = NODATA
    return depths
