# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строки каталога, описанные своими файлами (core/rows.py).

Новая строка - запись ROWS в своём файле ui/<строка>.py и одна строка
здесь. Каталог (ui/nasamaps.py), строка «Поиск» (ui/commands.py) и окно
глобуса (ui/globe) обходят реестр.
"""
from ..core.rows import Registry
from . import (aef, cables, cadastre, clouds, currents, deposits, faults,
               fieldmap, fires, geoid, geomap, grid, infra, magnetic,
               miningareas, paleo, plants, platemotion, plates, quakes,
               satellites, sky, surface, tilemaps, tileoverlays, transport,
               valuemaps, volcanoes, wiki)

ROWS = Registry().add(
    *sky.ROWS,
    *satellites.ROWS,
    *paleo.ROWS,
    *geoid.ROWS,
    *currents.ROWS,
    *clouds.ROWS,
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
    *platemotion.ROWS,
    *volcanoes.ROWS,
    *magnetic.ROWS,
    *quakes.ROWS,
    *fires.ROWS,
    *transport.ROWS,
    *plants.ROWS,
    *deposits.ROWS,
    *wiki.ROWS,
    *grid.ROWS,
    *surface.ROWS,
    *cadastre.ROWS,
)
