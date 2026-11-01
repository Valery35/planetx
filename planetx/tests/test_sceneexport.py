# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сцена вида в glTF и 3D Tiles."""
import json
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import ellipsoid  # noqa: E402
import gltf  # noqa: E402
import sceneexport as se  # noqa: E402


def wall(lat=58.0, lon=56.0, up=10.0):
    """Треугольник: вершина up метров над точкой и две на земле."""
    center = np.asarray(ellipsoid.geodetic_to_ecef(lat, lon, 0.0),
                        dtype=np.float64).reshape(3)
    axes = se.enu_axes(lat, lon)
    points = np.array([(0.0, 0.0, up), (5.0, 0.0, 0.0), (0.0, 5.0, 0.0)])
    positions = (points @ axes).astype(np.float32)
    colors = np.array([(255, 0, 0, 255)] * 3, dtype=np.uint8)
    return se.Item(center, positions, None, colors,
                   np.array([[0, 1, 2]], dtype=np.uint32))


def chunks(data):
    magic, version, length = struct.unpack_from("<III", data, 0)
    size, _ = struct.unpack_from("<II", data, 12)
    document = json.loads(data[20:20 + size])
    blob = data[20 + size + 8:]
    return magic, version, length, document, blob


def accessor(document, blob, number):
    entry = document["accessors"][number]
    view = document["bufferViews"][entry["bufferView"]]
    kinds = {se.FLOAT: "<f4", se.UBYTE: "u1", se.UINT: "<u4"}
    sizes = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}
    data = np.frombuffer(blob, dtype=kinds[entry["componentType"]],
                         count=entry["count"] * sizes[entry["type"]],
                         offset=view["byteOffset"])
    return data.reshape(-1, sizes[entry["type"]])


class TestGlb(unittest.TestCase):

    def test_structure(self):
        data = se.scene_glb([wall()], 58.0, 56.0)
        magic, version, length, document, _ = chunks(data)
        self.assertEqual(magic, se.GLB_MAGIC)
        self.assertEqual(version, 2)
        self.assertEqual(length, len(data))
        self.assertEqual(len(data) % 4, 0)
        self.assertEqual(document["asset"]["extras"]["origin"]["lat"], 58.0)

    def test_up_is_y_and_east_is_x(self):
        data = se.scene_glb([wall()], 58.0, 56.0)
        _, _, _, document, blob = chunks(data)
        primitive = document["meshes"][0]["primitives"][0]
        points = accessor(document, blob, primitive["attributes"]["POSITION"])
        self.assertAlmostEqual(float(points[0][1]), 10.0, places=2)
        self.assertAlmostEqual(float(points[1][0]), 5.0, places=2)
        # Север - минус Z.
        self.assertAlmostEqual(float(points[2][2]), -5.0, places=2)

    def test_normals_are_unit(self):
        data = se.scene_glb([wall()], 58.0, 56.0)
        _, _, _, document, blob = chunks(data)
        primitive = document["meshes"][0]["primitives"][0]
        normals = accessor(document, blob, primitive["attributes"]["NORMAL"])
        self.assertTrue(np.allclose(np.linalg.norm(normals, axis=1), 1.0,
                                    atol=1e-5))

    def test_reader_of_module_opens_it(self):
        parts = gltf.read(se.scene_glb([wall()], 58.0, 56.0), lambda ref: None)
        self.assertTrue(parts)

    def test_picture_goes_inside_file(self):
        item = wall()._replace(colors=None, picture=b"\x89PNG0000",
                               uvs=np.zeros((3, 2), dtype=np.float32))
        _, _, _, document, _ = chunks(se.scene_glb([item], 58.0, 56.0))
        self.assertEqual(document["images"][0]["mimeType"], "image/png")
        self.assertIn("baseColorTexture", document["materials"][0]
                      ["pbrMetallicRoughness"])


class TestTileset(unittest.TestCase):

    def test_vertices_return_to_ecef(self):
        item = wall()
        text, files = se.tileset([item])
        root = json.loads(text)["root"]
        child = root["children"][0]
        self.assertEqual(child["content"]["uri"], files[0][0])
        _, _, _, document, blob = chunks(files[0][1])
        primitive = document["meshes"][0]["primitives"][0]
        points = accessor(document, blob, primitive["attributes"]["POSITION"])
        # Читатель 3D Tiles: glTF Y вверх в Z вверх - (x, -z, y).
        back = np.stack((points[:, 0], -points[:, 2], points[:, 1]), axis=1)
        moved = back + np.array(child["transform"][12:15])
        expected = item.positions + item.center
        self.assertLess(float(np.abs(moved - expected).max()), 0.01)

    def test_root_holds_every_tile(self):
        items = [wall(58.0, 56.0), wall(58.01, 56.0)]
        text, files = se.tileset(items)
        root = json.loads(text)["root"]
        self.assertEqual(len(files), 2)
        middle = np.array(root["boundingVolume"]["sphere"][:3])
        reach = root["boundingVolume"]["sphere"][3]
        for item in items:
            self.assertLessEqual(
                float(np.linalg.norm(item.center - middle)), reach)

    def test_empty_gives_nothing(self):
        self.assertEqual(se.tileset([]), (None, []))


if __name__ == "__main__":
    unittest.main()
