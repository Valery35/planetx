# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вид метки: пять чисел, прежние три, запись, метка «Сохранить вид»."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import lookat as la  # noqa: E402


class TestView(unittest.TestCase):

    def test_round_trip(self):
        view = la.make(58.24, 56.57, 50257.0, 370.0, 95.0)
        self.assertEqual(view, (58.24, 56.57, 50257.0, 10.0, la.MAX_TILT))
        self.assertEqual(la.parse(la.text(view)), view)

    def test_old_three_numbers_look_at_the_place(self):
        self.assertEqual(la.parse("2500.0,30.0,45.0", (58.01, 56.23)),
                         (58.01, 56.23, 2500.0, 30.0, 45.0))
        self.assertIsNone(la.parse("2500.0,30.0,45.0"))

    def test_bad_fields(self):
        self.assertIsNone(la.parse(""))
        self.assertIsNone(la.parse("a,b,c,d,e"))
        self.assertIsNone(la.parse("58,56,0,0,0"))
        self.assertEqual(la.text(None), "")

    def test_view_mark(self):
        view = la.make(58.0, 56.0, 1000.0)
        self.assertTrue(la.is_view_mark("point", [(58.0, 56.0)], view))
        self.assertFalse(la.is_view_mark("point", [(58.1, 56.0)], view))
        self.assertFalse(la.is_view_mark("line", [(58.0, 56.0)], view))
        self.assertFalse(la.is_view_mark("point", [(58.0, 56.0)], None))


if __name__ == "__main__":
    unittest.main()
