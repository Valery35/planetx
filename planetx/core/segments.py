# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сегментация снимка: участок делится на объекты, похожие по цвету
и текстуре, классы получают объекты, а не клетки.

Просьба автора от 1 ноября 2026 года. Способ - слияние областей, как
многомасштабная сегментация Baatz и Schäpe 2000 года. Сначала каждая
клетка - своя область. Цена слияния соседей - прирост разнородности
n1 n2 / (n1 + n2) · |m1 - m2|² (мера Уорда) плюс прирост неровности
формы. За проход сливаются пары, где каждая область - лучший сосед
другой, пока цена не больше порога, порог растёт ступенями до квадрата
масштаба. Области соседние, поэтому объект всегда связный.
Каждый проход - операции над массивами рёбер, библиотек кроме NumPy
не нужно, ядро переносится в PlanetX Lite без изменений.

Каналы приводятся к разбросу 1 (core/rasterclass.py) и делятся на корень
из их количества: масштаб не зависит от количества каналов. Текстура -
местный разброс яркости в окне клетки, ещё один признак с долей weight.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import rasterclass
except ImportError:  # headless-тесты
    import rasterclass

SCALE = 15  # масштаб объектов по умолчанию
WEIGHT = 0.3  # доля текстуры среди признаков
LEAST = 16  # клеток в наименьшем объекте
RADIUS = 2  # окно текстуры 5 × 5 клеток
SHAPE = 0.2  # вес неровности формы в цене слияния
STAGES = 4  # ступеней роста порога, каждая вчетверо ниже следующей
MAX_CELLS = 2000 * 2000  # клеток участка: рёбер вдвое больше, память


def too_big(rows, cols):
    """Сетка слишком велика для сегментации."""
    return int(rows) * int(cols) > MAX_CELLS


def _box_sum(values, radius):
    """Сумма по окну (2 radius + 1)² с обрезкой у краёв сетки."""
    rows, cols = values.shape
    total = np.zeros((rows + 1, cols + 1), dtype=np.float64)
    total[1:, 1:] = values.cumsum(axis=0).cumsum(axis=1)
    top = np.clip(np.arange(rows) - radius, 0, rows)
    bottom = np.clip(np.arange(rows) + radius + 1, 0, rows)
    left = np.clip(np.arange(cols) - radius, 0, cols)
    right = np.clip(np.arange(cols) + radius + 1, 0, cols)
    return total[bottom][:, right] - total[top][:, right] \
        - total[bottom][:, left] + total[top][:, left]


def texture(bright, good, radius=RADIUS):
    """Местный разброс яркости bright по клеткам good в окне клетки."""
    value = np.where(good, bright, 0.0).astype(np.float64)
    count = np.maximum(_box_sum(good.astype(np.float64), radius), 1.0)
    first = _box_sum(value, radius) / count
    second = _box_sum(value * value, radius) / count
    return np.sqrt(np.maximum(second - first * first, 0.0))


def features(grid, good, weight=WEIGHT, radius=RADIUS):
    """Признаки клеток good: float32 (признаки, клетки). Сумма разбросов
    цветовых признаков - 1 - weight, текстуры - weight."""
    mean, spread = rasterclass.scales(grid, good)
    used = np.nonzero(spread > 0.0)[0]
    if not len(used):
        return None
    rows = []
    bright = np.zeros(good.shape, dtype=np.float64)
    for band in used:
        value = (grid[band].astype(np.float64) - mean[band]) / spread[band]
        value = np.where(good, value, 0.0)
        bright += value
        rows.append(value[good].astype(np.float32))
    colour = math.sqrt((1.0 - weight) / len(used))
    out = [row * colour for row in rows]
    if weight > 0.0:
        rough = texture(bright / len(used), good, radius)[good]
        spread = rough.std()
        if spread > 0.0:
            out.append(((rough - rough.mean()) / spread * math.sqrt(weight)
                        ).astype(np.float32))
    return np.stack(out)


def _edges(cells):
    """Рёбра соседних клеток: cells - номера клеток, -1 вне участка."""
    a = np.concatenate((cells[:, :-1].ravel(), cells[:-1, :].ravel()))
    b = np.concatenate((cells[:, 1:].ravel(), cells[1:, :].ravel()))
    keep = (a >= 0) & (b >= 0)
    return a[keep].astype(np.int64), b[keep].astype(np.int64)


def _costs(total, size, edge, shared, a, b, shape):
    """Цена слияния областей рёбер: прирост разнородности плюс shape ×
    прирост неровности формы sqrt(n) · периметр. shared - длина общей
    границы, edge - периметр областей."""
    na, nb = size[a], size[b]
    diff = total[:, a] / na - total[:, b] / nb
    cost = (diff * diff).sum(axis=0) * na * nb / (na + nb)
    if shape > 0.0:
        whole = np.sqrt(na + nb) * (edge[a] + edge[b] - 2.0 * shared)
        cost = cost + shape * (whole - np.sqrt(na) * edge[a]
                               - np.sqrt(nb) * edge[b])
    return cost


def _pairs(a, b, cost, regions):
    """Номера рёбер, где обе области - лучшие соседи друг друга. Ранг
    вместо цены: при равных ценах каждая область входит в одну пару."""
    order = np.argsort(cost, kind="stable")
    rank = np.empty(len(order), dtype=np.int64)
    rank[order] = np.arange(len(order))
    best = np.full(regions, len(order), dtype=np.int64)
    # При повторе индекса действует последнее присваивание: от большего
    # ранга к меньшему остаётся наименьший.
    down = order[::-1]
    best[a[down]] = rank[down]
    keep = rank < best[b]
    best[b[down[keep[down]]]] = rank[down[keep[down]]]
    return np.nonzero((best[a] == rank) & (best[b] == rank))[0]


