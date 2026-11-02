# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Похожие области: образец обводится на глобусе, модуль находит объекты
участка, похожие на него по цвету и текстуре.

Просьба автора от 1 ноября 2026 года. Объекты участка - те же, что
у классификации (core/segments.py). Образец - объекты, занимающие контур:
контур обводится неточно, а клетки соседнего леса в контуре вокруг пруда
уводили бы и средний цвет, и разброс. Контур через границу двух объектов
даёт два образца. Признаки объектов приводятся к среднему 0, доля цвета
в сумме разбросов - 1 - weight, доля текстуры (разброса внутри объекта) -
weight.
Среднее и разброс считаются с весом площади: мелкие объекты города
не решают масштаб признаков всего участка.

Похожесть - exp(-d²), d - расстояние до ближайшего образца. Сумма
разбросов признаков - 1, поэтому у двух случайных объектов участка d²
около 2 и похожесть около 14 %, у совпавших - 100 %. Порог ползунка
сравнивается с готовой похожестью и расчёта заново не требует.
"""
import numpy as np

try:  # внутри плагина QGIS
    from . import segments
except ImportError:  # headless-тесты
    import segments

LIMIT = 70  # %, порог похожести по умолчанию
SAMPLE_SHARE = 0.25  # доля контура, с которой объект входит в образец


def sample_rows(table, parts, mask):
    """Признаки образца: float32 (объекты образца, признаки) - строки
    table объектов, занимающих не меньше SAMPLE_SHARE клеток контура mask,
    иначе объекта с наибольшей долей. Пусто - в контуре нет объектов."""
    inside = parts[mask]
    inside = inside[inside >= 0]
    if not len(inside):
        return np.zeros((0, table.shape[0]), dtype=np.float32)
    counts = np.bincount(inside)
    keep = np.nonzero(counts >= SAMPLE_SHARE * len(inside))[0]
    if not len(keep):
        keep = np.array([counts.argmax()])
    return table[:, 0, keep].T

def scores(table, sizes, samples, weight=segments.WEIGHT, bands=None):
    """Похожесть объектов от 0 до 1. table - segments.table, за ней могут
    идти строки segments.pattern, sizes - клеток в объектах, samples -
    признаки образцов (образцы, признаки), weight - доля текстуры, bands -
    каналов (строк цвета), без него - половина строк. Текстура - разброс
    каналов внутри объекта и рисунок. None - признаки на участке
    не меняются."""
    rows = table[:, 0].astype(np.float64)
    if bands is None:
        bands = rows.shape[0] // 2
    share = np.asarray(sizes, dtype=np.float64)
    share = share / share.sum()
    mean = rows @ share
    spread = np.sqrt(((rows - mean[:, None]) ** 2) @ share)
    colour = np.nonzero(spread[:bands] > 0.0)[0]
    rough = np.nonzero(spread[bands:] > 0.0)[0] + bands
    if not len(colour) and not len(rough):
        return None
    if not len(rough):
        weight = 0.0
    elif not len(colour):
        weight = 1.0
    factor = np.zeros(rows.shape[0], dtype=np.float64)
    if len(colour):
        factor[colour] = np.sqrt((1.0 - weight) / len(colour)) \
            / spread[colour]
    if len(rough):
        factor[rough] = np.sqrt(weight / len(rough)) / spread[rough]
    objects = (rows - mean[:, None]) * factor[:, None]
    best = None
    for sample in np.asarray(samples, dtype=np.float64):
        point = (sample - mean) * factor
        far = ((objects - point[:, None]) ** 2).sum(axis=0)
        best = far if best is None else np.minimum(best, far)
    return np.exp(-best)


def pick(parts, score, limit, join=True):
    """Найденные объекты: (номера клеток с 0, -1 вне найденного,
    похожесть каждого в долях). limit - порог в долях, join - соседние
    найденные объекты сливаются, похожесть слитого - среднее по площади."""
    kept = score >= limit
    has = parts >= 0
    has[has] = kept[parts[has]]
    labels = parts
    if join:
        labels = segments.dissolve(parts, np.where(kept, 0, -1))[0]
    roots, numbers = np.unique(labels[has], return_inverse=True)
    out = np.full(parts.shape, -1, dtype=np.int32)
    out[has] = numbers
    size = np.bincount(numbers, minlength=len(roots))
    mean = np.bincount(numbers, score[parts[has]], len(roots)) \
        / np.maximum(size, 1)
    return out, mean
