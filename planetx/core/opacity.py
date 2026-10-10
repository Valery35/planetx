# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Непрозрачность выделенных «Моих меток» ползунком под списком, как
ползунок под «Местами» Google Earth Pro.

Непрозрачность объекта - альфа его цветов, так её хранит и KML. У метки
это цвет линии или значка и цвет заливки, у картинки - её цвет.
Ползунок показывает непрозрачность выделения - наибольшую альфу среди
выделенных объектов. Движение ползунка умножает альфы, снятые при
выделении, на отношение нового значения к прежнему, поэтому заливка
остаётся прозрачнее линии в той же доле. Из полной прозрачности
альфа ставится прямо значением ползунка, заливка - в FILL_SHARE от
него.
"""

FILL_SHARE = 0.5  # доля альфы заливки от линии после полной прозрачности


def alpha_of(color):
    return int(color[3]) if color is not None and len(color) > 3 else 255


def opacity_of(colors):
    """Непрозрачность объекта 0..1 по его цветам - наибольшая альфа.
    colors - цвета RGBA 0-255, None пропускается."""
    alphas = [alpha_of(c) for c in colors if c is not None]
    return max(alphas) / 255.0 if alphas else 1.0


def selection_opacity(items):
    """Непрозрачность выделения: items - списки цветов объектов."""
    values = [opacity_of(colors) for colors in items]
    return max(values) if values else 1.0


def scaled(colors, base, value):
    """Цвета colors (линия, затем прочие) при смене непрозрачности
    выделения с base на value, обе 0..1. None остаётся None."""
    out = []
    for n, color in enumerate(colors):
        if color is None:
            out.append(None)
            continue
        if base > 0.0:
            alpha = alpha_of(color) * value / base
        else:
            alpha = 255.0 * value * (1.0 if n == 0 else FILL_SHARE)
        alpha = int(round(min(max(alpha, 0.0), 255.0)))
        out.append(tuple(int(c) for c in color[:3]) + (alpha,))
    return out
