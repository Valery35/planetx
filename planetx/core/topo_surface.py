# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/topo_surface.py.
# Там - GPL-2.0-or-later, владелец тот же.
"""Морфометрия поверхности на чистом NumPy: уклон и экспозиция по
Horn (1981, ядро 3x3, как в gdaldem), вершины как локальные максимумы
с фильтрами по превышению и радиусу."""

import numpy as np


def _edge_pad(z):
    return np.pad(z, 1, mode="edge")


def slope_aspect(z, cell, nodata_mask=None):
    """Уклон (градусы) и экспозиция (градусы от севера по часовой).

    Horn 3x3. Экспозиция плоских ячеек (нулевой градиент) равна -1.
    Ячейки nodata и их соседи получают NaN в обоих выходах: ядро 3x3
    через дыры не считаем.
    """
    z = np.asarray(z, dtype=np.float64)
    if nodata_mask is None:
        nodata_mask = ~np.isfinite(z)
    zf = np.where(nodata_mask, np.nan, z)
    p = _edge_pad(zf)
    nw, n_, ne = p[:-2, :-2], p[:-2, 1:-1], p[:-2, 2:]
    w_, e_ = p[1:-1, :-2], p[1:-1, 2:]
    sw, s_, se = p[2:, :-2], p[2:, 1:-1], p[2:, 2:]

    dzdx = ((ne + 2.0 * e_ + se) - (nw + 2.0 * w_ + sw)) / (8.0 * cell)
    # строка 0 северная: положительный dzdy - рост на север
    dzdy = ((nw + 2.0 * n_ + ne) - (sw + 2.0 * s_ + se)) / (8.0 * cell)

    slope = np.degrees(np.arctan(np.hypot(dzdx, dzdy)))
    # экспозиция - азимут спуска: вектор (-dzdx, -dzdy) в осях (восток, север)
    aspect = np.degrees(np.arctan2(-dzdx, -dzdy))
    aspect = np.where(aspect < 0.0, aspect + 360.0, aspect)
    flat = (dzdx == 0.0) & (dzdy == 0.0)
    aspect = np.where(flat, -1.0, aspect)
    bad = ~np.isfinite(slope) | nodata_mask
    slope[bad] = np.nan
    aspect[bad] = np.nan
    return slope, aspect


def _window_max(z, r):
    """Максимум по квадратному окну (2r+1): раздельно по осям."""
    m = z.copy()
    for k in range(1, r + 1):
        sh = np.full_like(z, -np.inf)
        sh[:, k:] = z[:, :-k]
        m = np.maximum(m, sh)
        sh = np.full_like(z, -np.inf)
        sh[:, :-k] = z[:, k:]
        m = np.maximum(m, sh)
    z2 = m
    m = z2.copy()
    for k in range(1, r + 1):
        sh = np.full_like(z2, -np.inf)
        sh[k:, :] = z2[:-k, :]
        m = np.maximum(m, sh)
        sh = np.full_like(z2, -np.inf)
        sh[:-k, :] = z2[k:, :]
        m = np.maximum(m, sh)
    return m


def _window_min(z, r):
    return -_window_max(-z, r)


def find_peaks(z, cell, radius_m, min_drop, nodata_mask=None):
    """Вершины: локальные максимумы в радиусе с фильтром превышения.

    Ячейка объявляется вершиной, если она строго выше всех остальных
    ячеек квадратного окна радиуса radius_m и превышает минимум окна
    не меньше чем на min_drop. Возвращает список
    (row, col, z, drop), отсортированный по убыванию высоты.
    """
    z = np.asarray(z, dtype=np.float64)
    if nodata_mask is None:
        nodata_mask = ~np.isfinite(z)
    r = max(1, int(round(float(radius_m) / float(cell))))
    zf = np.where(nodata_mask, -np.inf, z)

    wmax = _window_max(zf, r)
    zmin = np.where(nodata_mask, np.inf, z)
    wmin = _window_min(zmin, r)

    is_peak = (zf >= wmax) & ~nodata_mask
    # строгость: победитель в окне один, дубли плато отбрасываем,
    # оставляя северо-западную ячейку плато
    drop = zf - np.where(np.isfinite(wmin), wmin, zf)
    is_peak &= drop >= float(min_drop)

    rows, cols = np.nonzero(is_peak)
    out = []
    order = np.argsort(-z[rows, cols])
    for i in order:
        rr, cc = int(rows[i]), int(cols[i])
        clash = False
        for pr, pc, _pz, _pd in out:
            if abs(pr - rr) <= r and abs(pc - cc) <= r:
                clash = True
                break
        if clash:
            continue
        out.append((rr, cc, float(z[rr, cc]), float(drop[rr, cc])))
    return out


def find_extremes(z, cell, radius_m, min_drop, nodata_mask=None):
    """Вершины и ямы разом: (row, col, z, drop, kind), kind это peak или pit.

    Яма ищется тем же find_peaks на обращённом рельефе - локальный минимум
    это локальный максимум минус-поверхности, а превышение над минимумом
    окна становится глубиной под максимумом. Отметка z и величина drop
    возвращаются в исходных знаках: у ямы z это её настоящая отметка, а
    drop положительная глубина.

    Обе половины нужны одновременно: поверхность, построенная по одним
    горизонталям, кладёт плоскую шапку на каждую замкнутую горизонталь, и
    ошибка объёма на вершине и в яме одна и та же с разным знаком.
    Пикеты экстремумов её закрывают.
    """
    z = np.asarray(z, dtype=np.float64)
    peaks = [(r, c, zv, dv, "peak")
             for r, c, zv, dv in find_peaks(z, cell, radius_m, min_drop,
                                            nodata_mask=nodata_mask)]
    pits = [(r, c, float(z[r, c]), dv, "pit")
            for r, c, _zv, dv in find_peaks(-z, cell, radius_m, min_drop,
                                            nodata_mask=nodata_mask)]
    out = peaks + pits
    out.sort(key=lambda t: -abs(t[3]))
    return out
