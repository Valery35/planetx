# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Сборка архива плагина для каталога QGIS и для выпуска на GitHub.

    python tools/build_zip.py

Архив dist/planetx-<версия>.zip содержит папку planetx без тестов
и кэша Python. Один и тот же архив идёт в каталог и на GitHub.
Перед сборкой прогоняется preflight, при ошибках архив не собирается.
"""
import configparser
import os
import subprocess
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PLUGIN = "planetx"
SKIP_DIRS = {"tests", "__pycache__"}
SKIP_SUFFIXES = (".pyc", ".pyo")


def version():
    meta = configparser.ConfigParser()
    meta.read(os.path.join(ROOT, PLUGIN, "metadata.txt"), encoding="utf-8")
    return meta.get("general", "version")


def files():
    base = os.path.join(ROOT, PLUGIN)
    for folder, dirs, names in os.walk(base):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(names):
            if name.endswith(SKIP_SUFFIXES):
                continue
            path = os.path.join(folder, name)
            yield path, os.path.relpath(path, ROOT).replace(os.sep, "/")


def main():
    check = subprocess.run(
        [sys.executable, os.path.join(ROOT, "tools", "preflight.py")],
        capture_output=True, text=True, encoding="utf-8", timeout=300)
    print(check.stdout.rstrip())
    if check.returncode != 0:
        print("\npreflight нашёл ошибки, архив не собран")
        return 1
    number = version()
    dist = os.path.join(ROOT, "dist")
    os.makedirs(dist, exist_ok=True)
    target = os.path.join(dist, "%s-%s.zip" % (PLUGIN, number))
    count = 0
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for path, name in files():
            archive.write(path, name)
            count += 1
    with zipfile.ZipFile(target) as archive:
        broken = archive.testzip()
        names = archive.namelist()
    if broken is not None:
        print("архив повреждён на", broken)
        return 1
    must = ["planetx/__init__.py", "planetx/metadata.txt", "planetx/LICENSE",
            "planetx/icon.png"]
    missing = [m for m in must if m not in names]
    if missing:
        print("в архиве нет", missing)
        return 1
    print("\nархив %s, файлов %d, %.0f КБ"
          % (os.path.relpath(target, ROOT), count,
             os.path.getsize(target) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
