# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горизонтали рельефа по тайлу высот и изолинии растра. Расчёт без Qt.

Просьба автора от 9 октября 2026 года - «подумаем об изолиниях»,
выбор того же дня - горизонтали рельефа глобуса и изолинии на гридах
под землёй.

Горизонтали рисуются в картинке тайла, как уклон (core/slope.py), по
высотам тайла Terrarium. Сечение рельефа - шаг из ряда 1, 2, 2.5, 5
× 10ⁿ метров, чтобы горизонтали стояли не реже STEP_PIXELS пикселей
тайла на склоне в 45°, как на топографической карте масштаба тайла:
у уровня 15 средних широт - 5 м, у уровня 13 - 20 м. Шаг считается
по уровню тайла и широте его середины, у соседних тайлов он один.
Каждая INDEX-я горизонталь утолщённая.

Линия сглажена: расстояние от пикселя до горизонтали в пикселях -
доля сечения, делённая на градиент высоты (|h/шаг - round| · шаг /
(|∇h| · пиксель)). Так толщина одинакова на пологом и крутом склоне.
Где горизонтали чаще FADE пикселей, они бледнеют, иначе крутой склон
залился бы цветом линий. Ниже нуля - изобаты своего цвета.

Изолинии грида под землёй - ломаные по клеткам сетки узлов методом
квадратов (marching squares), отрезки по ячейкам с разными знаками
h - уровень на рёбрах.

Цвета, толщины и пороги - выбор помощника, утверждает автор.
"""
import math

import numpy as np

SIZE = 256
NICE = (1.0, 2.0, 2.5, 5.0)
STEP_PIXELS = 2.0  # пикселей тайла на шаг сечения при уклоне 45°
MIN_STEP = 2.0  # м, мельче сечение высоты Terrarium не держат
INDEX = 5  # каждая пятая горизонталь утолщённая
WIDTH = 0.45  # полутолщина линии, пиксели
INDEX_WIDTH = 0.9
FADE = 4.0  # пикселей между горизонталями, чаще - линии бледнее
# Тайлы глубже уровня высот (до LEVEL) считаются по высотам предка,
# пересчитанным билинейно, иначе линии предка растягивались бы на
# экране вчетверо и вшестнадцатеро.
LEVEL = 17
LAND = (150, 85, 30)  # коричневый топографических карт
WATER = (40, 95, 175)  # изобаты
OPACITY = 0.85


def nice(value):
    """Ближайшее в логарифмах число ряда 1, 2, 2.5, 5 × 10ⁿ."""
    if value <= 0.0:
        return NICE[0]
    power = 10.0 ** math.floor(math.log10(value))
    candidates = [n * power for n in NICE] + [10.0 * power]
    return min(candidates, key=lambda c: abs(math.log(c / value)))


def tile_step(z, y, radius):
    """Сечение рельефа тайла (z, y), метры: по шагу пикселя на широте
    середины тайла."""
    n = 1 << z
    t = (y + 0.5) / n
    lat = math.atan(math.sinh(math.pi * (1.0 - 2.0 * t)))
    pixel = 2.0 * math.pi * radius * math.cos(lat) / (SIZE * n)
    return max(nice(pixel * STEP_PIXELS), MIN_STEP)


def contour_rgba(heights, z, y, radius, step=None):
    """Картинка горизонталей тайла: RGBA uint8 с премноженной альфой."""
    h = smooth(np.asarray(heights, dtype=np.float64))
    step = step or tile_step(z, y, radius)
    d_row, d_col = np.gradient(h)
    # Градиент в метрах высоты на пиксель.
    grad = np.hypot(d_row, d_col)
    level = h / step
    near = np.rint(level)
    gap = np.abs(level - near) * step / np.maximum(grad, 1e-6)
    index = (np.mod(near, INDEX) == 0)
    width = np.where(index, INDEX_WIDTH, WIDTH)
    alpha = np.clip(width + 0.5 - gap, 0.0, 1.0)
    # Расстояние между соседними горизонталями в пикселях.
    spacing = step / np.maximum(grad, 1e-6)
    alpha *= np.clip(spacing / FADE, 0.0, 1.0)
    alpha = (alpha * OPACITY).astype(np.float32)
    rgb = np.where((h < 0.0)[..., None], np.array(WATER, np.float32),
                   np.array(LAND, np.float32))
    rgb = np.where(index[..., None], rgb * 0.75, rgb)
    out = np.empty(h.shape + (4,), dtype=np.uint8)
    out[..., :3] = np.rint(rgb * alpha[..., None])
    out[..., 3] = np.rint(alpha * 255.0)
    return out


def smooth(h):
    """Высоты, сглаженные окном [1, 2, 1] / 4 по строкам и столбцам:
    без него ступеньки целых метров Terrarium давали бусы на линиях."""
    p = np.pad(h, 1, mode="edge")
    rows = (p[:-2] + 2.0 * p[1:-1] + p[2:]) / 4.0
    return (rows[:, :-2] + 2.0 * rows[:, 1:-1] + rows[:, 2:]) / 4.0


def levels(values, step):
    """Отметки изолиний через step в пределах значений, без NaN."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite) or step <= 0.0:
        return np.zeros(0)
    lo = math.ceil(finite.min() / step) * step
    hi = math.floor(finite.max() / step) * step
    if hi < lo:
        return np.zeros(0)
    return np.arange(lo, hi + step * 0.5, step)


