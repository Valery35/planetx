# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-модели: Collada, glTF, пакет файлов, место по KML."""
import json
import math
import os
import struct
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import io  # noqa: E402
import zipfile  # noqa: E402

import collada  # noqa: E402
import ellipsoid  # noqa: E402
import gltf  # noqa: E402
import kml  # noqa: E402
import models  # noqa: E402
from camera import enu  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16

# Как пишет SketchUp: дюймы, Z вверх, узел со сдвигом, картинка через
# surface и sampler2D, квадрат - polylist из одного четырёхугольника,
# стенка цветом с прозрачностью - triangles без нормалей.
DAE = b"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema"
 version="1.4.1">
<asset><unit meter="0.0254" name="inch"/><up_axis>Z_UP</up_axis></asset>
<library_images><image id="img0"><init_from>suzd1/texture0.jpg</init_from>
</image></library_images>
<library_effects>
<effect id="fx0"><profile_COMMON>
<newparam sid="surf"><surface type="2D"><init_from>img0</init_from>
</surface></newparam>
<newparam sid="samp"><sampler2D><source>surf</source></sampler2D>
</newparam>
<technique sid="COMMON"><lambert><diffuse>
<texture texture="samp" texcoord="UVSET0"/></diffuse></lambert>
</technique></profile_COMMON></effect>
<effect id="fx1"><profile_COMMON><technique sid="COMMON"><lambert>
<diffuse><color>1 0 0 1</color></diffuse>
<transparency><float>0.5</float></transparency>
</lambert></technique></profile_COMMON></effect>
</library_effects>
<library_materials>
<material id="m0"><instance_effect url="#fx0"/></material>
<material id="m1"><instance_effect url="#fx1"/></material>
</library_materials>
<library_geometries><geometry id="g"><mesh>
<source id="pos"><float_array id="pa" count="15">
0 0 0 100 0 0 100 100 0 0 100 0 0 0 100</float_array>
<technique_common><accessor source="#pa" count="5" stride="3">
<param name="X" type="float"/><param name="Y" type="float"/>
<param name="Z" type="float"/></accessor></technique_common></source>
<source id="nrm"><float_array id="na" count="3">0 0 1</float_array>
<technique_common><accessor source="#na" count="1" stride="3"/>
</technique_common></source>
<source id="uv"><float_array id="ua" count="8">0 0 1 0 1 1 0 1
</float_array><technique_common><accessor source="#ua" count="4"
 stride="2"/></technique_common></source>
