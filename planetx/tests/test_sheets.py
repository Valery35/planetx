# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/sheets.py на опубликованных номенклатурах листов."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import sheets  # noqa: E402

PERM = (58.01, 56.23)


class TestRussian(unittest.TestCase):

    def test_perm(self):
        self.assertEqual(sheets.russian(*PERM, 1000000), "O-40")
        self.assertEqual(sheets.russian(*PERM, 500000), "O-40-А")
        self.assertEqual(sheets.russian(*PERM, 200000), "O-40-XV")

    def test_ryazan_examples(self):
        # Примеры статьи «Советская система разграфки» - Рязань.
        self.assertEqual(sheets.russian(54.63, 39.74, 500000), "N-37-Б")
        self.assertEqual(sheets.russian(54.63, 39.74, 200000), "N-37-XVI")

    def test_doubled_north_of_60(self):
        # Белушья Губа - R-39-А,Б.
        self.assertEqual(sheets.russian(71.55, 52.3, 1000000), "R-39,40")
        self.assertEqual(sheets.russian(71.55, 52.3, 500000), "R-39-А,Б")
        self.assertEqual(sheets.russian(68.3, 42.5, 200000),
                         "R-38-XXXI,XXXII")

    def test_quadrupled_and_tripled_north_of_76(self):
        self.assertEqual(sheets.russian(80.3, 55.0, 1000000),
                         "U-37,38,39,40")
        self.assertEqual(sheets.russian(80.3, 55.0, 200000),
                         "U-40-XXXI,XXXII,XXXIII")

    def test_pole_and_south(self):
        self.assertEqual(sheets.russian(89.0, 10.0, 1000000), "Z")
        self.assertIsNone(sheets.russian(89.0, 10.0, 200000))
        self.assertEqual(sheets.russian(-1.0, 8.0, 1000000),
                         "A-32 (Ю. П.)")

    def test_roman(self):
        self.assertEqual([sheets.roman(n) for n in (4, 9, 14, 36)],
                         ["IV", "IX", "XIV", "XXXVI"])


class TestImwAndJog(unittest.TestCase):

    def test_imw(self):
        self.assertEqual(sheets.imw(*PERM), "NO 40")
        self.assertEqual(sheets.imw(-33.9, 18.4), "SI 34")
        self.assertEqual(sheets.imw(89.5, 0.0), "NZ")
        self.assertEqual(sheets.imw(10.0, 180.0), "NC 1")

    def test_jog_published_sheets(self):
        self.assertEqual(sheets.jog(*PERM), "NO 40-6")
        self.assertEqual(sheets.jog(30.18, 67.0), "NH 42-5")  # Кветта
        self.assertEqual(sheets.jog(51.18, -115.57), "NM 11-3")  # Банф
        self.assertEqual(sheets.jog(67.28, 14.40), "NQ 33,34-1")  # Будё
        self.assertEqual(sheets.jog(67.85, 20.23), "NQ 33,34-3")  # Кируна
        self.assertEqual(sheets.jog(67.68, 21.6), "NQ 33,34-4")  # Виттанги
        self.assertEqual(sheets.jog(68.44, 17.43), "NR 33,34-11")  # Нарвик

    def test_jog_none_far_north(self):
        self.assertIsNone(sheets.jog(78.2, 15.6))

    def test_mgrs_square(self):
        self.assertRegex(sheets.mgrs_square(*PERM), r"^40V [A-Z]{2}$")
        self.assertIsNone(sheets.mgrs_square(86.0, 0.0))

    def test_rows(self):
        rows = sheets.sheets(*PERM)
        self.assertEqual([r[0] for r in rows],
                         ["imw", "russian", "russian", "russian", "jog",
                          "mgrs"])


if __name__ == "__main__":
    unittest.main()
