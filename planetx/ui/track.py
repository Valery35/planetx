# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Растущие треки из точечных слоёв проекта и камера следом.

Трек - точечный слой проекта с полем времени и, если объектов
несколько, полем объекта. Настройки трека слоя хранятся в проекте.
Время берётся у временного контроллера QGIS: к концу его текущего
промежутка у объекта растёт пройденный путь, в текущей точке стоит
метка с названием объекта. Контроллер выключен - треки целиком.

Камера следом держит объект в центре, азимут - по ходу движения,
расстояние и наклон остаются. Между шагами времени камера доезжает
до новой точки плавно (core.track.Glide).
"""
import json
import time

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsFeatureRequest, QgsProject,
                       QgsVectorLayer)
from qgis.gui import QgsColorButton
from qgis.PyQt.QtCore import QDate, QDateTime, QObject, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QFormLayout, QPushButton,
                                 QVBoxLayout)
from qgis.utils import iface

from ..core.features import Shape
from ..core.navigation import Pose
from ..core.track import Glide, Track
from ..i18n import tr
from ..qt_compat import enum, enum_int
from .project import ENTRY

TRACK_KEY = "tracks"  # запись проекта: настройки треков по слоям, JSON
TRACK_COLOR = (255, 80, 40, 255)
TRACK_WIDTH = 3.0
# Переход камеры между шагами времени, секунд, в этих пределах.
GLIDE_MIN = 0.05
GLIDE_MAX = 1.0


JULIAN_1970 = 2440588  # юлианский день 1 января 1970 года


def seconds(value):
    """Время поля в секундах от 1970 года или None.

    Считается по показаниям часов, без часового пояса. Временной
    контроллер QGIS 3.36 отдаёт промежуток с тем же временем на часах,
    но в UTC, а время точек остаётся местным. Треки уходили на смещение
    пояса, 28 сентября 2026 года.
    """
    if isinstance(value, QDateTime):
        if not value.isValid():
            return None
        return (value.date().toJulianDay() - JULIAN_1970) * 86400.0 \
            + value.time().msecsSinceStartOfDay() / 1000.0
    if isinstance(value, QDate):
        if not value.isValid():
            return None
        return (value.toJulianDay() - JULIAN_1970) * 86400.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        parsed = QDateTime.fromString(value.strip(),
                                      enum(Qt, "DateFormat", "ISODate"))
        return seconds(parsed) if parsed.isValid() else None
    return None


def point_layer(layer):
    """Точечный векторный слой: номер Qgis.GeometryType 0."""
    return isinstance(layer, QgsVectorLayer) \
        and enum_int(layer.geometryType()) == 0


def read_track(layer, time_field, object_field=""):
    """Трек core.track.Track из точек слоя. Точки без времени
    пропускаются."""
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(layer.crs(), wgs,
                                       QgsProject.instance())
    names = [n for n in (time_field, object_field) if n]
    request = QgsFeatureRequest().setSubsetOfAttributes(names,
                                                        layer.fields())
    items = []
    for feature in layer.getFeatures(request):
        t = seconds(feature[time_field])
        point = _wgs_point(feature.geometry(), transform)
        if t is None or point is None:
            continue
        key = feature[object_field] if object_field else layer.name()
        items.append((str(key), t, point.y(), point.x()))
    return Track(items)


def _wgs_point(geometry, transform):
    """Точка геометрии в WGS84 или None, если её нет или пересчёт
    не удался."""
    if geometry is None or geometry.isEmpty():
        return None
    try:
        geometry.transform(transform)
    except QgsCsException:
        return None
    if geometry.isMultipart():
        points = geometry.asMultiPoint()
        return points[0] if points else None
    return geometry.asPoint()


def default_time_field(layer):
    """Поле времени из временных свойств слоя, если оно задано."""
    props = layer.temporalProperties()
    field = props.startField() if hasattr(props, "startField") else ""
    return field if field in layer.fields().names() else ""


class TrackDialog(QDialog):
    """Окно «Трек» слоя: поле времени, поле объекта, цвет, камера."""

    def __init__(self, layer, settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Трек: {name}", name=layer.name()))
        settings = settings or {}
        names = layer.fields().names()
        form = QFormLayout()
        self.time = QComboBox(self)
        self.time.addItems(names)
        chosen = settings.get("time") or default_time_field(layer)
        if chosen in names:
            self.time.setCurrentText(chosen)
        self.time.setToolTip(tr(
            "Поле с датой и временем точки. Годятся поля даты и времени, "
            "текст в виде ISO 8601 и число секунд от 1970 года."))
        form.addRow(tr("Время"), self.time)
        self.object = QComboBox(self)
        self.object.addItem(tr("Один объект"), "")
        for name in names:
            self.object.addItem(name, name)
        index = self.object.findData(settings.get("object", ""))
        self.object.setCurrentIndex(max(index, 0))
        self.object.setToolTip(tr(
            "Поле, которое отличает объекты друг от друга, например номер "
            "машины. У каждого объекта свой путь и своя метка."))
        form.addRow(tr("Объект"), self.object)
        self.color = QgsColorButton(self)
        self.color.setAllowOpacity(True)
        self.color.setColor(QColor(*settings.get("color", TRACK_COLOR)))
        self.color.setToolTip(tr("Цвет пройденного пути."))
        form.addRow(tr("Цвет"), self.color)
        self.follow = QCheckBox(tr("Камера следом"), self)
        self.follow.setChecked(bool(settings.get("follow", False)))
        self.follow.setToolTip(tr(
            "Камера держит первый объект трека в центре, азимут - по ходу "
            "движения. Расстояние и наклон меняются колесом и мышью."))
        form.addRow("", self.follow)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        self.remove = QPushButton(tr("Убрать трек"), self)
        self.remove.setToolTip(tr("Слой больше не показывается треком."))
        buttons.addButton(self.remove, enum(QDialogButtonBox, "ButtonRole",
                                            "DestructiveRole"))
        self.removed = False
        self.remove.clicked.connect(self._remove)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _remove(self):
        self.removed = True
        self.accept()

    def settings(self):
        color = self.color.color()
        return {"time": self.time.currentText(),
                "object": self.object.currentData() or "",
                "color": [color.red(), color.green(), color.blue(),
                          color.alpha()],
                "follow": self.follow.isChecked()}


class TrackManager(QObject):
    """Треки слоёв проекта, время контроллера QGIS и камера следом."""

    changed = pyqtSignal()

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.settings = {}  # номер слоя -> настройки
        self.tracks = {}  # номер слоя -> Track
        self.moment = None  # секунды или None - треки целиком
        self._shapes = []
        self._last_step = None
        controller = iface.mapCanvas().temporalController() \
            if iface is not None else None
        self.controller = controller
        # Контроллер переживает окно глобуса. Связь с ним снимает close,
        # иначе после закрытия окна сигнал шёл бы в удалённый объект,
        # как у ProjectWatch в QGIS 3.40.15.
        self._link = controller.updateTemporalRange.connect(
            self._time_changed) if controller is not None else None
        self.load()

    def close(self):
        """Снять связь с временным контроллером QGIS."""
        if self._link is not None:
            QObject.disconnect(self._link)
            self._link = None

    # Настройки в проекте.

    def load(self):
        text, ok = QgsProject.instance().readEntry(ENTRY, TRACK_KEY, "")
        try:
            data = json.loads(text) if ok and text else {}
        except ValueError:
            data = {}
        self.settings = data if isinstance(data, dict) else {}
        self.reload()

    def _save(self):
        QgsProject.instance().writeEntry(ENTRY, TRACK_KEY,
                                         json.dumps(self.settings))

    def set_track(self, layer, settings):
        """Показать слой треком с настройками или убрать, None."""
        if settings is None:
            self.settings.pop(layer.id(), None)
        else:
            self.settings[layer.id()] = settings
        self._save()
        self.reload()

    def reload(self):
        """Перечитать точки всех треков, например после правки слоёв."""
        self.tracks = {}
        project = QgsProject.instance()
        for layer_id, settings in list(self.settings.items()):
            layer = project.mapLayer(layer_id)
            if layer is None or not point_layer(layer) \
                    or settings.get("time") not in layer.fields().names():
                continue
            self.tracks[layer_id] = read_track(layer, settings["time"],
                                               settings.get("object", ""))
        self._time_changed()

    # Время.

    def _current_range(self):
        """Текущий промежуток контроллера или None, если он выключен.

        Номер режима: 0 - выключен, 1 - анимация, 2 - неподвижный
        промежуток, у QGIS 3 и 4 одинаково.
        """
        controller = self.controller
        if controller is None:
            return None
        mode = enum_int(controller.navigationMode())
        if mode == 0:
            return None
        if mode == 1:
            return controller.dateTimeRangeForFrameNumber(
                controller.currentFrameNumber())
        return controller.temporalExtents()

    def _time_changed(self, *args):
        """Новый промежуток времени: сигнал контроллера даёт его сам."""
        span = args[0] if args else self._current_range()
        if self.controller is not None \
                and enum_int(self.controller.navigationMode()) == 0:
            span = None
        self.moment = seconds(span.end()) if span is not None else None
        self._build()
        self._follow()
        self.changed.emit()

    def _build(self):
        shapes = []
        for layer_id, track in self.tracks.items():
            settings = self.settings.get(layer_id, {})
            color = tuple(settings.get("color", TRACK_COLOR))
            for position in track.at(self.moment):
                if len(position.path) >= 2:
                    shapes.append(Shape("line", position.path, color=color,
                                        width=TRACK_WIDTH))
                shapes.append(Shape("point", [(position.lat, position.lon)],
                                    name=position.key))
        self._shapes = shapes

    def shapes(self):
        """Пути и метки объектов для глобуса."""
        return list(self._shapes)

    # Камера.

    def _follow(self):
        target = None
        for layer_id, track in self.tracks.items():
            if self.settings.get(layer_id, {}).get("follow"):
                positions = track.at(self.moment)
                if positions:
                    target = positions[0]
                    break
        if target is None:
            self._last_step = None
            return
        nav = self.view.navigator
        now = time.monotonic()
        step = GLIDE_MAX if self._last_step is None \
            else min(max(now - self._last_step, GLIDE_MIN), GLIDE_MAX)
        self._last_step = now
        start = nav.pose
        heading = start.heading if target.heading != target.heading \
            else target.heading
        end = Pose(target.lat, target.lon, start.distance, heading,
                   start.tilt)
        nav.start_flight(Glide(start, end, step), now)
        self.view.update()
