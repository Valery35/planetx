# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поиск по руководству, core/manualindex.py."""
import json
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "core"))

import manualindex  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(HERE))

TEXT = """# Руководство

## Установка

Меню «Модули», поиск по слову PlanetX.

![окно](figures/ru/window.png)

## 3D-модели

### Анимация

Модель ветряка вращает лопасти.

```
## не заголовок
```

## 3D-модели

Второй раздел с тем же именем.
"""


class TestSections(unittest.TestCase):

    def test_headings_anchors_and_images(self):
        items = manualindex.sections(TEXT)
        self.assertEqual([t for t, _, _ in items],
                         ["Установка", "3D-модели", "Анимация", "3D-модели"])
        # Якоря GitHub: без знаков, повтор с номером.
        self.assertEqual([a for _, a, _ in items],
                         ["установка", "3d-модели", "анимация",
                          "3d-модели-1"])
        self.assertNotIn("figures", items[0][2])
        # Строка в ограде кода - текст, а не заголовок.
        self.assertIn("## не заголовок", items[2][2])

    def test_slug_drops_punctuation(self):
        self.assertEqual(manualindex.slug("Раздел «Слои»", {}),
                         "раздел-слои")


class TestSearch(unittest.TestCase):

    def setUp(self):
        self.index = manualindex.Index(manualindex.sections(TEXT))

    def test_stems_find_word_forms(self):
        found = self.index.search("Как вращать модели ветряков?")
        self.assertEqual(self.index.items[found[0]][0], "Анимация")

    def test_title_outweighs_text(self):
        found = self.index.search("установка")
        self.assertEqual(self.index.items[found[0]][0], "Установка")

    def test_short_and_stop_words_find_nothing(self):
        self.assertEqual(self.index.search("как"), [])
        self.assertEqual(self.index.search("где это"), [])

    def test_endings_and_synonyms(self):
        """«картой» находит «карты», «экспорт» - «выгрузку», «снимок» -
        «снимки». На прежней обрезке основы «карто» и без групп
        синонимов раздела нет."""
        index = manualindex.Index([
            ["Синхронизация", "s", "Окно карты QGIS следует за глобусом."],
            ["Горизонтали", "g", "Выгрузка горизонталей в GeoPackage."],
            ["Космоснимки", "k", "Снимки Sentinel-2 участком."],
        ])
        self.assertEqual(index.search("связь с картой")[:1], [0])
        self.assertEqual(index.search("экспорт горизонталей")[:1], [1])
        self.assertEqual(index.search("снимок sentinel")[:1], [2])
        self.assertEqual(manualindex.stem("ветряков"), "ветряк")
        self.assertEqual(manualindex.stem("models"), "model")

    def test_words_together_in_paragraph_outrank_scattered(self):
        """Раздел, где все слова вопроса в одном абзаце, выше длинного
        раздела, где они разбросаны по разным абзацам, даже если там
        слова встречаются чаще."""
        index = manualindex.Index([
            ["Слои", "a", "Горизонтали рельефа.\n\nГоризонтали вблизи.\n\n"
             "Горизонтали тайлами.\n\nСлой проекта QGIS.\n\n"
             "Проект QGIS и слой."],
            ["Выгрузка", "b", "Горизонтали вида в проект QGIS."],
        ])
        self.assertEqual(index.search("горизонтали в проект")[:1], [1])

    def test_table_rows_are_separate_paragraphs(self):
        self.assertEqual(manualindex.parts("| a | b |\n| c | d |\n\nтекст"),
                         [("| a | b |", True), ("| c | d |", True),
                          ("текст", False)])

    def test_snippet_is_matching_paragraph(self):
        n = self.index.find("анимация")
        self.assertEqual(self.index.snippet(n, "ветряк"),
                         "Модель ветряка вращает лопасти.")


class TestData(unittest.TestCase):

    def test_data_matches_manual(self):
        """Указатель модуля собран по нынешнему руководству. Красный -
        руководство правили, а tools/build_manual_index.py не запускали."""
        doc = os.path.join(ROOT, "doc")
        if not os.path.isdir(doc):
            self.skipTest("нет папки doc")
        for manual, data in (("MANUAL.md", "manual_ru.json"),
                             ("MANUAL.en.md", "manual_en.json")):
            with open(os.path.join(doc, manual), encoding="utf-8") as h:
                want = manualindex.sections(h.read())
            with open(os.path.join(ROOT, "planetx", "data", data),
                      encoding="utf-8") as h:
                have = json.load(h)
            self.assertEqual(have, want, data)


if __name__ == "__main__":
    unittest.main()
