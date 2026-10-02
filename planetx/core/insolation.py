# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Инсоляция - часы прямого солнечного света в сутки по рельефу.
Расчёт без Qt.

Шаг 3 плана фазы 3 (doc/PLAN_PHASE3.md), решение автора от 2 октября
2026 года. Положение солнца - core/sun.py, только у Земли.

Высоты берутся на квадратной сетке с равным шагом в метрах вокруг
точки: внутренний круг радиуса radius_m и поле вокруг шириной не меньше
MIN_HORIZON - из него берутся тени гор. Сетка - GRID узлов на сторону.
Для каждого внутреннего узла заранее считается горизонт - тангенс
наибольшего угла на рельеф по AZIMUTHS азимутам на расстоянии до
ширины поля, с опусканием за кривизну d² / 2R. Узел освещён в момент,
если солнце выше горизонта по своему азимуту и падает на поверхность
с её стороны (скалярное произведение нормали и направления на солнце
больше нуля).

Моменты - через STEP секунд по всем суткам UTC промежутка, если суток
больше MAX_DAYS - по MAX_DAYS суткам, равномерно. Итог - среднее
количество часов прямого света в сутки. Направление на солнце одно
для всей сетки, по центральной точке: на 20 км его азимут и высота
меняются меньше чем на 0.2°. Рефракция и облака не учитываются.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .sun import direction
    from .viewshed import distance_bearing
except ImportError:  # headless-тесты
    import ellipsoid
    from sun import direction
    from viewshed import distance_bearing

STEP = 600.0  # с между положениями солнца
MAX_DAYS = 15  # суток в расчёте, остальные пропускаются равномерно
AZIMUTHS = 32  # направлений горизонта
GRID = 800  # узлов сетки высот на сторону
MIN_HORIZON = 5000.0  # м, наименьшая ширина поля для теней гор
GROWTH = 1.08  # рост шага по лучу горизонта
DAY = 86400.0
OPACITY = 0.6
# Шкала часов в долях наибольшего значения: синий - мало света,
# красный - много.
STOPS = ((0.0, (49, 54, 149)), (0.2, (69, 117, 180)),
         (0.4, (171, 217, 233)), (0.6, (254, 224, 144)),
         (0.8, (244, 109, 67)), (1.0, (215, 48, 39)))


def sample_times(start, end):
    """Моменты расчёта и вес момента в часах на сутки.

    start и end - начало первых и последних суток промежутка, секунды
    UTC. Сутки берутся все, если их не больше MAX_DAYS, иначе MAX_DAYS
    равномерно."""
    days = int(round((end - start) / DAY)) + 1
    count = min(max(days, 1), MAX_DAYS)
    picked = np.unique(np.rint(np.linspace(0, days - 1, count)))
    per_day = np.arange(int(DAY / STEP)) * STEP + STEP / 2.0
    times = (start + picked[:, None] * DAY + per_day[None, :]).ravel()
    return times, STEP / 3600.0 / len(picked)


def sun_enu(lat, lon, times):
    """Направление на солнце в осях восток, север, верх точки:
    массив (моменты, 3)."""
    la, lo = math.radians(lat), math.radians(lon)
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo),
                      -math.sin(la) * math.sin(lo), math.cos(la)])
    up = np.array([math.cos(la) * math.cos(lo),
                   math.cos(la) * math.sin(lo), math.sin(la)])
    sun = np.array([direction(t) for t in times])
    return np.stack([sun @ east, sun @ north, sun @ up], axis=-1)


def layout(radius_m):
    """Шаг сетки, узлов поля с каждой стороны и внутренних узлов."""
    field = max(radius_m, MIN_HORIZON)
    cell = 2.0 * (radius_m + field) / GRID
    margin = int(math.ceil(field / cell))
    return cell, margin, GRID - 2 * margin


