# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Определение объектов щелчком по глобусу.

Опрашиваются слои проекта, отмеченные на глобусе, решение автора
от 27 сентября 2026 года. Точка щелчка переводится в систему координат
каждого слоя. Допуск задаётся в пикселях экрана и переводится в метры
по расстоянию от глаза до точки, потом в единицы слоя. Так он один
на любом удалении, от космоса до улиц.
"""
import math

from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsCsException,
                       QgsExpression, QgsExpressionContext,
                       QgsExpressionContextUtils, QgsFeatureRequest,
                       QgsGeometry, QgsPointXY, QgsProject, QgsRasterLayer,
                       QgsRectangle, QgsVectorLayer)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog, QLabel, QPushButton, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout)

from ..core.coords import format_point
from ..core.measure import surface_level
from ..core import ellipsoid
from ..i18n import tr
from ..qt_compat import enum

FEATURE_LIMIT = 50  # объектов на слой, не больше
EXPAND_UP_TO = 5  # объекты раскрыты, если их всего не больше
try:  # QGIS 3.30 и новее
    RASTER_VALUE = Qgis.RasterIdentifyFormat.Value
except AttributeError:  # QGIS 3.28 и старше
    from qgis.core import QgsRaster
    RASTER_VALUE = QgsRaster.IdentifyFormatValue


def _layer_point(layer, lat, lon, metres):
    """Точка и допуск в системе координат слоя или None."""
    to_layer = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"), layer.crs(),
        QgsProject.instance())
    dlon = math.degrees(metres / (ellipsoid.A * max(
        math.cos(math.radians(lat)), 1e-6)))
    try:
        p = to_layer.transform(QgsPointXY(lon, lat))
        q = to_layer.transform(QgsPointXY(min(lon + dlon, 180.0), lat))
    except QgsCsException:
        return None
    radius = math.hypot(q.x() - p.x(), q.y() - p.y())
    if not math.isfinite(radius):
        return None
    return p, radius


def _title(layer, feature, expression):
    context = QgsExpressionContext(
        QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    context.setFeature(feature)
    value = expression.evaluate(context) if expression else None
    return str(value) if value not in (None, "") else str(feature.id())


def _vector(layer, lat, lon, metres):
    """Объекты слоя под точкой: [(название, [(поле, значение)], номер)]."""
    found = _layer_point(layer, lat, lon, metres)
    if found is None:
        return []
    p, radius = found
    rect = QgsRectangle(p.x() - radius, p.y() - radius,
                        p.x() + radius, p.y() + radius)
    request = QgsFeatureRequest().setFilterRect(rect).setLimit(
        FEATURE_LIMIT)
    point = QgsGeometry.fromPointXY(p)
    text = layer.displayExpression()
    expression = QgsExpression(text) if text else None
    names = layer.fields().names()
    out = []
    for feature in layer.getFeatures(request):
        geometry = feature.geometry()
        if geometry.isEmpty() or geometry.distance(point) > radius:
            continue
        values = [(name, feature[name]) for name in names]
        out.append((_title(layer, feature, expression), values,
                    feature.id()))
    return out


def _raster(layer, lat, lon):
    """Значения каналов растра в точке: [(канал, значение)]."""
    found = _layer_point(layer, lat, lon, 0.0)
    if found is None or not layer.extent().contains(found[0]):
        return []
    result = layer.dataProvider().identify(found[0], RASTER_VALUE)
    if not result.isValid():
        return []
    return [(layer.bandName(band), value)
            for band, value in sorted(result.results().items())]


def identify(layers, lat, lon, metres):
    """Опрос слоёв: [(слой, [(название, [(поле, значение)], номер)])].

    У растра один «объект» - его значения в точке, номер None.
    """
    out = []
    for layer in layers:
        if isinstance(layer, QgsVectorLayer):
            features = _vector(layer, lat, lon, metres)
        elif isinstance(layer, QgsRasterLayer):
            values = _raster(layer, lat, lon)
            features = [(tr("значения в точке"), values, None)] \
                if values else []
        else:
            features = []
        if features:
            out.append((layer, features))
    return out


def hemispheres():
    """Подписи полушарий для градусов-минут-секунд."""
    return (tr("с. ш."), tr("ю. ш."), tr("в. д."), tr("з. д."))


def point_text(lat, lon, height=None, digits=6, fmt="decimal"):
    """Координаты точки и высота рельефа для окна и строки состояния.

    fmt - формат из core.coords.FORMATS.
    """
    text = format_point(lat, lon, fmt, hemispheres(), digits)
    if height is None:
        return text
    # Ниже уровня моря - глубина, как у дна океана, core.measure.
    kind, value = surface_level(height)
    if kind == "depth":
        return tr("{point}, глубина {depth} м", point=text, depth=value)
    return tr("{point}, высота {height} м", point=text, height=value)


def _value(value):
    return "" if value is None else str(value)


class IdentifyDialog(QDialog):
    """Немодальное окно «Объекты»: точка и дерево слой - объект - поле."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Объекты"))
        self.setModal(False)
        self.point = QLabel(self)
        self.point.setTextInteractionFlags(
            enum(Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        self.tree = QTreeWidget(self)
        self.tree.setColumnCount(2)
        self.tree.setHeaderLabels([tr("Объект"), tr("Значение")])
        self.select = QPushButton(tr("Выделить на карте"), self)
        self.select.setToolTip(tr(
            "Выделить найденные объекты в слоях QGIS. Выделение видно "
            "на карте, в таблице атрибутов и на глобусе."))
        self.select.clicked.connect(self._select_on_map)
        self.found = []
        layout = QVBoxLayout(self)
        layout.addWidget(self.point)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.select)
        self.resize(420, 360)

    def _select_on_map(self):
        """Выделение найденных объектов в их слоях, прежнее снимается."""
        for layer, features in self.found:
            ids = [fid for _, _, fid in features if fid is not None]
            if ids:
                layer.selectByIds(ids)

    def show_result(self, text, found):
        self.point.setText(text)
        self.tree.clear()
        self.found = found
        self.select.setEnabled(any(fid is not None for _, features in found
                                   for _, _, fid in features))
        total = sum(len(features) for _, features in found)
        for layer, features in found:
            top = QTreeWidgetItem(self.tree, [layer.name(), ""])
            top.setExpanded(True)
            for title, values, _ in features:
                item = QTreeWidgetItem(top, [title, ""])
                item.setExpanded(total <= EXPAND_UP_TO)
                for name, value in values:
                    QTreeWidgetItem(item, [str(name), _value(value)])
        if not found:
            QTreeWidgetItem(self.tree, [tr("Под точкой объектов нет"), ""])
        self.tree.resizeColumnToContents(0)
        self.show()
        self.raise_()
