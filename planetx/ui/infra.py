# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""ЛЭП, подстанции и трубопроводы OSM слоями QGIS в памяти.

Слои не входят в проект, их рисует наложение глобуса, как границы плит
(net.overlay.plate_layer). Линии - стиль по классу напряжения или
вещества (core.infra), подстанции - квадраты цвета класса напряжения.
"""
import math

from qgis.core import (QgsCategorizedSymbolRenderer, QgsFeature,
                       QgsFeatureRequest, QgsGeometry, QgsLineSymbol,
                       QgsMarkerSymbol, QgsPointXY, QgsRectangle,
                       QgsRendererCategory, QgsVectorLayer)

from ..core import infra
from ..i18n import tr
from .legend import infra_names

FIELDS = ("&field=kind:string(12)&field=style:string(8)"
          "&field=name:string(200)&field=operator:string(200)"
          "&field=voltage:double&field=substance:string(40)"
          "&field=location:string(40)&field=osm:string(40)")
SUBSTATION_SIZE = 7.0  # пиксели картинки тайла, выбор помощника
METRES_PER_DEGREE = 111320.0


def _rgb(color):
    return ",".join(str(c) for c in color) + ",255"


def infra_layers(items):
    """Слои линий и подстанций по объектам core.infra.parse."""
    lines = QgsVectorLayer("LineString?crs=EPSG:4326" + FIELDS,
                           "PlanetX power lines", "memory")
    points = QgsVectorLayer("Point?crs=EPSG:4326" + FIELDS,
                            "PlanetX substations", "memory")
    line_features, point_features = [], []
    for item in items:
        layer = points if item["kind"] == "substation" else lines
        feature = QgsFeature(layer.fields())
        if item["kind"] == "substation":
            lat, lon = item["points"][0]
            feature.setGeometry(QgsGeometry.fromPointXY(QgsPointXY(lon,
                                                                   lat)))
            point_features.append(feature)
        else:
            feature.setGeometry(QgsGeometry.fromPolylineXY(
                [QgsPointXY(lo, la) for la, lo in item["points"]]))
            line_features.append(feature)
        feature.setAttributes([item["kind"], item["style"], item["name"],
                               item["operator"], item["voltage"],
                               item["substance"], item["location"],
                               item["osm"]])
    lines.dataProvider().addFeatures(line_features)
    points.dataProvider().addFeatures(point_features)
    names = infra_names()
    categories = []
    for key, _, color, width in infra.VOLTAGES:
        symbol = QgsLineSymbol.createSimple({
            "color": _rgb(color), "width": str(width),
            "width_unit": "Pixel", "capstyle": "round"})
        categories.append(QgsRendererCategory(key, symbol, names[key]))
    for key, color, width in infra.CABLES:
        symbol = QgsLineSymbol.createSimple({
            "color": _rgb(color), "width": str(width),
            "width_unit": "Pixel", "use_custom_dash": "1",
            "customdash": "2;2", "customdash_unit": "Pixel"})
        categories.append(QgsRendererCategory(key, symbol, names[key]))
    for key, _, color in infra.SUBSTANCES:
        symbol = QgsLineSymbol.createSimple({
            "color": _rgb(color), "width": str(infra.PIPE_WIDTH),
            "width_unit": "Pixel", "use_custom_dash": "1",
            "customdash": "6;2", "customdash_unit": "Pixel"})
        categories.append(QgsRendererCategory(key, symbol, names[key]))
    lines.setRenderer(QgsCategorizedSymbolRenderer("style", categories))
    categories = []
    for key, _, color, _ in infra.VOLTAGES:
        symbol = QgsMarkerSymbol.createSimple({
            "name": "square", "color": _rgb(color),
            "outline_color": "40,40,40,255", "size": str(SUBSTATION_SIZE),
            "size_unit": "Pixel"})
        categories.append(QgsRendererCategory(key, symbol, names[key]))
    points.setRenderer(QgsCategorizedSymbolRenderer("style", categories))
    return lines, points


def _nearest(layer, lat, lon, tolerance):
    """Ближайший объект слоя в пределах tolerance метров."""
    dlat = tolerance / METRES_PER_DEGREE
    dlon = dlat / max(math.cos(math.radians(lat)), 0.01)
    rect = QgsRectangle(lon - dlon, lat - dlat, lon + dlon, lat + dlat)
    point = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
    best, best_gap = None, None
    for feature in layer.getFeatures(QgsFeatureRequest(rect)):
        geometry = feature.geometry()
        nearest = geometry.nearestPoint(point).asPoint()
        gap = math.hypot((nearest.x() - lon) * dlat / dlon,
                         nearest.y() - lat) * METRES_PER_DEGREE
        if gap <= tolerance and (best_gap is None or gap < best_gap):
            best, best_gap = feature, gap
    return best


def nearest_infra(lines, points, lat, lon, tolerance):
    """Подстанция или линия у точки щелчка: (название, [(поле,
    значение)]) или None. Подстанция ищется в двойном допуске - её
    квадрат крупнее линии."""
    feature = _nearest(points, lat, lon, 2.0 * tolerance) \
        or _nearest(lines, lat, lon, tolerance)
    if feature is None:
        return None
    names = infra_names()
    kind = feature["kind"]
    kinds = {"line": tr("ЛЭП"), "pipe": tr("Трубопровод"),
             "substation": tr("Подстанция"), "cable": tr("Силовой кабель"),
             "telecom": tr("Линия связи")}
    values = [(tr("Вид"), kinds.get(kind, kind)),
              (tr("Класс"), names.get(feature["style"], feature["style"]))]
    voltage = feature["voltage"]
    if isinstance(voltage, (int, float)) and voltage == voltage:
        values.append((tr("Напряжение"), tr("{value} кВ", value="{:g}".format(
            float(voltage)))))
    if feature["substance"]:
        values.append((tr("Вещество"), feature["substance"]))
    if feature["location"]:
        values.append((tr("Прокладка"), feature["location"]))
    if feature["operator"]:
        values.append((tr("Владелец"), feature["operator"]))
    values.append((tr("Объект OSM"), "https://www.openstreetmap.org/"
                   + feature["osm"]))
    return feature["name"], values