def grid_step(values, lines=12.0):
    """Шаг изолиний грида: около lines линий на размах значений."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return 0.0
    span = float(finite.max() - finite.min())
    return nice(span / lines) if span > 0.0 else 0.0


def segments(z, level):
    """Отрезки изолинии level по сетке z (rows, cols), NaN - пусто.
    Возвращает массив (n, 2, 2) точек в долях индексов узлов (строка,
    столбец). Ячейка с пустым углом пропускается."""
    z = np.asarray(z, dtype=np.float64)
    a, b = z[:-1, :-1], z[:-1, 1:]
    c, d = z[1:, :-1], z[1:, 1:]
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c) & np.isfinite(d)
    rows, cols = np.nonzero(ok)
    if not len(rows):
        return np.zeros((0, 2, 2))
    va, vb = a[rows, cols], b[rows, cols]
    vc, vd = c[rows, cols], d[rows, cols]
    # Рёбра ячейки: верх a-b, право b-d, низ c-d, лево a-c.
    edges = ((va, vb, 0.0, 0.0, 0.0, 1.0), (vb, vd, 0.0, 1.0, 1.0, 1.0),
             (vc, vd, 1.0, 0.0, 1.0, 1.0), (va, vc, 0.0, 0.0, 1.0, 0.0))
    points = []
    hits = []
    for v0, v1, r0, c0, r1, c1 in edges:
        # Узел ровно на уровне считается выше: линия не пропадает.
        cross = (v0 >= level) != (v1 >= level)
        t = np.where(cross, (level - v0) / np.where(v1 != v0, v1 - v0, 1.0),
                     0.0)
        pr = rows + r0 + (r1 - r0) * t
        pc = cols + c0 + (c1 - c0) * t
        points.append(np.stack([pr, pc], axis=-1))
        hits.append(cross)
    points = np.stack(points, axis=1)  # (n, 4, 2)
    hits = np.stack(hits, axis=1)  # (n, 4)
    count = hits.sum(axis=1)
    out = []
    two = count == 2
    if two.any():
        idx = np.argsort(~hits[two], axis=1, kind="stable")[:, :2]
        p = points[two]
        out.append(np.stack([p[np.arange(len(p)), idx[:, 0]],
                             p[np.arange(len(p)), idx[:, 1]]], axis=1))
    four = count == 4
    if four.any():
        # Седло: две пары рёбер, по среднему значению ячейки.
        p = points[four]
        mid = (va + vb + vc + vd)[four] / 4.0
        high = (mid > level) == (va[four] > level)
        first = np.where(high[:, None, None], p[:, [0, 1]], p[:, [0, 3]])
        second = np.where(high[:, None, None], p[:, [2, 3]], p[:, [1, 2]])
        out += [first, second]
    return np.concatenate(out) if out else np.zeros((0, 2, 2))
