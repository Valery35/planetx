# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подписи слоёв проекта: окно запроса, кегль, номера, без Qt.

Подписи отмеченных векторных слоёв идут в надписи глобуса, как
названия городов: ровно при любом повороте, без наложений, за горой
и горизонтом их нет. Текст, цвет и кегль берутся из подписей слоя
в QGIS. Объекты читаются в окне вокруг точки взгляда, не больше
MAX_PER_LAYER на слой. Решение автора от 29 сентября 2026 года.
"""
import math

M_PER_DEGREE = 111320.0
WINDOW = 3.0  # окно запроса - столько ширин видимой полосы
MAX_PER_LAYER = 500  # подписей слоя за один запрос, не больше
# Объектов слоя читается за запрос, не больше. Из них остаются
# MAX_PER_LAYER ближайших к точке взгляда: первые попавшиеся лежали
# бы где угодно в окне, а середина вида пустовала.
MAX_READ = 5000


def nearest(items, lat, lon, count=MAX_PER_LAYER):
    """count элементов (…, широта, долгота, …) ближе всех к точке
    взгляда. Широта и долгота - 3-е и 4-е поле элемента. Расстояние
    считается на плоскости с поправкой долготы на широту, для выбора
    этого хватает."""
    if len(items) <= count:
        return list(items)
    cos_lat = math.cos(math.radians(lat))

    def far(item):
        dlat = item[2] - lat
        dlon = ((item[3] - lon + 180.0) % 360.0 - 180.0) * cos_lat
        return dlat * dlat + dlon * dlon
    return sorted(items, key=far)[:count]
SIZE_RANGE = (9.0, 20.0)  # кегль подписи, логических пикселей
POINTS_PER_INCH = 72.0
MM_PER_INCH = 25.4
SCREEN_DPI = 96.0
STEP = 0.5  # окно перезапрашивается при сдвиге на долю ширины окна


def window(lat, lon, width):
    """Окно запроса (запад, юг, восток, север) в градусах. Широкий вид
    - весь шар."""
    half = WINDOW * width / 2.0 / M_PER_DEGREE
    if half >= 90.0:
        return -180.0, -90.0, 180.0, 90.0
    cos_lat = max(math.cos(math.radians(lat)), 0.05)
    south = max(-90.0, lat - half)
    north = min(90.0, lat + half)
    west, east = lon - half / cos_lat, lon + half / cos_lat
    if east - west >= 360.0:
        west, east = -180.0, 180.0
    return west, south, east, north


def key(lat, lon, width):
    """Ключ перезапроса: тот же, пока вид не сдвинулся на долю STEP
    окна и не изменился вдвое по ширине."""
    half = WINDOW * width / 2.0 / M_PER_DEGREE
    cell = max(half * 2.0 * STEP, 1e-6)
    return (round(math.log2(max(width, 1.0))),
            round(lat / cell), round(lon / cell))


def pixel_size(size, unit):
    """Кегль подписи QGIS в логических пикселях экрана. unit - «points»,
    «mm» или «pixels». Кегль ограничен SIZE_RANGE."""
    if unit == "points":
        px = size * SCREEN_DPI / POINTS_PER_INCH
    elif unit == "mm":
        px = size * SCREEN_DPI / MM_PER_INCH
    else:
        px = size
    return min(max(px, SIZE_RANGE[0]), SIZE_RANGE[1])


def label_id(layer, fid):
    """Номер надписи для объекта fid слоя layer: отрицательный, чтобы
    не совпасть с номерами объектов OpenMapTiles, и один и тот же
    при каждом запросе в этом запуске QGIS."""
    return -(10 ** 7 + hash((layer, fid)) % 10 ** 12)


def dark(rgb):
    """Цвет тёмный: обводка у такой подписи нужна светлая."""
    r, g, b = rgb[:3]
    return 0.299 * r + 0.587 * g + 0.114 * b < 128.0
