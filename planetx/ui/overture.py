# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-здания Overture Maps: тайлы MVT из одного архива PMTiles в сети.

Архив открывается в рабочем потоке при первой просьбе (заголовок
и корневой каталог), тайлы читаются частями файла мостом net/ranges.py.
Разбор - тот же, что у зданий векторной основы (core/buildings.py),
поля высоты Overture - core.buildings.heights. Слой building_part
не берётся, части лежат поверх своих зданий.
"""
import threading

from ..core import buildings, pmtiles, sources
from ..core.places import DecodeError
from ..net import ranges
from .threadtiles import ThreadTiles

WORKERS = 4  # рабочих потоков: тайл - одна-две части файла
IN_FLIGHT = 8  # тайлов в работе сразу


class OvertureTiles(ThreadTiles):
    """Загрузчик тайлов зданий Overture для render/buildings.py, сигнал
    loaded (ключ, Footprint или EMPTY, None)."""

    def __init__(self, url, parent=None):
        super().__init__(WORKERS, IN_FLIGHT, "overture", parent)
        self.url = url
        self.archive = None
        self.lock = threading.Lock()

    def _open(self):
        with self.lock:
            if self.archive is None:
                self.archive = pmtiles.Archive(
                    lambda start, length: ranges.fetch(self.url, start,
                                                       length))
            return self.archive

    def work(self, key):
        z, x, y = key
        data = self._open().tile(z, x, y)  # отказ сети - OSError
        if data is None:
            return buildings.EMPTY, None
        try:
            found = buildings.footprints(key, data)
        except (DecodeError, ValueError, IndexError) as error:
            raise pmtiles.PmtilesError(str(error)) from error
        return (buildings.EMPTY if found is None else found), None


def release_url(catalog):
    """Адрес архива по ответу каталога STAC (словарь или None)."""
    return sources.overture_url(catalog if isinstance(catalog, dict)
                                else None)
