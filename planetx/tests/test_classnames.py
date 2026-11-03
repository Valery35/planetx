# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты названий классов от помощника (core/classnames.py)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import classnames as cn  # noqa: E402

ROWS = [{"means": [0.08, 0.2, 0.02], "share": 0.43, "regions": 12,
         "area_ha": 230.5, "rule": "Хвойный лес"},
        {"means": [0.3, 0.22, 0.08], "share": 0.21, "regions": 3,
         "area_ha": 44.0, "rule": None}]


class TestQuestion(unittest.TestCase):
    def test_roles_values_and_rules(self):
        text = cn.question(ROWS, ["swir1", "nir", "blue"], "отражение 0-1",
                           (58.05, 56.2), 7)
        self.assertIn("SWIR 1,6 мкм, ближний ИК, синий", text)
        self.assertIn("Класс 1 - 0.080, 0.200, 0.020, доля участка 43 %",
                      text)
        self.assertIn("по правилам отражения - Хвойный лес", text)
        self.assertIn("Месяц съёмки - 7.", text)
        self.assertIn("Класс 2 - 0.300, 0.220, 0.080, доля участка 21 %, "
                      "областей 3, средняя область 44.0 га.", text)

    def test_unknown_bands_numbered(self):
        text = cn.question(ROWS, None, "яркость 0-255")
        self.assertIn("канал 1, канал 2, канал 3", text)
        self.assertNotIn("Место", text)

    def test_system_language(self):
        self.assertIn("русском", cn.system_text("ru"))
        self.assertIn("английском", cn.system_text("en"))
        self.assertIn('{"names"', cn.system_text("ru"))


class TestParse(unittest.TestCase):
    def test_object_in_text(self):
        text = 'Вот ответ:\n```json\n{"names": ["Хвоя", "Пашня"]}\n```'
        self.assertEqual(cn.parse_names(text, 2), ["Хвоя", "Пашня"])

    def test_bare_list_and_extra_names(self):
        self.assertEqual(cn.parse_names('["a", " b ", "c"]', 2), ["a", "b"])

    def test_short_or_broken_answer(self):
        self.assertIsNone(cn.parse_names('{"names": ["a"]}', 2))
        self.assertIsNone(cn.parse_names("не знаю", 2))
        self.assertIsNone(cn.parse_names("", 2))

    def test_long_name_cut(self):
        out = cn.parse_names('["' + "х" * 100 + '"]', 1)
        self.assertEqual(len(out[0]), cn.NAME_LIMIT)


if __name__ == "__main__":
    unittest.main()
