# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Заглушки вместо снимка и подмена их увеличенным предком.

Esri World Imagery там, где снимков крупного уровня нет, отвечает
не ошибкой, а картинкой «Map data not yet available». Это серый
квадрат 204, 204, 204 с надписью, 94 % пикселей одного точного цвета.
Замер 27 сентября 2026 года, уровень 19 у Соликамска и на севере
Пермского края. Настоящий снимок, даже снег или вода, так однороден
не бывает, шум сжатия JPEG даёт разброс.

Вместо заглушки глобус берёт ближайшего предка с настоящим снимком,
вырезает из его картинки долю, которую занимает тайл, и увеличивает
её до стороны тайла. Так делает Google Earth.
"""
import numpy as np

# Доля пикселей одного точного серого цвета, с которой тайл - заглушка.
PLACEHOLDER_SHARE = 0.8
# Самый глубокий предок, из которого вырезается тайл. На уровень 6
# вверх от тайла 256 пикселей приходится кусок 4 × 4.
MAX_FILL_DEPTH = 6


def is_placeholder(rgba, share=PLACEHOLDER_SHARE):
    """Заглушка ли картинка: массив (h, w, 4) uint8.

    Заглушка - серый цвет (R = G = B) не меньше чем на share пикселей.
    """
    if rgba is None or rgba.size == 0:
        return False
    rgb = rgba[..., :3].reshape(-1, 3)
    gray = (rgb[:, 0] == rgb[:, 1]) & (rgb[:, 1] == rgb[:, 2])
    if gray.mean() < share:
        return False
    counts = np.bincount(rgb[gray, 0], minlength=256)
    return counts.max() >= share * len(rgb)


def ancestor(key, depth):
    """Предок тайла key = (z, x, y) на depth уровней выше."""
    z, x, y = key
    return z - depth, x >> depth, y >> depth


def crop_window(key, depth, size=256):
    """Окно тайла key в картинке предка на depth уровней выше.

    Возвращает (x0, y0, сторона) в пикселях картинки предка стороной
    size. Первая строка картинки - северный край.
    """
    _, x, y = key
    cells = 1 << depth
    side = size // cells
    return (x % cells) * side, (y % cells) * side, side
