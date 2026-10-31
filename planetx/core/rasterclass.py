# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Классификация участка по своему растру: каналы растра - признаки
клетки.

Просьба Василия Швалёва от 31 октября 2026 года. Контрольные точки те
же, что у классификации по эмбеддингам AlphaEarth (core/aef.py), мера
другая. Векторы AlphaEarth - единичные, у них работает косинус. Каналы
своего растра бывают в разных единицах: косинус на одном канале равен 1
у всех клеток, а при высоте в метрах и отражении в долях единицы он
определяется одной высотой. Поэтому каждый канал приводится к среднему
0 и разбросу 1 по клеткам участка, близость - евклидово расстояние,
голос точки - обратное расстояние, сумма голосов класса делится на
количество его точек. Канал без разброса на участке признаком
не считается.

Модуль только на NumPy: чтение растра - в ui/aefclass.py, ядро
переносится в PlanetX Lite без изменений.
"""
import math

import numpy as np

KNN = 5  # контрольных точек голосуют за клетку, как у AlphaEarth
CHUNK = 128 * 1024  # клеток за шаг расчёта
AUTO_CELLS = 800 * 800  # клеток участка при пикселе «Авто»
NEAR = 1e-3  # добавка к расстоянию: точка на самой клетке даёт конечный голос
MAX_BYTES = 1 << 30  # байт сетки float32 в памяти


def auto_pixel(native, side, most=AUTO_CELLS):
    """Пиксель «Авто», м: пиксель растра native, если на участке со
    стороной side метров клеток не больше most, иначе крупнее."""
    return max(float(native), float(side) / math.sqrt(most))


def too_big(rows, cols, bands):
    """Сетка участка float32 не поместится в MAX_BYTES."""
    return 4 * int(rows) * int(cols) * int(bands) > MAX_BYTES


def usable(grid):
    """Клетки сетки (каналы, строки, столбцы), где есть все каналы."""
    return np.isfinite(grid).all(axis=0)


def covered(grid, inside):
    """Доля клеток участка inside, где есть все каналы растра."""
    total = int(inside.sum())
    return float((usable(grid) & inside).sum()) / total if total else 0.0


def scales(grid, inside=None):
    """Среднее и разброс каналов (каналы,) по клеткам участка со всеми
    каналами. Канал без разброса - разброс 0, признаком он не будет."""
    good = usable(grid)
    if inside is not None:
        good = good & inside
    bands = grid.shape[0]
    mean, spread = np.zeros(bands), np.zeros(bands)
    if not good.any():
        return mean, spread
    for band in range(bands):
        values = grid[band][good].astype(np.float64)
        mean[band] = values.mean()
        spread[band] = values.std()
    # Разброс из шума округления float32 - не разброс.
    spread[spread <= 1e-6 * np.maximum(np.abs(mean), 1e-30)] = 0.0
    return mean, spread


def classify(grid, samples, labels, inside=None, k=KNN, progress=None):
    """Классы клеток растра: grid - float32 (каналы, строки, столбцы),
    NaN без данных, samples - значения точек (каналы, точек), labels -
    номера классов точек, inside - клетки участка. Точка без данных
    не голосует. Итог - (классы int16, -1 без данных и вне участка,
    расстояние до лучшей точки float32). progress(готово, всего) зовётся
    перед каждой частью."""
    shape = grid.shape[1:]
    out = np.full(shape[0] * shape[1], -1, dtype=np.int16)
    distance = np.full(out.shape, np.nan, dtype=np.float32)
    done = out.reshape(shape), distance.reshape(shape)
    samples = np.asarray(samples, dtype=np.float64)
    labels = np.asarray(labels)
    good = np.isfinite(samples).all(axis=0)
    samples, labels = samples[:, good], labels[good]
    mean, spread = scales(grid, inside)
    used = spread > 0.0
    if not len(labels) or not used.any():
        return done
    train = ((samples[used].T - mean[used]) / spread[used]).astype(np.float32)
    square = (train * train).sum(axis=1)
    k = max(1, min(k, len(train)))
    classes, sizes = np.unique(labels, return_counts=True)
    cells = usable(grid)
    if inside is not None:
        cells = cells & inside
    cells = np.nonzero(cells.ravel())[0]
    flat = grid.reshape(grid.shape[0], -1)[used]
    for start in range(0, len(cells), CHUNK):
        if progress is not None:
            progress(start, len(cells))
        part = cells[start:start + CHUNK]
        values = ((flat[:, part].T - mean[used]) / spread[used]).astype(
            np.float32)
        # Квадрат расстояния через скалярное произведение: матрица
        # клетки × точки без оси каналов, каналов бывает больше 64.
        near2 = (values * values).sum(axis=1, keepdims=True) \
            - 2.0 * values @ train.T + square
        near = np.sqrt(np.maximum(near2, 0.0))
        order = np.argsort(near, axis=1)[:, :k]
        weight = 1.0 / (np.take_along_axis(near, order, axis=1) + NEAR)
        votes = np.zeros((len(part), len(classes)), dtype=np.float32)
        for n, cls in enumerate(classes):
            # Голос на точку класса: класс с лишними точками не перетягивает
            # клетки, когда голосуют почти все точки.
            votes[:, n] = np.where(labels[order] == cls, weight, 0.0).sum(
                axis=1) / sizes[n]
        out[part] = classes[np.argmax(votes, axis=1)]
        distance[part] = near.min(axis=1)
    return done
