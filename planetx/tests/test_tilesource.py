# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разбор адреса нового источника тайлов."""
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import tilesource as ts  # noqa: E402


class TestTemplate(unittest.TestCase):

    def test_template_as_is(self):
        url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
        self.assertEqual(ts.template(url), url)

    def test_leaflet_subdomain_and_retina(self):
        self.assertEqual(
            ts.template("https://{s}.tile.opentopomap.org/{z}/{x}/{y}{r}.png"),
            "https://a.tile.opentopomap.org/{z}/{x}/{y}.png")

    def test_encoded_and_openlayers_fields(self):
        self.assertEqual(
            ts.template("https://h.org/%7Bz%7D/%7Bx%7D/%7By%7D.jpg"),
            "https://h.org/{z}/{x}/{y}.jpg")
        self.assertEqual(ts.template("https://h.org/${z}/${x}/${-y}.png"),
                         "https://h.org/{z}/{x}/{-y}.png")

    def test_concrete_tile(self):
        self.assertEqual(
            ts.template("https://tile.example.org/maps/12/2589/1290.png"),
            "https://tile.example.org/maps/{z}/{x}/{y}.png")

    def test_arcgis_tile_is_z_y_x(self):
        url = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
               "World_Topo_Map/MapServer/tile/5/10/17")
        self.assertTrue(ts.template(url).endswith("/tile/{z}/{y}/{x}"))

    def test_query_parameters(self):
        self.assertEqual(
            ts.template("https://h.org/tiles?layer=a&x=3&y=5&z=4"),
            "https://h.org/tiles?layer=a&x={x}&y={y}&z={z}")

    def test_numbers_out_of_range_are_not_a_tile(self):
        # Уровень 2 - не больше 4 столбцов, 2589 тайлом быть не может.
        with self.assertRaises(ts.ParseError):
            ts.template("https://h.org/v2/2589/1290")

    def test_errors(self):
        for text in ("", "h.org/{z}/{x}/{y}", "https://h.org/map.png",
                     "https://h.org/{z}/{x}/{w}"):
            with self.assertRaises(ts.ParseError, msg=text):
                ts.template(text)


class TestHelpers(unittest.TestCase):

    def test_flip_rows(self):
        url = "https://h.org/{z}/{x}/{y}.png"
        self.assertEqual(ts.flip_rows(url), "https://h.org/{z}/{x}/{-y}.png")
        self.assertEqual(ts.flip_rows(ts.flip_rows(url)), url)

    def test_names(self):
        self.assertEqual(ts.name_for(
            "https://server.arcgisonline.com/x/{z}/{y}/{x}"), "arcgisonline")
        self.assertEqual(ts.name_for(
            "https://a.tile.opentopomap.org/{z}/{x}/{y}.png"), "opentopomap")

    def test_preview_keys(self):
        self.assertEqual(ts.preview_keys(1), [(1, 0, 0), (1, 1, 0),
                                              (1, 0, 1), (1, 1, 1)])


if __name__ == "__main__":
    unittest.main()
