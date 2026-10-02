# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Правка вершин: что под курсором, вставка, замыкание, попадание."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import numpy as np  # noqa: E402

import editing as ed  # noqa: E402

SQUARE = np.array([[0.0, 0.0], [100.0, 0.0], [100.0, 100.0], [0.0, 100.0]])
FRONT = np.ones(4, dtype=bool)
MIDDLES = np.array([[50.0, 0.0], [100.0, 50.0], [50.0, 100.0], [0.0, 50.0]])


class TestPick(unittest.TestCase):

    def test_vertex(self):
        self.assertEqual(ed.pick(SQUARE, FRONT, MIDDLES, FRONT, 98.0, 3.0,
                                 8.0), (ed.VERTEX, 1))

    def test_middle(self):
        self.assertEqual(ed.pick(SQUARE, FRONT, MIDDLES, FRONT, 52.0, 99.0,
                                 8.0), (ed.MIDDLE, 2))

    def test_vertex_before_middle(self):
        # Короткий отрезок: вершина и середина обе в радиусе.
        vertices = np.array([[0.0, 0.0], [6.0, 0.0]])
        middles = np.array([[3.0, 0.0]])
        self.assertEqual(ed.pick(vertices, [True, True], middles, [True],
                                 4.0, 0.0, 8.0), (ed.VERTEX, 1))

    def test_nothing(self):
        self.assertIsNone(ed.pick(SQUARE, FRONT, MIDDLES, FRONT, 50.0, 50.0,
                                  8.0))

    def test_behind_camera_is_skipped(self):
        front = np.array([False, True, True, True])
        self.assertIsNone(ed.pick(SQUARE, front, np.zeros((0, 2)), [],
                                  1.0, 1.0, 8.0))

    def test_empty(self):
        self.assertIsNone(ed.pick(np.zeros((0, 2)), [], np.zeros((0, 2)),
                                  [], 1.0, 1.0, 8.0))


class TestVertices(unittest.TestCase):

    def test_insert_inside(self):
        points, alts = ed.inserted([(0, 0), (0, 2)], [None, None], 0,
                                   (0, 1))
        self.assertEqual(points, [(0, 0), (0, 1), (0, 2)])
        self.assertEqual(alts, [None, None, None])

    def test_insert_on_closing_segment(self):
        points, _ = ed.inserted([(0, 0), (0, 2), (2, 2)], [None] * 3, 2,
                                (1, 1))
        self.assertEqual(points, [(0, 0), (0, 2), (2, 2), (1, 1)])

    def test_remove(self):
        points, alts = ed.removed([(0, 0), (0, 1), (0, 2)], [1.0, 2.0, 3.0],
                                  1)
        self.assertEqual(points, [(0, 0), (0, 2)])
        self.assertEqual(alts, [1.0, 3.0])


class TestClick(unittest.TestCase):

    def test_first_vertex_closes(self):
        self.assertEqual(ed.click_result("path", 3, 0, False), ed.CLOSE)
        self.assertEqual(ed.click_result("polygon", 4, 0, False), ed.CLOSE)

    def test_two_points_do_not_close(self):
        self.assertIsNone(ed.click_result("path", 2, 0, False))

    def test_last_vertex_finishes_path(self):
        self.assertEqual(ed.click_result("path", 3, 2, False), ed.FINISH)
        self.assertIsNone(ed.click_result("polygon", 3, 2, False))

    def test_finished_figure_ignores_click(self):
        self.assertIsNone(ed.click_result("path", 3, 0, True))

    def test_point_mode(self):
        self.assertIsNone(ed.click_result("point", 1, 0, False))


class TestHit(unittest.TestCase):

    def test_segment_distance(self):
        self.assertAlmostEqual(
            ed.segment_distance(SQUARE, FRONT, 50.0, 5.0), 5.0)

    def test_closing_segment_counts_only_when_closed(self):
        self.assertAlmostEqual(
            ed.segment_distance(SQUARE, FRONT, -3.0, 50.0, closed=True),
            3.0)
        self.assertGreater(
            ed.segment_distance(SQUARE, FRONT, -3.0, 50.0), 40.0)

    def test_inside(self):
        self.assertTrue(ed.inside(SQUARE, 50.0, 50.0))
        self.assertFalse(ed.inside(SQUARE, 150.0, 50.0))

    def test_hit_kinds(self):
        self.assertTrue(ed.hit("polygon", SQUARE, FRONT, 50.0, 50.0, 8.0))
        self.assertFalse(ed.hit("line", SQUARE, FRONT, 50.0, 50.0, 8.0))
        self.assertTrue(ed.hit("line", SQUARE, FRONT, 50.0, 4.0, 8.0))
        self.assertTrue(ed.hit("point", SQUARE, FRONT, 3.0, 3.0, 8.0))
        self.assertFalse(ed.hit("point", SQUARE, FRONT, 98.0, 3.0, 8.0))

    def test_hidden_object_is_not_hit(self):
        self.assertFalse(ed.hit("polygon", SQUARE, np.zeros(4, dtype=bool),
                                50.0, 50.0, 8.0))


if __name__ == "__main__":
    unittest.main()
