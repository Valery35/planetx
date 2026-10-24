# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка снимков полярных шапок (core/polar.py).

Снимок полюса просится один раз за сеанс, когда шапку видно
(core.polar.needed), - 36 тайлов служб Esri через кэш QGIS. Тайлы
раскодируются по приходу. Перед показом цвет мозаики подгоняется
к подложке: 8 тайлов уровня 3 у края шапки (core.polar.matched),
при смене подложки - заново. Отказ больше половины тайлов - снимок
не ставится, повтор через RETRY с.
"""
import time

import numpy as np
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtGui import QImage

from ..core import polar
from ..net.loader import image_to_rgba
from ..net.overlay import fetch_bytes

RETRY = 300.0  # с до повтора после отказа
EDGE_LEVEL = 3  # уровень тайлов подложки для цвета края


class PolarCaps(QObject):

    arrived = pyqtSignal()  # снимок полюса ушёл виду

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.done = set()  # полюса со снимком
        self.loading = {}  # полюс: {"layout", "images", "left", "replies"}
        self.failed_at = {}
        self.stopped = False
        self.raw = {}  # полюс: (раскладка, мозаика без подгонки)
        self.source = None  # подложка, к которой подгоняется цвет
        self.edges = {}  # полюс: ждущие запросы тайлов края

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

    def set_source(self, source):
        """Подложка сменилась: цвет готовых шапок подгоняется заново."""
        if source is self.source:
            return
        self.source = source
        for north in self.raw:
            self._match(north)

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
        job["images"][key] = _decode(data)
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
        self.raw[north] = (job["layout"], job["layout"].mosaic(images))
        self._match(north)

    def _match(self, north):
        """Тайлы подложки у края шапки, затем мозаика с подогнанным
        цветом виду. Без подложки или тайлов - мозаика как есть."""
        source = self.source
        if source is None:
            self._show(north, None)
            return
        n = 1 << EDGE_LEVEL
        row = 0 if north else n - 1
        job = {"left": n, "images": [None] * n, "source": source,
               "replies": []}
        self.edges[north] = job
        for x in range(n):
            job["replies"].append(fetch_bytes(
                source.tile_url(EDGE_LEVEL, x, row),
                lambda data, error, north=north, job=job, x=x:
                self._edge(north, job, x, data)))

    def _edge(self, north, job, x, data):
        if self.stopped or self.edges.get(north) is not job:
            return
        image = _decode(data)
        if image is not None:
            job["images"][x] = image[polar.edge_rows(north), :, :3] \
                .reshape(-1, 3).astype(np.float64).mean(axis=0)
        job["left"] -= 1
        if job["left"]:
            return
        del self.edges[north]
        colors = job["images"]
        known = [c for c in colors if c is not None]
        want = None
        if known:
            # Тайл без ответа - средний цвет пришедших.
            mean = np.mean(known, axis=0)
            want = np.array([c if c is not None else mean for c in colors])
        self._show(north, want)

    def _show(self, north, want):
        layout, image = self.raw[north]
        if want is not None:
            image = polar.matched(image, layout,
                                  polar.rim_color(layout, image), want)
        self.view.set_polar_image(north, image)
        self.arrived.emit()

    def close(self):
        """Снять ждущие запросы, поздние ответы окно не трогают."""
        self.stopped = True
        for job in list(self.loading.values()) + list(self.edges.values()):
            for reply in job["replies"]:
                reply.abort()
        self.loading = {}
        self.edges = {}


def _decode(data):
    image = QImage.fromData(data) if data else QImage()
    return None if image.isNull() else image_to_rgba(image)
