# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горизонтали: картинки цифр подписей для рабочего потока, выгрузка
горизонталей вида и изолиний грида слоем GeoPackage в проект QGIS."""
import os
import time

import numpy as np
from qgis.core import (Qgis, QgsCoordinateReferenceSystem, QgsLineSymbol,
                       QgsPalLayerSettings, QgsProject, QgsProperty,
                       QgsSingleSymbolRenderer, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QObject, QTimer
from qgis.PyQt.QtGui import QColor, QFont, QFontMetrics, QImage, QPainter
from qgis.PyQt.QtWidgets import QFileDialog

from ..core import contours, ellipsoid
from ..core.sync import ground_size
from ..core.terrain import ancestor, resample
from ..i18n import tr
from ..net.loader import image_to_rgba
from ..net.overlay import STROKE_WIDTH
from ..qt_compat import enum
from .inset import warm

NODATA = -99999.0
LINE_COLOR = "150,85,30"  # как у горизонталей на глобусе
LINE_WIDTH = 0.25  # мм, утолщённые - вдвое толще
WAIT = 30.0  # с ожидания тайлов высот, дальше - по тем, что есть
POLL = 300  # мс между проверками пришедших тайлов

# Кегль цифр подписи в пикселях тайла. Тексель тайла на экране -
# около пикселя, поэтому кегль близок к экранному.
LABEL_PIXELS = 11
CHARS = "0123456789-."

_glyphs = None


def digit_glyphs():
    """Альфа цифр, минуса и точки шрифтом интерфейса: {символ: массив
    float (высота, ширина)}, "height" - общая высота. Рисуется один раз
    в главном потоке, рабочий поток только читает массивы."""
    global _glyphs
    if _glyphs is not None:
        return _glyphs
    font = QFont()
    font.setPixelSize(LABEL_PIXELS)
    font.setBold(True)
    metrics = QFontMetrics(font)
    height = metrics.ascent() + 1
    glyphs = {"height": height}
    for char in CHARS:
        width = max(metrics.horizontalAdvance(char), 1)
        image = QImage(width, height, enum(QImage, "Format",
                                           "Format_ARGB32_Premultiplied"))
        image.fill(QColor(0, 0, 0, 0))
        painter = QPainter(image)
        painter.setRenderHint(enum(QPainter, "RenderHint",
                                   "TextAntialiasing"))
        painter.setFont(font)
        painter.setPen(QColor(255, 255, 255))
        painter.drawText(0, metrics.ascent(), char)
        painter.end()
        alpha = image_to_rgba(image)[..., 3].astype(np.float32) / 255.0
        alpha.setflags(write=False)
        glyphs[char] = alpha
    _glyphs = glyphs
    return glyphs


def write_contours(values, transform, wkt, step, path):
    """Горизонтали массива values (NaN - пусто) через step в файл
    GeoPackage path, слой contours с полем elev. transform -
    геопреобразование GDAL, wkt - система координат. Главный поток.
    Возвращает количество линий или None при ошибке GDAL."""
    from osgeo import gdal, ogr, osr
    warm()
    values = np.where(np.isfinite(values), values, NODATA).astype(
        np.float32)
    source = gdal.GetDriverByName("MEM").Create(
        "", values.shape[1], values.shape[0], 1, gdal.GDT_Float32)
    source.SetGeoTransform(transform)
    source.SetProjection(wkt)
    band = source.GetRasterBand(1)
    band.SetNoDataValue(NODATA)
    band.WriteArray(values)
    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(path):
        driver.DeleteDataSource(path)
    out = driver.CreateDataSource(path)
    if out is None:
        return None
    srs = osr.SpatialReference()
    srs.ImportFromWkt(wkt)
    layer = out.CreateLayer("contours", srs, ogr.wkbLineString)
    layer.CreateField(ogr.FieldDefn("id", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("elev", ogr.OFTReal))
    code = gdal.ContourGenerateEx(band, layer, options=[
        "LEVEL_INTERVAL={}".format(step), "ID_FIELD=0", "ELEV_FIELD=1",
        "NODATA={}".format(NODATA)])
    count = layer.GetFeatureCount()
    out = None
    source = None
    return None if code != 0 else count


class ContourExport(QObject):
    """Выгрузка горизонталей в проект QGIS.

    Горизонтали вида: тайлы высот участка вида (contours.export_tiles)
    просит вид, как линейка, выгрузка ждёт их не дольше WAIT секунд,
    недостающие берутся по предку. Изолинии грида строятся по самому
    растру с шагом изолиний глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)

    def _say(self, text):
        self.window.message = (text, time.monotonic())
        self.window._show_state()

    def view_contours(self, path=None):
        """«Горизонтали вида в проект QGIS…» меню на глобусе. path -
        файл GeoPackage, без него - окно выбора."""
        window = self.window
        view = window.view
        if not window.planet.earth:
            self._say(tr("Горизонтали в проект выгружаются только "
                         "на Земле."))
            return
        pose = view.navigator.pose
        width, height = ground_size(pose.distance, view.camera.fov_y,
                                    view.camera.aspect)
        level, keys = contours.export_tiles(
            pose.lat, pose.lon, width, height, ellipsoid.A,
            view.store.max_level)
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                window, tr("Горизонтали вида в проект QGIS"),
                os.path.join(QgsProject.instance().homePath()
                             or os.path.expanduser("~"), "contours.gpkg"),
                tr("GeoPackage (*.gpkg)"))
        if not path:
            return
        self.job = {"keys": keys, "level": level, "path": path,
                    "started": time.monotonic()}
        self.timer.start()
        self._poll()

    def _poll(self):
        job = self.job
        if job is None:
            self.timer.stop()
            return
        window = self.window
        missing = [k for k in job["keys"] if not window._has_height_tile(k)]
        if missing and time.monotonic() - job["started"] < WAIT:
            window.view.want_tool_heights(missing)
            self._say(tr("Загрузка высот: {done} из {total}",
                         done=len(job["keys"]) - len(missing),
                         total=len(job["keys"])))
            return
        self.timer.stop()
        self.job = None
        store = window.view.store
        grid, x0, y0 = contours.mosaic(job["keys"],
                                       lambda key: heights_of(store, key))
        level = job["level"]
        middle_y = y0 + grid.shape[0] // (2 * contours.SIZE)
        step = contours.tile_step(level, middle_y, ellipsoid.A)
        wkt = QgsCoordinateReferenceSystem("EPSG:3857").toWkt()
        # Сглаживание - как у горизонталей на глобусе. Пустые тайлы
        # (NaN) оно растащило бы на соседей, тогда мозаика как есть.
        if np.isfinite(grid).all():
            grid = contours.smooth(grid.astype(np.float64))
        count = write_contours(
            grid, contours.mercator_transform(level, x0, y0, ellipsoid.A),
            wkt, step, job["path"])
        self._finish(count, job["path"], step, bool(missing))

    def grid_contours(self, layer, path=None):
        """«Изолинии в проект QGIS…» меню растра: изолинии по значениям
        растра с шагом изолиний гридов на глобусе."""
        from osgeo import gdal
        warm()
        data = gdal.Open(layer.source())
        if data is None:
            self._say(tr("Растр «{name}» не читается.", name=layer.name()))
            return
        band = data.GetRasterBand(1)
        values = band.ReadAsArray().astype(np.float64)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            values[values == nodata] = np.nan
        step = contours.grid_step(values)
        if step <= 0.0:
            self._say(tr("У растра «{name}» нет перепада значений.",
                         name=layer.name()))
            return
        start = os.path.dirname(layer.source()) \
            or QgsProject.instance().homePath()
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self.window, tr("Изолинии в проект QGIS"),
                os.path.join(start, layer.name() + "_contours.gpkg"),
                tr("GeoPackage (*.gpkg)"))
        if not path:
            return
        count = write_contours(values, data.GetGeoTransform(),
                               layer.crs().toWkt(), step, path)
        data = None
        self._finish(count, path, step, False)

    def _finish(self, count, path, step, partial):
        if count is None:
            self._say(tr("Горизонтали не записаны в «{path}».", path=path))
            return
        name = os.path.splitext(os.path.basename(path))[0]
        if add_layer(path, name, step) is None:
            self._say(tr("Горизонтали не записаны в «{path}».", path=path))
            return
        text = tr("В проект добавлено горизонталей {count}, сечение {step} м.",
                  count=count, step=contours.label_text(step))
        if partial:
            text += " " + tr("Загружены не все высоты, часть горизонталей "
                             "построена по менее подробным.")
        self._say(text)


