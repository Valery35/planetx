# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Плиты Slab2 на разрезах: файл зоны, рамки, полоса на гранях.

Файлы зон лежат в хранилище planetx-terrain. Проверка на них идёт,
если переменная PLANETX_TERRAIN_DIR указывает на его локальную копию.
"""
import io
import json
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import cutaway as cw  # noqa: E402
import ellipsoid as el  # noqa: E402
import slabs as sl  # noqa: E402

INDEX = os.path.join(os.path.dirname(CORE), "data", "slab2_index.json")
TERRAIN = os.environ.get("PLANETX_TERRAIN_DIR")


def sample_bytes():
    """Зона 3×4 узла у линии перемены дат, одна клетка пустая."""
    depth = np.array([[100, 200, 300, sl.EMPTY],
                      [150, 250, 350, 450],
                      [200, 300, 400, 500]], dtype=np.int16)
    buffer = io.BytesIO()
    np.savez(buffer, origin=np.array([179.9, 10.0, 0.1]), depth=depth,
             thickness=np.full(depth.shape, 300, dtype=np.int16),
             dip=np.full(depth.shape, 60, dtype=np.uint8))
    return buffer.getvalue()


class TestSlabs(unittest.TestCase):

    def setUp(self):
        el.set_body(el.EARTH)

    def test_load_decodes_depth(self):
        slab = sl.load(sample_bytes(), "tst")
        self.assertEqual(slab.code, "tst")
        self.assertEqual(slab.depth[0, 0], 10.0)
        self.assertEqual(slab.thickness[1, 1], 30.0)
        self.assertTrue(np.isnan(slab.depth[0, 3]))
        with self.assertRaises(sl.SlabError):
            sl.load(b"not npz", "bad")

    def test_depth_wraps_dateline(self):
        slab = sl.load(sample_bytes(), "tst")
        self.assertEqual(sl.depth_at(slab, 9.9, -179.9), 35.0)
        self.assertTrue(np.isnan(sl.depth_at(slab, 0.0, 0.0)))

    def test_band_is_apparent_thickness(self):
        slab = sl.load(sample_bytes(), "tst")
        top, bottom = sl.band([slab], [9.9, 0.0], [-179.9, 0.0])
        self.assertEqual(top[0], 35.0)
        # Толщина 30 км при падении 60° - 60 км по вертикали.
        self.assertAlmostEqual(bottom[0] - top[0], 60.0, places=6)
        self.assertTrue(np.isnan(top[1]))

    def test_box_across_dateline(self):
        box = (40.0, 60.0, 170.0, -170.0)
        got = sl.in_box(box, [50.0, 50.0, 50.0, 30.0],
                        [175.0, -175.0, 0.0, 175.0])
        self.assertEqual(got.tolist(), [True, True, False, False])
        index = {"a": box, "b": (0.0, 10.0, 0.0, 10.0)}
        self.assertEqual(sl.touched(index, [50.0], [179.0]), ["a"])

    def test_bands_on_faces(self):
        slab = sl.load(sample_bytes(), "tst")
        # Западная грань - по 180°, через зону.
        wedge = cw.make_wedge(-180.0, -90.0, 0.0, 90.0)
        mesh = cw.slab_bands(wedge, [slab])
        self.assertIsNotNone(mesh)
        color = np.array(cw.SLAB_COLOR, dtype=np.uint8)
        self.assertTrue(np.all(mesh.vertices["color"][:, :3] == color))
        # Без плиты на дугах сетки нет.
        far = cw.make_wedge(-45.0, 45.0, 0.0, 90.0)
        self.assertIsNone(cw.slab_bands(far, [slab]))

    def test_index_in_module(self):
        with open(INDEX, encoding="utf-8") as fh:
            index = sl.read_index(fh.read())
        self.assertEqual(len(index), 27)
        # Разрез по 143.5° в. д. касается Курильской и Японской зоны.
        lats = np.linspace(0.0, 90.0, 181)
        codes = sl.touched(index, lats, np.full(lats.shape, 143.5))
        self.assertIn("kur", codes)
        self.assertNotIn("sam", codes)

    @unittest.skipUnless(TERRAIN, "нет PLANETX_TERRAIN_DIR")
    def test_zone_files(self):
        with open(INDEX, encoding="utf-8") as fh:
            codes = list(json.load(fh))
        for code in codes:
            with open(os.path.join(TERRAIN, "slab2", code + ".npz"),
                      "rb") as fh:
                slab = sl.load(fh.read(), code)
            self.assertTrue(np.any(np.isfinite(slab.depth)), code)
        with open(os.path.join(TERRAIN, "slab2", "kur.npz"), "rb") as fh:
            kur = sl.load(fh.read(), "kur")
        # Плита под Хоккайдо на 80-160 км, на западе глубже 600 км.
        self.assertTrue(80.0 < sl.depth_at(kur, 43.0, 143.0) < 160.0)
        self.assertGreater(np.nanmax(kur.depth), 600.0)


if __name__ == "__main__":
    unittest.main()
