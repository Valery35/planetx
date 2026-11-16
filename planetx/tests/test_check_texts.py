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
        # Таблица полос свода линейки C:\Dev\workplace\TEXTS.md.
        self.assertEqual(check_texts.band_of("CHANGELOG.md"), "letter")
        self.assertEqual(check_texts.band_of("site/posts_1.44.1_social.md"),
                         "letter")
        self.assertEqual(check_texts.band_of("doc/MANUAL.md"), "note")
        # README - ритм не меряется, только длина (свод линейки).
        self.assertEqual(check_texts.band_of("README.ru.md"),
                         check_texts.LENGTH_ONLY)

    def test_length_only_keeps_length(self):
        text = " ".join("Глобус открыт сразу." for _ in range(12))
        long_one = " ".join(["слово"] * 40) + ". "
        found = findings(long_one + text, band=check_texts.LENGTH_ONLY)
        self.assertIn("длина", found)
        self.assertNotIn("ритм", found)
        self.assertEqual(check_texts.band_of("doc/PLAN_PHASE1.md"),
                         "register")
        # Рабочий свод - записи с перечнями, ритм и длина не меряются.
        self.assertIsNone(check_texts.band_of("AGENTS.md"))
        self.assertEqual(check_texts.band_of("doc/AGENTS_NOTES.md"), "note")

    def test_markup_is_not_prose(self):
        # Заголовки, таблицы и код - не предложения. Прежний счёт брал их
        # в длину, отсюда ложные замечания на сводах.
        text = ("# Заголовок свода из нескольких слов подряд\n\n"
                "| Вид текста | Средняя | Коротких | Длинных |\n"
                "|---|---|---|---|\n"
                "| " + " ".join(["слово"] * 40) + " | 8-11 | 2/3 | 5 % |\n\n"
                "```\n" + " ".join(["код"] * 40) + "\n```\n")
        self.assertEqual(findings(text, band="note"), [])

    def test_band_key(self):
        # Средняя 9.8, коротких 40 %, длинных 20 % - полоса заметки
        # выпуска, но не руководства.
        text = ("Глобус открывается в отдельном окне. "
                "Слой проекта ложится сразу. "
                "Подписи основы идут поверх рельефа и не закрывают метки "
                "на снимке. "
                "Шкала времени открывается при первой метке со временем "
                "в папке. "
                "Тени от рельефа и зданий считаются по положению солнца "
                "на момент шкалы и ложатся на глобус поверх снимка дня. ") * 3
        path = os.path.join(ROOT, "tools", "_band_probe.md")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        try:
            for band, red in (("note", True), ("letter", False)):
                rel = os.path.relpath(path, ROOT)
                code = check_texts.main([rel, "--strict", "--band", band])
                self.assertEqual(code == 1, red, band)
        finally:
            os.remove(path)


class TestLines(unittest.TestCase):

    def test_finding_names_its_line(self):
        # Находка с местом в файле - иначе её ищут глазами по тексту.
        text = ("# Заголовок\n\nПервый абзац без нарушений.\n\n"
                "Второй абзац; с точкой с запятой.\n\n"
                + " ".join(["слово"] * 40) + ".\n")
        problems = []
        check_texts.check_prose("x.md", text, problems, band="note",
                                lines=True)
        where = {reason: place for place, _, reason in problems}
        self.assertEqual(where["точка с запятой"], "x.md:5")
        self.assertEqual(where["длина"], "x.md:7")


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
