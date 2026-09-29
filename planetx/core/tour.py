# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тур: перелёты по остановкам с паузой на каждой, как в Google Earth.

Тур - цепочка перелётов van Wijk-Nuij (core/flight.py). Первый идёт
от позы камеры к первой остановке, каждый следующий - от остановки
к остановке. После прилёта камера стоит pause секунд. Поза - функция
времени тура, а не часов на стене. Навигатор проигрывает тур как
обычный перелёт, пауза и продолжение сдвигают начало отсчёта.

Остановка-путь, как у Google Earth: камера подлетает к началу линии
и едет вдоль неё с постоянной скоростью, азимут следует направлению
пути, наклон постоянный. Точки и многоугольники - остановки по центру.

Решения автора от 28 сентября 2026 года: остановки - отмеченные
флажком «Мои метки» в порядке списка, запись видео и время слоёв
QGIS - позже.
"""
import bisect
import math

import numpy as np

try:  # внутри плагина QGIS
    from .ellipsoid import A
    from .features import densify
    from .flight import Flight
    from .navigation import Pose
except ImportError:  # headless-тесты
    from ellipsoid import A
    from features import densify
    from flight import Flight
    from navigation import Pose

PAUSE = 3.0  # секунд на остановке по умолчанию
# Путь. Расстояние камеры - доля длины пути в пределах, скорость -
# доля расстояния камеры в секунду. Так земля бежит по экрану с одной
# скоростью на пути любой длины, проезд пути длиннее 2.4 км идёт 32 с.
PATH_TILT = 60.0
PATH_VIEW = 8.0  # длина пути / расстояние камеры
PATH_MIN_DISTANCE = 300.0
PATH_MAX_DISTANCE = 20000.0
PATH_SPEED = 0.25  # расстояний камеры в секунду
# Азимут берётся по хорде пути длиной в расстояние камеры, повороты
# линии не дёргают камеру.
PATH_LOOK = 0.5


class Stop:
    """Остановка тура: название и поза в конце перелёта."""

    glide = 0.0  # секунд движения после прилёта

    def __init__(self, name, lat, lon, distance, heading=0.0, tilt=0.0):
        self.name = name
        self.lat = lat
        self.lon = lon
        self.distance = distance
        self.heading = heading
        self.tilt = tilt

    def pose_at(self, t):
        return Pose(self.lat, self.lon, self.distance, self.heading,
                    self.tilt)

    def end_pose(self):
        return self.pose_at(0.0)


def bearing(lat1, lon1, lat2, lon2):
    """Начальный азимут дуги большого круга, градусы от севера."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) \
        * math.cos(dl)
    return math.degrees(math.atan2(x, y)) % 360.0


class PathStop(Stop):
    """Остановка-путь: проезд вдоль линии (широта, долгота)."""

    def __init__(self, name, points, tilt=PATH_TILT):
        pts = densify(points)
        la, lo = np.radians(pts[:, 0]), np.radians(pts[:, 1])
        u = np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                      np.sin(la)], axis=1)
        steps = np.arccos(np.clip((u[:-1] * u[1:]).sum(axis=1),
                                  -1.0, 1.0)) * A
        self.points = pts
        self.s = np.concatenate([[0.0], np.cumsum(steps)])
        self.length = float(self.s[-1])
        distance = min(max(self.length / PATH_VIEW, PATH_MIN_DISTANCE),
                       PATH_MAX_DISTANCE)
        self.glide = self.length / (PATH_SPEED * distance)
        self.look = PATH_LOOK * distance
        lat, lon = pts[0]
        super().__init__(name, float(lat), float(lon), distance,
                         self.heading_at(0.0), tilt)

    def point_at(self, s):
        """Точка пути на расстоянии s от начала."""
        s = min(max(s, 0.0), self.length)
        i = min(int(np.searchsorted(self.s, s, side="right")) - 1,
                len(self.s) - 2)
        i = max(i, 0)
        span = self.s[i + 1] - self.s[i]
        k = (s - self.s[i]) / span if span > 0 else 0.0
        lat, lon = self.points[i] + k * (self.points[i + 1] - self.points[i])
        return float(lat), float(lon)

    def heading_at(self, s):
        a = self.point_at(s - self.look)
        b = self.point_at(s + self.look)
        if a == b:
            return 0.0
        return bearing(a[0], a[1], b[0], b[1])

    def pose_at(self, t):
        """Поза через t секунд проезда."""
        share = min(max(t / self.glide, 0.0), 1.0) if self.glide else 1.0
        s = share * self.length
        lat, lon = self.point_at(s)
        return Pose(lat, lon, self.distance, self.heading_at(s), self.tilt)

    def end_pose(self):
        return self.pose_at(self.glide)


def clock(seconds):
    """Время тура для панели: «м:сс», с часами - «ч:мм:сс»."""
    total = int(max(0.0, seconds) + 0.5)
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    if hours:
        return "%d:%02d:%02d" % (hours, minutes, secs)
    return "%d:%02d" % (minutes, secs)


class Tour:
    """Перелёты от позы start по остановкам stops с паузой pause."""

    def __init__(self, start, stops, pause=PAUSE, fov_y=45.0):
        self.stops = list(stops)
        self.pause = max(0.0, float(pause))
        self.starts = []  # время начала перелёта к каждой остановке
        self.glides = []  # время прилёта и начала проезда
        self.arrivals = []  # время, когда камера встала на остановке
        self.flights = []
        t = 0.0
        pose = start
        for stop in self.stops:
            flight = Flight(pose, stop.lat, stop.lon, stop.distance,
                            stop.heading, stop.tilt, fov_y=fov_y)
            self.starts.append(t)
            self.flights.append(flight)
            t += flight.duration
            self.glides.append(t)
            t += stop.glide
            self.arrivals.append(t)
            t += self.pause
            pose = stop.end_pose()
        self.duration = t
        self.start = start.copy()

    def index_at(self, t):
        """Номер остановки, к которой летит или на которой стоит камера."""
        if not self.stops:
            return -1
        return max(0, bisect.bisect_right(self.starts, t) - 1)

    def arrived(self, t):
        """Стоит ли камера на остановке, а не летит и не едет."""
        i = self.index_at(t)
        return i >= 0 and t >= self.arrivals[i]

    def pose_at(self, t):
        if not self.stops:
            return self.start.copy()
        i = self.index_at(t)
        stop = self.stops[i]
        if t < self.glides[i]:
            return self.flights[i].pose_at(t - self.starts[i])
        return stop.pose_at(t - self.glides[i])
