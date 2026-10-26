# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты шторки слоёв проекта."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import sides  # noqa: E402


class TestSides(unittest.TestCase):

    def test_round_trip_drops_unknown_side(self):
        text = sides.dump({"a": "left", "b": "right", "c": "middle"})
        self.assertEqual(sides.parse(text), {"a": "left", "b": "right"})
        self.assertEqual(sides.parse("not json"), {})
        self.assertEqual(sides.parse("[1]"), {})

    def test_each_side_hides_the_other(self):
        marks = {"a": "left", "b": "right"}
        ids = ["a", "b", "c"]
        self.assertEqual(sides.hidden(marks, ids, sides.LEFT), {"b"})
        self.assertEqual(sides.hidden(marks, ids, sides.RIGHT), {"a"})
        # Слой не на глобусе ничего не скрывает.
        self.assertEqual(sides.hidden(marks, ["a", "c"], sides.LEFT),
                         frozenset())

    def test_active_only_with_shown_layer(self):
        self.assertTrue(sides.active({"a": "left"}, ["a"]))
        self.assertFalse(sides.active({"a": "left"}, ["b"]))

    def test_label(self):
        self.assertEqual(sides.label([], "base"), "base")
        self.assertEqual(sides.label(["x", "y", "z"], "base"), "x, y, …")


if __name__ == "__main__":
    unittest.main()
