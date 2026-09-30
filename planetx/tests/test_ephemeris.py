# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Солнце, Луна и планеты против JPL Horizons."""
import calendar
import math
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ephemeris as eph  # noqa: E402

# Горизонты JPL, астрометрические RA и Dec ICRF, центр Земли, градусы.
# Запрошены 1 октября 2026 года.
HORIZONS = {
    (2026, 10, 1, 0, 0): {
        "sun": (186.85871, -2.96284), "moon": (60.42382, 25.90867),
        "mercury": (207.57717, -13.21449), "venus": (213.21656, -20.84700),
        "mars": (123.78543, 20.85435), "jupiter": (141.83407, 15.62451),
        "saturn": (11.35542, 1.93264), "uranus": (63.24310, 21.00366),
        "neptune": (2.84049, -0.31722)},
    (2012, 3, 20, 6, 0): {
        "sun": (359.87330, -0.05488), "moon": (333.07481, -5.73402),
        "mercury": (1.16882, 4.26439), "venus": (42.43609, 18.99746),
        "mars": (160.57900, 12.27538), "jupiter": (38.49222, 14.15009),
        "saturn": (206.90977, -8.17348), "uranus": (4.02260, 0.99033),
        "neptune": (333.73644, -11.45436)},
}
# Допуск, градусы дуги. Луна - формулы малой точности. У Юпитера
# и Сатурна JPL называет ошибку таблицы 1 до 400 и 600 секунд дуги,
# 1 октября 2026 года вышло 0.02° и 0.08°.
TOLERANCE = {"moon": 0.35, "jupiter": 0.12, "saturn": 0.17}
PLANET_TOLERANCE = 0.02


def arc(a, b):
    """Угол между двумя точками неба, градусы."""
    ra1, de1 = map(math.radians, a)
    ra2, de2 = map(math.radians, b)
    c = (math.sin(de1) * math.sin(de2)
         + math.cos(de1) * math.cos(de2) * math.cos(ra1 - ra2))
    return math.degrees(math.acos(max(-1.0, min(1.0, c))))


class TestHorizons(unittest.TestCase):

    def test_positions(self):
        for moment, bodies in HORIZONS.items():
            unix = calendar.timegm(moment + (0,))
            for name, expect in bodies.items():
                got = eph.ra_dec(name, unix)
                limit = TOLERANCE.get(name, PLANET_TOLERANCE)
                self.assertLess(arc(got, expect), limit,
                                "%s %s %s" % (moment, name, got))

    def test_distances(self):
        unix = calendar.timegm((2026, 10, 1, 0, 0, 0))
        self.assertAlmostEqual(eph.distance("sun", unix), 1.0, delta=0.02)
        self.assertAlmostEqual(eph.distance("moon", unix) * 149597870.7,
                               384400.0, delta=25000.0)

    def test_every_body_has_a_direction(self):
        for name in eph.BODIES:
            v = eph.direction(name, 0.0)
            self.assertAlmostEqual(sum(x * x for x in v), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
