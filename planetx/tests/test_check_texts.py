# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сторожа проверки текстов из tools/check_texts.py.

Проверка текстов сама по себе код, и она тоже может перестать ловить
нарушения. Тесты подают ей образцы с нарушениями.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_texts  # noqa: E402


def findings(text, russian=True):
    problems = []
    check_texts.check_prose("x", text, problems, russian=russian)
    return [reason for _, _, reason in problems]


class TestSentenceLength(unittest.TestCase):

    def test_long_sentence_is_counted(self):
        text = " ".join(["слово"] * 40) + "."
        _, total, over28, over34 = check_texts.sentence_stats(text)
        self.assertEqual((total, over28, over34), (1, 1, 1))

    def test_long_sentence_inside_list_item_is_counted(self):
        text = "Список:\n\n- " + " ".join(["слово"] * 40) + "\n"
        _, _, _, over34 = check_texts.sentence_stats(text)
        self.assertEqual(over34, 1)

    def test_list_items_are_not_glued(self):
        items = "\n".join("- пункт списка из шести слов" for _ in range(8))
        text = "Перечень:\n\n" + items + "\n\nДальше идёт проза."
        _, total, over28, _ = check_texts.sentence_stats(text)
        self.assertEqual(over28, 0)
        self.assertEqual(total, 10)

    def test_wrapped_sentence_stays_one(self):
        text = "Первая половина предложения\nи вторая его половина."
        _, total, _, _ = check_texts.sentence_stats(text)
        self.assertEqual(total, 1)


class TestProse(unittest.TestCase):

    def test_long_dash(self):
        self.assertIn("длинное тире", findings("Слово — слово."))

    def test_semicolon(self):
        self.assertIn("точка с запятой", findings("Одно; другое."))

    def test_colon_inside_line(self):
        self.assertIn("двоеточие внутри строки",
                      findings("Состояние: заготовка."))

    def test_colon_before_list_is_fine(self):
        self.assertEqual(findings("Критерий:"), [])

    def test_stop_word(self):
        self.assertIn("стоп-слово", findings("Это делается руками."))

    def test_whole_stop_word(self):
        self.assertIn("стоп-слово", findings("Глобус прямо в QGIS."))
        for text in ("Прямой запрет.", "Прямого разрешения нет.",
                     "Модуль берётся напрямую."):
            self.assertEqual(findings(text), [], text)

    def test_stop_words_skipped_for_english(self):
        self.assertEqual(findings("руками", russian=False), [])

    def test_number_instead_of_count(self):
        self.assertIn("«число» вместо «количества»",
                      findings("Большое число тайлов."))


if __name__ == "__main__":
    unittest.main()
