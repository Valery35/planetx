# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""«Мои метки» - сохранённые объекты глобуса, как в Google Earth.

Хранятся в одном файле GeoPackage в папке профиля QGIS и видны в любом
проекте. Решение автора от 27 сентября 2026 года. В файле три слоя
в WGS84: точки, линии, многоугольники. Файл - обычный источник QGIS,
его слои можно добавить в проект.

Запись идёт прямо в источник через dataProvider, без буфера правки.
"""
import os
import time

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
                       QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorFileWriter, QgsVectorLayer)
from qgis.PyQt.QtCore import QObject, pyqtSignal

from ..core.features import Shape
from ..i18n import tr
from ..qt_compat import enum

FILE_NAME = "myplaces.gpkg"
# Слой файла по виду объекта и вид геометрии слоя.
TABLES = {"point": ("points", "Point"), "line": ("lines", "LineString"),
          "polygon": ("polygons", "Polygon")}
FIELDS = (("name", "string"), ("description", "string"),
          ("color", "string"), ("width", "double"), ("fill", "string"),
          ("visible", "integer"), ("measure", "string"),
          ("created", "string"))
# Цвета по умолчанию, как у Google Earth: жёлтая метка и линия, белый
# контур многоугольника с полупрозрачной заливкой.
DEFAULT_COLOR = {"point": (255, 214, 0, 255), "line": (255, 214, 0, 255),
                 "polygon": (255, 255, 255, 255)}
DEFAULT_FILL = (255, 255, 255, 60)
DEFAULT_WIDTH = 2.0


def store_path():
    """Путь к файлу «Моих меток» в профиле QGIS."""
    return os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        FILE_NAME)


def _color(text, default):
    try:
        parts = tuple(int(v) for v in str(text).split(","))
    except ValueError:
        return default
    return parts if len(parts) == 4 else default


def _color_text(color):
    return ",".join(str(int(c)) for c in color) if color else ""


def _points(kind, geometry):
    """Вершины (широта, долгота) геометрии слоя меток."""
    if geometry is None or geometry.isEmpty():
        return []
    if kind == "point":
        p = geometry.asPoint()
        return [(p.y(), p.x())]
    if kind == "line":
        line = geometry.asPolyline() or (geometry.asMultiPolyline()
                                         or [[]])[0]
        return [(p.y(), p.x()) for p in line]
    rings = geometry.asPolygon() or (geometry.asMultiPolygon() or [[[]]])[0]
    ring = rings[0] if rings else []
    if len(ring) > 1 and ring[0] == ring[-1]:
        ring = ring[:-1]
    return [(p.y(), p.x()) for p in ring]


def _geometry(kind, points):
    xy = [QgsPointXY(lon, lat) for lat, lon in points]
    if kind == "point":
        return QgsGeometry.fromPointXY(xy[0])
    if kind == "line":
        return QgsGeometry.fromPolylineXY(xy)
    return QgsGeometry.fromPolygonXY([xy + xy[:1]])


class Place:
    """Метка из файла: ключ (вид, номер объекта), объект и видимость."""

    def __init__(self, kind, fid, shape, visible, measure=""):
        self.kind = kind
        self.fid = fid
        self.shape = shape
        self.visible = visible
        self.measure = measure

    @property
    def key(self):
        return "{}:{}".format(self.kind, self.fid)


class MyPlaces(QObject):
    """Файл «Моих меток» и список меток в памяти."""

    changed = pyqtSignal()

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path or store_path()
        self.places = []
        self.layers = {}

    # Файл.

    def _create(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        fields = "&".join("field={}:{}".format(n, t) for n, t in FIELDS)
        context = QgsProject.instance().transformContext()
        for n, (kind, (table, geometry)) in enumerate(TABLES.items()):
            memory = QgsVectorLayer("{}?crs=EPSG:4326&{}".format(
                geometry, fields), table, "memory")
            options = QgsVectorFileWriter.SaveVectorOptions()
            options.driverName = "GPKG"
            options.layerName = table
            if n:
                options.actionOnExistingFile = enum(
                    QgsVectorFileWriter, "ActionOnExistingFile",
                    "CreateOrOverwriteLayer")
            QgsVectorFileWriter.writeAsVectorFormatV3(memory, self.path,
                                                      context, options)

    def load(self):
        """Открыть файл, создать его при первом запуске, прочитать метки."""
        if not os.path.exists(self.path):
            self._create()
        self.layers = {}
        for kind, (table, _) in TABLES.items():
            layer = QgsVectorLayer("{}|layername={}".format(self.path, table),
                                   table, "ogr")
            if layer.isValid():
                self.layers[kind] = layer
        self._read()

    def _read(self):
        self.places = []
        for kind, layer in self.layers.items():
            for feature in layer.getFeatures():
                points = _points(kind, feature.geometry())
                if not points:
                    continue
                shape = Shape(
                    kind, points,
                    color=_color(feature["color"], DEFAULT_COLOR[kind]),
                    width=float(feature["width"] or DEFAULT_WIDTH),
                    fill=_color(feature["fill"], None) if kind == "polygon"
                    else None,
                    name=str(feature["name"] or ""))
                self.places.append(Place(
                    kind, feature.id(), shape,
                    bool(feature["visible"] if feature["visible"] is not None
                         else 1), str(feature["measure"] or "")))
        self.places.sort(key=lambda p: p.shape.name.lower())
        self.changed.emit()

    # Метки.

    def shapes(self):
        """Видимые метки для глобуса."""
        return [p.shape for p in self.places if p.visible]

    def find(self, key):
        return next((p for p in self.places if p.key == key), None)

    def add(self, shape, measure=""):
        """Записать новую метку. Возвращает её ключ или None."""
        layer = self.layers.get(shape.kind)
        if layer is None or not shape.points:
            return None
        feature = QgsFeature(layer.fields())
        feature.setGeometry(_geometry(shape.kind, shape.points))
        values = {"name": shape.name, "description": "",
                  "color": _color_text(shape.color),
                  "width": float(shape.width),
                  "fill": _color_text(shape.fill), "visible": 1,
                  "measure": measure,
                  "created": time.strftime("%Y-%m-%d %H:%M:%S")}
        for name, value in values.items():
            feature[name] = value
        ok, added = layer.dataProvider().addFeatures([feature])
        self._read()
        return "{}:{}".format(shape.kind, added[0].id()) if ok else None

    def _change(self, key, name, value):
        place = self.find(key)
        if place is None:
            return
        layer = self.layers[place.kind]
        index = layer.fields().indexOf(name)
        layer.dataProvider().changeAttributeValues(
            {place.fid: {index: value}})
        self._read()

    def set_visible(self, key, on):
        self._change(key, "visible", 1 if on else 0)

    def rename(self, key, name):
        self._change(key, "name", name)

    def remove(self, key):
        place = self.find(key)
        if place is None:
            return
        self.layers[place.kind].dataProvider().deleteFeatures([place.fid])
        self._read()

    def add_to_project(self):
        """Добавить слои файла в текущий проект, общий файл тот же."""
        added = []
        names = {"point": tr("Мои метки - точки"),
                 "line": tr("Мои метки - линии"),
                 "polygon": tr("Мои метки - многоугольники")}
        for kind, (table, _) in TABLES.items():
            layer = QgsVectorLayer("{}|layername={}".format(self.path, table),
                                   names[kind], "ogr")
            if layer.isValid():
                layer.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
                QgsProject.instance().addMapLayer(layer)
                added.append(layer)
        return added
