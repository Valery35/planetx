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

import uuid

import numpy as np
from qgis.core import (QgsColorRampShader, QgsCoordinateTransformContext,
                       QgsMarkerSymbol, QgsProject, QgsProperty,
                       QgsRasterLayer, QgsRasterShader, QgsRectangle,
                       QgsSingleBandPseudoColorRenderer,
                       QgsSingleSymbolRenderer, QgsSymbolLayer,
                       QgsVectorFileWriter, QgsVectorLayer)
from qgis.PyQt.QtGui import QColor

from ..core.sync import inside
from ..i18n import tr
from .project import COPY_PROPERTY, is_copy

__all__ = ("inside", "write_points", "write_layer", "add_points",
           "add_styled", "write_grid", "write_picture", "add_raster",
           "add_xyz")
NODATA = -9999.0

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


def write_grid(path, bands, west, north, step, box):
    """Сетку значений (строки с севера на юг, центр левого верхнего узла
    west, north, шаг step) в рамке box - GeoTIFF float32 EPSG:4326, полосы
    bands по порядку. Рамка через линию перемены дат берётся целиком по
    долготе. Возвращает количество узлов или None."""
    from osgeo import gdal, osr
    first = np.asarray(bands[0])
    rows, cols = first.shape
    b_west, south, b_east, b_north = box
    r0 = max(0, int(np.floor((north - b_north) / step)))
    r1 = min(rows, int(np.ceil((north - south) / step)) + 1)
    if b_west <= b_east:
        c0 = max(0, int(np.floor((b_west - west) / step)))
        c1 = min(cols, int(np.ceil((b_east - west) / step)) + 1)
    else:
        c0, c1 = 0, cols
    if r1 <= r0 or c1 <= c0:
        return None
    driver = gdal.GetDriverByName("GTiff")
    data = driver.Create(path, c1 - c0, r1 - r0, len(bands),
                         gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    data.SetGeoTransform((west + (c0 - 0.5) * step, step, 0.0,
                          north - (r0 - 0.5) * step, 0.0, -step))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    data.SetProjection(srs.ExportToWkt())
    for n, band in enumerate(bands):
        values = np.asarray(band, dtype=np.float32)[r0:r1, c0:c1]
        out = data.GetRasterBand(n + 1)
        out.WriteArray(np.where(np.isfinite(values), values, NODATA))
        out.SetNoDataValue(NODATA)
    data = None
    return (r1 - r0) * (c1 - c0)


def write_picture(path, data, box):
    """Картинку (байты PNG или JPEG) рамки box - GeoTIFF EPSG:4326.
    Истина - записан."""
    from osgeo import gdal
    source = "/vsimem/planetx_picture_{}".format(uuid.uuid4().hex)
    gdal.FileFromMemBuffer(source, bytes(data))
    try:
        west, south, east, north = box
        result = gdal.Translate(path, source, format="GTiff",
                                outputSRS="EPSG:4326",
                                outputBounds=[west, north, east, south],
                                creationOptions=["COMPRESS=DEFLATE"])
        ok = result is not None
        result = None
        return ok
    finally:
        gdal.Unlink(source)


def add_raster(path, title, stops=None, rights="", group=None, copy=None):
    """Растр файла в проект: stops - [(значение, (R, G, B[, A]))] -
    раскраска первой полосы, иначе как есть. rights - строка прав,
    group - название группы, без него «PlanetX - слои глобуса». copy -
    растр копирует слой глобуса, без него - когда группы нет (_to_group)."""
    layer = QgsRasterLayer(path, title, "gdal")
    if not layer.isValid():
        return None
    if stops:
        shader = QgsColorRampShader()
        shader.setColorRampType(_ramp_type())
        shader.setColorRampItemList([
            QgsColorRampShader.ColorRampItem(float(v), QColor(*c[:3]),
                                             "{:g}".format(v))
            for v, c in stops])
        raster = QgsRasterShader()
        raster.setRasterShaderFunction(shader)
        layer.setRenderer(QgsSingleBandPseudoColorRenderer(
            layer.dataProvider(), 1, raster))
    if rights:
        meta = layer.metadata()
        meta.setRights([rights])
        layer.setMetadata(meta)
    return _to_group(layer, group, copy)


def add_xyz(url, title, max_level, rights="", group=None):
    """Слой тайлов XYZ по шаблону url в проект, группа - как у
    add_raster. Без файла, тайлы читает QGIS."""
    uri = "type=xyz&url={}&zmin=0&zmax={}".format(
        url.replace("&", "%26"), int(max_level))
    layer = QgsRasterLayer(uri, title, "wms")
    if not layer.isValid():
        return None
    if rights:
        meta = layer.metadata()
        meta.setRights([rights])
        layer.setMetadata(meta)
    return _to_group(layer, group)


def add_wms(service, name, title, rights="", group=None):
    """Слой WMS service (слой name) в проект, EPSG:3857, PNG, группа -
    как у add_raster. Без файла, картинки рисует QGIS."""
    uri = "crs=EPSG:3857&format=image/png&layers={}&styles=&url={}".format(
        name, service)
    layer = QgsRasterLayer(uri, title, "wms")
    if not layer.isValid():
        return None
    if rights:
        meta = layer.metadata()
        meta.setRights([rights])
        layer.setMetadata(meta)
    return _to_group(layer, group)


def _ramp_type():
    scope = getattr(QgsColorRampShader, "Type", None)
    if scope is not None:
        return scope.Interpolated
    return QgsColorRampShader.Interpolated


def _to_group(layer, title=None, copy=None):
    """Слой в группу title. Без группы - группа «PlanetX - слои глобуса»,
    слой - копия слоя глобуса (project.COPY_PROPERTY): глобус его сам не
    показывает, а прежняя копия с тем же названием в группе заменяется,
    повторная выгрузка не копит одинаковые слои."""
    project = QgsProject.instance()
    if copy is None:
        copy = title is None
    title = title or tr("PlanetX - слои глобуса")
    root = project.layerTreeRoot()
    group = root.findGroup(title)
    if group is None:
        group = root.insertGroup(0, title)
    if copy:
        layer.setCustomProperty(COPY_PROPERTY, True)
        old = [node.layerId() for node in group.findLayers()
               if node.layer() is not None and is_copy(node.layer())
               and node.layer().name() == layer.name()]
        if old:
            project.removeMapLayers(old)
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    return layer
