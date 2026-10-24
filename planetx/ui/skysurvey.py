# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка снимков неба HiPS для вида неба (core/hips.py LAYERS,
render/hips.py).

У слоя с Allsky.jpg сначала она - всё небо порядка 3 одной картинкой.
Тайлы вида, которых не хватает (HipsSky.want), просятся, пока слой
проявлен, не больше PARALLEL сразу на все слои, через кэш QGIS. Тайлы,
ушедшие из вида, снимаются. Тайл без ответа просится снова не раньше
RETRY. Сколько тайлов вида ещё нет, вид знает по sky_pending - его
показывает значок загрузки.
"""
import time

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtGui import QImage

from ..core import hips
from ..net.loader import image_to_rgba
from ..net.overlay import fetch_bytes

PARALLEL = 6
TICK = 120  # мс между проверками нужных тайлов
RETRY = 60.0  # с до повторной просьбы тайла без ответа
ALLSKY = "allsky"


class SkySurveys(QObject):

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.on = False
        self.loading = {}  # (ключ слоя, ключ тайла или ALLSKY): ответ
        self.failed = {}  # ключ: время отказа
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._tick)

    def set_on(self, on):
        """Снимки неба при приближении включены или нет."""
        on = bool(on)
        self.view.sky_imagery = on
        if on == self.on:
            return
        self.on = on
        if on:
            self.timer.start()
        else:
            self.timer.stop()
            self._abort()
        self.view.update()

    def _abort(self):
        loading, self.loading = self.loading, {}
        self.view.sky_pending = 0
        for reply in loading.values():
            reply.abort()

    def _refused(self, key):
        """Отказ свежее RETRY - тайл пока не просится."""
        when = self.failed.get(key)
        if when is None:
            return False
        if time.monotonic() - when < RETRY:
            return True
        del self.failed[key]
        return False

    def _tick(self):
        if not self.on or self.view.sky_view is None:
            self.view.sky_pending = 0
            return
        wanted = set()
        queue = []
        for sky in self.view.hips_layers:
            layer = sky.layer
            if sky.share <= 0.0:
                continue
            if layer.allsky and sky.allsky is None \
                    and sky.allsky_pending is None:
                key = (layer.key, ALLSKY)
                if not self._refused(key):
                    wanted.add(key)
                    queue.append((key, hips.allsky_url(layer.base), sky))
            for tile in sky.want:
                key = (layer.key, tile)
                if sky.has(tile) or self._refused(key):
                    continue
                wanted.add(key)
                queue.append((key, hips.tile_url(layer.base, *tile), sky))
        for key in [k for k in self.loading if k not in wanted
                    and k[1] != ALLSKY]:
            self.loading.pop(key).abort()
        for key, url, sky in queue:
            if len(self.loading) >= PARALLEL:
                break
            if key in self.loading:
                continue
            self._fetch(key, url, sky)
        pending = len(wanted | set(self.loading))
        if pending != self.view.sky_pending:
            self.view.sky_pending = pending
            self.view.update()

    def _fetch(self, key, url, sky):
        self.loading[key] = fetch_bytes(
            url, lambda data, error, key=key, sky=sky:
            self._arrived(key, sky, data))

    def _arrived(self, key, sky, data):
        if self.loading.get(key) is None:
            return
        del self.loading[key]
        image = QImage.fromData(data) if data else QImage()
        if image.isNull():
            self.failed[key] = time.monotonic()
            return
        rgba = image_to_rgba(image)
        if key[1] == ALLSKY:
            sky.set_allsky(rgba)
        else:
            sky.add_tile(key[1], rgba)
        self.view.update()

    def missing(self):
        """Тайлов вида в загрузке, для значка загрузки."""
        return len(self.loading)

    def close(self):
        self.timer.stop()
        self.on = False
        self._abort()
