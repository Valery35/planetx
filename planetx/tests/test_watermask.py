# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/watermask.py: вода и суша ниже уровня моря."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import watermask as wm  # noqa: E402


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field(number, wire, payload):
    key = varint((number << 3) | wire)
    if wire == 0:
        return key + varint(payload)
    return key + varint(len(payload)) + payload


def zigzag(n):
    return (n << 1) ^ (n >> 31)


def ring_commands(points, cursor):
    """Команды MVT кольца: MoveTo, LineTo, ClosePath. Смещения - от
    курсора, конца прошлого кольца. Возвращает команды и новый курсор."""
    out = [(1 << 3) | 1]
    x, y = cursor
    px, py = points[0]
    out += [zigzag(px - x), zigzag(py - y)]
    x, y = px, py
    out.append(((len(points) - 1) << 3) | 2)
    for px, py in points[1:]:
        out += [zigzag(px - x), zigzag(py - y)]
        x, y = px, py
    out.append((1 << 3) | 7)
    return out, (x, y)


def tile(name, rings):
    geometry = []
    cursor = (0, 0)
    for ring in rings:
        commands, cursor = ring_commands(ring, cursor)
        geometry += commands
    packed = b"".join(varint(v) for v in geometry)
    feature = field(3, 0, 3) + field(4, 2, packed)
    layer = field(15, 0, 2) + field(1, 2, name.encode()) \
        + field(2, 2, feature) + field(5, 0, 4096)
    return field(3, 2, layer)


# Вода - квадрат 1000-3000 по часовой стрелке (y вниз), остров внутри -
# квадрат 1800-2200 против неё.
WATER = [[(1000, 1000), (3000, 1000), (3000, 3000), (1000, 3000)],
         [(1800, 1800), (1800, 2200), (2200, 2200), (2200, 1800)]]


class TestWaterMask(unittest.TestCase):

    def test_decode_and_inside(self):
        features = wm.decode_water(tile("water", WATER))
        self.assertEqual(len(features), 1)
        self.assertEqual(len(features[0]), 2)
        xs = [0.3, 0.5, 0.1]
        ys = [0.3, 0.5, 0.1]
        wet = wm.inside(features[0], xs, ys)
        # Вода, остров, суша за краем воды.
        self.assertEqual(list(wet), [True, False, False])

    def test_other_layer_is_not_water(self):
        self.assertEqual(wm.decode_water(tile("landcover", WATER)), [])

    def test_land_needs_tile(self):
        mask = wm.WaterMask()
        lat, lon = 51.2896, 37.6329  # дно Лебединского карьера
        key, fx, fy = wm.tile_of(lat, lon)
        self.assertTrue(0.0 <= fx < 1.0 and 0.0 <= fy < 1.0)
        # Тайла нет - не суша, метка остаётся на уровне моря.
        self.assertFalse(mask.land([lat], [lon])[0])
        self.assertEqual(mask.missing([lat], [lon]), {key})
        before = mask.gen
        mask.add(key, [])
        self.assertGreater(mask.gen, before)
        self.assertTrue(mask.land([lat], [lon])[0])
        self.assertEqual(mask.missing([lat], [lon]), set())
        # Точка в воде тайла - не суша.
        square = wm.decode_water(tile("water", [[
            (0, 0), (4096, 0), (4096, 4096), (0, 4096)]]))
        mask.add(key, square)
        self.assertFalse(mask.land([lat], [lon])[0])


class TestMaskParts(unittest.TestCase):

    def test_fine_tile_takes_part_of_water_tile(self):
        # Тайл уровня 14 - четверть стороны тайла воды уровня 12.
        parts = wm.mask_parts((14, 4 * 100 + 1, 4 * 200 + 3))
        self.assertEqual(parts, [((12, 100, 200), (0.25, 0.75, 0.25),
                                  (0.0, 0.0, 1.0))])
        # Вода в правой половине тайла воды: у этой четверти (x 0.25-0.5)
        # её нет, у четверти x 0.75-1 - вся.
        half = [[np.array(
            [[0.5, 0.0], [1.0, 0.0], [1.0, 1.0], [0.5, 1.0]])]]
        tiles = {(12, 100, 200): half}
        rings = wm.mask_rings((14, 401, 803), tiles)
        self.assertEqual(len(rings), 1)
        self.assertEqual(list(wm.inside(rings[0], [0.5], [0.5])), [False])
        rings = wm.mask_rings((14, 403, 803), tiles)
        self.assertEqual(list(wm.inside(rings[0], [0.5], [0.5])), [True])

    def test_coarse_tile_needs_all_children(self):
        parts = wm.mask_parts((11, 10, 20))
        self.assertEqual(len(parts), 4)
        tiles = {p[0]: [] for p in parts[:3]}
        self.assertIsNone(wm.mask_rings((11, 10, 20), tiles))
        tiles[parts[3][0]] = []
        self.assertEqual(wm.mask_rings((11, 10, 20), tiles), [])
        self.assertEqual(wm.mask_parts((9, 1, 1)), [])


if __name__ == "__main__":
    unittest.main()
