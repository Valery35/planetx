# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выдавливание объектов слоя по полю."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import extrude  # noqa: E402
from ellipsoid import (ecef_to_geodetic, geodetic_to_ecef,  # noqa: E402
                       surface_normal)


def square(lat, lon, side_deg, clockwise=False):
    ring = np.array([[lat, lon], [lat, lon + side_deg],
                     [lat + side_deg, lon + side_deg], [lat + side_deg, lon]])
    return ring[::-1] if clockwise else ring


def world(mesh):
    return mesh.center + mesh.vertices["position"].astype(np.float64)


class TestPolygon(unittest.TestCase):

    def test_prism_walls_face_out_and_roof_on_top(self):
        for clockwise in (False, True):
            parts = extrude.Parts()
            self.assertTrue(parts.add_polygon(
                [square(58.0, 56.0, 0.001, clockwise)], 30.0))
            fp = parts.footprint()
            mesh = extrude.mesh(fp, parts.follow(),
                                lambda la, lo: np.full(len(la), 100.0))
            self.assertEqual(len(mesh.vertices), parts.vertex_count())
            # 4 стены по 2 треугольника и крыша из 2 треугольников.
            self.assertEqual(len(mesh.indices), 3 * (8 + 2))
            points = world(mesh)
            lat, lon, h = ecef_to_geodetic(points)
            self.assertAlmostEqual(float(h.min()), 100.0, places=2)
            self.assertAlmostEqual(float(h.max()), 130.0, places=2)
            # Нормаль стены смотрит от середины призмы наружу.
            middle = geodetic_to_ecef(58.0005, 56.0005, 115.0)
            normals = mesh.vertices["normal"][:16, :3].astype(float)
            outward = points[:16] - middle
            self.assertTrue(np.all((normals * outward).sum(axis=1) > 0))

    def test_hole_keeps_roof_out_of_yard(self):
        parts = extrude.Parts()
        outer = square(58.0, 56.0, 0.003)
        hole = square(58.001, 56.001, 0.001)
        parts.add_polygon([outer, hole], 10.0)
        fp = parts.footprint()
        tri = fp.latlon[fp.roof.reshape(-1, 3)].mean(axis=1)
        inside = ((tri[:, 0] > 58.001) & (tri[:, 0] < 58.002)
                  & (tri[:, 1] > 56.001) & (tri[:, 1] < 56.002))
        self.assertFalse(inside.any())
        self.assertGreater(len(fp.roof), 0)

    def test_flat_or_negative_height_skipped(self):
        parts = extrude.Parts()
        self.assertFalse(parts.add_polygon([square(58, 56, 0.001)], 0.0))
        self.assertIsNone(parts.footprint())


class TestLineAndPoint(unittest.TestCase):

    def test_wall_follows_terrain(self):
        parts = extrude.Parts()
        line = np.array([[58.0, 56.0], [58.0, 56.01], [58.0, 56.02]])
        parts.add_line(line, 5.0)
        fp = parts.footprint()
        self.assertEqual(int(fp.wall.sum()), 2)
        self.assertEqual(len(fp.roof), 0)
        ground = {56.0: 100.0, 56.01: 300.0, 56.02: 150.0}

        def heights(la, lo):
            return np.array([ground[round(v, 2)] for v in lo])
        mesh = extrude.mesh(fp, parts.follow(), heights)
        _, lon, h = ecef_to_geodetic(world(mesh))
        for key, value in ground.items():
            near = np.abs(lon - key) < 1e-6
            self.assertAlmostEqual(float(h[near].min()), value, places=2)
            self.assertAlmostEqual(float(h[near].max()), value + 5.0,
                                   places=2)

    def test_column_radius(self):
        ring = extrude.column(58.0, 56.0, 10.0, 6378137.0)
        self.assertEqual(len(ring), extrude.SIDES)
        center = geodetic_to_ecef(58.0, 56.0, 0.0)
        far = np.linalg.norm(geodetic_to_ecef(ring[:, 0], ring[:, 1], 0.0)
                             - center, axis=1)
        self.assertTrue(np.allclose(far, 10.0, rtol=0.01))
        parts = extrude.Parts()
        self.assertTrue(parts.add_polygon([ring], 50.0))
        up = surface_normal(np.array([58.0]), np.array([56.0]))[0]
        self.assertGreater(float(up @ up), 0.0)


if __name__ == "__main__":
    unittest.main()