def heights_of(store, key):
    """Высоты тайла key из хранилища, без него - по ближайшему
    загруженному предку, без предка - None."""
    tile = store.tiles.get(key)
    if tile is not None:
        return tile.heights
    for level in range(key[0] - 1, -1, -1):
        parent = store.tiles.get(ancestor(key, level))
        if parent is not None:
            return resample(parent, key)
    return None


def add_layer(path, name, step):
    """Слой горизонталей файла path в группе «PlanetX - горизонтали»
    вверху дерева: коричневые линии, утолщённые через INDEX сечений
    с подписями отметок вдоль линии."""
    layer = QgsVectorLayer(path + "|layername=contours", name, "ogr")
    if not layer.isValid():
        return None
    index = contours.index_step(step)
    on_index = 'abs("elev" / {0} - round("elev" / {0})) < 1e-6'.format(
        index)
    symbol = QgsLineSymbol.createSimple({"line_color": LINE_COLOR,
                                         "line_width": str(LINE_WIDTH)})
    symbol.symbolLayer(0).setDataDefinedProperty(
        STROKE_WIDTH, QgsProperty.fromExpression("if({}, {}, {})".format(
            on_index, 2 * LINE_WIDTH, LINE_WIDTH)))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
    settings = QgsPalLayerSettings()
    settings.isExpression = True
    # format_number ставит разделитель тысяч языка, отметки - без него.
    settings.fieldName = 'if({}, to_string(round("elev", 1)), NULL)' \
        .format(on_index)
    settings.placement = Qgis.LabelPlacement.Curved
    text = settings.format()
    text.setColor(QColor(100, 55, 20))
    settings.setFormat(text)
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)
    project = QgsProject.instance()
    title = tr("PlanetX - горизонтали")
    group = project.layerTreeRoot().findGroup(title)
    if group is None:
        group = project.layerTreeRoot().insertGroup(0, title)
    project.addMapLayer(layer, False)
    group.addLayer(layer)
    return layer