def grid_axes(lat, lon, cell, n, radius):
    """Широты строк (с юга на север) и долготы столбцов сетки n×n
    с шагом cell метров и центром в точке."""
    offsets = (np.arange(n) - (n - 1) / 2.0) * cell
    lats = lat + np.degrees(offsets / radius)
    lons = lon + np.degrees(offsets / (radius * math.cos(math.radians(lat))))
    return lats, lons


def ray_steps(cell, field):
    """Расстояния вдоль луча горизонта: от шага сетки до ширины поля,
    шаг растёт в GROWTH раз, но не меньше шага сетки."""
    out = []
    d = cell
    while d <= field:
        out.append(d)
        d = max(d * GROWTH, d + cell)
    return out


def shifts(cell, margin):
    """Сдвиги сетки для горизонта: по азимутам списки (di, dj) без
    повторов, di - к северу, dj - к востоку, в узлах."""
    steps = ray_steps(cell, margin * cell)
    out = []
    for k in range(AZIMUTHS):
        a = 2.0 * math.pi * k / AZIMUTHS
        seen = []
        for d in steps:
            pair = (int(round(d * math.cos(a) / cell)),
                    int(round(d * math.sin(a) / cell)))
            if pair != (0, 0) and pair not in seen:
                seen.append(pair)
        out.append(seen)
    return out


def horizon_parts(h, cell, margin, radius, out):
    """Тангенс угла горизонта внутренних узлов в out (азимуты, n, n),
    по частям: после каждого сдвига сетки - yield. Строки h идут
    с юга на север."""
    inner = h.shape[0] - 2 * margin
    base = h[margin:margin + inner, margin:margin + inner]
    for k, pairs in enumerate(shifts(cell, margin)):
        best = np.full((inner, inner), -np.inf)
        for di, dj in pairs:
            dist = math.hypot(di, dj) * cell
            target = h[margin + di:margin + di + inner,
                       margin + dj:margin + dj + inner]
            drop = dist * dist / (2.0 * radius)
            np.maximum(best, (target - drop - base) / dist, out=best)
            yield
        out[k] = best


def horizon(h, cell, margin, radius):
    """Тангенс угла горизонта внутренних узлов по AZIMUTHS азимутам,
    массив (азимуты, n, n)."""
    inner = h.shape[0] - 2 * margin
    out = np.empty((AZIMUTHS, inner, inner), dtype=np.float32)
    for _ in horizon_parts(h, cell, margin, radius, out):
        pass
    return out


class Insolation:
    """Часы прямого света в сутки на внутренней сетке: hours (n, n),
    строки с юга на север, центр сетки - точка (lat, lon)."""

    def __init__(self, lat, lon, radius_m, cell, hours, days, radius):
        self.lat = lat
        self.lon = lon
        self.radius_m = radius_m
        self.cell = cell
        self.hours = hours
        self.days = days
        self.dlat = math.degrees(cell / radius)
        self.dlon = math.degrees(cell / (radius * math.cos(
            math.radians(lat))))

    @property
    def top(self):
        """Верх шкалы - наибольшее количество часов в круге, не меньше
        часа, с округлением вверх."""
        return max(1.0, math.ceil(float(np.nanmax(self.hours))))

    def at(self, lats, lons, radius):
        """Часы в точках и признак «внутри круга»."""
        n = self.hours.shape[0]
        row = np.rint((np.asarray(lats) - self.lat) / self.dlat
                      + (n - 1) / 2.0).astype(np.int64)
        col = np.rint((np.asarray(lons) - self.lon) / self.dlon
                      + (n - 1) / 2.0).astype(np.int64)
        dist, _ = distance_bearing(self.lat, self.lon, lats, lons, radius)
        inside = (dist <= self.radius_m) & (row >= 0) & (row < n) \
            & (col >= 0) & (col < n)
        values = self.hours[np.clip(row, 0, n - 1), np.clip(col, 0, n - 1)]
        return np.where(inside, values, np.nan), inside

    def share_at(self, value):
        """Доля шкалы 0-1 для количества часов."""
        return np.clip(np.asarray(value) / self.top, 0.0, 1.0)


