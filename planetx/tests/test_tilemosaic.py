# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Мозаика тайлов подложки под участком."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import basemap  # noqa: E402
import tilemosaic as tm  # noqa: E402


def tile(value):
    out = np.zeros((tm.SIZE, tm.SIZE, 4), dtype=np.uint8)
    out[:, :, 0] = value
    out[:, :, 1] = np.arange(tm.SIZE)[None, :]
    out[:, :, 2] = np.arange(tm.SIZE)[:, None]
    out[:, :, 3] = 255
    return out


def stub():
    out = np.full((tm.SIZE, tm.SIZE, 4), 204, dtype=np.uint8)
    out[:, :, 3] = 255
    return out


class TestLevel(unittest.TestCase):
    def test_level_gives_pixel_not_coarser_than_step(self):
        for lat in (0.0, 58.0, 75.0):
            for pixel in (0.5, 3.0, 40.0, 800.0):
                z = tm.level_for(lat, pixel, 19)
                self.assertLessEqual(tm.tile_pixel(lat, z), pixel)
                self.assertGreater(tm.tile_pixel(lat, z - 1), pixel)

    def test_level_stops_at_top_of_source(self):
        self.assertEqual(tm.level_for(58.0, 0.01, 16), 16)


class TestSpan(unittest.TestCase):
    def test_box_lies_inside_its_tiles(self):
        box = (56.2, 58.0, 56.3, 58.05)
        z = 14
        first, last, top, bottom = tm.span(box, z)
        west = basemap.tile_bbox(z, first, top)
        east = basemap.tile_bbox(z, last, bottom)
        half = basemap.MERCATOR_HALF
        self.assertLessEqual(west[0], box[0] / 180.0 * half)
        self.assertGreaterEqual(east[2], box[2] / 180.0 * half)
        self.assertEqual(tm.tile_count((first, last, top, bottom)),
                         len(tm.tile_keys(z, (first, last, top, bottom))))

    def test_geotransform_starts_at_tile_corner(self):
        west, pixel, _, north, _, down = tm.geotransform(3, (2, 3, 1, 2))
        box = basemap.tile_bbox(3, 2, 1)
        self.assertAlmostEqual(west, box[0])
        self.assertAlmostEqual(north, box[3])
        self.assertAlmostEqual(pixel * tm.SIZE, box[2] - box[0])
        self.assertAlmostEqual(down, -pixel)


class TestGather(unittest.TestCase):
    def test_placeholder_and_missing_take_ancestor_part(self):
        # Заглушка и пропажа дают долю предка, а не серый квадрат.
        calls = []

        def read(keys):
            calls.append(keys)
            return {key: tile(1 if key[0] == 15 else 7) if key[1] & 1
                    else (stub() if key[0] == 15 else None)
                    for key in keys}

        keys = [(15, 100, 200), (15, 101, 200), (15, 102, 200)]
        found = tm.gather(keys, read)
        self.assertEqual(sorted(found), keys)
        self.assertEqual(int(found[(15, 101, 200)][0, 0, 0]), 1)
        self.assertEqual(calls[1], [(14, 50, 100), (14, 51, 100)])

    def test_crop_takes_own_quarter_of_ancestor(self):
        parent = tile(5)
        right = tm.crop(parent, (11, 3, 2), 1)
        self.assertEqual(right.shape, parent.shape)
        self.assertEqual(int(right[0, 0, 1]), 128)
        self.assertEqual(int(right[0, 2, 1]), 129)
        self.assertEqual(int(right[0, 0, 2]), 0)

    def test_nothing_found_leaves_tile_out(self):
        found = tm.gather([(4, 3, 3)], lambda keys: {})
        self.assertEqual(found, {})

    def test_transparent_tile_is_kept_as_empty(self):
        empty = np.zeros((tm.SIZE, tm.SIZE, 4), dtype=np.uint8)
        found = tm.gather([(4, 3, 3)], lambda keys: {keys[0]: empty})
        self.assertIn((4, 3, 3), found)


class TestAssemble(unittest.TestCase):
    def test_tile_lands_at_its_place(self):
        frame = (10, 11, 20, 20)
        out = tm.assemble(5, frame, {(5, 11, 20): tile(9)})
        self.assertEqual(out.shape, (tm.SIZE, 2 * tm.SIZE, 4))
        self.assertEqual(int(out[0, tm.SIZE, 0]), 9)
        self.assertEqual(int(out[0, 0, 3]), 0)


if __name__ == "__main__":
    unittest.main()
