# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Эллипсоид тела и геоцентрические координаты ECEF.

ECEF - прямоугольная система с началом в центре тела. Ось X идёт
к пересечению экватора с нулевым меридианом, ось Z к северному
полюсу. Единица - метр, все расчёты в float64.

Широта и долгота - в градусах, высота - над эллипсоидом, в метрах.
Функции принимают числа и массивы NumPy одинаковой формы.

Тело одно на весь модуль: Земля (WGS84), Марс, Луна или другое тело
из BODIES, `set_body` меняет его. Полуоси A, B и квадрат
эксцентриситета E2 - величины модуля, другие модули читают их как
`ellipsoid.A` в момент расчёта, а не копируют при импорте. Марс и Луна -
сферы, как у тайлов снимков OpenPlanetaryMap в планетоцентрических
широтах. Радиус Марса 3396.19 км и Луны 1737.4 км - по рекомендациям
IAU 2015. Радиусы прочих тел - сферы глобальных мозаик USGS, у Юпитера -
сжатый эллипсоид IAU.
"""
from collections import namedtuple

import numpy as np

Body = namedtuple("Body", "key a f")
EARTH = Body("earth", 6378137.0, 1.0 / 298.257223563)
MARS = Body("mars", 3396190.0, 0.0)
MOON = Body("moon", 1737400.0, 0.0)
# Остальные тела - сферы средних радиусов, как у мозаик USGS, кроме
# сжатых Юпитера и Сатурна: экваториальный и полярный радиусы IAU 2015.
MERCURY = Body("mercury", 2439400.0, 0.0)
VENUS = Body("venus", 6051800.0, 0.0)
JUPITER = Body("jupiter", 71492000.0, 1.0 - 66854000.0 / 71492000.0)
IO = Body("io", 1821490.0, 0.0)
EUROPA = Body("europa", 1560800.0, 0.0)
GANYMEDE = Body("ganymede", 2631200.0, 0.0)
CALLISTO = Body("callisto", 2410300.0, 0.0)
MIMAS = Body("mimas", 198200.0, 0.0)
ENCELADUS = Body("enceladus", 252000.0, 0.0)
TETHYS = Body("tethys", 536300.0, 0.0)
DIONE = Body("dione", 563000.0, 0.0)
RHEA = Body("rhea", 764100.0, 0.0)
TITAN = Body("titan", 2575000.0, 0.0)
IAPETUS = Body("iapetus", 736000.0, 0.0)
CERES = Body("ceres", 470000.0, 0.0)
VESTA = Body("vesta", 255000.0, 0.0)
BODIES = (EARTH, MARS, MOON, MERCURY, VENUS, JUPITER, IO, EUROPA,
          GANYMEDE, CALLISTO, MIMAS, ENCELADUS, TETHYS, DIONE, RHEA,
          TITAN, IAPETUS, CERES, VESTA)

# WGS84 для расчётов, которые есть только у Земли: UTM и MGRS.
WGS84_A = EARTH.a
WGS84_F = EARTH.f

BODY = EARTH
A = F = B = E2 = EP2 = 0.0


def set_body(body):
    """Сделать тело body текущим: полуоси и эксцентриситет модуля."""
    global BODY, A, F, B, E2, EP2
    BODY = body
    A = body.a
    F = body.f
    B = A * (1.0 - F)
    E2 = F * (2.0 - F)
    EP2 = E2 / (1.0 - E2)


def body_by_key(key):
    """Тело по ключу, неизвестный ключ - Земля."""
    for body in BODIES:
        if body.key == key:
            return body
    return EARTH


set_body(EARTH)


def geodetic_to_ecef(lat, lon, h=0.0):
    """Широта, долгота и высота в ECEF. Результат формы (..., 3)."""
    lat = np.radians(np.asarray(lat, dtype=np.float64))
    lon = np.radians(np.asarray(lon, dtype=np.float64))
    h = np.asarray(h, dtype=np.float64)
    sin_lat = np.sin(lat)
    cos_lat = np.cos(lat)
    n = A / np.sqrt(1.0 - E2 * sin_lat * sin_lat)
    x = (n + h) * cos_lat * np.cos(lon)
    y = (n + h) * cos_lat * np.sin(lon)
    z = (n * (1.0 - E2) + h) * sin_lat
    return np.stack(np.broadcast_arrays(x, y, z), axis=-1)


def ecef_to_geodetic(xyz):
    """ECEF в широту, долготу и высоту.

    Решение Хейккинена, замкнутое, без итераций. Точность - доли
    миллиметра от центра Земли на удалении больше 100 км до десятков
    тысяч километров над поверхностью. Ближе к центру формула
    неустойчива, глобусу эти точки не нужны.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    x, y, z = xyz[..., 0], xyz[..., 1], xyz[..., 2]
    p2 = x * x + y * y
    p = np.sqrt(p2)
    z2 = z * z
    f54 = 54.0 * B * B * z2
    g = p2 + (1.0 - E2) * z2 - E2 * (A * A - B * B)
    c = E2 * E2 * f54 * p2 / (g * g * g)
    s = np.cbrt(1.0 + c + np.sqrt(c * c + 2.0 * c))
    k = s + 1.0 + 1.0 / s
    pp = f54 / (3.0 * k * k * g * g)
    q = np.sqrt(1.0 + 2.0 * E2 * E2 * pp)
    # У оси Земли подкоренное - разность величин порядка A², настоящее
    # значение около нуля. Округление уводило его в минус, и над
    # полюсом с 10 000-40 000 км выходил NaN, 6 октября 2026 года.
    r0 = (-pp * E2 * p / (1.0 + q)
          + np.sqrt(np.maximum(0.5 * A * A * (1.0 + 1.0 / q)
                               - pp * (1.0 - E2) * z2 / (q * (1.0 + q))
                               - 0.5 * pp * p2, 0.0)))
    t = p - E2 * r0
    u = np.sqrt(t * t + z2)
    v = np.sqrt(t * t + (1.0 - E2) * z2)
    z0 = B * B * z / (A * v)
    h = u * (1.0 - B * B / (A * v))
    lat = np.degrees(np.arctan2(z + EP2 * z0, p))
    lon = np.degrees(np.arctan2(y, x))
    return lat, lon, h


