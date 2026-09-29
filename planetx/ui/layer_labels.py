# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подписи слоёв проекта на глобусе.

Для отмеченных векторных слоёв с включёнными подписями берутся текст,
цвет и кегль подписи QGIS. Объекты в окне вокруг точки взгляда
читаются в рабочем потоке через QgsVectorLayerFeatureSource: запрос
к базе данных или большому файлу не держит кадр. Место подписи -
точка объекта, середина линии или точка на поверхности многоугольника.
Готовые подписи уходят в надписи вида, render/labels.py. Подписи по
правилам берутся по каждому правилу со своим фильтром. Масштаб
видимости подписей QGIS не учитывается, надписи вида сами уходят
друг от друга.
"""
from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsCsException, QgsExpression,
                       QgsExpressionContext, QgsExpressionContextUtils,
                       QgsFeatureRequest, QgsProject, QgsRectangle,
                       QgsRuleBasedLabeling, QgsVectorLayer,
                       QgsVectorLayerFeatureSource,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from ..core import layer_labels
from ..core.places import Place
from ..render.labels import layer_style

WGS84 = "EPSG:4326"


def _unit_name(unit):
    """Единица кегля подписи QGIS словом для core.layer_labels."""
    if unit == Qgis.RenderUnit.Millimeters:
        return "mm"
    if unit == Qgis.RenderUnit.Pixels:
        return "pixels"
    return "points"


def _geometry_kind(geometry_type):
    """Вид геометрии слоя словом: point, line, polygon."""
    if geometry_type == Qgis.GeometryType.Line:
        return "line"
    if geometry_type == Qgis.GeometryType.Polygon:
        return "polygon"
    return "point"


def _settings(layer):
    """Подписи слоя: пары (настройки QgsPalLayerSettings, фильтр
    правила или None). Пусто, если подписи слоя выключены."""
    if not layer.labelsEnabled() or layer.labeling() is None:
        return []
    labeling = layer.labeling()
    if isinstance(labeling, QgsVectorLayerSimpleLabeling):
        return [(labeling.settings(), None)]
    if isinstance(labeling, QgsRuleBasedLabeling):
        out = []
        for rule in labeling.rootRule().descendants():
            if rule.active() and rule.settings() is not None:
                out.append((rule.settings(), rule.filterExpression() or None))
        return out
    return []


class _Job:
    """Всё, что нужно рабочему потоку для одного слоя. Собирается
    в главном потоке, там же, где живёт слой."""

    def __init__(self, layer, settings, rule, rect, to_wgs, center):
        self.layer_id = layer.id()
        self.lat, self.lon = center  # точка взгляда, у неё подписи
        self.source = QgsVectorLayerFeatureSource(layer)
        self.geometry_kind = _geometry_kind(layer.geometryType())
        self.skipped = 0  # точек, которые не перевелись в WGS84
        self.rect = rect
        self.to_wgs = to_wgs
        text = settings.fieldName
        self.expression = QgsExpression(
            text if settings.isExpression else QgsExpression.quotedColumnRef(
                text))
        self.rule = QgsExpression(rule) if rule else None
        self.context = QgsExpressionContext(
            QgsExpressionContextUtils.globalProjectLayerScopes(layer))
        fmt = settings.format()
        color = fmt.color()
        self.kind_args = (
            layer_labels.pixel_size(fmt.size(), _unit_name(fmt.sizeUnit())),
            (color.red(), color.green(), color.blue(), 245),
            self.geometry_kind == "point")


def _anchor(geometry, kind):
    """Точка подписи объекта: точка, середина линии, точка
    на поверхности многоугольника. None у пустой геометрии."""
    if geometry is None or geometry.isEmpty():
        return None
    if kind == "line":
        point = geometry.interpolate(geometry.length() / 2.0)
    elif kind == "polygon":
        point = geometry.pointOnSurface()
    else:
        point = geometry.centroid()
    if point is None or point.isEmpty():
        return None
    return point.asPoint()


class _Result(QObject):
    """Живёт в главном потоке. Сигнал из рабочего потока идёт очередью."""

    done = pyqtSignal(int, object)


class _ReadTask(QRunnable):
    """Чтение подписей слоёв в рабочем потоке. Ничего не ждёт от главного
    потока. Исключения QGIS ловятся по месту: предупреждение Python
    в рабочем потоке роняет QGIS, см. AGENTS.md."""

    def __init__(self, generation, jobs, sink):
        super().__init__()
        self.generation = generation
        self.jobs = jobs
        self.sink = sink

    def run(self):
        found = []
        for job in self.jobs:
            found.extend(self._read(job))
        self.sink.done.emit(self.generation, found)

    @staticmethod
    def _read(job):
        """Подписи одного слоя: (номер, текст, широта, долгота, вид)."""
        request = QgsFeatureRequest().setFilterRect(job.rect)
        request.setLimit(layer_labels.MAX_READ)
        context = job.context
        job.expression.prepare(context)
        if job.rule is not None:
            job.rule.prepare(context)
        geometry_kind = job.geometry_kind
        out = []
        for feature in job.source.getFeatures(request):
            context.setFeature(feature)
            if job.rule is not None and not job.rule.evaluate(context):
                continue
            value = job.expression.evaluate(context)
            text = "" if value is None else str(value).strip()
            if not text or text == "NULL":
                continue
            point = _anchor(feature.geometry(), geometry_kind)
            if point is None:
                continue
            try:
                wgs = job.to_wgs.transform(point)
            except QgsCsException:
                # Точка вне области системы координат слоя.
                job.skipped += 1
                continue
            out.append((layer_labels.label_id(job.layer_id, feature.id()),
                        text, wgs.y(), wgs.x(), job.kind_args))
        return layer_labels.nearest(out, job.lat, job.lon)


class LayerLabels(QObject):
    """Подписи отмеченных слоёв проекта для вида глобуса."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.sink = _Result(self)
        self.sink.done.connect(self._done)
        self.generation = 0
        self.marks = []  # надписи core.places.Place для вида
        self._key = None

    def update(self, layer_ids, lat, lon, width, force=False):
        """Перечитать подписи, если сменились слои или окно вида."""
        key = (tuple(layer_ids), layer_labels.key(lat, lon, width))
        if key == self._key and not force:
            return
        self._key = key
        self.generation += 1
        jobs = self._jobs(layer_ids, layer_labels.window(lat, lon, width),
                          (lat, lon))
        if not jobs:
            if self.marks:
                self.marks = []
                self.changed.emit()
            return
        self.pool.start(_ReadTask(self.generation, jobs, self.sink))

    def clear(self):
        self.generation += 1
        self._key = None
        if self.marks:
            self.marks = []
            self.changed.emit()

    def _jobs(self, layer_ids, box, center):
        project = QgsProject.instance()
        wgs = QgsCoordinateReferenceSystem(WGS84)
        jobs = []
        for layer_id in layer_ids:
            layer = project.mapLayer(layer_id)
            if not isinstance(layer, QgsVectorLayer) or not layer.isValid():
                continue
            pairs = _settings(layer)
            if not pairs:
                continue
            context = project.transformContext()
            to_layer = QgsCoordinateTransform(wgs, layer.crs(), context)
            try:
                rect = to_layer.transformBoundingBox(QgsRectangle(*box))
            except QgsCsException:
                rect = layer.extent()
            to_wgs = QgsCoordinateTransform(layer.crs(), wgs, context)
            for settings, rule in pairs:
                jobs.append(_Job(layer, settings, rule, rect, to_wgs,
                                 center))
        return jobs

    def _done(self, generation, found):
        if generation != self.generation:
            return  # ответ на прежний вид или прежний набор слоёв
        self.marks = [Place(label_id, text, layer_style(*kind_args), 1,
                            lat, lon)
                      for label_id, text, lat, lon, kind_args in found]
        self.changed.emit()

    def close(self):
        self.generation += 1
        self.pool.clear()
        self.pool.waitForDone(2000)
