# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Уклон и экспозиция поверхности по тайлу высот. Расчёт без Qt.

Шаг 1 плана фазы 3 (doc/PLAN_PHASE3.md), решение автора от 2 октября
2026 года. Тайл высот Terrarium - 256×256 пикселей в сетке Web
Mercator. Mercator равноугольна, поэтому шаг пикселя на местности
по широте и долготе один и тот же в пределах строки и равен
2πR·cos φ / (256·2^z), φ - широта строки, R - радиус тела. Производные
высоты по востоку и северу - numpy.gradient, делённый на шаг строки,
на краях тайла односторонние.

Уклон - угол поверхности к горизонту, 0-90°. Экспозиция - азимут
направления вниз по склону, куда склон обращён, 0° - север, 90° -
восток, по часовой стрелке. У почти ровного места (уклон меньше
FLAT) экспозиции нет, NaN. Высоты берутся настоящие, без
вертикального масштаба вида.

Раскраска - RGBA uint8 с премноженной альфой и непрозрачностью
OPACITY, как у слоя температуры (core/temperature.py). Шкала уклона
и цвета сторон света предложил помощник, автор утвердил их 2 октября
2026 года.
"""
import math

import numpy as np

SIZE = 256
FLAT = 0.5  # градусов, ровнее - экспозиции нет
OPACITY = 0.7
# Шкала уклона: (нижняя граница класса, °; цвет). Зелёный - ровно,
# красный и лиловый - круто.
SLOPE_STOPS = ((0.0, (26, 150, 65)), (2.0, (166, 217, 106)),
               (5.0, (255, 255, 191)), (10.0, (253, 174, 97)),
               (15.0, (244, 109, 67)), (25.0, (215, 25, 28)),
               (35.0, (128, 0, 128)))
# Цвета сторон света для экспозиции, по часовой стрелке от севера.
ASPECT_STOPS = ((0.0, (230, 25, 75)), (45.0, (245, 130, 48)),
                (90.0, (255, 225, 25)), (135.0, (60, 180, 75)),
                (180.0, (70, 240, 240)), (225.0, (0, 130, 200)),
                (270.0, (145, 30, 180)), (315.0, (240, 50, 230)),
                (360.0, (230, 25, 75)))
FLAT_COLOR = (200, 200, 200)


def row_latitudes(z, y, size=SIZE):
    """Широты центров строк тайла (z, y), градусы."""
    n = 1 << z
    t = (y + (np.arange(size) + 0.5) / size) / n
    return np.degrees(np.arctan(np.sinh(math.pi * (1.0 - 2.0 * t))))


def pixel_size(z, y, radius, size=SIZE):
    """Шаг пикселя на местности по строкам тайла, метры."""
    lat = np.radians(row_latitudes(z, y, size))
    return 2.0 * math.pi * radius * np.cos(lat) / (size * (1 << z))


def gradients(heights, z, y, radius):
    """Производные высоты по востоку и по северу, безразмерные."""
    h = np.asarray(heights, dtype=np.float64)
    step = pixel_size(z, y, radius, h.shape[0])[:, None]
    d_row, d_col = np.gradient(h)
    # Строки тайла идут с севера на юг.
    return d_col / step, -d_row / step


def slope_aspect(heights, z, y, radius):
    """Уклон, градусы, и экспозиция, градусы от севера или NaN."""
    east, north = gradients(heights, z, y, radius)
    slope = np.degrees(np.arctan(np.hypot(east, north)))
    # Вниз по склону - против градиента высоты.
    aspect = np.degrees(np.arctan2(-east, -north)) % 360.0
    aspect[slope < FLAT] = np.nan
    return slope, aspect


def _classes(values, stops):
    """Цвет класса по нижним границам шкалы."""
    bounds = np.array([s[0] for s in stops])
    colors = np.array([s[1] for s in stops], dtype=np.float32)
    index = np.clip(np.searchsorted(bounds, values, side="right") - 1,
                    0, len(stops) - 1)
    return colors[index]


def _blend(values, stops):
    """Цвет по шкале с плавным переходом между точками."""
    bounds = np.array([s[0] for s in stops])
    colors = np.array([s[1] for s in stops], dtype=np.float32)
    return np.stack([np.interp(values, bounds, colors[:, c])
                     for c in range(3)], axis=-1)


def _premultiplied(rgb, alpha):
    out = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.rint(rgb * alpha[..., None])
    out[..., 3] = np.rint(alpha * 255.0)
    return out


def slope_rgba(slope):
    """Раскраска уклона классами SLOPE_STOPS."""
    alpha = np.full(slope.shape, OPACITY, dtype=np.float32)
    return _premultiplied(_classes(slope, SLOPE_STOPS), alpha)


def aspect_rgba(aspect):
    """Раскраска экспозиции цветами сторон света, ровное - серое."""
    flat = np.isnan(aspect)
    rgb = _blend(np.where(flat, 0.0, aspect), ASPECT_STOPS)
    rgb[flat] = FLAT_COLOR
    alpha = np.where(flat, OPACITY * 0.4, OPACITY).astype(np.float32)
    return _premultiplied(rgb, alpha)
