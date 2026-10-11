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

    def test_current_colors(self):
        colors = flow.current_colors([0.0, 0.5, 10.0])
        self.assertEqual(tuple(colors[1]), (140.0, 255.0, 140.0))
        self.assertEqual(tuple(colors[2]), (255.0, 60.0, 90.0))


if __name__ == "__main__":
    unittest.main()
