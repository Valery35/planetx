# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Выемка и насыпь» и разность двух съёмок через GDAL.

Пункт «Выемка и насыпь…» меню растра в «Слоях проекта» - растр слоя
новая съёмка, в окне выбираются прежняя съёмка и участок. Обе съёмки
приводятся к сетке новой в метрах: её системе координат, если она
в метрах, иначе к зоне UTM середины. Расчёт - core/volumes.py.
Разность ложится в проект GeoTIFF со шкалой - выемка красная, насыпь
синяя.

GDAL вызывается в главном потоке без UseExceptions: режим исключений
общий для модулей QGIS.
"""
from qgis.core import (QgsColorRampShader, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsProject, QgsRasterLayer,
                       QgsRasterShader, QgsSingleBandPseudoColorRenderer,
                       QgsUnitTypes, QgsVectorLayer)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QLabel,
                                 QVBoxLayout)

from ..core import volumes
from ..core.modis import utm_epsg
from ..i18n import tr
from ..qt_compat import enum, enum_int

WHOLE = ""  # участок - весь охват новой съёмки
CUT_COLOR = (200, 40, 30)  # выемка, выбор помощника
FILL_COLOR = (30, 90, 200)  # насыпь


def raster_layers(exclude=None):
    """Однополосные растры GDAL проекта, кроме exclude."""
    return [layer for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsRasterLayer)
            and layer.providerType() == "gdal" and layer.bandCount() >= 1
            and layer.id() != exclude]


def polygon_layers():
    return [layer for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsVectorLayer)
            and enum_int(layer.geometryType()) == 2]


def _metric_srs(layer):
    """WKT системы в метрах для расчёта: своя у слоя или зона UTM."""
    crs = layer.crs()
    meters = getattr(QgsUnitTypes, "DistanceMeters", None)
    if meters is None:
        from qgis.core import Qgis
        meters = Qgis.DistanceUnit.Meters
    if not crs.isGeographic() and crs.mapUnits() == meters:
        return crs
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    center = QgsCoordinateTransform(crs, wgs, QgsProject.instance()) \
        .transform(layer.extent().center())
    return QgsCoordinateReferenceSystem("EPSG:{}".format(
        utm_epsg([(center.y(), center.x())])))


def _warp(path, crs, bounds=None, size=None, step=None):
    """Растр path в MEM в системе crs. bounds и size - сетка, иначе шаг
    step или свой."""
    from osgeo import gdal
    options = {"format": "MEM", "dstSRS": crs.toWkt(),
               "resampleAlg": "bilinear", "dstNodata": float("nan"),
               "outputType": gdal.GDT_Float64}
    if bounds is not None:
        options.update(outputBounds=bounds, width=size[0], height=size[1])
    elif step is not None:
        options.update(xRes=step, yRes=step)
    return gdal.Warp("", path, **options)


def compute(old_layer, new_layer, area_layer, threshold, path):
    """Разность съёмок в GeoTIFF path и сводка core.volumes.summary.
    Возвращает (сводка, None) или (None, текст ошибки)."""
    from osgeo import gdal, ogr, osr
    crs = _metric_srs(new_layer)
    new = _warp(new_layer.source(), crs)
    if new is None:
        return None, gdal.GetLastErrorMsg() or new_layer.name()
    x0, dx, _, y0, _, dy = new.GetGeoTransform()
    cols, rows = new.RasterXSize, new.RasterYSize
    bounds = (x0, y0 + dy * rows, x0 + dx * cols, y0)
    old = _warp(old_layer.source(), crs, bounds, (cols, rows))
    if old is None:
        return None, gdal.GetLastErrorMsg() or old_layer.name()
    inside = None
    if area_layer is not None:
        srs = osr.SpatialReference(wkt=crs.toWkt())
        source = ogr.GetDriverByName("Memory").CreateDataSource("area")
        shapes = source.CreateLayer("area", srs, ogr.wkbMultiPolygon)
        transform = QgsCoordinateTransform(area_layer.crs(), crs,
                                           QgsProject.instance())
        for feature in area_layer.getFeatures():
            geometry = feature.geometry()
            if geometry.isNull():
                continue
            geometry.transform(transform)
            item = ogr.Feature(shapes.GetLayerDefn())
            item.SetGeometry(ogr.CreateGeometryFromWkt(geometry.asWkt()))
            shapes.CreateFeature(item)
        mask = gdal.GetDriverByName("MEM").Create("", cols, rows, 1,
                                                  gdal.GDT_Byte)
        mask.SetGeoTransform(new.GetGeoTransform())
        mask.SetProjection(crs.toWkt())
        gdal.RasterizeLayer(mask, [1], shapes, burn_values=[1])
        inside = mask.GetRasterBand(1).ReadAsArray() > 0
    diff = volumes.difference(old.GetRasterBand(1).ReadAsArray(),
                              new.GetRasterBand(1).ReadAsArray(), inside)
    out = volumes.summary(diff, abs(dx * dy), threshold)
    tiff = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, gdal.GDT_Float32,
        ["COMPRESS=DEFLATE", "PREDICTOR=3", "TILED=YES"])
    if tiff is None:
        return None, gdal.GetLastErrorMsg() or path
    tiff.SetGeoTransform(new.GetGeoTransform())
    tiff.SetProjection(crs.toWkt())
    band = tiff.GetRasterBand(1)
    band.SetNoDataValue(volumes.NODATA)
    band.WriteArray(volumes.for_file(diff, threshold))
    tiff.FlushCache()
    tiff = new = old = None
    return out, None


def style_difference(layer, out):
    """Шкала разности - выемка красная, ноль белый, насыпь синяя,
    симметрично по большему модулю."""
    reach = max(abs(out["deepest"]), abs(out["highest"]), 1.0)
    ramp = QgsColorRampShader(-reach, reach)
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(-reach, QColor(*CUT_COLOR),
                                         "{:g}".format(-reach)),
        QgsColorRampShader.ColorRampItem(0.0, QColor(255, 255, 255, 0),
                                         "0"),
        QgsColorRampShader.ColorRampItem(reach, QColor(*FILL_COLOR),
                                         "{:g}".format(reach))])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1,
                                                shader)
    renderer.setClassificationMin(-reach)
    renderer.setClassificationMax(reach)
    layer.setRenderer(renderer)


def summary_text(out):
    """Сводка объёмов для окна сообщения."""
    return tr(
        "Выемка {cut:,.0f} м³ на площади {cut_area:,.0f} м², до "
        "{deepest:.1f} м.\nНасыпь {fill:,.0f} м³ на площади "
        "{fill_area:,.0f} м², до {highest:.1f} м.\nРазность насыпи "
        "и выемки {net:,.0f} м³. Площадь сравнения {area:,.0f} м².",
        **out).replace(",", " ")


class VolumeDialog(QDialog):
    """Окно настроек: новая съёмка layer, прежняя и участок."""

    def __init__(self, layer, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Выемка и насыпь"))
        about = QLabel(tr(
            "Растр «{name}» - новая съёмка рельефа. Разность с прежней "
            "съёмкой даёт выемку и насыпь, их объёмы и растр разности "
            "в проекте.", name=layer.name()), self)
        about.setWordWrap(True)
        self.old = QComboBox(self)
        for other in raster_layers(exclude=layer.id()):
            self.old.addItem(other.name(), other.id())
        self.old.setToolTip(tr(
            "Растр прежней съёмки того же участка. Он пересчитывается на "
            "сетку новой съёмки."))
        self.area = QComboBox(self)
        self.area.addItem(tr("Весь охват новой съёмки"), WHOLE)
        for other in polygon_layers():
            self.area.addItem(other.name(), other.id())
        self.area.setToolTip(tr(
            "Многоугольники участка, например контур карьера и отвалов. "
            "Вне них разность не считается."))
        self.threshold = QDoubleSpinBox(self)
        self.threshold.setRange(0.0, 100.0)
        self.threshold.setDecimals(2)
        self.threshold.setSuffix(tr(" м"))
        self.threshold.setValue(volumes.THRESHOLD)
        self.threshold.setToolTip(tr(
            "Разность меньше порога по модулю не входит в объёмы - это "
            "шум съёмки. Порог больше погрешности съёмок занижает объёмы."))
        form = QFormLayout()
        form.addRow(tr("Прежняя съёмка"), self.old)
        form.addRow(tr("Участок"), self.area)
        form.addRow(tr("Порог"), self.threshold)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        buttons.button(enum(QDialogButtonBox, "StandardButton",
                            "Ok")).setEnabled(self.old.count() > 0)
        layout = QVBoxLayout(self)
        layout.addWidget(about)
        layout.addLayout(form)
        if self.old.count() == 0:
            layout.addWidget(QLabel(tr(
                "В проекте нет другого растра - прежней съёмки."), self))
        layout.addWidget(buttons)

    def values(self):
        """(номер прежней съёмки, номер участка или WHOLE, порог)."""
        return (self.old.currentData(), self.area.currentData(),
                float(self.threshold.value()))
