# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-модели на треках KML (gx:Track с Model): поза на момент шкалы
времени, модель под курсором и камера следом.

Просьба автора от 20 октября 2026 года - самосвалы демо треками KML
без слоя QGIS, с камерой следом. Модель, её место и поворот на момент -
core.track.model_pose, момент - правый бегунок шкалы, закрытая шкала -
конец пути. Камера следом - как у треков слоёв проекта (ui/track.py):
модель на луче взгляда (core.movers.chase_on), колесо и Esc -
ChaseControl.
"""
import numpy as np
from qgis.PyQt.QtCore import QTimer

from ..core import movers
from ..core.ellipsoid import geodetic_to_ecef
from ..core.navigation import Pose
from ..core.track import model_pose
from .chase import ChaseControl

FOLLOW_TICK = 50  # мс между позами камеры следом
FOLLOW_REACH = 200.0  # м от глаза до модели при включении
PICK_PIXELS = 14  # логических пикселей до модели под курсором


class ModelTracks:
    """Модели треков KML окна глобуса."""

    def __init__(self, window):
        self.window = window
        self.view = window.view
        # [(ключ наложения, название, строки пути, altitudeMode)]
        self.items = []
        self.followed = None
        self.chase = ChaseControl(self.view, lambda: self.set_follow(None))
        self.timer = QTimer(window)
        self.timer.setInterval(FOLLOW_TICK)
        self.timer.timeout.connect(self._step)

    def set_items(self, items):
        self.items = list(items)
        if self.followed is not None \
                and all(key != self.followed for key, *_ in self.items):
            self.set_follow(None)

    def moment(self, rows):
        """Время пути на момент шкалы, закрытая шкала - конец пути."""
        span = getattr(self.window, "_time_range", None)
        return span[1] if span else rows[-1][0]

    def span(self):
        """Охват времени всех путей (от, до) или None."""
        if not self.items:
            return None
        return (min(rows[0][0] for _, _, rows, _ in self.items),
                max(rows[-1][0] for _, _, rows, _ in self.items))

    def pose(self, item):
        """(широта, долгота, высота на экране, азимут) модели или None."""
        _, _, rows, mode = item
        found = model_pose(rows, self.moment(rows))
        if found is None:
            return None
        lat, lon, alt, heading = found[:4]
        scale = self.view.store.scale or 1.0
        if mode == "absolute":
            level = alt * scale
        else:
            level = float(self.view.label_height(lat, lon))
            if mode == "relativeToGround":
                level += alt
        return lat, lon, level, heading

    def under(self, px, py):
        """Ключ модели под пикселем кадра или None."""
        found = [(item[0], self.pose(item)) for item in self.items]
        found = [(key, p) for key, p in found if p is not None]
        if not found:
            return None
        lats = np.array([p[0] for _, p in found])
        lons = np.array([p[1] for _, p in found])
        levels = np.array([p[2] for _, p in found])
        pixels, front = self.view.camera.project(
            geodetic_to_ecef(lats, lons, levels))
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        gap = np.where(front, gap, np.inf)
        n = int(np.argmin(gap))
        if gap[n] > PICK_PIXELS * self.view.devicePixelRatioF():
            return None
        return found[n][0]

    def label(self, key):
        return next((name for k, name, _, _ in self.items if k == key), "")

    def set_follow(self, key):
        """Камера следом за моделью key, None - отпустить."""
        self.followed = key
        if key is None:
            self.timer.stop()
            self.chase.stop()
            return
        self.chase.start(FOLLOW_REACH)
        self.timer.start()
        self._step()

    def _step(self):
        item = next((i for i in self.items if i[0] == self.followed), None)
        found = self.pose(item) if item is not None else None
        if found is None:
            self.set_follow(None)
            return
        lat, lon, level, heading = found
        pose = self.view.navigator.pose
        look_lat, look_lon, look, distance = movers.chase_on(
            lat, lon, heading, level, self.view.label_height,
            self.chase.reach, pose.tilt)
        self.view.navigator.show(Pose(look_lat, look_lon, distance, look,
                                      pose.tilt))
        self.view.update()
