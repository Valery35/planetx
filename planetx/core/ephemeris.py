# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Солнце, Луна и планеты на небе Земли: прямое восхождение
и склонение J2000 на момент времени, без Qt.

Планеты - кеплеровы элементы орбит JPL «Approximate Positions of the
Planets», таблица 1, для 1800-2050 годов, E. M. Standish. Земля в них -
барицентр Земли и Луны, ошибка от этого для планет меньше угловой
секунды. Поправка на время света - одна итерация. Луна - формулы малой
точности Астрономического альманаха, до 0.3°, долгота переводится
с эклиптики даты на J2000 общей прецессией. Звёзды каталога тоже
в J2000 (core/stars.py), поэтому планеты и звёзды стоят в одной системе.

Сверка с JPL Horizons на 20 марта 2012 года и 1 октября 2026 года
лежит в tests/test_ephemeris.py.
"""
import math

import numpy as np

UNIX_J2000 = 946728000.0  # 1 января 2000 года, 12:00, секунды Unix
OBLIQUITY = math.radians(23.43928)  # наклон эклиптики J2000
LIGHT_DAYS_PER_AU = 0.0057755183  # время света на одну а. е., сутки
PRECESSION = 1.3969713  # общая прецессия по долготе, градусов в век

# a, e, I, L, долгота перигелия, долгота узла и их изменение за век.
# Углы в градусах, a в астрономических единицах.
ELEMENTS = {
    "mercury": ((0.38709927, 0.20563593, 7.00497902, 252.25032350,
                 77.45779628, 48.33076593),
                (0.00000037, 0.00001906, -0.00594749, 149472.67411175,
                 0.16047689, -0.12534081)),
    "venus": ((0.72333566, 0.00677672, 3.39467605, 181.97909950,
               131.60246718, 76.67984255),
              (0.00000390, -0.00004107, -0.00078890, 58517.81538729,
               0.00268329, -0.27769418)),
    "earth": ((1.00000261, 0.01671123, -0.00001531, 100.46457166,
               102.93768193, 0.0),
              (0.00000562, -0.00004392, -0.01294668, 35999.37244981,
               0.32327364, 0.0)),
    "mars": ((1.52371034, 0.09339410, 1.84969142, -4.55343205,
              -23.94362959, 49.55953891),
             (0.00001847, 0.00007882, -0.00813131, 19140.30268499,
              0.44441088, -0.29257343)),
    "jupiter": ((5.20288700, 0.04838624, 1.30439695, 34.39644051,
                 14.72847983, 100.47390909),
                (-0.00011607, -0.00013253, -0.00183714, 3034.74612775,
                 0.21252668, 0.20469106)),
    "saturn": ((9.53667594, 0.05386179, 2.48599187, 49.95424423,
                92.59887831, 113.66242448),
               (-0.00125060, -0.00050991, 0.00193609, 1222.49362201,
                -0.41897216, -0.28867794)),
    "uranus": ((19.18916464, 0.04725744, 0.77263783, 313.23810451,
                170.95427630, 74.01692503),
               (-0.00196176, -0.00004397, -0.00242939, 428.48202785,
                0.40805281, 0.04240589)),
    "neptune": ((30.06992276, 0.00859048, 1.77004347, -55.12002969,
                 44.96476227, 131.78422574),
                (0.00026291, 0.00005105, 0.00035372, 218.45945325,
                 -0.32241464, -0.00508664)),
}
PLANETS = ("mercury", "venus", "mars", "jupiter", "saturn", "uranus",
           "neptune")
BODIES = ("sun", "moon") + PLANETS


def centuries(unix_time):
    """Юлианские века от J2000. Разница TT и UT, около минуты,
    не учитывается."""
    return (unix_time - UNIX_J2000) / 86400.0 / 36525.0


def _ecliptic_to_equator(v):
    c, s = math.cos(OBLIQUITY), math.sin(OBLIQUITY)
    x, y, z = v
    return np.array([x, c * y - s * z, s * y + c * z])


def heliocentric(name, t):
    """Положение планеты от Солнца в экваториальной системе J2000,
    а. е. t - юлианские века от J2000."""
    base, rate = ELEMENTS[name]
    a, e, inc, mean_long, peri, node = (b + r * t for b, r in zip(base,
                                                                 rate))
    anomaly = math.radians((mean_long - peri + 180.0) % 360.0 - 180.0)
    omega = math.radians(peri - node)
    inc, node = math.radians(inc), math.radians(node)
    ecc = anomaly + e * math.sin(anomaly)
    for _ in range(30):
        step = (ecc - e * math.sin(ecc) - anomaly) / (1.0 - e * math.cos(ecc))
        ecc -= step
        if abs(step) < 1e-12:
            break
    xp = a * (math.cos(ecc) - e)
    yp = a * math.sqrt(1.0 - e * e) * math.sin(ecc)
    co, so = math.cos(omega), math.sin(omega)
    cn, sn = math.cos(node), math.sin(node)
    ci, si = math.cos(inc), math.sin(inc)
    x = (co * cn - so * sn * ci) * xp + (-so * cn - co * sn * ci) * yp
    y = (co * sn + so * cn * ci) * xp + (-so * sn + co * cn * ci) * yp
    z = so * si * xp + co * si * yp
    return _ecliptic_to_equator((x, y, z))


def _geocentric(name, t):
    """Вектор от Земли к телу, а. е., с поправкой на время света."""
    earth = heliocentric("earth", t)
    if name == "sun":
        # Солнце стоит в начале координат, свет идёт от него к Земле.
        return -earth
    vector = heliocentric(name, t) - earth
    delay = np.linalg.norm(vector) * LIGHT_DAYS_PER_AU / 36525.0
    return heliocentric(name, t - delay) - earth


def moon(t):
    """Направление на Луну от центра Земли, J2000, и расстояние
    в радиусах Земли."""
    def s(a, b):
        return math.sin(math.radians(a + b * t))

    def c(a, b):
        return math.cos(math.radians(a + b * t))
    lon = (218.32 + 481267.881 * t + 6.29 * s(135.0, 477198.87)
           - 1.27 * s(259.3, -413335.36) + 0.66 * s(235.7, 890534.22)
           + 0.21 * s(269.9, 954397.74) - 0.19 * s(357.5, 35999.05)
           - 0.11 * s(186.5, 966404.03))
    lat = (5.13 * s(93.3, 483202.02) + 0.28 * s(228.2, 960400.89)
           - 0.28 * s(318.3, 6003.15) - 0.17 * s(217.6, -407332.21))
    parallax = (0.9508 + 0.0518 * c(135.0, 477198.87)
                + 0.0095 * c(259.3, -413335.36)
                + 0.0078 * c(235.7, 890534.22)
                + 0.0028 * c(269.9, 954397.74))
    # Эклиптика даты - в эклиптику J2000.
    lon = math.radians(lon - PRECESSION * t)
    lat = math.radians(lat)
    v = (math.cos(lat) * math.cos(lon), math.cos(lat) * math.sin(lon),
         math.sin(lat))
    return _ecliptic_to_equator(v), 1.0 / math.sin(math.radians(parallax))


def direction(name, unix_time):
    """Единичный вектор на тело в экваториальной системе J2000."""
    t = centuries(unix_time)
    if name == "moon":
        return moon(t)[0]
    v = _geocentric(name, t)
    return v / np.linalg.norm(v)


def ra_dec(name, unix_time):
    """Прямое восхождение от 0 до 360° и склонение, градусы."""
    x, y, z = direction(name, unix_time)
    return (math.degrees(math.atan2(y, x)) % 360.0,
            math.degrees(math.asin(max(-1.0, min(1.0, z)))))


def distance(name, unix_time):
    """Расстояние от Земли, а. е. У Луны - по параллаксу."""
    t = centuries(unix_time)
    if name == "moon":
        return moon(t)[1] * 6378.137 / 149597870.7
    return float(np.linalg.norm(_geocentric(name, t)))
