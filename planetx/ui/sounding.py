# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Батиметрия по промерам» и грид глубин через GDAL.

Пункт «Батиметрия по промерам…» меню точечного слоя в «Слоях
проекта». Точки читаются в метрах зоны UTM середины слоя, грид строит
gdal.Grid (linear), маска - gdal.ComputeProximity по растру точек,
расчёт - core/sounding.py. Готовый GeoTIFF глубин окно глобуса кладёт
в проект и делает своей батиметрией (core/bathymetry.py).

GDAL вызывается в главном потоке без UseExceptions: режим исключений
общий для модулей QGIS.
"""
import os

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsFeatureRequest, QgsProject,
                       QgsWkbTypes)
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFileDialog, QFormLayout,
                                 QHBoxLayout, QLabel, QLineEdit, QPushButton,
                                 QVBoxLayout)

from ..core import sounding
from ..core.modis import utm_epsg
from ..i18n import tr
from ..qt_compat import enum

Z_FIELD = ""  # глубина - Z точки, а не поле


def numeric_fields(layer):
    """Имена числовых полей слоя."""
    return [f.name() for f in layer.fields() if f.isNumeric()]


def _number(value):
    """Число или None для пустого и нечислового значения поля."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def read_points(layer, field):
    """Точки слоя: (x, y, глубина) в метрах UTM середины слоя и EPSG
    зоны. field - имя поля глубины или Z_FIELD."""
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    project = QgsProject.instance()
    center = QgsCoordinateTransform(layer.crs(), wgs, project).transform(
        layer.extent().center())
    epsg = utm_epsg([(center.y(), center.x())])
    utm = QgsCoordinateReferenceSystem("EPSG:{}".format(epsg))
    transform = QgsCoordinateTransform(layer.crs(), utm, project)
    request = QgsFeatureRequest()
    if field:
        request.setSubsetOfAttributes([field], layer.fields())
    xs, ys, zs = [], [], []
    for feature in layer.getFeatures(request):
        geometry = feature.geometry()
        if geometry.isNull():
            continue
        value = _number(feature[field]) if field else None
        for vertex in geometry.vertices():
            z = _number(vertex.z()) if not field else value
            try:
                point = transform.transform(vertex.x(), vertex.y())
            except QgsCsException:
                # Точка вне области системы координат - без глубины.
                z = None
            if z is None:
                continue
            xs.append(point.x())
            ys.append(point.y())
            zs.append(z)
    xs, ys, zs = sounding.clean(xs, ys, zs)
    return xs, ys, zs, epsg


def build_grid(xs, ys, zs, epsg, cell, limit, path):
    """GeoTIFF глубин path по точкам UTM. Возвращает количество ячеек
    с глубиной или строку ошибки."""
    from osgeo import gdal, ogr, osr
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(epsg))
    # Набор GDAL, а не OGR - gdal.Grid в GDAL QGIS 3.36 берёт только его.
    source = gdal.GetDriverByName("Memory").Create(
        "soundings", 0, 0, 0, gdal.GDT_Unknown)
    points = source.CreateLayer("soundings", srs, ogr.wkbPoint25D)
    for x, y, z in zip(xs, ys, zs):
        feature = ogr.Feature(points.GetLayerDefn())
        point = ogr.Geometry(ogr.wkbPoint25D)
        point.AddPoint(float(x), float(y), float(z))
        feature.SetGeometry(point)
        points.CreateFeature(feature)
    (west, south, east, north), (cols, rows) = sounding.grid_frame(
        xs, ys, cell)
    grid = gdal.Grid("", source, format="MEM", width=cols, height=rows,
                     outputBounds=[west, north, east, south],
                     outputType=gdal.GDT_Float32, outputSRS=srs.ExportToWkt(),
                     algorithm="linear:radius=-1:nodata={}".format(
                         sounding.NODATA))
    if grid is None:
        return gdal.GetLastErrorMsg() or "gdal.Grid"
    depths = grid.GetRasterBand(1).ReadAsArray()
    # Расстояние до ближайшего промера: растр точек и близость к ним.
    mem = gdal.GetDriverByName("MEM")
    hits = mem.Create("", cols, rows, 1, gdal.GDT_Byte)
    hits.SetGeoTransform(grid.GetGeoTransform())
    hits.SetProjection(srs.ExportToWkt())
    gdal.RasterizeLayer(hits, [1], points, burn_values=[1])
    near = mem.Create("", cols, rows, 1, gdal.GDT_Float32)
    near.SetGeoTransform(grid.GetGeoTransform())
    near.SetProjection(srs.ExportToWkt())
    gdal.ComputeProximity(hits.GetRasterBand(1), near.GetRasterBand(1),
                          ["VALUES=1", "DISTUNITS=GEO",
                           "MAXDIST={}".format(float(limit) * 2.0),
                           "NODATA=-1"])
    distance = near.GetRasterBand(1).ReadAsArray().astype(np.float64)
    distance[distance < 0.0] = np.inf
    out = sounding.masked(depths, distance, float(limit))
    tiff = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, gdal.GDT_Float32,
        ["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"])
    if tiff is None:
        return gdal.GetLastErrorMsg() or path
    tiff.SetGeoTransform(grid.GetGeoTransform())
    tiff.SetProjection(srs.ExportToWkt())
    band = tiff.GetRasterBand(1)
    band.SetNoDataValue(sounding.NODATA)
    band.WriteArray(out)
    tiff.FlushCache()
    tiff = grid = hits = near = source = None
    return int((out != sounding.NODATA).sum())


