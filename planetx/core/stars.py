# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Звёзды: направления в ECEF на момент времени, размер и цвет, без Qt.

Каталог - звёзды BSC5 до величины MAX_MAG, прямое восхождение
и склонение J2000 в радианах, видимая величина и показатель цвета B-V.
Файл data/stars.npy собирает tools/build_stars.py. Небесная сфера
поворачивается вокруг оси Земли на гринвичское среднее звёздное время.
Прецессия с 2000 года - около 0.4°, она не учитывается. Звёзды гаснут,
когда камера опускается в атмосферу, от FADE_HIGH до FADE_LOW метров.
"""
import math

import numpy as np

MAX_MAG = 6.0  # звёзды тусклее в файл не идут
FADE_HIGH = 150000.0  # выше звёзды видны полностью
FADE_LOW = 30000.0  # ниже звёзд нет
UNIX_J2000 = 946728000.0  # 1 января 2000 года, 12:00 UT, в секундах Unix
SIZE_BRIGHT = 4.5  # размер самой яркой звезды в логических пикселях
SIZE_FAINT = 1.6  # размер звезды величины MAX_MAG
# Картинка неба с Млечным путём: NASA SVS Deep Star Maps 2020,
# переведённая tools/build_sky.py. Прямое восхождение 0-360° слева
# направо, склонение +90° в верхней строке. Лежит в выпуске GitHub,
# модуль скачивает её при первом показе звёзд, дальше - кэш QGIS.
# Решение автора от 29 сентября 2026 года.
SKY_URL = ("https://github.com/Valery35/planetx/releases/download/"
           "sky-2020/sky_2020_8k.jpg")
# Яркость картинки неба на экране и доля её яркости, которая становится
# чёрной - ниже неё зерно слабых звёзд. Подобраны на снимках над
# центром Галактики 29 сентября 2026 года, их утверждает автор.
SKY_GAIN = 0.5
SKY_FLOOR = 0.2


def gmst(unix_time):
    """Гринвичское среднее звёздное время в радианах, от 0 до 2π."""
    days = (unix_time - UNIX_J2000) / 86400.0
    degrees = 280.46061837 + 360.98564736629 * days
    return math.radians(degrees % 360.0)


def sky_directions(ra, dec):
    """Единичные векторы звёзд в экваториальной системе, (N, 3)."""
    ra = np.asarray(ra, dtype=np.float64)
    dec = np.asarray(dec, dtype=np.float64)
    cos_dec = np.cos(dec)
    return np.stack([cos_dec * np.cos(ra), cos_dec * np.sin(ra),
                     np.sin(dec)], axis=1)


def sky_rotation(unix_time):
    """Поворот из экваториальной системы в ECEF на момент unix_time.
    Земля повёрнута на угол GMST, звёзды в её системе - на тот же угол
    назад."""
    angle = gmst(unix_time)
    c, s = math.cos(angle), math.sin(angle)
    return np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])


def to_ecef(directions, unix_time):
    """Направления звёзд в ECEF на момент unix_time."""
    return np.asarray(directions) @ sky_rotation(unix_time).T


def sizes(mag):
    """Размер точки в логических пикселях по видимой величине."""
    mag = np.asarray(mag, dtype=np.float64)
    share = np.clip((mag + 1.5) / (MAX_MAG + 1.5), 0.0, 1.0)
    return SIZE_BRIGHT + (SIZE_FAINT - SIZE_BRIGHT) * share


def brightness(mag):
    """Яркость от 0 до 1. Разница в 5 величин - в 100 раз по свету,
    здесь сжата, иначе тусклые звёзды не видны на экране."""
    mag = np.asarray(mag, dtype=np.float64)
    return np.clip(10.0 ** (-0.1 * (mag - 1.0)), 0.45, 1.0)


def colors(bv):
    """Цвет RGB от 0 до 1 по показателю B-V: голубые звёзды около -0.3,
    белые около 0.3, оранжевые и красные от 1.2."""
    bv = np.clip(np.nan_to_num(np.asarray(bv, dtype=np.float64),
                               nan=0.6), -0.4, 2.0)
    stops = np.array([-0.4, 0.0, 0.4, 0.8, 1.2, 2.0])
    red = np.interp(bv, stops, [0.62, 0.80, 1.00, 1.00, 1.00, 1.00])
    green = np.interp(bv, stops, [0.72, 0.86, 0.98, 0.93, 0.80, 0.62])
    blue = np.interp(bv, stops, [1.00, 1.00, 0.96, 0.80, 0.60, 0.40])
    return np.stack([red, green, blue], axis=1)


def fade(altitude):
    """Доля видимости звёзд от высоты камеры в метрах, от 0 до 1."""
    if altitude <= FADE_LOW:
        return 0.0
    if altitude >= FADE_HIGH:
        return 1.0
    return math.log(altitude / FADE_LOW) / math.log(FADE_HIGH / FADE_LOW)
