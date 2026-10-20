# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Векторный слой проекта в «Мои метки» - дерево core.kml.

Просьба автора от 20 октября 2026 года - модуль в QGIS остаётся
площадкой подготовки данных, лёгкое приложение без QGIS берёт KML.
Пункт «В «Мои метки»…» меню слоя в разделе «Проект QGIS» кладёт слой
папкой с его именем, дальше «Сохранить как KML…» даёт полный файл.

- Геометрия - в градусах EPSG:4326, кривые разбиваются на отрезки,
  составной объект - метками по частям с одним названием,
  многоугольник - с дырами. Отметки Z не переносятся, метки лежат
  на поверхности.
- Атрибуты - поля объекта (ExtendedData KML), пустое значение -
  пустая строка.
- Название - подпись слоя QGIS (поле или выражение простых подписей),
  без неё - выражение отображения слоя.
- Цвета - символ каждого объекта по стилю слоя, так переносятся
  правила и градуированные стили: цвет точки, цвет и толщина линии,
  заливка и контур многоугольника.
- Подпись точки - цвет и размер шрифта простых подписей QGIS
  (LabelStyle). У точечного слоя без подписей подписи на глобусе нет,
  название остаётся в списке.
- Время - поля начала и конца временных свойств слоя (TimeStamp,
  TimeSpan).
