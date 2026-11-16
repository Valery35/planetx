# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сторожа проверки текстов из tools/check_texts.py.

Проверка текстов сама по себе код, и она тоже может перестать ловить
нарушения. Тесты подают ей образцы с нарушениями. Прозу меряет
tools/measure.py, копия измерителя линейки, тесты проверяют, что
check_texts.py отдаёт ему текст и берёт полосу по виду текста.
"""
import hashlib
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import check_texts  # noqa: E402

SOURCE = os.path.join(os.path.dirname(ROOT), "agents-md-document-project",
                      "measure.py")


def findings(text, russian=True, band=None):
    problems = []
    check_texts.check_prose("x", text, problems, russian=russian, band=band)
    return [reason for _, _, reason in problems]


class TestRhythm(unittest.TestCase):

    def test_long_sentence_is_found(self):
        text = " ".join(["слово"] * 40) + "."
        self.assertIn("длина", findings(text, band="note"))

    def test_fragments_are_found(self):
        # Текст, рассыпанный на обрубки, - то, чего прежний счёт средней
        # длины и длинных предложений не видел.
        text = " ".join("Глобус открыт сразу." for _ in range(12))
        self.assertIn("ритм", findings(text, band="note"))
        mixed = ("Глобус открывается в отдельном окне рядом с картой QGIS. "
                 "Слой проекта ложится на глобус сразу и обновляется после "
                 "каждой правки данных. Подписи идут поверх рельефа, не "
                 "закрывают метки и пропадают на удалении, когда их "
                 "становится слишком много для одного экрана. ")
        self.assertNotIn("ритм", findings(mixed * 3, band="note"))

    def test_band_by_kind(self):
        self.assertEqual(check_texts.band_of("CHANGELOG.md"), "register")
        self.assertEqual(check_texts.band_of("site/posts_1.44.1_social.md"),
                         "letter")
        self.assertEqual(check_texts.band_of("doc/MANUAL.md"), "letter")
        self.assertEqual(check_texts.band_of("AGENTS.md"), "note")
        self.assertEqual(check_texts.band_of("doc/SOURCES.md"), "note")


class TestProse(unittest.TestCase):

    def test_long_dash(self):
        self.assertIn("длинное тире", findings("Слово — слово."))

    def test_semicolon(self):
        self.assertIn("точка с запятой", findings("Одно; другое."))

    def test_colon_inside_line(self):
        self.assertIn("двоеточие внутри предложения",
                      findings("Состояние: заготовка."))

    def test_colon_before_list_is_fine(self):
        self.assertEqual(findings("Критерий:"), [])

    def test_stop_word(self):
        self.assertIn("стоп-слово", findings("Это делается руками."))

    def test_grab_is_stop_word(self):
        # Решение автора от 11 октября 2026 года.
        self.assertIn("стоп-слово",
                      findings("Схватите Землю левой кнопкой."))

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


class TestMeasureCopy(unittest.TestCase):

    @unittest.skipUnless(os.path.exists(SOURCE), "нет рабочей копии "
                         "agents-md-document-project рядом")
    def test_measure_is_unchanged_copy(self):
        def digest(path):
            with open(path, "rb") as fh:
                return hashlib.sha256(fh.read()).hexdigest()
        self.assertEqual(digest(os.path.join(ROOT, "tools", "measure.py")),
                         digest(SOURCE))


if __name__ == "__main__":
    unittest.main()
