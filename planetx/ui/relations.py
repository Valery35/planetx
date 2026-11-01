# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Связи объекта по отношениям проекта QGIS для карточки объекта.

Своего хранилища связей нет: отношения задаёт проект QGIS (Проект -
Свойства - Отношения), модуль только показывает их у объекта. Дочерние
записи и родитель идут списком, не больше LIMIT на отношение.
"""
from qgis.core import (QgsExpression, QgsExpressionContext,
                       QgsExpressionContextUtils, QgsProject)

LIMIT = 50  # записей на отношение в карточке


def feature_title(layer, feature):
    """Подпись записи по выражению отображения слоя."""
    context = QgsExpressionContext(
        QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    context.setFeature(feature)
    expression = QgsExpression(layer.displayExpression() or "$id")
    value = expression.evaluate(context)
    if value is None or str(value) in ("", "NULL"):
        return "#{}".format(feature.id())
    return str(value)


def related(layer, feature):
    """Связи объекта: [(название отношения, слой, [(номер, подпись)],
    всего записей)]. Сначала дочерние записи, потом родитель."""
    manager = QgsProject.instance().relationManager()
    out = []
    for relation in manager.referencedRelations(layer):
        other = relation.referencingLayer()
        if other is None or not relation.isValid():
            continue
        rows = []
        total = 0
        for item in relation.getRelatedFeatures(feature):
            total += 1
            if len(rows) < LIMIT:
                rows.append((item.id(), feature_title(other, item)))
        if rows:
            out.append((relation.name() or other.name(), other, rows, total))
    for relation in manager.referencingRelations(layer):
        other = relation.referencedLayer()
        if other is None or not relation.isValid():
            continue
        parent = relation.getReferencedFeature(feature)
        if parent.isValid():
            out.append((relation.name() or other.name(), other,
                        [(parent.id(), feature_title(other, parent))], 1))
    return out
