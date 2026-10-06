# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/routing.py: разбор дорог тайла, граф, путь."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import routing  # noqa: E402

KEY = (14, 10751, 4933)  # тайл центра Перми
E = routing.EXTENT


def varint(n):
    out = bytearray()
    while True:
        byte = n & 0x7F
        n >>= 7
        if n:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def field(number, wire, payload):
    key = varint((number << 3) | wire)
    if wire == 0:
        return key + varint(payload)
    return key + varint(len(payload)) + payload


def zig(v):
    return (v << 1) ^ (v >> 63)


def line_geometry(points):
    """Команды MVT одной линии."""
    out = [(1 << 3) | 1]
    x = y = 0
    px, py = points[0]
    out += [zig(px - x), zig(py - y)]
    x, y = px, py
    out.append(((len(points) - 1) << 3) | 2)
    for px, py in points[1:]:
        out += [zig(px - x), zig(py - y)]
        x, y = px, py
    return b"".join(varint(v) for v in out)


def tile(roads):
    """Тайл со слоем transportation. roads - (точки, атрибуты)."""
    keys, values, features = [], [], b""
    for points, attrs in roads:
        tags = []
        for k, v in attrs.items():
            if k not in keys:
                keys.append(k)
            if v not in values:
                values.append(v)
            tags += [keys.index(k), values.index(v)]
        features += field(2, 2, field(2, 2, b"".join(varint(t)
                                                      for t in tags))
                          + field(3, 0, 2)
                          + field(4, 2, line_geometry(points)))
    layer = field(15, 0, 2) + field(1, 2, b"transportation") + features
    for k in keys:
        layer += field(3, 2, k.encode())
    for v in values:
        if isinstance(v, str):
            layer += field(4, 2, field(1, 2, v.encode()))
        else:
            layer += field(4, 2, field(6, 0, zig(v)))
    layer += field(5, 0, E)
    return field(3, 2, layer)


def grid_to_latlon(x, y):
    lat, lon = routing.to_latlon(np.array([[KEY[1] * E + x,
                                            KEY[2] * E + y]], float))
    return float(lat[0]), float(lon[0])


def graph(roads, mode="car"):
    return routing.run(routing.build_steps(
        routing.decode(KEY, tile(roads)), mode))


class TestDecode(unittest.TestCase):

    def test_lines_attributes_and_world_grid(self):
        lines = routing.decode(KEY, tile([
            ([(0, 0), (100, 0)], {"class": "primary", "oneway": 1}),
            ([(0, 50), (0, 200)], {"class": "path", "brunnel": "bridge",
                                   "oneway": -1})]))
        self.assertEqual(len(lines), 2)
        first, second = lines
        self.assertEqual(first.cls, "primary")
        self.assertEqual(first.oneway, 1)
        self.assertEqual(second.oneway, -1)
        self.assertEqual(second.brunnel, "bridge")
        np.testing.assert_array_equal(
            first.points, [[KEY[1] * E, KEY[2] * E],
                           [KEY[1] * E + 100, KEY[2] * E]])

    def test_grid_round_trip(self):
        x, y = routing.to_grid(58.0105, 56.2294)
        lat, lon = routing.to_latlon(np.array([[x, y]]))
        self.assertAlmostEqual(float(lat[0]), 58.0105, places=9)
        self.assertAlmostEqual(float(lon[0]), 56.2294, places=9)


class TestRoute(unittest.TestCase):

    def test_shortest_of_two_ways(self):
        # Квадрат 1000 × 1000 единиц: напрямую по низу и в обход по
        # трём сторонам. Путь из левого нижнего в правый нижний угол -
        # по низу.
        g = graph([
            ([(0, 1000), (1000, 1000)], {"class": "minor"}),
            ([(0, 1000), (0, 0), (1000, 0), (1000, 1000)],
             {"class": "minor"})])
        a = grid_to_latlon(5, 1000)
        b = grid_to_latlon(995, 1000)
        route = routing.run(routing.route_steps(g, a, b))
        unit = routing.unit_metres(a[0])
        self.assertAlmostEqual(route.length, 990 * unit, delta=0.01 * 990
                               * unit)
        self.assertAlmostEqual(route.seconds, route.length / (30 / 3.6),
                               delta=1.0)

    def test_faster_road_wins_over_shorter(self):
        # Прямо по грунтовке 1000 единиц или в обход по трассе 1400.
        g = graph([
            ([(0, 1000), (1000, 1000)], {"class": "track"}),
            ([(0, 1000), (500, 1490), (1000, 1000)],
             {"class": "primary"})])
        route = routing.run(routing.route_steps(
            g, grid_to_latlon(0, 1000), grid_to_latlon(1000, 1000)))
        self.assertGreater(max(p[0] for p in route.points), -90.0)
        lats = [p[0] for p in route.points]
        # Трасса южнее грунтовки: широты пути ниже широты грунтовки.
        self.assertLess(min(lats), grid_to_latlon(0, 1000)[0] - 1e-4)

    def test_car_keeps_oneway_foot_does_not(self):
        roads = [([(1000, 1000), (0, 1000)], {"class": "minor",
                                               "oneway": 1}),
                 ([(0, 1000), (0, 0), (1000, 0), (1000, 1000)],
                  {"class": "minor"})]
        a, b = grid_to_latlon(0, 1000), grid_to_latlon(1000, 1000)
        car = routing.run(routing.route_steps(graph(roads), a, b))
        foot = routing.run(routing.route_steps(graph(roads, "foot"), a, b,
                                               "foot"))
        unit = routing.unit_metres(a[0])
        # Машина против одностороннего не едет: в обход, 3000 единиц.
        self.assertAlmostEqual(car.length, 3000 * unit, delta=30 * unit)
        self.assertAlmostEqual(foot.length, 1000 * unit, delta=10 * unit)
        self.assertAlmostEqual(foot.seconds, foot.length / (5 / 3.6),
                               delta=1.0)

    def test_path_is_not_for_car(self):
        roads = [([(0, 0), (1000, 0)], {"class": "path"})]
        self.assertIsNone(graph(roads))
        self.assertIsNotNone(graph(roads, "foot"))

    def test_t_junction_without_shared_vertex_is_snapped(self):
        # Боковая дорога кончается в 2 единицах от главной, общей
        # вершины нет. 2 единицы у Перми - около 0.6 м, меньше SNAP.
        g = graph([
            ([(0, 0), (2000, 0)], {"class": "primary"}),
            ([(1000, 1000), (1000, 2)], {"class": "minor"})])
        route = routing.run(routing.route_steps(
            g, grid_to_latlon(1000, 1000), grid_to_latlon(2000, 0)))
        self.assertIsNotNone(route)
        unit = routing.unit_metres(grid_to_latlon(0, 0)[0])
        self.assertAlmostEqual(route.length, 2000 * unit, delta=20 * unit)

    def test_bridge_over_road_is_not_a_junction(self):
        # Мост пересекает дорогу посередине без общей вершины, и конец
        # дороги не у моста: перехода с дороги на мост нет.
        g = graph([
            ([(0, 500), (1000, 500)], {"class": "minor"}),
            ([(500, 0), (500, 1000)], {"class": "primary",
                                        "brunnel": "bridge"})])
        route = routing.run(routing.route_steps(
            g, grid_to_latlon(0, 500), grid_to_latlon(500, 0)))
        self.assertIsNone(route)

    def test_tile_seam_overlap_joins(self):
        # Одна дорога, разрезанная по краю тайла с запасом: две копии
        # перекрываются, у концов копий нет общих вершин.
        g = graph([
            ([(0, 0), (1000, 0), (1100, 0)], {"class": "minor"}),
            ([(1050, 0), (1150, 0), (2000, 0)], {"class": "minor"})])
        route = routing.run(routing.route_steps(
            g, grid_to_latlon(10, 0), grid_to_latlon(1990, 0)))
        self.assertIsNotNone(route)

    def test_unreachable_point(self):
        g = graph([([(0, 0), (100, 0)], {"class": "minor"})])
        far = grid_to_latlon(0, 0)
        self.assertIsNone(routing.run(routing.route_steps(
            g, far, (far[0] + 1.0, far[1]))))


class TestCorridor(unittest.TestCase):

    def test_tiles_along_line(self):
        a, b = (58.0105, 56.2294), (58.0105, 56.4)
        keys = routing.corridor(a, b, 1500.0)
        xs = sorted({k[1] for k in keys})
        ys = sorted({k[2] for k in keys})
        # Коридор - тайлы, задетые точками, и запас в тайл по краям.
        self.assertTrue(KEY[1] - 2 <= xs[0] <= KEY[1])
        # 0.17° долготы у Перми - около 10 км, тайл - около 1.3 км.
        self.assertGreaterEqual(len(xs), 8)
        self.assertLessEqual(len(ys), 5)
        self.assertTrue(all(k[0] == 14 for k in keys))


if __name__ == "__main__":
    unittest.main()
