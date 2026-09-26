# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Правила кода из AGENTS.md, проверяемые без QGIS.

Каждое правило - функция, которая получает текст модуля и возвращает
список находок. Класс ``TestGuardsCatch`` подаёт каждой функции образец
с нарушением. Так проверяется, что сторож ловит нарушение, а не только
пропускает чистый код.
"""
import ast
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
ROOT = os.path.dirname(PLUGIN)
SKIP_DIRS = {"__pycache__", "libs"}
MAX_LINE = 79

# Модули ядра считают без Qt, QGIS и GL.
CORE_FORBIDDEN = {"qgis", "PyQt5", "PyQt6", "OpenGL", "sip"}


def broad_handlers(source):
    """except Exception и except BaseException."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler) or node.type is None:
            continue
        types = node.type.elts if isinstance(node.type, ast.Tuple) \
            else [node.type]
        names = {ast.unparse(t).split(".")[-1] for t in types}
        if names & {"Exception", "BaseException"}:
            found.append(node.lineno)
    return found


def bare_handlers(source):
    """except без типа исключения."""
    return [node.lineno for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.ExceptHandler) and node.type is None]


def silent_handlers(source):
    """Обработчик из одного pass, continue или break."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.ExceptHandler) or len(node.body) != 1:
            continue
        if isinstance(node.body[0], (ast.Pass, ast.Continue, ast.Break)):
            found.append(node.lineno)
    return found


def duplicate_imports(source):
    """Повторный импорт того же имени на верхнем уровне, замечание F811.

    Ветки try и except одного импорта повтором не считаются, это откат
    для другой версии Qt.
    """
    found = []
    seen = set()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Try):
            branches = [node.body] + [h.body for h in node.handlers]
            names = set()
            for branch in branches:
                for sub in branch:
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        names.update(a.asname or a.name for a in sub.names)
            pairs = [(name, node.lineno) for name in sorted(names)]
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            pairs = [(a.asname or a.name, node.lineno) for a in node.names]
        else:
            continue
        for name, line in pairs:
            if name in seen:
                found.append(line)
            seen.add(name)
    return found


def long_lines(source):
    """Строки длиннее 79 символов. Считаются символы, а не байты."""
    return [number for number, line in enumerate(source.split("\n"), 1)
            if len(line) > MAX_LINE]


def missing_header(source):
    """В первых пяти строках нет упоминания лицензии."""
    head = "\n".join(source.split("\n")[:5])
    return [] if "GNU GPL" in head else [1]


def core_imports_qt(source):
    """Импорт Qt, QGIS или GL в модуле ядра."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0:
            names = [node.module or ""]
        else:
            continue
        if any(n.split(".")[0] in CORE_FORBIDDEN for n in names):
            found.append(node.lineno)
    return found


def unused_imports(source):
    """Имена, которые модуль импортирует и нигде не использует.

    Замена pyflakes F401, его нет в Python из QGIS. Импорт в блоке
    try с откатом и имена из __all__ считаются использованными.
    """
    tree = ast.parse(source)
    imported = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                name = alias.asname or alias.name.split(".")[0]
                imported.setdefault(name, node.lineno)
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            base = node
            while isinstance(base, ast.Attribute):
                base = base.value
            if isinstance(base, ast.Name):
                used.add(base.id)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            used.add(node.value)  # имена из __all__
    return sorted(line for name, line in imported.items()
                  if name not in used)


def bom(source):
    """Метка BOM в начале файла. Её пишет Set-Content в PowerShell 5.1."""
    return [1] if source.startswith("﻿") else []


def python_files():
    """Все модули плагина и инструментов, кроме вложенных библиотек."""
    for top in (PLUGIN, os.path.join(ROOT, "tools")):
        for folder, dirs, files in os.walk(top):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for name in sorted(files):
                if name.endswith(".py"):
                    yield os.path.join(folder, name)


def read(path):
    """Текст файла. Метка BOM сохраняется, её ловит отдельный сторож."""
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def scan(check, paths):
    found = []
    for path in paths:
        for line in check(read(path)):
            found.append("%s:%d" % (os.path.relpath(path, ROOT), line))
    return found


