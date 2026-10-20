# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тайлы воды векторной основы для суши ниже уровня моря.

С глубинами морей метки, пути и подписи стоят не ниже нуля. Где
рельеф ниже нуля, окно раз в TICK мс просит тайлы основы уровня
core.watermask.LEVEL под своими объектами и у точки взгляда, разбирает
слой water и кладёт его в маску вида (GlobeView.water). Точка вне воды
- суша, метка встаёт на рельеф (GlobeView.label_heights). Тайлы идут
через кэш QGIS, не больше PARALLEL сразу, не больше KEPT в памяти.
"""
import time

import numpy as np
from qgis.PyQt.QtCore import QObject, QTimer

from ..core import watermask
from ..core.sync import ground_size, view_box
from ..net.overlay import fetch_bytes

TICK = 1000  # мс между проверками
PARALLEL = 4  # тайлов в пути одновременно
KEPT = 256  # тайлов в памяти
POINTS = 400  # точек одного объекта, не больше
RETRY = 300.0  # с, через столько тайл с ошибкой просится снова
GRID = 3  # точек вида поперёк, сетка GRID × GRID


class WaterTiles(QObject):
    """Загрузка тайлов воды окна window."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.replies = {}  # ключ тайла - ответ в пути
        self.failed = {}  # ключ тайла - время ошибки
        self.stopped = False
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self.tick)
        self.timer.start()

    def _points(self):
        """Широты и долготы своих объектов и сетки у точки взгляда."""
        view = self.window.view
        lats, lons = [], []
        for shape in view.features.shapes:
            points = shape.points or ()
            step = max(1, len(points) // POINTS)
            for lat, lon in list(points)[::step]:
                lats.append(lat)
                lons.append(lon)
        pose = view.navigator.pose
        camera = view.camera
        width, height = ground_size(pose.distance, camera.fov_y,
                                    camera.aspect)
        west, south, east, north = view_box(pose.lat, pose.lon, width,
                                            height, margin=1.0)
        if east < west:
            east += 360.0
        for lat in np.linspace(south, north, GRID):
            for lon in np.linspace(west, east, GRID):
                lats.append(float(lat))
                lons.append((float(lon) + 180.0) % 360.0 - 180.0)
        return np.array(lats, dtype=np.float64), \
            np.array(lons, dtype=np.float64)

    def tick(self):
        window = self.window
        view = window.view
        source = getattr(window, "_ofm_source", None)
        if self.stopped or source is None or not view.sea_floor \
                or not window.planet.earth or view.sky_view is not None:
            return
        keys = set()
        lats, lons = self._points()
        if len(lats):
            low = view.store.heights_at(lats, lons) < 0.0
            if low.any():
                keys |= view.water.missing(lats[low], lons[low])
        # Тайлы вида с рельефом ниже нуля - для масок прохода воды
        # (GlobeView._water_mask).
        selection = getattr(view, "selection", None)
        for key in (selection.draw if selection is not None else ()):
            if key[0] < watermask.MASK_FROM \
                    or view.store.range_for(key)[0] >= 0.0:
                continue
            keys |= {water for water, _, _ in watermask.mask_parts(key)
                     if water not in view.water.tiles}
        if len(keys) > KEPT // 2:
            # Вид на побережье издалека: масок не будет, тайлов не нужно.
            keys = set(sorted(keys)[:KEPT // 2])
        now = time.monotonic()
        for key in sorted(keys):
            if len(self.replies) >= PARALLEL:
                break
            if key in self.replies \
                    or now - self.failed.get(key, -RETRY) < RETRY:
                continue
            self._fetch(source, key)

    def _fetch(self, source, key):
        url = source.tile_url(*key)

        def done(data, error, key=key):
            if self.stopped:
                return
            self.replies.pop(key, None)
            features = None
            if data:
                try:
                    features = watermask.decode_water(bytes(data))
                except (ValueError, IndexError):
                    features = None
            if features is None:
                self.failed[key] = time.monotonic()
                return
            water = self.window.view.water
            while len(water.tiles) >= KEPT:
                # Старые тайлы первыми: словарь хранит порядок прихода.
                water.tiles.pop(next(iter(water.tiles)))
            water.add(key, features)
            self.window.view.update()
        self.replies[key] = fetch_bytes(url, done)

    def stop(self):
        self.stopped = True
        self.timer.stop()
        for reply in list(self.replies.values()):
            reply.abort()
        self.replies.clear()
