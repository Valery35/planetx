# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сторожа проверки metadata.txt перед каталогом из tools/preflight.py.

Адрес в процент-кодировке каталог не принял у Routeliner, выданный
номер версии закрыт. Сеть и git здесь подменены.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import gittool  # noqa: E402
import preflight  # noqa: E402


class TestUrls(unittest.TestCase):

    def test_percent_encoding_is_error(self):
        found = preflight.url_problems({
            "homepage": "https://www.informpp.ru/%D0%B3%D0%BB/planetx"})
        self.assertTrue(any("процент" in f for f in found), found)

    def test_letters_without_www_and_http(self):
        self.assertEqual(preflight.url_problems({
            "homepage": "https://www.informpp.ru/главная-страница/planetx",
            "tracker": "https://github.com/Valery35/planetx/issues"}), [])
        found = preflight.url_problems({
            "homepage": "https://informpp.ru/planetx",
            "repository": "http://github.com/Valery35/planetx"})
        self.assertEqual(len(found), 2, found)


class TestTags(unittest.TestCase):

    def run_with(self, tags, head, tag_at, version):
        answers = {"tag": "\n".join(tags), "rev-parse": head,
                   "rev-list": tag_at, "fetch": ""}

        def fake(*args):
            return answers[args[0]]
        saved = gittool.git
        gittool.git = fake
        try:
            return [text for level, text in preflight.tag_problems(version)
                    if level == "error"]
        finally:
            gittool.git = saved

    def test_new_number_passes(self):
        self.assertEqual(self.run_with(["v1.44.0", "v1.44.1"], "a", "b",
                                       "1.44.2"), [])

    def test_released_number_on_other_commit(self):
        self.assertEqual(len(self.run_with(["v1.44.1"], "a", "b",
                                           "1.44.1")), 1)

    def test_tagged_head_passes(self):
        self.assertEqual(self.run_with(["v1.44.1"], "a", "a", "1.44.1"), [])

    def test_number_below_last_release(self):
        # 1.9 сравнивается числами: 1.44.1 больше 1.9.0.
        found = self.run_with(["v1.9.0", "v1.44.1"], "a", "b", "1.10.0")
        self.assertEqual(len(found), 1, found)
        self.assertIn("v1.44.1", found[0])


if __name__ == "__main__":
    unittest.main()
