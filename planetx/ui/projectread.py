# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слои проекта QGIS для ИИ-помощника: список слоёв и строки слоя.

Решение автора от 25 октября 2026 года - слои проекта, их поля и строки
уходят в модель только по разрешению пользователя на каждое чтение, как
чтение файлов у помощника RustGIS. Разрешение спрашивает окно
«Помощник» (core.assistant.GATED_TOOLS), здесь - само чтение и подписи
вопроса.
"""
import json

from qgis.core import (QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsExpression,
                       QgsFeatureRequest, QgsProject, QgsRasterLayer,
                       QgsVectorLayer)

from ..core import assistant as ai
from ..i18n import tr

# Полей слоя в списке не больше, знаков значения в строке не больше.
FIELDS_SHOWN = 40
VALUE_CHARS = 200


def row_limit(value, default=50):
    """Предел строк read_features из аргумента модели."""
    try:
        value = int(float(value))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, ai.FEATURE_LIMIT))


def project_layers():
    """Слои проекта в порядке дерева слоёв."""
    root = QgsProject.instance().layerTreeRoot()
    return [node.layer() for node in root.findLayers()
            if node.layer() is not None]


def find_layer(ref):
    """Слой по номеру из list_project_layers (с 1) или по названию."""
    layers = project_layers()
    ref = str(ref).strip()
    if ref.isdigit() and 1 <= int(ref) <= len(layers):
        return layers[int(ref) - 1]
    for layer in layers:
        if layer.name() == ref:
            return layer
    return None


def _kind(layer):
    if isinstance(layer, QgsVectorLayer):
        return "vector"
    return "raster" if isinstance(layer, QgsRasterLayer) else "other"


def layers_text():
    """Ответ list_project_layers: строка JSON на слой."""
    lines = []
    for n, layer in enumerate(project_layers(), 1):
        item = {"layer": n, "name": layer.name(), "kind": _kind(layer),
                "crs": layer.crs().authid()}
        if isinstance(layer, QgsVectorLayer):
            item["features"] = layer.featureCount()
            fields = [f.name() for f in layer.fields()]
            item["fields"] = fields[:FIELDS_SHOWN]
            if len(fields) > FIELDS_SHOWN:
                item["fields_more"] = len(fields) - FIELDS_SHOWN
        lines.append(json.dumps(item, ensure_ascii=False))
    return "\n".join(lines) if lines else tr("В проекте нет слоёв.")


def _value(value):
    if value is None or (hasattr(value, "isNull") and value.isNull()):
        return None
    if isinstance(value, (int, float, bool)):
        return value
    text = str(value)
    return text if len(text) <= VALUE_CHARS else text[:VALUE_CHARS] + "…"


def features_text(layer, where="", fields=None, limit=50, geometry=False):
    """Ответ read_features: строка JSON на объект, не больше
    core.assistant.FEATURE_LIMIT. geometry - точка середины объекта
    в градусах WGS84."""
    if layer is None:
        return tr("Слоя нет. Номер берётся из list_project_layers.")
    if not isinstance(layer, QgsVectorLayer):
        return tr("Слой «{name}» не векторный, строк у него нет.",
                  name=layer.name())
    limit = row_limit(limit)
    request = QgsFeatureRequest()
    if where:
        expression = QgsExpression(str(where))
        if expression.hasParserError():
            return tr("Ошибка в выражении отбора: {error}",
                      error=expression.parserErrorString())
        request.setFilterExpression(str(where))
    request.setLimit(limit + 1)
    names = [f.name() for f in layer.fields()]
    wanted = [str(f) for f in (fields or []) if str(f) in names] or names
    transform = QgsCoordinateTransform(
        layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
        QgsProject.instance())
    lines = []
    for feature in layer.getFeatures(request):
        if len(lines) == limit:
            lines.append(tr("Строк больше {limit}, показаны первые.",
                            limit=limit))
            break
        item = {name: _value(feature[name]) for name in wanted}
        if geometry and feature.hasGeometry():
            point = transform.transform(
                feature.geometry().pointOnSurface().asPoint())
            item["_lat"] = round(point.y(), 6)
            item["_lon"] = round(point.x(), 6)
        lines.append(json.dumps(item, ensure_ascii=False, default=str))
    return "\n".join(lines) if lines else tr("Подходящих строк нет.")


def describe(call, actions=()):
    """Вопрос о разрешении вызова для окна «Помощник». actions -
    действия строки «Поиск», у вызова run_action - его название."""
    args = call.args or {}
    if call.name == "list_project_layers":
        return tr("Помощник просит список слоёв проекта QGIS - названия, "
                  "поля, системы координат и количество объектов.")
    if call.name == "read_features":
        layer = find_layer(args.get("layer", ""))
        name = layer.name() if layer is not None \
            else str(args.get("layer", ""))
        text = tr("Помощник просит прочитать строки слоя «{name}», не "
                  "больше {limit}.", name=name,
                  limit=row_limit(args.get("limit")))
        if args.get("where"):
            text += " " + tr("Отбор: {where}.", where=args["where"])
        if args.get("geometry"):
            text += " " + tr("С координатами объектов.")
        return text
    if call.name == "run_action":
        for item in actions:
            if item.key == str(args.get("key", "")):
                return tr("Помощник просит выполнить «{title}». Откроется "
                          "окно, которое ждёт вашего ответа.",
                          title=item.text)
    return ""
