# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетевые ссылки KML: адреса и сроки."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import kml  # noqa: E402
import netlink as nl  # noqa: E402

BASE = "https://raw.githubusercontent.com/Valery35/planetx/main/x/link.kml"


class TestAddress(unittest.TestCase):

    def test_web_and_local(self):
        self.assertTrue(nl.is_web(BASE))
        self.assertFalse(nl.is_web(r"C:\data\a.kml"))
        self.assertEqual(nl.local_path("file:///C:/data/a%20b.kml"),
                         os.path.normpath("C:/data/a b.kml"))
        self.assertEqual(nl.local_path(r"C:\data\a.kml"),
                         os.path.normpath(r"C:\data\a.kml"))
        self.assertIsNone(nl.local_path(BASE))

    def test_relative_to_document(self):
        self.assertEqual(nl.resolve("demos.kml", BASE),
                         "https://raw.githubusercontent.com/Valery35/"
                         "planetx/main/x/demos.kml")
        self.assertEqual(nl.resolve("https://a.org/b.kml", BASE),
                         "https://a.org/b.kml")
        self.assertEqual(nl.resolve("sub/b.kml", r"C:\data\link.kml"),
                         os.path.normpath(r"C:\data\sub\b.kml"))

    def test_tree_links_resolved(self):
        tree = kml.KFolder("t", children=[
            kml.KFolder("a", link="a.kml"),
            kml.KFolder("f", children=[kml.KFolder("b", link="../b.kmz")])])
        nl.resolve_tree(tree, BASE)
        self.assertTrue(tree.children[0].link.endswith("/main/x/a.kml"))
        self.assertTrue(tree.children[1].children[0].link.endswith(
            "/main/b.kmz"))


class TestDue(unittest.TestCase):

    def test_once_and_interval(self):
        self.assertTrue(nl.due(None, 0.0, 100.0))
        self.assertFalse(nl.due(50.0, 0.0, 1e9))
        # refreshInterval 4 поднимается до 10 с.
        self.assertFalse(nl.due(100.0, 4.0, 105.0))
        self.assertTrue(nl.due(100.0, 4.0, 110.0))
        self.assertTrue(nl.due(100.0, 60.0, 160.0))


if __name__ == "__main__":
    unittest.main()
