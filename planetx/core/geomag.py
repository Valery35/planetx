# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Магнитное поле Земли: полюса по годам и модель IGRF-14.

Полюса - северный и южный магнитные полюса (точки, где стрелка стоит
отвесно) по годам 1590-2025 из таблиц NOAA NCEI «Wandering of the
Geomagnetic Poles» (модели gufm1 до 1890 года и IGRF), общественное
достояние США. Файл модуля data/magnetic_poles.json собирает
tools/build_poles.py. Между годами точка идёт по дуге большого круга.

Поле - Международное геомагнитное эталонное поле IGRF-14 (IAGA, 2024),
коэффициенты Шмидта до степени 13 на 1900-2025 годы через 5 лет
и вековой ход на 2025-2030 годы, файл data/igrf14coeffs.txt как есть.
Расчёт - по образцу igrf_utils из выпуска IGRF-14: пересчёт
геодезической широты в геоцентрическую, присоединённые функции
Лежандра, составляющие X (север), Y (восток), Z (вниз) в нТл.
Полюс после последнего года таблицы - точка, где горизонтальная
составляющая IGRF равна нулю (dip_pole).

Модуль Qt не знает.
"""
import datetime
import json
import math

# Эллипсоид WGS84 и радиус сферы модели IGRF, км.
A = 6378.137
B = 6356.752314245
REFERENCE = 6371.2


class Model:
    """Коэффициенты IGRF: эпохи, коэффициенты по эпохам, вековой ход."""

    def __init__(self, epochs, coeffs, secular, nmax):
        self.epochs = epochs
        self.coeffs = coeffs
        self.secular = secular
        self.nmax = nmax

    @property
    def first(self):
        return self.epochs[0]

    @property
    def last(self):
        """Конец действия модели - последняя эпоха плюс 5 лет хода."""
        return self.epochs[-1] + 5.0

    def at(self, year):
        """Коэффициенты на год, None вне 1900-2030."""
        if not self.first <= year <= self.last:
            return None
        epochs = self.epochs
        if year >= epochs[-1]:
            dt = year - epochs[-1]
            return [c + s * dt for c, s in zip(self.coeffs[-1],
                                                self.secular)]
        i = max(k for k in range(len(epochs)) if epochs[k] <= year)
        share = (year - epochs[i]) / (epochs[i + 1] - epochs[i])
        return [a + (b - a) * share
                for a, b in zip(self.coeffs[i], self.coeffs[i + 1])]


def parse_igrf(text):
    """Файл коэффициентов IGRF в Model. Порядок коэффициентов - g10,
    g11, h11, g20, g21, h21, g22, h22 и далее."""
    epochs = None
    rows = []
    for line in text.splitlines():
        parts = line.split()
        if not parts or line.startswith("#"):
            continue
        if parts[0] == "g/h":
            epochs = [float(p) for p in parts[3:-1]]
            continue
        if parts[0] not in ("g", "h") or epochs is None:
            continue
        values = [float(p) for p in parts[3:]]
        rows.append((int(parts[1]), int(parts[2]), parts[0], values))
    if epochs is None or not rows:
        raise ValueError("not an IGRF coefficient file")
    order = {}
    for n, m, kind, values in rows:
        order[(n, m, kind)] = values
    nmax = max(n for n, _, _, _ in rows)
    keys = []
    for n in range(1, nmax + 1):
        keys.append((n, 0, "g"))
        for m in range(1, n + 1):
            keys.append((n, m, "g"))
            keys.append((n, m, "h"))
    count = len(epochs)
    coeffs = [[order[k][e] for k in keys] for e in range(count)]
    secular = [order[k][count] for k in keys]
    return Model(epochs, coeffs, secular, nmax)


def _legendre(nmax, theta):
    """Присоединённые функции Лежандра Шмидта P[n][m] и их производные
    по кошироте в верхнем треугольнике P[m][n + 1], igrf_utils."""
    cos_t = math.cos(theta)
    sin_t = math.sqrt(max(1.0 - cos_t * cos_t, 0.0))
    p = [[0.0] * (nmax + 2) for _ in range(nmax + 1)]
    p[0][0] = 1.0
    p[1][1] = sin_t
    root = [math.sqrt(i) for i in range(2 * nmax * nmax + 1)]
    for m in range(nmax):
        tmp = root[m + m + 1] * p[m][m]
        p[m + 1][m] = cos_t * tmp
        if m > 0:
            p[m + 1][m + 1] = sin_t * tmp / root[m + m + 2]
        for n in range(m + 2, nmax + 1):
            d = n * n - m * m
            e = n + n - 1
            p[n][m] = (e * cos_t * p[n - 1][m] - root[d - e] * p[n - 2][m]) \
                / root[d]
    p[0][2] = -p[1][1]
    p[1][2] = p[1][0]
    for n in range(2, nmax + 1):
        p[0][n + 1] = -math.sqrt((n * n + n) / 2.0) * p[n][1]
        p[1][n + 1] = (math.sqrt(2.0 * (n * n + n)) * p[n][0]
                       - math.sqrt(n * n + n - 2.0) * p[n][2]) / 2.0
        for m in range(2, n):
            p[m][n + 1] = 0.5 * (
                math.sqrt((n + m) * (n - m + 1.0)) * p[n][m - 1]
                - math.sqrt((n + m + 1.0) * (n - m)) * p[n][m + 1])
        p[n][n + 1] = math.sqrt(2.0 * n) * p[n][n - 1] / 2.0
    return p


def _geocentric(lat, height):
    """Геодезическая широта, градусы, и высота, км, - радиус, км,
    геоцентрическая кошироты, рад, и косинус и синус поворота осей."""
    colat = math.radians(90.0 - lat)
    a2, b2 = A * A, B * B
    ct, st = math.cos(colat), math.sin(colat)
    one, two = a2 * st * st, b2 * ct * ct
    three = one + two
    rho = math.sqrt(three)
    radius = math.sqrt(height * (height + 2.0 * rho)
                       + (a2 * one + b2 * two) / three)
    cd = (height + rho) / radius
    sd = (a2 - b2) / rho * ct * st / radius
    ct2 = ct * cd - st * sd
    st2 = st * cd + ct * sd
    return radius, math.atan2(st2, ct2), cd, sd


def components(coeffs, nmax, lat, lon, height=0.0):
    """Составляющие поля X (север), Y (восток), Z (вниз), нТл, в точке
    с геодезической широтой и долготой, градусы, на высоте height км."""
    radius, theta, cd, sd = _geocentric(lat, height)
    # У самого полюса деление на синус кошироты неустойчиво.
    theta = min(max(theta, 1e-9), math.pi - 1e-9)
    p = _legendre(nmax, theta)
    sin_t = p[1][1]
    phi = math.radians(lon)
    ratio = REFERENCE / radius
    br = bt = bp = 0.0
    k = 0
    for n in range(1, nmax + 1):
        rn = ratio ** (n + 2)
        g = coeffs[k]
        k += 1
        br += (n + 1) * p[n][0] * rn * g
        bt -= p[0][n + 1] * rn * g
        for m in range(1, n + 1):
            g, h = coeffs[k], coeffs[k + 1]
            k += 2
            cm, sm = math.cos(m * phi), math.sin(m * phi)
            br += (n + 1) * p[n][m] * rn * (g * cm + h * sm)
            bt -= p[m][n + 1] * rn * (g * cm + h * sm)
            bp += m * p[n][m] / sin_t * rn * (g * sm - h * cm)
    x, y, z = -bt, bp, -br
    # Из геоцентрической системы в геодезическую.
    return x * cd + z * sd, y, z * cd - x * sd


def field(model, lat, lon, year, height=0.0):
    """Поле на год: словарь declination, inclination (градусы),
    total, horizontal (нТл) или None вне лет модели."""
    coeffs = model.at(year)
    if coeffs is None:
        return None
    x, y, z = components(coeffs, model.nmax, lat, lon, height)
    h = math.hypot(x, y)
    return {"declination": math.degrees(math.atan2(y, x)),
            "inclination": math.degrees(math.atan2(z, h)),
            "total": math.sqrt(h * h + z * z), "horizontal": h,
            "x": x, "y": y, "z": z}


# Полюса.

def parse_poles(text):
    """data/magnetic_poles.json - {"north": [(год, широта, долгота)],
    "south": [...]}, по возрастанию лет."""
    data = json.loads(text)
    return {key: sorted(tuple(float(v) for v in row) for row in data[key])
            for key in ("north", "south")}


def _unit(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
            math.sin(la))


def _point(vector):
    x, y, z = vector
    return (math.degrees(math.atan2(z, math.hypot(x, y))),
            math.degrees(math.atan2(y, x)))


def _between(a, b, share):
    """Точка на дуге большого круга между (широта, долгота) a и b."""
    ua, ub = _unit(*a), _unit(*b)
    dot = max(min(sum(p * q for p, q in zip(ua, ub)), 1.0), -1.0)
    angle = math.acos(dot)
    if angle < 1e-12:
        return a
    sa = math.sin((1.0 - share) * angle) / math.sin(angle)
    sb = math.sin(share * angle) / math.sin(angle)
    return _point(tuple(sa * p + sb * q for p, q in zip(ua, ub)))


def pole_at(track, year):
    """Полюс (широта, долгота) на год по таблице или None вне её лет."""
    if not track or not track[0][0] <= year <= track[-1][0]:
        return None
    for i in range(1, len(track)):
        if track[i][0] >= year:
            y0, la0, lo0 = track[i - 1]
            y1, la1, lo1 = track[i]
            share = 0.0 if y1 == y0 else (year - y0) / (y1 - y0)
            return _between((la0, lo0), (la1, lo1), share)
    return track[-1][1], track[-1][2]


def _offset(lat, lon, north, east):
    """Точка в north, east км от (lat, lon) на сфере среднего радиуса."""
    radius = REFERENCE
    distance = math.hypot(north, east) / radius
    if distance == 0.0:
        return lat, lon
    bearing = math.atan2(east, north)
    la, lo = math.radians(lat), math.radians(lon)
    la2 = math.asin(math.sin(la) * math.cos(distance)
                    + math.cos(la) * math.sin(distance)
                    * math.cos(bearing))
    lo2 = lo + math.atan2(math.sin(bearing) * math.sin(distance)
                          * math.cos(la),
                          math.cos(distance) - math.sin(la) * math.sin(la2))
    return math.degrees(la2), (math.degrees(lo2) + 540.0) % 360.0 - 180.0


def dip_pole(model, year, start, steps=30, tolerance=0.01):
    """Магнитный полюс на год по IGRF - точка с нулевой горизонтальной
    составляющей, поиск Ньютоном от точки start. None вне лет модели
    или без схождения."""
    coeffs = model.at(year)
    if coeffs is None:
        return None
    lat, lon = start
    step = 1.0  # км, шаг конечных разностей
    for _ in range(steps):
        x, y, _ = components(coeffs, model.nmax, lat, lon)
        if math.hypot(x, y) < tolerance:
            return lat, lon
        jac = []
        for dn, de in ((step, 0.0), (0.0, step)):
            # Производные в местных осях исходной точки: у полюса оси
            # соседней точки повёрнуты, поэтому сдвиг меряется так же.
            la2, lo2 = _offset(lat, lon, dn, de)
            x2, y2, _ = components(coeffs, model.nmax, la2, lo2)
            jac.append(((x2 - x) / step, (y2 - y) / step))
        (a, c), (b, d) = jac
        det = a * d - b * c
        if det == 0.0:
            return None
        north = -(d * x - b * y) / det
        east = -(-c * x + a * y) / det
        # Не больше 200 км за шаг - начало поиска рядом с полюсом.
        size = math.hypot(north, east)
        if size > 200.0:
            north, east = north * 200.0 / size, east * 200.0 / size
        lat, lon = _offset(lat, lon, north, east)
    return None


def year_of(seconds):
    """Год с дробью по секундам UTC от 1970 года, по календарю: 1 января
    - целый год. Средний год давал 2019.997 вместо 2020."""
    epoch = datetime.datetime(1970, 1, 1)
    moment = epoch + datetime.timedelta(seconds=seconds)
    start = datetime.datetime(moment.year, 1, 1)
    length = (datetime.datetime(moment.year + 1, 1, 1) - start)
    return moment.year + (moment - start) / length


def pole(model, track, year):
    """Полюс на год: по таблице в её годах, позже - по IGRF от
    последней точки таблицы. None вне лет таблицы и модели."""
    found = pole_at(track, year)
    if found is not None or not track or year < track[-1][0]:
        return found
    return dip_pole(model, year, track[-1][1:])


def trail(track, year):
    """След полюса - точки таблицы не позже года."""
    return [(lat, lon) for y, lat, lon in track if y <= year]
