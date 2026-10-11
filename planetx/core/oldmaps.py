# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Исторические карты по годам. Без Qt.

Карта с годом - картинка на поверхности с моментом времени (TimeStamp
в KML) или растр проекта с годом карты. Карты одной группы (папки
«Моих меток» или группы слоёв проекта) сменяют друг друга. При
открытой шкале времени видна последняя карта не позже правого бегунка,
до года первой карты группы не видно ни одной. Карта с промежутком
времени (TimeSpan) этому правилу не подчиняется, она видна в своём
промежутке, как метка. Решение автора от 10 октября 2026 года.
"""
import math

try:  # внутри плагина QGIS
    from . import when
except ImportError:  # headless-тесты
    import when


def year_time(year):
    """Время-момент карты года year: пара строк «1890»."""
    text = "%04d" % year if year > 0 else "-%04d" % (1 - year)
    return when.stamp(text)


YEAR = 365.2425 * 86400.0  # средний год, с


def year_label(seconds):
    """Подпись года момента: «1890», до н. э. - «-500»."""
    year = when.civil(seconds)[0]
    return str(year if year > 0 else year - 1)


def start(time):
    """Секунды момента карты или None, если время не момент."""
    if not when.is_stamp(time):
        return None
    return when.parse(time[0])


def shown(entries, moment):
    """Ключи видимых карт из entries - (ключ, группа, секунды момента).
    moment None - шкала закрыта, видны все. В группе - карта
    с наибольшим моментом не позже moment, при равных - все такие."""
    if moment is None:
        return {key for key, _, _ in entries}
    best = {}
    for _, group, at in entries:
        if at <= moment and (group not in best or at > best[group]):
            best[group] = at
    return {key for key, group, at in entries
            if group in best and at == best[group]}


def step(moments, moment, delta):
    """Соседний момент карт для шага шкалы ◂ ▸ или None. delta -1 -
    ближайший раньше moment, +1 - ближайший позже."""
    values = sorted(set(m for m in moments if math.isfinite(m)))
    if delta < 0:
        before = [m for m in values if m < moment - 0.5]
        return before[-1] if before else None
    after = [m for m in values if m > moment + 0.5]
    return after[0] if after else None


def parse_year(text):
    """Год из строки поля «Год карты»: «1890», «-500», пусто - None.
    Неверная строка - ValueError."""
    text = (text or "").strip()
    if not text:
        return None
    year = int(text)
    if year == 0 or abs(year) > 99999:
        raise ValueError(text)
    # Год до н. э. пишется со знаком, астрономический год на 1 больше.
    return year if year > 0 else year + 1
