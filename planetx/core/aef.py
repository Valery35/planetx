# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Изменения местности по эмбеддингам AlphaEarth Foundations. Модуль
не знает про Qt.

Просьба автора от 28 октября 2026 года по образцу «Обнаружить
изменение» Google Earth. Набор AlphaEarth Foundations Satellite
Embedding (Google, Google DeepMind, CC BY 4.0) - на каждый год
2017-2025 у клетки 10 м вектор из 64 чисел, сводка снимков и радара
за год. Степень изменения между двумя годами - несходство векторов,
1 - косинус угла между ними: у неизменённой местности около 0.05,
у стройки, вырубки, нового карьера - 0.5 и выше. Так считает и Google
Earth, его шкала тоже от 0 до 1.

Файлы - COG в хранилище Google Cloud без учётной записи: по зонам UTM
квадраты 81 920 м (8192 пикселя), 64 канала Int8 плоскостями, сжатие
ZSTD, обзоры до 1 × 1. Значение v - вектор sign(v) · (v / 127.5)²,
-128 - нет данных. Указатель файлов (у Google - parquet 70 МБ) собран
по зонам в planetx-terrain/aef (tools/build_aef_index.py): квадраты
зоны с именами файлов по годам.

Обзор вида идёт с обзоров файлов - пиксель не мельче 160 м (PREVIEW_
LEVEL), тайлы глубже PREVIEW_ZOOM вне подробного участка пусты, вид
рисует предка. Подробный участок - полное разрешение 10 м: блок файла
1024 × 1024 у каждого из 64 каналов, около 40 МБ на год, поэтому
участок задаёт пользователь, а окно называет объём загрузки.
Степень изменения считается один раз на квадрат, обзор и блок
и помнится байтами (Changes), векторы после расчёта не хранятся.
"""
import json
import math
import threading
from collections import OrderedDict

import numpy as np

try:  # внутри плагина QGIS
    from .cog import tile_points
    from .coords import utm_arrays
    from .subsurface import inside as ring_inside
except ImportError:  # headless-тесты
    from cog import tile_points
    from coords import utm_arrays
    from subsurface import inside as ring_inside

YEARS = tuple(range(2017, 2026))
BASE = ("https://storage.googleapis.com/alphaearth_foundations/"
        "satellite_embedding/v1/annual/")
INDEX = "aef/{zone}.json"  # путь указателя зоны в planetx-terrain
ATTRIBUTION = "AlphaEarth Foundations, Google, Google DeepMind"
TERMS = ("https://developers.google.com/earth-engine/datasets/catalog/"
         "GOOGLE_SATELLITE_EMBEDDING_V1_ANNUAL")
# Подпись по условиям набора (CC BY 4.0), её просит Google.
CREDIT = ("The AlphaEarth Foundations Satellite Embedding dataset is "
          "produced by Google and Google DeepMind.")
CELL = 81920.0  # сторона квадрата файла, м
FILE_SIDE = 8192  # пикселей полного разрешения на сторону файла
TILE = 1024  # пикселей тайла файла на всех обзорах
PIXEL = 10.0  # м полного разрешения
HEAD = 1 << 17  # байт начала файла: каталоги всех 14 обзоров
NODATA = -128
EMPTY = 255  # нет данных в байтах степени изменения
# Обзор вида: обзор файла с пикселем не крупнее PIXEL_SHARE пикселей
# тайла, но не мельче PREVIEW_LEVEL (160 м, 13 МБ на файл и год).
PIXEL_SHARE = 2.0
PREVIEW_LEVEL = 4
MIN_ZOOM = 8  # мельче тайлы без слоя: заголовков файлов было бы сотни
PREVIEW_ZOOM = 11  # глубже - только подробный участок
DETAIL_ZOOM = 14  # тайлы подробного участка, пиксель тайла 5-10 м
DETAIL_SIDE = 20000.0  # наибольшая сторона подробного участка, м
# Подробность участка: обзор и пиксель, м. Сжатый блок 1024 × 1024
# всех 64 каналов за год, МБ, по замеру 28 октября 2026 года у файла
# зоны 10N: 10 м - 42, 20 м - 45, 40 м - 50, 80 м - 52 (весь файл).
DETAIL_LEVELS = ((0, 10), (1, 20), (2, 40), (3, 80))
BLOCK_MB = (42.0, 45.0, 50.0, 52.0)
CHUNK = 128  # строк блока за шаг расчёта: 64 канала float32 в памяти
# Классификация: ближайших контрольных точек голосуют, наименьшее
# количество точек класса и классов, как у Google Earth.
KNN = 5
MIN_POINTS = 3
MIN_CLASSES = 2
# Пиксель «Авто» классификации: клеток участка от AUTO_FEW до
# AUTO_CELLS, из таких - с наименьшей загрузкой, при равной - мельче.
AUTO_CELLS = 800 * 800
AUTO_FEW = 120 * 120
KEPT_BYTES = 256 << 20  # байт степени изменения в памяти
# Шкала - от чёрного к жёлтому, как у Google Earth.
STOPS = ((0.0, (0, 0, 0)), (0.35, (70, 60, 10)), (0.65, (190, 170, 20)),
         (1.0, (255, 245, 30)))
OPACITY = 0.8
# Величина v шага 1 - вектор, -128 - нет данных (NaN).
LUT = np.array([math.copysign((v / 127.5) ** 2, v) for v in range(-128, 128)],
               dtype=np.float32)
LUT[0] = np.nan


def file_url(year, zone, name):
    """Адрес файла года: name - «образ:строка:столбец» указателя,
    строка и столбец в долях 8192 пикселей образа Earth Engine."""
    image, row, col = name.split(":")
    return "{}{}/{}/{}-{:010d}-{:010d}.tiff".format(
        BASE, year, zone, image, int(row) * FILE_SIDE, int(col) * FILE_SIDE)


def zone_of(lon, lat):
    """Зона указателя для точки: номер 1-60 по долготе и полушарие."""
    number = int(np.clip(np.floor((lon + 180.0) / 6.0), 0, 59)) + 1
    return "{}{}".format(number, "N" if lat >= 0 else "S")


class ZoneIndex:
    """Квадраты одной зоны UTM: западный и северный край, имена файлов
    по годам."""

    def __init__(self, zone, cells):
        self.zone = zone
        self.number = int(zone[:-1])
        self.south = zone.endswith("S")
        self.west = np.array([c[0] for c in cells], dtype=np.float64)
        self.north = np.array([c[1] for c in cells], dtype=np.float64)
        self.names = [{int(y): n for y, n in c[2].items()} for c in cells]

    @classmethod
    def parse(cls, data):
        """Указатель из байтов JSON файла planetx-terrain/aef."""
        doc = json.loads(bytes(data).decode("utf-8"))
        return cls(doc["zone"], doc["cells"])

    def project(self, lon, lat):
        """Точки (градусы) в метры UTM зоны."""
        return utm_arrays(lat, lon, self.number, self.south)

    def cells_in(self, west, south, east, north):
        """Номера квадратов, задевающих рамку UTM."""
        hit = (self.west < east) & (self.west + CELL > west) \
            & (self.north > south) & (self.north - CELL < north)
        return np.nonzero(hit)[0].tolist()

    def name(self, cell, year):
        return self.names[cell].get(int(year))


def build_index(rows):
    """Указатели зон из строк parquet Google: (путь, год, зона, запад,
    север). Словарь зона: документ JSON."""
    zones = {}
    for path, year, zone, west, north in rows:
        tail = path.rsplit("/", 1)[1].rsplit(".", 1)[0]
        image, row, col = tail.rsplit("-", 2)
        name = "{}:{}:{}".format(image, int(row) // FILE_SIDE,
                                 int(col) // FILE_SIDE)
        key = (int(round(west)), int(round(north)))
        zones.setdefault(zone, {}).setdefault(key, {})[str(year)] = name
    out = {}
    for zone, cells in zones.items():
        out[zone] = {"zone": zone, "cell": CELL, "cells": [
            [w, n, dict(sorted(names.items()))]
            for (w, n), names in sorted(cells.items())]}
    return out


def level_for(pixel, levels=14):
    """Обзор файла для тайла обзора вида с пикселем pixel метров:
    пиксель обзора 10 · 2^k не крупнее PIXEL_SHARE · pixel и не мельче
    PREVIEW_LEVEL."""
    level = int(math.floor(math.log2(max(PIXEL_SHARE * pixel / PIXEL,
                                         1.0))))
    return min(max(level, PREVIEW_LEVEL), levels - 1)


def tile_pixel(z, y):
    """Пиксель тайла z/y на местности, м, по широте его середины."""
    n = 1 << z
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 0.5)
                                                       / n))))
    return 2 * math.pi * 6378137.0 * math.cos(math.radians(lat)) / (256 * n)


def change(a, b):
    """Степень изменения по векторам двух лет: массивы Int8 (64, ...)
    в float32 (...), 1 - косинус, от 0 до 1, NaN без данных. Считается
    полосами по CHUNK строк: 64 канала float32 блока 1024 × 1024 - это
    256 МБ."""
    shape = a.shape[1:]
    a2 = a.reshape(a.shape[0], -1)
    b2 = b.reshape(b.shape[0], -1)
    out = np.empty(a2.shape[1], dtype=np.float32)
    step = CHUNK * (shape[-1] if len(shape) > 1 else 1)
    for start in range(0, a2.shape[1], step):
        va = LUT[a2[:, start:start + step].astype(np.int16) + 128]
        vb = LUT[b2[:, start:start + step].astype(np.int16) + 128]
        dot = (va * vb).sum(axis=0)
        norm = np.sqrt((va * va).sum(axis=0) * (vb * vb).sum(axis=0))
        with np.errstate(invalid="ignore", divide="ignore"):
            part = 1.0 - dot / norm
        part[~(norm > 0.25)] = np.nan
        out[start:start + step] = np.clip(part, 0.0, 1.0)
    return out.reshape(shape)


def to_bytes(values):
    """Степень изменения в байты 0-254, EMPTY - нет данных."""
    out = np.full(values.shape, EMPTY, dtype=np.uint8)
    ok = np.isfinite(values)
    out[ok] = np.rint(values[ok] * 254.0).astype(np.uint8)
    return out


def from_bytes(data):
    values = data.astype(np.float32) / 254.0
    values[data == EMPTY] = np.nan
    return values


def colors(values, low=0.0, high=1.0, opacity=OPACITY):
    """Раскраска степени изменения RGBA uint8: шкала STOPS, вне
    промежутка low..high и без данных - прозрачно."""
    rgba = np.zeros(values.shape + (4,), dtype=np.uint8)
    show = np.isfinite(values) & (values >= low - 1e-6) \
        & (values <= high + 1e-6)
    if not show.any():
        return rgba
    v = values[show]
    for channel in range(3):
        rgba[..., channel][show] = np.interp(
            v, [s[0] for s in STOPS],
            [s[1][channel] for s in STOPS]).astype(np.uint8)
    rgba[..., 3][show] = int(round(255 * opacity))
    return rgba


class Changes:
    """Степень изменения пары лет по квадратам, обзорам и блокам.
    open_cog(год, зона, имя) - файл core.cog.Cog или None, его даёт
    вызывающий. Рабочие потоки зовут одновременно: каждый кусок
    считается один раз."""

    def __init__(self, before, after, open_cog):
        self.before, self.after = int(before), int(after)
        self.open_cog = open_cog
        self.lock = threading.Lock()
        self.parts = OrderedDict()  # ключ: (x0, y0, шаг, байты) или None
        self.making = {}
        self.kept = 0

    def part(self, index, cell, level, col, row):
        """Кусок степени изменения: (x0, y0, (dx, dy), байты) - блок
        col, row обзора level квадрата cell, угол и шаги пикселя со
        знаком в метрах UTM, None - нет данных."""
        key = (index.zone, cell, level, col, row)
        with self.lock:
            if key in self.parts:
                self.parts.move_to_end(key)
                return self.parts[key]
            lock = self.making.setdefault(key, threading.Lock())
        with lock:
            with self.lock:
                if key in self.parts:
                    return self.parts[key]
            found = self._make(index, cell, level, col, row)
            with self.lock:
                self.parts[key] = found
                self.making.pop(key, None)
                if found is not None:
                    self.kept += found[3].nbytes
                while self.kept > KEPT_BYTES and len(self.parts) > 1:
                    _, old = self.parts.popitem(last=False)
                    if old is not None:
                        self.kept -= old[3].nbytes
            return found

    def _make(self, index, cell, level, col, row):
        tiles = []
        for year in (self.before, self.after):
            name = index.name(cell, year)
            if name is None:
                return None
            cog = self.open_cog(year, index.zone, name)
            if cog is None:
                return None
            tile = cog.band_tile(level, col, row)
            if tile is None:
                return None
            tiles.append((cog, tile))
        (cog, a), (_, b) = tiles
        h = min(a.shape[1], b.shape[1])
        w = min(a.shape[2], b.shape[2])
        image = cog.images[level]
        x0, dx, _, y0, _, dy = cog.transform
        dx, dy = dx * image.scale, dy * image.scale
        # Угол куска и шаги со знаком: у файлов AlphaEarth строки идут
        # с юга на север, шаг по Y положительный.
        values = to_bytes(change(a[:, :h, :w], b[:, :h, :w]))
        return (x0 + col * image.tile_w * dx, y0 + row * image.tile_h * dy,
                (dx, dy), values)

    def frame(self, index, cell):
        """Привязка полного разрешения квадрата (x0, dx, y0, dy) по файлу
        первого года, None - файла нет."""
        name = index.name(cell, self.before)
        cog = self.open_cog(self.before, index.zone, name) if name else None
        if cog is None:
            return None
        x0, dx, _, y0, _, dy = cog.transform
        return (x0, dx, y0, dy)


def tile_values(changes, index_of, z, x, y, detail=None, detail_level=0,
                size=256, ring=None):
    """Степень изменения тайла z/x/y size × size float32, NaN без
    данных, или None - тайл пуст. index_of(зона) - ZoneIndex или None.
    detail - рамка подробного участка (запад, юг, восток, север)
    в градусах, в ней - обзор detail_level (0 - 10 м). ring - участок
    многоугольником (широта, долгота): глубже обзора вне него пусто."""
    n = 1 << z
    west = x / n * 360.0 - 180.0
    east = (x + 1) / n * 360.0 - 180.0
    north = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    south = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1)
                                                         / n))))
    inside = detail is not None and west < detail[2] and east > detail[0] \
        and south < detail[3] and north > detail[1]
    if z > PREVIEW_ZOOM and not inside:
        return None
    # В участке глубже обзора - всегда обзор участка: иначе тайлы
    # уровней 12, 13 и 14 читали бы три обзора по 40 МБ на год.
    level = detail_level if z > PREVIEW_ZOOM \
        else level_for(tile_pixel(z, y))
    lon, lat = tile_points(z, x, y, size)
    out = np.full(lon.shape, np.nan, dtype=np.float32)
    zone_numbers = np.clip(np.floor((lon + 180.0) / 6.0), 0, 59) + 1
    any_index = False
    for number in np.unique(zone_numbers).astype(int).tolist():
        for hemisphere in ("N", "S"):
            pick = (zone_numbers == number) & (
                (lat >= 0) if hemisphere == "N" else (lat < 0))
            if not pick.any():
                continue
            index = index_of("{}{}".format(number, hemisphere))
            if index is None:
                continue
            any_index = True
            xs, ys = index.project(lon[pick], lat[pick])
            out[pick] = _sample(changes, index, level, xs, ys)
    if not any_index:
        return None
    if ring and z > PREVIEW_ZOOM:
        out[~ring_inside(lat, lon, ring)] = np.nan
    return out


def _sample(changes, index, level, xs, ys):
    """Степень изменения в точках зоны, ближайший пиксель куска."""
    out = np.full(xs.shape, np.nan, dtype=np.float32)
    for cell in index.cells_in(xs.min(), ys.min(), xs.max(), ys.max()):
        west, north = index.west[cell], index.north[cell]
        here = (xs >= west) & (xs < west + CELL) & (ys <= north) \
            & (ys > north - CELL)
        if not here.any():
            continue
        frame = changes.frame(index, cell)
        if frame is None:
            continue
        x0, dx, y0, dy = frame
        scale = 1 << level
        cols = np.floor((xs - x0) / (dx * scale * TILE)).astype(int)
        rows = np.floor((ys - y0) / (dy * scale * TILE)).astype(int)
        for col, row in set(zip(cols[here].tolist(), rows[here].tolist())):
            if col < 0 or row < 0:
                continue
            found = changes.part(index, cell, level, col, row)
            if found is None:
                continue
            px, py, (sx, sy), data = found
            use = here & (cols == col) & (rows == row)
            c = np.floor((xs[use] - px) / sx).astype(int)
            r = np.floor((ys[use] - py) / sy).astype(int)
            ok = (c >= 0) & (r >= 0) & (c < data.shape[1]) \
                & (r < data.shape[0])
            values = np.full(c.shape, EMPTY, dtype=np.uint8)
            values[ok] = data[r[ok], c[ok]]
            out[use] = from_bytes(values)
    return out


def detail_parts(index, box, level=0, south_up=True):
    """Блоки обзора level подробного участка в зоне index: (квадрат,
    столбец, строка). box - рамка участка в градусах. south_up - строки
    файлов идут с юга, как у AlphaEarth."""
    west, south, east, north = box
    lon = np.array([west, east, west, east, (west + east) / 2])
    lat = np.array([south, south, north, north, (south + north) / 2])
    xs, ys = index.project(lon, lat)
    x0, x1, y0, y1 = xs.min(), xs.max(), ys.min(), ys.max()
    block = TILE * PIXEL * (1 << level)
    last = max(FILE_SIDE // TILE >> level, 1) - 1
    out = []
    for cell in index.cells_in(x0, y0, x1, y1):
        cw, cn = index.west[cell], index.north[cell]
        c0 = int(max(0, math.floor((x0 - cw) / block)))
        c1 = int(min(last, math.floor((x1 - cw) / block)))
        if south_up:
            base = cn - CELL
            r0 = int(max(0, math.floor((y0 - base) / block)))
            r1 = int(min(last, math.floor((y1 - base) / block)))
        else:
            r0 = int(max(0, math.floor((cn - y1) / block)))
            r1 = int(min(last, math.floor((cn - y0) / block)))
        for col in range(c0, c1 + 1):
            for row in range(r0, r1 + 1):
                out.append((cell, col, row))
    return out


def mosaic(changes, index, box, level=0):
    """Степень изменения подробного участка на сетке файлов зоны:
    (x0, y0 - левый верхний угол, шаг м, float32 строки с севера) или
    None. Квадраты одной зоны на одной сетке 10 м, поэтому куски
    складываются без пересчёта."""
    parts = detail_parts(index, box, level)
    pieces = []
    for cell, col, row in parts:
        found = changes.part(index, cell, level, col, row)
        if found is not None:
            pieces.append(found)
    if not pieces:
        return None
    west, south, east, north = box
    lon = np.array([west, east, west, east])
    lat = np.array([south, south, north, north])
    xs, ys = index.project(lon, lat)
    step = abs(pieces[0][2][0])
    x0 = math.floor(xs.min() / step) * step
    y1 = math.ceil(ys.max() / step) * step
    width = int(math.ceil((xs.max() - x0) / step))
    height = int(math.ceil((y1 - ys.min()) / step))
    out = np.full((height, width), np.nan, dtype=np.float32)
    # Середины пикселей мозаики.
    cx = x0 + (np.arange(width) + 0.5) * step
    cy = y1 - (np.arange(height) + 0.5) * step
    for px, py, (sx, sy), data in pieces:
        c = np.floor((cx - px) / sx).astype(int)
        r = np.floor((cy - py) / sy).astype(int)
        okc = (c >= 0) & (c < data.shape[1])
        okr = (r >= 0) & (r < data.shape[0])
        if not okc.any() or not okr.any():
            continue
        block = from_bytes(data[np.ix_(r[okr], c[okc])])
        target = out[np.ix_(okr, okc)]
        use = np.isfinite(block)
        target[use] = block[use]
        out[np.ix_(okr, okc)] = target
    return x0, y1, step, out


def auto_level(index, box, side, most=AUTO_CELLS, few=AUTO_FEW):
    """Уровень пикселя «Авто» для квадрата box со стороной side метров.
    Из DETAIL_LEVELS с клетками участка от few до most берётся уровень
    с наименьшей загрузкой блоков, при равной - мельче. Нет таких -
    ближайший к пределам."""
    best = None
    for level, pixel in DETAIL_LEVELS:
        cells = (side / pixel) ** 2
        if cells > most:
            continue
        if cells < few and best is not None:
            break
        mb = detail_megabytes(detail_parts(index, box, level), level)
        if best is None or mb < best[0]:
            best = (mb, level)
    return DETAIL_LEVELS[-1][0] if best is None else best[1]


def grid_frame(index, box, step):
    """Сетка участка box в метрах UTM зоны с шагом step, кратная шагу:
    (x0, y0 - левый верхний угол, столбцов, строк)."""
    west, south, east, north = box
    xs, ys = index.project(np.array([west, east, west, east]),
                           np.array([south, south, north, north]))
    x0 = math.floor(xs.min() / step) * step
    y0 = math.ceil(ys.max() / step) * step
    return (x0, y0, int(math.ceil((xs.max() - x0) / step)),
            int(math.ceil((y0 - ys.min()) / step)))


def vectors(open_cog, index, box, level, year, progress=None):
    """Векторы года на участке box: (x0, y0 - левый верхний угол, шаг м,
    Int8 (каналы, строки с севера, столбцы)) или None. Сетка - как
    у mosaic, вне файлов - NODATA. progress(готово, всего) зовётся
    после каждого блока."""
    pieces = []
    parts = detail_parts(index, box, level)
    for done, (cell, col, row) in enumerate(parts):
        if progress is not None:
            progress(done, len(parts))
        name = index.name(cell, year)
        cog = open_cog(year, index.zone, name) if name else None
        if cog is None:
            continue
        tile = cog.band_tile(level, col, row)
        if tile is None:
            continue
        image = cog.images[level]
        x0, dx, _, y0, _, dy = cog.transform
        dx, dy = dx * image.scale, dy * image.scale
        pieces.append((x0 + col * image.tile_w * dx,
                       y0 + row * image.tile_h * dy, (dx, dy), tile))
    if not pieces:
        return None
    step = abs(pieces[0][2][0])
    x0, y1, width, height = grid_frame(index, box, step)
    bands = pieces[0][3].shape[0]
    out = np.full((bands, height, width), NODATA, dtype=np.int8)
    cx = x0 + (np.arange(width) + 0.5) * step
    cy = y1 - (np.arange(height) + 0.5) * step
    for px, py, (sx, sy), data in pieces:
        c = np.floor((cx - px) / sx).astype(int)
        r = np.floor((cy - py) / sy).astype(int)
        okc = (c >= 0) & (c < data.shape[2])
        okr = (r >= 0) & (r < data.shape[1])
        if not okc.any() or not okr.any():
            continue
        block = data[:, r[okr]][:, :, c[okc]]
        target = out[:, okr][:, :, okc]
        use = block[0] != NODATA
        target[:, use] = block[:, use]
        out[np.ix_(np.arange(bands), okr, okc)] = target
    return x0, y1, step, out


def unit(raw):
    """Векторы Int8 (64, n) в единичные float32 (n, 64), NaN без
    данных."""
    values = LUT[raw.astype(np.int16) + 128].T
    norm = np.linalg.norm(values, axis=1, keepdims=True)
    with np.errstate(invalid="ignore", divide="ignore"):
        return values / norm


def classify(grid, samples, labels, k=KNN):
    """Классы клеток участка по контрольным точкам: grid - Int8
    (64, строки, столбцы), samples - Int8 (64, точек), labels - номера
    классов точек. Ближайшие k точек по косинусу голосуют сходством.
    Итог - (классы int16, -1 без данных, сходство с лучшей точкой
    float32)."""
    labels = np.asarray(labels)
    train = unit(samples)
    good = np.isfinite(train).all(axis=1)
    train, labels = train[good], labels[good]
    shape = grid.shape[1:]
    out = np.full(shape[0] * shape[1], -1, dtype=np.int16)
    score = np.full(out.shape, np.nan, dtype=np.float32)
    if not len(train):
        return out.reshape(shape), score.reshape(shape)
    k = max(1, min(k, len(train)))
    classes = np.unique(labels)
    flat = grid.reshape(grid.shape[0], -1)
    step = CHUNK * 1024
    for start in range(0, flat.shape[1], step):
        values = unit(flat[:, start:start + step])
        ok = np.isfinite(values).all(axis=1)
        if not ok.any():
            continue
        sim = values[ok] @ train.T
        near = np.argsort(-sim, axis=1)[:, :k]
        weight = np.take_along_axis(sim, near, axis=1)
        votes = np.zeros((len(near), len(classes)), dtype=np.float32)
        for n, cls in enumerate(classes):
            votes[:, n] = np.where(labels[near] == cls,
                                   np.maximum(weight, 0.0) + 1e-6,
                                   0.0).sum(axis=1)
        part = np.full(len(values), -1, dtype=np.int16)
        part[ok] = classes[np.argmax(votes, axis=1)]
        best = np.full(len(values), np.nan, dtype=np.float32)
        best[ok] = sim.max(axis=1)
        out[start:start + len(values)] = part
        score[start:start + len(values)] = best
    return out.reshape(shape), score.reshape(shape)


def pixel_of(index, x0, y0, step, lat, lon):
    """Строка и столбец сетки участка для точки, вне сетки - за её
    пределами, проверяет вызывающий."""
    xs, ys = index.project(np.array([lon]), np.array([lat]))
    col = int(math.floor((xs[0] - x0) / step))
    row = int(math.floor((y0 - ys[0]) / step))
    return row, col


def hot_spots(values, count=10, spacing=10, low=0.3):
    """Места сильных изменений: до count (строка, столбец, степень)
    по сглаженной окном 3 × 3 степени, не ближе spacing пикселей друг
    к другу и не слабее low."""
    data = np.nan_to_num(values, nan=0.0)
    pad = np.pad(data, 1, mode="edge")
    smooth = sum(pad[1 + dy:1 + dy + data.shape[0],
                     1 + dx:1 + dx + data.shape[1]]
                 for dy in (-1, 0, 1) for dx in (-1, 0, 1)) / 9.0
    out = []
    while len(out) < count:
        flat = int(np.argmax(smooth))
        row, col = divmod(flat, smooth.shape[1])
        value = float(smooth[row, col])
        if value < low:
            break
        out.append((row, col, value))
        smooth[max(0, row - spacing):row + spacing + 1,
               max(0, col - spacing):col + spacing + 1] = 0.0
    return out


def detail_megabytes(parts, level):
    """Оценка загрузки подробного участка, МБ: два года на блок, у блока
    64 плоскости около BLOCK_MB мегабайт."""
    return 2 * len(parts) * BLOCK_MB[min(level, len(BLOCK_MB) - 1)]


def square_ring(lat, lon, side):
    """Вершины квадрата side метров с серединой в точке, (широта,
    долгота) против часовой стрелки с юго-запада."""
    west, south, east, north = square(lat, lon, side)
    return [(south, west), (south, east), (north, east), (north, west)]


def ring_box(points):
    """Рамка многоугольника (широта, долгота) в градусах и его наибольший
    размер в метрах: ((запад, юг, восток, север), сторона)."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    south, north = min(lats), max(lats)
    west, east = min(lons), max(lons)
    middle = math.radians((south + north) / 2.0)
    side = max((north - south) * 111320.0,
               (east - west) * 111320.0 * math.cos(middle))
    return (west, south, east, north), side


