# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои объекты глобуса: сгущение, посадка, треугольники."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid as el  # noqa: E402
import features as ft  # noqa: E402


class TestDensify(unittest.TestCase):

    def test_step_along_arc(self):
        # Градус меридиана - около 111 км, при шаге 100 м ~1113 точек.
        out = ft.densify([(58.0, 56.0), (59.0, 56.0)])
        self.assertEqual(tuple(out[0]), (58.0, 56.0))
        self.assertAlmostEqual(out[-1][0], 59.0)
        self.assertTrue(1100 < len(out) < 1130)
        self.assertTrue(np.all(np.diff(out[:, 0]) > 0))

    def test_great_circle_bulges_to_pole(self):
        # Дуга между точками одной параллели идёт севернее её.
        out = ft.densify([(60.0, 0.0), (60.0, 40.0)], step=10000.0)
        self.assertGreater(out[:, 0].max(), 61.0)

    def test_point_cap(self):
        out = ft.densify([(0.0, 0.0), (0.0, 90.0)], max_points=500)
        self.assertLessEqual(len(out), 500)

    def test_closed_ring_returns_to_start_without_repeat(self):
        ring = [(0.0, 0.0), (0.0, 0.01), (0.01, 0.01)]
        out = ft.densify(ring, closed=True, step=200.0)
        self.assertEqual(tuple(out[0]), (0.0, 0.0))
        self.assertFalse(np.allclose(out[-1], out[0]))

    def test_short(self):
        self.assertEqual(len(ft.densify([(1.0, 2.0)])), 1)


class TestLift(unittest.TestCase):

    def test_heights_and_center(self):
        latlon = np.array([[58.0, 56.0], [58.01, 56.01]])
        xyz = ft.lift(latlon, lambda lat, lon: 150.0)
        lat, lon, h = el.ecef_to_geodetic(xyz[0])
        self.assertAlmostEqual(float(h), 150.0, 3)
        center, offsets = ft.centered(xyz)
        self.assertEqual(offsets.dtype, np.float32)
        # Смещения малы, float32 их держит до сантиметров.
        back = center + offsets.astype(np.float64)
        self.assertLess(np.abs(back - xyz).max(), 0.01)


class TestLiftAndWalls(unittest.TestCase):

    def test_offset_above_terrain(self):
        xyz = ft.lift([(58.0, 56.0)], lambda lat, lon: 150.0, offset=40.0)
        self.assertAlmostEqual(float(el.ecef_to_geodetic(xyz[0])[2]),
                               190.0, 3)

    def test_wall_quads(self):
        # Линия из трёх точек: два отрезка, по два треугольника.
        tri = ft.walls(3)
        self.assertEqual(len(tri), 12)
        self.assertEqual(list(tri[:6]), [0, 1, 4, 0, 4, 3])
        # Замкнутый контур добавляет стену от последней точки к первой.
        closed = ft.walls(3, closed=True)
        self.assertEqual(len(closed), 18)
        self.assertEqual(list(closed[-6:]), [2, 0, 3, 2, 3, 5])
        self.assertEqual(len(ft.walls(1)), 0)

    def test_shape_defaults_on_ground(self):
        shape = ft.Shape("line", [(58.0, 56.0), (58.1, 56.1)])
        self.assertEqual((shape.height, shape.extrude), (0.0, False))


class TestSegments(unittest.TestCase):

    def test_open_and_closed(self):
        self.assertEqual(list(ft.segments(3)), [0, 1, 1, 2])
        self.assertEqual(list(ft.segments(3, closed=True)),
                         [0, 1, 1, 2, 2, 0])


