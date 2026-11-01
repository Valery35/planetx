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
- Подпись точки - текст, цвет и размер шрифта подписи QGIS (LabelStyle),
  простой или по правилам: правило берётся первое подходящее, как
  у QGIS, вложенные и ELSE учитываются. У точки без подписи подписи на
  глобусе нет, название остаётся в списке.
- Подпись с обводкой, подложкой или тенью KML не описывает. Такая точка
  получает значок-картинку PNG (LabelStyle размером 0): символ слоя
  в середине, подпись справа от него, как рисует QGIS. Левая половина
  картинки пустая, поэтому точка метки стоит на символе и без hotSpot.
  Разных картинок на слой не больше PICTURE_LIMIT, дальше - обычная
  подпись. Масштаб видимости подписей не учитывается.
- Время - поля начала и конца временных свойств слоя (TimeStamp,
  TimeSpan).
"""
from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsExpression,
                       QgsExpressionContext, QgsExpressionContextUtils,
                       QgsFeatureRequest, QgsGeometry, QgsProject,
                       QgsRenderContext, QgsRuleBasedLabeling, QgsTextRenderer,
                       QgsVectorLayerSimpleLabeling, QgsWkbTypes)
from qgis.PyQt.QtCore import QBuffer, QByteArray, QPointF, QSize
from qgis.PyQt.QtGui import QImage, QPainter

from ..core import when
from ..core.kml import KFolder, KPlace
from ..qt_compat import enum, enum_int
from .myplaces import DEFAULT_FILL
from .track import seconds

# Логических пикселей на миллиметр экрана, 96 точек на дюйм.
PIXELS_PER_MM = 96.0 / 25.4
# Кегль подписи метки на глобусе, пикселей (render.labels, класс «mark»).
LABEL_PIXELS = 12.0
# Объектов слоя, после которых окно спрашивает, брать ли только
# видимую часть.
FEATURE_LIMIT = 5000
# Разных картинок подписей на слой, дальше - обычная подпись.
PICTURE_LIMIT = 2000
PICTURE_PAD = 10  # поле картинки под обводку и подложку, пикселей
PICTURE_GAP = 3  # от символа до подписи, пикселей
SYMBOL_PIXELS = (6, 48)  # пределы символа точки на картинке, пикселей


def _rgba(color):
    return (color.red(), color.green(), color.blue(), color.alpha())


def _pixels(context, size, unit):
    """Размер символа или шрифта в логических пикселях."""
    try:
        return float(context.convertToPainterUnits(size, unit))
    except (TypeError, ValueError):
        return float(size) * PIXELS_PER_MM


class _Label:
    """Вид подписи: выражение текста, цвет, размер, формат QGIS."""

    def __init__(self, settings, look):
        text = settings.fieldName
        self.expression = None
        if text:
            self.expression = QgsExpression(
                text if settings.isExpression
                else QgsExpression.quotedColumnRef(text))
            self.expression.prepare(look.context.expressionContext())
        self.format = settings.format()
        self.color = _rgba(self.format.color())
        self.scale = round(_pixels(look.context, self.format.size(),
                                   self.format.sizeUnit()) / LABEL_PIXELS, 2)
        # Обводку, подложку и тень KML не описывает.
        self.rich = bool(self.format.buffer().enabled()
                         or self.format.background().enabled()
                         or self.format.shadow().enabled())


def _encode(image):
    """Байты PNG картинки."""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(enum(QBuffer, "OpenModeFlag", "WriteOnly"))
    image.save(buffer, "PNG")
    buffer.close()
    return bytes(data)


def label_picture(text, label, symbol, context):
    """Картинка подписи с символом точки: байты PNG, символ в середине.
    symbol - символ объекта или None."""
    probe = QImage(1, 1, enum(QImage, "Format",
                              "Format_ARGB32_Premultiplied"))
    painter = QPainter(probe)
    render = QgsRenderContext.fromQPainter(painter)
    render.setScaleFactor(PIXELS_PER_MM)
    text_width = QgsTextRenderer.textWidth(render, label.format, [text])
    text_height = QgsTextRenderer.textHeight(render, label.format, [text])
    painter.end()
    side = 0
    mark = None
    if symbol is not None:
        size = _pixels(context, symbol.size(), symbol.sizeUnit()) \
            if hasattr(symbol, "size") else 0.0
        side = int(round(min(max(size, SYMBOL_PIXELS[0]), SYMBOL_PIXELS[1])))
        mark = symbol.asImage(QSize(side, side))
    half = int(side / 2.0 + PICTURE_GAP + text_width + PICTURE_PAD + 1.0)
    height = int(max(text_height, side) + 2 * PICTURE_PAD + 1.0)
    image = QImage(2 * half, height, enum(QImage, "Format",
                                          "Format_ARGB32_Premultiplied"))
    image.fill(0)
    painter = QPainter(image)
    render = QgsRenderContext.fromQPainter(painter)
    render.setScaleFactor(PIXELS_PER_MM)
    render.setFlag(enum(Qgis, "RenderContextFlag", "Antialiasing"), True)
    if mark is not None:
        painter.drawImage(QPointF(half - side / 2.0,
                                  (height - side) / 2.0), mark)
    left = half + side / 2.0 + PICTURE_GAP
    QgsTextRenderer.drawText(
        QPointF(left, (height + text_height) / 2.0), 0.0,
        Qgis.TextHorizontalAlignment.Left, [text], render, label.format)
    painter.end()
    return _encode(image)


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
        self.root = None  # корень правил подписей
        self.simple = None  # простая подпись
        self.rule_labels = {}  # ключ правила - _Label
        self.filters = {}  # ключ правила - выражение отбора
        self.pictures = {}  # (вид, текст, цвет) - байты PNG
        self.plain = 0  # подписей без картинки сверх PICTURE_LIMIT
        labeling = layer.labeling()
        if layer.labelsEnabled():
            if isinstance(labeling, QgsVectorLayerSimpleLabeling):
                self.simple = _Label(labeling.settings(), self)
            elif isinstance(labeling, QgsRuleBasedLabeling):
                self.root = labeling.rootRule()
        self.display = QgsExpression(layer.displayExpression() or "$id")
        self.display.prepare(self.context.expressionContext())

    def _passes(self, rule):
        text = rule.filterExpression()
        if not text:
            return True
        key = rule.ruleKey()
        expression = self.filters.get(key)
        if expression is None:
            expression = self.filters[key] = QgsExpression(text)
            expression.prepare(self.context.expressionContext())
        return bool(expression.evaluate(self.context.expressionContext()))

    def _rule_for(self, parent):
        """Первое подходящее правило с подписью под parent или None."""
        matched = False
        for rule in parent.children():
            if not rule.active():
                continue
            if rule.isElse():
                passes = not matched
            else:
                passes = self._passes(rule)
            if not passes:
                continue
            matched = True
            if rule.settings() is not None:
                return rule
            found = self._rule_for(rule)
            if found is not None:
                return found
        return None

    def label_of(self, feature):
        """Вид подписи объекта (_Label) или None."""
        if self.root is None:
            return self.simple
        self.context.expressionContext().setFeature(feature)
        rule = self._rule_for(self.root)
        if rule is None:
            return None
        key = rule.ruleKey()
        if key not in self.rule_labels:
            self.rule_labels[key] = _Label(rule.settings(), self)
        return self.rule_labels[key]

    def label_text(self, label, feature):
        """Текст подписи объекта, пустая строка - подписи нет."""
        if label is None or label.expression is None:
            return ""
        self.context.expressionContext().setFeature(feature)
        value = label.expression.evaluate(self.context.expressionContext())
        return "" if value is None or str(value) == "NULL" else str(value)

    def picture(self, label, text, feature):
        """Байты PNG подписи с символом объекта, None - сверх предела."""
        self.context.expressionContext().setFeature(feature)
        symbol = self.renderer.symbolForFeature(feature, self.context) \
            if self.renderer is not None else None
        key = (id(label), text, _rgba(symbol.color()) if symbol else None)
        if key not in self.pictures:
            if len(self.pictures) >= PICTURE_LIMIT:
                self.plain += 1
                return None
            self.pictures[key] = label_picture(text, label, symbol,
                                               self.context)
        return self.pictures[key]

    def close(self):
        if self.renderer is not None:
            self.renderer.stopRender(self.context)

    def name(self, feature):
        self.context.expressionContext().setFeature(feature)
        value = self.display.evaluate(self.context.expressionContext())
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
            label = look.label_of(feature)
            text = look.label_text(label, feature)
            name = text or look.name(feature)
            data = [(n, _value(feature[n])) for n in names]
            time = _time(layer, feature)
            for kind, points, holes in parts:
                color, width, fill = look.colors(feature, kind)
                vertices += len(points) + sum(len(h) for h in holes or ())
                picture = None
                label_color, label_scale = None, 1.0
                if kind == "point":
                    if text and label.rich:
                        picture = look.picture(label, text, feature)
                    if picture is not None or not text:
                        label_scale = 0.0
                    else:
                        label_color, label_scale = label.color, label.scale
                children.append(KPlace(
                    name, kind, points, color=color, width=width, fill=fill,
                    time=time, holes=holes, data=data or None,
                    label_color=label_color, label_scale=label_scale,
                    picture=picture))
    finally:
        look.close()
    return KFolder(layer.name(), True, children), count, vertices