class TestCodeRules(unittest.TestCase):
    """Правила из раздела «Чего нельзя делать в коде»."""

    def setUp(self):
        self.paths = list(python_files())

    def test_files_are_found(self):
        names = {os.path.basename(p) for p in self.paths}
        self.assertIn("plugin.py", names)
        self.assertIn("test_hygiene.py", names)

    def test_no_broad_exception_handlers(self):
        self.assertEqual(scan(broad_handlers, self.paths), [])

    def test_no_bare_except(self):
        self.assertEqual(scan(bare_handlers, self.paths), [])

    def test_no_silent_exception_handlers(self):
        self.assertEqual(scan(silent_handlers, self.paths), [])

    def test_no_duplicate_imports(self):
        self.assertEqual(scan(duplicate_imports, self.paths), [])

    def test_lines_fit_79_characters(self):
        self.assertEqual(scan(long_lines, self.paths), [])

    def test_every_module_has_license_header(self):
        self.assertEqual(scan(missing_header, self.paths), [])

    def test_no_unused_imports(self):
        plugin = [p for p in self.paths
                  if os.sep + "tests" + os.sep not in p]
        self.assertEqual(scan(unused_imports, plugin), [])

    def test_no_bom(self):
        texts = [os.path.join(ROOT, n) for n in os.listdir(ROOT)
                 if n.endswith(".md")]
        self.assertEqual(scan(bom, self.paths + texts), [])

    def test_no_module_shadows_the_standard_library(self):
        # Тесты кладут папку core в начало sys.path. Модуль с именем
        # из стандартной библиотеки подменил бы её.
        names = {os.path.splitext(os.path.basename(p))[0]
                 for p in self.paths}
        self.assertEqual(sorted(names & set(sys.stdlib_module_names)), [])

    def test_core_does_not_import_qt(self):
        core = [p for p in self.paths
                if os.sep + "core" + os.sep in p]
        self.assertEqual(scan(core_imports_qt, core), [])


class TestGuardsCatch(unittest.TestCase):
    """Каждый сторож краснеет на образце с нарушением."""

    def assertCatches(self, check, bad, good):
        self.assertTrue(check(bad), "сторож пропустил нарушение")
        self.assertEqual(check(good), [], "сторож сработал на чистом коде")

    def test_broad_handler_guard(self):
        good = "try:\n    x = 1\nexcept ValueError:\n    x = 2\n"
        for bad_type in ("Exception", "BaseException", "(ValueError, "
                         "Exception)", "Exception as exc"):
            bad = "try:\n    x = 1\nexcept %s:\n    x = 2\n" % bad_type
            self.assertCatches(broad_handlers, bad, good)

    def test_bare_handler_guard(self):
        self.assertCatches(
            bare_handlers,
            "try:\n    x = 1\nexcept:\n    x = 2\n",
            "try:\n    x = 1\nexcept OSError:\n    x = 2\n")

    def test_silent_handler_guard(self):
        for body in ("pass", "continue", "break"):
            bad = ("for i in []:\n    try:\n        x = 1\n"
                   "    except OSError:\n        %s\n" % body)
            self.assertCatches(
                silent_handlers, bad,
                "try:\n    x = 1\nexcept OSError:\n    x = 2\n")

    def test_duplicate_import_guard(self):
        self.assertCatches(
            duplicate_imports,
            "import os\nimport os\n",
            "try:\n    from a import X\nexcept ImportError:\n"
            "    from b import X\n")

    def test_long_line_guard(self):
        self.assertCatches(long_lines, "x = 1" + " " * 80 + "\n",
                           "ш" * 79 + "\n")

    def test_header_guard(self):
        self.assertCatches(missing_header, "import os\n",
                           "# Лицензия GNU GPL версии 3.\n")

    def test_unused_import_guard(self):
        self.assertCatches(unused_imports,
                           "import os\nimport sys\nsys.exit()\n",
                           "import os\nos.getcwd()\n")

    def test_bom_guard(self):
        self.assertCatches(bom, "﻿# x\n", "# x\n")

    def test_core_import_guard(self):
        for bad in ("import OpenGL\n", "from qgis.core import X\n",
                    "from PyQt6 import QtCore\n", "import PyQt5.QtGui\n"):
            self.assertCatches(core_imports_qt, bad,
                               "import numpy as np\nfrom .a import b\n")


if __name__ == "__main__":
    unittest.main()
