# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Часы глобуса: ход момента шкалы времени в реальном времени.

Солнце, спутники и светила неба зависят от момента, а не от данных.
Для них шкала времени нужна и без меток: охват шкалы - окно HALF
вокруг момента вместе с охватом данных. Показ идёт со скоростью RATE,
во сколько раз быстрее часов. Дойдя до края окна, охват сдвигается
вслед за моментом, время не кончается. Без таких строк шкала
по-прежнему проходит охват данных и встаёт на его конце.
"""

HALF = 86400.0  # с, полуширина окна часов вокруг момента
# Скорости показа: во сколько раз время шкалы идёт быстрее часов.
# None - вся шкала за FIT_SECONDS, прежний показ по данным.
RATES = (1.0, 10.0, 60.0, 600.0, 3600.0, 86400.0)
FIT_SECONDS = 20.0


def window(moment, lo=None):
    """Окно часов вокруг момента, левый бегунок lo в нём остаётся."""
    start = moment - HALF
    if lo is not None:
        start = min(start, lo)
    return start, moment + HALF


def extent(data, moment, lo=None, on=True):
    """Охват шкалы: охват данных data (или None) вместе с окном часов
    вокруг момента, если часы нужны (on). Без часов - охват данных."""
    if not on or moment is None:
        return data
    a, b = window(moment, lo)
    if data is None:
        return a, b
    return min(a, data[0]), max(b, data[1])


def shift(span, rate, dt, seconds=FIT_SECONDS):
    """Сдвиг момента за dt секунд часов. rate None - охват span
    проходится за seconds."""
    if rate is None:
        lo, hi = span
        return (hi - lo) * dt / seconds
    return rate * dt


def advance(lo, hi, span, step, grow, loop):
    """Промежуток (lo, hi) после сдвига на step при охвате span.

    grow - часы: на краю охвата показ идёт дальше, охват None значит,
    что его надо построить заново вокруг нового момента. Иначе loop -
    промежуток той же ширины начинает с начала охвата, без него встаёт
    на конце. Возвращает (lo, hi, охват, идёт ли показ)."""
    a, b = span
    lo, hi = lo + step, hi + step
    if hi <= b:
        return lo, hi, span, True
    if grow:
        return lo, hi, None, True
    width = hi - lo
    if loop:
        return a, a + width, span, True
    return b - width, b, span, False
