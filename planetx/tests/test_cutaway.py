# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разрез Земли: сектор, грани с оболочками PREM."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import cutaway as cw  # noqa: E402
import ellipsoid as el  # noqa: E402


class TestCutaway(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_shells_cover_radius_without_gaps(self):
        self.assertEqual(cw.SHELLS[0][1], 0.0)
        self.assertEqual(cw.SHELLS[-1][2], cw.PREM_RADIUS)
        for below, above in zip(cw.SHELLS, cw.SHELLS[1:]):
            self.assertEqual(below[2], above[1])
        # Ядро - 3480 км, внутреннее ядро - 1221.5 км.
        radii = {name: high for name, _, high, _ in cw.SHELLS}
        self.assertEqual(radii["outer_core"], 3480.0)
        self.assertEqual(radii["inner_core"], 1221.5)

    def test_inside_wraps_longitude(self):
        wedge = cw.wedge_at(30.0, 170.0)
        got = cw.inside(wedge, [10.0, 10.0, -10.0, 10.0],
                        [-160.0, 120.0, 170.0, 215.0 - 360.0])
        self.assertEqual(got.tolist(), [True, False, False, True])
        south = cw.wedge_at(-5.0, 0.0)
        self.assertEqual((south.south, south.north), (-90.0, 0.0))
        self.assertTrue(cw.inside(south, [-80.0], [40.0])[0])

    def test_move_corner(self):
        wedge = cw.wedge_at(30.0, 100.0)
        # Юго-западный угол - на 20° с. ш., 70° в. д.
        moved = cw.move_corner(wedge, 0, 20.0, 70.0)
        self.assertEqual(moved, cw.Wedge(70.0, 145.0, 20.0, 90.0))
        # Северо-восточный угол через линию перемены дат.
        wide = cw.move_corner(moved, 3, 60.0, -170.0)
        self.assertAlmostEqual(cw.span(wide), 120.0)
        self.assertEqual((wide.south, wide.north), (20.0, 60.0))
        self.assertTrue(cw.inside(wide, [40.0], [179.0])[0])
        self.assertFalse(cw.inside(wide, [65.0], [179.0])[0])
        # Восток за западом - сектор не выворачивается.
        thin = cw.move_corner(wedge, 1, 30.0, 50.0)
        self.assertAlmostEqual(cw.span(thin), cw.MIN_SPAN)
        # Угол за полюс и широты наоборот - по порядку.
        flipped = cw.move_corner(wedge, 2, -10.0, 55.0)
        self.assertEqual((flipped.south, flipped.north), (-10.0, 0.0))

    def test_uniform_matches_inside(self):
        # Шейдер считает сектор по нормали: dot(xy, c) >= cos(half)·|xy|
        # и синус широты между синусами границ. Та же проверка, что
        # и inside.
        wedge = cw.make_wedge(20.0, 130.0, -25.0, 50.0)
        cx, cy, cos_half, sin_s, sin_n = cw.uniform(wedge)
        rng = np.random.default_rng(3)
        lats = rng.uniform(-89.0, 89.0, 500)
        lons = rng.uniform(-180.0, 180.0, 500)
        up = el.surface_normal(lats, lons)
        xy = np.hypot(up[:, 0], up[:, 1])
        shader = ((up[:, 0] * cx + up[:, 1] * cy >= cos_half * xy)
                  & (up[:, 2] > sin_s) & (up[:, 2] < sin_n))
        self.assertEqual(shader.tolist(),
                         cw.inside(wedge, lats, lons).tolist())

    def test_face_edge_lies_on_ellipsoid(self):
        wedge = cw.wedge_at(50.0, 30.0)
        mesh = cw.faces(wedge)
        points = mesh.vertices["position"].astype(np.float64) + mesh.center
        r = np.linalg.norm(points, axis=1)
        edge = r > 0.99 * el.B
        outer = points[edge]
        # Внешний край - на эллипсоиде: x²/a² + y²/a² + z²/b² = 1.
        # Точность float32 вершин - около метра.
        level = ((outer[:, 0] ** 2 + outer[:, 1] ** 2) / el.A ** 2
                 + outer[:, 2] ** 2 / el.B ** 2)
        self.assertLess(float(np.max(np.abs(level - 1.0))), 0.01)
        outermost = level > 0.999
        self.assertGreater(int(np.sum(outermost)), 100)
        self.assertLess(float(np.max(np.abs(level[outermost] - 1.0))),
                        1e-6)
        # Ничего не выходит из сектора: долготы граней в его пределах.
        # У оси Земли долгота не определена.
        far = np.hypot(points[:, 0], points[:, 1]) > 1000.0
        lon = np.degrees(np.arctan2(points[far, 1], points[far, 0]))
        self.assertLessEqual(float(np.max(np.abs(lon - 30.0))), 45.0 + 1e-3)
        self.assertGreaterEqual(float(np.min(points[far, 2])), -1.0)

    def test_core_boundary_radius(self):
        mesh = cw.faces(cw.wedge_at(10.0, 0.0), shells=cw.SHELLS[1:2])
        points = mesh.vertices["position"].astype(np.float64) + mesh.center
        r = np.linalg.norm(points, axis=1)
        # Граница ядра - 3480/6371 радиуса эллипсоида в направлении.
        self.assertAlmostEqual(float(r.max()) / el.A, 3480.0 / 6371.0,
                               delta=1e-4)


class TestStretch(unittest.TestCase):
    """Выделение коры издалека."""

    def test_stretch_keeps_ends_and_order(self):
        depth = np.linspace(0.0, 700.0, 141)
        shown = cw.stretch(depth, 8.0)
        self.assertEqual(float(shown[0]), 0.0)
        self.assertAlmostEqual(float(cw.stretch([400.0], 8.0)[0]), 400.0)
        self.assertTrue(np.all(np.diff(shown) > 0.0))
        deep = depth >= cw.STRETCH_DEPTH
        self.assertTrue(np.allclose(shown[deep], depth[deep]))
        # У поверхности - в gain раз.
        self.assertAlmostEqual(float(cw.stretch([0.01], 8.0)[0]) / 0.01,
                               8.0, delta=0.01)
        self.assertEqual(cw.stretch([10.0], 1.0).tolist(), [10.0])

    def test_gain_steps_with_distance(self):
        self.assertEqual(cw.gain_for(5.0e5), 1.0)
        self.assertEqual(cw.gain_for(cw.GAIN_DISTANCE * 4.5), 4.0)
        self.assertEqual(cw.gain_for(1.0e9), max(cw.GAIN_STEPS))

    def test_stretched_core_unchanged(self):
        plain = cw.faces(cw.wedge_at(10.0, 0.0), shells=cw.SHELLS[:2])
        far = cw.faces(cw.wedge_at(10.0, 0.0), shells=cw.SHELLS[:2],
                       gain=8.0)
        self.assertTrue(np.allclose(plain.vertices["position"],
                                    far.vertices["position"]))


class TestCrustFaces(unittest.TestCase):
    """Грани с моделью коры: мантия до Мохо точки, слои CRUST1.0."""

    def setUp(self):
        el.set_body(el.EARTH)
        import crust as cr
        self.cr = cr
        bounds = np.zeros((cr.ROWS, cr.COLS, cr.BOUNDS), dtype=np.float32)
        # Вода 4 км, осадки 1 км, кора до Мохо 30 км везде.
        bounds[..., 0] = 0.0
        bounds[..., 1:6] = -4.0
        bounds[..., 3] = -5.0
        bounds[..., 4:6] = -5.0
        bounds[..., 6] = -15.0
        bounds[..., 7] = -22.0
        bounds[..., 8] = -30.0
        self.model = cr.Crust(bounds)

    def test_layer_keys_match_model(self):
        self.assertEqual(cw.crust_layers(), self.cr.LAYERS)

    def test_mantle_reaches_moho(self):
        mantle = cw.faces(cw.wedge_at(10.0, 0.0), shells=cw.SHELLS[4:5],
                          crust=self.model)
        # Только верхняя мантия и слои коры: самая высокая точка мантии
        # ищется среди вершин цвета мантии.
        color = np.array(cw.SHELLS[4][3], dtype=np.uint8)
        own = np.all(mantle.vertices["color"][:, :3] == color, axis=1)
        points = mantle.vertices["position"][own].astype(np.float64) \
            + mantle.center
        r = np.linalg.norm(points, axis=1)
        self.assertAlmostEqual(float(r.max()) / el.A,
                               (cw.PREM_RADIUS - 30.0) / cw.PREM_RADIUS,
                               delta=1e-5)

    def test_water_layer_on_top(self):
        mesh = cw.faces(cw.wedge_at(10.0, 0.0), shells=(), crust=self.model)
        color = np.array(cw.CRUST_COLORS["water"], dtype=np.uint8)
        water = np.all(mesh.vertices["color"][:, :3] == color, axis=1)
        self.assertTrue(np.any(water))
        ice = np.array(cw.CRUST_COLORS["ice"], dtype=np.uint8)
        # Лёд нулевой толщины не рисуется.
        self.assertFalse(np.any(np.all(
            mesh.vertices["color"][:, :3] == ice, axis=1)))


if __name__ == "__main__":
    unittest.main()
