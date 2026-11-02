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


class Legend:
    visible = False
    title = footer = ""
    rows = ()

    def set_rows(self, title, rows, footer=""):
        self.title, self.rows, self.footer = title, rows, footer

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False


class Owner:
    def _drop_viewshed(self):
        pass


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

    def test_legend_follows_owner(self):
        window = Window()
        window.site_legend = Legend()
        a, b = Tool(window), Tool(window)
        a.legend_title = "A"
        a.result = {"classes": [[0, 1, 1], [-1, 1, 2]],
                    "colors": [(1, 2, 3), (4, 5, 6), (7, 8, 9)],
                    "names": ["x", "y", "z"]}
        a.put_tiles(Tiles(), 12)
        self.assertTrue(window.site_legend.visible)
        self.assertEqual(window.site_legend.title, "A")
        self.assertEqual([text for _, text in window.site_legend.rows],
                         ["y 60 %", "x 20 %", "z 20 %"])
        b.put_tiles(Tiles(), 12)  # у b классов нет
        self.assertFalse(window.site_legend.visible)
        a.result = {"classes": [[0]], "colors": [(1, 2, 3)],
                    "names": ["x"]}
        a.put_tiles(Tiles(), 12)
        b.clear()  # снятый раньше b не прячет шкалу a
        self.assertTrue(window.site_legend.visible)
        window.site_layer.claim(sitelayer.ViewshedOwner(Owner()))
        self.assertFalse(window.site_legend.visible)

    def test_legend_rows_cut_with_footer(self):
        window = Window()
        window.site_legend = Legend()
        a = Tool(window)
        n = sitelayer.LEGEND_ROWS + 3
        a.result = {"classes": [list(range(n))], "colors": [(0, 0, 0)] * n,
                    "names": [str(k) for k in range(n)]}
        a.put_tiles(Tiles(), 12)
        self.assertEqual(len(window.site_legend.rows), sitelayer.LEGEND_ROWS)
        self.assertIn("3", window.site_legend.footer)
        a.clear()
        self.assertFalse(window.site_legend.visible)

    def test_level_by_step(self):
        result = {"box": (56.0, 58.0, 56.1, 58.1), "step": 10.0}
        level = sitelayer.result_level(result)
        self.assertGreaterEqual(level, 13)
        self.assertLessEqual(level, 14)


if __name__ == "__main__":
    unittest.main()
