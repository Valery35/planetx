# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Мозаика тайлов подложки под участком для расчётов окон анализа.

Вопрос Василия Швалёва от 1 ноября 2026 года - сегментировать
и классифицировать снимки с подложек. Окна «Классификация» и «Похожие
области» читают растр, поэтому тайлы подложки складываются в одну
картинку EPSG:3857 в памяти. На диск она не пишется.

Уровень тайлов - первый, у которого пиксель не крупнее шага сетки
участка. Тайла нет или вместо снимка заглушка - берётся увеличенный
предок (core/placeholder.py), как на глобусе.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .basemap import MERCATOR_HALF, tile_bbox
    from .placeholder import (MAX_FILL_DEPTH, ancestor, crop_window,
                              is_placeholder)
except ImportError:  # headless-тесты
    from basemap import MERCATOR_HALF, tile_bbox
    from placeholder import (MAX_FILL_DEPTH, ancestor, crop_window,
                             is_placeholder)

SIZE = 256  # пикселей на сторону тайла
MAX_TILES = 1024  # тайлов мозаики, массового скачивания нет
LAT_LIMIT = 85.05  # предел широты Web Mercator
MIN_COS = 0.01  # косинус широты у полюса, чтобы пиксель не был нулём


def tile_pixel(lat, z):
    """Сторона пикселя тайла уровня z на местности у широты lat, м."""
    cos = max(math.cos(math.radians(lat)), MIN_COS)
    return 2.0 * MERCATOR_HALF * cos / (SIZE * (1 << z))


def level_for(lat, pixel, top):
    """Первый уровень от 0 до top с пикселем не крупнее pixel метров,
    у top - даже если пиксель крупнее."""
    for z in range(top + 1):
        if tile_pixel(lat, z) <= pixel:
            return z
    return top


def tile_column(lon, z):
    count = 1 << z
    return min(max(int((lon + 180.0) / 360.0 * count), 0), count - 1)


def tile_row(lat, z):
    count = 1 << z
    lat = min(max(lat, -LAT_LIMIT), LAT_LIMIT)
    share = 0.5 - math.asinh(math.tan(math.radians(lat))) / (2.0 * math.pi)
    return min(max(int(share * count), 0), count - 1)


def span(box, z):
    """Тайлы уровня z под рамкой box (запад, юг, восток, север, градусы):
    первый и последний столбец, первая и последняя строка."""
    west, south, east, north = box
    return (tile_column(west, z), tile_column(east, z),
            tile_row(north, z), tile_row(south, z))


def tile_count(frame):
    first, last, top, bottom = frame
    return (last - first + 1) * (bottom - top + 1)


def tile_keys(z, frame):
    first, last, top, bottom = frame
    return [(z, x, y) for y in range(top, bottom + 1)
            for x in range(first, last + 1)]


def geotransform(z, frame):
    """Привязка мозаики в метрах EPSG:3857 для GDAL."""
    west, _, east, north = tile_bbox(z, frame[0], frame[2])
    pixel = (east - west) / SIZE
    return west, pixel, 0.0, north, 0.0, -pixel


def crop(rgba, key, depth):
    """Окно тайла key в картинке его предка на depth уровней выше,
    увеличенное до стороны картинки: пиксель - квадрат пикселей, пересчёт
    на сетку участка потом сгладит ступени."""
    if not depth:
        return rgba
    x0, y0, side = crop_window(key, depth, rgba.shape[0])
    part = rgba[y0:y0 + side, x0:x0 + side]
    return part.repeat(1 << depth, axis=0).repeat(1 << depth, axis=1)


def is_image(rgba):
    """Картинка годится: есть, и это не заглушка. Прозрачный тайл - ответ
    «здесь пусто», заглушкой он не считается."""
    if rgba is None:
        return False
    return not rgba[:, :, 3].any() or not is_placeholder(rgba)


def gather(keys, read):
    """Картинки тайлов keys: {ключ: RGBA}. read(ключи) даёт {ключ: RGBA
    или None}. Недостающие ищутся у предков, не выше MAX_FILL_DEPTH. Тайл
    без картинки в итог не входит."""
    found = {}
    left = list(keys)
    for depth in range(MAX_FILL_DEPTH + 1):
        if not left:
            break
        left = [key for key in left if depth <= key[0]]
        images = read(sorted({ancestor(key, depth) for key in left}))
        rest = []
        for key in left:
            image = images.get(ancestor(key, depth))
            if is_image(image):
                found[key] = crop(image, key, depth)
            else:
                rest.append(key)
        left = rest
    return found


def assemble(z, frame, found):
    """Мозаика RGBA uint8 из картинок found, пустое место прозрачно."""
    first, last, top, bottom = frame
    out = np.zeros(((bottom - top + 1) * SIZE, (last - first + 1) * SIZE, 4),
                   dtype=np.uint8)
    for (_, x, y), image in found.items():
        col, row = (x - first) * SIZE, (y - top) * SIZE
        out[row:row + SIZE, col:col + SIZE] = image
    return out
