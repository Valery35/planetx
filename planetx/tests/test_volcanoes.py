# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вулканы GVP: разбор ответа WFS, периоды, файл профиля."""
import os
import sys
import tempfile
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import volcanoes as vo  # noqa: E402

SAMPLE = (
    "FID,Volcano_Number,Volcano_Name,Volcanic_Landform,"
    "Primary_Volcano_Type,Last_Eruption_Year,Country,Region,Subregion,"
    "Geological_Summary,Latitude,Longitude,Elevation,Tectonic_Setting,"
    "Geologic_Epoch,Evidence_Category\n"
    "1,300250,Klyuchevskoy,Composite,Stratovolcano,2025,Russia,Kamchatka,"
    "x,\"Long, text\",56.056,160.642,4754,Subduction zone,Holocene,"
    "Eruption Observed\n"
    "2,211040,Vesuvius,Composite,Stratovolcano,1944,Italy,Europe,x,s,"
    "40.821,14.426,1281,Subduction zone,Holocene,Eruption Observed\n"
    "3,1,Old,Composite,Caldera,-4350,Japan,x,x,s,35.0,139.0,500,"
    "Subduction zone,Holocene,Eruption Dated\n"
    "4,2,Unknown,Composite,Shield,,Chile,x,x,s,-20.0,-68.0,,"
    "Subduction zone,Holocene,Evidence Credible\n"
    "5,3,Broken,Composite,Shield,,Chile,x,x,s,,,,Rift,Holocene,x\n")


class TestVolcanoes(unittest.TestCase):

    def test_parse_and_periods(self):
        found = vo.parse(SAMPLE.encode("utf-8"))
        self.assertEqual(len(found), 4)
        self.assertEqual(found.period.tolist(), [0, 0, 2, 3])
        self.assertTrue(np.isnan(found.last[3]))
        self.assertEqual(found.last[2], -4350.0)
        number, name, kind, country, setting, evidence = found.text(0)
        self.assertEqual((number, name, kind), ("300250", "Klyuchevskoy",
                                                "Stratovolcano"))
        self.assertEqual(found.text(1)[1], "Vesuvius")
        sizes = vo.sizes(found.elevation)
        self.assertGreater(sizes[0], sizes[1])
        self.assertEqual(float(sizes[3]), vo.SIZE_MIN)

    def test_period_bounds(self):
        self.assertEqual(vo.period_of(1900.0), 0)
        self.assertEqual(vo.period_of(1899.0), 1)
        self.assertEqual(vo.period_of(1500.0), 1)
        self.assertEqual(vo.period_of(-9000.0), 2)
        self.assertEqual(vo.period_of(float("nan")), 3)

    def test_save_load(self):
        found = vo.parse(SAMPLE.encode("utf-8"))
        path = os.path.join(tempfile.mkdtemp(), "v.npz")
        vo.save(found, path)
        back = vo.load(path)
        self.assertEqual(back.text(1), found.text(1))
        self.assertTrue(np.allclose(back.lat, found.lat, atol=1e-4))

    def test_not_a_list(self):
        with self.assertRaises(ValueError):
            vo.parse(b"a,b\n1,2\n")


if __name__ == "__main__":
    unittest.main()