class TestTriangulate(unittest.TestCase):

    def area(self, p, tri):
        total = 0.0
        for i in range(0, len(tri), 3):
            a, b, c = p[tri[i]], p[tri[i + 1]], p[tri[i + 2]]
            total += abs((b[0] - a[0]) * (c[1] - a[1])
                         - (b[1] - a[1]) * (c[0] - a[0])) / 2.0
        return total

    def test_square_both_orders(self):
        sq = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=float)
        for p in (sq, sq[::-1]):
            tri = ft.triangulate(p)
            self.assertEqual(len(tri), 6)
            self.assertAlmostEqual(self.area(p, tri), 1.0)

    def test_concave_l_shape(self):
        p = np.array([[0, 0], [2, 0], [2, 1], [1, 1], [1, 2], [0, 2]],
                     dtype=float)
        tri = ft.triangulate(p)
        self.assertEqual(len(tri), 12)
        self.assertAlmostEqual(self.area(p, tri), 3.0)

    def test_fill_of_large_polygon_is_fast(self):
        # Многоугольник 0.2° × 0.3° сгущается до 800 точек. Резка всего
        # контура шла 1.1 с на каждое движение мыши, у больших - минуты,
        # QGIS висел. Режутся только вершины, 27 сентября 2026 года.
        import time
        corners = [(58.0, 56.0), (58.0, 56.3), (58.2, 56.3), (58.2, 56.0)]
        start = time.perf_counter()
        ring, tri = ft.fill(corners)
        self.assertLess(time.perf_counter() - start, 0.2)
        self.assertEqual(len(tri), 6)
        # Номера треугольников указывают на вершины в сгущённом контуре.
        for i in tri:
            self.assertIn(tuple(ring[i]), corners)

    def test_plane_of_small_polygon(self):
        xy = ft.plane([(58.0, 56.0), (58.0, 56.01), (58.01, 56.01)])
        # 0.01° долготы на 58° - около 590 м.
        self.assertAlmostEqual(abs(xy[1, 0] - xy[0, 0]), 590.0, delta=5.0)


class TestHeightSlider(unittest.TestCase):

    def test_ends_and_round_trip(self):
        self.assertEqual(ft.height_share(0.0), 0.0)
        self.assertAlmostEqual(ft.height_share(ft.MAX_HEIGHT), 1.0)
        self.assertEqual(ft.height_share(-5.0), 0.0)
        for h in (1.0, 36.0, 3600.0, 50000.0):
            self.assertAlmostEqual(ft.share_height(ft.height_share(h)), h,
                                   places=6)

    def test_low_heights_get_room(self):
        # Первая пятая ползунка - до 9 м, половина - до 316 м.
        self.assertLess(ft.share_height(0.2), 10.0)
        self.assertLess(ft.share_height(0.5), 320.0)


class TestGrown(unittest.TestCase):

    LINE = ft.Shape("line", [(0.0, 0.0), (0.0, 10.0), (0.0, 30.0)])

    def test_full_is_same_object(self):
        # Тот же объект - буферы видеокарты не пересобираются.
        self.assertIs(ft.grown(self.LINE, 1.0), self.LINE)

    def test_cut_inside_second_segment(self):
        points = ft.grown(self.LINE, 0.5).points
        self.assertEqual(points[:2], [(0.0, 0.0), (0.0, 10.0)])
        self.assertAlmostEqual(points[2][1], 15.0, 6)
        self.assertAlmostEqual(points[2][0], 0.0, 6)

    def test_cut_inside_first_segment(self):
        points = ft.grown(self.LINE, 0.1).points
        self.assertEqual(len(points), 2)
        self.assertAlmostEqual(points[1][1], 3.0, 6)

    def test_start_is_still_a_line(self):
        points = ft.grown(self.LINE, 0.0).points
        self.assertEqual(len(points), 2)
        self.assertLess(points[1][1], 0.1)

    def test_other_kinds_untouched(self):
        polygon = ft.Shape("polygon", [(0, 0), (0, 1), (1, 1)])
        self.assertIs(ft.grown(polygon, 0.3), polygon)


if __name__ == "__main__":
    unittest.main()


