# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Крупные файлы демо - на GitHub, а не в архиве модуля.

Архив для каталога QGIS не больше 10 МБ, решение автора от 13 октября
2026 года - вынести крупные файлы на GitHub. С 23 октября 2026 года,
решение автора, демо модуля и PlanetX Lite лежат в папке demo
хранилища planetx-terrain с той же раскладкой, что в папке demo модуля.
Прежний выпуск demo-data хранилища модуля остаётся для вышедших версий.
Демо ищет файл в папке модуля (рабочая копия), потом в профиле QGIS,
иначе скачивает его в профиль. Файл годен, если его размер совпал
с записанным здесь - так страница ошибки не сойдёт за файл. Хешей нет:
длинную шестнадцатеричную строку сканер каталога принимает за ключ.

Модуль Qt не знает.
"""
import os

BASE = "https://raw.githubusercontent.com/Valery35/planetx-terrain/main/demo/"
# Путь в папке demo модуля и размер в байтах.
FILES = {
    "quarry/quarry_dem.tif": 3500587,
    "brienz/brienzersee_bed.tif": 823631,
    "models.planetx": 2369838,
}
# Файлы каждого демо.
DEMOS = {
    "quarry": ("quarry/quarry_dem.tif",),
    "brienz": ("brienz/brienzersee_bed.tif",),
    "models": ("models.planetx",),
}


def url(path):
    """Адрес файла демо в planetx-terrain."""
    return BASE + path


def is_good(path, size):
    """Файл есть и его размер совпал."""
    try:
        return os.path.getsize(path) == size
    except OSError:
        return False


def locate(path, folders):
    """Годный файл демо в первой из папок folders или None."""
    size = FILES[path]
    for folder in folders:
        full = os.path.join(folder, *path.split("/"))
        if is_good(full, size):
            return full
    return None


def missing(name, folders):
    """Файлы демо name, которых нет ни в одной из папок."""
    return [p for p in DEMOS.get(name, ()) if locate(p, folders) is None]


def total_size(paths):
    """Сумма размеров файлов, байты."""
    return sum(FILES[p] for p in paths)
