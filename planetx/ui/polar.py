# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка снимков полярных шапок (core/polar.py).

Снимок полюса просится один раз за сеанс, когда шапку видно
(core.polar.needed), - 36 тайлов служб Esri через кэш QGIS. Тайлы
раскодируются по приходу, мозаика уходит виду (set_polar_image).
Отказ больше половины тайлов - снимок не ставится, повтор через
RETRY с.
"""
import time

from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QImage

from ..core import polar
from ..net.loader import image_to_rgba
from ..net.overlay import fetch_bytes

RETRY = 300.0  # с до повтора после отказа


class PolarCaps(QObject):

    arrived = pyqtSignal()  # снимок полюса ушёл виду

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.done = set()  # полюса со снимком
        self.loading = {}  # полюс: {"layout", "images", "left", "replies"}
        self.failed_at = {}
        self.stopped = False

    def check(self, lat, altitude):
        """Попросить снимки видимых шапок."""
        if self.stopped or not self.view.polar_on:
            return
        now = time.monotonic()
        for north in polar.needed(lat, altitude):
            if north in self.done or north in self.loading \
                    or now - self.failed_at.get(north, -RETRY) < RETRY:
                continue
            self._load(north)

    def _load(self, north):
        layout = polar.Layout(north)
        tiles = layout.tiles()
        job = self.loading[north] = {"layout": layout, "images": {},
                                     "left": len(tiles), "replies": []}
        for row, col, url in tiles:
            job["replies"].append(fetch_bytes(
                url, lambda data, error, north=north, key=(row, col):
                self._arrived(north, key, data)))

    def _arrived(self, north, key, data):
        job = self.loading.get(north)
        if job is None or self.stopped:
            return
        image = QImage.fromData(data) if data else QImage()
        job["images"][key] = None if image.isNull() \
            else image_to_rgba(image)
        job["left"] -= 1
        if job["left"]:
            return
        del self.loading[north]
        images = job["images"]
        good = sum(1 for i in images.values() if i is not None)
        if good * 2 < len(images):
            self.failed_at[north] = time.monotonic()
            return
        self.done.add(north)
        self.view.set_polar_image(north, job["layout"].mosaic(images))
        self.arrived.emit()

    def close(self):
        """Снять ждущие запросы, поздние ответы окно не трогают."""
        self.stopped = True
        for job in self.loading.values():
            for reply in job["replies"]:
                reply.abort()
        self.loading = {}
