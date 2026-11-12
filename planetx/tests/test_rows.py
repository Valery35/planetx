# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Реестр строк каталога core/rows.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import rows  # noqa: E402


class Tool:
    pass


def names():
    return "A", "a"


class TestRegistry(unittest.TestCase):

    def make(self):
        return rows.Registry().add(
            rows.Row("a", "life", names, Tool, source="S", colors=[(1, 2, 3)],
                     words=["w"], fades=["emag"], view_map="emag"),
            rows.Row("b", "life", names, Tool, earth=False, default=True),
            rows.Row("c", "sky", names, qgis_layer=True, points="dots"))

    def test_tables(self):
        reg = self.make()
        self.assertEqual(reg.keys(), ("a", "b", "c"))
        self.assertEqual(reg.defaults(), {"a": False, "b": True, "c": False})
        self.assertEqual(reg.earth_keys(), ("a", "c"))
        self.assertEqual(reg.fades(), {"a": ("emag",)})
        self.assertEqual(reg.view_maps("emag"), ("a",))
        self.assertEqual(reg.groups(), (("a", "life"), ("b", "life"),
                                        ("c", "sky")))
        self.assertEqual(reg.colors(), {"a": ((1, 2, 3),)})
        self.assertEqual(reg.words(), {"a": ("w",)})
        self.assertEqual(reg.names()["c"], ("A", "a"))
        self.assertEqual(reg.tools(), [Tool])
        self.assertEqual(reg.qgis_keys(), ("c",))
        self.assertEqual(reg.points(), {"c": "dots"})
        self.assertIs(reg.get("b").tool, Tool)

    def test_place_after_keys_and_chains(self):
        reg = rows.Registry().add(
            rows.Row("y", "g", names, after="x"),
            rows.Row("end", "g", names),
            rows.Row("x", "g", names, after="a"))
        self.assertEqual(reg.place((("a", "g"), ("b", "g"))),
                         (("a", "g"), ("x", "g"), ("y", "g"), ("b", "g"),
                          ("end", "g")))
        bad = rows.Registry().add(rows.Row("z", "g", names, after="none"))
        with self.assertRaises(rows.RowError):
            bad.place(())

    def test_row_outside_catalog_is_not_placed(self):
        # Пожары: карточку даёт выбор тем, в каталоге слоёв строки нет,
        # а ключ, точки и умолчание - у реестра.
        reg = rows.Registry().add(
            rows.Row("fires", "fire", names, Tool, points="fires",
                     catalog=False),
            rows.Row("x", "g", names, after="a"))
        self.assertEqual(reg.place((("a", "g"),)),
                         (("a", "g"), ("x", "g")))
        self.assertEqual(reg.points(), {"fires": "fires"})
        self.assertEqual(reg.defaults(), {"fires": False, "x": False})

    def test_forgotten_rows_and_previews(self):
        # Палеогеография: выключена при открытии окна, превью - тайл.
        reg = rows.Registry().add(
            rows.Row("paleo", "geology", names, Tool, remember=False,
                     preview="https://t/{z}/{x}/{y}.jpg"),
            rows.Row("x", "g", names, flow="currents"))
        self.assertEqual(reg.forgotten(), ("paleo",))
        self.assertEqual(reg.flows(), {"x": "currents"})
        self.assertEqual(reg.previews(),
                         {"paleo": "https://t/{z}/{x}/{y}.jpg"})

    def test_repeated_key_refused(self):
        reg = self.make()
        with self.assertRaises(rows.RowError):
            reg.add(rows.Row("a", "sky", names))

    def test_names_must_be_callable(self):
        with self.assertRaises(rows.RowError):
            rows.Row("x", "sky", ("A", "a"))


if __name__ == "__main__":
    unittest.main()
