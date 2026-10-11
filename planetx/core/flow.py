# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Струйки ветра и течений - частицы по полю скоростей. Без Qt.

Просьба автора от 11 октября 2026 года со снимком ролика о ветрах
Земли - «взгляни визуализацию ветра, и течения добавь». Частицы
рождаются в рамке вида, плывут по полю U, V (м/с, восток и север)
и тянут за собой след из TRAIL прежних положений. Отмерив свой век
или уйдя из рамки и с данных (суша у течений), частица рождается
заново. Скорость на экране не настоящая - поле проходит за секунду
показа долю SHARE ширины вида при типичной скорости typical, иначе
течение в 0.5 м/с стояло бы на месте, а ветер вблизи улетал бы.

Сетка поля - строки с севера на юг, как у core.weather.Grid. Величины -
выбор помощника, утверждает автор.
"""
import math

import numpy as np

RADIUS = 6371000.0
TRAIL = 14  # положений в следе частицы
AGE = (40, 100)  # век частицы, шагов, случайный в этих пределах
SHARE = 0.12  # доля ширины вида за секунду при типичной скорости
# Цвета струек течений по скорости, м/с, светлые - на синем океане
# тёмные струйки не видны. Ветер рисуется белым поверх своей раскраски.
CURRENT_STOPS = ((0.05, (200, 230, 255)), (0.25, (110, 240, 255)),
                 (0.5, (140, 255, 140)), (1.0, (255, 240, 80)),
                 (1.5, (255, 150, 40)), (2.5, (255, 60, 90)))


class VectorGrid:
    """Поле скоростей u, v на сетке широт и долгот. west, north - центр
    левого верхнего узла, step - шаг в градусах, строки с севера на юг,
    NaN - нет данных."""

    def __init__(self, u, v, west, north, step):
        self.u = np.asarray(u, dtype=np.float32)
        self.v = np.asarray(v, dtype=np.float32)
        self.west = float(west)
        self.north = float(north)
        self.step = float(step)

    def sample(self, lats, lons):
        """u и v в точках, билинейно, долгота по кругу. Узел без данных
        делает точку пустой (NaN)."""
        rows, cols = self.u.shape
        y = (self.north - np.asarray(lats, dtype=np.float64)) / self.step
        x = ((np.asarray(lons, dtype=np.float64) - self.west) / self.step) \
            % cols
        outside = (y < 0.0) | (y > rows - 1.0)
        y = np.clip(y, 0.0, rows - 1.0)
        y0 = np.minimum(np.floor(y).astype(np.int64), rows - 2)
        x0 = np.floor(x).astype(np.int64) % cols
        x1 = (x0 + 1) % cols
        fy = y - y0
        fx = x - np.floor(x)
        out = []
        for grid in (self.u, self.v):
            top = grid[y0, x0] * (1.0 - fx) + grid[y0, x1] * fx
            bottom = grid[y0 + 1, x0] * (1.0 - fx) + grid[y0 + 1, x1] * fx
            value = top * (1.0 - fy) + bottom * fy
            value[outside] = np.nan
            out.append(value)
        return out[0], out[1]


def spawn(count, box, rng):
    """Точки, равномерные по площади в рамке (запад, юг, восток, север),
    рамка может переходить линию перемены дат."""
    west, south, east, north = box
    width = (east - west) % 360.0 or 360.0
    s = math.sin(math.radians(south))
    n = math.sin(math.radians(north))
    lats = np.degrees(np.arcsin(rng.uniform(s, n, count)))
    lons = (west + rng.uniform(0.0, width, count) + 180.0) % 360.0 - 180.0
    return lats, lons


def inside(lats, lons, box):
    west, south, east, north = box
    keep = (lats >= south) & (lats <= north)
    if (east - west) % 360.0 == 0.0:
        return keep
    if west <= east:
        return keep & (lons >= west) & (lons <= east)
    return keep & ((lons >= west) | (lons <= east))


class Particles:
    """Частицы со следом. lats, lons - (n, TRAIL), столбец 0 - голова.
    speed - скорость поля у головы, м/с."""

    def __init__(self, count, seed=0):
        self.count = count
        self.rng = np.random.default_rng(seed)
        self.lats = np.zeros((count, TRAIL))
        self.lons = np.zeros((count, TRAIL))
        self.speed = np.zeros(count)
        self.age = np.zeros(count, dtype=np.int64)
        self.life = np.zeros(count, dtype=np.int64)
        self.fresh = np.ones(count, dtype=bool)  # след ещё не тянется
        self.box = None

    def reset(self, box):
        """Все частицы заново в рамке box."""
        self.box = box
        self._respawn(np.arange(self.count))
        # Возраст вразброс, иначе все частицы перерождались бы разом.
        self.age = self.rng.integers(0, AGE[1], self.count)

    def _respawn(self, which):
        if not len(which):
            return
        lats, lons = spawn(len(which), self.box, self.rng)
        self.lats[which] = lats[:, None]
        self.lons[which] = lons[:, None]
        self.age[which] = 0
        self.life[which] = self.rng.integers(AGE[0], AGE[1], len(which))
        self.speed[which] = 0.0
        self.fresh[which] = True

    def step(self, field, dt, metres_per_mps):
        """Шаг dt секунд показа: голова сдвигается на скорость поля,
        умноженную на metres_per_mps метров за секунду на 1 м/с."""
        if self.box is None:
            return
        u, v = field.sample(self.lats[:, 0], self.lons[:, 0])
        dead = ~np.isfinite(u) | ~np.isfinite(v)
        u = np.where(dead, 0.0, u)
        v = np.where(dead, 0.0, v)
        distance = metres_per_mps * dt
        lat = self.lats[:, 0]
        cos_lat = np.maximum(np.cos(np.radians(lat)), 0.05)
        new_lat = lat + np.degrees(v * distance / RADIUS)
        new_lon = self.lons[:, 0] + np.degrees(
            u * distance / (RADIUS * cos_lat))
        new_lon = (new_lon + 180.0) % 360.0 - 180.0
        self.lats[:, 1:] = self.lats[:, :-1]
        self.lons[:, 1:] = self.lons[:, :-1]
        self.lats[:, 0] = np.clip(new_lat, -89.9, 89.9)
        self.lons[:, 0] = new_lon
        self.speed = np.hypot(u, v)
        self.age += 1
        self.fresh &= self.age < TRAIL
        gone = dead | (self.age > self.life) \
            | ~inside(self.lats[:, 0], self.lons[:, 0], self.box)
        self._respawn(np.nonzero(gone)[0])


def metres_per_mps(view_width, typical):
    """Метров за секунду показа на 1 м/с поля: типичная скорость
    проходит долю SHARE ширины вида."""
    return SHARE * view_width / max(typical, 1e-6)


def segments(particles):
    """Отрезки следов: пары точек (m, 2, 2) широта и долгота и доля
    от головы 0..1 у каждого отрезка. Отрезки через линию перемены дат
    и у новорождённых частиц отбрасываются."""
    lat, lon = particles.lats, particles.lons
    a = np.stack([lat[:, :-1], lon[:, :-1]], axis=-1)
    b = np.stack([lat[:, 1:], lon[:, 1:]], axis=-1)
    keep = np.abs(a[..., 1] - b[..., 1]) < 90.0
    depth = np.arange(TRAIL - 1)[None, :] < np.minimum(
        particles.age, TRAIL - 1)[:, None]
    keep &= depth
    share = np.broadcast_to(np.arange(TRAIL - 1) / (TRAIL - 1.0),
                            keep.shape)
    pairs = np.stack([a[keep], b[keep]], axis=1)
    return pairs, share[keep], np.broadcast_to(
        particles.speed[:, None], keep.shape)[keep]


def current_colors(speed):
    """Цвета струек течений (n, 3) 0..255 по скорости, м/с."""
    speed = np.asarray(speed, dtype=np.float64)
    values = np.array([s[0] for s in CURRENT_STOPS])
    colors = np.array([s[1] for s in CURRENT_STOPS], dtype=np.float64)
    return np.stack([np.interp(speed, values, colors[:, k])
                     for k in range(3)], axis=1)
