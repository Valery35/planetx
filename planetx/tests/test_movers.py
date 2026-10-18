# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Суда Digitraffic и самолёты adsb.lol: разбор ответов и ход."""
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import aircraft  # noqa: E402
import models  # noqa: E402
import movers  # noqa: E402
import trains  # noqa: E402
import vessels  # noqa: E402

# Записи ответов служб от 19 октября 2026 года.
LOCATIONS = {"type": "FeatureCollection", "features": [
    {"mmsi": 230943910, "type": "Feature",
     "geometry": {"type": "Point", "coordinates": [22.385135, 60.420192]},
     "properties": {"mmsi": 230943910, "sog": 12.0, "cog": 90.0,
                    "navStat": 0, "heading": 511, "timestamp": 0,
                    "timestampExternal": 1792356241064}},
    {"mmsi": 1, "type": "Feature",
     "geometry": {"type": "Point", "coordinates": [22.0, 60.0]},
     "properties": {"mmsi": 1, "sog": 102.3, "cog": 360.0,
                    "heading": 45, "timestampExternal": 1792356241064}},
    {"mmsi": 2, "geometry": None, "properties": {"mmsi": 2}}]}
VESSELS = [{"callSign": "5BFU4", "destination": "SE LLA", "imo": 9194098,
            "mmsi": 210547000, "name": "SWE-FREIGHTER ",
            "referencePointA": 83, "referencePointB": 16,
            "referencePointC": 7, "referencePointD": 7, "shipType": 70}]
PLANES = {"now": 1792356307501.0, "ac": [
    {"hex": "4ACA82", "flight": "NSZ1GT  ", "r": "SE-RTB", "t": "B38M",
     "alt_baro": 12375, "gs": 306.0, "track": 87.54,
     "true_heading": 87.63, "baro_rate": -1856, "roll": -0.35,
     "category": "A3", "lat": 60.194554, "lon": 23.450472,
     "seen_pos": 2.5},
    {"hex": "abc", "alt_baro": "ground", "gs": 3.0, "track": 10.0,
     "lat": 60.3, "lon": 24.96, "seen": 1.0},
    {"hex": "nopos", "alt_baro": 1000}]}


class TestVessels(unittest.TestCase):

    def test_locations(self):
        found = {s.key: s for s in vessels.parse_locations(LOCATIONS)}
        self.assertEqual(sorted(found), [1, 230943910])
        ship = found[230943910]
        self.assertAlmostEqual(ship.speed, 12.0 * 1852.0 / 3600.0)
        self.assertEqual(ship.course, 90.0)
        self.assertTrue(math.isnan(ship.heading))
        self.assertAlmostEqual(ship.t, 1792356241.064)
        still = found[1]
        self.assertEqual(still.speed, 0.0)
        self.assertTrue(math.isnan(still.course))
        self.assertEqual(still.heading, 45.0)

    def test_vessels_and_size(self):
        info = vessels.parse_vessels(VESSELS)[210547000]
        self.assertEqual((info.name, info.group), ("SWE-FREIGHTER", "cargo"))
        self.assertEqual(vessels.ship_size(info), (14.0, 99.0, 14.0))
        self.assertEqual(vessels.ship_size(None)[1], 30.0)
        self.assertEqual(vessels.label(5, None), "5")
        self.assertEqual(vessels.group(65), "passenger")
        self.assertEqual(vessels.group(84), "tanker")
        self.assertEqual(vessels.group(37), "pleasure")

    def test_ship_model_unit_length(self):
        parts = models.merge(vessels.unit_ship_parts(vessels.WHITE))
        box = models.bounds(parts)
        self.assertAlmostEqual(box[1, 1] - box[0, 1], 1.0)
        self.assertAlmostEqual(box[0, 2], 0.0)


class TestAircraft(unittest.TestCase):

    def test_parse(self):
        samples, info = aircraft.parse(PLANES)
        found = {s.key: s for s in samples}
        self.assertEqual(sorted(found), ["4aca82", "abc"])
        plane = found["4aca82"]
        self.assertAlmostEqual(plane.alt, 12375 * 0.3048)
        self.assertAlmostEqual(plane.climb, -1856 * 0.3048 / 60.0)
        self.assertAlmostEqual(plane.t, 1792356307.501 - 2.5)
        self.assertEqual(plane.heading, 87.63)
        self.assertEqual(aircraft.label("4aca82", info["4aca82"]),
                         "NSZ1GT")
        self.assertEqual(info["4aca82"].group, "large")
        self.assertTrue(math.isnan(found["abc"].alt))
        self.assertTrue(info["abc"].ground)
        self.assertEqual(aircraft.label("abc", info["abc"]), "ABC")

    def test_url_radius(self):
        self.assertTrue(aircraft.point_url(60.0, 25.0, 1e7).endswith("/250"))
        self.assertTrue(aircraft.point_url(60.0, 25.0, 100.0).endswith("/5"))
        self.assertIn("/60.0000/25.0000/", aircraft.point_url(60, 25, 1e4))

    def test_plane_model(self):
        parts = models.merge(aircraft.unit_plane_parts((1.0, 0.0, 0.0)))
        box = models.bounds(parts)
        self.assertAlmostEqual(box[1, 1] - box[0, 1], 1.0)
        self.assertAlmostEqual(box[1, 0] - box[0, 0], 1.0)
        self.assertEqual(aircraft.plane_size("A5")[1], 64.0)


class TestMovers(unittest.TestCase):

    def test_course_speed_and_climb(self):
        fleet = movers.Movers(extrapolate=30.0)
        fleet.update([movers.Sample("a", 1000.0, 60.0, 25.0, 100.0, 90.0,
                                    math.nan, 1000.0, 5.0)], 0.0,
                     clock=1000.0)
        (_, lat, lon, heading, alt), = fleet.positions(0.0, clock=1010.0)
        self.assertAlmostEqual(trains._metres(60.0, 25.0, lat, lon), 1000.0,
                               delta=0.5)
        self.assertEqual(heading, 90.0)
        self.assertAlmostEqual(alt, 1050.0)
        # Не дольше extrapolate.
        (_, lat, lon, _, alt), = fleet.positions(0.0, clock=2000.0)
        self.assertAlmostEqual(trains._metres(60.0, 25.0, lat, lon), 3000.0,
                               delta=1.0)
        self.assertAlmostEqual(alt, 1150.0)

    def test_view_part_keeps_others_until_stale(self):
        fleet = movers.Movers(stale=100.0)
        fleet.update([movers.Sample("a", 1000.0, 60.0, 25.0)], 0.0,
                     clock=1000.0)
        fleet.update([movers.Sample("b", 1050.0, 61.0, 25.0)], 0.0,
                     clock=1050.0, keep=True)
        self.assertEqual(sorted(fleet.items), ["a", "b"])
        fleet.update([], 0.0, clock=1101.0, keep=True)
        self.assertEqual(sorted(fleet.items), ["b"])
        fleet.update([], 0.0, clock=1102.0)
        self.assertEqual(len(fleet), 0)

    def test_new_sample_blends(self):
        fleet = movers.Movers()
        fleet.update([movers.Sample("a", 1000.0, 60.0, 25.0, 10.0, 0.0)],
                     0.0, clock=1000.0)
        before = fleet.positions(5.0, clock=1010.0)[0]
        fleet.update([movers.Sample("a", 1010.0, 60.002, 25.0, 10.0, 0.0)],
                     5.0, clock=1010.0)
        after = fleet.positions(5.0, clock=1010.0)[0]
        self.assertAlmostEqual(before[1], after[1], places=9)


if __name__ == "__main__":
    unittest.main()
