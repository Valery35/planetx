# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поле «Скрывать дальше, км» окон свойств метки и папки.

Поле пишет Region KML (core/region.py). Region из чужого файла поле
показывает тем же расстоянием, правка меняет у него только
minLodPixels, рамка и maxLodPixels остаются.
"""
from qgis.PyQt.QtWidgets import QDoubleSpinBox

from ..core import region
from ..i18n import tr

MAX_KM = 20000.0


def make(parent, current):
    """Поле расстояния для Region current (или None)."""
    field = QDoubleSpinBox(parent)
    field.setRange(0.0, MAX_KM)
    field.setDecimals(1)
    field.setSuffix(tr(" км"))
    field.setSpecialValueText(tr("не скрывать"))
    km = region.distance_km(current)
    field.setValue(min(km, MAX_KM) if km is not None else 0.0)
    field.setToolTip(tr(
        "Метка видна, только пока глаз ближе этого расстояния, как "
        "Region в KML. У папки - все её метки. 0 - видна всегда."))
    return field


def value(field, points, current):
    """Region по полю: km 0 - без нижнего предела. Region из файла
    с maxLodPixels остаётся с ним, иначе Region снимается."""
    km = field.value()
    if km > 0.0 and points:
        return region.for_distance(points, km, current)
    if km > 0.0:
        return current
    if current is not None and current.max_lod >= 0.0:
        return current._replace(min_lod=0.0)
    return None
