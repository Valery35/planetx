# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка объектов OpenStreetMap через Overpass по тайлам вида.

Общий код строк «Шахты и карьеры OSM» и «ЛЭП и трубопроводы OSM»:
тайлы уровня core.mining.ZOOM у точки взгляда ниже MAX_ALTITUDE,
недостающие тайлы - одним запросом POST по общей рамке. Сервер выбирает
общий для всех строк набор зеркал MIRRORS (core/mirrors.py) - по отказам
и времени ответа, не чаще core.mining.GAP к одному серверу. После отказа
тайлы возвращаются в очередь. Выключение строки посреди запроса - не
отказ.
Пользователю при отказе - короткая фраза, подробности без адресов -
в журнал работы.
"""
import re
import time

from qgis.PyQt.QtCore import QTimer

from .. import journal
from ..core import mining
from ..core.mirrors import Mirrors
from ..net.overlay import post_form

# Одно состояние зеркал на все строки: отказ сервера в одной строке
# уводит от него и другие.
MIRRORS = Mirrors(mining.OSM_SERVERS, gap=mining.GAP)


def brief_error(text):
    """Ошибка сети без адресов запроса. Qt пишет в текст ошибки полный
    адрес, у запроса Overpass он в сотни знаков."""
    return re.sub(r"https?://([^/\s]+)\S*", r"\1", text or "")


class OverpassTiles:
    """Объекты Overpass по тайлам. query(рамка) - текст запроса,
    parse(ответ) - список объектов, done() - пришли новые, busy - флажок
    window.view.data_pending, failed(текст) - сообщение пользователю."""

    def __init__(self, view, name, query, parse, done, failed):
        self.view = view
        self.name = name
        self.query = query
        self.parse = parse
        self.done = done
        self.failed = failed
        self.items = {}
        self.queue = []
        self.reply = None
        self.server = None  # адрес текущего или последнего запроса
        self.started = 0.0

    def all_items(self):
        return [item for found in self.items.values() for item in found]

    def want(self, lat, lon, altitude):
        """Недостающие тайлы у точки взгляда - в очередь."""
        tiles = mining.view_tiles(lat, lon, altitude)
        self.queue = [t for t in tiles if t not in self.items]
        self.pump()

    def stop(self):
        """Снять очередь и запрос. Отмена - не отказ сервера."""
        self.queue = []
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()

    def pump(self):
        if self.reply is not None or not self.queue:
            return
        now = time.monotonic()
        server, wait = MIRRORS.pick(now)
        if wait > 0.0:
            QTimer.singleShot(int(wait * 1000) + 1, self.pump)
            return
        tiles, self.queue = self.queue, []
        box = mining.union(mining.tile_bounds(*tile) for tile in tiles)
        MIRRORS.sent(server, now)
        self.server = server
        self.started = now
        self.view.data_pending += 1
        self.reply = post_form(
            server, {"data": self.query(box)},
            lambda data, error, tiles=tiles: self._arrived(tiles, data,
                                                           error))

    def _arrived(self, tiles, data, error):
        self.view.data_pending = max(0, self.view.data_pending - 1)
        if self.reply is None:
            return  # снят выключением строки
        self.reply = None
        now = time.monotonic()
        if data is None:
            pause = MIRRORS.failed(self.server, now - self.started, now)
            journal.note("overpass {} {} tiles: {}, pause {:.0f} s; {}".format(
                self.name, len(tiles), brief_error(error), pause,
                MIRRORS.describe(now)))
            self.failed()
            # Тайлы - обратно в очередь, повтор на следующем сервере после
            # паузы, а не только после сдвига вида.
            self.queue = tiles + [t for t in self.queue if t not in tiles]
            self.pump()
            return
        MIRRORS.ok(self.server, now - self.started)
        found = self.parse(data)
        for n, tile in enumerate(tiles):
            # Объекты общей рамки - у первого тайла, прочие помечены
            # загруженными.
            self.items[tile] = found if n == 0 else []
        self.done()
        self.pump()
