# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Трассировка: цвета, слияние мелких областей, общие цепочки границ,
сглаживание Potrace, кольца без щелей."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import tracing as trace  # noqa: E402


def picture():
    """Сетка 60 × 80: фон, круг, квадрат с дырой и шум по пикселям."""
    rng = np.random.default_rng(5)
    grid = np.full((3, 60, 80), 200.0, dtype=np.float32)
    r, c = np.mgrid[0:60, 0:80]
    grid[:, (r - 30) ** 2 + (c - 20) ** 2 < 144] = 40.0
    grid[0, 10:50, 45:75] = 120.0
    grid[1, 10:50, 45:75] = 30.0
    grid[2, 10:50, 45:75] = 30.0
    grid[:, 25:35, 55:65] = 200.0
    grid += rng.normal(0.0, 6.0, grid.shape).astype(np.float32)
    return grid


def total_area(shapes):
    area = 0.0
    for outer, holes in shapes.values():
        area += abs(trace.ring_area(outer))
        area -= sum(abs(trace.ring_area(hole)) for hole in holes)
    return area


class TestColors(unittest.TestCase):
    def test_three_colors_found(self):
        grid = picture()
        good = np.ones(grid.shape[1:], dtype=bool)
        classes, centers = trace.quantize(trace.blur(grid, good), good, 3)
        self.assertEqual(len(centers), 3)
        self.assertEqual(len(np.unique(classes[good])), 3)
        # Центр круга и угол фона - разные цвета, дыра квадрата - фон.
        self.assertNotEqual(classes[30, 20], classes[2, 2])
        self.assertEqual(classes[30, 60], classes[2, 2])

    def test_outside_cells_stay_empty(self):
        grid = picture()
        good = np.ones(grid.shape[1:], dtype=bool)
        good[:, :10] = False
        classes, _ = trace.quantize(grid, good, 3)
        self.assertTrue((classes[:, :10] == -1).all())

    def test_ranked_colors_by_share(self):
        # Источник «Цвета снимка» окна «Распознавание»: цвет 0 - фон,
        # самый крупный, средние каналов - в том же порядке.
        grid = picture()
        good = np.ones(grid.shape[1:], dtype=bool)
        good[:, :5] = False
        cells, centers = trace.ranked_colors(grid, good, 3)
        self.assertTrue((cells[:, :5] == -1).all())
        sizes = [int((cells == n).sum()) for n in range(len(centers))]
        self.assertEqual(sizes, sorted(sizes, reverse=True))
        self.assertEqual(cells[2, 10], 0)
        self.assertGreater(centers[0, 0], 150.0)
        self.assertLess(centers[cells[30, 20], 0], 80.0)

    def test_class_shapes_cover_classes(self):
        # Многоугольники классов окна «Распознавание»: пятно меньше least
        # уходит соседу, площади колец - все клетки участка.
        classes = np.full((30, 40), -1, dtype=np.int64)
        classes[:, :20] = 0
        classes[:, 20:] = 1
        classes[5, 5] = 1
        found = trace.class_shapes(classes, least=5)
        kinds = list(found["kinds"])
        self.assertEqual(sorted(kinds), [0, 1])
        total = sum(abs(trace.ring_area(outer))
                    - sum(abs(trace.ring_area(h)) for h in holes)
                    for outer, holes in found["shapes"].values())
        self.assertAlmostEqual(total, 30 * 40, delta=30 * 40 * 0.02)
        self.assertEqual(classes[5, 5], 1)  # растр классов прежний


class TestMerge(unittest.TestCase):
    def test_small_spots_join_neighbour(self):
        colors = np.zeros((20, 20), dtype=np.int32)
        colors[5, 5] = 1
        colors[10:12, 10:12] = 1
        colors[14:20, 0:20] = 2
        parts, kinds, out = trace.merge_small(colors, least=10)
        self.assertEqual(out[5, 5], 0)
        self.assertEqual(out[10, 10], 0)
        self.assertEqual(len(kinds), 2)
        self.assertEqual(sorted(kinds.tolist()), [0, 2])