<vertices id="v"><input semantic="POSITION" source="#pos"/></vertices>
<polylist count="1" material="Mat0">
<input semantic="VERTEX" source="#v" offset="0"/>
<input semantic="NORMAL" source="#nrm" offset="1"/>
<input semantic="TEXCOORD" source="#uv" offset="2" set="0"/>
<vcount>4</vcount><p>0 0 0 1 0 1 2 0 2 3 0 3</p></polylist>
<triangles count="1" material="Mat1">
<input semantic="VERTEX" source="#v" offset="0"/>
<p>0 1 4</p></triangles>
<lines count="1"><input semantic="VERTEX" source="#v" offset="0"/>
<p>0 1</p></lines>
</mesh></geometry></library_geometries>
<library_nodes><node id="ln"><instance_geometry url="#g">
<bind_material><technique_common>
<instance_material symbol="Mat0" target="#m0"/>
<instance_material symbol="Mat1" target="#m1"/>
</technique_common></bind_material></instance_geometry></node>
</library_nodes>
<library_visual_scenes><visual_scene id="s">
<node><matrix>1 0 0 1000 0 1 0 0 0 0 1 0 0 0 0 1</matrix>
<instance_node url="#ln"/></node>
</visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#s"/></scene>
</COLLADA>
"""


def glb(positions, indices, uv=None, picture=None, matrix=None):
    """Двоичный glTF из массивов."""
    blob = bytearray()
    views = []
    accessors = []

    def add(array, kind, ctype, target=None):
        while len(blob) % 4:
            blob.append(0)
        data = np.ascontiguousarray(array).tobytes()
        views.append({"buffer": 0, "byteOffset": len(blob),
                      "byteLength": len(data)})
        blob.extend(data)
        acc = {"bufferView": len(views) - 1, "componentType": ctype,
               "count": len(array), "type": kind}
        accessors.append(acc)
        return len(accessors) - 1

    attributes = {"POSITION": add(np.asarray(positions, np.float32),
                                  "VEC3", 5126)}
    if uv is not None:
        attributes["TEXCOORD_0"] = add(np.asarray(uv, np.float32),
                                       "VEC2", 5126)
    prim = {"attributes": attributes,
            "indices": add(np.asarray(indices, np.uint16), "SCALAR",
                           5123)}
    doc = {"asset": {"version": "2.0"}, "scene": 0,
           "scenes": [{"nodes": [0]}], "meshes": [{"primitives": [prim]}],
           "nodes": [{"mesh": 0}], "accessors": accessors,
           "bufferViews": views}
    if matrix is not None:
        doc["nodes"][0]["matrix"] = matrix
    if picture is not None:
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob),
                      "byteLength": len(picture)})
        blob.extend(picture)
        doc["images"] = [{"bufferView": len(views) - 1,
                          "mimeType": "image/png"}]
        doc["textures"] = [{"source": 0}]
        doc["materials"] = [{"pbrMetallicRoughness": {
            "baseColorTexture": {"index": 0},
            "baseColorFactor": [1, 1, 1, 1]}}]
        prim["material"] = 0
    while len(blob) % 4:
        blob.append(0)
    doc["buffers"] = [{"byteLength": len(blob)}]
    text = json.dumps(doc).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(blob)
    return (b"glTF" + struct.pack("<II", 2, total)
            + struct.pack("<I", len(text)) + b"JSON" + text
            + struct.pack("<I", len(blob)) + b"BIN\x00" + bytes(blob))


class TestCollada(unittest.TestCase):

    def test_sketchup_style_file(self):
        parts = collada.read_dae(DAE)
        self.assertEqual(len(parts), 2)
        square, wall = parts
        # Четырёхугольник - два треугольника веером.
        self.assertEqual(square.positions.shape, (6, 3))
        self.assertEqual(square.image, "suzd1/texture0.jpg")
        # Дюймы в метры, узел сдвинул на 1000 дюймов по X.
        self.assertAlmostEqual(square.positions[:, 0].min(), 25.4)
        self.assertAlmostEqual(square.positions[:, 0].max(), 27.94)
        np.testing.assert_allclose(square.normals[0], (0, 0, 1))
        # v перевёрнута: угол с v = 0 в Collada - низ картинки.
        self.assertAlmostEqual(square.uv[0, 1], 1.0)
        self.assertEqual(wall.image, None)
        self.assertEqual(wall.rgba, (1.0, 0.0, 0.0, 0.5))
        self.assertIsNone(wall.normals)

    def test_images_list(self):
        self.assertEqual(collada.images(DAE), ["suzd1/texture0.jpg"])

    def test_y_up_turns_to_z_up(self):
        data = DAE.replace(b"Z_UP", b"Y_UP")
        wall = collada.read_dae(data)[1]
        # Вершина (0, 0, 100) дюймов по оси Z Collada Y_UP - на юг.
        np.testing.assert_allclose(wall.positions[2], (25.4, -2.54, 0.0),
                                   atol=1e-9)

    def test_entities_refused(self):
        bad = b'<!DOCTYPE c [<!ENTITY a "aaaa">]><COLLADA>&a;</COLLADA>'
        with self.assertRaises(models.ModelError):
            collada.read_dae(bad)

    def test_bad_index_is_model_error(self):
        bad = DAE.replace(b"<p>0 1 4</p>", b"<p>0 1 44</p>")
        with self.assertRaises(models.ModelError):
            collada.read_dae(bad)


class TestGltf(unittest.TestCase):

    def test_glb_triangle_with_picture(self):
        data = glb([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2],
                   uv=[(0, 0), (1, 0), (0, 1)], picture=PNG)
        parts, pictures = gltf.read(data, lambda ref: None)
        self.assertEqual(len(parts), 1)
        part = parts[0]
        self.assertEqual(part.image, "gltf:0")
        self.assertEqual(pictures["gltf:0"], PNG)
        # Y вверх glTF - Z вверх модуля.
        np.testing.assert_allclose(part.positions[2], (0, 0, 1))

    def test_node_matrix_by_columns(self):
        move = [1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 5, 0, 0, 1]
        data = glb([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2],
                   matrix=move)
        parts, _ = gltf.read(data, lambda ref: None)
        self.assertAlmostEqual(parts[0].positions[0, 0], 5.0)

    def test_draco_refused(self):
        text = json.dumps({"asset": {"version": "2.0"},
                           "extensionsRequired":
                           ["KHR_draco_mesh_compression"]}).encode()
        with self.assertRaises(models.ModelError):
            gltf.read(text, lambda ref: None)

    def test_strip_unrolls(self):
        order = gltf._triangles(5, 4, None)
        self.assertEqual(order.tolist(), [0, 1, 2, 1, 3, 2])


class TestPackage(unittest.TestCase):

    def test_pack_read_dae_with_texture(self):
        data = models.pack("models/suzd1.dae",
                           {"models/suzd1.dae": DAE,
                            "models/suzd1/texture0.jpg": PNG})
        parts, pictures = models.read(data)
        images = sorted(p.image or "" for p in parts)
        self.assertEqual(images, ["", "models/suzd1/texture0.jpg"])
        self.assertEqual(pictures["models/suzd1/texture0.jpg"], PNG)

    def test_alias_and_missing_picture(self):
        data = models.pack("a.dae", {"a.dae": DAE, "images/t.png": PNG},
                           {"suzd1/texture0.jpg": "images/t.png"})
        parts, pictures = models.read(data)
        self.assertIn("images/t.png", pictures)
        data = models.pack("a.dae", {"a.dae": DAE})
        parts, pictures = models.read(data)
        # Без картинки часть остаётся цветом материала.
        self.assertEqual(pictures, {})
        self.assertTrue(all(p.image is None for p in parts))

    def test_flat_normals_added(self):
        parts, _ = models.read(models.pack("a.dae", {"a.dae": DAE}))
        for part in parts:
            self.assertEqual(part.normals.shape, part.positions.shape)

    def test_glb_package(self):
        data = models.pack("m.glb", {"m.glb": glb(
            [(0, 0, 0), (1, 0, 0), (0, 1, 0)], [0, 1, 2])})
        parts, _ = models.read(data)
        self.assertEqual(len(parts[0].positions), 3)

    def test_vertex_limit(self):
        many = models.Part(np.zeros((9, 3)), None, None, None,
                           models.GRAY)
        old = models.MAX_VERTICES
        models.MAX_VERTICES = 6
        try:
            with self.assertRaises(models.ModelError):
                models.merge([many])
        finally:
            models.MAX_VERTICES = old


class TestPlacement(unittest.TestCase):

    def test_heading_turns_clockwise(self):
        # Ось X модели (восток) при азимуте 90° смотрит на юг.
        turned = models.rotation(90.0, 0.0, 0.0) @ (1.0, 0.0, 0.0)
        np.testing.assert_allclose(turned, (0.0, -1.0, 0.0), atol=1e-12)
        # Ось Y (север) - на восток.
        turned = models.rotation(90.0, 0.0, 0.0) @ (0.0, 1.0, 0.0)
        np.testing.assert_allclose(turned, (1.0, 0.0, 0.0), atol=1e-12)

    def test_frame_maps_model_axes_to_enu(self):
        lat, lon = 56.42, 40.44
        east, north, up = enu(lat, lon)
        matrix = models.frame(lat, lon, scale=(2.0, 2.0, 2.0))
        np.testing.assert_allclose(matrix @ (0, 0, 1), 2 * up, atol=1e-12)
        np.testing.assert_allclose(matrix @ (1, 0, 0), 2 * east,
                                   atol=1e-12)
        np.testing.assert_allclose(matrix @ (0, 1, 0), 2 * north,
                                   atol=1e-12)

    def test_vertices_relative_to_anchor(self):
        part = models.Part([(0, 0, 0), (10, 0, 0), (0, 0, 20)],
                           [(0, -1, 0)] * 3, [(0, 0)] * 3, None,
                           models.GRAY)
        lat, lon = 56.42, 40.44
        array = models.vertices([part], lat, lon)[0]
        top = models.anchor(lat, lon, "clampToGround", 0.0, 100.0) \
            + array["position"][2].astype(np.float64)
        back = ellipsoid.ecef_to_geodetic(top)
        self.assertAlmostEqual(float(back[2]), 120.0, places=2)

    def test_mirror_keeps_winding_outward(self):
        part = models.Part([(0, 0, 0), (1, 0, 0), (0, 1, 0)],
                           [(0, 0, 1)] * 3, [(0, 0)] * 3, None,
                           models.GRAY)
        plain = models.vertices([part], 0.0, 0.0)[0]
        mirror = models.vertices([part], 0.0, 0.0,
                                 scale=(-1.0, 1.0, 1.0))[0]
        a, b, c = (p.astype(np.float64) for p in plain["position"])
        d, e, f = (p.astype(np.float64) for p in mirror["position"])
        n1 = np.cross(b - a, c - a)
        n2 = np.cross(e - d, f - d)
        # Нормаль по обходу у отражённой модели смотрит в ту же сторону,
        # что нормаль вершины.
        self.assertGreater(float(n1 @ plain["normal"][0]), 0.0)
        self.assertGreater(float(n2 @ mirror["normal"][0]), 0.0)

    def test_anchor_modes(self):
        lat, lon = 10.0, 20.0

        def height(mode, alt):
            point = models.anchor(lat, lon, mode, alt, 150.0, scale=2.0)
            return float(ellipsoid.ecef_to_geodetic(point)[2])
        self.assertAlmostEqual(height("clampToGround", 30.0), 150.0, 3)
        self.assertAlmostEqual(height("relativeToGround", 30.0), 180.0, 3)
        self.assertAlmostEqual(height("absolute", 100.0), 200.0, 3)

    def test_radius(self):
        part = models.Part([(3, 4, 0), (0, 0, 0), (0, 0, 0)], None, None,
                           None, models.GRAY)
        self.assertAlmostEqual(models.radius([part]), 5.0)
        self.assertAlmostEqual(models.radius([part], (2, 2, 2)), 10.0)
        self.assertTrue(math.isfinite(models.radius([part])))


MODEL_KML = b"""<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Church</name><Model><altitudeMode>relativeToGround
</altitudeMode><Location><longitude>40.44</longitude><latitude>56.42
</latitude><altitude>2</altitude></Location><Orientation>
<heading>88.41885380513968</heading><tilt>0</tilt><roll>0</roll>
</Orientation><Scale><x>0.6721278848236247</x>
<y>1</y><z>1.5</z></Scale><Link><href>models/church.dae</href></Link>
<ResourceMap><Alias><targetHref>../images/t.png</targetHref>
<sourceHref>suzd1/texture0.jpg</sourceHref></Alias></ResourceMap>
</Model></Placemark></Document></kml>"""


def kmz(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestKml(unittest.TestCase):

    def read(self):
        data = kmz({"doc.kml": MODEL_KML, "models/church.dae": DAE,
                    "images/t.png": PNG, "images/unused.png": PNG})
        return kml.read_file(data, "x")

    def test_kmz_model_with_resource_map(self):
        tree = self.read()
        item = tree.overlays()[0]
        self.assertEqual(item.kind, "model")
        self.assertEqual(item.name, "Church")
        self.assertEqual(item.overlay.camera[:4],
                         (56.42, 40.44, 2.0, 88.41885380513968))
        self.assertEqual(item.overlay.scale, (0.6721278848236247, 1.0, 1.5))
        self.assertEqual(item.overlay.mode, "relativeToGround")
        parts, pictures = models.read(item.image)
        self.assertEqual(list(pictures.values()), [PNG])
        # В пакет идёт только картинка по ссылке модели.
        _, files, _ = models.unpack(item.image)
        self.assertEqual(len(files), 2)

    def test_round_trip(self):
        tree = self.read()
        again = kml.read_file(kml.write_kmz(tree), "y").overlays()[0]
        item = tree.overlays()[0]
        # Место без потери знаков: азимут и масштаб из KMZ Google Earth
        # с 16 знаками, запись {:g} оставляла 6.
        self.assertEqual(again.overlay.params(), item.overlay.params())
        parts, pictures = models.read(again.image)
        self.assertEqual(list(pictures.values()), [PNG])
        self.assertEqual(sum(len(p.positions) for p in parts), 9)

    def test_plain_kml_keeps_href(self):
        item = kml.read_kml(MODEL_KML).overlays()[0]
        self.assertIsNone(item.image)
        self.assertEqual(item.href, "models/church.dae")
        self.assertEqual(item.aliases,
                         {"suzd1/texture0.jpg": "../images/t.png"})
        text = kml.write_kml(kml.KFolder("d", children=[item]))
        self.assertIn("<sourceHref>suzd1/texture0.jpg</sourceHref>", text)

    def test_overlay_params_round_trip(self):
        import overlays
        item = self.read().overlays()[0]
        back = overlays.from_params("model", item.overlay.params())
        self.assertEqual(back.camera, item.overlay.camera)
        self.assertEqual(back.scale, item.overlay.scale)
        self.assertEqual(back.mode, item.overlay.mode)


if __name__ == "__main__":
    unittest.main()
