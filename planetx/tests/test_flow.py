# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Струйки ветра и течений: поле, частицы, следы."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import flow  # noqa: E402


def uniform_field(u, v, land=None):
    """Поле 1° на весь шар, u и v постоянны, land - строки без данных."""
    uu = np.full((181, 360), u, dtype=np.float32)
    vv = np.full((181, 360), v, dtype=np.float32)
    if land is not None:
        uu[land] = np.nan
        vv[land] = np.nan
    return flow.VectorGrid(uu, vv, -180.0, 90.0, 1.0)


class TestFlow(unittest.TestCase):

    def test_sample_wraps_longitude(self):
        field = uniform_field(3.0, -2.0)
        u, v = field.sample([10.0, -45.5], [179.7, -179.9])
        self.assertTrue(np.allclose(u, 3.0))
        self.assertTrue(np.allclose(v, -2.0))

    def test_particles_move_east_with_westerly(self):
        field = uniform_field(10.0, 0.0)
        p = flow.Particles(200, seed=1)
        p.reset((0.0, -10.0, 20.0, 10.0))
        start = p.lons[:, 0].copy()
        p.age[:] = 0
        p.life[:] = 1000
        scale = flow.metres_per_mps(2.0e6, 10.0)
        p.step(field, 1.0, scale)
        moved = p.lons[:, 0] - start
        kept = moved > 0.0
        # 12 % от 2000 км - 240 км, у экватора около 2.2°.
        self.assertTrue(np.all(moved[kept] < 2.3))
        self.assertGreater(float(np.median(moved[kept])), 2.0)
        self.assertTrue(np.allclose(p.lats[kept, 0], p.lats[kept, 1]))

    def test_particles_on_land_respawn(self):
        field = uniform_field(1.0, 1.0, land=slice(0, 181))
        p = flow.Particles(50, seed=2)
        p.reset((0.0, -10.0, 20.0, 10.0))
        p.step(field, 1.0, 1000.0)
        self.assertTrue(np.all(p.age == 0))

    def test_spawn_inside_box_across_date_line(self):
        rng = np.random.default_rng(3)
        lats, lons = flow.spawn(1000, (170.0, -5.0, -170.0, 5.0), rng)
        self.assertTrue(np.all(flow.inside(lats, lons,
                                           (170.0, -5.0, -170.0, 5.0))))
        self.assertTrue(np.all((lons >= 170.0) | (lons <= -170.0)))

    def test_segments_follow_trail(self):
        field = uniform_field(0.0, 5.0)
        p = flow.Particles(10, seed=4)
        # Рамка с запасом: за 10 шагов частица уходит на 4.5° к северу.
        p.reset((0.0, -60.0, 20.0, 30.0))
        p.age[:] = 0
        p.life[:] = 1000
        for _ in range(flow.TRAIL + 2):
            p.step(field, 1.0, 10000.0)
            p.box = (0.0, -60.0, 20.0, 60.0)
        pairs, share, speed = flow.segments(p)
        self.assertEqual(len(pairs), 10 * (flow.TRAIL - 1))
        self.assertTrue(np.all(pairs[:, 0, 0] > pairs[:, 1, 0]))
        self.assertAlmostEqual(float(share.max()),
                               (flow.TRAIL - 2) / (flow.TRAIL - 1.0))
        self.assertTrue(np.allclose(speed, 5.0))

    def test_current_day_clamps_to_series(self):
        last = "2026-09-28"
        self.assertEqual(flow.current_day(None, last), last)
        self.assertEqual(flow.current_day(
            flow.day_seconds("2020-07-15"), last), "2020-07-15")
        self.assertEqual(flow.current_day(
            flow.day_seconds("2026-10-11"), last), last)
        self.assertEqual(flow.current_day(
            flow.day_seconds("2001-01-01"), last), flow.CURRENTS_FIRST)

    def test_current_colors(self):
        colors = flow.current_colors([0.0, 0.4, 10.0])
        self.assertEqual(tuple(colors[1]), (40.0, 200.0, 170.0))
        self.assertEqual(tuple(colors[2]), (230.0, 40.0, 70.0))

    def test_speed_fill_tile(self):
        # Заливка скорости под струйками течений: суша прозрачна, быстрая
        # вода непрозрачнее медленной, цвет с премноженной альфой.
        row = [0.05, 0.05, 1.0, 1.0, np.nan, np.nan]
        u = np.array([row, row])
        grid = flow.VectorGrid(u, np.zeros_like(u), 0.0, 1.0, 1.0)
        lats = np.array([[0.5, 0.5, 0.5]])
        lons = np.array([[0.5, 2.5, 4.5]])
        rgba = flow.speed_rgba(flow.fill_job(grid), lats, lons)
        self.assertEqual(rgba.shape, (1, 3, 4))
        slow, fast, land = rgba[0]
        self.assertEqual(land[3], 0)
        self.assertLess(slow[3], fast[3])
        self.assertTrue(np.all(fast[:3] <= fast[3]))

    def test_cap_spawn_stays_in_visible_circle(self):
        # Издалека частицы рождаются в видимом круге Земли. Прежде
        # прямоугольник широт и долгот с 12 800 км захватывал обратную
        # сторону шара, видна была треть частиц, 12 октября 2026 года.
        rng = np.random.default_rng(3)
        box = flow.cap_box(35.0, -40.0, 60.0)
        lats, lons = flow.spawn(20000, box, rng)
        self.assertTrue(np.all(flow.inside(lats, lons, box)))
        # Равномерно по площади: в круге половинной площади - половина.
        half = np.degrees(np.arccos(0.5 * (1.0 + np.cos(np.radians(60.0)))))
        share = np.mean(flow.inside(lats, lons,
                                    flow.cap_box(35.0, -40.0, half)))
        self.assertAlmostEqual(share, 0.5, delta=0.02)
        # Точка за кругом снаружи, круг через линию перемены дат.
        self.assertFalse(flow.inside(np.array([35.0]), np.array([140.0]),
                                     box)[0])
        pacific = flow.cap_box(0.0, 179.0, 10.0)
        self.assertTrue(flow.inside(np.array([0.0]), np.array([-175.0]),
                                    pacific)[0])

    def test_far_view_step_stays_inside_cell_share(self):
        # Издалека типичная скорость за шаг проходит не больше
        # CELL_SHARE клетки поля, иначе след петлял через вихри, снимок
        # автора от 12 октября 2026 года. На прежней скорости по доле
        # ширины вида шаг с 13 000 км - 1.1 клетки 0.5°.
        dt, typical, step = 0.04, 0.3, 0.5
        cell = np.radians(step) * flow.RADIUS
        far = flow.display_metres(1.3e7, typical, step, dt, flow.CELL_SHARE)
        self.assertLessEqual(far * typical * dt / cell,
                             flow.CELL_SHARE + 1e-9)
        # Вблизи предел не действует: доля ширины вида прежняя.
        near = flow.display_metres(5.0e5, typical, step, dt, flow.CELL_SHARE)
        self.assertAlmostEqual(near, flow.metres_per_mps(5.0e5, typical))
        # Без доли - прежняя скорость.
        self.assertAlmostEqual(flow.display_metres(1.3e7, typical, step, dt),
                               flow.metres_per_mps(1.3e7, typical))


if __name__ == "__main__":
    unittest.main()
