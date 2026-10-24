# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Обзоры неба HiPS: сетка HEALPix, вершины тайлов, выбор тайлов."""
import math
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import hips  # noqa: E402


def lat_lon(d):
    return (math.degrees(math.asin(d[2])),
            math.degrees(math.atan2(d[1], d[0])) % 360.0)


class TestHealpix(unittest.TestCase):

    def test_face_corners(self):
        # Середина грани 4 - экватор на долготе 0, грани 0 - z 2/3 на
        # 45°, южный угол грани 0 - экватор на 45°.
        lat, lon = lat_lon(hips.face_directions(4, 0.5, 0.5))
        self.assertAlmostEqual(lat, 0.0)
        self.assertAlmostEqual(lon, 0.0)
        d = hips.face_directions(0, 0.5, 0.5)
        self.assertAlmostEqual(float(d[2]), 2.0 / 3.0)
        self.assertAlmostEqual(lat_lon(d)[1], 45.0)
        self.assertAlmostEqual(lat_lon(hips.face_directions(0, 0, 0))[0], 0)
        self.assertAlmostEqual(float(hips.face_directions(0, 1, 1)[2]), 1)
        self.assertAlmostEqual(float(hips.face_directions(8, 0, 0)[2]), -1)

    def test_equal_areas(self):
        # Середины ячеек порядка 2 на сфере расставлены равномерно:
        # ближайший сосед у всех на одном расстоянии с точностью 40 %.
        c = hips.centers(2, np.arange(192))
        cos = c @ c.T
        np.fill_diagonal(cos, -1)
        near = np.degrees(np.arccos(cos.max(axis=1)))
        self.assertLess(near.max() / near.min(), 1.4)
        self.assertTrue(np.allclose(np.linalg.norm(c, axis=1), 1.0))

    def test_children_inside_parent(self):
        parent = hips.centers(3, [100])[0]
        kids = hips.centers(4, np.arange(400, 404))
        size = hips.cell_size(3)
        self.assertTrue(np.all(np.arccos(kids @ parent) < size))

    def test_nest_bits(self):
        # Чётные биты - ix, нечётные - iy: 1011 даёт ix 01, iy 11.
        face, ix, iy = hips.nest_xyf(2, np.array([16 * 5 + 0b1011]))
        self.assertEqual((int(face[0]), int(ix[0]), int(iy[0])), (5, 1, 3))


class TestTiles(unittest.TestCase):

    def test_mesh_matches_centers(self):
        dirs, uv = hips.tile_mesh(3, 327, steps=8)
        self.assertEqual(dirs.shape, (81, 3))
        middle = dirs[40]
        center = hips.centers(3, [327])[0]
        self.assertGreater(float(middle @ center), math.cos(1e-6))
        self.assertEqual(len(hips.mesh_indices(8)), 8 * 8 * 6)
        self.assertEqual(tuple(uv[0]), (0.0, 0.0))

    def test_url(self):
        self.assertEqual(hips.tile_url("b/", 5, 12345),
                         "b/Norder5/Dir10000/Npix12345.jpg")
        self.assertEqual(hips.allsky_url("b/"), "b/Norder3/Allsky.jpg")

    def test_order_for_view(self):
        # Широкий вид - Allsky.jpg, поле 1° на 1000 пикселей - порядок
        # с пикселем не крупнее 1.5 пикселя экрана, не глубже обзора.
        self.assertIsNone(hips.order_for(math.radians(110) / 800, 9))
        self.assertEqual(hips.order_for(math.radians(70) / 1800, 9), 3)
        order = hips.order_for(math.radians(1) / 1000, 9)
        self.assertEqual(order, 7)
        self.assertEqual(hips.order_for(1e-8, 9), 9)

    def test_visible_cone(self):
        axis = hips.centers(5, [5000])[0]
        cells = hips.visible(5, axis, math.radians(2))
        self.assertIn(5000, cells)
        self.assertLess(len(cells), 60)
        c = hips.centers(5, cells)
        self.assertTrue(np.all(np.degrees(np.arccos(c @ axis)) < 6))
        everything = hips.visible(3, axis, math.pi)
        self.assertEqual(len(everything), 768)

    def test_allsky_rect(self):
        u0, v0, du, dv = hips.allsky_rect(28, 1728, 1856)
        self.assertAlmostEqual(u0, 64 / 1728)
        self.assertAlmostEqual(v0, 64 / 1856)
        self.assertAlmostEqual(du, 64 / 1728)


if __name__ == "__main__":
    unittest.main()
