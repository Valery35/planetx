# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Томография мантии: выборка, раскраска, мантия на гранях разреза."""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import cutaway as cw  # noqa: E402
import ellipsoid as el  # noqa: E402
import tomography as tm  # noqa: E402


def model():
    """Западное полушарие медленнее на 2 %, восточное быстрее, сетка
    файла - широты с севера, долготы 0-359."""
    depths = np.arange(50.0, 2851.0, 50.0)
    lats = np.arange(89.0, -90.0, -1.0)
    lons = np.arange(0.0, 360.0, 1.0)
    dvs = np.where(lons >= 180.0, -2.0, 2.0)[None, None, :] \
        * np.ones((len(depths), len(lats), 1))
    return tm.make(depths, lats, lons, dvs)


class TestTomography(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)
        self.tomo = model()

    def test_make_sorts_latitudes(self):
        self.assertLess(self.tomo.lats[0], self.tomo.lats[-1])
        self.assertEqual(self.tomo.dvs.shape, (57, 179, 360))

    def test_sample_and_colors(self):
        values = tm.sample(self.tomo, [0.0, 0.0, 10.0], [-90.0, 90.0, 270.0],
                           300.0)
        self.assertTrue(np.allclose(values, [-2.0, 2.0, -2.0]))
        rgb = tm.colors(values)
        self.assertEqual(tuple(rgb[0]), tm.STOPS[0][1])
        self.assertEqual(tuple(rgb[1]), tm.STOPS[-1][1])
        # Ниже последней глубины модели - край модели.
        deep = tm.sample(self.tomo, [0.0], [90.0], 2890.0)
        self.assertAlmostEqual(float(deep[0]), 2.0)

    def test_faces_paint_mantle(self):
        # Сектор у 0° долготы - обе половины модели на гранях.
        mesh = cw.faces(cw.wedge_at(10.0, 0.0), tomo=self.tomo)
        rgb = mesh.vertices["color"][:, :3]

        def has(color):
            return bool(np.any(np.all(rgb == np.array(color, np.uint8),
                                      axis=1)))
        self.assertTrue(has(tm.STOPS[0][1]))
        self.assertTrue(has(tm.STOPS[-1][1]))
        # Оболочек мантии PREM на гранях нет, ядро есть.
        for key, _, _, color in cw.SHELLS:
            if key in cw.MANTLE:
                self.assertFalse(has(color), key)
        self.assertTrue(has(cw.SHELLS[1][3]))

    def test_save_load(self):
        path = os.path.join(tempfile.mkdtemp(), "t.npz")
        tm.save(self.tomo, path)
        back = tm.load(path)
        self.assertTrue(np.allclose(back.dvs, self.tomo.dvs, atol=1e-2))


if __name__ == "__main__":
    unittest.main()
