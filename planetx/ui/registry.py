# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строки каталога, описанные своими файлами (core/rows.py).

Новая строка - запись ROWS в своём файле ui/<строка>.py и одна строка
здесь. Каталог (ui/nasamaps.py), строка «Поиск» (ui/commands.py) и окно
глобуса (ui/globe) обходят реестр.
"""
from ..core.rows import Registry
from . import fieldmap

ROWS = Registry().add(
    *fieldmap.ROWS,
)
