# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Проверка готовности к публикации.

Перенесена из Topoliner. Смотрит на то, что обычно возвращает модератор
каталога: заполненность метаданных, лицензию, внешние зависимости, единый
номер версии. Запуск из корня репозитория:

    python tools/preflight.py

Код возврата 1 означает ошибки. Замечания код возврата не меняют.
"""

import ast
import configparser
import importlib.util
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = "planetx"
SKIP_DIRS = {"tests", "__pycache__", "libs"}

REQUIRED = ("name", "qgisMinimumVersion", "qgisMaximumVersion",
            "description", "version", "author", "email", "about",
            "repository", "tracker", "icon")

# Кроме стандартной библиотеки допустимы модули, которые есть в QGIS.
ALLOWED = {"qgis", "PyQt5", "PyQt6", "numpy", "OpenGL"}

VERSION = re.compile(r"\b(\d+\.\d+\.\d+)\b")
# Файлы, где номер версии плагина повторяется. Ищется номер рядом
# с именем плагина или в заголовке раздела журнала изменений.
VERSION_FILES = ("README.md", "README.en.md")


def module_level_imports(path):
    """Имена всех модулей, которые файл импортирует.

    Учитываются и импорты внутри try и функций. Откат вида
    ``try: PyQt6 ... except ImportError`` тоже внешний импорт, если модуля
    нет в списке допустимых.
    """
    with open(path, encoding="utf-8") as fh:
        tree = ast.parse(fh.read())
    # Запасной импорт в обработчике ImportError нужен тестам без QGIS.
    # Внутри плагина срабатывает относительный импорт перед ним.
    fallback = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None \
                and ast.unparse(node.type) == "ImportError":
            for sub in ast.walk(node):
                fallback.add(id(sub))
    names = set()
    for node in ast.walk(tree):
        if id(node) in fallback:
            continue
        if isinstance(node, ast.Import):
            names.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module \
                and node.level == 0:
            names.add(node.module.split(".")[0])
    return names


def plugin_files():
    for folder, dirs, files in os.walk(os.path.join(ROOT, PLUGIN)):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(folder, name)


def read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def version_mentions():
    """Пары место и номер для всех упоминаний версии плагина."""
    found = []
    for name in VERSION_FILES:
        path = os.path.join(ROOT, name)
        if not os.path.exists(path):
            continue
        for number, line in enumerate(read(path).split("\n"), 1):
            if re.search(r"PlanetX|[Вв]ерси|[Vv]ersion", line):
                for match in VERSION.finditer(line):
                    found.append(("%s:%d" % (name, number), match.group(1)))
    changelog = os.path.join(ROOT, "CHANGELOG.md")
    if os.path.exists(changelog):
        for number, line in enumerate(read(changelog).split("\n"), 1):
            match = VERSION.search(line) if line.startswith("## ") else None
            if match:
                found.append(("CHANGELOG.md:%d" % number, match.group(1)))
                break
    for path in plugin_files():
        for number, line in enumerate(read(path).split("\n"), 1):
            for match in re.finditer(r"PlanetX (\d+\.\d+\.\d+)", line):
                found.append(("%s:%d" % (os.path.relpath(path, ROOT),
                                         number), match.group(1)))
    return found


def main():
    errors, warnings = [], []

    meta_path = os.path.join(ROOT, PLUGIN, "metadata.txt")
    cp = configparser.ConfigParser()
    cp.read(meta_path, encoding="utf-8")
    general = cp["general"]

    for field in REQUIRED:
        if not general.get(field, "").strip():
            errors.append("metadata.txt: не заполнено поле %s" % field)
    if re.search(r"[А-Яа-яЁё]", general.get("description", "")):
        warnings.append("description на русском, каталог международный")
    if general.get("experimental", "").lower() not in ("false", ""):
        warnings.append("плагин помечен как experimental")

    # Без qgisMaximumVersion QGIS подставляет 3.99 и на четвёртой версии
    # объявляет плагин несовместимым.
    maximum = general.get("qgisMaximumVersion", "").strip()
    if maximum and int(maximum.split(".")[0]) < 4:
        errors.append("qgisMaximumVersion=%s не покрывает QGIS 4" % maximum)

    icon = general.get("icon", "").strip()
    if icon and not os.path.exists(os.path.join(ROOT, PLUGIN, icon)):
        errors.append("нет файла значка %s/%s" % (PLUGIN, icon))

    for name in ("__init__.py", "metadata.txt", "LICENSE"):
        if not os.path.exists(os.path.join(ROOT, PLUGIN, name)):
            errors.append("нет файла %s/%s" % (PLUGIN, name))
    license_path = os.path.join(ROOT, "LICENSE")
    if not os.path.exists(license_path):
        errors.append("нет файла LICENSE")
    elif "GNU GENERAL PUBLIC LICENSE" not in read(license_path):
        errors.append("LICENSE не является текстом GPL")

    version = general.get("version", "").strip()
    for place, number in version_mentions():
        if number != version:
            errors.append("%s: версия %s, в metadata.txt %s"
                          % (place, number, version))

    allowed = ALLOWED | set(sys.stdlib_module_names)
    for path in plugin_files():
        for module in sorted(module_level_imports(path) - allowed):
            errors.append("%s: внешний импорт %s"
                          % (os.path.relpath(path, ROOT), module))

    # Каталог прогоняет код анализатором и возвращает загрузку
    # с замечаниями. Если pyflakes установлен, они ловятся здесь.
    if importlib.util.find_spec("pyflakes") is None:
        warnings.append("pyflakes не установлен, анализ кода пропущен")
    else:
        out = subprocess.run(
            [sys.executable, "-m", "pyflakes", os.path.join(ROOT, PLUGIN)],
            capture_output=True, text=True, timeout=120)
        for line in out.stdout.splitlines():
            if line.strip():
                warnings.append("pyflakes: " + line.strip())

    print("Проверка готовности PlanetX %s" % (version or "?"))
    if errors:
        print("\nОшибки:")
        for line in errors:
            print("  " + line)
    if warnings:
        print("\nЗамечания:")
        for line in warnings:
            print("  " + line)
    if not errors and not warnings:
        print("\nВсё в порядке.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
