# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Непрозрачность выделенных меток ползунком."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import opacity  # noqa: E402


class TestOpacity(unittest.TestCase):
    def test_selection_is_most_opaque(self):
        self.assertAlmostEqual(opacity.selection_opacity(
            [[(255, 0, 0, 51), (255, 0, 0, 25)], [(0, 0, 0, 102), None]]),
            0.4)
        self.assertEqual(opacity.selection_opacity([]), 1.0)

    def test_scaling_keeps_fill_share(self):
        line, fill = opacity.scaled([(10, 20, 30, 200), (1, 2, 3, 100)],
                                    1.0 * 200 / 255, 0.5 * 200 / 255)
        self.assertEqual(line, (10, 20, 30, 100))
        self.assertEqual(fill, (1, 2, 3, 50))

    def test_back_to_start_is_exact(self):
        colors = [(10, 20, 30, 137), (1, 2, 3, 61)]
        base = opacity.opacity_of(colors)
        down = opacity.scaled(colors, base, 0.1)
        self.assertNotEqual(down, colors)
        # Ползунок считает от цветов при выделении, а не от уже
        # уменьшенных, поэтому возврат точный.
        self.assertEqual(opacity.scaled(colors, base, base), colors)

    def test_from_transparent(self):
        line, fill, none = opacity.scaled(
            [(1, 1, 1, 0), (2, 2, 2, 0), None], 0.0, 0.8)
        self.assertEqual(line[3], 204)
        self.assertEqual(fill[3], 102)
        self.assertIsNone(none)

    def test_clipped(self):
        line, = opacity.scaled([(0, 0, 0, 200)], 0.5, 1.0)
        self.assertEqual(line[3], 255)


if __name__ == "__main__":
    unittest.main()
