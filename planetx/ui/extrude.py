# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выдавливание векторных слоёв проекта по полю.

Пункт «Выдавливание…» меню слоя в «Слоях проекта». Многоугольник -
призма от рельефа на высоту поля × множитель, точка - столбик,
линия - стенка. Цвет - символ объекта в стиле слоя QGIS, как на
карте. Слой выдавлен, пока он отмечен на глобусе. Настройки лежат
в записи проекта (project.read_extrude). Сетки строятся заново при
смене настроек, отметки слоёв, «Обновить» и после прихода подробных
высот рельефа (store.version), не чаще раза в REBUILD_PAUSE мс.
"""
import math

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsProject, QgsRenderContext,
                       QgsVectorLayer, QgsWkbTypes)
from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QLabel)

from ..core import ellipsoid, extrude
from ..i18n import tr
from ..qt_compat import enum
from .project import read_extrude, write_extrude

MAX_FEATURES = 20000  # объектов слоя, дальше не читаются
# Радиус столбика точки - доля поперечника слоя, в пределах метров.
COLUMN_SHARE = 1.0 / 150.0
COLUMN_RANGE = (2.0, 2000.0)
COLUMN_LONE = 10.0  # м, у слоя из одной точки
REBUILD_PAUSE = 2000  # мс между пересборками по приходу высот


def numeric_fields(layer):
    """Числовые поля слоя: имена."""
    return [f.name() for f in layer.fields() if f.isNumeric()]


def feature_height(value, factor):
    """Высота объекта в метрах или None - пусто, не число, не выше 0."""
    try:
        height = float(value) * factor
    except (TypeError, ValueError):
        return None
    return height if math.isfinite(height) and height > 0.0 else None


def in_wgs(geometry, transform):
    """Копия геометрии в широтах и долготах или None, если она пуста
    или не пересчитывается."""
    if geometry is None or geometry.isEmpty():
        return None
    try:
        geometry.transform(transform)
    except QgsCsException:
        return None
    return geometry


class ExtrudeDialog(QDialog):
    """Окно «Выдавливание»: поле высоты и множитель."""

    def __init__(self, layer, current, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Выдавливание - {name}", name=layer.name()))
        form = QFormLayout(self)
        form.addRow(QLabel(tr(
            "Объекты слоя поднимаются над рельефом на высоту из поля: "
            "многоугольник - призмой, точка - столбиком, линия - "
            "стенкой. Цвет - стиль слоя.")))
        self.field = QComboBox()
        self.field.addItem(tr("Не выдавливать"), "")
        for name in numeric_fields(layer):
            self.field.addItem(name, name)
        index = self.field.findData(current.get("field", ""))
        self.field.setCurrentIndex(max(index, 0))
        self.field.setToolTip(tr(
            "Числовое поле высоты объекта. Объект с пустым, нулевым или "
            "отрицательным значением не выдавливается."))
        form.addRow(tr("Высота из поля"), self.field)
        self.factor = QDoubleSpinBox()
        self.factor.setDecimals(3)
        self.factor.setRange(0.001, 100000.0)
        self.factor.setValue(float(current.get("factor", 1.0)))
        self.factor.setToolTip(tr(
            "Высота в метрах - значение поля, умноженное на множитель. "
            "У поля этажей множитель около 3."))
        form.addRow(tr("Множитель, м"), self.factor)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def settings(self):
        field = self.field.currentData()
        if not field:
            return None
        return {"field": field, "factor": self.factor.value()}


class ExtrudeManager(QObject):
    """Сетки выдавленных слоёв вида view.extruded по отметке слоёв."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.shown = []
        self.version = None
        self.counts = {}  # номер слоя - количество выдавленных объектов
        self.timer = QTimer(self)
        self.timer.setInterval(REBUILD_PAUSE)
        self.timer.timeout.connect(self._heights_moved)

    def configure(self, layer):
        """Пункт меню слоя: окно настроек, запись в проект, пересборка."""
        settings = read_extrude()
        dialog = ExtrudeDialog(layer, settings.get(layer.id(), {}),
                               self.window)
        if not dialog.exec():
            return
        value = dialog.settings()
        if value is None:
            settings.pop(layer.id(), None)
        else:
            settings[layer.id()] = value
        write_extrude(settings)
        self.sync(self.shown)

    def sync(self, shown):
        """Отмеченные на глобусе слои shown: выдавленные - в сетки."""
        self.shown = list(shown)
        view = self.window.view
        settings = read_extrude() if self.window.planet.earth else {}
        wanted = [i for i in self.shown if i in settings]
        for name in list(view.extruded.buffers) + list(view.extruded.pending):
            if name not in wanted:
                view.extruded.set_mesh(name, None)
                self.counts.pop(name, None)
        project = QgsProject.instance()
        for layer_id in wanted:
            layer = project.mapLayer(layer_id)
            if not isinstance(layer, QgsVectorLayer):
                continue
            mesh, count = self.build(layer, settings[layer_id])
            view.extruded.set_mesh(layer_id, mesh)
            self.counts[layer_id] = count
        self.version = view.store.version
        if wanted:
            self.timer.start()
        else:
            self.timer.stop()
        view.update()

    def _heights_moved(self):
        """Пришли новые высоты - сетки садятся на них заново."""
        if self.window.view.store.version != self.version:
            self.sync(self.shown)

    def build(self, layer, settings):
        """Сетка слоя и количество выдавленных объектов."""
        field = settings.get("field")
        factor = float(settings.get("factor", 1.0))
        index = layer.fields().indexOf(field or "")
        if index < 0:
            return None, 0
        to_wgs = QgsCoordinateTransform(
            layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance())
        renderer = layer.renderer().clone() if layer.renderer() else None
        context = QgsRenderContext()
        if renderer is not None:
            renderer.startRender(context, layer.fields())
        kind = QgsWkbTypes.geometryType(layer.wkbType())
        radius_m = self._column_radius(layer, to_wgs)
        parts = extrude.Parts()
        try:
            for n, feature in enumerate(layer.getFeatures()):
                if n >= MAX_FEATURES:
                    break
                height = feature_height(feature.attribute(index), factor)
                geometry = in_wgs(feature.geometry(), to_wgs) \
                    if height is not None else None
                if geometry is None:
                    continue
                color = self._color(renderer, feature, context)
                self._add(parts, kind, geometry, height, color, radius_m)
                if n % 200 == 0 \
                        and parts.vertex_count() > extrude.MAX_VERTICES:
                    break
        finally:
            if renderer is not None:
                renderer.stopRender(context)
        footprint = parts.footprint(layer.id())
        if footprint is None:
            return None, 0
        store = self.window.view.store
        return extrude.mesh(footprint, parts.follow(),
                            store.heights_at), len(parts.height)

    @staticmethod
    def _color(renderer, feature, context):
        if renderer is None:
            return (200, 200, 200)
        symbol = renderer.symbolForFeature(feature, context)
        if symbol is None:
            return (200, 200, 200)
        color = symbol.color()
        return (color.red(), color.green(), color.blue())

    @staticmethod
    def _column_radius(layer, to_wgs):
        """Радиус столбика точки по поперечнику слоя."""
        try:
            box = to_wgs.transformBoundingBox(layer.extent())
        except QgsCsException:
            return COLUMN_LONE
        lat = math.radians(box.center().y())
        width = math.radians(box.width()) * math.cos(lat)
        height = math.radians(box.height())
        span = ellipsoid.A * math.hypot(width, height)
        if span <= 0.0:
            return COLUMN_LONE
        return min(max(span * COLUMN_SHARE, COLUMN_RANGE[0]),
                   COLUMN_RANGE[1])

    @staticmethod
    def _add(parts, kind, geometry, height, color, radius_m):
        """Объект в parts по виду геометрии: 0 точки, 1 линии, 2
        многоугольники, составные - по частям."""
        code = int(getattr(kind, "value", kind))
        if code == 0:
            points = geometry.asMultiPoint() if geometry.isMultipart() \
                else [geometry.asPoint()]
            for p in points:
                parts.add_polygon([extrude.column(p.y(), p.x(), radius_m,
                                                  ellipsoid.A)],
                                  height, color=color)
        elif code == 1:
            lines = geometry.asMultiPolyline() if geometry.isMultipart() \
                else [geometry.asPolyline()]
            for line in lines:
                parts.add_line([(p.y(), p.x()) for p in line], height,
                               color=color)
        elif code == 2:
            polygons = geometry.asMultiPolygon() if geometry.isMultipart() \
                else [geometry.asPolygon()]
            for polygon in polygons:
                rings = [[(p.y(), p.x()) for p in ring] for ring in polygon]
                parts.add_polygon(rings, height, color=color)
