# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка зданий для видимости из точки и инсоляции.

Тайлы слоя building OpenFreeMap (core/roofs.py) под кругом расчёта
идут через кэш QGIS, не больше PARALLEL сразу. Разбор тайла стоит
десятки миллисекунд Python, поэтому он идёт в главном потоке частями
(step) из таймера окна, как расчёт инсоляции: в рабочем потоке разбор
отнимал бы у вида GIL.
"""
import time

from ..core import roofs
from ..net.overlay import fetch_bytes

PARALLEL = 6  # тайлов в пути одновременно


class RoofLoader:
    """Растр крыш круга: тайлы просятся при создании, step разбирает
    пришедшие. Без источника основы или при слишком большом круге
    зданий нет (skipped)."""

    def __init__(self, source, lat, lon, reach, cell):
        self.grid = roofs.Roofs(lat, lon, reach, cell)
        self.keys = roofs.tiles_around(lat, lon, reach)
        self.skipped = source is None or len(self.keys) > roofs.MAX_TILES
        self.source = source
        self.queue = [] if self.skipped else list(self.keys)
        self.replies = {}
        self.arrived = []  # (ключ, байты) ждут разбора
        self.failed = 0
        self.done = 0
        self.stopped = False
        self._pump()

    def _pump(self):
        while self.queue and len(self.replies) < PARALLEL:
            key = self.queue.pop(0)
            self.replies[key] = fetch_bytes(
                self.source.tile_url(*key),
                lambda data, error, key=key: self._done(key, data))

    def _done(self, key, data):
        if self.stopped:
            return
        self.replies.pop(key, None)
        if data:
            self.arrived.append((key, bytes(data)))
        else:
            self.failed += 1
        self._pump()

    @property
    def total(self):
        return 0 if self.skipped else len(self.keys)

    @property
    def ready(self):
        """Все тайлы пришли или отказали и разобраны."""
        return self.skipped or (not self.queue and not self.replies
                                and not self.arrived)

    def step(self, budget):
        """Разбор пришедших тайлов, не дольше budget секунд, но хотя бы
        одного."""
        started = time.perf_counter()
        while self.arrived:
            key, data = self.arrived.pop(0)
            try:
                self.grid.add_tile(key, data)
            except (ValueError, IndexError, KeyError):
                self.failed += 1
            self.done += 1
            if time.perf_counter() - started > budget:
                break

    def heights(self, ground):
        """Функция высот: ground плюс крыши."""
        def at(lats, lons):
            return ground(lats, lons) + self.grid.at(lats, lons)
        return at

    def stop(self):
        self.stopped = True
        for reply in list(self.replies.values()):
            reply.abort()
        self.replies.clear()
        self.queue = []
