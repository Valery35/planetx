# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузчик тайлов слоя вида, которые собираются в рабочих потоках
из частей файлов в сети: снимки событий (ui/events.py) и здания Overture
(ui/overture.py).

Вид просит тайлы так же, как у загрузчика тайлов по адресам
(net/loader.py): want_many, retain, abort, сигнал loaded (ключ, два
значения). Части файлов идут мостом net/ranges.py через менеджер сети
модуля в главном потоке, поэтому поток только ждёт ответа и разбирает.
"""
import time
from concurrent.futures import ThreadPoolExecutor

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from .. import journal
from ..core import cog, pmtiles
from ..net import ranges

POLL = 15  # мс между проверками рабочих потоков
RETRY = 30.0  # с до новой попытки тайла после отказа сети
# Ошибки, после которых тайл просится снова через RETRY.
FAILURES = (OSError, cog.CogError, pmtiles.PmtilesError)


class ThreadTiles(QObject):
    """Тайлы work(ключ) -> (значение, значение) в рабочих потоках,
    не больше in_flight сразу."""

    loaded = pyqtSignal(object, object, object)

    def __init__(self, workers, in_flight, name, parent=None):
        super().__init__(parent)
        self.workers = workers
        self.in_flight = in_flight
        self.name = name
        self.queue = []
        self.running = {}
        self.failed = {}  # ключ тайла: время отказа
        self.pool = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._work)
        ranges.bridge()  # мост создаётся в главном потоке

    def work(self, key):
        raise NotImplementedError

    def want_many(self, items):
        now = time.monotonic()
        for key, _ in items:
            if key in self.queue or key in self.running:
                continue
            if now - self.failed.get(key, -RETRY) < RETRY:
                continue
            self.queue.append(key)
        if self.queue and not self.timer.isActive():
            self.timer.start()

    def retain(self, wanted):
        self.queue = [k for k in self.queue if k in wanted]

    def busy(self):
        return len(self.queue) + len(self.running)

    def pump_if_due(self):
        """Вид зовёт после кадра, как у загрузчика тайлов по адресам:
        здесь работу ведёт свой таймер."""
        if self.queue and not self.timer.isActive():
            self.timer.start()

    def abort(self):
        self.timer.stop()
        self.queue = []
        for future in self.running.values():
            future.cancel()
        self.running = {}
        if self.pool is not None:
            self.pool.shutdown(wait=False)
            self.pool = None

    def _work(self):
        for key, future in list(self.running.items()):
            if not future.done():
                continue
            del self.running[key]
            try:
                first, second = future.result()
            except FAILURES as error:
                self.failed[key] = time.monotonic()
                journal.note("{} tile {}: {}".format(self.name, key, error))
                continue
            self.loaded.emit(key, first, second)
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=self.workers)
        while self.queue and len(self.running) < self.in_flight:
            key = self.queue.pop(0)
            self.running[key] = self.pool.submit(self.work, key)
        if not self.queue and not self.running:
            self.timer.stop()
