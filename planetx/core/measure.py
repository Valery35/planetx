# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейка: единицы, запись величин, точка по азимуту. Без Qt.

Длина, площадь и окружность круга на эллипсоиде WGS84 считаются
в ui/measure.py через QgsDistanceArea из QGIS. Здесь - то, что
от QGIS не зависит.
"""
import math

try:  # внутри плагина QGIS
    from .ellipsoid import A
except ImportError:  # headless-тесты
    from ellipsoid import A

CIRCLE_POINTS = 128

# Единицы длины и площади: код, множитель от метров или квадратных
# метров. Названия для окна - в ui/measure.py, через перевод.
LENGTH_UNITS = (("m", 1.0), ("km", 1000.0), ("mi", 1609.344),
                ("nmi", 1852.0))
AREA_UNITS = (("m2", 1.0), ("ha", 1.0e4), ("km2", 1.0e6),
              ("mi2", 1609.344 ** 2))


def destination(lat, lon, bearing, distance):
    """Точка на расстоянии distance метров по азимуту bearing, сфера.

    Для проверок и грубых построений. Точная окружность круга строится
    на эллипсоиде в ui/measure.py.
    """
    phi = math.radians(lat)
    lam = math.radians(lon)
    theta = math.radians(bearing)
    delta = distance / A
    sin_phi = math.sin(phi) * math.cos(delta) \
        + math.cos(phi) * math.sin(delta) * math.cos(theta)
    phi2 = math.asin(max(-1.0, min(1.0, sin_phi)))
    lam2 = lam + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi),
        math.cos(delta) - math.sin(phi) * sin_phi)
    lon2 = (math.degrees(lam2) + 180.0) % 360.0 - 180.0
    return math.degrees(phi2), lon2


def convert(value, unit, units):
    """Величина в метрах или кв. метрах в единицах unit из units."""
    return value / dict(units)[unit]


def number(value):
    """Число для окна.

    От 1 до 1000 - две цифры после точки. От 1000 - одна цифра, тысячи
    разделены пробелом. Меньше 1 - три значащие цифры.
    """
    if value >= 1000.0:
        return "{:,.1f}".format(value).replace(",", " ")
    if value >= 1.0:
        return "{:.2f}".format(value)
    return "{:.3g}".format(value)
