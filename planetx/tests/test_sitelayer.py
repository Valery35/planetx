# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Общий слой вида окон анализа: один хозяин, снятие прежнего."""
import importlib.util
import os
import unittest

PATH = os.path.join(os.path.dirname(__file__), "..", "ui", "sitelayer.py")
SPEC = importlib.util.spec_from_file_location("sitelayer", PATH)
sitelayer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(sitelayer)


class Signal:
    def connect(self, slot):
        self.slot = slot


class Tiles:
    def __init__(self):
        self.loaded = Signal()
        self.aborted = False

    def abort(self):
        self.aborted = True

    def deleteLater(self):
        pass


class Layer:
    max_level = 0
    fade = 0.0

    def __init__(self):
        self.empty = set()


class View:
    def __init__(self):
        self.gibs = {sitelayer.LAYER: Layer()}
        self.on = None

    def set_gibs(self, name, on, tiles=None, keep=False):
        self.on = on

    def add_gibs(self, *args):
        pass

    def update(self):
        pass


class Window:
    def __init__(self):
        self.view = View()
        self.site_layer = sitelayer.SiteLayer()


class Tool(sitelayer.SiteTool):
    def __init__(self, window):
        self.window = window
        self.result = None

    def forget(self):
        self.result = None


class TestSiteLayer(unittest.TestCase):
    def test_new_owner_drops_old_without_switching_layer_off(self):
        window = Window()
        a, b = Tool(window), Tool(window)
        first = Tiles()
        a.result = "a"
        a.put_tiles(first, 12, 0.6)
        self.assertIs(window.site_layer.owner, a)
        self.assertAlmostEqual(window.view.gibs[sitelayer.LAYER].fade, 0.4)
        b.result = "b"
        b.put_tiles(Tiles(), 10)
        self.assertIs(window.site_layer.owner, b)
        self.assertTrue(first.aborted)
        self.assertIsNone(a.tiles)
        self.assertIsNone(a.result)
        self.assertTrue(window.view.on)
        self.assertEqual(window.view.gibs[sitelayer.LAYER].max_level, 10)

    def test_clear_of_dropped_tool_keeps_other_result(self):
        window = Window()
        a, b = Tool(window), Tool(window)
        a.put_tiles(Tiles(), 12)
        b.put_tiles(Tiles(), 12)
        a.clear()
        self.assertTrue(window.view.on)
        self.assertIs(window.site_layer.owner, b)
        b.clear()
        self.assertFalse(window.view.on)
        self.assertIsNone(window.site_layer.owner)

    def test_same_owner_redraw_keeps_itself(self):
        window = Window()
        a = Tool(window)
        a.result = "a"
        first = Tiles()
        a.put_tiles(first, 12)
        a.put_tiles(Tiles(), 12, keep=True)
        self.assertEqual(a.result, "a")
        self.assertTrue(first.aborted)
        self.assertIsNotNone(a.tiles)

    def test_level_by_step(self):
        result = {"box": (56.0, 58.0, 56.1, 58.1), "step": 10.0}
        level = sitelayer.result_level(result)
        self.assertGreaterEqual(level, 13)
        self.assertLessEqual(level, 14)


if __name__ == "__main__":
    unittest.main()
