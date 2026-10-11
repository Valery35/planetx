# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Исторические карты коллекции Дэвида Рамсея. Без Qt.

Просьба автора от 11 октября 2026 года - карты Рамсея на глобусе.
Тайлы привязанных карт у Рамсея (Georeferencer) - по входу. Набор
Стэнфорда «David Rumsey Map Collection: Georeferenced Maps Metadata»
(CC0) несёт для всех 56 тысяч карт опорные точки привязки, обрезку поля
карты и адрес изображения IIIF, изображение по кускам открыто. Поэтому
модуль собирает изображение сам и привязывает его через GDAL тем же
способом, что у Рамсея. Каталог - planetx-terrain/rumsey, собирает
tools/build_rumsey.py: index.json со всеми картами и cells/<клетка>.json
с подробностями.

Изображения у Рамсея - CC BY-NC-SA 3.0: некоммерческое использование
с указанием источника, модуль их не хранит и не передаёт, скачивает
пользователь.
"""
import json
import math

import numpy as np

IIIF = "https://images.iiifhosting.com/iiif/"
INDEX_PATH = "/rumsey/index.json"
CELL_PATH = "/rumsey/cells/{cell}.json"
ATTRIBUTION = ("Historical maps: David Rumsey Map Collection, "
               "CC BY-NC-SA 3.0", "https://www.davidrumsey.com")
MAX_SIDE = 3072  # пикселей по большей стороне собранного изображения
LIST_MAX = 400  # карт в списке окна
LARGE = 40.0  # во сколько раз площадь рамки больше вида - в конец списка
TILE = 256


class Catalogue:
    """Указатель карт: номера, рамки, годы, названия, масштабы, клетки."""

    def __init__(self, maps):
        self.number = np.array([m[0] for m in maps], dtype=np.int64)
        self.box = np.array([m[1:5] for m in maps], dtype=np.float64)
        self.year = [m[5] for m in maps]
        self.title = [m[6] for m in maps]
        self.scale = [m[7] for m in maps]
        self.cell = [m[8] for m in maps]

    @classmethod
    def from_text(cls, text):
        return cls(json.loads(text).get("maps", ()))

    def __len__(self):
        return len(self.number)


def area(box):
    """Площадь рамок (n, 4) в квадратных градусах с поправкой на широту."""
    box = np.asarray(box, dtype=np.float64)
    middle = np.radians((box[..., 1] + box[..., 3]) / 2.0)
    return np.maximum(box[..., 2] - box[..., 0], 1e-6) \
        * np.maximum(box[..., 3] - box[..., 1], 1e-6) * np.cos(middle)


def covering(catalogue, lat, lon, view):
    """Номера строк указателя - карты у вида: рамка задевает рамку вида
    view (запад, юг, восток, север). Сначала карты с точкой взгляда
    внутри, по площади от подробных к обзорным, карты много больше вида -
    в конце. Не больше LIST_MAX."""
    if not len(catalogue):
        return []
    b = catalogue.box
    west, south, east, north = view
    lat_hit = (b[:, 3] >= south) & (b[:, 1] <= north)
    if west <= east:
        lon_hit = (b[:, 2] >= west) & (b[:, 0] <= east)
    else:
        lon_hit = (b[:, 2] >= west) | (b[:, 0] <= east)
    hits = np.nonzero(lat_hit & lon_hit)[0]
    if not len(hits):
        return []
    inside = (b[hits, 0] <= lon) & (b[hits, 2] >= lon) \
        & (b[hits, 1] <= lat) & (b[hits, 3] >= lat)
    sizes = area(b[hits])
    view_area = float(area(np.array([west, south, east if east > west
                                      else east + 360.0, north])))
    large = sizes > LARGE * max(view_area, 1e-6)
    order = np.lexsort((sizes, large, ~inside))
    return [int(i) for i in hits[order][:LIST_MAX]]


def search(catalogue, text, limit=LIST_MAX):
    """Номера строк указателя с text в названии или годе по всему
    каталогу, не больше limit. Пустой текст - пустой список."""
    words = [w for w in str(text).lower().split() if w]
    if not words:
        return []
    found = []
    for row, (title, year) in enumerate(zip(catalogue.title,
                                            catalogue.year)):
        line = "{} {}".format(year or "", title).lower()
        if all(w in line for w in words):
            found.append(row)
            if len(found) >= limit:
                break
    return found


def fly_distance(box, fov_deg=40.0):
    """Расстояние камеры, с которого рамка карты видна целиком, м."""
    west, south, east, north = box
    middle = math.radians((south + north) / 2.0)
    width = (east - west) * 111320.0 * max(math.cos(middle), 0.05)
    height = (north - south) * 110540.0
    size = max(width, height, 500.0)
    return 0.6 * size / math.tan(math.radians(fov_deg) / 2.0)


def image_url(image):
    """Адрес службы IIIF изображения из записи каталога."""
    return image if image.startswith("http") else IIIF + image


def tile_plan(width, height, factors, max_side=MAX_SIDE, tile=TILE):
    """Уменьшение и куски изображения width × height. factors - степени
    уменьшения службы IIIF. Берётся наименьшее уменьшение, при котором
    большая сторона не больше max_side. Возвращает уменьшение, размер
    собранного изображения и куски (x, y, w, h - область в полном
    размере, ox, oy, ow, oh - место в собранном)."""
    factors = sorted(factors) or [1]
    factor = factors[-1]
    for f in factors:
        if max(width, height) / f <= max_side:
            factor = f
            break
    step = tile * factor
    out_w = int(math.ceil(width / factor))
    out_h = int(math.ceil(height / factor))
    pieces = []
    for y in range(0, height, step):
        for x in range(0, width, step):
            w = min(step, width - x)
            h = min(step, height - y)
            pieces.append((x, y, w, h, x // factor, y // factor,
                           int(math.ceil(w / factor)),
                           int(math.ceil(h / factor))))
    return factor, out_w, out_h, pieces


def piece_url(service, piece):
    """Адрес куска IIIF Image API 2: область и ширина в пикселях."""
    x, y, w, h, _, _, ow, _ = piece
    return "{}/{},{},{},{}/{},/0/default.jpg".format(service, x, y, w, h,
                                                     ow)


def warp_options(method, count):
    """Параметры gdal.Warp по способу привязки Рамсея: tps - тонкая
    пластина, polynomial - полином второй степени (третьей при 10 и
    больше точках), прочее - первой."""
    if method == "tps" and count >= 3:
        return {"tps": True}
    if method == "polynomial":
        return {"polynomialOrder": 3 if count >= 10 else 2}
    return {"polynomialOrder": 1}


def scaled_points(points, factor):
    """Опорные точки (x, y, долгота, широта) и обрезка в пикселях
    собранного изображения с уменьшением factor."""
    return [(p[0] / factor, p[1] / factor, p[2], p[3]) for p in points]


def year_text(year):
    if year is None:
        return ""
    return str(year) if year > 0 else "{} до н. э.".format(1 - year)
