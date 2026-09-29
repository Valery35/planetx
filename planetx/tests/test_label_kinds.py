# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""У каждого стиля надписи есть класс в ядре.

render/labels.py рисует надпись по стилю STYLES[вид], а место в очереди
берёт из core.places.KIND[вид]. Вид без класса ронял кадр: подписи
сетки «grid» и «circle» дали KeyError в QGIS автора 29 сентября 2026
года. render/labels.py требует Qt, поэтому ключи стилей читаются
из текста файла.
"""
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "core"))

import places  # noqa: E402


def style_kinds():
    with open(os.path.join(HERE, "render", "labels.py"),
              encoding="utf-8") as f:
        text = f.read()
    block = text[text.index("STYLES = {"):]
    block = block[:block.index("\n}")]
    return set(re.findall(r'^\s+"(\w+)":', block, re.MULTILINE))


class TestKinds(unittest.TestCase):

    def test_every_style_has_class(self):
        kinds = style_kinds()
        self.assertIn("grid", kinds)
        self.assertEqual(kinds - set(places.KIND), set())


if __name__ == "__main__":
    unittest.main()