class SoundingDialog(QDialog):
    """Окно настроек грида по промерам слоя layer. level - уровень воды
    по умолчанию, path - файл по умолчанию."""

    def __init__(self, layer, level, path, parent=None):
        super().__init__(parent)
        self.layer = layer
        self.points = None
        self.setWindowTitle(tr("Батиметрия по промерам"))
        about = QLabel(tr(
            "Точки слоя «{name}» - промеры глубин, например галсы эхолота. "
            "Из них строится растр глубин триангуляцией, он ложится "
            "в рельеф глобуса дном водоёма, над ним - вода на уровне "
            "водоёма.", name=layer.name()), self)
        about.setWordWrap(True)
        self.field = QComboBox(self)
        if QgsWkbTypes.hasZ(layer.wkbType()):
            self.field.addItem(tr("Z точки"), Z_FIELD)
        for name in numeric_fields(layer):
            self.field.addItem(name, name)
        self.field.setToolTip(tr(
            "Поле с глубиной или Z точки. Знак глубины не важен, берётся "
            "её модуль."))
        self.field.currentIndexChanged.connect(self._read)
        self.cell = QDoubleSpinBox(self)
        self.cell.setRange(sounding.MIN_CELL, 1000.0)
        self.cell.setDecimals(1)
        self.cell.setSuffix(tr(" м"))
        self.cell.setToolTip(tr(
            "Размер ячейки растра глубин. По умолчанию - по количеству "
            "точек на площадь промеров. Мельче ячейка - подробнее дно "
            "и больше файл."))
        self.limit = QDoubleSpinBox(self)
        self.limit.setRange(1.0, 100000.0)
        self.limit.setDecimals(0)
        self.limit.setSuffix(tr(" м"))
        self.limit.setToolTip(tr(
            "Ячейка дальше этого расстояния от ближайшего промера остаётся "
            "пустой. Так растр не заливает берег и заливы без промеров. "
            "Предел больше расстояния между галсами, иначе между ними "
            "остаются полосы."))
        self.level = QDoubleSpinBox(self)
        self.level.setRange(-500.0, 9000.0)
        self.level.setDecimals(2)
        self.level.setSuffix(tr(" м"))
        self.level.setValue(float(level))
        self.level.setToolTip(tr(
            "Высота поверхности воды над уровнем моря в день промеров. "
            "Отметка дна - уровень воды минус глубина."))
        self.path = QLineEdit(path, self)
        self.path.setToolTip(tr("Файл GeoTIFF растра глубин."))
        browse = QPushButton(tr("Обзор…"), self)
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.path, 1)
        row.addWidget(browse)
        self.state = QLabel(self)
        self.state.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Глубина"), self.field)
        form.addRow(tr("Ячейка"), self.cell)
        form.addRow(tr("Предел от промера"), self.limit)
        form.addRow(tr("Уровень воды"), self.level)
        form.addRow(tr("Файл"), row)
        self.buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addWidget(about)
        layout.addLayout(form)
        layout.addWidget(self.state)
        layout.addWidget(self.buttons)
        self._read()

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Растр глубин"), self.path.text(), "GeoTIFF (*.tif)")
        if path:
            self.path.setText(path)

    def _read(self, *args):
        """Точки по выбранному полю, шаг и предел по умолчанию."""
        ok = self.buttons.button(enum(QDialogButtonBox, "StandardButton",
                                      "Ok"))
        if self.field.count() == 0:
            self.points = None
            self.state.setText(tr("У слоя нет числовых полей и Z точек."))
            ok.setEnabled(False)
            return
        self.points = read_points(self.layer, self.field.currentData())
        xs, ys, zs, _ = self.points
        if len(xs) < 3:
            self.state.setText(tr("Промеров с глубиной меньше трёх."))
            ok.setEnabled(False)
            return
        cell = sounding.auto_cell(xs, ys)
        self.cell.setValue(cell)
        self.limit.setValue(cell * sounding.MAX_GAP_CELLS)
        self.state.setText(tr(
            "Промеров {count}, глубина от {low:.1f} до {high:.1f} м.",
            count=len(xs), low=float(zs.min()), high=float(zs.max())))
        ok.setEnabled(True)

    def values(self):
        """(точки, шаг, предел, уровень, файл)."""
        return (self.points, float(self.cell.value()),
                float(self.limit.value()), float(self.level.value()),
                os.path.abspath(self.path.text()))
