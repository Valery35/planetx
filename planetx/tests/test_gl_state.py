# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кадр начинается со своего состояния OpenGL.

1 октября 2026 года на Луне и Марсе тайлы рисовались с оставшимся
включённым смешиванием, край диска и швы выходили белыми. Каждая
функция вида, которая очищает буфер кадра, сначала зовёт
gpu.reset_state.
"""
import ast
import os
import unittest

VIEW = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "render", "view.py")


def clears_without_reset(source):
    """Функции, где glClear стоит раньше reset_state или без него."""
    out = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.FunctionDef):
            continue
        calls = sorted(
            (call.lineno, call.func.attr) for call in ast.walk(node)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Attribute)
            and call.func.attr in ("glClear", "reset_state"))
        names = [name for _, name in calls]
        if "glClear" in names and (
                "reset_state" not in names
                or names.index("reset_state") > names.index("glClear")):
            out.append(node.name)
    return out


class TestFrameState(unittest.TestCase):

    def test_view_resets_before_clear(self):
        with open(VIEW, encoding="utf-8") as fh:
            self.assertEqual(clears_without_reset(fh.read()), [])

    def test_guard_sees_missing_reset(self):
        bad = ("def paint(self):\n"
               "    gl.glClear(1)\n"
               "    gpu.reset_state()\n")
        self.assertEqual(clears_without_reset(bad), ["paint"])


if __name__ == "__main__":
    unittest.main()
