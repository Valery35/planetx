# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Одна шкала времени сцены: тур, треки и время данных (шаг 13).

Расчёт без Qt. Время записи идёт кадрами по FPS в секунду. Кадр n -
момент тура n / FPS: поза камеры из тура, время данных - промежуток
временного контроллера, растянутый на длительность тура. Без
промежутка время данных стоит.

Запись начинается с первой остановки тура, а не с позы камеры в момент
записи. Иначе повтор записи начинался бы с другой позы. Решения
помощника от 28 сентября 2026 года, их утверждает автор.
"""
import math

try:  # внутри плагина QGIS
    from .navigation import Pose
    from .tour import Tour
except ImportError:  # headless-тесты
    from navigation import Pose
    from tour import Tour

FPS = 25


class Frame:
    """Кадр записи: номер, время тура, поза камеры, время данных."""

    def __init__(self, number, t, pose, moment):
        self.number = number
        self.t = t
        self.pose = pose
        self.moment = moment


class Timeline:
    """Кадры тура по stops с паузой pause при FPS кадрах в секунду.

    data - (начало, конец) времени данных в секундах или None.
    """

    def __init__(self, stops, pause, data=None, fps=FPS, fov_y=45.0):
        stops = list(stops)
        if not stops:
            raise ValueError("no stops")
        first = stops[0].pose_at(0.0)
        start = Pose(first.lat, first.lon, first.distance, first.heading,
                     first.tilt)
        self.tour = Tour(start, stops, pause, fov_y)
        self.fps = float(fps)
        self.data = data
        self.count = int(math.floor(self.tour.duration * self.fps)) + 1

    def moment(self, t):
        if self.data is None:
            return None
        begin, end = self.data
        share = t / self.tour.duration if self.tour.duration else 1.0
        return begin + (end - begin) * min(max(share, 0.0), 1.0)

    def frame(self, n):
        t = n / self.fps
        return Frame(n, t, self.tour.pose_at(t), self.moment(t))

    def frames(self):
        return (self.frame(n) for n in range(self.count))