def ring_mask(index, x0, y0, step, shape, points):
    """Клетки сетки участка (строки с севера) внутри многоугольника
    points (широта, долгота), правило чётности по серединам клеток."""
    xs, ys = index.project(np.array([p[1] for p in points]),
                           np.array([p[0] for p in points]))
    rows, cols = shape
    cx = x0 + (np.arange(cols) + 0.5) * step
    cy = y0 - (np.arange(rows) + 0.5) * step
    mask = np.zeros(shape, dtype=bool)
    x1, y1 = np.asarray(xs, float), np.asarray(ys, float)
    x2, y2 = np.roll(x1, -1), np.roll(y1, -1)
    for r, y in enumerate(cy):
        cross = (y1 > y) != (y2 > y)
        if not cross.any():
            continue
        xa, ya, xb, yb = x1[cross], y1[cross], x2[cross], y2[cross]
        at = np.sort(xa + (y - ya) * (xb - xa) / (yb - ya))
        # Клетка внутри, если левее неё нечётное количество пересечений.
        mask[r] = np.searchsorted(at, cx) % 2 == 1
    return mask


def square(lat, lon, side):
    """Рамка квадрата side метров с серединой в точке, градусы."""
    half_lat = side / 2.0 / 111320.0
    half_lon = half_lat / max(math.cos(math.radians(lat)), 0.01)
    return (lon - half_lon, lat - half_lat, lon + half_lon, lat + half_lat)
