# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейные объекты участка осевыми линиями.

Вариант Д, выбор автора от 3 ноября 2026 года - дороги, просеки, реки
и лесополосы линиями, а не площадями. Порядок:
- маска вида (почва, вода, растительность) на сетке участка;
- тонкие части маски - то, что убирает морфологическое открытие
  квадратом (thin): узкая полоса уходит, поле остаётся;
- скелет тонких частей - утончение Чжана-Суэня 1984 года (skeleton);
- цепочки скелета от узла до узла (chains), связный кусок скелета
  короче наименьшей длины отбрасывается, короткие отростки - тоже;
- ломаные упрощаются Дугласом-Пекером (tracing.simplify).

Координаты цепочек - середины клеток: x - столбец, y - строка сверху.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import tracing
except ImportError:  # headless-тесты
    import tracing

WIDTH = 40.0  # м, линейный объект не шире - выбор помощника
LENGTH = 200.0  # м, связный кусок линии не короче
SPUR = 3.0  # отросток короче SPUR ширин линии отбрасывается
STEPS = ((-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1),
         (-1, -1))  # соседи P2..P9 по часовой стрелке от верхнего


def _shift(mask, dr, dc):
    """Маска, сдвинутая на (dr, dc): клетка (r, c) берёт (r + dr, c + dc),
    за краем - ложь."""
    out = np.zeros_like(mask)
    rows, cols = mask.shape
    out[max(0, -dr):rows - max(0, dr), max(0, -dc):cols - max(0, dc)] = \
        mask[max(0, dr):rows - max(0, -dr), max(0, dc):cols - max(0, -dc)]
    return out


def erode(mask, radius):
    out = mask.copy()
    for _ in range(radius):
        step = out.copy()
        for dr, dc in STEPS:
            step &= _shift(out, dr, dc)
        out = step
    return out


def dilate(mask, radius):
    out = mask.copy()
    for _ in range(radius):
        step = out.copy()
        for dr, dc in STEPS:
            step |= _shift(out, dr, dc)
        out = step
    return out


def thin(mask, cells):
    """Части маски уже примерно cells клеток: маска без её открытия
    квадратом стороны 2r + 1, r = cells / 2."""
    mask = np.asarray(mask, dtype=bool)
    radius = max(1, int(round(cells / 2.0)))
    return mask & ~dilate(erode(mask, radius), radius)


def skeleton(mask):
    """Утончение Чжана-Суэня до линии в клетку, связность 8."""
    img = np.pad(np.asarray(mask, dtype=bool), 1)
    while True:
        changed = False
        for phase in (0, 1):
            p = [_shift(img, dr, dc) for dr, dc in STEPS]
            count = sum(v.astype(np.int8) for v in p)
            turns = sum((~p[n] & p[(n + 1) % 8]).astype(np.int8)
                        for n in range(8))
            p2, p4, p6, p8 = p[0], p[2], p[4], p[6]
            if phase == 0:
                cut = ~(p2 & p4 & p6) & ~(p4 & p6 & p8)
            else:
                cut = ~(p2 & p4 & p8) & ~(p2 & p6 & p8)
            gone = img & (count >= 2) & (count <= 6) & (turns == 1) & cut
            if gone.any():
                img &= ~gone
                changed = True
        if not changed:
            return img[1:-1, 1:-1]


def _neighbours(cells, r, c):
    return [(r + dr, c + dc) for dr, dc in STEPS if (r + dr, c + dc) in cells]


def chains(skel):
    """Цепочки скелета от узла до узла: список [(строка, столбец)]. Узел -
    клетка не с двумя соседями, кольцо без узлов - одна цепочка."""
    rows, cols = np.nonzero(skel)
    cells = set(zip(rows.tolist(), cols.tolist()))
    links = {cell: _neighbours(cells, *cell) for cell in cells}
    nodes = {cell for cell, near in links.items() if len(near) != 2}
    used = set()
    out = []
    for start in sorted(nodes) + sorted(cells - nodes):
        for nxt in links[start]:
            if (start, nxt) in used:
                continue
            path = [start, nxt]
            used.add((start, nxt))
            used.add((nxt, start))
            while path[-1] not in nodes and path[-1] != start:
                here = path[-1]
                step = next((c for c in links[here]
                             if (here, c) not in used), None)
                if step is None:
                    break
                used.add((here, step))
                used.add((step, here))
                path.append(step)
            out.append(path)
        if start not in nodes:
            nodes.add(start)  # кольцо обойдено, дальше узел
    return out


def _length(path):
    return sum(math.hypot(a[0] - b[0], a[1] - b[1])
               for a, b in zip(path, path[1:]))


def lines(mask, width_cells, least_cells):
    """Осевые линии тонких частей маски: список ломаных [(x, y)] в клетках
    (x - столбец, y - строка, середины клеток). Отростки короче
    SPUR * width_cells, связные куски короче least_cells отбрасываются."""
    skel = skeleton(thin(mask, width_cells))
    if not skel.any():
        return []
    found = chains(skel)
    ends = {}
    for path in found:
        for end in (path[0], path[-1]):
            ends[end] = ends.get(end, 0) + 1
    spur = SPUR * max(width_cells, 1.0)
    kept = [p for p in found
            if not ((ends[p[0]] == 1 or ends[p[-1]] == 1)
                    and _length(p) < spur
                    and not (ends[p[0]] == 1 and ends[p[-1]] == 1))]
    groups = _groups(kept)
    out = []
    for group in groups:
        if sum(_length(kept[n]) for n in group) < least_cells:
            continue
        for n in group:
            pts = [(c + 0.5, r + 0.5) for r, c in kept[n]]
            out.append([tuple(p) for p in tracing.simplify(pts, 1.0)])
    return out


def _groups(paths):
    """Связные группы цепочек по общим концам и клеткам."""
    parent = list(range(len(paths)))

    def root(n):
        while parent[n] != n:
            parent[n] = parent[parent[n]]
            n = parent[n]
        return n

    owner = {}
    for n, path in enumerate(paths):
        for cell in (path[0], path[-1]):
            if cell in owner:
                parent[root(n)] = root(owner[cell])
            else:
                owner[cell] = n
    out = {}
    for n in range(len(paths)):
        out.setdefault(root(n), []).append(n)
    return list(out.values())


def cells_of(paths, shape):
    """Клетки сетки shape под ломаными - для показа линий на глобусе."""
    out = np.zeros(shape, dtype=bool)
    for path in paths:
        for (x0, y0), (x1, y1) in zip(path, path[1:]):
            steps = max(2, int(math.hypot(x1 - x0, y1 - y0) * 2) + 1)
            xs = np.linspace(x0, x1, steps).astype(int)
            ys = np.linspace(y0, y1, steps).astype(int)
            ok = (ys >= 0) & (ys < shape[0]) & (xs >= 0) & (xs < shape[1])
            out[ys[ok], xs[ok]] = True
    return out


def length_m(points, step):
    """Длина ломаной в метрах по шагу сетки."""
    return _length(points) * step