class TestHoles(unittest.TestCase):
    """Многоугольник с дырой: заливка обходит дыру, контур и стены -
    у каждого кольца."""

    OUTER = [(0.0, 0.0), (0.0, 0.01), (0.01, 0.01), (0.01, 0.0)]
    HOLE = [(0.004, 0.004), (0.004, 0.006), (0.006, 0.006),
            (0.006, 0.004)]

    def _area(self, geo):
        xy = ft.plane(geo.ring)
        tri = xy[geo.triangles.reshape(-1, 3)]
        a, b, c = tri[:, 0], tri[:, 1], tri[:, 2]
        return float(np.abs((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1])
                            - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))
                     .sum() / 2.0)

    def test_fill_leaves_hole_open(self):
        whole = ft.geometry(ft.Shape("polygon", self.OUTER,
                                     fill=(255, 255, 255, 60)))
        holed = ft.geometry(ft.Shape("polygon", self.OUTER,
                                     fill=(255, 255, 255, 60),
                                     holes=(self.HOLE,)))
        share = self._area(holed) / self._area(whole)
        self.assertAlmostEqual(share, 0.96, places=2)
        # Середина дыры не лежит ни в одном треугольнике заливки.
        both = ft.plane(np.vstack([holed.ring, [[0.005, 0.005]]]))
        xy, middle = both[:-1], both[-1]
        for a, b, c in xy[holed.triangles.reshape(-1, 3)]:
            self.assertFalse(ft._inside(middle, a, b, c)
                             or ft._inside(middle, a, c, b))
        # Отрезки: контур и дыра замкнуты каждый сам по себе.
        self.assertEqual(len(holed.lines) // 2, len(holed.ring))

    def test_walls_go_round_every_ring(self):
        geo = ft.geometry(ft.Shape("polygon", self.OUTER, height=10.0,
                                   extrude=True, holes=(self.HOLE,)))
        n = len(geo.ring)
        self.assertEqual(len(geo.wall) // 6, n)
        self.assertEqual(int(geo.wall.max()), 2 * n - 1)


class TestAltitudeModes(unittest.TestCase):
    """Режимы высоты меток, core.features.MODES."""

    def setUp(self):
        # Рельеф с дном моря -100 м, поверхность - вода на нуле.
        self.floor = lambda la, lo: np.full(len(la), -100.0)
        self.surface = lambda la, lo: np.zeros(len(la))

    def top(self, mode, height, scale=1.0):
        shape = ft.Shape("point", [(0.0, 0.0)], height=height,
                               extrude=True, mode=mode)
        geo = ft.geometry(shape)
        xyz = ft.vertices(geo, height, self.floor, mode=mode,
                                surface_at=self.surface, scale=scale)
        return float(np.linalg.norm(xyz[0])) - el.A, \
            float(np.linalg.norm(xyz[1])) - el.A

    def test_heights_by_mode(self):
        cases = ((ft.RELATIVE, 30.0, 30.0),
                 (ft.RELATIVE_FLOOR, 30.0, -70.0),
                 (ft.ABSOLUTE, 30.0, 60.0))
        for mode, height, expected in cases:
            top, foot = self.top(mode, height, scale=2.0)
            self.assertAlmostEqual(top, expected, places=3, msg=mode)
            # Стена идёт до поверхности, над морем - до воды.
            self.assertAlmostEqual(foot, 0.0, places=3, msg=mode)

    def test_clamp_modes_ignore_height(self):
        line = ft.Shape("line", [(0.0, 0.0), (0.0, 0.001)],
                              height=500.0, mode=ft.SEAFLOOR)
        geo = ft.geometry(line)
        xyz = ft.vertices(geo, 500.0, self.floor,
                                mode=ft.SEAFLOOR,
                                surface_at=self.surface)
        self.assertAlmostEqual(float(np.linalg.norm(xyz[0])) - el.A,
                               -100.0, places=3)

    def test_old_records_keep_meaning(self):
        """Метка без режима: с подъёмом - относительно поверхности."""
        self.assertEqual(ft.altitude_mode(
            ft.Shape("point", [(0, 0)], height=10.0)),
            ft.RELATIVE)
        self.assertEqual(ft.altitude_mode(
            ft.Shape("point", [(0, 0)])), ft.CLAMP)
