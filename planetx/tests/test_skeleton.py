# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/skeleton: прямой скелет (bpypolyskel) без Blender."""
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

from skeleton import Vector, polygonize  # noqa: E402
from skeleton.vector import geometry  # noqa: E402


class TestVector(unittest.TestCase):
    def test_cross(self):
        self.assertEqual(Vector((1, 0)).cross(Vector((0, 1))), 1.0)
        self.assertEqual(list(Vector((1, 0, 0)).cross(Vector((0, 1, 0)))),
                         [0.0, 0.0, 1.0])

    def test_inplace(self):
        v = Vector((1, 2, 3))
        v += Vector((1, 1, 1))
        v /= 2
        v[2] = 0.0
        self.assertEqual(list(v), [1.0, 1.5, 0.0])
        self.assertEqual(list(v.xy), [1.0, 1.5])

    def test_point_line(self):
        p, t = geometry.intersect_point_line(
            Vector((1, 5)), Vector((0, 0)), Vector((4, 0)))
        self.assertEqual(list(p), [1.0, 0.0])
        self.assertAlmostEqual(t, 0.25)


class TestPolygonize(unittest.TestCase):
    def roof(self, pts):
        verts = [Vector((x, y, 0.0)) for x, y in pts]
        faces = polygonize(verts, 0, len(pts), None, 0.0, 0.5, None, None)
        return verts, faces

    def test_rectangle(self):
        """Прямоугольник 10x4: два ската-трапеции и два треугольных вальма."""
        verts, faces = self.roof([(0, 0), (10, 0), (10, 4), (0, 4)])
        self.assertEqual(sorted(len(f) for f in faces), [3, 3, 4, 4])
        ridge = [v for v in verts[4:]]
        self.assertEqual(len(ridge), 2)
        for v in ridge:
            self.assertAlmostEqual(v.y, 2.0)
            self.assertAlmostEqual(v.z, 1.0)  # 2 м до края * tan 0.5

    def test_l_shape(self):
        """Г-образный контур: шесть скатов, по одному на сторону."""
        verts, faces = self.roof(
            [(4, 10), (4, 4), (7, 4), (7, 0), (0, 0), (0, 10)][::-1])
        self.assertEqual(len(faces), 6)
        for f in faces:
            self.assertGreaterEqual(len(f), 3)
            self.assertEqual(len(f), len(set(f)))
        top = max(v.z for v in verts)
        self.assertAlmostEqual(top, 1.0)


if __name__ == "__main__":
    unittest.main()