def grid_points(lat, lon, radius_m, radius=None):
    """Широты и долготы всех узлов сетки высот, массивы (GRID, GRID)."""
    radius = radius or ellipsoid.A
    cell, _, _ = layout(radius_m)
    lats, lons = grid_axes(lat, lon, cell, GRID, radius)
    return np.meshgrid(lats, lons, indexing="ij")


def parts(lat, lon, radius_m, heights, start, end, radius=None):
    """Расчёт инсоляции по частям. Генератор: после каждой части в 1-2
    мс отдаёт долю сделанного 0-1, результат Insolation - значение
    StopIteration. Так окно глобуса считает в главном потоке, не дольше
    нескольких миллисекунд за проход цикла событий. Рабочий поток
    отнимал у главного GIL, и вид переставал отвечать мыши.

    Величины - как у compute."""
    radius = radius or ellipsoid.A
    cell, margin, inner = layout(radius_m)
    if callable(heights):
        grid_lat, grid_lon = grid_points(lat, lon, radius_m, radius)
        heights = heights(grid_lat.ravel(), grid_lon.ravel())
    h = np.asarray(heights, dtype=np.float64).reshape(GRID, GRID)
    times, weight = sample_times(start, end)
    total = sum(len(p) for p in shifts(cell, margin)) + len(times)
    done = 0
    hor = np.empty((AZIMUTHS, inner, inner), dtype=np.float32)
    for _ in horizon_parts(h, cell, margin, radius, hor):
        done += 1
        yield done / total
    part = h[margin - 1:margin + inner + 1, margin - 1:margin + inner + 1]
    d_north, d_east = np.gradient(part, cell)
    d_north = d_north[1:-1, 1:-1]
    d_east = d_east[1:-1, 1:-1]
    norm = np.sqrt(d_east ** 2 + d_north ** 2 + 1.0)
    nx, ny, nz = -d_east / norm, -d_north / norm, 1.0 / norm
    yield done / total
    hours = np.zeros((inner, inner), dtype=np.float64)
    per_day = int(DAY / STEP)
    for first in range(0, len(times), per_day):
        sun = sun_enu(lat, lon, times[first:first + per_day])
        done += len(sun)
        for e, n, u in sun[sun[:, 2] > 0.0]:
            level = math.hypot(e, n)
            tan_el = u / level if level > 0.0 else np.inf
            k = int(round(math.atan2(e, n) / (2.0 * math.pi)
                          * AZIMUTHS)) % AZIMUTHS
            lit = (hor[k] < tan_el) & (nx * e + ny * n + nz * u > 0.0)
            hours += lit * weight
            yield done / total
    days = int(round((end - start) / DAY)) + 1
    return Insolation(lat, lon, radius_m, cell, hours, days, radius)


def compute(lat, lon, radius_m, heights, start, end, radius=None):
    """Инсоляция в круге radius_m метров вокруг точки за сутки UTC
    от start до end включительно (начала суток, секунды UTC).
    heights - функция настоящих высот массивов широт и долгот или
    готовые высоты узлов grid_points."""
    work = parts(lat, lon, radius_m, heights, start, end, radius)
    while True:
        try:
            next(work)
        except StopIteration as stop:
            return stop.value


def tile_rgba(result, lats, lons, radius):
    """Картинка тайла: часы цветами STOPS, вне круга прозрачно. RGBA
    uint8 с премноженной альфой."""
    values, inside = result.at(lats, lons, radius)
    share = result.share_at(np.where(inside, values, 0.0))
    bounds = np.array([s[0] for s in STOPS])
    colors = np.array([s[1] for s in STOPS], dtype=np.float64)
    rgb = np.stack([np.interp(share, bounds, colors[:, c])
                    for c in range(3)], axis=-1)
    out = np.zeros(np.shape(lats) + (4,), dtype=np.uint8)
    out[inside, :3] = np.rint(rgb[inside] * OPACITY)
    out[inside, 3] = round(OPACITY * 255)
    return out
