# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Форматы координат: UTM, MGRS, градусы-минуты-секунды, разбор строки.

Эталоны UTM - пересчёт QGIS 4.0.3 из EPSG:4326 в EPSG:326xx и 327xx,
30 сентября 2026 года. Эталон MGRS - пример статьи Military Grid
Reference System, Гонолулу, «4Q FJ 1234 6789».
"""
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import coords as co  # noqa: E402

# Широта, долгота, зона, восток, север по QGIS.
QGIS_UTM = (
    (58.0105, 56.2294, 40, 454464.3794, 6430138.879),
    (60.0, 5.0, 32, 276979.9264, 6658157.2024),
    (78.0, 15.0, 33, 500000.0, 8658369.5858),
    (-33.8688, 151.2093, 56, 334368.6336, 6250948.3454),
    (-0.5, -78.5, 17, 778265.7783, 9944681.96),
    (10.0, 0.0, 31, 171071.2639, 1106908.8542),
    (70.0, 179.9, 60, 610660.4649, 7768505.4523),
    (43.3499, 42.4453, 38, 292952.0158, 4802841.4832),
)
HONOLULU = (21 + 24 / 60 + 35.43062452380 / 3600,
            -(157 + 54 / 60 + 57.89102787040 / 3600))


class TestUtm(unittest.TestCase):
    def test_matches_qgis(self):
        for lat, lon, zone, east, north in QGIS_UTM:
            got = co.to_utm(lat, lon)
            self.assertEqual(got[0], zone, (lat, lon))
            self.assertAlmostEqual(got[2], east, delta=0.001)
            self.assertAlmostEqual(got[3], north, delta=0.001)

    def test_round_trip(self):
        for lat, lon, *_ in QGIS_UTM:
            zone, letter, east, north = co.to_utm(lat, lon)
            back = co.from_utm(zone, letter < "N", east, north)
            self.assertAlmostEqual(back[0], lat, places=9)
            self.assertAlmostEqual(back[1], lon, places=9)

    def test_outside_utm(self):
        self.assertIsNone(co.to_utm(85.0, 10.0))
        self.assertEqual(co.format_point(85.0, 10.0, "utm"),
                         "85.00000, 10.00000")


class TestMgrs(unittest.TestCase):
    def test_honolulu(self):
        self.assertEqual(co.to_mgrs(*HONOLULU, digits=4),
                         "4Q FJ 1234 6789")

    def test_parse_honolulu(self):
        lat, lon = co.parse_point("4QFJ12346789")
        # Юго-западный угол квадрата 10 м.
        self.assertAlmostEqual(lat, HONOLULU[0], delta=10 / 111000.0)
        self.assertAlmostEqual(lon, HONOLULU[1], delta=15 / 104000.0)

    def test_round_trip(self):
        for lat, lon, *_ in QGIS_UTM:
            text = co.to_mgrs(lat, lon)
            back = co.parse_point(text)
            self.assertIsNotNone(back, text)
            # Метровый квадрат: угол не дальше 1.5 м от точки.
            self.assertAlmostEqual(back[0], lat, delta=1.5 / 111000.0)
            self.assertAlmostEqual(back[1], lon, delta=1.5 / 30000.0)


class TestDms(unittest.TestCase):
    def test_text(self):
        self.assertEqual(
            co.format_point(58.0105, -56.2294, "dms"),
            "58°00′37.8″ N, 56°13′45.8″ W")

    def test_rounding_carries(self):
        self.assertEqual(co.dms_text(10.99999999, "N", "S"),
                         "11°00′00.0″ N")

    def test_parse_forms(self):
        for text in ("58°00′37.8″ N, 56°13′45.8″ E",
                     "58°00'37.8\"N 56°13'45.8\"E",
                     "58 00 37.8 N 56 13 45.8 E",
                     "56°13′45.8″ E 58°00′37.8″ N",
                     "58°00′37,8″ с. ш., 56°13′45,8″ в. д."):
            lat, lon = co.parse_point(text)
            self.assertAlmostEqual(lat, 58.0105, places=4, msg=text)
            self.assertAlmostEqual(lon, 56.2294, places=4, msg=text)

    def test_west_south(self):
        lat, lon = co.parse_point("33°52′08″ S 151°12′33″ E")
        self.assertLess(lat, 0.0)
        lat, lon = co.parse_point("21°24′35″ N 157°54′58″ W")
        self.assertLess(lon, 0.0)


class TestParse(unittest.TestCase):
    def test_decimal_with_height(self):
        # Строка координат самого глобуса, её вставляли в поиск.
        self.assertEqual(co.parse_point("59.593416, 56.806003, высота 207 м"),
                         (59.593416, 56.806003))

    def test_utm(self):
        # Восток и север округлены до метра.
        lat, lon = co.parse_point("40V 454464 6430139")
        self.assertAlmostEqual(lat, 58.0105, delta=1e-5)
        self.assertAlmostEqual(lon, 56.2294, delta=2e-5)
        lat, lon = co.parse_point("56H 334369 6250948")
        self.assertAlmostEqual(lat, -33.8688, places=5)

    def test_place_names_are_not_points(self):
        for text in ("Москва", "Пермь", "Route 66", "улица Ленина 5 в",
                     "New York", "Sea of Japan"):
            self.assertIsNone(co.parse_point(text), text)

    def test_all_formats_round_trip(self):
        for lat, lon, *_ in QGIS_UTM:
            for fmt in co.FORMATS:
                text = co.format_point(lat, lon, fmt)
                back = co.parse_point(text)
                self.assertIsNotNone(back, text)
                self.assertAlmostEqual(back[0], lat, delta=3e-5, msg=text)
                self.assertAlmostEqual(back[1], lon, delta=6e-5, msg=text)


if __name__ == "__main__":
    unittest.main()
