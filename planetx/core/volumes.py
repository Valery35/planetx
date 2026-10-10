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
"""
import numpy as np

THRESHOLD = 0.1  # м, разность меньше - шум съёмки
NODATA = -9999.0


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
