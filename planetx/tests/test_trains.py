# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поезда Digitraffic: разбор ответов, ход между положениями, рельсы."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import models  # noqa: E402
import routing  # noqa: E402
import trains as tr  # noqa: E402

# Запись ответа train-locations/latest от 18 октября 2026 года.
LATEST = [{"accuracy": 0, "isGpsLocation": True,
           "location": {"type": "Point",
                        "coordinates": [30.098746, 62.214724]},
           "speed": 138, "trainNumber": 9, "departureDate": "2026-10-18",
           "timestamp": "2026-10-18T17:31:33.000Z"},
          {"location": None, "trainNumber": 10,
           "timestamp": "2026-10-18T17:31:33.000Z"}]
TYPES = {"data": {"currentlyRunningTrains": [
    {"trainNumber": 9, "departureDate": "2026-10-18", "commuterLineid": "",
     "trainType": {"name": "S", "trainCategory": {"name": "Long-distance"}},
     "operator": {"shortCode": "vr"}},
    {"trainNumber": 9123, "departureDate": "2026-10-18",
     "commuterLineid": "R",
     "trainType": {"name": "HL", "trainCategory": {"name": "Commuter"}},
     "operator": {"shortCode": "vr"}}]}}
LAT = 60.20  # участок у Хельсинки


def grid_line(points):
    return np.array([routing.to_grid(lat, lon) for lat, lon in points])


class TestParse(unittest.TestCase):

    def test_latest(self):
        found = tr.parse_latest(LATEST)
        self.assertEqual(len(found), 1)
        s = found[0]
        self.assertEqual(s.key, (9, "2026-10-18"))
        self.assertAlmostEqual(s.lat, 62.214724)
        self.assertAlmostEqual(s.speed, 138 / 3.6)
        self.assertEqual(s.t, tr.epoch("2026-10-18T17:31:33Z"))

    def test_epoch_fraction(self):
        self.assertAlmostEqual(tr.epoch("1970-01-01T00:00:01.250Z"), 1.25)
        self.assertIsNone(tr.epoch("вчера"))

    def test_types_and_labels(self):
        info = tr.parse_types(TYPES)
        self.assertEqual(info[(9, "2026-10-18")].category, "Long-distance")
        self.assertEqual(tr.label((9, "2026-10-18"),
                                  info[(9, "2026-10-18")]), "S 9")
        self.assertEqual(tr.label((9123, "2026-10-18"),
                                  info[(9123, "2026-10-18")]), "R 9123")
        self.assertEqual(tr.label((5, ""), None), "5")

    def test_one_train_of_arrived(self):
        # Ответ trains/2026-10-18/8208 - прибывший пригородный поезд.
        found = tr.parse_train([{"trainNumber": 8208,
                                 "departureDate": "2026-10-18",
                                 "trainType": "HL",
                                 "trainCategory": "Commuter",
                                 "commuterLineID": "A",
                                 "operatorShortCode": "vr",
                                 "runningCurrently": False}])
        info = found[(8208, "2026-10-18")]
        self.assertEqual((info.category, info.line), ("Commuter", "A"))
        self.assertEqual(tr.train_url((8208, "2026-10-18")),
                         "https://rata.digitraffic.fi/api/v1/trains/"
                         "2026-10-18/8208")


class TestMotion(unittest.TestCase):

    def sample(self, t, lat, lon, kmh=72.0):
        return tr.Sample((1, "d"), t, lat, lon, kmh / 3.6)

    def test_heading_and_dead_reckoning_without_rails(self):
        fleet = tr.Fleet()
        fleet.update([self.sample(1000.0, LAT, 25.0)], 0.0, clock=1000.0)
        fleet.update([self.sample(1010.0, LAT + 0.001, 25.0)], 0.0,
                     clock=1010.0)
        # Переход кончился, 10 с хода по 20 м/с на север - 200 м.
        (_, lat, lon, heading), = fleet.positions(10.0, clock=1020.0)
        self.assertAlmostEqual(heading, 0.0, places=3)
        metres = tr._metres(LAT + 0.001, 25.0, lat, lon)
        self.assertAlmostEqual(metres, 200.0, delta=0.5)
        # Ход по скорости - не дольше EXTRAPOLATE_MAX.
        (_, lat, lon, _), = fleet.positions(10.0, clock=5000.0)
        metres = tr._metres(LAT + 0.001, 25.0, lat, lon)
        self.assertAlmostEqual(metres, 20.0 * tr.EXTRAPOLATE_MAX, delta=1.0)

    def test_new_sample_blends_without_jump(self):
        fleet = tr.Fleet()
        fleet.update([self.sample(1000.0, LAT, 25.0)], 0.0, clock=1000.0)
        fleet.update([self.sample(1010.0, LAT + 0.001, 25.0)], 0.0,
                     clock=1010.0)
        before = fleet.positions(5.0, clock=1025.0)[0]
        fleet.update([self.sample(1020.0, LAT + 0.002, 25.0)], 5.0,
                     clock=1025.0)
        after = fleet.positions(5.0, clock=1025.0)[0]
        self.assertAlmostEqual(before[1], after[1], places=9)
        later = fleet.positions(5.0 + tr.BLEND, clock=1025.0)[0]
        target = tr.destination(LAT + 0.002, 25.0, 0.0, 20.0 * 5.0)
        self.assertAlmostEqual(later[1], target[0], places=7)

    def test_gone_and_stale_trains_dropped(self):
        fleet = tr.Fleet()
        fleet.update([self.sample(1000.0, LAT, 25.0)], 0.0, clock=1000.0)
        fleet.update([], 0.0, clock=1010.0)
        self.assertEqual(fleet.trains, {})
        fleet.update([self.sample(1000.0, LAT, 25.0)], 0.0,
                     clock=1000.0 + tr.STALE + 1.0)
        self.assertEqual(fleet.trains, {})


