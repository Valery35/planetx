# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Солнце: положение по таблицам, направление в ECEF, высота и азимут."""
import calendar
import math
import os
import sys
import unittest

import numpy as np

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "core"))

import sun  # noqa: E402


def unix(year, month, day, hour=0, minute=0, second=0):
    return float(calendar.timegm((year, month, day, hour, minute, second)))


class TestTables(unittest.TestCase):
    """Сверка с опубликованными примерами."""

    def test_meeus_example_25a(self):
        # Меёс, «Astronomical Algorithms», пример 25.a: 13 октября
        # 1992 года, 0 ч. Видимое прямое восхождение 13h13m31.4s,
        # склонение -7°47'06".
        ra, dec = sun.equatorial(unix(1992, 10, 13))
        self.assertAlmostEqual(math.degrees(ra),
                               (13 + 13 / 60 + 31.4 / 3600) * 15, delta=0.01)
        self.assertAlmostEqual(math.degrees(dec),
                               -(7 + 47 / 60 + 6 / 3600), delta=0.01)

    def test_nrel_spa_example(self):
        # Reda, Andreas, «Solar Position Algorithm for Solar Radiation
        # Applications», NREL 2004, контрольный пример: 17 октября
        # 2003 года, 12:30:30 по поясу -7, широта 39.742476, долгота
        # -105.1786. Зенитное расстояние 50.11162° с рефракцией около
        # 0.016°, азимут 194.34024°.
        elevation, azimuth = sun.horizontal(39.742476, -105.1786,
                                            unix(2003, 10, 17, 19, 30, 30))
        self.assertAlmostEqual(elevation, 90.0 - 50.11162 - 0.016,
                               delta=0.05)
        self.assertAlmostEqual(azimuth, 194.34024, delta=0.05)

    def test_june_solstice_2024(self):
        # Солнцестояние 20 июня 2024 года, 20:51 UTC: склонение равно
        # наклону эклиптики, 23.4393°.
        _, dec = sun.equatorial(unix(2024, 6, 20, 20, 51))
        self.assertAlmostEqual(math.degrees(dec), 23.4393, delta=0.01)

    def test_march_equinox_2024(self):
        # Равноденствие 20 марта 2024 года, 03:06 UTC: склонение 0.
        _, dec = sun.equatorial(unix(2024, 3, 20, 3, 6))
        self.assertAlmostEqual(math.degrees(dec), 0.0, delta=0.01)


class TestDirection(unittest.TestCase):

    def test_unit_vector(self):
        v = sun.direction(unix(2026, 9, 30, 9))
        self.assertAlmostEqual(float(np.linalg.norm(v)), 1.0, places=12)

    def test_zenith_at_subsolar_point(self):
        t = unix(2026, 9, 30, 9)
        lat, lon = sun.subsolar(t)
        elevation, _ = sun.horizontal(lat, lon, t)
        self.assertAlmostEqual(elevation, 90.0, delta=1e-6)
        elevation, _ = sun.horizontal(-lat, lon + 180.0, t)
        self.assertAlmostEqual(elevation, -90.0, delta=1e-6)

    def test_noon_over_greenwich(self):
        # Уравнение времени 3 ноября около +16.4 мин: в 12:00 UTC солнце
        # уже прошло Гринвич и стоит западнее на 16.4 / 4 = 4.1°.
        _, lon = sun.subsolar(unix(2024, 11, 3, 12))
        self.assertAlmostEqual(lon, -16.43 / 4.0, delta=0.05)

    def test_sun_moves_west_15_degrees_an_hour(self):
        _, a = sun.subsolar(unix(2026, 9, 30, 9))
        _, b = sun.subsolar(unix(2026, 9, 30, 10))
        self.assertAlmostEqual((a - b) % 360.0, 15.0, delta=0.01)

    def test_night_in_perm_at_midnight(self):
        # Пермь, 30 сентября, полночь по местному времени (UTC+5).
        elevation, _ = sun.horizontal(58.01, 56.23, unix(2026, 9, 29, 19))
        self.assertLess(elevation, -20.0)



class TestLight(unittest.TestCase):
    """Свет солнца: день как постоянная отмывка, ночь, сумерки."""

    UP = np.array([[0.0, 0.0, 1.0]])

    def at(self, elevation):
        e = math.radians(elevation)
        return float(sun.light(self.UP, np.array([math.cos(e), 0.0,
                                                  math.sin(e)]))[0])

    def test_flat_ground_at_45_degrees_is_one(self):
        self.assertAlmostEqual(self.at(45.0), 1.0, places=9)

    def test_night(self):
        self.assertAlmostEqual(self.at(-20.0), sun.NIGHT, places=9)
        self.assertAlmostEqual(self.at(-90.0), sun.NIGHT, places=9)

    def test_brighter_with_higher_sun(self):
        values = [self.at(e) for e in (-8, -4, 0, 2, 5, 20, 45, 80)]
        self.assertEqual(values, sorted(values))

    def test_twilight_is_continuous(self):
        steps = np.diff([self.at(e / 10.0) for e in range(-120, 60)])
        self.assertLess(float(np.abs(steps).max()), 0.02)

    def test_slope_facing_away_is_dark(self):
        # Склон 60° от солнца на высоте 30°: солнце ниже его плоскости.
        e = math.radians(30.0)
        s = np.array([math.cos(e), 0.0, math.sin(e)])
        a = math.radians(60.0)
        away = np.array([[-math.sin(a), 0.0, math.cos(a)]])
        self.assertAlmostEqual(float(sun.light(away, s)[0]), sun.NIGHT,
                               places=9)


if __name__ == "__main__":
    unittest.main()
