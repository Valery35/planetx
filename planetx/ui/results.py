# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Результаты инструментов слоями проекта QGIS.

Решение автора от 28 октября 2026 года для видимости, инсоляции,
затопления, уклона и экспозиции участка, изменений местности
и классификации. «Построить» показывает результат на глобусе
предпросмотром, «OK» записывает его растром GeoTIFF в проект QGIS
и закрывает окно, «Отмена» и крестик убирают предпросмотр. Дальше
результат - обычный слой проекта, глобус показывает его как слой
проекта, прячется и удаляется он в QGIS. Файл - в папке проекта, если
проект сохранён, иначе в папке PlanetX профиля, имя - инструмент
и время, повторный «OK» даёт новый слой.

Решение автора от 28 октября 2026 года, по образцу Google Earth: каждый
расчёт - подгруппа «<инструмент> <время>» в группе «PlanetX - анализ
участка», в ней слой контура участка и все слои расчёта. Удаление
подгруппы убирает расчёт целиком (Session).
"""
import os
import time

import numpy as np
from qgis.core import QgsApplication, QgsProject
from qgis.PyQt import sip
from qgis.PyQt.QtWidgets import QDialogButtonBox

from ..i18n import tr
from ..qt_compat import enum

FOLDER = "results"  # папка файлов в папке PlanetX профиля
NODATA = -9999.0
AREA_COLOR = (255, 255, 255)  # контур участка в проекте
AREA_FILL = (255, 255, 255, 0)


def root_name():
    """Общая группа результатов анализа участка."""
    return tr("PlanetX - анализ участка")


def begin_group(window, title, ring):
    """Подгруппа «title ЧЧ:ММ:СС» вверху группы «PlanetX - анализ
    участка» со слоем контура участка ring (широта, долгота), контур
    отмечен на глобусе. Возвращает узел подгруппы."""
    root = QgsProject.instance().layerTreeRoot()
    top = root.findGroup(root_name())
    if top is None:
        top = root.insertGroup(0, root_name())
    group = top.insertGroup(0, "{} {}".format(title,
                                              time.strftime("%H:%M:%S")))
    if ring and len(ring) >= 3:
        path = result_path("area", ".gpkg")
        if write_vector(path, "area", "polygon", [(list(ring), {})], []):
            add_vector(window, path, "area", tr("Участок"), group,
                       AREA_COLOR, width=0.6, fill=AREA_FILL)
    return group


class Session:
    """Подгруппа одного расчёта окна: заводится первым слоем результата
    и служит, пока участок прежний. reset - окно закрыто, следующий
    результат - новая подгруппа."""

    def __init__(self, window, title):
        self.window = window
        self.title = title
        self.group = None
        self.ring = None

    def group_for(self, ring):
        """Подгруппа для участка ring: прежняя, если участок тот же и её
        не удалили, иначе новая."""
        ring = [tuple(p) for p in ring] if ring else []
        group = self.group
        if group is None or sip.isdeleted(group) or ring != self.ring \
                or group.parent() is None:
            self.group = begin_group(self.window, self.title, ring)
            self.ring = ring
        return self.group

    def reset(self):
        self.group = None
        self.ring = None


def result_path(stem, ext=".tif"):
    """Путь нового файла результата stem: папка проекта или профиля,
    имя со временем."""
    folder = QgsProject.instance().homePath()
    if not folder or not os.path.isdir(folder):
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX", FOLDER)
    os.makedirs(folder, exist_ok=True)
    name = "{}_{}".format(stem, time.strftime("%Y%m%d_%H%M%S"))
    path = os.path.join(folder, name + ext)
    number = 2
    while os.path.exists(path):
        path = os.path.join(folder, "{}_{}{}".format(name, number, ext))
        number += 1
    return path


def keep_buttons(dialog, buttons):
    """Кнопки OK и «Отмена» окна инструмента: OK - accept, «Отмена»
    и крестик - reject. Возвращает кнопку OK, она доступна, когда
    есть что записать."""
    ok = buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Ok"))
    ok.setToolTip(tr(
        "Записать результат в проект QGIS и закрыть окно. Расчёт "
        "ложится подгруппой группы «PlanetX - анализ участка» вместе "
        "с контуром участка, удаление подгруппы убирает его целиком."))
    cancel = buttons.addButton(enum(QDialogButtonBox, "StandardButton",
                                    "Cancel"))
    cancel.setToolTip(tr("Убрать результат с глобуса и закрыть окно."))
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    ok.setEnabled(False)
    return ok


def accepted(result):
    """Окно закрыто кнопкой OK: result - код сигнала finished, у
    QDialog Accepted - 1 в Qt 5 и Qt 6."""
    return int(result) == 1


def write_lat_lon(path, values, north, west, dlat, dlon, byte=False):
    """Сетку values (строки с севера, центр левого верхнего узла north,
    west, шаги dlat, dlon градусов) в GeoTIFF EPSG:4326. byte - целые
    0-254, 255 - нет данных, иначе float32 с NODATA. True - записано."""
    from osgeo import gdal, osr
    from .inset import warm
    warm()
    values = np.asarray(values)
    rows, cols = values.shape
    kind = gdal.GDT_Byte if byte else gdal.GDT_Float32
    data = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, kind, ["COMPRESS=DEFLATE"])
    if data is None:
        return False
    data.SetGeoTransform((west - dlon / 2.0, dlon, 0.0, north + dlat / 2.0,
                          0.0, -dlat))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    data.SetProjection(srs.ExportToWkt())
    band = data.GetRasterBand(1)
    if byte:
        band.SetNoDataValue(255)
        band.WriteArray(values.astype(np.uint8))
    else:
        band.SetNoDataValue(NODATA)
        band.WriteArray(np.where(np.isfinite(values), values,
                                 NODATA).astype(np.float32))
    data = None
    return True


def add_paletted(path, title, group, classes, opacity=1.0):
    """Растр классов в проект в группу group: classes - [(значение,
    (R, G, B), подпись)]."""
    from qgis.core import QgsPalettedRasterRenderer, QgsRasterLayer
    from qgis.PyQt.QtGui import QColor
    from .export import _to_group
    layer = QgsRasterLayer(path, title, "gdal")
    if not layer.isValid():
        return None
    layer.setRenderer(QgsPalettedRasterRenderer(
        layer.dataProvider(), 1,
        [QgsPalettedRasterRenderer.Class(value, QColor(*rgb), name)
         for value, rgb, name in classes]))
    layer.setOpacity(opacity)
    return _to_group(layer, group)


def write_vector(path, name, kind, items, fields):
    """Объекты в слой name файла GeoPackage path, EPSG:4326. kind -
    "point", "line" или "polygon", items - [(точки [(широта, долгота)],
    {поле: значение})], fields - [(имя, "str", "int" или "real")].
    Возвращает количество объектов или None."""
    from osgeo import ogr, osr
    from .inset import warm
    warm()
    driver = ogr.GetDriverByName("GPKG")
    data = ogr.Open(path, 1) if os.path.exists(path) \
        else driver.CreateDataSource(path)
    if data is None:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    types = {"point": ogr.wkbPoint, "line": ogr.wkbLineString,
             "polygon": ogr.wkbPolygon}
    layer = data.CreateLayer(name, srs, types[kind], ["OVERWRITE=YES"])
    if layer is None:
        return None
    kinds = {"str": ogr.OFTString, "int": ogr.OFTInteger,
             "real": ogr.OFTReal}
    for field, field_kind in fields:
        layer.CreateField(ogr.FieldDefn(field, kinds[field_kind]))
    layer.StartTransaction()
    count = 0
    for points, values in items:
        if kind == "point":
            geometry = ogr.Geometry(ogr.wkbPoint)
            geometry.AddPoint_2D(float(points[0][1]), float(points[0][0]))
        else:
            ring = ogr.Geometry(ogr.wkbLinearRing if kind == "polygon"
                                else ogr.wkbLineString)
            for lat, lon in points:
                ring.AddPoint_2D(float(lon), float(lat))
            if kind == "polygon":
                ring.CloseRings()
                geometry = ogr.Geometry(ogr.wkbPolygon)
                geometry.AddGeometry(ring)
            else:
                geometry = ring
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetGeometry(geometry)
        for field, value in values.items():
            if value is not None:
                feature.SetField(field, value)
        layer.CreateFeature(feature)
        count += 1
    layer.CommitTransaction()
    data = None
    return count


def _symbol(layer, color, width=None, fill=None):
    from qgis.core import QgsSymbol
    from qgis.PyQt.QtGui import QColor
    symbol = QgsSymbol.defaultSymbol(layer.geometryType())
    if symbol is None:
        return None
    if fill is not None:
        # Многоугольник - заливка fill и контур color.
        symbol.setColor(QColor(*fill))
        part = symbol.symbolLayer(0)
        if hasattr(part, "setStrokeColor"):
            part.setStrokeColor(QColor(*color[:3]))
            part.setStrokeWidth(width or 0.6)
    else:
        symbol.setColor(QColor(*color[:3]))
        if width is not None and hasattr(symbol, "setWidth"):
            symbol.setWidth(width)
        if hasattr(symbol, "setSize"):
            symbol.setSize(3.0)
    return symbol


def add_vector(window, path, name, title, group, color, width=None,
               fill=None, classes=None):
    """Слой name файла path в проект в группу group, отмечен на глобусе.
    color и width (мм) - линия или точка, fill - заливка многоугольника.
    classes - (поле, [(значение, (R, G, B), подпись)]) - цвета по полю."""
    from qgis.core import (QgsCategorizedSymbolRenderer, QgsRendererCategory,
                           QgsSingleSymbolRenderer, QgsVectorLayer)
    from .export import _to_group
    layer = QgsVectorLayer("{}|layername={}".format(path, name), title,
                           "ogr")
    if not layer.isValid():
        return None
    if classes:
        field, values = classes
        layer.setRenderer(QgsCategorizedSymbolRenderer(field, [
            QgsRendererCategory(value, _symbol(layer, rgb, width), label)
            for value, rgb, label in values]))
    else:
        symbol = _symbol(layer, color, width, fill)
        if symbol is not None:
            layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    return show_layer(window, _to_group(layer, group))


def show_layer(window, layer):
    """Слой результата отмечен на глобусе: глобус показывает его как
    слой проекта."""
    if layer is not None and window is not None:
        window.set_layer_shown(layer.id(), True)
    return layer
