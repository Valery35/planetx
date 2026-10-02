# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетки подземного режима: трубка, горизонт, стенка, вырез."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import subsurface as ss  # noqa: E402

LAT, LON = 58.0, 56.0


class TestTube(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_tube_radius_and_closure(self):
        points = ss.ecef([LAT, LAT, LAT + 0.001], [LON, LON, LON],
                         [100.0, -100.0, -200.0])
        part = ss.tube(points, 5.0, (255, 0, 0))
        self.assertEqual(len(part.positions), 3 * ss.SIDES)
        # Каждая вершина кольца - на радиусе от своей точки оси.
        rings = part.positions.reshape(3, ss.SIDES, 3)
        for ring, center in zip(rings, points):
            radii = np.linalg.norm(ring - center, axis=1)
            self.assertTrue(np.allclose(radii, 5.0))
        # Две грани на сторону сечения на каждом из двух отрезков.
        self.assertEqual(len(part.indices), 2 * 2 * ss.SIDES)
        self.assertLess(part.indices.max(), len(part.positions))


class TestSurface(unittest.TestCase):

    def test_hole_cells_skipped(self):
        lats, lons = np.meshgrid(LAT + np.arange(3) * 0.001,
                                 LON + np.arange(3) * 0.001, indexing="ij")
        alts = np.full(lats.shape, -50.0)
        points = ss.ecef(lats, lons, alts)
        valid = np.ones(lats.shape, dtype=bool)
        full = ss.grid_surface(points, valid, (0, 200, 0))
        self.assertEqual(len(full.indices), 8)
        valid[1, 1] = False  # средний узел пуст - все 4 ячейки пропадают
        self.assertIsNone(ss.grid_surface(points, valid, (0, 200, 0)))
        # Нормали смотрят вверх, от центра Земли.
        up = el.surface_normal(LAT, LON)
        self.assertGreater(float(np.dot(full.normals[4], up)), 0.99)


class TestWall(unittest.TestCase):

    def test_wall_between_planes(self):
        lats = [LAT, LAT, LAT]
        lons = [LON, LON + 0.01, LON + 0.02]
        part = ss.wall(lats, lons, [0.0, 0.0, 0.0], [-30.0, -30.0, -30.0],
                       (10, 20, 30))
        top, bottom = part.positions[:3], part.positions[3:]
        self.assertTrue(np.allclose(np.linalg.norm(top - bottom, axis=1),
                                    30.0, atol=1e-6))
        self.assertEqual(len(part.indices), 4)

    def test_crossed_surfaces_give_no_wall(self):
        part = ss.wall([LAT, LAT], [LON, LON + 0.01], [-40.0, -40.0],
                       [-30.0, -30.0], (1, 2, 3))
        self.assertIsNone(part)


class TestMerge(unittest.TestCase):

    def test_merge_offsets_indices(self):
        a = ss.wall([LAT, LAT], [LON, LON + 0.01], [0, 0], [-10, -10],
                    (1, 2, 3))
        b = ss.wall([LAT, LAT], [LON, LON + 0.01], [-10, -10], [-20, -20],
                    (4, 5, 6))
        mesh = ss.merge([a, b, None])
        self.assertEqual(len(mesh.vertices), 8)
        self.assertEqual(mesh.indices.max(), 7)
        back = mesh.vertices["position"].astype(np.float64) + mesh.center
        self.assertTrue(np.allclose(back, np.vstack([a.positions,
                                                     b.positions]),
                                    atol=0.01))


class TestHelpers(unittest.TestCase):

    def test_display_scale_and_flat(self):
        self.assertEqual(float(ss.display(-100.0, 3.0, 150.0)), -300.0)
        # Рельеф выключен: глубина под поверхностью.
        self.assertEqual(float(ss.display(-100.0, 0.0, 150.0)), -250.0)

    def test_sample_grid(self):
        z = np.array([[10.0, 20.0], [30.0, np.nan]])
        grid = ss.Grid(100.0, 200.0, 10.0, -10.0, z)
        got = ss.sample_grid(grid, [100.0, 105.0, 105.0, 50.0],
                             [200.0, 200.0, 195.0, 200.0])
        self.assertEqual(got[:2].tolist(), [10.0, 15.0])
        self.assertTrue(np.isnan(got[2]))  # рядом пустой узел
        self.assertTrue(np.isnan(got[3]))  # вне растра

    def test_stack_no_crossings(self):
        out = ss.stack([[0.0, 0.0], [-10.0, 5.0], [np.nan, -20.0]])
        self.assertEqual(out.tolist(), [[0.0, 0.0], [-10.0, 0.0],
                                        [-10.0, -20.0]])

    def test_densify_keeps_vertices(self):
        out = ss.densify([(0.0, 0.0), (10.0, 0.0), (10.0, 5.0)], 4.0)
        self.assertEqual(out[0].tolist(), [0.0, 0.0])
        self.assertEqual(out[-1].tolist(), [10.0, 5.0])
        self.assertIn([10.0, 0.0], out.tolist())
        steps = np.hypot(*np.diff(out, axis=0).T)
        self.assertLessEqual(steps.max(), 4.0 + 1e-9)

    def test_fence_and_floor(self):
        surfaces = ss.stack([[0.0, 0.0], [-10.0, -10.0], [-30.0, -30.0]])
        parts = ss.fence([LAT, LAT], [LON, LON + 0.01], surfaces,
                         [(1, 2, 3), (4, 5, 6)])
        self.assertEqual(len([p for p in parts if p is not None]), 2)
        floor = ss.floor_part([(LAT, LON), (LAT, LON + 0.01),
                               (LAT + 0.01, LON + 0.01), (LAT + 0.01, LON)],
                              -30.0, (9, 9, 9))
        self.assertEqual(len(floor.indices), 2)


class TestInside(unittest.TestCase):

    def test_square(self):
        ring = [(0, 0), (0, 1), (1, 1), (1, 0)]
        got = ss.inside([0.5, 1.5, 0.5], [0.5, 0.5, -0.1], ring)
        self.assertEqual(got.tolist(), [True, False, False])


if __name__ == "__main__":
    unittest.main()
