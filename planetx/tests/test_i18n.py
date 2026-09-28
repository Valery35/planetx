# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Перевод интерфейса: у каждой строки в tr() есть английская пара."""
import ast
import os
import re
import sys
import unittest

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PLUGIN)

import i18n  # noqa: E402


def tr_literals():
    """Строки, переданные в tr() литералом, пары файл и текст."""
    out = []
    for folder, dirs, files in os.walk(PLUGIN):
        dirs[:] = [d for d in dirs if d not in ("tests", "__pycache__")]
        for name in files:
            if not name.endswith(".py"):
                continue
            path = os.path.join(folder, name)
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call)
                        and getattr(node.func, "id", "") == "tr"
                        and node.args
                        and isinstance(node.args[0], ast.Constant)):
                    out.append((name, node.args[0].value))
    return out


def i18n_source():
    with open(os.path.join(PLUGIN, "i18n.py"), encoding="utf-8") as fh:
        return fh.read()


def repeated_keys(source):
    """Ключи, записанные в литерале словаря EN больше одного раза."""
    seen, out = set(), []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Assign) and any(
                getattr(t, "id", "") == "EN" for t in node.targets) \
                and isinstance(node.value, ast.Dict):
            for key in node.value.keys:
                if isinstance(key, ast.Constant):
                    if key.value in seen:
                        out.append(key.value)
                    seen.add(key.value)
    return out


class TestCatalogue(unittest.TestCase):

    def test_literals_are_found(self):
        self.assertTrue(tr_literals())

    def test_every_string_has_english(self):
        missing = [(f, t) for f, t in tr_literals() if t not in i18n.EN]
        self.assertEqual(missing, [])

    def test_no_dead_entries(self):
        used = {t for _, t in tr_literals()}
        self.assertEqual(sorted(set(i18n.EN) - used), [])

    def test_no_repeated_keys(self):
        # Повтор ключа в словаре Python молча затирает первый перевод:
        # «Вставить» было и «Insert» у макета, и «Paste» в меню меток.
        self.assertEqual(repeated_keys(i18n_source()), [])

    def test_repeated_key_is_caught(self):
        sample = 'EN = {\n    "A": "a",\n    "B": "b",\n    "A": "c",\n}\n'
        self.assertEqual(repeated_keys(sample), ["A"])

    def test_english_has_no_cyrillic(self):
        for text in i18n.EN.values():
            self.assertIsNone(re.search(r"[А-Яа-яЁё]", text), text)

    def test_placeholders_match(self):
        for source, text in i18n.EN.items():
            self.assertEqual(sorted(re.findall(r"{\w+}", source)),
                             sorted(re.findall(r"{\w+}", text)), source)


class TestSwitch(unittest.TestCase):

    def tearDown(self):
        i18n.set_language("ru")

    def test_language_switch(self):
        i18n.set_language("ru")
        self.assertEqual(i18n.tr("{value} км", value="12"), "12 км")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("{value} км", value="12"), "12 km")

    def test_text_placeholder(self):
        # Подстановка с именем первого параметра tr падала TypeError.
        i18n.set_language("ru")
        self.assertEqual(i18n.tr("Поиск: {text}", text="Пермь"),
                         "Поиск: Пермь")


if __name__ == "__main__":
    unittest.main()
