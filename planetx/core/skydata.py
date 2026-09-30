# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Созвездия, имена звёзд и светила для вида неба, без Qt.

Файл data/constellations.json собирает tools/build_constellations.py
из данных d3-celestial. Положения Солнца, Луны и планет считает
core/ephemeris.py. Всё в экваториальной системе J2000.
"""
import json
import math
import os

import numpy as np

try:  # внутри плагина QGIS
    from . import ephemeris
except ImportError:  # headless-тесты
    import ephemeris

DATA = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "data", "constellations.json")

# Светила: цвет RGB и размер точки в логических пикселях. Размер
# условный, он не следует блеску. Подобраны помощником.
BODY_STYLE = {
    "sun": ((1.0, 0.93, 0.62), 16.0),
    "moon": ((0.92, 0.92, 0.88), 14.0),
    "mercury": ((0.82, 0.76, 0.70), 5.0),
    "venus": ((1.0, 0.98, 0.88), 8.0),
    "mars": ((1.0, 0.52, 0.32), 6.5),
    "jupiter": ((1.0, 0.93, 0.80), 7.5),
    "saturn": ((0.96, 0.86, 0.60), 6.5),
    "uranus": ((0.62, 0.90, 0.95), 4.5),
    "neptune": ((0.50, 0.62, 1.0), 4.5),
}


def load(path=DATA):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def direction(ra, dec):
    """Единичный вектор J2000 по RA и Dec в градусах."""
    r, d = math.radians(ra), math.radians(dec)
    return (math.cos(d) * math.cos(r), math.cos(d) * math.sin(r),
            math.sin(d))


def segments(data):
    """Отрезки фигур созвездий парами направлений, (2N, 3) float32,
    для GL_LINES."""
    out = []
    for line in data["lines"]:
        points = [direction(ra, dec) for ra, dec in line]
        for a, b in zip(points, points[1:]):
            out.append(a)
            out.append(b)
    return np.array(out, dtype=np.float32).reshape(-1, 3)


def bodies(unix_time):
    """Светила на момент: (ключ, направление, цвет, размер)."""
    out = []
    for name in ephemeris.BODIES:
        color, size = BODY_STYLE[name]
        out.append((name, ephemeris.direction(name, unix_time), color, size))
    return out


def body_points(unix_time):
    """Вершины светил для программы звёзд render/stars.py, (N, 8):
    направление, размер, цвет и яркость."""
    rows = []
    for _, v, color, size in bodies(unix_time):
        rows.append(list(v) + [size] + list(color) + [1.0])
    return np.array(rows, dtype=np.float32)
