# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""ЛЭП и трубопроводы OSM: напряжение, классы, разбор ответа."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import infra  # noqa: E402


class TestInfra(unittest.TestCase):

    def test_kilovolts(self):
        self.assertEqual(infra.kilovolts("500000"), 500.0)
        self.assertEqual(infra.kilovolts("220000;110000"), 220.0)
        self.assertEqual(infra.kilovolts("110 kV"), 110.0)
        self.assertIsNone(infra.kilovolts(""))
        self.assertIsNone(infra.kilovolts("высокое"))

    def test_classes(self):
        self.assertEqual(infra.voltage_class(500.0), "v500")
        self.assertEqual(infra.voltage_class(330.0), "v220")
        self.assertEqual(infra.voltage_class(110.0), "v110")
        self.assertEqual(infra.voltage_class(35.0), "v35")
        self.assertEqual(infra.voltage_class(None), "v35")
        self.assertEqual(infra.substance_class("gas"), "gas")
        self.assertEqual(infra.substance_class("crude_oil"), "oil")
        self.assertEqual(infra.substance_class(""), "other")

    def test_query_and_parse(self):
        text = infra.query((59.0, 56.0, 60.0, 57.0))
        self.assertIn('way["power"="line"](59.00000,56.00000,60.00000,'
                      '57.00000);', text)
        self.assertIn("out geom tags;", text)
        answer = {"elements": [
            {"type": "way", "id": 1,
             "geometry": [{"lat": 59.0, "lon": 56.0},
                          {"lat": 59.1, "lon": 56.1}],
             "tags": {"power": "line", "voltage": "500000",
                      "name": "ВЛ 500 кВ"}},
            {"type": "way", "id": 2,
             "geometry": [{"lat": 59.0, "lon": 56.0},
                          {"lat": 59.2, "lon": 56.2}],
             "tags": {"man_made": "pipeline", "substance": "gas",
                      "operator": "Газпром"}},
            {"type": "way", "id": 3, "geometry": [{"lat": 59.0, "lon": 56.0}],
             "tags": {"power": "line"}},
            {"type": "way", "id": 4, "center": {"lat": 59.3, "lon": 56.3},
             "tags": {"power": "substation", "voltage": "110000"}},
            {"type": "way", "id": 1,
             "geometry": [{"lat": 59.0, "lon": 56.0},
                          {"lat": 59.1, "lon": 56.1}],
             "tags": {"power": "line"}},
            {"type": "way", "id": 5,
             "geometry": [{"lat": 59.0, "lon": 56.0},
                          {"lat": 59.0, "lon": 56.03}],
             "tags": {"power": "cable", "voltage": "220000",
                      "location": "underwater"}},
            {"type": "way", "id": 6,
             "geometry": [{"lat": 59.0, "lon": 56.0},
                          {"lat": 59.4, "lon": 56.0}],
             "tags": {"communication": "line"}}]}
        items = infra.unique(infra.parse(answer))
        self.assertEqual([i["kind"] for i in items],
                         ["line", "pipe", "substation", "cable",
                          "telecom"])
        self.assertEqual(items[3]["location"], "underwater")
        self.assertEqual(items[3]["voltage"], 220.0)
        self.assertIn('way["power"="cable"]', text)
        self.assertEqual(items[0]["style"], "v500")
        self.assertEqual(items[1]["style"], "gas")
        self.assertEqual(items[1]["operator"], "Газпром")
        self.assertEqual(items[2]["style"], "v110")

    def test_submarine_cables_left_to_cable_row(self):
        # Подводные линии связи и длинные силовые кабели под водой рисует
        # строка «Подводные кабели», у ЛЭП OSM их второй копии нет.
        line = [{"lat": 59.0, "lon": 20.0}, {"lat": 59.0, "lon": 20.3}]
        river = [{"lat": 59.0, "lon": 20.0}, {"lat": 59.0, "lon": 20.03}]
        answer = {"elements": [
            {"type": "way", "id": 1, "geometry": line,
             "tags": {"communication": "line", "location": "underwater"}},
            {"type": "way", "id": 2, "geometry": line,
             "tags": {"communication": "line", "submarine": "yes"}},
            {"type": "way", "id": 3, "geometry": line,
             "tags": {"power": "cable", "location": "submarine"}},
            {"type": "way", "id": 4, "geometry": river,
             "tags": {"power": "cable", "location": "underwater"}},
            {"type": "way", "id": 5, "geometry": line,
             "tags": {"power": "cable", "location": "underground"}}]}
        self.assertEqual([i["osm"] for i in infra.parse(answer)],
                         ["way/4", "way/5"])


if __name__ == "__main__":
    unittest.main()
