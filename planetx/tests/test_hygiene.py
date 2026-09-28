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


SECRET_WORDS = ("pass", "pwd", "secret", "token")


def _secret_name(name):
    return any(word in (name or "").lower() for word in SECRET_WORDS)


def _string(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def secret_literals(source):
    """Строка при имени вида password, правила Bandit B105-B107.

    Каталог QGIS проверяет архив Bandit и блокирует выпуск при такой
    находке, даже если строка пустая. Так был заблокирован выпуск 0.2.0.
    Ловятся значение по умолчанию параметра, именованный аргумент вызова
    и присваивание.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.Lambda)):
            args = node.args
            pairs = list(zip(args.args[len(args.args)
                                       - len(args.defaults):],
                             args.defaults))
            pairs += [(a, d) for a, d in zip(args.kwonlyargs,
                                             args.kw_defaults) if d]
            found += [d.lineno for a, d in pairs
                      if _secret_name(a.arg) and _string(d)]
        elif isinstance(node, ast.Call):
            found += [k.value.lineno for k in node.keywords
                      if _secret_name(k.arg) and _string(k.value)]
        elif isinstance(node, ast.Assign) and _string(node.value):
            for target in node.targets:
                name = getattr(target, "id", None) \
                    or getattr(target, "attr", None)
                if _secret_name(name):
                    found.append(node.lineno)
    return found


SYMBOLS = {"QgsLineSymbol", "QgsFillSymbol", "QgsMarkerSymbol"}


def symbol_from_layers(source):
    """Символ QGIS из списка слоёв конструктором, например
    QgsLineSymbol([слой]). В QGIS 3 слой оставался у Python и удалялся
    дважды, QGIS 3.36 падал. Символ строится через createSimple."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Call) and node.args \
                and isinstance(node.func, ast.Name) \
                and node.func.id in SYMBOLS:
            found.append(node.lineno)
    return found


def flat_property(source):
    """Плоское имя свойства QGIS вида QgsSymbolLayer.PropertyStrokeWidth.

    Проверка Qt 6 каталога считает его ошибкой перечисления, даже
    в ветке для QGIS 3. Версия 0.4.2 получила отметку «Qt6 Check»
    с крестиком, 27 сентября 2026 года.
    """
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) \
                and isinstance(node.value, ast.Name) \
                and node.value.id.startswith("Qgs") \
                and node.attr.startswith("Property") \
                and node.attr[len("Property"):][:1].isupper():
            found.append(node.lineno)
    return found


UNSAFE_XML = ("xml.etree", "xml.sax", "xml.dom", "lxml")


def unsafe_xml(source):
    """Модули XML, которые Bandit каталога QGIS считает опасными для
    чужих файлов. KML читается через expat (core/kml.py)."""
    found = []
    for node in ast.walk(ast.parse(source)):
        names = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        if any(n == bad or n.startswith(bad + ".") for n in names
               for bad in UNSAFE_XML):
            found.append(node.lineno)
    return found


def ctypes_byref(source):
    """Указатель ctypes.byref в вызове OpenGL. PyOpenGL до 3.1.10
    на Python 3.12 ищет обработчик типа _ctypes.CArgObject и не
    находит его. QGIS 3.40.15 падал на запросах видимости надписей,
    28 сентября 2026 года. Ответ пишется в массив (c_uint * 1)()."""
    found = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Attribute) and node.attr == "byref":
            found.append(node.lineno)
        elif isinstance(node, ast.alias) and node.name == "byref":
            found.append(getattr(node, "lineno", 1))
    return found


def outside_connect(source):
    """Прямая связь с сигналом чужого объекта в ui/project.py.

    ProjectWatch связывается с проектом, деревом слоёв и слоями только
    через _link, связи снимаются вместе с ним. Прямая связь с лямбдой
    переживала окно, QGIS 3.40.15 писал RuntimeError про удалённый
    ProjectWatch, 28 сентября 2026 года.
    """
    tree = ast.parse(source)
    allowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_link":
            allowed.update(id(sub) for sub in ast.walk(node))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "connect") or id(node) in allowed:
            continue
        root = node.func.value
        while isinstance(root, ast.Attribute):
            root = root.value
        if not (isinstance(root, ast.Name) and root.id == "self"):
            found.append(node.lineno)
    return found


GL_ENTRIES = ("initializeGL", "_render", "_paint_preview")


def _gl_call(node):
    """Вызов вида GL.x(...) или gpu.gl.x(...)."""
    if not (isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)):
        return False
    owner = node.func.value
    if isinstance(owner, ast.Name):
        return owner.id == "GL"
    return (isinstance(owner, ast.Attribute) and owner.attr == "gl"
            and isinstance(owner.value, ast.Name)
            and owner.value.id == "gpu")


