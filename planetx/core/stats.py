# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сводка значений участка: среднее, разброс и квантили.

Просьба пользователя Василия Швалёва от 29 октября 2026 года - не только
сумма, но и среднее, разброс и квантили. Слово автора - окна прежние,
сводка общая. Значения - растр расчёта любого окна анализа, NaN и
бесконечность в сводку не идут.
"""
from collections import namedtuple

import numpy as np

Summary = namedtuple("Summary",
                     "count mean std low p10 q1 median q3 p90 high")
Summary.__doc__ = """Сводка: count - значений, mean - среднее, std -
стандартное отклонение, low и high - края, p10, q1, median, q3, p90 -
квантили 10, 25, 50, 75 и 90 %."""

QUANTILES = (10.0, 25.0, 50.0, 75.0, 90.0)


def describe(values):
    """Сводка конечных значений массива или None, если их нет."""
    data = np.asarray(values, dtype=np.float64)
    data = data[np.isfinite(data)]
    if data.size == 0:
        return None
    p10, q1, median, q3, p90 = np.percentile(data, QUANTILES)
    return Summary(int(data.size), float(data.mean()), float(data.std()),
                   float(data.min()), float(p10), float(q1), float(median),
                   float(q3), float(p90), float(data.max()))


def rounded(value):
    """Запись значения - три значащие цифры, большие без дробной части."""
    size = abs(value)
    if size >= 100.0:
        return "{:.0f}".format(value)
    if size >= 10.0:
        return "{:.1f}".format(value)
    return "{:.2f}".format(value)
