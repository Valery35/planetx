# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Крупные файлы демо в planetx-terrain: адреса, поиск, проверка."""
import os
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

import demofiles  # noqa: E402

DEMO = os.path.join(os.path.dirname(HERE), "demo")


class TestDemoFiles(unittest.TestCase):
    def test_sizes_match_working_copy(self):
        # Размер в списке - сторож пересборки файла без правки списка.
        for path, size in demofiles.FILES.items():
            full = os.path.join(DEMO, *path.split("/"))
            if os.path.exists(full):
                self.assertEqual(os.path.getsize(full), size, path)

    def test_url_keeps_demo_layout(self):
        # Файл в planetx-terrain/demo лежит по тому же пути, что в папке
        # demo модуля.
        self.assertEqual(
            demofiles.url("quarry/quarry_dem.tif"),
            "https://raw.githubusercontent.com/Valery35/planetx-terrain/"
            "main/demo/quarry/quarry_dem.tif")

    def test_wrong_size_is_missing(self):
        with tempfile.TemporaryDirectory() as folder:
            self.assertEqual(demofiles.missing("brienz", [folder]),
                             ["brienz/brienzersee_bed.tif"])
            os.makedirs(os.path.join(folder, "brienz"))
            target = os.path.join(folder, "brienz", "brienzersee_bed.tif")
            with open(target, "wb") as fh:
                fh.write(b"<html>Not Found</html>")
            self.assertEqual(len(demofiles.missing("brienz", [folder])), 1)
            with open(target, "wb") as fh:
                fh.write(b"\0" * demofiles.FILES[
                    "brienz/brienzersee_bed.tif"])
            self.assertEqual(demofiles.missing("brienz", [folder]), [])
            self.assertEqual(
                demofiles.locate("brienz/brienzersee_bed.tif",
                                 ["nowhere", folder]), target)

    def test_other_demos_need_nothing(self):
        self.assertEqual(demofiles.missing("perm", []), [])


if __name__ == "__main__":
    unittest.main()
