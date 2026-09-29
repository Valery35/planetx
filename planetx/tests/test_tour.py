# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тур: остановки, время, непрерывность позы."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

from navigation import Pose  # noqa: E402
import tour as tr  # noqa: E402

STOPS = [tr.Stop("Пермь", 58.01, 56.23, 20000.0, 30.0, 45.0),
         tr.Stop("Кунгур", 57.43, 56.94, 5000.0),
         tr.Stop("Эльбрус", 43.35, 42.44, 30000.0, 180.0, 60.0)]


def close(pose, stop):
    return (abs(pose.lat - stop.lat) < 1e-9
            and abs(pose.lon - stop.lon) < 1e-9
            and abs(pose.distance - stop.distance) < 1e-6
            and abs((pose.heading - stop.heading + 180.0) % 360.0 - 180.0)
            < 1e-9 and abs(pose.tilt - stop.tilt) < 1e-9)


class TestTour(unittest.TestCase):

    def setUp(self):
        self.start = Pose(55.75, 37.62, 2.0e6)
        self.tour = tr.Tour(self.start, STOPS, pause=2.0)

    def test_duration_is_flights_and_pauses(self):
        flights = sum(f.duration for f in self.tour.flights)
        self.assertAlmostEqual(self.tour.duration, flights + 3 * 2.0)

    def test_camera_stands_on_each_stop_during_pause(self):
        for i, stop in enumerate(STOPS):
            for dt in (0.0, 1.0, 1.99):
                t = self.tour.arrivals[i] + dt
                self.assertEqual(self.tour.index_at(t), i)
                self.assertTrue(self.tour.arrived(t))
                self.assertTrue(close(self.tour.pose_at(t), stop))

    def test_starts_from_camera(self):
        pose = self.tour.pose_at(0.0)
        self.assertAlmostEqual(pose.lat, self.start.lat)
        self.assertAlmostEqual(pose.distance, self.start.distance)
        self.assertFalse(self.tour.arrived(0.0))

    def test_pose_is_continuous_at_leg_start(self):
        # Перелёт к следующей остановке начинается с позы предыдущей.
        t = self.tour.starts[1]
        before = self.tour.pose_at(t - 1e-6)
        after = self.tour.pose_at(t + 1e-6)
        self.assertAlmostEqual(before.lat, after.lat, 5)
        self.assertAlmostEqual(before.lon, after.lon, 5)
        self.assertLess(abs(before.distance - after.distance)
                        / before.distance, 1e-4)

    def test_end_and_empty(self):
        end = self.tour.pose_at(self.tour.duration + 5.0)
        self.assertTrue(close(end, STOPS[-1]))
        empty = tr.Tour(self.start, [])
        self.assertEqual(empty.duration, 0.0)
        self.assertEqual(empty.index_at(0.0), -1)


class TestClock(unittest.TestCase):

    def test_minutes_and_hours(self):
        self.assertEqual(tr.clock(0.0), "0:00")
        self.assertEqual(tr.clock(65.4), "1:05")
        self.assertEqual(tr.clock(3725.0), "1:02:05")
        self.assertEqual(tr.clock(-3.0), "0:00")


class TestPath(unittest.TestCase):

    def setUp(self):
        # Путь 20 км на север, потом 20 км на восток.
        self.path = tr.PathStop("Путь", [(58.0, 56.0), (58.18, 56.0),
                                         (58.18, 56.34)])

    def test_length_distance_and_time(self):
        self.assertAlmostEqual(self.path.length, 40000.0, delta=300.0)
        self.assertAlmostEqual(self.path.distance, self.path.length / 8.0)
        # Проезд пути длиннее 2.4 км - 32 с при любой длине.
        self.assertAlmostEqual(self.path.glide, 32.0)

    def test_heading_follows_path(self):
        first = self.path.pose_at(0.2 * self.path.glide)
        last = self.path.pose_at(0.9 * self.path.glide)
        self.assertLess(min(first.heading, 360.0 - first.heading), 1.0)
        self.assertAlmostEqual(last.heading, 90.0, delta=1.5)
        self.assertEqual(first.tilt, tr.PATH_TILT)

    def test_ends_at_last_point(self):
        end = self.path.end_pose()
        self.assertAlmostEqual(end.lat, 58.18, 6)
        self.assertAlmostEqual(end.lon, 56.34, 6)

    def test_tour_glides_after_flight_and_continues(self):
        tour = tr.Tour(Pose(55.75, 37.62, 2.0e6),
                       [self.path, STOPS[0]], pause=1.0)
        g = tour.glides[0]
        at_arrival = tour.pose_at(g - 1e-6)
        gliding = tour.pose_at(g + 1e-6)
        self.assertAlmostEqual(at_arrival.lat, gliding.lat, 6)
        self.assertAlmostEqual(at_arrival.heading, gliding.heading, 3)
        self.assertFalse(tour.arrived(g + 1.0))  # едет, не стоит
        self.assertTrue(tour.arrived(tour.arrivals[0] + 0.5))
        # Следующий перелёт начинается с конца пути.
        leg = tour.pose_at(tour.starts[1] + 1e-6)
        self.assertAlmostEqual(leg.lat, 58.18, 4)
        self.assertAlmostEqual(leg.lon, 56.34, 4)


class TestRecorded(unittest.TestCase):
    """Записанный тур: позы между моментами, переходы через 180°,
    прореживание, место в туре."""

    SAMPLES = [(0.0, 58.0, 179.0, 1000.0, 350.0, 30.0),
               (1.0, 58.0, -179.0, 4000.0, 10.0, 50.0),
               (3.0, 58.2, -179.0, 4000.0, 10.0, 50.0)]

    def test_interpolation(self):
        stop = tr.RecordedStop("Запись", self.SAMPLES)
        self.assertEqual(stop.glide, 3.0)
        mid = stop.pose_at(0.5)
        # Через линию перемены дат, а не назад через весь шар.
        self.assertAlmostEqual(abs(mid.lon), 180.0, places=6)
        # Через север, а не через юг.
        self.assertAlmostEqual(mid.heading % 360.0, 0.0, places=6)
        self.assertAlmostEqual(mid.distance, 2000.0, places=6)
        self.assertAlmostEqual(mid.tilt, 40.0, places=6)
        end = stop.end_pose()
        self.assertAlmostEqual(end.lat, 58.2, places=9)

    def test_in_tour(self):
        stop = tr.RecordedStop("Запись", self.SAMPLES)
        tour = tr.Tour(Pose(55.0, 37.0, 2.0e6), [stop], pause=1.0)
        arrive = tour.glides[0]
        self.assertAlmostEqual(tour.duration, arrive + 3.0 + 1.0)
        self.assertAlmostEqual(tour.pose_at(arrive + 3.0).lat, 58.2)

    def test_thin(self):
        still = (58.0, 56.0, 1000.0, 0.0, 0.0)
        samples = [(float(t),) + still for t in range(5)]
        samples.append((5.0, 58.1, 56.0, 1000.0, 0.0, 0.0))
        out = tr.thin(samples)
        self.assertEqual([s[0] for s in out], [0.0, 4.0, 5.0])

if __name__ == "__main__":
    unittest.main()
