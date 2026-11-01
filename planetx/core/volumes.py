# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выемка и насыпь между двумя съёмками рельефа. Расчёт без Qt.

Просьба автора от 10 октября 2026 года - «карьеры с отвалами». Две
съёмки одного участка - растры отметок, прежняя и новая. Разность
новая минус прежняя на сетке новой съёмки - насыпь (отвалы) со знаком
плюс и выемка (карьер) со знаком минус. Объём - сумма разностей на
площадь ячейки. Разности меньше порога по модулю не считаются - это
шум съёмки. Порог по умолчанию 0.1 м - выбор помощника, утверждает
автор.

Вне многоугольника участка, если он задан, и там, где нет хотя бы
одной съёмки, разность пустая.

Земляные работы (окно ui/earthwork.py) - вторая разность: ровная
площадка на отметке level минус рельеф участка. Просьба автора от
1 ноября 2026 года. Плюс - насыпь до площадки, минус - выемка. Отметка
с равными объёмами - средняя высота участка. Открытые высоты несут
ошибку в метры, поэтому объём на такой доле участка идёт с оценкой
ошибки площадь × OPEN_ERROR.
"""
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import hydro
except ImportError:  # headless-тесты
    import hydro

THRESHOLD = 0.1  # м, разность меньше - шум съёмки
NODATA = -9999.0
OPEN_ERROR = 3.0  # м, ошибка открытых моделей высот для оценки объёма
OWN_ENOUGH = 0.99  # доля участка на своём рельефе без оговорки
ALPHA = 200  # непрозрачность раскраски на глобусе
CUT_RGB = (200, 40, 30)
FILL_RGB = (30, 90, 200)

Earthwork = namedtuple("Earthwork", "grid diff level reach lat lon radius_m "
                                    "box")
Earthwork.__doc__ = """Площадка на отметке level над сеткой grid (core.
hydro.Grid). diff - отметка минус рельеф, вне участка NaN, reach -
наибольший модуль разности для шкалы, lat, lon, radius_m - точка
и полусторона, box - рамка (юг, север, запад, восток) для тайлов."""


def difference(old, new, inside=None):
    """Разность new - old, NaN там, где нет одной из съёмок или вне
    маски inside."""
    old = np.asarray(old, dtype=np.float64)
    new = np.asarray(new, dtype=np.float64)
    diff = new - old
    if inside is not None:
        diff = np.where(np.asarray(inside, dtype=bool), diff, np.nan)
    return diff


def summary(diff, cell_area, threshold=THRESHOLD):
    """Объёмы и площади по разности: словарь cut, fill, net (м³),
    cut_area, fill_area, area (м²), deepest, highest (м)."""
    diff = np.asarray(diff, dtype=np.float64)
    known = np.isfinite(diff)
    fill = known & (diff >= threshold)
    cut = known & (diff <= -threshold)
    fill_volume = float(diff[fill].sum() * cell_area)
    cut_volume = float(-diff[cut].sum() * cell_area)
    return {"fill": fill_volume, "cut": cut_volume,
            "net": fill_volume - cut_volume,
            "fill_area": float(fill.sum() * cell_area),
            "cut_area": float(cut.sum() * cell_area),
            "area": float(known.sum() * cell_area),
            "deepest": float(diff[cut].min()) if cut.any() else 0.0,
            "highest": float(diff[fill].max()) if fill.any() else 0.0}


def for_file(diff, threshold=THRESHOLD):
    """Разность для файла: NODATA вместо NaN, мелкие разности - ноль."""
    out = np.where(np.isfinite(diff), diff, NODATA).astype(np.float32)
    small = np.isfinite(diff) & (np.abs(diff) < threshold)
    out[small] = 0.0
    return out


def balance_level(z):
    """Отметка площадки с равными выемкой и насыпью - средняя высота,
    None без высот."""
    z = np.asarray(z, dtype=np.float64)
    known = np.isfinite(z)
    return float(z[known].mean()) if known.any() else None


def earthwork(z, grid, level, radius):
    """Площадка на отметке level над высотами z сетки grid."""
    diff = float(level) - np.asarray(z, dtype=np.float64)
    known = np.isfinite(diff)
    reach = float(np.abs(diff[known]).max()) if known.any() else 0.0
    lats, lons = hydro.latlon(grid, np.array([0, grid.rows - 1]),
                              np.array([0, grid.cols - 1]), radius)
    box = (float(lats[1]), float(lats[0]), float(lons[0]), float(lons[1]))
    return Earthwork(grid, diff, float(level), max(reach, 1.0), grid.lat,
                     grid.lon, (grid.rows - 1) * grid.cell / 2.0, box)


def own_share(work, boxes, radius):
    """Доля участка на своём рельефе. boxes - рамки растров (x0, y0, x1,
    y1) в метрах Web Mercator."""
    known = np.isfinite(work.diff)
    if not known.any() or not boxes:
        return 0.0
    grid = work.grid
    rows, cols = np.nonzero(known)
    x = grid.x0 + cols * grid.step
    y = grid.y0 - rows * grid.step
    own = np.zeros(len(rows), dtype=bool)
    for x0, y0, x1, y1 in boxes:
        own |= (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
    return float(own.mean())


def open_error(work, share):
    """Оценка ошибки объёма, м³: площадь на открытых высотах × OPEN_ERROR."""
    known = int(np.isfinite(work.diff).sum())
    return known * float(work.grid.cell) ** 2 * (1.0 - share) * OPEN_ERROR


def tile_rgba(work, lats, lons, radius):
    """Картинка тайла слоя вида: выемка красная, насыпь синяя, ближе
    к площадке прозрачнее, вне участка прозрачно (ui.viewshed.
    ResultTiles)."""
    grid = work.grid
    x, y = hydro.mercator(lats, lons, radius)
    cols = np.rint((x - grid.x0) / grid.step)
    rows = np.rint((grid.y0 - y) / grid.step)
    inside = (rows >= 0) & (rows < grid.rows) & (cols >= 0) \
        & (cols < grid.cols)
    values = np.full(np.shape(lats), np.nan)
    values[inside] = work.diff[rows[inside].astype(int),
                               cols[inside].astype(int)]
    rgba = np.zeros(np.shape(lats) + (4,), dtype=np.uint8)
    known = np.isfinite(values)
    rgba[known & (values < 0.0), :3] = CUT_RGB
    rgba[known & (values >= 0.0), :3] = FILL_RGB
    share = np.abs(np.where(known, values, 0.0)) / work.reach
    rgba[..., 3] = np.where(known, 50.0 + (ALPHA - 50.0) * share, 0.0)
    rgba[known & (np.abs(values) < THRESHOLD), 3] = 0
    return rgba