def outside_errors_late(source):
    """Первый вызов OpenGL в начале кадра раньше сбора чужих ошибок.

    PyOpenGL поднимает накопленную ошибку на первом проверяемом вызове.
    В QGIS 4.0.2 у пользователя кадр обрывался на glClearColor
    с ошибкой 1280, 28 сентября 2026 года. render/view.py.
    """
    found = []
    for func in ast.walk(ast.parse(source)):
        if not (isinstance(func, ast.FunctionDef)
                and func.name in GL_ENTRIES):
            continue
        calls = [n for n in ast.walk(func) if isinstance(n, ast.Call)]
        taken = [n.lineno for n in calls
                 if isinstance(n.func, ast.Attribute)
                 and n.func.attr == "_take_outside_errors"]
        first = min((n.lineno for n in calls if _gl_call(n)), default=None)
        if first is not None and (not taken or min(taken) > first):
            found.append(first)
    return found


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

    def test_no_secret_like_literals(self):
        # В архив идут модули плагина без тестов, их и проверяет каталог.
        plugin = [p for p in self.paths if p.startswith(PLUGIN)
                  and os.sep + "tests" + os.sep not in p]
        self.assertEqual(scan(secret_literals, plugin), [])

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

    def test_no_symbol_built_from_layers(self):
        self.assertEqual(scan(symbol_from_layers, self.paths), [])

    def test_no_flat_qgis_property(self):
        plugin = [p for p in self.paths if p.startswith(PLUGIN)
                  and os.sep + "tests" + os.sep not in p]
        self.assertEqual(scan(flat_property, plugin), [])

    def test_no_unsafe_xml(self):
        plugin = [p for p in self.paths if p.startswith(PLUGIN)
                  and os.sep + "tests" + os.sep not in p]
        self.assertEqual(scan(unsafe_xml, plugin), [])

    def test_no_ctypes_byref(self):
        plugin = [p for p in self.paths if p.startswith(PLUGIN)
                  and os.sep + "tests" + os.sep not in p]
        self.assertEqual(scan(ctypes_byref, plugin), [])

    def test_project_watch_links_through_link(self):
        path = os.path.join(PLUGIN, "ui", "project.py")
        self.assertEqual(scan(outside_connect, [path]), [])

    def test_outside_gl_errors_taken_first(self):
        path = os.path.join(PLUGIN, "render", "view.py")
        self.assertEqual(scan(outside_errors_late, [path]), [])

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

    def test_secret_literal_guard(self):
        good = "def f(login=None):\n    user, password = login\n"
        for bad in ('def f(password=""):\n    return password\n',
                    'def f(*, api_token="x"):\n    return 1\n',
                    'f(password="")\n',
                    'self.password = ""\n',
                    'secret = "abc"\n'):
            self.assertCatches(secret_literals, bad, good)

    def test_symbol_guard(self):
        self.assertCatches(
            symbol_from_layers, "s = QgsLineSymbol([line])\n",
            "s = QgsLineSymbol.createSimple(props)\n")

    def test_flat_property_guard(self):
        self.assertCatches(
            flat_property, "w = QgsSymbolLayer.PropertyStrokeWidth\n",
            "w = QgsSymbolLayer.Property.StrokeWidth\n")

    def test_unsafe_xml_guard(self):
        for bad in ("import xml.etree.ElementTree as ET\n",
                    "from xml.sax.saxutils import escape\n",
                    "from xml.dom import minidom\n"):
            self.assertCatches(unsafe_xml, bad,
                               "from xml.parsers import expat\n")

    def test_byref_guard(self):
        good = "v = (ctypes.c_uint * 1)()\nf(q, v)\n"
        for bad in ("f(q, ctypes.byref(v))\n",
                    "from ctypes import byref\nf(q, byref(v))\n"):
            self.assertCatches(ctypes_byref, bad, good)

    def test_outside_connect_guard(self):
        good = ("def _link(self, signal, slot):\n"
                "    self._links.append(signal.connect(slot))\n"
                "self._pass.timeout.connect(self._end_pass)\n"
                "self._link(root.visibilityChanged, self._legend)\n")
        for bad in ("root.visibilityChanged.connect(lambda: 1)\n",
                    "layer.nameChanged.connect(self.renamed)\n"):
            self.assertCatches(outside_connect, bad, good)

    def test_outside_errors_guard(self):
        good = ("def _render(self):\n"
                "    self._take_outside_errors()\n"
                "    gpu.gl.glClearColor(0, 0, 0, 1)\n")
        for bad in ("def _render(self):\n"
                    "    gpu.gl.glClearColor(0, 0, 0, 1)\n"
                    "    self._take_outside_errors()\n",
                    "def initializeGL(self):\n"
                    "    GL.glGetString(GL.GL_RENDERER)\n"):
            self.assertCatches(outside_errors_late, bad, good)

    def test_bom_guard(self):
        self.assertCatches(bom, "﻿# x\n", "# x\n")

    def test_core_import_guard(self):
        for bad in ("import OpenGL\n", "from qgis.core import X\n",
                    "from PyQt6 import QtCore\n", "import PyQt5.QtGui\n"):
            self.assertCatches(core_imports_qt, bad,
                               "import numpy as np\nfrom .a import b\n")


if __name__ == "__main__":
    unittest.main()