def surface_normal(lat, lon):
    """Единичная нормаль к эллипсоиду, форма (..., 3)."""
    lat = np.radians(np.asarray(lat, dtype=np.float64))
    lon = np.radians(np.asarray(lon, dtype=np.float64))
    cos_lat = np.cos(lat)
    return np.stack(np.broadcast_arrays(
        cos_lat * np.cos(lon), cos_lat * np.sin(lon), np.sin(lat)), axis=-1)


def ray_intersect(origin, direction, h=0.0):
    """Расстояние вдоль луча до первой встречи с эллипсоидом.

    Эллипсоид раздут на высоту ``h`` по обеим полуосям. Для рельефа это
    приближение, для h = 0 - точный эллипсоид WGS84. Направление
    нормировать не нужно, расстояние считается в его единицах длины.
    Возвращает None, если луч проходит мимо или эллипсоид позади.
    Начало луча внутри эллипсоида даёт точку выхода.
    """
    o = np.asarray(origin, dtype=np.float64)
    d = np.asarray(direction, dtype=np.float64)
    # Сжатие пространства превращает эллипсоид в единичную сферу.
    scale = np.array([1.0 / (A + h), 1.0 / (A + h), 1.0 / (B + h)])
    os_ = o * scale
    ds = d * scale
    qa = ds @ ds
    qb = 2.0 * (os_ @ ds)
    qc = os_ @ os_ - 1.0
    disc = qb * qb - 4.0 * qa * qc
    if qa == 0.0 or disc < 0.0:
        return None
    root = np.sqrt(disc)
    # Устойчивая запись корней без вычитания близких величин.
    qq = -0.5 * (qb + np.copysign(root, qb))
    roots = sorted(r for r in (qq / qa, qc / qq if qq != 0.0 else None)
                   if r is not None)
    for r in roots:
        if r >= 0.0:
            return float(r)
    return None
