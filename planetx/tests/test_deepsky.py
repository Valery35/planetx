# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Объекты глубокого неба: каталог, имена, поиск, ответ Sesame."""
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "core")
sys.path.insert(0, CORE)

import deepsky  # noqa: E402
import searchbar  # noqa: E402

OBJECTS = deepsky.load()
BY_LABEL = {obj.label: obj for obj in OBJECTS}

SESAME = """# M31\t#Q12499889
#=Sc=Simbad (CDS, via client/server):    1   290ms
%@ @1575544
%C.0 AGN
%J 10.68470833 +41.26875000 = 00 42 44.330  +41 16 07.50
%I.0 M  31
%I NGC 224
"""


class TestCatalogue(unittest.TestCase):
    def test_messier_and_famous_objects(self):
        messier = [obj for obj in OBJECTS if deepsky.is_messier(obj)]
        self.assertEqual(len(messier), 109)
        m31 = BY_LABEL["M31"]
        self.assertAlmostEqual(m31.ra, 10.685, places=2)
        self.assertAlmostEqual(m31.dec, 41.269, places=2)
        self.assertEqual(m31.other, "NGC 224")
        self.assertEqual(m31.ru, "Галактика Андромеды")
        self.assertEqual(BY_LABEL["M42"].ru, "Туманность Ориона")
        self.assertIn("NGC 7000", BY_LABEL)

    def test_no_stars_without_messier_number(self):
        for obj in OBJECTS:
            if obj.kind in ("*", "**"):
                self.assertTrue(deepsky.is_messier(obj), obj.label)

    def test_names_and_title(self):
        m31 = BY_LABEL["M31"]
        names = deepsky.names(m31)
        for name in ("M31", "M 31", "NGC 224", "NGC224",
                     "Галактика Андромеды", "Andromeda Galaxy"):
            self.assertIn(name, names)
        self.assertEqual(deepsky.title(m31, "en"), "Andromeda Galaxy")
        self.assertEqual(deepsky.title(BY_LABEL["M40"], "ru"), "M40")

    def test_ngc_only_when_close(self):
        ngc = BY_LABEL["NGC 7000"]
        self.assertTrue(deepsky.shown(BY_LABEL["M31"], 100.0))
        self.assertFalse(deepsky.shown(ngc, deepsky.NGC_FOV + 1.0))
        self.assertTrue(deepsky.shown(ngc, deepsky.NGC_FOV))
        self.assertLess(deepsky.rank(BY_LABEL["M31"]), deepsky.rank(ngc))

    def test_fov_and_radius(self):
        m31 = BY_LABEL["M31"]
        self.assertAlmostEqual(deepsky.fov_for(m31),
                               deepsky.FIT * m31.size / 60.0)
        self.assertEqual(deepsky.fov_for(BY_LABEL["M40"]),
                         deepsky.FOV_UNKNOWN)
        # 178′ при 0.01° на пиксель - около 148 пикселей радиуса.
        import math
        r = deepsky.radius_pixels(m31, math.radians(0.01))
        self.assertAlmostEqual(r, m31.size / 120.0 / 0.01, places=3)

    def test_coordinates_text(self):
        self.assertEqual(deepsky.ra_text(10.68470833), "0h 42m 44s")
        self.assertEqual(deepsky.dec_text(-5.3876), "-5° 23′ 15″")


class TestSearch(unittest.TestCase):
    def setUp(self):
        self.sky = searchbar.sky_objects({}, "ru", OBJECTS)

    def test_found_by_designation_and_name(self):
        for query in ("m31", "M 31", "NGC 224", "ngc224", "андромед"):
            found = searchbar.suggestions(query, sky=self.sky)
            self.assertTrue(found, query)
            self.assertEqual(found[0].kind, "deepsky", query)
            self.assertEqual(OBJECTS[found[0].key].label, "M31", query)

    def test_exact_by_any_name(self):
        found = searchbar.exact("NGC 1976", self.sky)
        self.assertEqual([OBJECTS[s.key].label for s in found], ["M42"])
        self.assertEqual(found[0].text, "Туманность Ориона (M42)")


class TestSesame(unittest.TestCase):
    def test_parse(self):
        ra, dec, name = deepsky.parse_sesame(SESAME)
        self.assertAlmostEqual(ra, 10.68470833)
        self.assertAlmostEqual(dec, 41.26875)
        self.assertEqual(name, "M 31")

    def test_not_found(self):
        self.assertIsNone(deepsky.parse_sesame("# xyz\n#! *** Nothing found"))
        self.assertIsNone(deepsky.parse_sesame(""))

    def test_url(self):
        self.assertEqual(deepsky.sesame_url(" Orion Nebula"),
                         deepsky.SESAME + "Orion%20Nebula")


if __name__ == "__main__":
    unittest.main()