class TestChains(unittest.TestCase):
    def test_square_in_field_is_closed_chain(self):
        parts = np.zeros((10, 10), dtype=np.int32)
        parts[3:6, 3:6] = 1
        found = trace.chains(parts)
        inner = [c for c in found if 1 in (c[1], c[2]) and 0 in (c[1], c[2])]
        self.assertEqual(len(inner), 1)
        self.assertTrue(inner[0][3])
        self.assertEqual(len(inner[0][0]) - 1, 12)

    def test_left_side_is_region_on_screen_left(self):
        # Отвесная граница: слева на экране (запад) область 0, справа 1.
        parts = np.array([[0, 1], [0, 1]], dtype=np.int32)
        found = trace.chains(parts)
        middle = [c for c in found if {c[1], c[2]} == {0, 1}][0]
        xy = middle[0]
        going_down = xy[-1][1] > xy[0][1]
        self.assertEqual(middle[1], 1 if going_down else 0)


class TestSmooth(unittest.TestCase):
    def test_staircase_becomes_straight(self):
        steps = [(0, 0)]
        for k in range(10):
            steps += [(k + 1, k), (k + 1, k + 1)]
        line = trace.simplify(steps)
        self.assertEqual(len(line), 2)

    def test_long_right_angle_stays_corner(self):
        self.assertGreaterEqual(trace.corner_alpha((0, 0), (20, 0), (20, 20)),
                                trace.CORNER)
        self.assertLess(trace.corner_alpha((0, 0), (3, 0), (3, 3)),
                        trace.CORNER)

    def test_open_chain_keeps_ends(self):
        pts = [(0, 0), (5, 0), (5, 5), (10, 5)]
        out = trace.smooth_chain(pts)
        self.assertEqual(out[0], (0.0, 0.0))
        self.assertEqual(out[-1], (10.0, 5.0))


class TestRings(unittest.TestCase):
    def test_regions_tile_the_site_without_gaps(self):
        grid = picture()
        good = np.ones(grid.shape[1:], dtype=bool)
        out = trace.trace(grid, good, colors=3, least=10)
        self.assertEqual(len(out["shapes"]), len(out["kinds"]))
        # Общие цепочки: сумма площадей областей - весь участок.
        self.assertAlmostEqual(total_area(out["shapes"]), 60 * 80, delta=1.0)

    def test_square_has_hole(self):
        grid = picture()
        good = np.ones(grid.shape[1:], dtype=bool)
        out = trace.trace(grid, good, colors=3, least=10)
        square = out["parts"][15, 60]
        outer, holes = out["shapes"][int(square)]
        self.assertEqual(len(holes), 1)
        self.assertAlmostEqual(abs(trace.ring_area(holes[0])), 100, delta=8)

    def test_area_outside_site_is_not_traced(self):
        grid = picture()
        good = np.zeros(grid.shape[1:], dtype=bool)
        good[5:55, 5:75] = True
        out = trace.trace(grid, good, colors=3, least=10)
        self.assertAlmostEqual(total_area(out["shapes"]), 50 * 70, delta=1.0)


class TestDisplay(unittest.TestCase):
    def test_byte_colors_as_is(self):
        self.assertEqual(trace.display_colors([[10, 20, 30], [200, 0, 5]]),
                         [(10, 20, 30), (200, 0, 5)])

    def test_reflectance_stretched(self):
        out = trace.display_colors([[0.1], [0.3]])
        self.assertEqual(out, [(0, 0, 0), (255, 255, 255)])


class TestJoin(unittest.TestCase):
    def test_untouched_colors_stay(self):
        lookup, keep = trace.join_colors([-1, -1, -1])
        self.assertEqual(list(lookup), [0, 1, 2])
        self.assertEqual(keep, [0, 1, 2])

    def test_chain_goes_to_free_color(self):
        # 0 слит с 2, 2 - с 3: оба уходят в 3.
        lookup, keep = trace.join_colors([2, -1, 3, -1])
        self.assertEqual(keep, [1, 3])
        self.assertEqual(list(lookup), [1, 0, 1, 1])

    def test_circle_is_one_class(self):
        lookup, keep = trace.join_colors([1, 2, 0, -1])
        self.assertEqual(keep, [0, 3])
        self.assertEqual(list(lookup), [0, 0, 0, 1])

    def test_cells_and_regions_follow(self):
        lookup, _ = trace.join_colors([-1, 0, -1])
        classes, kinds = trace.joined([[0, 1], [2, -1]], [1, 2, 0], lookup)
        self.assertEqual(classes.tolist(), [[0, 0], [1, -1]])
        self.assertEqual(kinds.tolist(), [0, 1, 0])


if __name__ == "__main__":
    unittest.main()
