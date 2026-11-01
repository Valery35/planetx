# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Границы полей Fields of the World: разбор тайла, оценка, цвет."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(
    os.path.abspath(__file__)), "..", "core"))

import fieldmap  # noqa: E402


def varint(value):
    out = bytearray()
    while value >= 0x80:
        out.append(value & 0x7F | 0x80)
        value >>= 7
    out.append(value)
    return bytes(out)


def field(number, payload):
    return varint(number << 3 | 2) + varint(len(payload)) + payload


def number(no, value):
    return varint(no << 3) + varint(value)


def zigzag(value):
    return value << 1 if value >= 0 else (-value << 1) - 1


def square(x, y, side):
    """Геометрия MVT квадрата от начала координат тайла."""
    cells = [1 << 3 | 1, zigzag(x), zigzag(y), 3 << 3 | 2,
             zigzag(side), 0, 0, zigzag(side), zigzag(-side), 0, 7 << 3 | 7]
    return b"".join(varint(c) for c in cells)


def feature(label, confidence, x):
    tags = b"".join(varint(v) for v in (0, label, 1, confidence))
    return field(2, tags) + number(3, 3) + field(4, square(x, 100, 400))


def tile(title="fields", extent=4096):
    layer = (field(1, title.encode())
             + field(3, b"label") + field(3, b"confidence_mean")
             + field(4, field(1, b"field"))
             + field(4, field(1, b"field_boundaries"))
             + field(4, field(1, b"0.55"))
             + field(4, field(1, b"0.2"))
             + field(2, feature(0, 2, 100))
             + field(2, feature(1, 2, 600))
             + field(2, feature(0, 3, 1100))
             + number(5, extent))
    return field(3, layer)


class TestDecode(unittest.TestCase):
    def test_only_confident_fields_of_layer(self):
        found = fieldmap.decode(tile(), "fields")
        self.assertEqual(len(found), 1)  # полоса и низкая оценка отброшены
        self.assertAlmostEqual(found[0].score, 0.55 / fieldmap.FULL * 100.0)

    def test_rings_are_tile_shares(self):
        ring = fieldmap.decode(tile(extent=1024), "fields")[0].rings[0]
        self.assertAlmostEqual(ring[:, 0].min(), 100 / 1024.0)
        self.assertAlmostEqual(ring[:, 1].max(), 500 / 1024.0)

    def test_other_layer_gives_nothing(self):
        self.assertEqual(fieldmap.decode(tile(), "2024"), [])


class TestScore(unittest.TestCase):
    def test_full_value_is_hundred(self):
        self.assertAlmostEqual(fieldmap.score_of(str(fieldmap.FULL)), 100.0)
        self.assertEqual(fieldmap.score_of("0.9"), 100.0)
        self.assertIsNone(fieldmap.score_of(None))

    def test_color_follows_stops(self):
        self.assertEqual(fieldmap.color(fieldmap.MIN_SCORE),
                         fieldmap.STOPS[0][1])
        self.assertEqual(fieldmap.color(100.0), fieldmap.STOPS[-1][1])
        self.assertEqual(fieldmap.color(90.0), (207, 236, 176))


class TestSources(unittest.TestCase):
    def test_every_year_has_key_address_and_layer(self):
        for year in fieldmap.YEARS:
            self.assertIn(year, fieldmap.KEYS)
            self.assertTrue(fieldmap.URLS[year].endswith(".pmtiles"))
            self.assertIn(year, fieldmap.LAYERS)


if __name__ == "__main__":
    unittest.main()
