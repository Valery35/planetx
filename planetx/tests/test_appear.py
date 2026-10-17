# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проявление картинок слоя по тайлам вида."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import appear  # noqa: E402

TILE = (8, 100, 60)


class TestAppear(unittest.TestCase):
    def test_finer_picture_starts_at_old_resolution(self):
        a = appear.Appear()
        a.step([TILE], [6], 0.0)
        bias, hide = a.step([TILE], [8], 1.0)[0]
        self.assertAlmostEqual(bias, 2 + appear.EXTRA)
        self.assertEqual(hide, 0.0)
        self.assertTrue(a.busy())
        mid = a.step([TILE], [8], 1.0 + appear.DURATION / 2)[0]
        self.assertTrue(0.0 < mid[0] < bias)
        self.assertEqual(a.step([TILE], [8], 1.0 + appear.DURATION)[0],
                         appear.STILL)
        self.assertFalse(a.busy())

    def test_tile_without_picture_appears_from_transparency(self):
        a = appear.Appear()
        a.step([TILE], [None], 0.0)
        self.assertEqual(a.step([TILE], [8], 1.0)[0], (0.0, 1.0))
        bias, hide = a.step([TILE], [8], 1.0 + appear.DURATION / 2)[0]
        self.assertEqual(bias, 0.0)
        self.assertAlmostEqual(hide, 0.5)

    def test_new_child_takes_level_of_drawn_parent(self):
        a = appear.Appear()
        parent = (7, 50, 30)
        a.step([parent], [5], 0.0)
        child = (8, 100, 61)
        bias, _ = a.step([child], [8], 1.0)[0]
        self.assertAlmostEqual(bias, 3 + appear.EXTRA)

    def test_coarser_or_first_frame_is_still(self):
        a = appear.Appear()
        self.assertEqual(a.step([TILE], [8], 0.0)[0], appear.STILL)
        self.assertEqual(a.step([TILE], [6], 1.0)[0], appear.STILL)

    def test_disabled_is_sharp(self):
        a = appear.Appear()
        a.step([TILE], [None], 0.0)
        self.assertEqual(a.step([TILE], [8], 1.0, enabled=False)[0],
                         appear.STILL)

    def test_curve_ends(self):
        self.assertEqual(appear.curve(0.0), 1.0)
        self.assertEqual(appear.curve(1.0), 0.0)
        self.assertAlmostEqual(appear.curve(0.5), 0.5)


if __name__ == "__main__":
    unittest.main()
