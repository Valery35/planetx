# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Перелёт по методу van Wijk и Nuij.

Статья «Smooth and efficient zooming and panning», 2003. Путь строится
в плоскости (u, w). Здесь u - расстояние по дуге большого круга между
точками взгляда, w - ширина видимой полосы. Ширина пропорциональна
расстоянию камеры до точки взгляда, w = 2·d·tan(fov/2).

Метрика пути - ds² = (ρ²·du² + dw²/ρ²) / w². Оптимальный путь в ней
задаётся формулами статьи, длина пути S. Проверка метрики по формулам
пути - в tests/test_flight.py. Камера проходит путь
с постоянной скоростью в этой метрике, время перелёта пропорционально S.

Величины r0 и r1 статьи записаны через asinh. Исходная запись
ln(-b + sqrt(b² + 1)) теряет точность при большом b, то есть при
перелёте на большое расстояние у самой земли.
"""
import math

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .navigation import Pose, max_altitude
except ImportError:  # headless-тесты
    import ellipsoid
    from navigation import Pose, max_altitude

RHO = math.sqrt(2.0)
SPEED = 2.0  # единиц длины пути S в секунду
MIN_TIME = 1.0
MAX_TIME = 8.0
PURE_ZOOM = 1.0  # метров, ближе этого точки взгляда считаются одной


class Path:
    """Путь van Wijk-Nuij от (0, w0) до (u1, w1)."""

    def __init__(self, u1, w0, w1):
        self.u1, self.w0, self.w1 = u1, w0, w1
        if u1 < PURE_ZOOM:
            self.zoom_only = True
            self.k = 1.0 if w1 >= w0 else -1.0
            self.length = abs(math.log(w1 / w0)) / RHO
            return
        self.zoom_only = False
        rho2 = RHO * RHO
        rho4 = rho2 * rho2
        b0 = (w1 * w1 - w0 * w0 + rho4 * u1 * u1) / (2.0 * w0 * rho2 * u1)
        b1 = (w1 * w1 - w0 * w0 - rho4 * u1 * u1) / (2.0 * w1 * rho2 * u1)
        # ln(-b + sqrt(b² + 1)) = -asinh(b)
        self.r0 = -math.asinh(b0)
        self.r1 = -math.asinh(b1)
        self.length = (self.r1 - self.r0) / RHO

    def at(self, s):
        """Точка (u, w) на пути, s от 0 до length."""
        if self.zoom_only:
            return 0.0, self.w0 * math.exp(self.k * RHO * s)
        r0 = self.r0
        c = self.w0 / (RHO * RHO)
        u = c * math.cosh(r0) * math.tanh(RHO * s + r0) - c * math.sinh(r0)
        w = self.w0 * math.cosh(r0) / math.cosh(RHO * s + r0)
        return u, w


def _unit(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return (math.cos(la) * math.cos(lo), math.cos(la) * math.sin(lo),
            math.sin(la))


def _angle(p, q):
    dot = sum(a * b for a, b in zip(p, q))
    cross = (p[1] * q[2] - p[2] * q[1], p[2] * q[0] - p[0] * q[2],
             p[0] * q[1] - p[1] * q[0])
    return math.atan2(math.sqrt(sum(c * c for c in cross)), dot)


def _slerp(p, q, angle, share):
    """Точка на дуге большого круга от p к q, доля share пути."""
    if angle < 1e-15:
        return p
    sin = math.sin(angle)
    a = math.sin((1.0 - share) * angle) / sin
    b = math.sin(share * angle) / sin
    return tuple(a * x + b * y for x, y in zip(p, q))


def _smooth(share):
    """Плавный вход и выход, производная на концах нулевая."""
    return share * share * (3.0 - 2.0 * share)


class Flight:
    """Перелёт от позы start к точке взгляда (lat, lon) с расстоянием.

    Азимут и наклон плавно приходят к heading и tilt. Точка взгляда идёт
    по дуге большого круга. Широта и долгота берутся как углы на сфере,
    поэтому концы пути совпадают с позами точно. Отличие дуги такой
    сферы от геодезической линии эллипсоида на плавность не влияет.
    """

    def __init__(self, start, lat, lon, distance, heading=0.0, tilt=0.0,
                 fov_y=45.0):
        self.start = start.copy()
        self.end = Pose(lat, lon, distance, heading, tilt)
        self.p0 = _unit(start.lat, start.lon)
        self.p1 = _unit(lat, lon)
        self.angle = _angle(self.p0, self.p1)
        self.scale = 2.0 * math.tan(math.radians(fov_y) / 2.0)
        self.path = Path(ellipsoid.A * self.angle, start.distance * self.scale,
                         distance * self.scale)
        self.duration = min(MAX_TIME, max(MIN_TIME,
                                          self.path.length / SPEED))
        # Поворот по кратчайшему пути, не больше 180°.
        self.turn = (heading - start.heading + 180.0) % 360.0 - 180.0

    def s_at(self, t):
        """Длина пройденного пути ко времени t, скорость постоянна."""
        share = min(1.0, max(0.0, t / self.duration))
        return share * self.path.length

    def pose_at(self, t):
        if t >= self.duration:
            return self.end.copy()
        s = self.s_at(t)
        u, w = self.path.at(s)
        share = 0.0 if self.path.zoom_only else u / self.path.u1
        x, y, z = _slerp(self.p0, self.p1, self.angle, share)
        lat = math.degrees(math.atan2(z, math.hypot(x, y)))
        lon = math.degrees(math.atan2(y, x))
        blend = _smooth(t / self.duration)
        pose = Pose(lat, lon, min(w / self.scale, max_altitude()),
                    (self.start.heading + self.turn * blend) % 360.0,
                    self.start.tilt + (self.end.tilt - self.start.tilt)
                    * blend)
        return pose


FIT_MARGIN = 1.2  # запас вокруг охвата при перелёте к слою
MIN_FIT_DISTANCE = 300.0  # метров, ближе к точечному слою не подлетаем
M_PER_DEGREE = 111320.0


def fit_view(west, south, east, north, fov_y, aspect):
    """Точка взгляда и расстояние, с которых охват виден целиком.

    Охват в градусах WGS84. Камера смотрит отвесно в середину охвата.
    Ширина считается по средней широте. Расстояние - такое, чтобы
    охват с запасом FIT_MARGIN поместился и по высоте, и по ширине
    кадра, но не меньше MIN_FIT_DISTANCE.
    """
    lat = 0.5 * (south + north)
    lon = 0.5 * (west + east)
    height = (north - south) * M_PER_DEGREE
    width = (east - west) * M_PER_DEGREE * math.cos(math.radians(lat))
    half = math.tan(math.radians(fov_y) / 2.0)
    distance = max(height, width / aspect) * FIT_MARGIN / (2.0 * half)
    return lat, lon, max(distance, MIN_FIT_DISTANCE)


def parse_latlon(text):
    """Широта и долгота из строки или None.

    Понимает «58.0105, 56.2294», «58.0105 56.2294» и запись с запятой
    в дробной части через точку с запятой: «58,0105; 56,2294».
    """
    text = text.strip()
    if ";" in text:
        parts = [p.strip().replace(",", ".") for p in text.split(";")]
    elif "," in text:
        parts = [p.strip() for p in text.split(",")]
    else:
        parts = text.split()
    if len(parts) != 2:
        return None
    try:
        lat, lon = float(parts[0]), float(parts[1])
    except ValueError:
        return None
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon
