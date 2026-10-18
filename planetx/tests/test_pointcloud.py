# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек: разбор LAS, клетки, выбор по экрану, цвета."""
import json
import math
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import ellipsoid  # noqa: E402
import pointcloud as pc  # noqa: E402

LENGTHS = {3: 34, 7: 36}


def make_las(xyz, cls, rgb=None, fmt=7, scale=(1e-7, 1e-7, 0.001),
             offset=(0.0, 0.0, 0.0)):
    """Файл LAS без сжатия: 1.4 у формата 7, 1.2 у формата 3."""
    xyz = np.asarray(xyz, dtype=np.float64)
    count = len(xyz)
    length = LENGTHS[fmt]
    minor = 4 if fmt >= 6 else 2
    header_size = 375 if minor == 4 else 227
    head = bytearray(header_size)
    head[:4] = b"LASF"
    head[24], head[25] = 1, minor
    struct.pack_into("<H", head, 94, header_size)
    struct.pack_into("<I", head, 96, header_size)
    head[104] = fmt
    struct.pack_into("<H", head, 105, length)
    struct.pack_into("<I", head, 107, count)
    struct.pack_into("<6d", head, 131, *scale, *offset)
    if minor == 4:
        struct.pack_into("<Q", head, 247, count)
    rows = np.zeros((count, length), dtype=np.uint8)
    ints = np.round((xyz - offset) / scale).astype("<i4")
    rows[:, :12] = ints.view(np.uint8).reshape(count, 12)
    rows[:, 12:14] = np.full(count, 500, "<u2").view(np.uint8) \
        .reshape(count, 2)
    if fmt >= 6:
        rows[:, 16] = cls
        rgb_at = 30
    else:
        rows[:, 15] = np.asarray(cls, dtype=np.uint8) | 0x20  # флаг Synthetic
        rgb_at = 28
    if rgb is not None:
        wide = (np.asarray(rgb, dtype=np.uint16) * 256).astype("<u2")
        rows[:, rgb_at:rgb_at + 6] = wide.view(np.uint8).reshape(count, 6)
    return bytes(head) + rows.tobytes()


class FakeFrame:
    """Камера для выбора: всё видно, ошибка - шаг клетки, делённый
    на расстояние, глаз в точке eye."""

    def __init__(self, eye, focal=1000.0):
        self.eye = np.asarray(eye, dtype=np.float64)
        self.focal = focal

    def visible(self, z, info):
        return True

    def error(self, info):
        d = max(math.dist(info.center, self.eye) - info.radius, 0.5)
        return info.texel * self.focal / d


CLOUD = pc.Cloud(0.0, 0.0, 0.01, 0.01, 100.0, 120.0, 100000)


def geo(xs, ys):
    return np.asarray(xs) + 56.0, np.asarray(ys) + 58.0


def info_of(key):
    return pc.cell_info(CLOUD, key, geo, 1.0, 1.0)


class TestReadLas(unittest.TestCase):

    def test_format_7_with_colour(self):
        xyz = [(56.1, 58.2, 120.5), (56.10001, 58.20002, 121.0)]
        data = make_las(xyz, [2, 6], rgb=[(10, 20, 30), (200, 100, 50)],
                        offset=(56.0, 58.0, 100.0))
        points = pc.read_las(data)
        self.assertEqual(len(points.x), 2)
        self.assertAlmostEqual(points.x[1], 56.10001, places=6)
        self.assertAlmostEqual(points.y[1], 58.20002, places=6)
        self.assertAlmostEqual(points.z[0], 120.5, places=3)
        self.assertEqual(points.cls.tolist(), [2, 6])
        self.assertEqual(points.rgb.tolist(), [[10, 20, 30], [200, 100, 50]])
        self.assertEqual(points.intensity.tolist(), [500, 500])

    def test_format_3_class_in_low_bits(self):
        data = make_las([(1.0, 2.0, 3.0)], [9], rgb=None, fmt=3,
                        scale=(0.01, 0.01, 0.01))
        points = pc.read_las(data)
        # Старшие биты байта класса - флаги, класс - пять младших.
        self.assertEqual(points.cls.tolist(), [9])
        self.assertIsNone(points.rgb)

    def test_not_las_is_refused(self):
        with self.assertRaises(ValueError):
            pc.read_las(b"<html>" + bytes(400))

    def test_real_pdal_output(self):
        # Ответ PDAL по облаку Autzen: файл из PLANETX_POINTCLOUD_LAS.
        path = os.environ.get("PLANETX_POINTCLOUD_LAS")
        if not path or not os.path.exists(path):
            self.skipTest("нет PLANETX_POINTCLOUD_LAS")
        with open(path, "rb") as handle:
            points = pc.read_las(handle.read())
        self.assertGreater(len(points.x), 1000)
        self.assertTrue(-180.0 <= float(np.min(points.x)) <= 180.0)
        self.assertTrue(-90.0 <= float(np.min(points.y)) <= 90.0)


class TestUnits(unittest.TestCase):

    def test_vertical_factor(self):
        self.assertAlmostEqual(pc.vertical_factor(
            "+proj=lcc +units=ft +vunits=us-ft"), 1200.0 / 3937.0)
        self.assertEqual(pc.vertical_factor("+proj=utm +units=m"), 1.0)
        self.assertEqual(pc.vertical_factor("+proj=longlat"), 1.0)
        self.assertAlmostEqual(pc.vertical_factor("+proj=lcc +units=ft"),
                               0.3048)


class TestCells(unittest.TestCase):

    def test_bounds_and_resolution(self):
        self.assertEqual(pc.bounds(CLOUD, (0, 0, 0)), (0.0, 0.0, 0.01, 0.01))
        x0, y0, x1, y1 = pc.bounds(CLOUD, (2, 3, 1))
        self.assertAlmostEqual(x0, 0.0075)
        self.assertAlmostEqual(y1, 0.005)
        self.assertAlmostEqual(pc.resolution(CLOUD, 1),
                               0.005 / pc.CELL_GRID)

    def test_max_level_stops_at_own_spacing(self):
        level = pc.max_level(CLOUD)
        native = pc.spacing(CLOUD)
        self.assertLessEqual(pc.resolution(CLOUD, level), native)
        self.assertGreater(pc.resolution(CLOUD, level - 1), native)

    def test_cell_texel_in_metres(self):
        # Клетка 0.01° на 58° с. ш.: около 590 м по долготе.
        info = info_of((0, 0, 0))
        self.assertAlmostEqual(info.texel * pc.CELL_GRID, 1113.0, delta=60.0)


class TestSelect(unittest.TestCase):

    def setUp(self):
        center = np.array(info_of((0, 0, 0)).center)
        up = center / np.linalg.norm(center)
        self.near = FakeFrame(center + up * 300.0)
        self.far = FakeFrame(center + up * 3.0e7)

    def test_root_is_wanted_first(self):
        sel = pc.select(CLOUD, self.near, {}, info_of)
        self.assertEqual(sel.draw, [])
        self.assertEqual([k for _, k in sel.want], [(0, 0, 0)])

    def test_far_view_draws_root_only(self):
        sel = pc.select(CLOUD, self.far, {(0, 0, 0): 5000}, info_of)
        self.assertEqual(sel.draw, [(0, 0, 0)])
        self.assertEqual(sel.want, [])

    def test_children_replace_parent_only_together(self):
        ready = {(0, 0, 0): 5000}
        kids = pc.children((0, 0, 0))
        for kid in kids[:3]:
            ready[kid] = 2000
        sel = pc.select(CLOUD, self.near, ready, info_of)
        # Готовы не все дети - рисуется родитель, недостающий просится.
        self.assertEqual(sel.draw, [(0, 0, 0)])
        self.assertEqual([k for _, k in sel.want], [kids[3]])
        ready[kids[3]] = 0  # пустая клетка тоже готова
        sel = pc.select(CLOUD, self.near, ready, info_of)
        self.assertEqual(sel.draw, sorted(kids[:3]))
        self.assertEqual(sel.points, 6000)

    def test_budget_is_kept(self):
        ready = {(0, 0, 0): 5000}
        for kid in pc.children((0, 0, 0)):
            ready[kid] = 4000
        sel = pc.select(CLOUD, self.near, ready, info_of, budget=10000)
        self.assertEqual(sel.draw, [(0, 0, 0)])
        sel = pc.select(CLOUD, self.near, ready, info_of, budget=20000)
        self.assertEqual(len(sel.draw), 4)
        self.assertLessEqual(sel.points, 20000)


class TestColoursAndVertices(unittest.TestCase):

    def setUp(self):
        self.points = pc.Points(
            np.array([56.0, 56.0001]), np.array([58.0, 58.0001]),
            np.array([100.0, 200.0]), np.array([2, 6], dtype=np.uint8),
            None, np.array([0, 1000], dtype=np.uint16))

    def test_rgb_without_colour_falls_back_to_class(self):
        out = pc.colors(self.points, "rgb")
        self.assertEqual(out[0, :3].tolist(), list(pc.CLASS_COLORS[2]))
        self.assertEqual(out[1, :3].tolist(), list(pc.CLASS_COLORS[6]))
        self.assertEqual(out[:, 3].tolist(), [255, 255])

    def test_height_ramp_ends(self):
        out = pc.colors(self.points, "height", zrange=(100.0, 200.0))
        self.assertEqual(out[0, :3].tolist(), list(pc.HEIGHT_STOPS[0][1]))
        self.assertEqual(out[1, :3].tolist(), list(pc.HEIGHT_STOPS[-1][1]))

    def test_keep_classes(self):
        kept = pc.keep_classes(self.points, {2})
        self.assertEqual(kept.cls.tolist(), [2])
        self.assertIs(pc.keep_classes(self.points, None), self.points)

    def test_vertices_are_offsets_from_center(self):
        cloud = pc.Cloud(56.0, 58.0, 56.0001, 58.0001, 100.0, 200.0, 2)
        center, up = pc.anchor(cloud, (0, 0, 0),
                               lambda xs, ys: (xs, ys))
        offsets, heights = pc.vertices(self.points, center, 0.3048)
        self.assertEqual(offsets.dtype, np.float32)
        self.assertTrue(np.allclose(heights, [30.48, 60.96], atol=1e-4))
        # Шейдер: смещение плюс нормаль клетки × высота × масштаб.
        for scale in (1.0, 2.0):
            back = center + offsets[1].astype(np.float64) \
                + up * float(heights[1]) * scale
            want = np.array(ellipsoid.geodetic_to_ecef(
                58.0001, 56.0001, 200.0 * 0.3048 * scale))
            self.assertLess(float(np.linalg.norm(back - want)), 0.01)

    def test_anchor_is_cell_middle_on_ellipsoid(self):
        center, up = pc.anchor(CLOUD, (0, 0, 0), geo)
        lat, lon, h = ellipsoid.ecef_to_geodetic(center)
        self.assertAlmostEqual(float(lat), 58.005, places=6)
        self.assertAlmostEqual(float(lon), 56.005, places=6)
        self.assertAlmostEqual(float(h), 0.0, places=3)
        self.assertAlmostEqual(float(np.linalg.norm(up)), 1.0)

    def test_flat_relief_puts_cloud_bottom_on_ellipsoid(self):
        cloud = pc.Cloud(0, 0, 1, 1, 100.0, 200.0, 2)
        heights = pc.display(np.array([100.0, 200.0]), cloud, 1.0, 0.0)
        self.assertEqual(heights.tolist(), [0.0, 100.0])


class TestStyleAndPick(unittest.TestCase):

    def test_style_defaults_and_cleanup(self):
        self.assertEqual(pc.style(None),
                         {"mode": "rgb", "size": pc.POINT_SIZE,
                          "classes": None})
        got = pc.style({"mode": "class", "size": 40, "classes": [6, 2, 2,
                                                                 300]})
        self.assertEqual(got, {"mode": "class", "size": 16.0,
                               "classes": [2, 6]})
        self.assertEqual(pc.style({"mode": "x", "size": "a"})["mode"], "rgb")

    def test_ray_span_between_heights(self):
        eye = np.array(ellipsoid.geodetic_to_ecef(58.0, 56.0, 1000.0))
        down = -eye / np.linalg.norm(eye)
        top, bottom = pc.ray_span(eye, down, 100.0, 300.0)
        self.assertAlmostEqual(float(ellipsoid.ecef_to_geodetic(top)[2]),
                               300.0, delta=1.0)
        self.assertAlmostEqual(
            float(ellipsoid.ecef_to_geodetic(bottom)[2]), 100.0, delta=1.0)
        up = -down
        self.assertIsNone(pc.ray_span(eye, up, 100.0, 300.0))

    def test_pick_nearest_on_screen_then_eye(self):
        pixels = [(100.0, 100.0), (103.0, 100.0), (103.0, 100.4),
                  (300.0, 300.0)]
        front = [True, True, True, True]
        # Две точки на одном пикселе - ближняя к глазу.
        self.assertEqual(pc.pick(pixels, front, [50, 40, 30, 10],
                                 103.0, 100.0), 2)
        self.assertIsNone(pc.pick(pixels, front, [1, 1, 1, 1], 500, 500))
        self.assertIsNone(pc.pick([], [], [], 0, 0))


class TestPipeline(unittest.TestCase):

    def test_cell_pipeline(self):
        text = pc.pipeline("C:/a.copc.laz", CLOUD, (1, 1, 0), "C:/o.las")
        stages = json.loads(text)["pipeline"]
        self.assertEqual([s["type"] for s in stages],
                         ["readers.copc", "filters.reprojection",
                          "writers.las"])
        self.assertIn("[0.005, 0.01]", stages[0]["bounds"])
        self.assertAlmostEqual(stages[0]["resolution"],
                               pc.resolution(CLOUD, 1))
        self.assertFalse(stages[2]["compression"])

    def test_convert_pipeline(self):
        stages = json.loads(pc.convert_pipeline("a.laz", "b.copc.laz"))
        self.assertEqual(stages["pipeline"][1]["type"], "writers.copc")


if __name__ == "__main__":
    unittest.main()
