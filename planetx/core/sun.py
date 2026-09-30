# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Солнце: направление в ECEF на момент времени, высота и азимут, без Qt.

Положение солнца считается по алгоритму NOAA Solar Calculator, он
идёт от формул Жана Меёса «Astronomical Algorithms». Точность около
0.01° с 1800 по 2100 год. Время - секунды Unix, то есть UTC. Разница
земного и всемирного времени, около минуты, не учитывается, она сдвигает
солнце на 0.02°. Рефракция не учитывается, солнце у горизонта в расчёте
ниже видимого на полградуса.

Солнце считается бесконечно далёким, направление на него одно для
всей Земли. Вектор направления - в той же системе ECEF, что и мир
глобуса.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .stars import UNIX_J2000, gmst
    from .tiling import AMBIENT, LIGHT_ELEVATION, SHADE_LIMITS
except ImportError:  # headless-тесты
    from stars import UNIX_J2000, gmst
    from tiling import AMBIENT, LIGHT_ELEVATION, SHADE_LIMITS

# Яркость ночной стороны в долях яркости ровной земли днём. Сумерки -
# переход от ночи ко дню по синусу высоты солнца над плоскостью склона,
# от DUSK до DAWN, примерно от -6° до +3°. Величины назначил помощник
# 30 сентября 2026 года, их утверждает автор.
NIGHT = 0.15
DUSK = -0.10
DAWN = 0.05


def _centuries(unix_time):
    """Юлианские столетия от J2000.0."""
    return (unix_time - UNIX_J2000) / (86400.0 * 36525.0)


def equatorial(unix_time):
    """Видимые прямое восхождение и склонение солнца в радианах."""
    t = _centuries(unix_time)
    mean_long = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360.0
    anomaly = math.radians(357.52911 + t * (35999.05029 - 0.0001537 * t))
    center = (math.sin(anomaly) * (1.914602 - t * (0.004817 + 0.000014 * t))
              + math.sin(2.0 * anomaly) * (0.019993 - 0.000101 * t)
              + math.sin(3.0 * anomaly) * 0.000289)
    omega = math.radians(125.04 - 1934.136 * t)
    longitude = math.radians(mean_long + center - 0.00569
                             - 0.00478 * math.sin(omega))
    seconds = 21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))
    obliquity = math.radians(23.0 + (26.0 + seconds / 60.0) / 60.0
                             + 0.00256 * math.cos(omega))
    ra = math.atan2(math.cos(obliquity) * math.sin(longitude),
                    math.cos(longitude))
    dec = math.asin(math.sin(obliquity) * math.sin(longitude))
    return ra % (2.0 * math.pi), dec


def subsolar(unix_time):
    """Широта и долгота точки, где солнце в зените, в градусах.

    Долгота - прямое восхождение минус гринвичское звёздное время,
    от -180 до 180.
    """
    ra, dec = equatorial(unix_time)
    lon = math.degrees(ra - gmst(unix_time))
    return math.degrees(dec), (lon + 180.0) % 360.0 - 180.0


def direction(unix_time):
    """Единичный вектор на солнце в ECEF, float64, форма (3,)."""
    lat, lon = (math.radians(v) for v in subsolar(unix_time))
    return np.array([math.cos(lat) * math.cos(lon),
                     math.cos(lat) * math.sin(lon), math.sin(lat)])


def horizontal(lat, lon, unix_time):
    """Высота над горизонтом и азимут от севера по часовой, градусы.

    lat, lon - геодезические, в градусах. Горизонт - плоскость,
    перпендикулярная нормали эллипсоида в точке.
    """
    sun = direction(unix_time)
    la, lo = math.radians(lat), math.radians(lon)
    up = np.array([math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
                   math.sin(la)])
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.cross(up, east)
    elevation = math.degrees(math.asin(max(-1.0, min(1.0, sun @ up))))
    azimuth = math.degrees(math.atan2(sun @ east, sun @ north)) % 360.0
    return elevation, azimuth


def daylight(cos):
    """Доля дня от 0 ночью до 1 днём по синусу высоты солнца cos над
    плоскостью поверхности. Переход - smoothstep от DUSK до DAWN, как
    в шейдере."""
    t = np.clip((np.asarray(cos, dtype=np.float64) - DUSK) / (DAWN - DUSK),
                0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def light(normals, sun):
    """Множитель яркости поверхности под солнцем, как в шейдере тайла.

    normals - единичные нормали (N, 3) в ECEF, sun - направление на
    солнце. Днём - та же отмывка, что у постоянного света
    core.tiling.shade: рассеянный свет AMBIENT и прямой по косинусу,
    ровная земля под солнцем на высоте LIGHT_ELEVATION даёт 1. Ночью -
    NIGHT, между ними сумерки.
    """
    cos = np.asarray(normals, dtype=np.float64) @ np.asarray(sun)
    flat = math.sin(LIGHT_ELEVATION)
    day = np.clip((AMBIENT + (1.0 - AMBIENT) * np.clip(cos, 0.0, 1.0))
                  / (AMBIENT + (1.0 - AMBIENT) * flat), *SHADE_LIMITS)
    return NIGHT + (day - NIGHT) * daylight(cos)
