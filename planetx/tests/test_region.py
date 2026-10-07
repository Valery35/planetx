# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/region.py: Region KML и скрытие дальше расстояния."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import region as rg  # noqa: E402
from ellipsoid import geodetic_to_ecef  # noqa: E402


def eye(lat, lon, height):
    return geodetic_to_ecef(lat, lon, height)


class TestRegion(unittest.TestCase):

    def test_distance_field_hides_beyond_km(self):
        # Метка в Перми, скрывать дальше 50 км: видна с 40 км, не видна
        # с 60 км, при любом окне глобуса.
        place = [(58.0105, 56.2294)]
        region = rg.for_distance(place, 50.0)
        self.assertAlmostEqual(rg.distance_km(region), 50.0, places=3)
        self.assertTrue(rg.active(region, eye(58.0105, 56.2294, 40000.0)))
        self.assertFalse(rg.active(region, eye(58.0105, 56.2294, 60000.0)))
        # Рамка точки - около BOX_SIDE метров.
        self.assertAlmostEqual(rg.side(region), rg.BOX_SIDE, delta=5.0)

    def test_max_lod_hides_close(self):
        # maxLodPixels: вблизи рамка больше предела - метка скрыта.
        region = rg.Region(58.1, 57.9, 56.4, 56.0, 0.0, 128.0)
        self.assertFalse(rg.active(region, eye(58.0, 56.2, 10000.0)))
        self.assertTrue(rg.active(region, eye(58.0, 56.2, 1000000.0)))
        self.assertTrue(rg.active(None, eye(0.0, 0.0, 1.0)))

    def test_edit_keeps_box_and_max_lod(self):
        old = rg.Region(58.1, 57.9, 56.4, 56.0, 300.0, 4000.0)
        new = rg.for_distance([(0.0, 0.0)], 20.0, old)
        self.assertEqual(new[:4], old[:4])
        self.assertEqual(new.max_lod, 4000.0)
        self.assertAlmostEqual(rg.distance_km(new), 20.0, places=3)

    def test_box_over_dateline(self):
        region = rg.Region(10.0, 0.0, -179.0, 179.0, 0.0, -1.0)
        width, _ = rg._span(region)
        self.assertAlmostEqual(width, 2.0 * rg.M_PER_DEGREE * 0.9962,
                               delta=500.0)
        self.assertAlmostEqual(rg.center(region)[1] % 360.0, 180.0)

    def test_text_round_trip_and_kml(self):
        region = rg.for_distance([(58.0, 56.0), (58.5, 56.5)], 100.0)
        self.assertEqual(rg.parse(rg.text(region)), region)
        self.assertIsNone(rg.parse(""))
        self.assertIsNone(rg.parse("[1, 2]"))
        self.assertIsNone(rg.parse("не json"))
        self.assertIn("<minLodPixels>", rg.kml(region))
        self.assertEqual(rg.kml(None), "")
        self.assertIsNone(rg.distance_km(rg.Region(1, 0, 1, 0, 0.0, -1)))


if __name__ == "__main__":
    unittest.main()
