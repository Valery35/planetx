# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Границы сельскохозяйственных полей Fields of the World. Без Qt.

Слово автора от 1 ноября 2026 года - «делай» на разбор данных RustGIS.
Набор ftw/global-data на Source Cooperative - поля модели PRUE по снимкам
Sentinel-2 за 2024 и 2025 годы, CC BY 4.0. Это оценка модели, а не
кадастр. Один архив PMTiles на год, файл 2025 года - 268 ГБ.

Тайлы архивов собраны без предела размера, замер 1 ноября 2026 года -
тайл уровня 5 в Пенджабе 396 МБ, уровня 8 - 24 МБ, уровня 10 - 1.8 МБ,
поэтому поля просятся с MIN_LEVEL. В архиве 2024 года уровни 10-14,
в архиве 2025 года 0-14. Объекты 2024 года с меткой field_boundaries -
полосы границ, 1268 из 1334 в тайле на Кубани, они не рисуются.

Оценка 0-100 - confidence_mean / FULL, как в стилях набора. Рекомендация
набора - показывать оценки не ниже MIN_SCORE.
"""
from collections import namedtuple

try:  # внутри плагина QGIS
    from .buildings import _rings
    from .places import _fields, _packed, _unpack, _value
except ImportError:  # headless-тесты
    from buildings import _rings
    from places import _fields, _packed, _unpack, _value

YEARS = (2025, 2024)
KEYS = {2025: "ftw_2025", 2024: "ftw_2024"}  # строки раздела «Слои»
URLS = {
    2025: "https://data.source.coop/ftw/global-field-boundaries/pmtiles/"
          "ftw-global-fields-2025.pmtiles",
    2024: "https://data.source.coop/ftw/global-data/predictions/vectors/"
          "alpha/2024_with_confidence.pmtiles"}
LAYERS = {2025: "fields", 2024: "2024"}  # слои векторных тайлов
ATTRIBUTION = "Fields of the World"
TERMS = "https://source.coop/ftw/global-data"
MIN_LEVEL = 10
MAX_LEVEL = 14
FULL = 0.578178  # confidence_mean оценки 100
MIN_SCORE = 69.0
LABEL = "field"
EXTENT = 4096
# Шкала стилей набора от рекомендованного порога.
STOPS = ((MIN_SCORE, (254, 195, 121)), (80.0, (243, 250, 187)),
         (90.0, (207, 236, 176)), (100.0, (51, 160, 44)))

Field = namedtuple("Field", "rings score")
Field.__doc__ = """Поле тайла: rings - кольца, массивы (n, 2) долями тайла
0-1, y растёт к югу, score - оценка 0-100."""


def score_of(value):
    """Оценка 0-100 по значению confidence_mean или None."""
    try:
        return min(float(value) / FULL * 100.0, 100.0)
    except (TypeError, ValueError):
        return None


def color(score):
    """Цвет оценки RGB 0-255 по шкале STOPS."""
    for (low, first), (high, last) in zip(STOPS, STOPS[1:]):
        if score <= high:
            share = max(score - low, 0.0) / (high - low)
            return tuple(int(a + (b - a) * share + 0.5)
                         for a, b in zip(first, last))
    return STOPS[-1][1]


def _feature(items, keys, values):
    """(атрибуты, геометрия) объекта-многоугольника или None."""
    kind = 0
    tags = geometry = None
    for number, wire, value in items:
        if number == 2 and wire == 2:
            tags = _packed(value)
        elif number == 3 and wire == 0:
            kind = value
        elif number == 4 and wire == 2:
            geometry = _packed(value)
    if kind != 3 or tags is None or geometry is None:
        return None
    found = {}
    for key, value in zip(tags[::2], tags[1::2]):
        if key < len(keys) and value < len(values):
            found[keys[key]] = values[value]
    return found, geometry


def decode(data, title):
    """Поля слоя title тайла не ниже MIN_SCORE: список Field."""
    out = []
    for number, wire, layer in _fields(_unpack(data)):
        if number != 3 or wire != 2:
            continue
        items = list(_fields(layer))
        name = next((bytes(v).decode("utf-8", errors="replace")
                     for n, w, v in items if n == 1 and w == 2), None)
        if name != title:
            continue
        extent = next((v for n, w, v in items if n == 5 and w == 0),
                      EXTENT) or EXTENT
        keys = [bytes(v).decode("utf-8", errors="replace")
                for n, w, v in items if n == 3 and w == 2]
        values = [_value(v) for n, w, v in items if n == 4 and w == 2]
        for n, w, feature in items:
            if n != 2 or w != 2:
                continue
            parsed = _feature(_fields(feature), keys, values)
            if parsed is None or parsed[0].get("label") != LABEL:
                continue
            score = score_of(parsed[0].get("confidence_mean"))
            if score is None or score < MIN_SCORE:
                continue
            rings = [ring / float(extent)
                     for ring, _ in _rings(parsed[1])]
            if rings:
                out.append(Field(rings, score))
    return out
