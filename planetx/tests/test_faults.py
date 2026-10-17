# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Активные разломы GEM: виды смещения, значения полей, разбор, поиск."""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import faults  # noqa: E402

# Поля - как в файле базы, записи 17 октября 2026 года.
SAMPLE = {"type": "FeatureCollection", "features": [
    {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
        [-121.9, 37.8], [-121.8, 37.9]]},
     "properties": {"name": "Mount Diablo Thrust", "slip_type": "Reverse",
                    "net_slip_rate": "(1.55,0.8,2.22)",
                    "average_dip": "(38,,)", "dip_dir": "E",
                    "catalog_name": "UCERF3"}},
    {"type": "Feature", "geometry": {"type": "MultiLineString",
                                     "coordinates": [
                                         [[30.0, 40.0], [31.0, 40.0]],
                                         [[32.0, 40.0], [33.0, 40.2]]]},
     "properties": {"fs_name": "North Anatolian", "slip_type": "Dextral",
                    "strike_slip_rate": "(20.0, 15.0, 25.0)"}},
    {"type": "Feature", "geometry": {"type": "Point",
                                     "coordinates": [0.0, 0.0]},
     "properties": {}},
    {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [
        [10.0, 10.0]]}, "properties": {}}]}


class TestFaults(unittest.TestCase):
    def test_kinds(self):
        cases = {"Normal": "normal", "Normal-Dextral": "normal",
                 "Reverse-Strike-Slip": "reverse",
                 "Subduction_Thrust": "reverse", "Blind Thrust": "reverse",
                 "Dextral_Transform": "strike", "Sinistral": "strike",
                 "Strike-Slip": "strike", "Spreading_Ridge": "ridge",
                 "Anticline": "fold", "Syncline": "fold", None: "other",
                 "": "other", "Unknown": "other"}
        for slip, kind in cases.items():
            self.assertEqual(faults.kind_of(slip), kind, slip)
        self.assertEqual(set(faults.COLORS), set(faults.KINDS))

    def test_first_value(self):
        self.assertEqual(faults.first_value("(1.55,0.8,2.22)"), 1.55)
        self.assertEqual(faults.first_value("(38,,)"), 38.0)
        self.assertEqual(faults.first_value("(3.0, 1.0, 5.0)"), 3.0)
        self.assertIsNone(faults.first_value("(,1600000,)"))
        self.assertIsNone(faults.first_value(None))
        self.assertEqual(faults.first_value(2), 2.0)

    def test_parse(self):
        data = faults.parse(json.dumps(SAMPLE).encode("utf-8"))
        self.assertEqual(len(data), 3)
        first = data.faults[0]
        self.assertEqual((first.kind, first.name, first.rate, first.dip,
                          first.dip_dir, first.catalog),
                         ("reverse", "Mount Diablo Thrust", 1.55, 38.0, "E",
                          "UCERF3"))
        self.assertEqual(first.lats, (37.8, 37.9))
        self.assertEqual(first.lons, (-121.9, -121.8))
        # Части MultiLineString - отдельные разломы, имя из fs_name,
        # скорость - сдвиговая, если общей нет.
        self.assertEqual([f.name for f in data.faults[1:]],
                         ["North Anatolian"] * 2)
        self.assertEqual(data.faults[1].rate, 20.0)
        self.assertEqual(data.faults[2].kind, "strike")

    def test_nearest(self):
        data = faults.parse(json.dumps(SAMPLE))
        found = faults.nearest(data, 40.01, 30.5, 2000.0)
        self.assertEqual(found.name, "North Anatolian")
        self.assertIsNone(faults.nearest(data, 41.0, 30.5, 2000.0))
        self.assertEqual(faults.nearest(data, 37.85, -121.85, 500.0).name,
                         "Mount Diablo Thrust")


if __name__ == "__main__":
    unittest.main()
