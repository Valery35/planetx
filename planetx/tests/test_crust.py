# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кора CRUST1.0: разбор файла границ, ячейки, слои.

Модель в модуль не входит. Проверка на настоящем файле идёт, если
переменная PLANETX_CRUST1 указывает на архив crust1.0.tar.gz.
"""
import io
import os
import sys
import tarfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import crust as cr  # noqa: E402


def sample_bounds():
    """Отметки, по которым видна ячейка: Мохо = -(строка + столбец/1000)."""
    b = np.zeros((cr.ROWS, cr.COLS, cr.BOUNDS), dtype=np.float32)
    row, col = np.meshgrid(np.arange(cr.ROWS), np.arange(cr.COLS),
                           indexing="ij")
    b[..., 0] = 1.0
    b[..., 1] = 1.0
    b[..., 2] = 1.0
    b[..., 3:8] = np.linspace(0.0, -5.0, 5)
    b[..., 8] = -(10.0 + row + col / 1000.0)
    return b


def as_text(bounds):
    lines = (" ".join("%7.3f" % v for v in cell)
             for cell in bounds.reshape(-1, cr.BOUNDS))
    return "\n".join(lines).encode("ascii")


def as_archive(text):
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
        info = tarfile.TarInfo(cr.MEMBER)
        info.size = len(text)
        tar.addfile(info, io.BytesIO(text))
    return buffer.getvalue()


class TestCrust(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.model = cr.from_archive(as_archive(as_text(sample_bounds())))

    def test_cells_follow_file_order(self):
        # Первая строка - 89.5° с. ш., первый столбец - 179.5° з. д.
        row, col = cr.cells([89.9, 0.5, -89.9, 10.0],
                            [-179.9, 0.5, 179.9, 190.0])
        # Широта 10° - граница ячеек, точка уходит в южную, 9-10°.
        self.assertEqual(row.tolist(), [0, 89, 179, 80])
        self.assertEqual(col.tolist(), [0, 180, 359, 10])

    def test_moho_and_thickness_by_cell(self):
        moho = self.model.moho([0.5], [0.5])
        self.assertAlmostEqual(float(moho[0]), 10.0 + 89 + 0.180, places=3)
        thick = self.model.thickness([0.5], [0.5])
        self.assertAlmostEqual(float(thick[0]), 1.0 + 99.180, places=3)

    def test_layers_skip_empty(self):
        layers = self.model.layers([0.5], [0.5])[0]
        keys = [k for k, _, _ in layers]
        # Вода и лёд нулевой толщины пропущены.
        self.assertNotIn("water", keys)
        self.assertNotIn("ice", keys)
        self.assertEqual(keys[-1], "crust_lower")
        for (_, top, bottom), (_, below, _) in zip(layers, layers[1:]):
            self.assertGreater(top, bottom)
            self.assertEqual(bottom, below)

    def test_bad_files_raise(self):
        with self.assertRaises(cr.CrustError):
            cr.parse_bounds(b"1 2 3")
        with self.assertRaises(cr.CrustError):
            cr.from_archive(b"not an archive")


@unittest.skipUnless(os.environ.get("PLANETX_CRUST1"),
                     "нет PLANETX_CRUST1 - архива CRUST1.0")
class TestRealModel(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(os.environ["PLANETX_CRUST1"], "rb") as f:
            cls.model = cr.from_archive(f.read())

    def test_ocean_is_thin_and_continent_thick(self):
        # Тихий океан, Тибет, Пермский край.
        lats, lons = [0.5, 32.5, 59.5], [-150.5, 88.5, 56.5]
        thick = self.model.thickness(lats, lons)
        moho = self.model.moho(lats, lons)
        self.assertLess(thick[0], 10.0)
        self.assertGreater(moho[0], 8.0)
        self.assertGreater(thick[1], 60.0)
        self.assertTrue(35.0 < thick[2] < 50.0)
        water = self.model.layers(lats[:1], lons[:1])[0][0]
        self.assertEqual(water[0], "water")
        self.assertGreater(-water[2], 3.0)


if __name__ == "__main__":
    unittest.main()