"""
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsExpression, QgsExpressionContext,
                       QgsExpressionContextUtils, QgsFeatureRequest,
                       QgsGeometry, QgsProject, QgsRenderContext,
                       QgsVectorLayerSimpleLabeling, QgsWkbTypes)

from ..core import when
from ..core.kml import KFolder, KPlace
from ..qt_compat import enum_int
from .myplaces import DEFAULT_FILL
from .track import seconds

# Логических пикселей на миллиметр экрана, 96 точек на дюйм.
PIXELS_PER_MM = 96.0 / 25.4
# Кегль подписи метки на глобусе, пикселей (render.labels, класс «mark»).
LABEL_PIXELS = 12.0
# Объектов слоя, после которых окно спрашивает, брать ли только
# видимую часть.
FEATURE_LIMIT = 5000


def _rgba(color):
    return (color.red(), color.green(), color.blue(), color.alpha())


def _pixels(context, size, unit):
    """Размер символа или шрифта в логических пикселях."""
    try:
        return float(context.convertToPainterUnits(size, unit))
    except (TypeError, ValueError):
        return float(size) * PIXELS_PER_MM


class _Look:
    """Цвета и подписи объектов слоя по его стилю."""

    def __init__(self, layer):
        self.layer = layer
        self.context = QgsRenderContext()
        self.context.setScaleFactor(PIXELS_PER_MM)
        self.context.setExpressionContext(QgsExpressionContext(
            QgsExpressionContextUtils.globalProjectLayerScopes(layer)))
        self.renderer = layer.renderer().clone() \
            if layer.renderer() is not None else None
        if self.renderer is not None:
            self.renderer.startRender(self.context, layer.fields())
        self.label = None  # выражение подписи
        self.label_color = None
        self.label_scale = 1.0
        labeling = layer.labeling()
        if layer.labelsEnabled() \
                and isinstance(labeling, QgsVectorLayerSimpleLabeling):
            settings = labeling.settings()
            text = settings.fieldName
            if text:
                self.label = QgsExpression(
                    text if settings.isExpression
                    else QgsExpression.quotedColumnRef(text))
            fmt = settings.format()
            self.label_color = _rgba(fmt.color())
            self.label_scale = round(_pixels(
                self.context, fmt.size(), fmt.sizeUnit()) / LABEL_PIXELS, 2)
        self.labelled = self.label is not None
        if self.label is None:
            self.label = QgsExpression(layer.displayExpression() or "$id")
        self.label.prepare(self.context.expressionContext())

    def close(self):
        if self.renderer is not None:
            self.renderer.stopRender(self.context)

    def name(self, feature):
        self.context.expressionContext().setFeature(feature)
        value = self.label.evaluate(self.context.expressionContext())
        return "" if value is None or str(value) == "NULL" else str(value)

    def colors(self, feature, kind):
        """(цвет, толщина, заливка) объекта по символу стиля."""
        color, width, fill = (255, 214, 0, 255), 2.0, None
        if kind == "polygon":
            color, fill = (255, 255, 255, 255), DEFAULT_FILL
        if self.renderer is None:
            return color, width, fill
        self.context.expressionContext().setFeature(feature)
        symbol = self.renderer.symbolForFeature(feature, self.context)
        if symbol is None:
            return color, width, fill
        main = _rgba(symbol.color())
        if kind == "point":
            return main, width, None
        if kind == "line":
            size = symbol.width() if hasattr(symbol, "width") else 0.0
            if size:
                width = max(1.0, _pixels(self.context, size,
                                         symbol.outputUnit()))
            return main, width, None
        fill = main
        first = symbol.symbolLayer(0) if symbol.symbolLayerCount() else None
        if first is not None and hasattr(first, "strokeColor"):
            color = _rgba(first.strokeColor())
            stroke = first.strokeWidth() if hasattr(first, "strokeWidth") \
                else 0.0
            if stroke:
                width = max(1.0, _pixels(self.context, stroke,
                                         first.strokeWidthUnit()))
        return color, width, fill


def _time(layer, feature):
    """Время объекта по временным свойствам слоя: пара строк core.when
    или None."""
    props = layer.temporalProperties()
    if props is None or not props.isActive() \
            or not hasattr(props, "startField"):
        return None
    names = layer.fields().names()
    start = props.startField() if props.startField() in names else ""
    end = props.endField() if props.endField() in names else ""
    begin = seconds(feature[start]) if start else None
    finish = seconds(feature[end]) if end else None
    if begin is None and finish is None:
        return None
    text_begin = when.text(begin) if begin is not None else ""
    text_end = when.text(finish) if finish is not None else ""
    if not end:
        text_end = text_begin
    return (text_begin, text_end)


def _value(value):
    if value is None or str(value) == "NULL":
        return ""
    if hasattr(value, "toString") and not isinstance(value, str):
        return value.toString()
    return str(value)


def _parts(geometry):
    """Части геометрии: (вид, вершины, дыры) в градусах."""
    if QgsWkbTypes.isCurvedType(geometry.wkbType()):
        geometry = QgsGeometry(geometry.constGet().segmentize())
    parts = geometry.asGeometryCollection() if geometry.isMultipart() \
        else [geometry]
    out = []
    for part in parts:
        kind = enum_int(part.type())
        if kind == 0:
            p = part.asPoint()
            out.append(("point", [(p.y(), p.x())], None))
        elif kind == 1:
            line = [(p.y(), p.x()) for p in part.asPolyline()]
            if len(line) >= 2:
                out.append(("line", line, None))
        elif kind == 2:
            rings = []
            for ring in part.asPolygon():
                points = [(p.y(), p.x()) for p in ring]
                if len(points) > 1 and points[0] == points[-1]:
                    points = points[:-1]
                rings.append(points)
            if rings and len(rings[0]) >= 3:
                holes = tuple(r for r in rings[1:] if len(r) >= 3) or None
                out.append(("polygon", rings[0], holes))
    return out


def layer_tree(layer, ids=None, rect=None):
    """Слой проекта деревом core.kml: (папка, объектов, вершин).

    ids - номера объектов (выделенные), rect - рамка в системе слоя,
    None - все объекты."""
    request = QgsFeatureRequest()
    if ids is not None:
        request.setFilterFids(list(ids))
    elif rect is not None:
        request.setFilterRect(rect)
    transform = QgsCoordinateTransform(
        layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance())
    look = _Look(layer)
    names = layer.fields().names()
    children = []
    count = vertices = 0
    try:
        for feature in layer.getFeatures(request):
            geometry = feature.geometry()
            if geometry is None or geometry.isEmpty():
                continue
            geometry = QgsGeometry(geometry)
            geometry.transform(transform)
            parts = _parts(geometry)
            if not parts:
                continue
            count += 1
            name = look.name(feature)
            data = [(n, _value(feature[n])) for n in names]
            time = _time(layer, feature)
            for kind, points, holes in parts:
                color, width, fill = look.colors(feature, kind)
                vertices += len(points) + sum(len(h) for h in holes or ())
                children.append(KPlace(
                    name, kind, points, color=color, width=width, fill=fill,
                    time=time, holes=holes, data=data or None,
                    label_color=look.label_color if kind == "point"
                    else None,
                    label_scale=(look.label_scale if look.labelled else 0.0)
                    if kind == "point" else 1.0))
    finally:
        look.close()
    return KFolder(layer.name(), True, children), count, vertices
