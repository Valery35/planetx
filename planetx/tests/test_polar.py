# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Полярные шапки снимками Esri: проекции и раскладка мозаики."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import polar  # noqa: E402
import tiling  # noqa: E402

# Точки GDAL 3.13 из QGIS 4.0.3, 23 октября 2026 года: код EPSG,
# долгота, широта, x, y.
GDAL = (
    (5936, 0, 85.0511, 2274886.901, 2476118.079),
    (5936, 33, 88, 1988377.792, 2221764.931),
    (5936, -150, 86, 2000000.000, 1555731.571),
    (5936, 100, 89.5, 1947835.552, 2018986.306),
    (5936, 10, 70, 2766942.470, 4107157.119),
    (3031, 0, -85.0511, 0.000, 538031.105),
    (3031, 45, -88, 153672.731, 153672.731),
    (3031, -120, -86, -376529.864, -217389.618),
    (3031, 170, -89.5, 9433.707, -53501.210),
    (3031, 10, -70, 381069.927, 2161154.949),
)


class TestProject(unittest.TestCase):

    def test_matches_gdal(self):
        for code, lon, lat, x, y in GDAL:
            px, py = polar.project(lat, lon, code == 5936)
            self.assertAlmostEqual(float(px), x, delta=0.01, msg=code)
            self.assertAlmostEqual(float(py), y, delta=0.01, msg=code)


class TestLayout(unittest.TestCase):

    def test_cap_inside_mosaic(self):
        for north in (True, False):
            lay = polar.Layout(north)
            self.assertEqual(len(lay.tiles()), 36)
            lat = np.full(360, polar.MAX_LAT * (1 if north else -1))
            u, v = lay.uv(lat, np.arange(360) - 180.0)
            for w in (u, v):
                self.assertGreater(w.min(), 0.0)
                self.assertLess(w.max(), 1.0)
            pu, pv = lay.uv(90.0 if north else -90.0, 0.0)
            self.assertAlmostEqual(float(pu), 0.5, delta=0.1)
            self.assertIn("/tile/8/", lay.tiles()[0][2])
            self.assertIn("Arctic" if north else "Antarctic",
                          lay.tiles()[0][2])

    def test_mosaic_places_tiles(self):
        lay = polar.Layout(False)
        tile = np.zeros((256, 256, 4), np.uint8)
        tile[..., 0] = 200
        out = lay.mosaic({(lay.row0 + 1, lay.col0 + 2): tile,
                          (lay.row0, lay.col0): None})
        self.assertEqual(out.shape, (6 * 256, 6 * 256, 4))
        self.assertEqual(out[256 + 5, 512 + 5, 0], 200)
        self.assertEqual(out[5, 5, 0], 40)

    def test_rim_color_matches_base(self):
        lay = polar.Layout(True)
        image = lay.mosaic({})
        image[..., :3] = (10, 40, 100)
        have = polar.rim_color(lay, image)
        self.assertEqual(have.shape, (polar.SECTORS, 3))
        self.assertEqual([round(v) for v in have[3]], [10, 40, 100])
        out = polar.matched(image, lay, have, [(15, 60, 150)] * 8)
        self.assertEqual(tuple(out[5, 5, :3]), (15, 60, 150))
        # Множитель ограничен: чёрный край не делает снимок белым.
        out = polar.matched(image, lay, have, [(255, 255, 255)] * 8)
        self.assertEqual(int(out[5, 5, 2]), 200)
        self.assertEqual(polar.edge_rows(False), slice(240, 256))

    def test_sector_gain_follows_longitude(self):
        # Сектор 0 (долготы -180..-135) светлее вдвое, прочие как есть:
        # точка края на -157.5° вдвое светлее, на 22.5° без изменений.
        for north in (True, False):
            lay = polar.Layout(north)
            image = lay.mosaic({})
            image[..., :3] = 100
            want = np.full((8, 3), 100.0)
            want[0] = 200.0
            out = polar.matched(image, lay, np.full((8, 3), 100.0), want)
            lat = np.array([polar.RIM_LAT if north else -polar.RIM_LAT] * 2)
            u, v = lay.uv(lat, np.array([-157.5, 22.5]))
            h, w = out.shape[:2]
            got = out[(v * h).astype(int), (u * w).astype(int), 0]
            self.assertGreater(int(got[0]), 185, north)
            self.assertEqual(int(got[1]), 100, north)
            lon, share = polar.pixel_lon(lay, image.shape)
            self.assertLess(float(share.min()), 0.01)

    def test_needed(self):
        self.assertEqual(polar.needed(10.0, 2.5e7), (True, False))
        self.assertEqual(polar.needed(70.0, 1.0e5), (True,))
        self.assertEqual(polar.needed(-80.0, 1.0e5), (False,))
        self.assertEqual(polar.needed(40.0, 1.0e5), ())


class TestCapMesh(unittest.TestCase):

    def test_cap_mesh_has_rings_and_uv(self):
        lay = polar.Layout(True)
        mesh = tiling.polar_cap_mesh(True, uv=lay.uv)
        self.assertGreater(len(mesh.uv), 1000)
        self.assertGreater(mesh.uv[:, 0].max(), 0.5)
        self.assertLess(int(mesh.indices.max()), len(mesh.uv))
        plain = tiling.polar_cap_mesh(False)
        self.assertEqual(float(np.abs(plain.uv).max()), 0.0)


if __name__ == "__main__":
    unittest.main()
