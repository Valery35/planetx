# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Википедия рядом: загрузка статей с координатами по тайлам вида.

Ядро - core/wikipedia.py. Тайлы вокруг точки взгляда просятся по
одному, не чаще core.wikipedia.GAP, ответы ложатся в кэш QGIS. Смена
языка интерфейса сбрасывает пришедшие тайлы. После отказа службы тайл
возвращается в очередь через RETRY. Выключение строки посреди запроса -
не отказ.
"""
import time

from qgis.PyQt.QtCore import QTimer

from .. import journal
from ..core import wikipedia
from ..net.overlay import fetch_json
from .overpass import brief_error

RETRY = 30.0  # с паузы после отказа службы, выбор помощника
KEPT_TILES = 400  # тайлов в памяти, давние уходят первыми


class WikiArticles:
    """Статьи Википедии по тайлам. done() - пришли новые, failed() -
    отказ службы, сообщение пользователю."""

    def __init__(self, view, done, failed):
        self.view = view
        self.done = done
        self.failed = failed
        self.lang = "en"
        self.tiles = {}  # тайл - список core.wikipedia.Article
        self.queue = []
        self.reply = None
        self.sent = 0.0
        self.paused_until = 0.0

    def articles(self):
        return [a for found in self.tiles.values() for a in found]

    def want(self, lat, lon, altitude, lang):
        """Недостающие тайлы у точки взгляда - в очередь."""
        lang = wikipedia.language(lang)
        if lang != self.lang:
            self.stop()
            self.tiles = {}
            self.lang = lang
        tiles = wikipedia.view_tiles(lat, lon, altitude)
        self.queue = [t for t in tiles if t not in self.tiles]
        self.pump()

    def stop(self):
        """Снять очередь и запрос. Отмена - не отказ службы."""
        self.queue = []
        reply, self.reply = self.reply, None
        if reply is not None:
            self.view.data_pending = max(0, self.view.data_pending - 1)
            reply.abort()

    def pump(self):
        if self.reply is not None or not self.queue:
            return
        now = time.monotonic()
        wait = max(self.sent + wikipedia.GAP, self.paused_until) - now
        if wait > 0.0:
            QTimer.singleShot(int(wait * 1000) + 1, self.pump)
            return
        tile = self.queue.pop(0)
        self.sent = now
        self.view.data_pending += 1
        self.reply = fetch_json(
            wikipedia.geosearch_url(self.lang, tile),
            lambda data, error, tile=tile, lang=self.lang:
                self._arrived(tile, lang, data, error))

    def _arrived(self, tile, lang, data, error):
        if self.reply is None or lang != self.lang:
            return  # снят выключением строки или сменой языка
        self.view.data_pending = max(0, self.view.data_pending - 1)
        self.reply = None
        found = None
        if data is not None:
            try:
                found = wikipedia.parse_geosearch(data)
            except ValueError as problem:
                error = str(problem)
        if found is None:
            journal.note("wikipedia {}: {}".format(tile, brief_error(error)))
            self.paused_until = time.monotonic() + RETRY
            self.queue = [tile] + [t for t in self.queue if t != tile]
            self.failed()
            self.pump()
            return
        self.tiles[tile] = found
        while len(self.tiles) > KEPT_TILES:
            self.tiles.pop(next(iter(self.tiles)))
        self.done()
        self.pump()
