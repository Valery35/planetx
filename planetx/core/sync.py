# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Синхронизация глобуса с окном карты QGIS, расчёт без Qt.

Карта и глобус обмениваются точкой взгляда и размером видимой полосы
на местности в метрах. Система координат карты сюда не попадает:
окно переводит центр карты и её края в широту и долготу само, через
преобразование QGIS. Так расчёт один для любой проекции карты,
в том числе полярной и в градусах.

Ширина полосы на местности считается по дуге большого круга между
точками, поэтому она не зависит от искажений проекции в центре.
"""
import math

try:  # внутри плагина QGIS
    from .ellipsoid import A
except ImportError:  # headless-тесты
    from ellipsoid import A

OFF, MAP_TO_GLOBE, GLOBE_TO_MAP, BOTH = "off", "map", "globe", "both"
DIRECTIONS = (MAP_TO_GLOBE, GLOBE_TO_MAP, BOTH)
# Относительная разница видов, ниже которой виды считаются одним.
# Ответный сигнал другой стороны на только что сделанный шаг не должен
# давать новый шаг, иначе карта и глобус толкают друг друга по кругу.
SAME_VIEW = 0.02
MAX_GROUND = 2.0e7  # метров, полоса шире половины экватора не берётся


def arc(lat1, lon1, lat2, lon2):
    """Расстояние по дуге большого круга на сфере радиуса A, метров."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = p2 - p1
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2.0) ** 2 \
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2.0) ** 2
    return 2.0 * A * math.asin(min(1.0, math.sqrt(h)))


def ground_size(distance, fov_y, aspect):
    """Ширина и высота видимой полосы на местности при отвесном взгляде."""
    height = 2.0 * distance * math.tan(math.radians(fov_y) / 2.0)
    return min(height * aspect, MAX_GROUND), min(height, MAX_GROUND)


def distance_for(width, height, fov_y, aspect):
    """Расстояние камеры, с которого полоса width × height видна целиком.

    Обратное к ground_size: полоса ложится в кадр по большей из сторон.
    """
    half = math.tan(math.radians(fov_y) / 2.0)
    return max(height, width / aspect) / (2.0 * half)


def same_view(a, b, tolerance=SAME_VIEW):
    """Совпадают ли виды (lat, lon, ширина полосы) с точностью tolerance.

    Сдвиг центра меряется в долях ширины полосы, размер - отношением.
    """
    if a is None or b is None:
        return False
    lat1, lon1, w1 = a
    lat2, lon2, w2 = b
    size = max(min(w1, w2), 1.0)
    shift = arc(lat1, lon1, lat2, lon2) / size
    ratio = abs(math.log(max(w1, 1.0) / max(w2, 1.0)))
    return shift < tolerance and ratio < tolerance
