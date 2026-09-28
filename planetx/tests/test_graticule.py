# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Координатная сетка: шаг, окно, линии, подписи."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import graticule as gr  # noqa: E402


class TestStep(unittest.TestCase):

    def test_step_follows_width(self):
        self.assertEqual(gr.step_for(2.0e7), 30.0)
        self.assertEqual(gr.step_for(1.0e6), 2.0)
        self.assertAlmostEqual(gr.step_for(20000.0), 2 / 60.0)
        self.assertAlmostEqual(gr.step_for(300.0), 2 / 3600.0)

    def test_about_eight_lines_across(self):
        for width in (5.0e6, 2.0e5, 8000.0):
            step = gr.step_for(width)
            across = width / (step * gr.M_PER_DEGREE)
            self.assertGreaterEqual(across, 3.0, width)
            self.assertLessEqual(across, gr.LINES_ACROSS + 0.01, width)


class TestLines(unittest.TestCase):

    def test_global_grid(self):
        step, found = gr.lines(58.0, 56.0, 2.0e7)
        self.assertEqual(step, 30.0)
        parallels = [v for kind, v, _ in found if kind == "lat"]
        meridians = [v for kind, v, _ in found if kind == "lon"]
        # Экватор - особая параллель, в общей сетке его нет.
        self.assertEqual(parallels, [-60.0, -30.0, 30.0, 60.0])
        self.assertEqual(len(meridians), 12)
        # Параллель гнётся по вершинам не реже SEGMENT градусов.
        points = [p for kind, v, p in found if kind == "lat"][0]
        gaps = [b[1] - a[1] for a, b in zip(points, points[1:])]
        self.assertLessEqual(max(gaps), gr.SEGMENT + 1e-9)

    def test_local_window_near_view(self):
        step, found = gr.lines(58.0, 56.2, 20000.0)
        self.assertAlmostEqual(step, 2 / 60.0)
        for kind, value, points in found:
            if kind == "lat":
                self.assertLess(abs(value - 58.0), 1.0)
            else:
                self.assertLess(abs(value - 56.2), 2.0)
        self.assertLess(len(found), 80)

    def test_labels_and_key(self):
        spots = gr.labels(58.0, 56.2, 20000.0)
        self.assertTrue(any(kind == "lat" for _, _, kind, _ in spots))
        self.assertTrue(any(kind == "lon" for _, _, kind, _ in spots))
        self.assertEqual(gr.key(58.0, 56.2, 20000.0),
                         gr.key(58.001, 56.201, 20000.0))
        self.assertNotEqual(gr.key(58.0, 56.2, 20000.0),
                            gr.key(58.0, 56.2, 2.0e6))


class TestCircles(unittest.TestCase):

    def test_all_circles_from_space(self):
        found = gr.circles(58.0, 56.0, 2.0e7)
        self.assertEqual([name for name, _, _ in found],
                         ["equator", "cancer", "capricorn", "arctic",
                          "antarctic"])
        values = dict((name, value) for name, value, _ in found)
        self.assertAlmostEqual(values["arctic"], 66.5638, places=4)
        self.assertAlmostEqual(values["capricorn"], -23.4362, places=4)
        self.assertEqual(len(gr.circle_labels(58.0, 56.0, 2.0e7)), 5)

    def test_only_circles_in_window(self):
        self.assertEqual(gr.circles(58.0, 56.2, 20000.0), [])
        found = gr.circles(66.5, 40.0, 50000.0)
        self.assertEqual([name for name, _, _ in found], ["arctic"])


class TestText(unittest.TestCase):

    def test_angle_text(self):
        self.assertEqual(gr.angle_text(58.0, 10.0), "58°")
        self.assertEqual(gr.angle_text(-58.5, 0.5), "58°30′")
        self.assertEqual(gr.angle_text(56.2275, 1 / 3600.0), "56°13′39″")


if __name__ == "__main__":
    unittest.main()
