# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тела: Земля, Марс, Луна. Размеры тела меняются во всём ядре."""
import ast
import math
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import ellipsoid as el  # noqa: E402
import lod  # noqa: E402
import measure  # noqa: E402


class BodyCase(unittest.TestCase):

    def tearDown(self):
        el.set_body(el.EARTH)
        lod.clear_cache()


class TestBodies(BodyCase):

    def test_radius_of_each_body(self):
        for body, radius in ((el.EARTH, 6378137.0), (el.MARS, 3396190.0),
                             (el.MOON, 1737400.0)):
            el.set_body(body)
            p = el.geodetic_to_ecef(0.0, 0.0, 0.0)
            self.assertAlmostEqual(float(np.linalg.norm(p)), radius, places=3)

    def test_round_trip_on_spheres(self):
        for body in (el.MARS, el.MOON):
            el.set_body(body)
            lat, lon, h = 18.65, -133.8, 21900.0  # Олимп на Марсе
            back = el.ecef_to_geodetic(el.geodetic_to_ecef(lat, lon, h))
            self.assertAlmostEqual(float(back[0]), lat, places=9)
            self.assertAlmostEqual(float(back[1]), lon, places=9)
            self.assertAlmostEqual(float(back[2]), h, places=4)

    def test_measures_follow_the_body(self):
        # Дуга в 1° по экватору - доля окружности текущего тела.
        for body in el.BODIES:
            el.set_body(body)
            length = measure.sphere_length([(0.0, 0.0), (0.0, 1.0)])
            self.assertAlmostEqual(length, 2.0 * math.pi * body.a / 360.0,
                                   delta=1e-6 * body.a)

    def test_tile_size_follows_the_body(self):
        el.set_body(el.EARTH)
        lod.clear_cache()
        earth = lod.tile_info(3, 4, 3).texel
        el.set_body(el.MOON)
        lod.clear_cache()
        moon = lod.tile_info(3, 4, 3).texel
        self.assertAlmostEqual(moon / earth, el.MOON.a / el.EARTH.a,
                               places=9)

    def test_unknown_key_is_earth(self):
        self.assertIs(el.body_by_key("pluto"), el.EARTH)
        self.assertIs(el.body_by_key("mars"), el.MARS)


def stale_imports(root):
    """Модули, которые копируют полуоси тела при импорте. После смены
    тела такая копия остаётся земной."""
    out = []
    for folder, _, files in os.walk(root):
        if "tests" in folder:
            continue
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module \
                        and node.module.split(".")[-1] == "ellipsoid":
                    names = {a.name for a in node.names}
                    if names & {"A", "B", "E2", "EP2", "F", "BODY"}:
                        out.append("%s:%d" % (name, node.lineno))
    return out


class TestImagery(unittest.TestCase):
    """Снимки Марса и Луны OpenPlanetaryMap лежат в разметке TMS.

    С рядами XYZ Луна 30 сентября 2026 года вышла полосами по широте.
    """

    def test_mars_and_moon_are_tms(self):
        import planets
        for planet in (planets.MARS_PLANET, planets.MOON_PLANET):
            self.assertIn("{-y}", planet.imagery[1], planet.key)


class TestNoStaleCopies(unittest.TestCase):

    def test_plugin_reads_axes_at_run_time(self):
        root = os.path.dirname(CORE)
        self.assertEqual(stale_imports(root), [])

    def test_guard_catches_a_copy(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            with open(os.path.join(folder, "bad.py"), "w",
                      encoding="utf-8") as fh:
                fh.write("from .ellipsoid import A\n")
            self.assertEqual(stale_imports(folder), ["bad.py:1"])


if __name__ == "__main__":
    unittest.main()
