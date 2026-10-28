# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Изменения местности по эмбеддингам AlphaEarth (core/aef.py)
и чтение каналов COG (core/cog.py)."""
import json
import math
import os
import struct
import sys
import unittest
import zlib

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import aef  # noqa: E402
import cog  # noqa: E402
from coords import from_utm  # noqa: E402

ZONE = "40N"
WEST, NORTH = 409600.0, 6471680.0  # квадрат у Перми


def vector(value, bands=4):
    """Квантованный вектор Int8 вдоль первой оси: все каналы value."""
    return np.full(bands, value, dtype=np.int8)


class FakeImage:
    def __init__(self, scale):
        self.scale = scale
        self.tile_w = self.tile_h = aef.TILE


class FakeCog:
    """Файл квадрата: строки с юга, как у AlphaEarth. changed(x, y) -
    в каких точках UTM второй год другой."""

    def __init__(self, changed, second):
        self.transform = (WEST, 10.0, 0.0, NORTH - aef.CELL, 0.0, 10.0)
        self.images = [FakeImage(1 << k) for k in range(14)]
        self.changed = changed
        self.second = second

    def band_tile(self, level, col, row):
        scale = 1 << level
        side = min(aef.TILE, aef.FILE_SIDE // scale)
        step = 10.0 * scale
        x = WEST + (col * aef.TILE + np.arange(side) + 0.5) * step
        y = NORTH - aef.CELL + (row * aef.TILE + np.arange(side) + 0.5) \
            * step
        xx, yy = np.meshgrid(x, y)
        tile = np.empty((4, side, side), dtype=np.int8)
        tile[:] = 90
        if self.second:
            # Другой вектор: два канала со знаком минус.
            mask = self.changed(xx, yy)
            tile[2:, mask] = -90
        return tile


def make_index():
    doc = {"zone": ZONE, "cell": aef.CELL,
           "cells": [[WEST, NORTH, {"2017": "a:0:0", "2025": "b:0:0"}]]}
    return aef.ZoneIndex.parse(json.dumps(doc).encode())


def north_block(x, y):
    """Изменения - северная четверть квадрата."""
    return y > NORTH - aef.CELL / 4


class TestBasics(unittest.TestCase):

    def test_file_url(self):
        self.assertEqual(
            aef.file_url(2019, "1S", "x8qq:1:0"),
            aef.BASE + "2019/1S/x8qq-0000008192-0000000000.tiff")

    def test_build_index_groups_years_by_cell(self):
        rows = [("gs://b/annual/2017/40N/img1-0000008192-0000000000.tiff",
                 2017, "40N", 409600.0, 6471680.0),
                ("gs://b/annual/2025/40N/img2-0000008192-0000000000.tiff",
                 2025, "40N", 409600.0, 6471680.0)]
        doc = aef.build_index(rows)["40N"]
        self.assertEqual(doc["cells"], [[409600, 6471680, {
            "2017": "img1:1:0", "2025": "img2:1:0"}]])

    def test_zone_of(self):
        self.assertEqual(aef.zone_of(56.25, 58.0), "40N")
        self.assertEqual(aef.zone_of(-123.0, -45.0), "10S")
        self.assertEqual(aef.zone_of(180.0, 10.0), "60N")

    def test_change_of_vectors(self):
        a = np.stack([vector(90), vector(90), vector(-128)], axis=1)
        b = np.stack([vector(90), -vector(90), vector(90)], axis=1)
        out = aef.change(a, b)
        self.assertAlmostEqual(float(out[0]), 0.0, places=5)
        # Противоположные векторы - несходство 2, шкала обрезает до 1.
        self.assertAlmostEqual(float(out[1]), 1.0, places=5)
        self.assertTrue(math.isnan(out[2]))

    def test_dequantize_like_google(self):
        for v in (-127, -40, 0, 1, 127):
            self.assertAlmostEqual(
                float(aef.LUT[v + 128]),
                ((v / 127.5) ** 2) * np.sign(v), places=6)
        self.assertTrue(math.isnan(aef.LUT[0]))

    def test_bytes_round_trip(self):
        values = np.array([0.0, 0.5, 1.0, np.nan], dtype=np.float32)
        back = aef.from_bytes(aef.to_bytes(values))
        self.assertTrue(np.allclose(back[:3], values[:3], atol=0.003))
        self.assertTrue(math.isnan(back[3]))

    def test_level_for(self):
        self.assertEqual(aef.level_for(10.0), aef.PREVIEW_LEVEL)
        self.assertEqual(aef.level_for(320.0), 6)  # 640 м
        self.assertEqual(aef.level_for(1e9), 13)

    def test_colors_hide_outside_span(self):
        values = np.array([[0.1, 0.5, np.nan]], dtype=np.float32)
        rgba = aef.colors(values, low=0.3, high=1.0)
        self.assertEqual(rgba[0, 0, 3], 0)
        self.assertGreater(rgba[0, 1, 3], 0)
        self.assertEqual(rgba[0, 2, 3], 0)


class TestPlacement(unittest.TestCase):
    """Изменение в северной четверти квадрата ложится на север. Файлы
    AlphaEarth хранят строки с юга: прежнее чтение сверху вниз давало
    пустой обзор, а у переворота - изменение на юге."""

    def setUp(self):
        index = make_index()
        cogs = {2017: FakeCog(north_block, False),
                2025: FakeCog(north_block, True)}
        self.changes = aef.Changes(2017, 2025,
                                   lambda year, zone, name: cogs[year])
        self.index = index

    def points(self, northing):
        lat, lon = from_utm(40, False, WEST + aef.CELL / 2, northing)
        return lat, lon

    def test_preview_tile_puts_change_north(self):
        lat_n, lon = self.points(NORTH - aef.CELL / 8)
        lat_s, _ = self.points(NORTH - aef.CELL * 7 / 8)
        z = 10
        n = 1 << z

        def tile_of(lat):
            x = int((lon + 180) / 360 * n)
            y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi)
                    / 2 * n)
            return x, y

        found = {}
        for name, lat in (("north", lat_n), ("south", lat_s)):
            x, y = tile_of(lat)
            values = aef.tile_values(self.changes, lambda zone: self.index
                                     if zone == ZONE else None, z, x, y)
            found[name] = float(np.nanmedian(values))
        self.assertGreater(found["north"], 0.4)
        self.assertLess(found["south"], 0.05)

    def test_deep_tile_outside_detail_is_empty(self):
        self.assertIsNone(aef.tile_values(
            self.changes, lambda zone: self.index, aef.PREVIEW_ZOOM + 1,
            0, 0))

    def test_mosaic_and_spots(self):
        lat, lon = self.points(NORTH - aef.CELL / 4)
        box = aef.square(lat, lon, 4000.0)
        x0, y0, step, values = aef.mosaic(self.changes, self.index, box,
                                          level=2)
        self.assertEqual(step, 40.0)
        rows = (y0 - (np.arange(values.shape[0]) + 0.5) * step)
        north = values[rows > NORTH - aef.CELL / 4 + 100]
        south = values[rows < NORTH - aef.CELL / 4 - 100]
        self.assertGreater(float(np.nanmedian(north)), 0.4)
        self.assertLess(float(np.nanmedian(south)), 0.05)
        spots = aef.hot_spots(values, count=3, spacing=5)
        self.assertTrue(spots)
        row = spots[0][0]
        self.assertGreater(y0 - (row + 0.5) * step, NORTH - aef.CELL / 4)

    def test_detail_parts_south_up(self):
        lat, lon = self.points(NORTH - 5000.0)
        parts = aef.detail_parts(self.index, aef.square(lat, lon, 1000.0))
        # Северный край квадрата - последняя строка блоков.
        self.assertEqual({row for _, _, row in parts}, {7})
        self.assertEqual(aef.detail_megabytes(parts, 0),
                         2 * len(parts) * aef.BLOCK_MB[0])

    def test_ring_mask_and_box(self):
        lat, lon = self.points(NORTH - aef.CELL / 2)
        ring = aef.square_ring(lat, lon, 1000.0)
        box, side = aef.ring_box(ring)
        self.assertAlmostEqual(side, 1000.0, delta=20.0)
        # Треугольник - половина квадрата под диагональю юго-запад -
        # северо-восток.
        triangle = [ring[0], ring[1], ring[2]]
        xs, ys = self.index.project(np.array([box[0], box[2]]),
                                    np.array([box[3], box[1]]))
        step = 10.0
        x0, y0 = float(xs[0]), float(ys[0])
        shape = (int(round((ys[0] - ys[1]) / step)),
                 int(round((xs[1] - xs[0]) / step)))
        whole = aef.ring_mask(self.index, x0, y0, step, shape, ring)
        half = aef.ring_mask(self.index, x0, y0, step, shape, triangle)
        self.assertGreater(whole.mean(), 0.95)
        self.assertAlmostEqual(half.mean(), 0.5, delta=0.05)
        # Юго-восточный угол сетки внутри, северо-западный - нет.
        self.assertTrue(half[-2, -2])
        self.assertFalse(half[1, 1])

    def test_auto_level_fits_blocks_and_cells(self):
        # Середина квадрата файла - угол блоков всех уровней мельче 80 м.
        lat, lon = self.points(NORTH - aef.CELL / 2)
        # Малый участок у угла блоков - всё равно 10 м, 80 м дали бы
        # 25 клеток поперёк.
        small = aef.square(lat, lon, 2000.0)
        self.assertEqual(aef.auto_level(self.index, small, 2000.0), 0)
        # 10 км с пикселем 10 м - миллион клеток, берётся крупнее.
        side = 10000.0
        box = aef.square(lat, lon, side)
        level = aef.auto_level(self.index, box, side)
        self.assertGreater(level, 0)
        pixel = dict(aef.DETAIL_LEVELS)[level]
        self.assertLessEqual((side / pixel) ** 2, aef.AUTO_CELLS)
        # У угла блоков меньше всего грузит 80 м - один блок.
        self.assertEqual(level, 3)
        self.assertEqual(len(aef.detail_parts(self.index, box, level)), 1)


class TestClassify(unittest.TestCase):
    """Классы участка по контрольным точкам: точки на севере и на юге
    делят участок по границе северной четверти квадрата."""

    def setUp(self):
        self.index = make_index()
        cog_ = FakeCog(north_block, True)
        self.open = lambda year, zone, name: cog_

    def test_classes_follow_control_points(self):
        edge = NORTH - aef.CELL / 4
        lat, lon = from_utm(40, False, WEST + aef.CELL / 2, edge)
        box = aef.square(lat, lon, 4000.0)
        x0, y0, step, grid = aef.vectors(self.open, self.index, box, 2,
                                         2025)
        self.assertEqual(step, 40.0)
        self.assertEqual(grid.shape[0], 4)
        rows = y0 - (np.arange(grid.shape[1]) + 0.5) * step
        # Другие векторы - на севере: строки сетки идут с севера.
        self.assertTrue((grid[2][rows > edge + 100] == -90).all())
        self.assertTrue((grid[2][rows < edge - 100] == 90).all())
        samples, labels = [], []
        for label, shift in ((0, -1500.0), (1, 1500.0)):
            for dx in (-500.0, 0.0, 500.0):
                plat, plon = from_utm(40, False, WEST + aef.CELL / 2 + dx,
                                      edge + shift)
                r, c = aef.pixel_of(self.index, x0, y0, step, plat, plon)
                samples.append(grid[:, r, c])
                labels.append(label)
        classes, score = aef.classify(grid, np.stack(samples, axis=1),
                                      labels)
        rows = y0 - (np.arange(classes.shape[0]) + 0.5) * step
        # Север - класс точек на севере, у переворота строк наоборот.
        self.assertTrue((classes[rows > edge + 100] == 1).all())
        self.assertTrue((classes[rows < edge - 100] == 0).all())
        self.assertGreater(float(np.nanmin(score)), 0.99)

    def test_cells_without_data_have_no_class(self):
        grid = np.full((4, 2, 2), 90, dtype=np.int8)
        grid[:, 0, 0] = aef.NODATA
        grid[2:, 1, 1] = -90
        samples = np.stack([vector(90), np.array([90, 90, -90, -90],
                                                 dtype=np.int8)], axis=1)
        classes, _ = aef.classify(grid, samples, [3, 7])
        self.assertEqual(classes.tolist(), [[-1, 3], [3, 7]])

    def test_unit_vectors(self):
        out = aef.unit(np.stack([vector(90), vector(aef.NODATA)], axis=1))
        self.assertAlmostEqual(float(np.linalg.norm(out[0])), 1.0, places=5)
        self.assertTrue(np.isnan(out[1]).all())


def band_tiff(width, height, tile, bands):
    """Маленький TIFF каналов Int8 плоскостями, DEFLATE, привязка
    ModelTransformation со строками с юга."""
    across = -(-width // tile)
    down = -(-height // tile)
    raws = []
    for band in range(bands):
        for r in range(down):
            for c in range(across):
                data = np.zeros((tile, tile), dtype=np.int8)
                part = np.full((height, width), band + 1, dtype=np.int8)
                part[0, 0] = -band - 1
                h = min(tile, height - r * tile)
                w = min(tile, width - c * tile)
                data[:h, :w] = part[r * tile:r * tile + h,
                                    c * tile:c * tile + w]
                raws.append(zlib.compress(data.tobytes()))
    matrix = (10.0, 0, 0, 500000.0, 0, 10.0, 0, 6000000.0,
              0, 0, 0, 0, 0, 0, 0, 1)
    entries = [(256, 3, [width]), (257, 3, [height]), (258, 3, [8] * bands),
               (259, 3, [8]), (277, 3, [bands]), (284, 3, [2]),
               (322, 3, [tile]), (323, 3, [tile]), (339, 3, [2] * bands)]
    # Данные - после каталога: длины тегов известны заранее.
    head = 8
    count = len(entries) + 3
    after = head + 2 + 12 * count + 4
    blobs = b""
    values = {}
    for tag, kind, data in entries:
        if len(data) * 2 > 4:
            values[tag] = after + len(blobs)
            blobs += struct.pack("<%dH" % len(data), *data)
    mat_at = after + len(blobs)
    blobs += struct.pack("<16d", *matrix)
    off_at = after + len(blobs)
    blobs += b"\0" * 4 * len(raws)
    cnt_at = after + len(blobs)
    blobs += struct.pack("<%dI" % len(raws), *[len(r) for r in raws])
    data_at = after + len(blobs)
    offsets = []
    at = data_at
    for raw in raws:
        offsets.append(at)
        at += len(raw)
    blobs = blobs[:off_at - after] + struct.pack(
        "<%dI" % len(raws), *offsets) + blobs[off_at - after + 4 * len(raws):]
    out = bytearray(b"II*\0" + struct.pack("<I", head))
    out += struct.pack("<H", count)
    tags = [(tag, kind, data) for tag, kind, data in entries]
    for tag, kind, data in sorted(tags + [
            (324, 4, None), (325, 4, None), (34264, 12, None)]):
        if tag == 324:
            out += struct.pack("<HHII", 324, 4, len(raws), off_at)
        elif tag == 325:
            out += struct.pack("<HHII", 325, 4, len(raws), cnt_at)
        elif tag == 34264:
            out += struct.pack("<HHII", 34264, 12, 16, mat_at)
        elif tag in values:
            out += struct.pack("<HHII", tag, kind, len(data), values[tag])
        else:
            out += struct.pack("<HHI", tag, kind, len(data)) \
                + struct.pack("<H", data[0]) + b"\0\0"
    out += struct.pack("<I", 0)
    return bytes(out) + blobs + b"".join(raws)


class TestBandCog(unittest.TestCase):

    def setUp(self):
        blob = band_tiff(20, 12, 16, 3)
        self.cog = cog.Cog(lambda start, length: blob[start:start + length])

    def test_bands_mode_and_south_up_transform(self):
        image = self.cog.images[0]
        self.assertTrue(image.bands)
        self.assertEqual(image.dtype, np.int8)
        self.assertEqual(self.cog.transform,
                         (500000.0, 10.0, 0.0, 6000000.0, 0.0, 10.0))

    def test_band_tile_is_cut_to_image(self):
        tile = self.cog.band_tile(0, 1, 0)
        # Тайл 16 × 16 справа обрезан до 4 столбцов изображения.
        self.assertEqual(tile.shape, (3, 12, 4))
        self.assertEqual(int(tile[2, 0, 0]), 3)
        first = self.cog.band_tile(0, 0, 0)
        self.assertEqual([int(first[b, 0, 0]) for b in range(3)],
                         [-1, -2, -3])

    def test_band_pixels(self):
        xs = np.array([500005.0, 500195.0, 400000.0])
        ys = np.array([6000005.0, 6000115.0, 6000005.0])
        values, inside = self.cog.band_pixels(xs, ys, 0)
        self.assertEqual(inside.tolist(), [True, True, False])
        self.assertEqual(values[:, 0].tolist(), [-1, -2, -3])
        self.assertEqual(values[:, 1].tolist(), [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
