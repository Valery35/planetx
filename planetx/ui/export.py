# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Видимое на глобусе - слоем GeoPackage в проект QGIS.

Решение автора от 11 октября 2026 года - слои витрины уходят в проект
по команде, пункт «В проект QGIS…» строки раздела «На глобусе». Берётся
рамка вида (core.sync.view_box). Точки (месторождения, электростанции,
шахты, очаги, пожары) пишутся через OGR с полями записи, цветом и
размером точки глобуса, стиль слоя - цвет и размер из полей. Слои QGIS
в памяти или в файле (плиты, контуры, ЛЭП) пишет QgsVectorFileWriter
по рамке, стиль копируется. Слои ложатся в группу «PlanetX - слои
глобуса» вверху дерева.
"""
import os

from qgis.core import (QgsCoordinateTransformContext, QgsMarkerSymbol,
                       QgsProject, QgsProperty, QgsRectangle,
                       QgsSingleSymbolRenderer, QgsSymbolLayer,
                       QgsVectorFileWriter, QgsVectorLayer)

from ..core.sync import inside
from ..i18n import tr

__all__ = ("inside", "write_points", "write_layer", "add_points",
           "add_styled")

PIXEL_MM = 0.26  # мм на логический пиксель точки глобуса


def _property(name):
    """Свойство символа по имени - областное в QGIS 4, плоское в 3."""
    scope = getattr(QgsSymbolLayer, "Property", None)
    if scope is not None:
        return getattr(scope, name)
    return getattr(QgsSymbolLayer, "Property" + name)


def write_points(path, name, lats, lons, colors, sizes, fields, rows):
    """Точки слоем name файла GeoPackage path. colors - (n, 3) 0..255,
    sizes - логические пиксели, fields - [(имя, «str» или «real»)],
    rows - значения полей по точкам. Возвращает количество или None."""
    from osgeo import ogr, osr
    driver = ogr.GetDriverByName("GPKG")
    data = ogr.Open(path, 1) if os.path.exists(path) \
        else driver.CreateDataSource(path)
    if data is None:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layer = data.CreateLayer(name, srs, ogr.wkbPoint,
                             ["OVERWRITE=YES"])
    if layer is None:
        return None
    kinds = {"str": ogr.OFTString, "real": ogr.OFTReal}
    for field, kind in fields + [("color", "str"), ("size", "real")]:
        layer.CreateField(ogr.FieldDefn(field, kinds[kind]))
    layer.StartTransaction()
    count = 0
    for n, row in enumerate(rows):
        feature = ogr.Feature(layer.GetLayerDefn())
        for (field, kind), value in zip(fields, row):
            if value not in (None, ""):
                feature.SetField(field, float(value) if kind == "real"
                                 else str(value))
        r, g, b = (int(c) for c in colors[n][:3])
        feature.SetField("color", "#{:02x}{:02x}{:02x}".format(r, g, b))
        feature.SetField("size", float(sizes[n]) * PIXEL_MM)
        point = ogr.Geometry(ogr.wkbPoint)
        point.AddPoint_2D(float(lons[n]), float(lats[n]))
        feature.SetGeometry(point)
        layer.CreateFeature(feature)
        count += 1
    layer.CommitTransaction()
    data = None
    return count


def write_layer(path, name, layer, box, first):
    """Объекты слоя QGIS layer в рамке box слоем name файла path.
    first - файл создаётся заново. Возвращает количество или None."""
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.layerName = name
    options.filterExtent = QgsRectangle(box[0], box[1], box[2], box[3])
    if not first:
        options.actionOnExistingFile = \
            QgsVectorFileWriter.ActionOnExistingFile.CreateOrOverwriteLayer \
            if hasattr(QgsVectorFileWriter, "ActionOnExistingFile") \
            else QgsVectorFileWriter.CreateOrOverwriteLayer
    result = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, QgsCoordinateTransformContext(), options)
    if result[0] != _no_error():
        return None
    written = QgsVectorLayer("{}|layername={}".format(path, name), name,
                             "ogr")
    return written.featureCount() if written.isValid() else None


def _no_error():
    scope = getattr(QgsVectorFileWriter, "WriterError", None)
    if scope is not None:
        return scope.NoError
    return QgsVectorFileWriter.NoError


def add_points(path, name, title):
    """Слой точек файла в проект: цвет и размер - поля color и size."""
    layer = QgsVectorLayer("{}|layername={}".format(path, name), title,
                           "ogr")
    if not layer.isValid():
        return None
    symbol = QgsMarkerSymbol.createSimple({
        "name": "circle", "outline_color": "40,40,40,255",
        "outline_width": "0.2"})
    marker = symbol.symbolLayer(0)
    marker.setDataDefinedProperty(_property("FillColor"),
                                  QgsProperty.fromField("color"))
    marker.setDataDefinedProperty(_property("Size"),
                                  QgsProperty.fromField("size"))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return _to_group(layer)


def add_styled(path, name, title, source):
    """Слой файла в проект со стилем слоя source."""
    layer = QgsVectorLayer("{}|layername={}".format(path, name), title,
                           "ogr")
    if not layer.isValid():
        return None
    layer.setRenderer(source.renderer().clone())
    layer.setOpacity(source.opacity())
    return _to_group(layer)


def _to_group(layer):
    project = QgsProject.instance()
    title = tr("PlanetX - слои глобуса")
    root = project.layerTreeRoot()
    group = root.findGroup(title)
    if group is None:
        group = root.insertGroup(0, title)
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    return layer
