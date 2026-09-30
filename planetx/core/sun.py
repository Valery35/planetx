# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Солнце: направление в ECEF на момент времени и свет, без Qt.

Положение солнца считается по формулам малой точности Астрономического
альманаха (Astronomical Almanac, раздел C) - ошибка склонения
и прямого восхождения около 0.01° в годы 1950-2050. Земля повёрнута на
гринвичское среднее звёздное время, как у звёзд (core/stars.py).
Нутация и рефракция не учитываются, это доли градуса.

Свет рельефа и зданий при включённом солнце - ламбертов по нормали
к поверхности с рассеянным светом AMBIENT днём и NIGHT ночью. Переход
дня в ночь идёт по высоте солнца от TWILIGHT до DAYLIGHT. Яркость
делится на яркость ровной местности при солнце на высоте 45°, так
днём глобус светлый, как при отмывке без солнца.
"""
import math
import time

try:  # внутри плагина QGIS
    from .stars import UNIX_J2000, gmst
except ImportError:  # headless-тесты
    from stars import UNIX_J2000, gmst

AMBIENT = 0.35  # рассеянный свет днём, как у отмывки (core/tiling.py)
NIGHT = 0.07  # рассеянный свет ночью
# Синус высоты солнца: ниже TWILIGHT - ночь, выше DAYLIGHT - день.
TWILIGHT = math.sin(math.radians(-12.0))
DAYLIGHT = math.sin(math.radians(6.0))
FLAT = AMBIENT + (1.0 - AMBIENT) * math.sin(math.radians(45.0))


def equatorial(unix_time):
    """Прямое восхождение и склонение солнца в радианах."""
    n = (unix_time - UNIX_J2000) / 86400.0
    mean_lon = math.radians((280.460 + 0.9856474 * n) % 360.0)
    anomaly = math.radians((357.528 + 0.9856003 * n) % 360.0)
    ecl_lon = mean_lon + math.radians(1.915) * math.sin(anomaly) \
        + math.radians(0.020) * math.sin(2.0 * anomaly)
    obliquity = math.radians(23.439 - 0.0000004 * n)
    ra = math.atan2(math.cos(obliquity) * math.sin(ecl_lon),
                    math.cos(ecl_lon))
    dec = math.asin(math.sin(obliquity) * math.sin(ecl_lon))
    return ra, dec


def subsolar(unix_time):
    """Точка, где солнце в зените: широта и долгота в градусах,
    долгота от -180 до 180."""
    ra, dec = equatorial(unix_time)
    lon = math.degrees(ra - gmst(unix_time))
    return math.degrees(dec), (lon + 180.0) % 360.0 - 180.0


def direction(unix_time):
    """Единичный вектор на солнце в ECEF. Солнце далеко, направление
    одно для всей Земли."""
    lat, lon = subsolar(unix_time)
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
            math.sin(la))


def elevation(lat, lon, unix_time):
    """Высота солнца над горизонтом в точке, градусы. Горизонт -
    плоскость, перпендикулярная нормали эллипсоида."""
    la, lo = math.radians(lat), math.radians(lon)
    up = (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
          math.sin(la))
    sun = direction(unix_time)
    dot = sum(a * b for a, b in zip(up, sun))
    return math.degrees(math.asin(max(-1.0, min(1.0, dot))))


def smoothstep(edge0, edge1, x):
    t = min(max((x - edge0) / (edge1 - edge0), 0.0), 1.0)
    return t * t * (3.0 - 2.0 * t)


def brightness(cos_sun):
    """Множитель яркости поверхности, у которой косинус угла между
    нормалью и направлением на солнце равен cos_sun. Ровная местность
    при солнце на высоте 45° даёт 1. Та же формула стоит в шейдерах."""
    day = smoothstep(TWILIGHT, DAYLIGHT, cos_sun)
    ambient = NIGHT + (AMBIENT - NIGHT) * day
    return (ambient + (1.0 - AMBIENT) * max(cos_sun, 0.0)) / FLAT


def now():
    """Момент для солнца по часам компьютера, секунды UTC."""
    return time.time()
