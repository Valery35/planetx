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
import datetime
import math
from collections import namedtuple

import numpy as np

RADIUS = 6371000.0
TRAIL = 14  # положений в следе частицы
AGE = (40, 100)  # век частицы, шагов, случайный в этих пределах
SHARE = 0.12  # доля ширины вида за секунду при типичной скорости
# Цвета заливки скорости течений, м/с. С 12 октября 2026 года, просьба
# автора, под струйками течений лежит заливка скорости, струйки белые,
# как у ветра. Прежде светлые цвета были у самих струек.
CURRENT_STOPS = ((0.05, (20, 40, 110)), (0.2, (30, 120, 200)),
                 (0.4, (40, 200, 170)), (0.7, (150, 230, 70)),
                 (1.0, (250, 220, 40)), (1.5, (250, 130, 30)),
                 (2.5, (230, 40, 70)))
# Непрозрачность заливки по скорости, 0..255: медленная вода почти
# прозрачна, снимок океана под ней виден. Синие цвета медленной воды
# терялись на синем океане, первый вариант это показал. Выбор помощника.
FILL_ALPHA = ((0.0, 0.0), (0.08, 40.0), (0.2, 120.0), (0.5, 190.0),
              (1.0, 220.0), (2.5, 230.0))
FILL_LEVEL = 4  # предельный уровень тайлов заливки, пиксель 0.09°


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


CAP = "cap"  # рамка-круг: (CAP, широта, долгота, угловой радиус, °)


def cap_box(lat, lon, angle):
    """Рамка-круг на шаре: центр и угловой радиус в градусах. Издалека
    рамка - видимый круг Земли, прежде прямоугольник широт и долгот
    захватывал обратную сторону шара, и там рождались две трети частиц,
    12 октября 2026 года."""
    return (CAP, float(lat), float(lon), float(angle))


def _cap_cos(lats, lons, box):
    """Косинус угла от центра круга до точек."""
    _, lat0, lon0, _ = box
    a = np.radians(lats)
    b = math.radians(lat0)
    return np.sin(a) * math.sin(b) + np.cos(a) * math.cos(b) * np.cos(
        np.radians(np.asarray(lons) - lon0))


def spawn(count, box, rng):
    """Точки, равномерные по площади в рамке (запад, юг, восток, север)
    или в круге cap_box, рамка может переходить линию перемены дат."""
    if box[0] == CAP:
        _, lat0, lon0, angle = box
        d = np.arccos(rng.uniform(math.cos(math.radians(angle)), 1.0,
                                  count))
        az = rng.uniform(0.0, 2.0 * math.pi, count)
        b = math.radians(lat0)
        lat = np.arcsin(math.sin(b) * np.cos(d)
                        + math.cos(b) * np.sin(d) * np.cos(az))
        lon = math.radians(lon0) + np.arctan2(
            np.sin(az) * np.sin(d) * math.cos(b),
            np.cos(d) - math.sin(b) * np.sin(lat))
        lons = (np.degrees(lon) + 180.0) % 360.0 - 180.0
        return np.degrees(lat), lons
    west, south, east, north = box
    width = (east - west) % 360.0 or 360.0
    s = math.sin(math.radians(south))
    n = math.sin(math.radians(north))
    lats = np.degrees(np.arcsin(rng.uniform(s, n, count)))
    lons = (west + rng.uniform(0.0, width, count) + 180.0) % 360.0 - 180.0
    return lats, lons


def inside(lats, lons, box):
    if box[0] == CAP:
        return _cap_cos(lats, lons, box) >= math.cos(math.radians(box[3]))
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


# Доля клетки поля, которую типичная скорость проходит за шаг показа,
# не больше. Замечание автора от 12 октября 2026 года со снимком
# Атлантики с 12 800 км - «что-то не то с течениями». Издалека частица
# течений за шаг перескакивала клетку 0.5°, след тянулся на 420 км через
# вихри петлями. На поле течений того дня с долей 0.3 след - 110 км,
# у десятой части частиц путь длиннее прямой на 23 % вместо 99 %.
# Величина - выбор помощника.
CELL_SHARE = 0.3


def display_metres(view_width, typical, step_deg, dt, share=None):
    """Метров за секунду показа на 1 м/с поля: доля SHARE ширины вида,
    но типичная скорость за шаг dt секунд проходит не больше доли share
    клетки поля шагом step_deg градусов. share None - без предела.
    Предел действует издалека, вблизи остаётся доля ширины вида."""
    metres = metres_per_mps(view_width, typical)
    if share is None:
        return metres
    cell = math.radians(step_deg) * RADIUS
    return min(metres, share * cell / (max(typical, 1e-6) * dt))


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


CURRENTS_FIRST = "2017-02-13"  # первый день ряда течений NOAA CoastWatch


def current_day(moment, last, first=CURRENTS_FIRST):
    """День течений «ГГГГ-ММ-ДД» для момента moment (секунды UTC) или
    последний готовый last при None. За краями ряда - первый или
    последний день."""
    if moment is None or not last:
        return last
    day = datetime.datetime.fromtimestamp(
        moment, datetime.timezone.utc).strftime("%Y-%m-%d")
    return min(max(day, first), last)


def day_seconds(day):
    """Полдень дня «ГГГГ-ММ-ДД» в секундах UTC."""
    moment = datetime.datetime.strptime(day, "%Y-%m-%d").replace(
        hour=12, tzinfo=datetime.timezone.utc)
    return moment.timestamp()


def current_colors(speed):
    """Цвета заливки течений (n, 3) 0..255 по скорости, м/с."""
    speed = np.asarray(speed, dtype=np.float64).ravel()
    values = np.array([s[0] for s in CURRENT_STOPS])
    colors = np.array([s[1] for s in CURRENT_STOPS], dtype=np.float64)
    return np.stack([np.interp(speed, values, colors[:, k])
                     for k in range(3)], axis=1)


FillJob = namedtuple("FillJob", "grid box")
FillJob.__doc__ = """Поле течений для картинок тайлов заливки: VectorGrid
и рамка всего мира (юг, север, запад, восток)."""


def fill_job(grid):
    return FillJob(grid, (-90.0, 90.0, -180.0, 180.0))


def speed_rgba(task, lats, lons, radius=None):
    """Картинка тайла заливки скорости: RGBA uint8 с премноженной альфой
    по сетке широт и долгот. Суша и места без данных прозрачны."""
    u, v = task.grid.sample(np.ravel(lats), np.ravel(lons))
    speed = np.hypot(u, v)
    rgb = current_colors(np.nan_to_num(speed))
    alpha = np.interp(np.nan_to_num(speed), [a for a, _ in FILL_ALPHA],
                      [b for _, b in FILL_ALPHA])
    alpha[~np.isfinite(speed)] = 0.0
    out = np.empty((rgb.shape[0], 4), dtype=np.uint8)
    out[:, :3] = np.rint(rgb * (alpha / 255.0)[:, None])
    out[:, 3] = np.rint(alpha)
    return out.reshape(np.shape(lats) + (4,))
