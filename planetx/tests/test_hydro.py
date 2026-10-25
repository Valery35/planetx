# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вода по рельефу: уровень перелива, затопление, линия стока,
водосбор и его контур."""
import heapq
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import hydro  # noqa: E402

R = 6378137.0


def minimax(z, seed):
    """Уровень перелива перебором: Дейкстра с наибольшим рельефом пути
    вместо суммы, восемь соседей."""
    rows, cols = z.shape
    out = np.full(z.shape, np.inf)
    out[seed] = z[seed]
    heap = [(z[seed], seed)]
    while heap:
        level, (r, c) = heapq.heappop(heap)
        if level > out[r, c]:
            continue
        for dr in (-1, 0, 1):
            for dc in (-1, 0, 1):
                rr, cc = r + dr, c + dc
                if (dr or dc) and 0 <= rr < rows and 0 <= cc < cols \
                        and np.isfinite(z[rr, cc]):
                    new = max(level, z[rr, cc])
                    if new < out[rr, cc]:
                        out[rr, cc] = new
                        heapq.heappush(heap, (new, (rr, cc)))
    return out


def two_pits():
    """Две котловины с дном 0 м, между ними седловина 5 м, вокруг 20 м."""
    z = np.full((21, 41), 20.0)
    yy, xx = np.mgrid[0:21, 0:41]
    for cx in (10, 30):
        d = np.hypot(yy - 10, xx - cx)
        z = np.where(d < 9, 0.0, z)
    # Седловина 5 м между котловинами.
    z[10, 18:23] = 5.0
    return z


class TestSpill(unittest.TestCase):
    def test_matches_minimax_search(self):
        rng = np.random.default_rng(3)
        z = rng.random((30, 37)) * 50.0
        z[5, 7] = np.nan
        z[12:14, 20] = np.nan
        levels = hydro.spill_levels(z, (15, 15))
        ref = minimax(z, (15, 15))
        finite = np.isfinite(ref)
        np.testing.assert_allclose(levels[finite], ref[finite], atol=1e-9)
        self.assertTrue(np.isinf(levels[~finite]).all())

    def test_ridge_keeps_other_pit_dry(self):
        z = two_pits()
        levels = hydro.spill_levels(z, (10, 10))
        low = hydro.flood(z, levels, 4.0, 10.0)
        self.assertTrue(low.mask[10, 10])
        self.assertFalse(low.mask[10, 30])
        self.assertFalse(low.edge)
        high = hydro.flood(z, levels, 6.0, 10.0)
        self.assertTrue(high.mask[10, 30])
        self.assertAlmostEqual(high.depth, 6.0)

    def test_volume_is_depth_times_cell(self):
        z = np.full((5, 5), 10.0)
        z[2, 2] = 7.0
        z[2, 3] = 8.0
        levels = hydro.spill_levels(z, (2, 2))
        f = hydro.flood(z, levels, 9.0, 2.0)
        self.assertEqual(int(f.mask.sum()), 2)
        self.assertAlmostEqual(f.area, 8.0)
        self.assertAlmostEqual(f.volume, (2.0 + 1.0) * 4.0)

    def test_point_above_level_floods_nothing(self):
        z = two_pits()
        levels = hydro.spill_levels(z, (0, 0))
        self.assertFalse(hydro.flood(z, levels, 19.0, 10.0).mask.any())

    def test_water_nodes_keep_narrow_channel(self):
        mask = np.zeros((10, 10), dtype=bool)
        mask[:, 5] = True
        stride, wet = hydro.water_nodes(mask, side=5)
        self.assertEqual(stride, 2)
        self.assertEqual(wet.shape, (5, 5))
        self.assertTrue(wet[:, 2].all())
        self.assertEqual(int(wet.sum()), 5)


class TestGrid(unittest.TestCase):
    def test_index_round_trip_and_ground_step(self):
        grid = hydro.make_grid(58.0, 56.2, 5000.0, 10.0, R)
        self.assertEqual(grid.rows % 2, 1)
        r, c = hydro.index_of(grid, 58.0, 56.2, R)
        self.assertEqual((r, c), (grid.rows // 2, grid.cols // 2))
        lat, lon = hydro.latlon(grid, r, c + 1, R)
        east = math.radians(lon - 56.2) * R * math.cos(math.radians(58.0))
        self.assertAlmostEqual(east, grid.cell, delta=0.01)
        self.assertLessEqual(grid.rows, hydro.SIDE + 1)


class TestFlow(unittest.TestCase):
    def test_line_runs_down_ramp_to_edge(self):
        yy, xx = np.mgrid[0:20, 0:30]
        z = 100.0 - xx * 1.0 + yy * 0.01
        line = hydro.flow_line(z, (10, 3), 5.0)
        self.assertEqual(line.end, "edge")
        self.assertEqual(int(line.cols[-1]), 29)
        self.assertAlmostEqual(line.length, 26 * 5.0, delta=1.0)
        self.assertGreater(line.drop, 25.0)

    def test_line_ends_in_pit_area_after_fill(self):
        z = two_pits()
        line = hydro.flow_line(z, (10, 14), 1.0)
        self.assertEqual(line.end, "edge")

    def test_watershed_of_valley_and_outline(self):
        yy, xx = np.mgrid[0:41, 0:41]
        # Долина на юг: склоны к оси x = 20, уклон оси к нижнему краю.
        z = np.abs(xx - 20) * 2.0 + (40 - yy) * 0.5 + 10.0
        basin = hydro.watershed(z, (38, 21), 10.0)
        self.assertEqual(basin.seed[1], 20)
        self.assertGreaterEqual(basin.seed[0], 38)
        self.assertGreater(int(basin.mask.sum()), 41 * 30)
        self.assertTrue(basin.mask[0, 20])
        self.assertTrue(basin.edge)
        self.assertGreater(basin.report["stream_km"], 0.3)
        rings = hydro.outline(basin.mask)
        ring = rings[0]
        area = 0.5 * abs(np.dot(ring[:, 0], np.roll(ring[:, 1], 1))
                         - np.dot(ring[:, 1], np.roll(ring[:, 0], 1)))
        self.assertAlmostEqual(area, basin.mask.sum(),
                               delta=0.05 * basin.mask.sum())

    def test_catchment_of_line_across_valley(self):
        # Линия поперёк долины на юг перехватывает всё, что выше неё.
        grid = hydro.make_grid(50.0, 30.0, 400.0, 10.0, R)
        n = grid.rows
        yy, xx = np.mgrid[0:n, 0:n]
        z = np.abs(xx - n // 2) * 2.0 + (n - yy) * 0.5 + 10.0
        lat_a, lon_a = hydro.latlon(grid, 60, 10, R)
        lat_b, lon_b = hydro.latlon(grid, 60, n - 11, R)
        seeds, length = hydro.shape_seeds(
            grid, "line", [(float(lat_a), float(lon_a)),
                           (float(lat_b), float(lon_b))], R)
        self.assertEqual(len(seeds), n - 20)
        self.assertAlmostEqual(length, (n - 21) * grid.cell, delta=1.0)
        result = hydro.shape_catchment(z, seeds, grid.cell, length)
        self.assertTrue(result.mask[0, n // 2])
        self.assertFalse(result.mask[n - 1, n // 2])
        self.assertTrue(result.edge)
        self.assertGreater(result.report["area_km2"], 0.0)

    def test_polygon_seeds_cover_inside(self):
        grid = hydro.make_grid(50.0, 30.0, 200.0, 10.0, R)
        ring = [hydro.latlon(grid, r, c, R) for r, c in
                ((10, 10), (10, 30), (30, 30), (30, 10))]
        seeds, _ = hydro.shape_seeds(
            grid, "polygon", [(float(a), float(b)) for a, b in ring], R)
        self.assertIn(20 * grid.cols + 20, seeds)
        self.assertGreaterEqual(len(seeds), 21 * 21 - 5)

    def test_rivers_join_into_higher_order(self):
        # Две долины сходятся в одну: два звена порядка 1 и звено 2.
        n = 61
        yy, xx = np.mgrid[0:n, 0:n]
        left = np.abs(xx - 15) + np.abs(yy - 45) * 0.0
        right = np.abs(xx - 45)
        z = np.where(yy < 40, np.minimum(left, right), np.abs(xx - 30))
        z = z * 2.0 + (n - yy) * 1.0
        streams = hydro.rivers(z, 10.0, area=20 * 100.0)
        orders = sorted({s.order for s in streams})
        self.assertIn(1, orders)
        self.assertIn(2, orders)
        for s in streams:
            self.assertGreater(len(s.rows), 1)
        # Порядок от 2 оставляет только звенья ниже слияния, порядок
        # у них прежний - он считается по всей сети.
        trunk = hydro.rivers(z, 10.0, area=20 * 100.0, order=2)
        self.assertTrue(trunk)
        self.assertEqual({s.order for s in trunk},
                         {o for o in orders if o >= 2})
        self.assertLess(len(trunk), len(streams))

    def test_line_stops_on_stream(self):
        # Долина на юг: линия со склона кончается на оси долины.
        yy, xx = np.mgrid[0:41, 0:41]
        z = np.abs(xx - 20) * 2.0 + (40 - yy) * 0.5 + 10.0
        whole = hydro.flow_line(z, (10, 5), 10.0)
        self.assertEqual(whole.end, "edge")
        line = hydro.flow_line(z, (10, 5), 10.0, area=60 * 100.0)
        self.assertEqual(line.end, "stream")
        self.assertLessEqual(abs(int(line.cols[-1]) - 20), 1)
        self.assertLess(line.length, whole.length)

    def test_line_stops_on_flattening(self):
        # Крутой склон 30° на 20 ячеек, дальше равнина 0.5°.
        x = np.arange(60, dtype=np.float64)
        profile = np.where(x < 20, (20 - x) * 10.0 * math.tan(
            math.radians(30.0)), 0.0) - x * 10.0 * math.tan(
            math.radians(0.5))
        z = np.tile(profile, (21, 1)) + np.abs(
            np.arange(21) - 10)[:, None] * 0.001
        whole = hydro.flow_line(z, (10, 2), 10.0)
        line = hydro.flow_line(z, (10, 2), 10.0, flat=(2.0, 50.0))
        self.assertEqual(line.end, "flat")
        self.assertLess(line.length, whole.length)
        self.assertLessEqual(abs(int(line.cols[-1]) - 20), 2)

    def test_flattening_with_step_not_dividing_window(self):
        # Шаг 16.7 м не делит окно 50 м: прежде уклон окна не мерился.
        cell = 16.7
        x = np.arange(80, dtype=np.float64)
        profile = np.where(x < 20, (20 - x) * cell * math.tan(
            math.radians(30.0)), 0.0) - x * cell * math.tan(
            math.radians(0.5))
        z = np.tile(profile, (21, 1)) + np.abs(
            np.arange(21) - 10)[:, None] * 0.001
        line = hydro.flow_line(z, (10, 2), cell, flat=(2.0, 50.0))
        self.assertEqual(line.end, "flat")
        self.assertLessEqual(abs(int(line.cols[-1]) - 20), 2)

    def test_lines_from_shape_merge(self):
        # Линии от многих узлов поперёк склона долины сливаются в одну.
        yy, xx = np.mgrid[0:41, 0:41]
        z = np.abs(xx - 20) * 2.0 + (40 - yy) * 0.5 + 10.0
        seeds = [10 * 41 + c for c in range(2, 39)]
        apart = hydro.flow_lines(z, seeds, 10.0)
        joined = hydro.flow_lines(z, seeds, 10.0, merge=True)
        self.assertEqual(len(apart), len(seeds))
        self.assertLessEqual(len(joined), len(seeds))
        ends = {line.end for line in joined}
        self.assertIn("merge", ends)
        self.assertIn("edge", ends)
        cells = [set(zip(l.rows.tolist(), l.cols.tolist()))
                 for l in joined]
        # Узел принадлежит одной линии, кроме узла слияния.
        total = sum(len(c) for c in cells)
        merged = sum(1 for l in joined if l.end == "merge")
        self.assertEqual(len(set().union(*cells)), total - merged)

    def test_outlet_basins_split_square(self):
        # Хребет посередине: две долины, два устья у нижнего края.
        n = 41
        yy, xx = np.mgrid[0:n, 0:n]
        z = np.minimum(np.abs(xx - 10), np.abs(xx - 30)) * 2.0 \
            + (n - yy) * 0.5
        regions = hydro.outlet_basins(z, 10.0, area=100 * 100.0)
        self.assertEqual(len(regions), 2)
        left, right = sorted(regions, key=lambda r: np.argwhere(
            r.mask)[:, 1].mean())
        self.assertTrue(left.mask[0, 10])
        self.assertTrue(right.mask[0, 30])
        self.assertFalse(left.mask[0, 30])
        self.assertAlmostEqual(left.area, left.mask.sum() * 100.0)

    def test_shape_grid_covers_shape(self):
        lat, lon, side = hydro.shape_grid([(50.0, 30.0), (50.01, 30.0)], R)
        self.assertAlmostEqual(lat, 50.005)
        self.assertAlmostEqual(side, 2000.0)
        _, _, side = hydro.shape_grid([(50.0, 30.0), (50.2, 30.0)], R)
        self.assertAlmostEqual(side, 3 * 0.1 * math.pi / 180.0 * R,
                               delta=1.0)

    def test_simplify_keeps_corners_on_line_of_ring_ends(self):
        # Кольцо начинается посередине длинной стороны, концы цепочки
        # соседние. Дуглас-Пекер до прямой через них выбрасывал углы на
        # этой прямой, и у водосбора Баксана вышел отрезок 13.8 км.
        ring = np.array([(0.0, x) for x in range(5, 101)]
                        + [(1.0, 100.0), (2.0, 100.0)]
                        + [(2.0, x) for x in range(99, -1, -1)]
                        + [(1.0, 0.0)] + [(0.0, x) for x in range(0, 5)],
                        dtype=np.float64)
        kept = hydro.simplify(ring, 0.5)
        corners = {(0.0, 100.0), (2.0, 100.0), (2.0, 0.0), (0.0, 0.0)}
        self.assertTrue(corners <= {tuple(p) for p in kept})

    def test_outline_of_square_is_four_corners(self):
        mask = np.zeros((10, 10), dtype=bool)
        mask[2:6, 3:8] = True
        ring = hydro.outline(mask)[0]
        self.assertLessEqual(len(ring), 8)
        self.assertAlmostEqual(ring[:, 0].min(), 1.5)
        self.assertAlmostEqual(ring[:, 1].max(), 7.5)


if __name__ == "__main__":
    unittest.main()
