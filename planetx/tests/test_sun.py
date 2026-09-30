# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Положение солнца против таблиц и свет поверхности."""
import calendar
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import sun  # noqa: E402


def utc(*parts):
    return float(calendar.timegm(parts + (0,) * (6 - len(parts))))


class TestPosition(unittest.TestCase):

    def test_solstice_and_equinox_declination(self):
        # Солнцестояние 21 июня 2024 года, 20:51 UTC, склонение 23.44°.
        # Равноденствие 20 марта 2024 года, 03:06 UTC, склонение 0.
        lat, _ = sun.subsolar(utc(2024, 6, 20, 20, 51))
        self.assertAlmostEqual(lat, 23.44, delta=0.02)
        lat, _ = sun.subsolar(utc(2024, 3, 20, 3, 6))
        self.assertAlmostEqual(lat, 0.0, delta=0.02)
        lat, _ = sun.subsolar(utc(2024, 12, 21, 9, 21))
        self.assertAlmostEqual(lat, -23.44, delta=0.02)

    def test_equation_of_time(self):
        # Уравнение времени по таблицам NOAA - 3 ноября +16.4 мин,
        # 11 февраля -14.2 мин, 13 июня около 0. Солнечные часы при
        # плюсе спешат, солнце проходит Гринвич раньше 12:00 UTC и в 12:00
        # стоит в зените западнее, на долготе -минуты / 4.
        for day, minutes in (((2025, 11, 3), 16.4), ((2025, 2, 11), -14.2),
                             ((2025, 6, 13), 0.0)):
            _, lon = sun.subsolar(utc(*day, 12))
            self.assertAlmostEqual(lon, -minutes / 4.0, delta=0.08, msg=day)

    def test_noon_elevation_in_perm(self):
        # Пермь, 58.01° с. ш. Высота солнца в полдень летнего
        # солнцестояния - 90 - 58.01 + 23.44 = 55.43°. Полдень по солнцу
        # на долготе 56.23° - около 08:15 UTC.
        best = max(sun.elevation(58.01, 56.23,
                                 utc(2024, 6, 20, 8) + 60.0 * m)
                   for m in range(0, 60))
        self.assertAlmostEqual(best, 55.43, delta=0.05)

    def test_direction_is_unit_and_points_to_subsolar(self):
        t = utc(2026, 9, 30, 6)
        d = sun.direction(t)
        self.assertAlmostEqual(math.hypot(*d), 1.0, places=12)
        lat, lon = sun.subsolar(t)
        self.assertAlmostEqual(sun.elevation(lat, lon, t), 90.0, delta=1e-4)

    def test_night_on_the_opposite_side(self):
        t = utc(2026, 9, 30, 6)
        lat, lon = sun.subsolar(t)
        # У -90° арксинус теряет точность, 1e-4° - это 11 м на Земле.
        self.assertAlmostEqual(sun.elevation(-lat, lon + 180.0, t), -90.0,
                               delta=1e-4)


class TestBrightness(unittest.TestCase):

    def test_flat_ground_at_45_degrees_is_one(self):
        self.assertAlmostEqual(sun.brightness(math.sin(math.radians(45))),
                               1.0, places=12)

    def test_night_is_dark_and_day_is_bright(self):
        self.assertAlmostEqual(sun.brightness(-0.5), sun.NIGHT / sun.FLAT)
        self.assertGreater(sun.brightness(1.0), 1.0)

    def test_twilight_is_monotonic(self):
        values = [sun.brightness(c / 100.0) for c in range(-40, 41)]
        self.assertEqual(values, sorted(values))


if __name__ == "__main__":
    unittest.main()
