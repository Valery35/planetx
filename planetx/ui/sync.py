# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Синхронизация глобуса с окном карты QGIS.

Карта ведёт глобус: сдвиг и масштаб карты переносят точку взгляда
в центр карты, расстояние камеры подбирается по размеру карты
на местности. Азимут и наклон глобуса остаются, решение автора
от 27 сентября 2026 года.

Глобус ведёт карту: после остановки глобуса центр карты встаёт в точку
взгляда, ширина карты на местности равна ширине вида глобуса.

Система координат карты любая. Центр и края карты переводятся в широту
и долготу преобразованием QGIS, размер на местности считается по дуге
большого круга. Расчёт без Qt лежит в core/sync.py.

Ответ другой стороны на только что сделанный шаг узнаётся по
core.sync.same_view и шага не даёт.
"""
import math

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsPointXY, QgsProject, QgsRectangle)
from qgis.PyQt.QtCore import QObject, QTimer

from ..core import ellipsoid
from ..core.sync import (BOTH, GLOBE_TO_MAP, MAP_TO_GLOBE, MAX_GROUND, arc,
                         distance_for, ground_size, same_view)

MAP_DELAY = 250  # мс тишины на карте перед переносом на глобус
GLOBE_DELAY = 300  # мс покоя глобуса перед переносом на карту
WGS84 = "EPSG:4326"


def _transform(source, target):
    return QgsCoordinateTransform(source, target, QgsProject.instance())


def map_view(canvas):
    """Вид карты: (широта, долгота, ширина и высота на местности, м).

    Края берутся от центра влево и вправо, вверх и вниз по отдельности.
    У карты всего мира левый и правый края - одна точка, а сумма двух
    половин даёт настоящую ширину. None, если центр карты вне области
    определения её проекции.
    """
    extent = canvas.extent()
    crs = canvas.mapSettings().destinationCrs()
    to_wgs = _transform(crs, QgsCoordinateReferenceSystem(WGS84))
    c = extent.center()
    hw, hh = extent.width() / 2.0, extent.height() / 2.0
    try:
        center = to_wgs.transform(c)
        edges = [to_wgs.transform(QgsPointXY(c.x() + dx, c.y() + dy))
                 for dx, dy in ((-hw, 0.0), (hw, 0.0), (0.0, -hh),
                                (0.0, hh))]
    except QgsCsException:
        return None
    lat, lon = center.y(), center.x()
    sides = [arc(lat, lon, p.y(), p.x()) for p in edges]
    width = min(sides[0] + sides[1], MAX_GROUND)
    height = min(sides[2] + sides[3], MAX_GROUND)
    if not (math.isfinite(lat) and math.isfinite(lon)) or width <= 0.0:
        return None
    return lat, lon, width, height


def extent_for(canvas, lat, lon, width):
    """Охват карты в её системе координат: центр и ширина на местности.

    Масштаб проекции в центре меряется сдвигом на полширины к востоку
    и к западу. Высота охвата - по пропорции окна карты. None, если
    точка вне области определения проекции карты.
    """
    crs = canvas.mapSettings().destinationCrs()
    to_map = _transform(QgsCoordinateReferenceSystem(WGS84), crs)
    half = width / 2.0
    dlon = math.degrees(half / (ellipsoid.A * max(math.cos(math.radians(lat)),
                                        1e-6)))
    try:
        c = to_map.transform(QgsPointXY(lon, lat))
        east = to_map.transform(QgsPointXY(min(lon + dlon, 180.0), lat))
        west = to_map.transform(QgsPointXY(max(lon - dlon, -180.0), lat))
    except QgsCsException:
        return None
    hw = 0.5 * (math.hypot(east.x() - c.x(), east.y() - c.y())
                + math.hypot(west.x() - c.x(), west.y() - c.y()))
    if not math.isfinite(hw) or hw <= 0.0:
        return None
    size = canvas.size()
    aspect = size.width() / max(1, size.height())
    hh = hw / aspect
    return QgsRectangle(c.x() - hw, c.y() - hh, c.x() + hw, c.y() + hh)


class MapSync(QObject):
    """Связь окна глобуса с окном карты QGIS.

    window - окно глобуса, у него view, navigator и перелёт fly_view.
    canvas - QgsMapCanvas.
    """

    def __init__(self, window, canvas):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.canvas = canvas
        self.direction = BOTH
        self.enabled = False
        self.moves = 0  # сколько раз карта или глобус переставлены
        self._sent_map = None  # вид, поставленный на карту
        self._sent_globe = None  # вид, поставленный на глобус
        self._seen_pose = None
        self._map_timer = QTimer(self)
        self._map_timer.setSingleShot(True)
        self._map_timer.timeout.connect(self._map_moved)
        self._globe_timer = QTimer(self)
        self._globe_timer.setSingleShot(True)
        self._globe_timer.timeout.connect(self._globe_moved)

    def set_enabled(self, on):
        if on == self.enabled:
            return
        self.enabled = on
        if on:
            self.canvas.extentsChanged.connect(self._map_changed)
            self._sent_map = self._sent_globe = None
            # При включении ведущая сторона сразу ставит ведомую.
            if self.direction == GLOBE_TO_MAP:
                self._globe_moved()
            else:
                self._map_moved()
        else:
            self.canvas.extentsChanged.disconnect(self._map_changed)
            self._map_timer.stop()
            self._globe_timer.stop()

    def set_direction(self, direction):
        self.direction = direction

    def close(self):
        self.set_enabled(False)

    # Карта ведёт глобус.

    def _map_changed(self):
        if self.direction in (MAP_TO_GLOBE, BOTH):
            self._map_timer.start(MAP_DELAY)

    def _map_moved(self):
        if not self.enabled or self.direction == GLOBE_TO_MAP:
            return
        seen = map_view(self.canvas)
        if seen is None:
            return
        lat, lon, width, height = seen
        if same_view((lat, lon, width), self._sent_map):
            return  # это ответ карты на шаг глобуса
        camera = self.view.camera
        distance = distance_for(width, height, camera.fov_y, camera.aspect)
        self._sent_globe = (lat, lon, ground_size(
            distance, camera.fov_y, camera.aspect)[0])
        self.moves += 1
        self.window.fly_view(lat, lon, distance)

    # Глобус ведёт карту.

    def globe_frame(self):
        """Кадр глобуса нарисован. Покой после движения ставит карту."""
        if not self.enabled or self.direction == MAP_TO_GLOBE:
            return
        nav = self.view.navigator
        if nav.grab is not None or nav.inertia is not None \
                or nav.zooming is not None or nav.flight is not None \
                or self.view.turning is not None:
            self._globe_timer.stop()
            return
        pose = nav.pose
        key = (pose.lat, pose.lon, pose.distance)
        if key != self._seen_pose:
            self._seen_pose = key
            self._globe_timer.start(GLOBE_DELAY)

    def globe_view(self):
        pose = self.view.navigator.pose
        camera = self.view.camera
        return pose.lat, pose.lon, ground_size(
            pose.distance, camera.fov_y, camera.aspect)[0]

    def _globe_moved(self):
        if not self.enabled or self.direction == MAP_TO_GLOBE:
            return
        seen = self.globe_view()
        if same_view(seen, self._sent_globe):
            return  # это конец перелёта, начатого картой
        rect = extent_for(self.canvas, *seen)
        if rect is None:
            return
        self.canvas.setExtent(rect)
        self.canvas.refresh()
        now = map_view(self.canvas)
        self._sent_map = now[:3] if now is not None else None
        self.moves += 1
