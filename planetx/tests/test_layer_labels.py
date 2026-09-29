# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подписи слоёв проекта: окно запроса, ключ, кегль, номера, цвет."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import layer_labels as ll  # noqa: E402


class TestWindow(unittest.TestCase):

    def test_window_around_view(self):
        west, south, east, north = ll.window(58.0, 56.2, 20000.0)
        self.assertLess(west, 56.2)
        self.assertGreater(east, 56.2)
        self.assertAlmostEqual(north - 58.0, 58.0 - south, places=9)
        self.assertLess(north - south, 1.0)

    def test_wide_view_is_whole_globe(self):
        self.assertEqual(ll.window(20.0, 60.0, 2.0e7),
                         (-180.0, -90.0, 180.0, 90.0))

    def test_key_changes_with_move_and_zoom(self):
        k = ll.key(58.0, 56.2, 20000.0)
        self.assertEqual(k, ll.key(58.0005, 56.2005, 20000.0))
        self.assertNotEqual(k, ll.key(58.3, 56.2, 20000.0))
        self.assertNotEqual(k, ll.key(58.0, 56.2, 80000.0))


class TestNearest(unittest.TestCase):

    def test_keeps_nearest_to_view(self):
        items = [(n, "t", 58.0 + n * 0.01, 56.0, None) for n in range(10)]
        kept = ll.nearest(items, 58.05, 56.0, 3)
        self.assertEqual(sorted(i[0] for i in kept), [4, 5, 6])

    def test_across_date_line(self):
        items = [(0, "a", 0.0, 179.9, None), (1, "b", 0.0, 0.0, None)]
        self.assertEqual(ll.nearest(items, 0.0, -179.9, 1)[0][0], 0)


class TestLook(unittest.TestCase):

    def test_pixel_size(self):
        self.assertAlmostEqual(ll.pixel_size(10.0, "points"), 13.333,
                               places=3)
        self.assertEqual(ll.pixel_size(40.0, "points"), ll.SIZE_RANGE[1])
        self.assertEqual(ll.pixel_size(1.0, "mm"), ll.SIZE_RANGE[0])
        self.assertEqual(ll.pixel_size(12.0, "pixels"), 12.0)

    def test_ids_are_stable_and_negative(self):
        a = ll.label_id("layer_a", 5)
        self.assertEqual(a, ll.label_id("layer_a", 5))
        self.assertNotEqual(a, ll.label_id("layer_b", 5))
        self.assertLess(a, -10 ** 6)

    def test_dark_color(self):
        self.assertTrue(ll.dark((0, 0, 0)))
        self.assertFalse(ll.dark((255, 255, 255)))


if __name__ == "__main__":
    unittest.main()
