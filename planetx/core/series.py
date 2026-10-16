# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Ряд снимков участка: значение индекса по датам сцен. Расчёт без Qt.

Просьба автора от 17 октября 2026 года, пункт списка возможностей
после 0.67.1 - «ряд снимков в точке графиком». Сцены - найденные окном
«Космоснимки» и видимые в его списке, то есть не облачнее заданного
над участком. У каждой сцены продукт считается по участку без облаков
и теней по маске сцены, на грубой сетке - не больше SERIES_PIXELS
пикселей по стороне. Точка графика - медиана участка, полоса - от 10-го
до 90-го процентиля. Медиана, а не среднее - остатки облаков, полосы
MSS и края снимка сдвигают её меньше.

Продукты ряда - индексы и температура, у сочетаний каналов одного
числа нет. У MODIS классы снега за 8 суток и день выгорания тоже не
величины для медианы. У ASTER маски облаков нет, ряда у него нет.
"""
import datetime
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import modis
    from . import sentinel as s2
except ImportError:  # headless-тесты
    import modis
    import sentinel as s2

SERIES_PIXELS = 200  # пикселей стороны участка при расчёте ряда
MIN_CLEAR = 10.0  # %, меньше чистых пикселей участка - сцена без точки
LOW, HIGH = 10.0, 90.0  # процентили полосы разброса
MODIS_SERIES = ("lst_day", "lst_night", "modis_ndvi", "modis_evi",
                "snow_cover")
EPOCH = datetime.date(1970, 1, 1)
MONTH_STEPS = (1, 2, 3, 6, 12, 24, 60, 120)
DAY_STEPS = (1, 2, 5, 7, 14)

Point = namedtuple("Point", "median low high share")
Point.__doc__ = """Сводка продукта по участку одной сцены: медиана,
10-й и 90-й процентили, доля пикселей участка со значением, %."""


def products(mission):
    """Продукты ряда спутника по порядку окна снимков, пусто - ряда
    нет."""
    if modis.is_modis(mission):
        return tuple(p for p in modis.products_of(mission)
                     if p in MODIS_SERIES)
    if mission not in ("sentinel2",) + s2.LANDSATS:
        return ()
    return tuple(p for p in s2.products_of(mission)
                 if p in s2.INDICES or p == "lst")


def step(xy, mission):
    """Шаг сетки ряда, м: шаг продукта спутника, но не мельче стороны
    участка, делённой на SERIES_PIXELS."""
    box = s2.bounds(xy, 1.0)
    side = max(box[2] - box[0], box[3] - box[1])
    native = modis.step(mission) if modis.is_modis(mission) \
        else s2.step_for(xy, mission)
    return max(native, math.ceil(side / SERIES_PIXELS))


def point(values, area, clear):
    """Сводка продукта по участку. values - массив продукта, area -
    пиксели участка, clear - пиксели без облаков, теней и пропусков.
    Point или None, если чистых значений меньше MIN_CLEAR % участка."""
    values = np.asarray(values, dtype=np.float64)
    total = int(np.count_nonzero(area))
    if total == 0:
        return None
    chosen = values[area & clear & np.isfinite(values)]
    share = 100.0 * chosen.size / total
    if share < MIN_CLEAR:
        return None
    low, median, high = np.percentile(chosen, [LOW, 50.0, HIGH])
    return Point(float(median), float(low), float(high), float(share))


def day_number(when):
    """Сутки от 1970-01-01 по времени сцены «ГГГГ-ММ-ДД ЧЧ:ММ», с долей
    суток."""
    date = datetime.date(int(when[0:4]), int(when[5:7]), int(when[8:10]))
    hours = 0.0
    if len(when) >= 16:
        hours = int(when[11:13]) + int(when[14:16]) / 60.0
    return (date - EPOCH).days + hours / 24.0


def _date(day):
    return EPOCH + datetime.timedelta(days=int(math.floor(day)))


def date_ticks(first, last, count=6):
    """Деления оси дат между сутками first и last: [(сутки, подпись)].
    Шаг - сутки (1, 2, 5, 7, 14) при коротком промежутке, иначе месяцы
    (1, 2, 3, 6, 12 и больше), около count делений. Подпись - год у шага
    в год и больше, год и месяц у шага в месяцы, дата у шага в сутки."""
    span = max(last - first, 1.0)
    if span / 30.0 < count:
        for size in DAY_STEPS:
            if span / size <= count:
                break
        start = math.ceil(first / size) * size
        out = []
        day = start
        while day <= last:
            out.append((float(day), _date(day).isoformat()))
            day += size
        return out
    months = span / 30.44
    size = next((m for m in MONTH_STEPS if months / m <= count),
                MONTH_STEPS[-1])
    begin = _date(first)
    index = begin.year * 12 + begin.month - 1
    if begin.day > 1:
        index += 1
    index = int(math.ceil(index / size) * size)
    out = []
    while True:
        date = datetime.date(index // 12, index % 12 + 1, 1)
        day = float((date - EPOCH).days)
        if day > last:
            return out
        label = str(date.year) if size % 12 == 0 \
            else "{:04d}-{:02d}".format(date.year, date.month)
        out.append((day, label))
        index += size


def csv_text(rows, title):
    """Ряд для таблицы: строки (время сцены, Point или None) в текст CSV
    с заголовком. Сцена без значения - пустые поля."""
    lines = ["date,scene,median,p10,p90,clear_percent,product"]
    for when, scene, value in rows:
        if value is None:
            lines.append('{},{},,,,,"{}"'.format(when, scene, title))
            continue
        lines.append('{},{},{:.4f},{:.4f},{:.4f},{:.1f},"{}"'.format(
            when, scene, value.median, value.low, value.high, value.share,
            title))
    return "\n".join(lines) + "\n"