def _merge(total, size, edge, parent, a, b, shared, limit, shape,
           small=None, progress=None):
    """Слияния до цены limit. small - наименьшая площадь: сливаются только
    области меньше неё, цена не ограничена. Меняет total, size, edge,
    parent, возвращает оставшиеся рёбра и длины их границ."""
    while len(a):
        if progress is not None:
            progress(len(a))
        if small is None:
            near = np.arange(len(a))
        else:
            near = np.nonzero((size[a] < small) | (size[b] < small))[0]
            if not len(near):
                break
        ea, eb, length = a[near], b[near], shared[near]
        cost = _costs(total, size, edge, length, ea, eb, shape)
        if small is None:
            ok = cost <= limit
            if not ok.any():
                break
            ea, eb, length, cost = ea[ok], eb[ok], length[ok], cost[ok]
        chosen = _pairs(ea, eb, cost, len(parent))
        keep, drop = ea[chosen], eb[chosen]
        total[:, keep] += total[:, drop]
        size[keep] += size[drop]
        edge[keep] += edge[drop] - 2.0 * length[chosen]
        parent[drop] = keep
        a, b = parent[a], parent[b]
        different = a != b
        low = np.minimum(a[different], b[different])
        high = np.maximum(a[different], b[different])
        keys, group = np.unique(low * len(parent) + high,
                                return_inverse=True)
        shared = np.bincount(group, shared[different])
        a, b = keys // len(parent), keys % len(parent)
    return a, b, shared


def segment(grid, inside=None, scale=SCALE, weight=WEIGHT, least=LEAST,
            shape=SHAPE, progress=None):
    """Объекты сетки grid (каналы, строки, столбцы), NaN без данных,
    inside - клетки участка. Итог - int32 номера объектов с 0, -1 без
    объекта. progress(рёбер) зовётся перед каждым проходом."""
    good = rasterclass.usable(grid)
    if inside is not None:
        good = good & inside
    labels = np.full(good.shape, -1, dtype=np.int32)
    count = int(good.sum())
    if not count:
        return labels
    data = features(grid, good, weight)
    if data is None:  # каналы не меняются - один объект на связную часть
        data = np.zeros((1, count), dtype=np.float32)
    cells = np.full(good.shape, -1, dtype=np.int64)
    cells[good] = np.arange(count)
    a, b = _edges(cells)
    total = data.astype(np.float64)
    size = np.ones(count, dtype=np.float64)
    parent = np.arange(count, dtype=np.int64)
    shared = np.ones(len(a), dtype=np.float64)
    # Периметр клетки - только к соседям на участке: край участка
    # не делает область неровной.
    edge = (np.bincount(a, minlength=count)
            + np.bincount(b, minlength=count)).astype(np.float64)
    target = float(scale) ** 2
    limit = target / 4.0 ** STAGES
    # Порог растёт ступенями: области растут вровень, а не одна за счёт
    # соседей.
    for _ in range(STAGES + 1):
        a, b, shared = _merge(total, size, edge, parent, a, b, shared, limit,
                              shape, progress=progress)
        limit *= 4.0
    # Форма держала границы ровными, но не пускала большие однородные
    # области срастись: река выходила сотами. Последний проход - по цвету.
    a, b, shared = _merge(total, size, edge, parent, a, b, shared, target,
                          0.0, progress=progress)
    if least > 1:
        _merge(total, size, edge, parent, a, b, shared, None, shape,
               small=float(least), progress=progress)
    while True:
        up = parent[parent]
        if (up == parent).all():
            break
        parent = up
    _, numbers = np.unique(parent, return_inverse=True)
    labels[good] = numbers.astype(np.int32)
    return labels


def table(grid, labels):
    """Признаки объектов для классов: float32 (каналы × 2, 1, объекты) -
    среднее и разброс каналов внутри объекта. Форма сетки rasterclass:
    объект - клетка строки 1. Каналы с NaN у объекта быть не может."""
    count = int(labels.max()) + 1
    has = labels >= 0
    numbers = labels[has]
    size = np.bincount(numbers, minlength=count).astype(np.float64)
    bands = grid.shape[0]
    out = np.zeros((2 * bands, 1, count), dtype=np.float32)
    for band in range(bands):
        value = grid[band][has].astype(np.float64)
        first = np.bincount(numbers, value, count) / size
        second = np.bincount(numbers, value * value, count) / size
        out[band, 0] = first
        out[band + bands, 0] = np.sqrt(np.maximum(second - first * first,
                                                  0.0))
    return out


def areas(labels):
    """Клеток в объектах."""
    has = labels >= 0
    if not has.any():
        return np.zeros(0, dtype=np.int64)
    return np.bincount(labels[has])


def borders(labels):
    """Клетки на границе объектов: сосед справа или снизу из другого
    объекта."""
    edge = np.zeros(labels.shape, dtype=bool)
    edge[:, :-1] |= labels[:, :-1] != labels[:, 1:]
    edge[:-1, :] |= labels[:-1, :] != labels[1:, :]
    return edge & (labels >= 0)
