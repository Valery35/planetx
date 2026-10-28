# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Анализ рельефа квадрата у точки. Расчёт без Qt.

Просьба автора от 26 октября 2026 года - уклон и экспозиция «по
аналогии» с гидрологией: на сетке квадрата core/hydro.py по истинным
высотам, а не слоем вида по тайлам. Уклон и экспозиция - ядро Horn 3×3
(topo_surface.slope_aspect, инструмент 2.08 Isoliner), вершины и ямы -
topo_surface.find_extremes (2.09). Шаг сетки на местности один по обеим
осям, поэтому ядро годится как есть.

Экспозиция ровного места (уклон меньше slope.FLAT) - NaN, как у слоя
уклона вида. Классы уклона и цвета - core/slope.py, общие со слоем.
"""
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import hydro, slope, topo_surface
except ImportError:  # headless-тесты
    import hydro
    import slope
    import topo_surface

# Вершины и ямы: радиус окна и наименьший перепад по умолчанию, метры -
# выбор помощника, утверждает автор.
PEAK_RADIUS = 300.0
PEAK_DROP = 20.0
# Стороны света экспозиции по 45° с серединой на направлении.
SIDES = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")

Relief = namedtuple("Relief", "grid slope aspect lat lon radius_m box mode")
Relief.__doc__ = """Уклон и экспозиция сетки grid (core.hydro.Grid),
градусы, экспозиция ровного - NaN. lat, lon, radius_m - точка и
полусторона квадрата, box - рамка (юг, север, запад, восток) для
тайлов слоя вида, mode - "slope" или "aspect" - что показывать."""

Summary = namedtuple("Summary", "low median high classes sides flat")
Summary.__doc__ = """Сводка уклона: наименьший, медиана, наибольший,
градусы. classes - (нижняя граница класса, площадь м²) по
slope.SLOPE_STOPS, sides - доли площади с экспозицией по SIDES,
flat - доля ровного места."""


def analyse(z, grid, radius, mode="slope"):
    """Уклон и экспозиция высот z сетки grid, radius - радиус тела."""
    z = np.asarray(z, dtype=np.float64)
    values, aspect = topo_surface.slope_aspect(z, float(grid.cell))
    aspect = np.where(values < slope.FLAT, np.nan, aspect)
    lats, lons = hydro.latlon(grid, np.array([0, grid.rows - 1]),
                              np.array([0, grid.cols - 1]), radius)
    box = (float(lats[1]), float(lats[0]), float(lons[0]), float(lons[1]))
    return Relief(grid, values, aspect, grid.lat, grid.lon,
                  (grid.rows - 1) * grid.cell / 2.0, box, mode)


def summary(relief):
    """Сводка уклона и экспозиции по узлам с данными."""
    values = relief.slope
    ok = np.isfinite(values)
    if not ok.any():
        return None
    cell2 = float(relief.grid.cell) ** 2
    good = values[ok]
    bounds = [s[0] for s in slope.SLOPE_STOPS]
    index = np.searchsorted(bounds, good, side="right") - 1
    counts = np.bincount(np.clip(index, 0, len(bounds) - 1),
                         minlength=len(bounds))
    classes = [(b, float(n) * cell2) for b, n in zip(bounds, counts)]
    aspect = relief.aspect[ok]
    has = np.isfinite(aspect)
    sector = np.floor(((aspect[has] + 22.5) % 360.0) / 45.0).astype(int)
    shares = np.bincount(sector, minlength=8) / float(good.size)
    return Summary(float(good.min()), float(np.median(good)),
                   float(good.max()), classes,
                   [float(s) for s in shares],
                   float((~has).sum()) / float(good.size))


def extremes(z, grid, radius_m=PEAK_RADIUS, drop=PEAK_DROP):
    """Вершины и ямы: (строка, столбец, отметка, перепад, "peak" или
    "pit"), по убыванию перепада."""
    z = np.asarray(z, dtype=np.float64)
    return topo_surface.find_extremes(z, float(grid.cell), radius_m, drop)


def sample(relief, lats, lons, radius):
    """Значения relief (по mode) в точках lats, lons - ближайший узел,
    вне сетки NaN."""
    grid = relief.grid
    x, y = hydro.mercator(lats, lons, radius)
    cols = np.rint((x - grid.x0) / grid.step)
    rows = np.rint((grid.y0 - y) / grid.step)
    inside = (rows >= 0) & (rows < grid.rows) & (cols >= 0) \
        & (cols < grid.cols)
    values = relief.slope if relief.mode == "slope" else relief.aspect
    out = np.full(np.shape(lats), np.nan)
    r = rows[inside].astype(int)
    c = cols[inside].astype(int)
    out[inside] = values[r, c]
    return out, inside


def tile_rgba(relief, lats, lons, radius):
    """Картинка тайла слоя вида: раскраска слоя уклона или экспозиции,
    вне сетки прозрачно (ui.viewshed.ResultTiles)."""
    values, inside = sample(relief, lats, lons, radius)
    if relief.mode == "slope":
        rgba = slope.slope_rgba(np.where(inside, values, 0.0))
        rgba[~inside | ~np.isfinite(values)] = 0
    else:
        rgba = slope.aspect_rgba(values)
        # Экспозиция ровного места - NaN, вне участка NaN и уклон.
        slopes, _ = sample(relief._replace(mode="slope"), lats, lons,
                           radius)
        rgba[~inside | ~np.isfinite(slopes)] = 0
    return rgba
