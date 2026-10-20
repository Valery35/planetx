# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Растущие треки: точки объектов по времени, путь к моменту t.

Расчёт без Qt. Трек - точки одного или нескольких объектов с временем
в секундах от 1970 года. К моменту t у объекта пройденный путь -
его точки не позже t и точка на отрезке, по которому он идёт в t.
Положение между точками линейное по времени. До первой точки объекта
нет, после последней он стоит в ней.

Решения автора от 28 сентября 2026 года: треки из точечного слоя QGIS
с полем времени, время задаёт временной контроллер QGIS, камера идёт
следом по ходу движения.

У точки может быть высота в метрах (просьба автора от 19 октября 2026
года - самолёты и дроны): между точками она тоже линейна по времени.
Нет высоты - NaN.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .tour import bearing
except ImportError:  # headless-тесты
    from tour import bearing

# Азимут по хорде пути за это время до момента t, секунд. Отдельные
# точки GPS дрожат, азимут по последнему отрезку дёргал бы камеру.
HEADING_SPAN = 30.0


class Position:
    """Объект в момент t: путь, текущая точка, азимут движения, высота
    точки и высоты пути в метрах или NaN."""

    def __init__(self, key, path, lat, lon, heading, alt=math.nan,
                 alts=None):
        self.key = key
        self.path = path  # [(широта, долгота)], последняя - текущая
        self.lat = lat
        self.lon = lon
        self.heading = heading
        self.alt = alt
        self.alts = alts  # высоты точек path или None


class Glide:
    """Плавный переход камеры за объектом между шагами времени.

    Навигатор проигрывает его как перелёт: поза - функция времени
    от start к end за duration секунд, азимут по кратчайшему повороту.
    """

    def __init__(self, start, end, duration):
        self.start = start.copy()
        self.end = end.copy()
        self.duration = max(float(duration), 1e-3)
        self.turn = (end.heading - start.heading + 180.0) % 360.0 - 180.0

    def pose_at(self, t):
        k = min(max(t / self.duration, 0.0), 1.0)
        pose = self.end.copy()
        pose.lat = self.start.lat + k * (self.end.lat - self.start.lat)
        dlon = (self.end.lon - self.start.lon + 180.0) % 360.0 - 180.0
        pose.lon = (self.start.lon + k * dlon + 180.0) % 360.0 - 180.0
        pose.distance = self.start.distance + k * (self.end.distance
                                                   - self.start.distance)
        pose.heading = (self.start.heading + k * self.turn) % 360.0
        pose.tilt = self.start.tilt + k * (self.end.tilt - self.start.tilt)
        return pose


class Track:
    """Точки объектов по времени.

    items - (объект, время, широта, долгота) или с высотой пятым
    числом. Точки без времени пропускает тот, кто читает слой. Точки
    одного объекта с одинаковым временем оставляются первой.
    """

    def __init__(self, items):
        groups = {}
        for item in items:
            key, t, lat, lon = item[:4]
            alt = float(item[4]) if len(item) > 4 and item[4] is not None \
                else math.nan
            groups.setdefault(key, []).append((float(t), float(lat),
                                               float(lon), alt))
        self.objects = {}
        self.alts = {}
        for key, rows in groups.items():
            rows.sort(key=lambda r: r[0])
            data = np.asarray(rows, dtype=np.float64)
            keep = np.concatenate([[True], np.diff(data[:, 0]) > 0])
            data = data[keep]
            self.objects[key] = (data[:, 0], data[:, 1], data[:, 2])
            self.alts[key] = data[:, 3]
        times = [t for t, _, _ in self.objects.values() if len(t)]
        self.start = min(t[0] for t in times) if times else None
        self.end = max(t[-1] for t in times) if times else None

    def _point(self, times, lats, lons, t):
        """Положение объекта в момент t: номер последней точки не позже t
        и точка на отрезке."""
        i = int(np.searchsorted(times, t, side="right")) - 1
        if i >= len(times) - 1:
            return len(times) - 1, (lats[-1], lons[-1])
        span = times[i + 1] - times[i]
        k = (t - times[i]) / span if span > 0 else 0.0
        return i, (lats[i] + k * (lats[i + 1] - lats[i]),
                   lons[i] + k * (lons[i + 1] - lons[i]))

    def at(self, t=None):
        """Объекты в момент t, None - весь трек, объект в конце пути."""
        out = []
        for key, (times, lats, lons) in self.objects.items():
            heights = self.alts[key]
            if not len(times):
                continue
            moment = times[-1] if t is None else t
            if moment < times[0]:
                continue
            i, (lat, lon) = self._point(times, lats, lons, moment)
            path = list(zip(lats[:i + 1].tolist(), lons[:i + 1].tolist()))
            if path[-1] != (lat, lon):
                path.append((float(lat), float(lon)))
            _, (lat0, lon0) = self._point(times, lats, lons,
                                          max(times[0],
                                              moment - HEADING_SPAN))
            heading = bearing(lat0, lon0, lat, lon) \
                if (lat0, lon0) != (lat, lon) else math.nan
            alt, alts = math.nan, None
            if not np.all(np.isnan(heights)):
                _, (alt, _) = self._point(times, heights, heights, moment)
                alts = heights[:i + 1].tolist()
                if len(alts) < len(path):
                    alts.append(float(alt))
            out.append(Position(key, path, float(lat), float(lon),
                                heading, float(alt), alts))
        return out


def model_pose(rows, t):
    """Поза модели gx:Track с Model на момент t: (широта, долгота,
    высота, азимут, наклон, крен) или None вне времени трека.

    rows - [секунды, широта, долгота, высота, азимут, наклон, крен] по
    возрастанию времени, азимут None - без gx:angles, он берётся по
    направлению движения. Между точками всё идёт линейно, азимут - по
    кратчайшему повороту."""
    if not rows or t < rows[0][0] or t > rows[-1][0]:
        return None
    times = [r[0] for r in rows]
    i = max(0, min(int(np.searchsorted(times, t, side="right")) - 1,
                   len(rows) - 1))
    j = min(i + 1, len(rows) - 1)
    span = rows[j][0] - rows[i][0]
    k = (t - rows[i][0]) / span if span > 0 else 0.0
    a, b = rows[i], rows[j]

    def mix(n):
        return a[n] + (b[n] - a[n]) * k
    lat, lon, alt = mix(1), mix(2), mix(3)
    if a[4] is None or b[4] is None:
        p, q = (a, b) if j != i else (rows[max(i - 1, 0)], a)
        heading = bearing(p[1], p[2], q[1], q[2]) \
            if (p[1], p[2]) != (q[1], q[2]) else 0.0
        return lat, lon, alt, heading, 0.0, 0.0
    turn = (b[4] - a[4] + 180.0) % 360.0 - 180.0
    return (lat, lon, alt, (a[4] + turn * k) % 360.0, mix(5),
            (mix(6) if a[6] is not None and b[6] is not None else 0.0))
