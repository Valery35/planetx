# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Анимация узлов 3D-моделей glTF и Collada."""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import animation  # noqa: E402
import collada  # noqa: E402
import gltf  # noqa: E402
import models  # noqa: E402
from test_models import glb  # noqa: E402

TRIANGLE = [[0, 0, 0], [1, 0, 0], [0, 1, 0]]


def moved(delta, point):
    return (delta @ np.append(point, 1.0))[:3]


def channel_doc(nodes, path, node, times, values, kind):
    def extra(doc, add):
        doc["nodes"] = nodes
        doc["scenes"] = [{"nodes": [0]}]
        doc["animations"] = [{
            "samplers": [{"input": add(np.asarray(times, np.float32),
                                       "SCALAR", 5126),
                          "output": add(np.asarray(values, np.float32),
                                        kind, 5126)}],
            "channels": [{"sampler": 0,
                          "target": {"node": node, "path": path}}]}]
    return glb(TRIANGLE, [0, 1, 2], extra=extra)


class TestSample(unittest.TestCase):

    def test_linear_step_and_ends(self):
        times = [0.0, 2.0]
        values = [[0.0], [10.0]]
        self.assertAlmostEqual(animation.sample(times, values, 0.5)[0], 2.5)
        self.assertEqual(animation.sample(times, values, 0.5,
                                          animation.STEP)[0], 0.0)
        self.assertEqual(animation.sample(times, values, -1.0)[0], 0.0)
        self.assertEqual(animation.sample(times, values, 5.0)[0], 10.0)

    def test_cubic_spline_with_flat_tangents(self):
        # Касательная входа, значение, касательная выхода.
        values = [[0.0], [0.0], [0.0], [0.0], [10.0], [0.0]]
        mid = animation.sample([0.0, 1.0], values, 0.5, animation.CUBIC)
        self.assertAlmostEqual(mid[0], 5.0)
        quarter = animation.sample([0.0, 1.0], values, 0.25,
                                   animation.CUBIC)
        self.assertLess(quarter[0], 2.5)

    def test_slerp_half_turn(self):
        half = math.sqrt(0.5)
        q = animation.sample_rotation([0.0, 1.0], [[0, 0, 0, 1],
                                                   [0, half, 0, half]], 0.5)
        angle = 2 * math.degrees(math.acos(q[3]))
        self.assertAlmostEqual(angle, 45.0, places=4)


class TestGltf(unittest.TestCase):

    def test_parent_translation_moves_child_mesh(self):
        nodes = [{"children": [1]}, {"mesh": 0, "translation": [1, 0, 0]}]
        data = channel_doc(nodes, "translation", 0, [0.0, 2.0],
                           [[0, 0, 0], [0, 10, 0]], "VEC3")
        parts, _, moving = gltf.read_animated(data, lambda uri: None)
        self.assertEqual([p.track for p in parts], [0])
        self.assertAlmostEqual(moving.duration, 2.0)
        rest = parts[0].positions[0]
        np.testing.assert_allclose(rest, [1, 0, 0], atol=1e-9)
        # Y glTF вверх - Z модуля вверх.
        delta = moving.deltas(1.0)[0]
        np.testing.assert_allclose(moved(delta, rest), [1, 0, 5],
                                   atol=1e-6)
        # Время идёт по кругу длительности.
        np.testing.assert_allclose(moving.deltas(3.0)[0], delta, atol=1e-9)

    def test_rotation_about_up_axis(self):
        half = math.sqrt(0.5)
        data = channel_doc([{"mesh": 0}], "rotation", 0, [0.0, 1.0],
                           [[0, 0, 0, 1], [0, half, 0, half]], "VEC4")
        parts, _, moving = gltf.read_animated(data, lambda uri: None)
        point = parts[0].positions[1]
        np.testing.assert_allclose(point, [1, 0, 0], atol=1e-9)
        turned = moved(moving.deltas(0.5)[0], point)
        # Поворот glTF вокруг Y на 45° - поворот вокруг Z модуля.
        np.testing.assert_allclose(turned, [half, half, 0], atol=1e-6)

    def test_still_model_has_no_animation(self):
        parts, _, moving = gltf.read_animated(glb(TRIANGLE, [0, 1, 2]),
                                              lambda uri: None)
        self.assertIsNone(moving)
        self.assertIsNone(parts[0].track)

    def test_merge_keeps_moving_parts_apart(self):
        still = models.Part(np.zeros((3, 3)), None, None, None,
                            (1, 1, 1, 1))
        moving = models.Part(np.ones((3, 3)), None, None, None,
                             (1, 1, 1, 1), track=0)
        merged = models.merge([still, moving])
        self.assertEqual(sorted(p.track is None for p in merged),
                         [False, True])


DAE = b"""<?xml version="1.0" encoding="utf-8"?>
<COLLADA xmlns="http://www.collada.org/2005/11/COLLADASchema"
 version="1.4.1">
<asset><unit meter="0.5"/><up_axis>Z_UP</up_axis></asset>
<library_animations><animation>
<source id="t"><float_array id="ta" count="2">0 4</float_array>
<technique_common><accessor source="#ta" count="2" stride="1"/>
</technique_common></source>
<source id="x"><float_array id="xa" count="2">0 8</float_array>
<technique_common><accessor source="#xa" count="2" stride="1"/>
</technique_common></source>
<sampler id="s"><input semantic="INPUT" source="#t"/>
<input semantic="OUTPUT" source="#x"/></sampler>
<channel source="#s" target="n/location.X"/>
</animation></library_animations>
<library_geometries><geometry id="g"><mesh>
<source id="pos"><float_array id="pa" count="9">0 0 0 1 0 0 0 1 0
</float_array><technique_common><accessor source="#pa" count="3"
 stride="3"/></technique_common></source>
<vertices id="v"><input semantic="POSITION" source="#pos"/></vertices>
<triangles count="1"><input semantic="VERTEX" source="#v" offset="0"/>
<p>0 1 2</p></triangles></mesh></geometry></library_geometries>
<library_visual_scenes><visual_scene id="vs">
<node id="n"><translate sid="location">0 0 0</translate>
<instance_geometry url="#g"/></node>
<node id="still"><instance_geometry url="#g"/></node>
</visual_scene></library_visual_scenes>
<scene><instance_visual_scene url="#vs"/></scene>
</COLLADA>
"""


class TestCollada(unittest.TestCase):

    def test_keyed_translate_component_in_metres(self):
        parts, moving = collada.read_dae_animated(DAE)
        self.assertEqual([p.track for p in parts], [0, None])
        self.assertAlmostEqual(moving.duration, 4.0)
        delta = moving.deltas(2.0)[0]
        # 4 единицы файла по 0.5 м.
        np.testing.assert_allclose(delta[:3, 3], [2, 0, 0], atol=1e-9)
        np.testing.assert_allclose(delta[:3, :3], np.eye(3), atol=1e-9)

    def test_package_reads_animation(self):
        data = models.pack("a.dae", {"a.dae": DAE})
        parts, _, moving = models.read_animated(data)
        self.assertIsNotNone(moving)
        self.assertEqual(sorted(p.track is None for p in parts),
                         [False, True])

    def test_frame_delta_in_ecef(self):
        frame = models.frame(57.9, 56.2, heading=30.0)
        delta = np.eye(4)
        delta[:3, 3] = [0, 0, 3]
        linear, shift = animation.frame_delta(frame, delta)
        np.testing.assert_allclose(linear, np.eye(3), atol=1e-9)
        np.testing.assert_allclose(shift, frame @ [0, 0, 3], atol=1e-9)


if __name__ == "__main__":
    unittest.main()
