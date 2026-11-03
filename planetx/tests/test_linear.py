# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты линейных объектов (core/linear.py)."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import linear  # noqa: E402


def total(paths):
    return sum(linear.length_m(p, 1.0) for p in paths)


class TestThin(unittest.TestCase):
    def test_strip_is_thin_field_is_not(self):
        mask = np.zeros((80, 120), dtype=bool)
        mask[10:13, 5:115] = True      # дорога в 3 клетки
        mask[30:75, 20:70] = True      # поле
        part = linear.thin(mask, 3)
        self.assertTrue(part[11, 60])
        self.assertFalse(part[50, 45])


class TestLines(unittest.TestCase):
    def test_road_becomes_one_line(self):
        mask = np.zeros((40, 120), dtype=bool)
        mask[10:13, 5:115] = True
        found = linear.lines(mask, 3, 20)
        self.assertEqual(len(found), 1)
        self.assertGreater(total(found), 95)
        ys = [y for _, y in found[0]]
        self.assertTrue(all(10.0 <= y <= 13.0 for y in ys))

    def test_field_gives_no_line(self):
        mask = np.zeros((80, 80), dtype=bool)
        mask[10:70, 10:70] = True
        self.assertEqual(linear.lines(mask, 3, 20), [])

    def test_short_piece_dropped(self):
        mask = np.zeros((40, 40), dtype=bool)
        mask[10:12, 5:15] = True
        self.assertEqual(linear.lines(mask, 3, 20), [])

    def test_crossing_roads_one_group(self):
        mask = np.zeros((101, 101), dtype=bool)
        mask[49:52, 5:96] = True
        mask[5:96, 49:52] = True
        found = linear.lines(mask, 3, 20)
        self.assertGreaterEqual(len(found), 4)
        self.assertGreater(total(found), 170)

    def test_road_into_field_keeps_road(self):
        mask = np.zeros((80, 160), dtype=bool)
        mask[20:60, 0:40] = True        # поле
        mask[39:42, 40:150] = True       # дорога от поля
        found = linear.lines(mask, 3, 20)
        self.assertGreater(total(found), 95)
        xs = [x for p in found for x, _ in p]
        self.assertGreater(max(xs), 140)


class TestSkeleton(unittest.TestCase):
    def test_one_cell_wide(self):
        mask = np.zeros((20, 40), dtype=bool)
        mask[5:10, 3:37] = True
        skel = linear.skeleton(mask)
        self.assertTrue(skel.any())
        self.assertLessEqual(skel[:, 20].sum(), 1)


if __name__ == "__main__":
    unittest.main()
