# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подводные кабели: разбор файла и кабель у точки щелчка."""
import json
import os
import sys
import unittest

ROOT = os.path.join(os.path.dirname(__file__), "..")
sys.path.insert(0, os.path.join(ROOT, "core"))

import cables  # noqa: E402

SAMPLE = {"date": "2026-10-11", "cables": [
    {"kind": "telecom", "name": "A", "osm": "way/1",
     "points": [[50.0, -10.0], [40.0, -60.0]]},
    {"kind": "power", "name": "B", "voltage": "450000", "osm": "way/2",
     "points": [[55.0, 8.0], [56.0, 8.0]]},
    {"kind": "pipe", "points": [[0.0, 0.0], [1.0, 1.0]]},
    {"kind": "power", "points": [[0.0, 0.0]]}]}


class TestCables(unittest.TestCase):

    def test_parse_keeps_known_kinds(self):
        data = cables.Cables.from_text(json.dumps(SAMPLE))
        self.assertEqual([c.name for c in data.cables], ["A", "B"])
        self.assertEqual(data.date, "2026-10-11")
        self.assertEqual(data.boxes[1], (55.0, 8.0, 56.0, 8.0))

    def test_nearest_on_long_ocean_segment(self):
        data = cables.Cables.from_text(json.dumps(SAMPLE))
        # Середина отрезка в тысячи километров - вершин рядом нет.
        found = cables.nearest(data, 45.6, -33.0, 60000.0)
        self.assertIsNotNone(found)
        self.assertEqual(found.name, "A")
        self.assertIsNone(cables.nearest(data, 30.0, -33.0, 60000.0))
        self.assertEqual(cables.nearest(data, 55.5, 8.01, 2000.0).name, "B")

    def test_module_file(self):
        path = os.path.join(ROOT, "data", "cables.json")
        with open(path, encoding="utf-8") as fh:
            data = cables.Cables.from_text(fh.read())
        kinds = {kind: sum(1 for c in data.cables if c.kind == kind)
                 for kind in cables.KINDS}
        self.assertGreater(kinds["telecom"], 500)
        self.assertGreater(kinds["power"], 500)
        names = {c.name for c in data.cables}
        self.assertIn("NorNed", names)


if __name__ == "__main__":
    unittest.main()
