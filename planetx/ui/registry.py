# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строки каталога, описанные своими файлами (core/rows.py).

Новая строка - запись ROWS в своём файле ui/<строка>.py и одна строка
здесь. Каталог (ui/nasamaps.py), строка «Поиск» (ui/commands.py) и окно
глобуса (ui/globe) обходят реестр.
"""
from ..core.rows import Registry
from . import (aef, cables, faults, fieldmap, geomap, infra, miningareas,
               plants, plates, tilemaps, tileoverlays, valuemaps, volcanoes)

ROWS = Registry().add(
    *fieldmap.ROWS,
    *aef.ROWS,
    *tilemaps.ROWS,
    *valuemaps.ROWS,
    *geomap.ROWS,
    *infra.ROWS,
    *tileoverlays.ROWS,
    *cables.ROWS,
    *miningareas.ROWS,
    # Порядок строк с overlay_top - порядок слоёв наложения сверху вниз.
    *faults.ROWS,
    *plates.ROWS,
    *volcanoes.ROWS,
    *plants.ROWS,
)
