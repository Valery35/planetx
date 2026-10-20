# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шаблон всплывающего окна BalloonStyle."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import balloon  # noqa: E402


class TestFill(unittest.TestCase):

    def test_places(self):
        text = balloon.fill(
            "<h3>$[name]</h3>$[description]<br>$[depth/displayName]: "
            "$[depth] м $[owner] $[nope]$[geDirections]",
            name="Скв. <7>", description="<b>керн</b>",
            data=[("depth", "412.5"), ("owner", "A & B")])
        self.assertEqual(text, "<h3>Скв. &lt;7&gt;</h3><b>керн</b><br>"
                               "depth: 412.5 м A &amp; B ")

    def test_empty_template(self):
        self.assertEqual(balloon.fill("", "x"), "")


if __name__ == "__main__":
    unittest.main()
