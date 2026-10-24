# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка обзора неба HiPS для вида неба (core/hips.py,
render/hips.py).

Сначала Allsky.jpg - всё небо порядка 3 одной картинкой, потом тайлы
вида, которых не хватает (HipsSky.want), не больше PARALLEL сразу,
через кэш QGIS. Тайлы, ушедшие из вида, снимаются. Тайл без ответа
не просится снова до смены обзора.
"""
from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtGui import QImage

from ..core import hips
from ..net.loader import image_to_rgba
from ..net.overlay import fetch_bytes

PARALLEL = 6
TICK = 120  # мс между проверками нужных тайлов
ALLSKY = "allsky"


class SkySurveys(QObject):

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.key = None
        self.base = None
        self.loading = {}  # ключ тайла или ALLSKY: ответ
        self.failed = set()
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._tick)

    def set_survey(self, key):
        """Обзор неба по ключу core.hips.SURVEYS, None - Млечный путь."""
        item = hips.survey(key) if key else None
        if item is None:
            key = None
        if key == self.key:
            return
        self._abort()
        self.failed.clear()
        self.key = key
        self.base = item[1] if item else None
        self.view.hips.set_survey(key, item[2] if item else hips.MIN_ORDER)
        if key is None:
            self.timer.stop()
        else:
            self.timer.start()
        self.view.update()

    def _abort(self):
        loading, self.loading = self.loading, {}
        for reply in loading.values():
            reply.abort()

    def _tick(self):
        sky = self.view.hips
        if self.key is None or self.view.sky_view is None:
            return
        if sky.allsky is None and sky.allsky_pending is None \
                and ALLSKY not in self.loading and ALLSKY not in self.failed:
            self._fetch(ALLSKY, hips.allsky_url(self.base))
        want = [k for k in sky.want if k not in self.failed]
        wanted = set(want)
        for key in [k for k in self.loading if k != ALLSKY
                    and k not in wanted]:
            self.loading.pop(key).abort()
        for key in want:
            if len(self.loading) >= PARALLEL:
                break
            if key in self.loading or sky.has(key):
                continue
            self._fetch(key, hips.tile_url(self.base, *key))

    def _fetch(self, key, url):
        survey = self.key
        self.loading[key] = fetch_bytes(
            url, lambda data, error, key=key, survey=survey:
            self._arrived(key, survey, data))

    def _arrived(self, key, survey, data):
        if survey != self.key or self.loading.get(key) is None:
            return
        del self.loading[key]
        image = QImage.fromData(data) if data else QImage()
        if image.isNull():
            self.failed.add(key)
            return
        rgba = image_to_rgba(image)
        if key == ALLSKY:
            self.view.hips.set_allsky(rgba)
        else:
            self.view.hips.add_tile(key, rgba)
        self.view.update()

    def missing(self):
        """Тайлов вида в загрузке, для значка загрузки."""
        return len(self.loading)

    def close(self):
        self.timer.stop()
        self.key = None
        self._abort()
