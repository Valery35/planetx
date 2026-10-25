# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карта тренда по ряду снимков: в каждом пикселе наклон Тейла-Сена
и тест Манна-Кендалла по значениям сцен ряда. Расчёт без Qt.

Наклон Тейла-Сена - медиана наклонов по всем парам сцен пикселя,
в единицах величины за год. Остатки облаков и выбросы его почти
не сдвигают, в отличие от наклона по методу наименьших квадратов.
Тест Манна-Кендалла - есть ли монотонный тренд: S - сумма знаков
разностей пар, дисперсия - n(n-1)(2n+5)/18 без поправки на равные
значения, Z с поправкой на непрерывность, p - двусторонняя по
нормальному распределению. Сезонный ход ряда тест не вычитает: ряд из
сцен одного сезона даёт тренд между годами, ряд всех месяцев -
смешивает сезон и тренд.

Пиксель без MIN_SCENES чистых значений тренда не получает. Пары
считаются частями по CHUNK пикселей, чтобы матрица пар не занимала
сотни мегабайт.
"""
import math

import numpy as np

MIN_SCENES = 6  # чистых значений пикселя, меньше - тренда нет
CHUNK = 4096  # пикселей в части расчёта
YEAR = 365.25  # суток в году
SIGNIFICANT = 0.05  # p, ниже которой тренд значим


def trend(stack, days, min_scenes=MIN_SCENES):
    """stack - массив (сцены, строки, столбцы) с NaN вне чистых
    пикселей, days - сутки сцен. Возвращает (наклон за год, p, n) -
    массивы (строки, столбцы), у пикселя без тренда наклон и p - NaN."""
    stack = np.asarray(stack, dtype=np.float64)
    days = np.asarray(days, dtype=np.float64)
    count, rows, cols = stack.shape
    flat = stack.reshape(count, rows * cols)
    slope = np.full(rows * cols, np.nan)
    p_value = np.full(rows * cols, np.nan)
    valid = np.isfinite(flat)
    n = valid.sum(axis=0)
    first, second = np.triu_indices(count, 1)
    gap = (days[second] - days[first]) / YEAR
    usable = gap != 0.0
    first, second, gap = first[usable], second[usable], gap[usable]
    for start in range(0, rows * cols, CHUNK):
        part = slice(start, start + CHUNK)
        enough = n[part] >= min_scenes
        if not enough.any():
            continue
        values = flat[:, part][:, enough]
        diff = values[second] - values[first]
        slopes = diff / gap[:, None]
        with np.errstate(invalid="ignore"):
            index = np.nonzero(enough)[0] + start
            slope[index] = np.nanmedian(slopes, axis=0)
            s = np.nansum(np.sign(diff), axis=0)
        p_value[index] = _p_value(s, n[index])
    return (slope.reshape(rows, cols), p_value.reshape(rows, cols),
            n.reshape(rows, cols))


def _p_value(s, n):
    """Двусторонняя p теста Манна-Кендалла по S и количеству n."""
    n = np.asarray(n, dtype=np.float64)
    variance = n * (n - 1.0) * (2.0 * n + 5.0) / 18.0
    z = np.where(s > 0, s - 1.0, np.where(s < 0, s + 1.0, 0.0)) \
        / np.sqrt(np.maximum(variance, 1e-12))
    erfc = np.vectorize(math.erfc, otypes=[np.float64])
    return erfc(np.abs(z) / math.sqrt(2.0))


def limits(slope, share=98.0):
    """Симметричные пределы шкалы наклона по процентилю модулей: шкала
    от -a до a, a - процентиль share модулей наклона."""
    values = np.abs(slope[np.isfinite(slope)])
    if not values.size:
        return -1.0, 1.0
    top = float(np.percentile(values, share)) or float(values.max()) or 1.0
    return -top, top