class TestRails(unittest.TestCase):

    def setUp(self):
        # Путь на восток, в конце - стрелка: прямо на восток и отворот
        # на северо-восток. Третья линия - отдельный путь в стороне.
        self.a = grid_line([(LAT, 25.00), (LAT, 25.01)])
        self.east = grid_line([(LAT, 25.01), (LAT, 25.02)])
        self.north = grid_line([(LAT, 25.01), (LAT + 0.005, 25.02)])
        self.rails = tr.Rails([np.rint(self.a), np.rint(self.east),
                               np.rint(self.north)])

    def test_snap_and_walk_through_switch(self):
        x, y = routing.to_grid(LAT + 0.0002, 25.005)  # 22 м от пути
        reach = tr.SNAP_REACH / routing.unit_metres(LAT)
        line, s = self.rails.snap(x, y, reach)
        self.assertEqual(line, 0)
        # Курс на восток: за стрелкой ход идёт прямо, не на север.
        pos = self.rails.walk(tr.RailPos(line, s, 1),
                              1000.0 / routing.unit_metres(LAT))
        self.assertEqual(pos.line, 1)
        xy, tangent = self.rails.point(pos.line, pos.s)
        lat, lon = routing.to_latlon(xy)
        self.assertAlmostEqual(float(lat), LAT, places=5)
        self.assertAlmostEqual(tr.grid_heading(tangent), 90.0, delta=0.5)
        self.assertIsNone(self.rails.snap(*routing.to_grid(LAT + 0.01,
                                                           25.005), reach))

    def test_train_follows_rails(self):
        fleet = tr.Fleet()
        fleet.set_rails(self.rails)
        sample = tr.Sample((1, "d"), 1000.0, LAT + 0.0002, 25.004, 20.0)
        fleet.update([sample], 0.0, clock=1000.0)
        moved = tr.Sample((1, "d"), 1010.0, LAT + 0.0002, 25.0076, 20.0)
        fleet.update([moved], 0.0, clock=1010.0)
        (_, lat, lon, heading), = fleet.positions(10.0, clock=1020.0)
        # Притянут к пути и прошёл 200 м по нему на восток.
        self.assertAlmostEqual(lat, LAT, places=5)
        start = tr.destination(LAT, 25.0076, 90.0, 0.0)
        self.assertAlmostEqual(tr._metres(start[0], start[1], lat, lon),
                               200.0, delta=3.0)
        self.assertAlmostEqual(heading, 90.0, delta=0.5)

    def test_cars_bend_along_rails(self):
        # Поезд прошёл стрелку и идёт на северо-восток, хвост ещё на
        # пути с запада: вагон в 300 м позади головы смотрит на восток.
        fleet = tr.Fleet()
        rails = tr.Rails([np.rint(self.a), np.rint(self.north)])
        fleet.set_rails(rails)
        fleet.update([tr.Sample((1, "d"), 1000.0, LAT + 0.0005, 25.011,
                                20.0)], 0.0, clock=1000.0)
        fleet.update([tr.Sample((1, "d"), 1010.0, LAT + 0.00075, 25.0115,
                                20.0)], 0.0, clock=1010.0)
        train = fleet.trains[(1, "d")]
        head = fleet.place(train, 10.0, 1010.0)
        tail = fleet.place(train, 10.0, 1010.0, back=300.0)
        self.assertAlmostEqual(head[2], 44.9, delta=1.0)
        self.assertAlmostEqual(tail[2], 90.0, delta=0.5)
        self.assertAlmostEqual(tail[0], LAT, places=5)
        # По пути от хвоста до головы - 300 м: до стрелки на восток
        # и от стрелки на северо-восток.
        self.assertAlmostEqual(tr._metres(LAT, 25.01, tail[0], tail[1]),
                               300.0 - tr._metres(LAT, 25.01, *head[:2]),
                               delta=3.0)

    def test_end_of_line_stops(self):
        pos = self.rails.walk(tr.RailPos(1, 0.0, 1), 1e9)
        self.assertEqual((pos.line, pos.s), (1, self.rails.lengths[1][-1]))


class TestModel(unittest.TestCase):

    def test_moved_equals_vertices_built_in_place(self):
        parts = models.merge(tr.train_parts(tr.OTHER))
        base = models.frame(0.0, 0.0, 0.0, scale=(2.0, 2.0, 2.0))
        start = models.vertices(parts, 0.0, 0.0, scale=(2.0, 2.0, 2.0))
        linear = models.moved(base, 61.5, 24.0, 135.0,
                              scale=(2.0, 2.0, 2.0))
        there = models.vertices(parts, 61.5, 24.0, 135.0,
                                scale=(2.0, 2.0, 2.0))
        for a, b in zip(start, there):
            self.assertTrue(np.allclose(a["position"] @ linear.T,
                                        b["position"], atol=1e-3))

    def test_car_points_along_y(self):
        parts = models.merge(tr.train_parts(tr.category_color("Cargo")))
        box = models.bounds(parts)
        self.assertAlmostEqual(box[1, 1] - box[0, 1], tr.CAR_LENGTH,
                               delta=0.1)
        self.assertAlmostEqual(box[0, 2], 0.0)
        self.assertTrue(any(p.rgba[:3] == tr.category_color("Cargo")
                            for p in parts))
        self.assertEqual(tr.category_color("?"), tr.OTHER)


if __name__ == "__main__":
    unittest.main()
