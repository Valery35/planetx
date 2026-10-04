# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подземный режим: окно, чтение данных, сборка сеток, вырез, пол.

Подшаги 4.4-4.5 плана фазы 3 (doc/PLAN_PHASE3.md). Данные - таблицы
как у Isoliner: collar, interval, survey, beds (код, порядок, цвет,
растр кровли), sections (линии разрезов), cut (многоугольник выреза).
Источник - файл GeoPackage с таблицами этих имён или слои проекта.
Растры кровель читает GDAL по пути файла.

Сетки (core/subsurface.py) рисует render/subsurface.py до тайлов.
Высота на экране - отметка, умноженная на масштаб рельефа, при
выключенном рельефе - глубина под поверхностью (core.subsurface
.display). Сетки собираются заново при смене масштаба.

- Разрез - стенки между поверхностями вдоль линии: рельеф, кровли
  пластов по порядку, низ модели.
- Вырез блока - маска в шейдере тайла (слой вида «cut»), горизонты
  внутри выреза убираются, по краю выреза - стенки разреза, на дне -
  плоскость на отметке низа модели.
- Камера под землёй - пол навигации (GlobeView.floor) на отметке низа
  модели в её рамке, глаз опускается ниже рельефа.

Настройки лежат в записи проекта PlanetX/subsurface.
"""
import copy
import json
import math
import os
import time
from collections import namedtuple

import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsCsException, QgsExpression,
                       QgsExpressionContext, QgsExpressionContextUtils,
                       QgsPalLayerSettings, QgsPointXY, QgsProject,
                       QgsRasterLayer, QgsRenderContext, QgsVectorLayer,
                       QgsVectorLayerSimpleLabeling)
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QFileDialog, QFormLayout, QLabel, QPushButton,
                                 QSlider, QVBoxLayout)

from ..core import drillholes, ellipsoid, viewshed
from ..core import subsurface as core
from ..core.places import Place
from ..i18n import tr
from ..qt_compat import enum
from .project import ENTRY
from .layer_labels import label_settings
from .viewshed import ResultTiles, fit_status

SETTINGS_KEY = "subsurface"
ROLES = ("collar", "interval", "survey", "beds", "sections", "cut",
         "tunnels", "images")
MAX_NODES = 300  # узлов растра кровли на сторону, больше - прорежение
TUBE_SHARE = 1.0 / 400.0  # радиус ствола - доля поперечника модели
MIN_TUBE = 2.0  # м
SECTION_POINTS = 400  # точек стенки разреза на линию, не больше
BOTTOM_MARGIN = 20.0  # м ниже самой глубокой кровли, если скважин нет
EMPTY_COLOR = (150, 150, 150)
POLL = 250  # мс между проверками высот
WAIT = 30.0  # с ожидания высот
MARK_ID = -700000  # номера подписей устьев
# Тоннели, таблица tunnels: линии, поля name, depth - глубина оси
# в начале линии, depth_end - в конце (без него как depth), diameter,
# color «#rrggbb». Умолчания - тоннель Boring Company: диаметр 3.7 м
# (12 футов), цвет - выбор помощника.
TUNNEL_DIAMETER = 3.7  # м
TUNNEL_COLOR = (90, 160, 220)
TUNNEL_STEP = 10.0  # м между точками оси
# Разрезы с картинками, таблица images: линии, поля name, image - путь
# к картинке PNG или JPG (от папки файла GeoPackage), top и bottom -
# отметки верха и низа картинки, м. Картинка ложится по длине линии.
IMAGE_SIDE = 4096  # пикселей по большей стороне, больше - уменьшение
DEFAULTS = {"layers": {}, "horizons": [],
            "opacity": 0.6, "cut": True, "under": False}


def _value(v):
    """Значение атрибута: NULL QGIS в None."""
    if v is None or (hasattr(v, "isNull") and v.isNull()):
        return None
    return v


def _wgs():
    return QgsCoordinateReferenceSystem("EPSG:4326")


def rows_of(layer, points=False, skipped=None):
    """Строки слоя словарями. points - ещё x, y в системе слоя и
    широта, долгота устья. Точки без геометрии и с ошибкой пересчёта
    координат считаются в skipped["no_point"]."""
    names = [f.name() for f in layer.fields()]
    to_wgs = QgsCoordinateTransform(layer.crs(), _wgs(),
                                    QgsProject.instance()) if points else None
    skipped = {} if skipped is None else skipped
    out = []
    for feature in layer.getFeatures():
        row = {n: _value(v) for n, v in zip(names, feature.attributes())}
        row["__fid"] = feature.id()
        if points:
            geom = feature.geometry()
            point = None
            if geom is not None and not geom.isEmpty():
                p = geom.vertexAt(0)
                row["x"], row["y"] = p.x(), p.y()
                try:
                    point = to_wgs.transform(QgsPointXY(p.x(), p.y()))
                except QgsCsException:
                    point = None
            if point is None:
                skipped["no_point"] = skipped.get("no_point", 0) + 1
                continue
            row["lat"], row["lon"] = point.y(), point.x()
        out.append(row)
    return out


def _parts(geom, kind):
    """Части геометрии: ломаные (kind "line") или внешние кольца."""
    if geom is None or geom.isEmpty():
        return []
    if kind == "line":
        return geom.asMultiPolyline() if geom.isMultipart() \
            else [geom.asPolyline()]
    polygons = geom.asMultiPolygon() if geom.isMultipart() \
        else [geom.asPolygon()]
    return [p[0] for p in polygons if p]


def lines_of(layer, step):
    """Линии слоя со строками атрибутов: [(строка, точки (n, 2) широта
    и долгота)], точки через step метров."""
    names = [f.name() for f in layer.fields()]
    to_wgs, step = _transform(layer, step)
    out = []
    for feature in layer.getFeatures():
        row = {n: _value(v) for n, v in zip(names, feature.attributes())}
        row["__fid"] = feature.id()
        for pts in _feature_shapes(feature, to_wgs, "line", step):
            out.append((row, pts))
    return out


def _transform(layer, step):
    """Пересчёт системы слоя в WGS 84 и шаг в единицах слоя."""
    to_wgs = QgsCoordinateTransform(layer.crs(), _wgs(),
                                    QgsProject.instance())
    if step is not None and layer.crs().isGeographic():
        step = step / 111000.0
    return to_wgs, step


def _feature_shapes(feature, to_wgs, kind, step):
    """Части геометрии объекта в широтах и долготах (n, 2)."""
    out = []
    for part in _parts(feature.geometry(), kind):
        xy = np.array([(p.x(), p.y()) for p in part])
        if len(xy) < 2:
            continue
        dense = core.densify(xy, step) if step is not None else xy
        if kind != "line":
            dense = dense[:-1]
        try:
            pts = [to_wgs.transform(QgsPointXY(x, y)) for x, y in dense]
        except QgsCsException:
            # Линия вне области системы координат - без неё.
            pts = []
        if pts:
            out.append(np.array([(p.y(), p.x()) for p in pts]))
    return out


def image_rgba(path):
    """Картинка разреза массивом (h, w, 4) uint8, верхняя строка -
    верх картинки, или None, если файл не читается. Большая картинка
    уменьшается до IMAGE_SIDE по большей стороне."""
    image = QImage(path) if path else QImage()
    if image.isNull():
        return None
    if max(image.width(), image.height()) > IMAGE_SIDE:
        image = image.scaled(IMAGE_SIDE, IMAGE_SIDE,
                             enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
                             enum(Qt, "TransformationMode",
                                  "SmoothTransformation"))
    image = image.convertToFormat(enum(QImage, "Format",
                                       "Format_RGBA8888"))
    width, height, line = image.width(), image.height(), \
        image.bytesPerLine()
    bits = image.constBits()
    bits.setsize(line * height)
    return np.frombuffer(bits, dtype=np.uint8).reshape(
        height, line)[:, :width * 4].reshape(height, width, 4).copy()


def build_images(model, scale, ground):
    """Стенки разрезов с картинками для вида: [(центр, вершины, индексы,
    rgba)]. Верх и низ - отметки, на экране как у прочего подземного."""
    walls = []
    alpha = model.alpha.get("images", 1.0)
    for name, pts, top, bottom, rgba in model.images:
        if alpha < 1.0:
            rgba = rgba.copy()
            rgba[..., 3] = (rgba[..., 3] * alpha).astype(np.uint8)
        lats, lons = pts[:, 0], pts[:, 1]
        g = ground(lats, lons)
        walls.append(core.image_wall(
            lats, lons, core.display(np.full(len(lats), top), scale, g),
            core.display(np.full(len(lats), bottom), scale, g)) + (rgba,))
    return walls


TEMPLATE_STEP = 100.0  # м между предметами примера шаблона


def write_template(path, lat, lon, ground):
    """Файл GeoPackage со всеми таблицами подземного режима и примером
    у точки (lat, lon) с отметкой рельефа ground: скважина с двумя
    интервалами и инклинометрией, два пласта, разрез, тоннель, вырез.
    Таблица images пустая, у картинки нужен свой файл. Система
    координат - WGS 84. Файл не создан - RuntimeError. Режим исключений
    GDAL не включается: он общий для всех модулей QGIS."""
    if os.path.exists(path):
        os.remove(path)
    ds = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    if ds is None:
        raise RuntimeError(gdal.GetLastErrorMsg() or path)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    step = TEMPLATE_STEP

    def at(east, north):
        return _to_latlon(lat, lon, east, north)

    def layer(name, geom, fields):
        lyr = ds.CreateLayer(name, wgs if geom != ogr.wkbNone else None,
                             geom)
        if lyr is None:
            raise RuntimeError(gdal.GetLastErrorMsg() or name)
        for field, kind in fields:
            lyr.CreateField(ogr.FieldDefn(field, kind))
        return lyr

    def add(lyr, values, wkt=None):
        feature = ogr.Feature(lyr.GetLayerDefn())
        for key, value in values.items():
            feature.SetField(key, value)
        if wkt:
            feature.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        lyr.CreateFeature(feature)

    def line(points):
        return "LINESTRING (%s)" % ", ".join(
            "%.8f %.8f" % (lo, la) for la, lo in points)

    collar = layer("collar", ogr.wkbPoint, [("hole_id", ogr.OFTString),
                                            ("z", ogr.OFTReal),
                                            ("eoh", ogr.OFTReal)])
    add(collar, {"hole_id": "1", "z": round(ground, 2), "eoh": 120.0},
        "POINT (%.8f %.8f)" % (lon, lat))
    interval = layer("interval", ogr.wkbNone, [("hole_id", ogr.OFTString),
                                               ("from", ogr.OFTReal),
                                               ("to", ogr.OFTReal),
                                               ("code", ogr.OFTString)])
    add(interval, {"hole_id": "1", "from": 0.0, "to": 40.0, "code": "A"})
    add(interval, {"hole_id": "1", "from": 40.0, "to": 120.0, "code": "B"})
    survey = layer("survey", ogr.wkbNone, [("hole_id", ogr.OFTString),
                                           ("depth", ogr.OFTReal),
                                           ("azimuth", ogr.OFTReal),
                                           ("dip", ogr.OFTReal)])
    for depth, dip in ((0.0, -90.0), (60.0, -80.0), (120.0, -70.0)):
        add(survey, {"hole_id": "1", "depth": depth, "azimuth": 90.0,
                     "dip": dip})
    beds = layer("beds", ogr.wkbNone, [("code", ogr.OFTString),
                                       ("ord", ogr.OFTInteger),
                                       ("color", ogr.OFTString),
                                       ("surface", ogr.OFTString)])
    add(beds, {"code": "A", "ord": 1, "color": "#d9c27a", "surface": ""})
    add(beds, {"code": "B", "ord": 2, "color": "#6f9fd8", "surface": ""})
    sections = layer("sections", ogr.wkbLineString,
                     [("name", ogr.OFTString)])
    a, b = at(-2 * step, step), at(2 * step, step)
    add(sections, {"name": "Разрез 1"},
        line([(a[0], a[1]), (b[0], b[1])]))
    cut = layer("cut", ogr.wkbPolygon, [("name", ogr.OFTString)])
    ring = [at(e * step, n * step) for e, n in
            ((-2, -3), (2, -3), (2, -1), (-2, -1), (-2, -3))]
    add(cut, {"name": "Вырез"}, "POLYGON ((%s))" % ", ".join(
        "%.8f %.8f" % (lo, la) for la, lo in ring))
    tunnels = layer("tunnels", ogr.wkbLineString,
                    [("name", ogr.OFTString), ("depth", ogr.OFTReal),
                     ("depth_end", ogr.OFTReal), ("diameter", ogr.OFTReal),
                     ("color", ogr.OFTString)])
    a, b = at(-3 * step, -0.5 * step), at(3 * step, -0.5 * step)
    add(tunnels, {"name": "Тоннель 1", "depth": 15.0, "depth_end": 25.0,
                  "diameter": 5.0, "color": "#5aa0dc"},
        line([(a[0], a[1]), (b[0], b[1])]))
    layer("images", ogr.wkbLineString,
          [("name", ogr.OFTString), ("image", ogr.OFTString),
           ("top", ogr.OFTReal), ("bottom", ogr.OFTReal)])
    ds = None


# Раскраски растра, которые настраивают нарочно: кровля берёт их цвета.
# Серый растр по умолчанию оставляет цвет пласта.
STYLED_RASTERS = ("singlebandpseudocolor", "paletted", "multibandcolor",
                  "singlebandcolordata")
# Стили векторного слоя с цветом по объекту. Простой символ QGIS
# выбирает случайно при загрузке, у него цвет - из данных.
STYLED_VECTORS = ("categorizedSymbol", "graduatedSymbol", "RuleRenderer")


def raster_colors(layer, shape):
    """Цвета узлов кровли из раскраски растра QGIS (rows, cols, 4) или
    None, если раскраска не настроена нарочно."""
    renderer = layer.renderer()
    if renderer is None or renderer.type() not in STYLED_RASTERS:
        return None
    rows, cols = shape
    block = renderer.block(1, layer.extent(), cols, rows)
    if block is None or not block.isValid():
        return None
    image = block.image().convertToFormat(enum(QImage, "Format",
                                               "Format_RGBA8888"))
    line = image.bytesPerLine()
    bits = image.constBits()
    bits.setsize(line * image.height())
    data = np.frombuffer(bits, dtype=np.uint8).reshape(image.height(), line)
    return data[:, :cols * 4].reshape(rows, cols, 4).copy()


def symbol_colors(layer):
    """Цвета символов объектов слоя {номер объекта: (r, g, b)} при стиле
    по категориям, градуированном или по правилам, иначе {}."""
    renderer = layer.renderer() if hasattr(layer, "renderer") else None
    if renderer is None or renderer.type() not in STYLED_VECTORS:
        return {}
    context = QgsRenderContext()
    renderer.startRender(context, layer.fields())
    out = {}
    try:
        for feature in layer.getFeatures():
            symbol = renderer.symbolForFeature(feature, context)
            if symbol is not None:
                c = symbol.color()
                out[feature.id()] = (c.red(), c.green(), c.blue())
    finally:
        renderer.stopRender(context)
    return out


def label_texts(layer, rows):
    """Подписи устьев {номер скважины: текст} по настройкам подписей
    слоя QGIS - полю или выражению. Подписи слоя выключены - {}."""
    found = label_settings(layer)
    if not found or not rows:
        return {}
    settings = found[0][0]
    text = settings.fieldName
    expression = QgsExpression(text if settings.isExpression
                               else QgsExpression.quotedColumnRef(text))
    context = QgsExpressionContext(
        QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    f_id = drillholes.find_field(rows[0].keys(), "hole_id")
    by_fid = {r["__fid"]: str(r.get(f_id)) for r in rows if f_id}
    out = {}
    for feature in layer.getFeatures():
        hole = by_fid.get(feature.id())
        if hole is None:
            continue
        context.setFeature(feature)
        value = expression.evaluate(context)
        if value is not None and str(value) != "NULL":
            out[hole] = str(value)
    return out


def label_by_field(layer, field):
    """Простые подписи слоя по полю field, как в QGIS."""
    settings = QgsPalLayerSettings()
    settings.fieldName = field
    settings.isExpression = False
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.setLabelsEnabled(True)


def _with_alpha(color, alpha):
    """Цвет (r, g, b) с прозрачностью alpha от 0 до 1."""
    return tuple(color[:3]) + (int(round(255 * alpha)),)


def _color(text, default):
    """Цвет «#rrggbb» в (r, g, b), неверная запись - default."""
    text = str(text or "").strip().lstrip("#")
    try:
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4)) \
            if len(text) == 6 else default
    except ValueError:
        return default


def _number(row, name, default):
    value = row.get(name)
    try:
        return float(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def shapes_of(layer, kind, step):
    """Линии или кольца слоя в широтах и долготах, точки через step
    единиц системы слоя. Кольцо - без повтора первой точки."""
    to_wgs, step = _transform(layer, step)
    out = []
    for feature in layer.getFeatures():
        out += _feature_shapes(feature, to_wgs, kind, step)
    return out


class Horizon:
    """Кровля пласта: растр отметок и пересчёт широт в его систему."""

    def __init__(self, code, path):
        ds = gdal.Open(path)
        band = ds.GetRasterBand(1)
        cols, rows = ds.RasterXSize, ds.RasterYSize
        step = max(1, int(math.ceil(max(cols, rows) / MAX_NODES)))
        bc, br = max(2, cols // step), max(2, rows // step)
        z = band.ReadAsArray(buf_xsize=bc, buf_ysize=br).astype(np.float64)
        nodata = band.GetNoDataValue()
        if nodata is not None:
            z[z == nodata] = np.nan
        gt = ds.GetGeoTransform()
        dx, dy = gt[1] * cols / bc, gt[5] * rows / br
        self.code = code
        self.colors = None  # цвета узлов из раскраски растра в QGIS
        self.alpha = 1.0
        self.grid = core.Grid(gt[0] + dx / 2, gt[3] + dy / 2, dx, dy, z)
        srs = osr.SpatialReference()
        srs.ImportFromWkt(ds.GetProjection())
        srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        wgs = osr.SpatialReference()
        wgs.ImportFromEPSG(4326)
        wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
        self.to_grid = osr.CoordinateTransformation(wgs, srs)
        to_wgs = osr.CoordinateTransformation(srs, wgs)
        xs = self.grid.x0 + np.arange(bc) * dx
        ys = self.grid.y0 + np.arange(br) * dy
        gx, gy = np.meshgrid(xs, ys)
        pts = np.array(to_wgs.TransformPoints(
            np.stack([gx.ravel(), gy.ravel()], axis=1).tolist()))
        self.lons = pts[:, 0].reshape(gx.shape)
        self.lats = pts[:, 1].reshape(gx.shape)
        ds = None

    def at(self, lats, lons):
        """Отметки кровли в точках (широты, долготы), вне растра - NaN."""
        pts = np.array(self.to_grid.TransformPoints(
            np.stack([lons, lats], axis=1).tolist()))
        return core.sample_grid(self.grid, pts[:, 0], pts[:, 1])


class Model:
    """Подземные данные: скважины, кровли, разрезы, вырез, пласты."""

    def __init__(self):
        self.holes = []  # (Hole, широта, долгота устья)
        self.horizons = []  # Horizon сверху вниз
        self.beds = []  # коды пластов сверху вниз
        self.palette = {}  # код - «#rrggbb»
        self.sections = []  # (широты, долготы)
        self.rings = []  # кольца выреза (n, 2), сгущённые для стенок
        self.mask_rings = []  # те же кольца по вершинам, для маски
        self.tunnels = []  # (название, точки (n, 2), глубины, диаметр, цвет)
        self.images = []  # (название, точки (n, 2), верх, низ, rgba)
        # Прозрачность слоёв QGIS по ролям, от 0 до 1.
        self.alpha = {}
        self.hole_colors = {}  # номер скважины - цвет символа устья
        self.hole_labels = {}  # номер скважины - подпись из настроек QGIS
        self.skipped = {}
        self.missing = []  # не найденные таблицы и растры

    def color(self, code):
        if not code:
            return EMPTY_COLOR
        return drillholes.code_color(code, self.palette)

    def box(self):
        """Рамка данных: (юг, север, запад, восток) или None."""
        lats, lons = [], []
        for _, lat, lon in self.holes:
            lats.append(lat)
            lons.append(lon)
        for h in self.horizons:
            lats += [np.nanmin(h.lats), np.nanmax(h.lats)]
            lons += [np.nanmin(h.lons), np.nanmax(h.lons)]
        for shape in self.sections + self.rings + [
                t[1] for t in self.tunnels + self.images]:
            lats += [shape[:, 0].min(), shape[:, 0].max()]
            lons += [shape[:, 1].min(), shape[:, 1].max()]
        if not lats:
            return None
        return min(lats), max(lats), min(lons), max(lons)

    def extent(self):
        """Поперечник рамки, метры."""
        box = self.box()
        if box is None:
            return 0.0
        south, north, west, east = box
        dy = math.radians(north - south) * ellipsoid.A
        dx = math.radians(east - west) * ellipsoid.A * math.cos(
            math.radians((north + south) / 2))
        return math.hypot(dx, dy)

    def bottom(self):
        """Отметка низа модели: забой самой глубокой скважины или ниже
        самой глубокой кровли на BOTTOM_MARGIN."""
        lows = [h.axis[:, 3].min() for h, _, _ in self.holes]
        roofs = [np.nanmin(h.grid.z) for h in self.horizons
                 if np.any(np.isfinite(h.grid.z))]
        if roofs:
            lows.append(min(roofs) - BOTTOM_MARGIN)
        return min(lows) if lows else 0.0




def _file_of_source(source):
    """Файл источника слоя: путь до «|» параметров OGR."""
    return source.split("|")[0]


def _file_of(layer):
    return _file_of_source(layer.source())


def detect_role(layer):
    """Роль слоя подземного режима или None: по имени таблицы - имени
    слоя или layername источника GeoPackage, иначе по полям. Разрезы
    и вырез узнаются только по имени, у линий и многоугольников полей
    для них нет."""
    if isinstance(layer, QgsRasterLayer):
        return None
    names = [layer.name().strip().lower()]
    source = layer.source().lower()
    if "layername=" in source:
        names.append(source.split("layername=")[1].split("|")[0].strip())
    for role in ROLES:
        if role in names:
            return role
    fields = [f.name() for f in layer.fields()]

    def has(*roles):
        return all(drillholes.find_field(fields, r) for r in roles)
    lower = {f.lower() for f in fields}
    kind = layer.geometryType()
    point, line = Qgis.GeometryType.Point, Qgis.GeometryType.Line
    table = Qgis.GeometryType.Null
    if kind == point and has("hole_id", "eoh"):
        return "collar"
    if kind == table and has("hole_id", "from", "to"):
        return "interval"
    if kind == table and has("hole_id", "md", "azimuth"):
        return "survey"
    if kind == table and has("code") and {"ord", "color"} & lower:
        return "beds"
    if kind == line and {"depth", "diameter"} <= lower:
        return "tunnels"
    if kind == line and {"image", "top", "bottom"} <= lower:
        return "images"
    return None


def add_to_project(title, path, tables, rasters):
    """Таблицы tables файла GeoPackage path и растры rasters - группа
    title вверху дерева слоёв проекта. Прежняя группа с тем же
    названием убирается вместе с её слоями. Возвращает номера слоёв."""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    old = root.findGroup(title)
    if old is not None:
        project.removeMapLayers([n.layerId() for n in old.findLayers()])
        root.removeChildNode(old)
    group = root.insertGroup(0, title)
    ids = []
    layers = [QgsVectorLayer("{}|layername={}".format(path, name), name,
                             "ogr") for name in tables]
    layers += [QgsRasterLayer(f, os.path.splitext(os.path.basename(f))[0])
               for f in rasters]
    for layer in layers:
        if not layer.isValid():
            continue
        if detect_role(layer) == "collar":
            field = drillholes.find_field(
                [f.name() for f in layer.fields()], "hole_id")
            if field:
                label_by_field(layer, field)
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        ids.append(layer.id())
    return ids


TABLE_ROLES = ("interval", "survey", "beds")


def table_roles(used):
    """Таблицы интервалов, инклинометрии и пластов в проекте: {роль:
    номер слоя}. Слои той же группы дерева, что слои used, - первыми."""
    project = QgsProject.instance()
    root = project.layerTreeRoot()
    groups = set()
    for layer_id in used:
        node = root.findLayer(layer_id)
        if node is not None:
            groups.add(id(node.parent()))
    found = {}
    for node in sorted(root.findLayers(),
                       key=lambda n: id(n.parent()) not in groups):
        layer = node.layer()
        if layer is None:
            continue
        role = detect_role(layer)
        if role in TABLE_ROLES and role not in found:
            found[role] = layer.id()
    return found


def subsurface_ids(layer_ids):
    """Номера слоёв из layer_ids, которые идут в подземное, а не
    в наложение на поверхность."""
    project = QgsProject.instance()
    layers = [project.mapLayer(i) for i in layer_ids]
    roles, roofs = project_roles([la for la in layers if la is not None])
    return set(roles.values()) | set(roofs)


def project_roles(layers):
    """Слои подземного режима среди layers - слоёв проекта по порядку
    карты: ({роль: номер слоя}, [номера растров кровель]). Кровля -
    растр, файл которого назван в поле surface таблицы пластов любого
    слоя проекта."""
    roles = {}
    for layer in layers:
        role = detect_role(layer)
        if role and role not in roles:
            roles[role] = layer.id()
    surfaces = set()
    for layer in QgsProject.instance().mapLayers().values():
        if detect_role(layer) == "beds" and layer.fields().indexOf(
                "surface") >= 0:
            for feature in layer.getFeatures():
                value = _value(feature["surface"])
                if value:
                    surfaces.add(os.path.basename(str(value)).lower())
    roofs = [layer.id() for layer in layers
             if isinstance(layer, QgsRasterLayer)
             and os.path.basename(_file_of(layer)).lower() in surfaces]
    return roles, roofs


def load(settings):
    """Модель по настройкам окна. Таблиц может не быть, кроме устьев
    или кровель - нужно хотя бы что-то одно."""
    model = Model()
    layers = {}
    rasters = []
    raster_layers = {}  # источник - слой проекта, для стиля
    project = QgsProject.instance()
    for role in ROLES:
        layer_id = settings["layers"].get(role)
        layers[role] = project.mapLayer(layer_id) if layer_id else None
    for layer_id in settings["horizons"]:
        layer = project.mapLayer(layer_id)
        if isinstance(layer, QgsRasterLayer):
            rasters.append((layer.name(), layer.source()))
            raster_layers[layer.source()] = layer
    base = project.homePath()
    if layers["images"] is not None:
        # Картинки разрезов - от папки файла слоя.
        folder = os.path.dirname(_file_of(layers["images"]))
        base = folder or base
    beds = rows_of(layers["beds"]) if layers["beds"] else []
    if beds:
        f_code = drillholes.find_field(beds[0].keys(), "code")
        ordered = sorted(beds, key=lambda r: (r.get("ord") is None,
                                              r.get("ord") or 0))
        for row in ordered:
            code = str(row.get(f_code) or "")
            model.beds.append(code)
            if row.get("color"):
                model.palette[code] = str(row["color"])
            surface = row.get("surface")
            if surface:
                # Слой проекта - кровля этого пласта по имени файла.
                name = os.path.basename(str(surface)).lower()
                rasters = [(code if os.path.basename(_file_of_source(
                    src)).lower() == name else c, src)
                    for c, src in rasters]
    for code, path in rasters:
        try:
            horizon = Horizon(code, path)
        except RuntimeError:
            model.missing.append(os.path.basename(path))
            continue
        layer = raster_layers.get(path)
        if layer is not None:
            horizon.colors = raster_colors(layer, horizon.grid.z.shape)
            horizon.alpha = layer.opacity()
        model.horizons.append(horizon)
    for role in ("collar", "tunnels", "images", "sections"):
        if layers[role] is not None:
            model.alpha[role] = layers[role].opacity()
    if not beds:
        # Без таблицы пластов кровли идут по средней отметке сверху вниз.
        model.horizons.sort(key=lambda h: -np.nanmean(h.grid.z))
        model.beds = [""] + [h.code for h in model.horizons]
    else:
        order = {code: i for i, code in enumerate(model.beds)}
        model.horizons.sort(key=lambda h: order.get(h.code, len(order)))
    if layers["collar"]:
        lost = {}
        collars = rows_of(layers["collar"], points=True, skipped=lost)
        intervals = rows_of(layers["interval"]) if layers["interval"] else []
        surveys = rows_of(layers["survey"]) if layers["survey"] else []
        where = {(r["x"], r["y"]): (r["lat"], r["lon"]) for r in collars}
        holes, model.skipped = drillholes.assemble(collars, intervals,
                                                   surveys)
        model.skipped.update(lost)
        model.holes = [(h,) + where[(h.x, h.y)] for h in holes]
        model.hole_labels = label_texts(layers["collar"], collars)
        colors = symbol_colors(layers["collar"])
        if colors:
            f_id = drillholes.find_field(collars[0].keys(), "hole_id") \
                if collars else None
            model.hole_colors = {str(r.get(f_id)): colors[r["__fid"]]
                                 for r in collars
                                 if f_id and r["__fid"] in colors}
        if not beds and model.beds and not model.beds[0]:
            # Верхний пласт - код верхнего интервала скважин.
            tops = [h.intervals[0].code for h, _, _ in model.holes
                    if h.intervals and h.intervals[0].start <= 0.0]
            if tops:
                model.beds[0] = max(set(tops), key=tops.count)
    step = max(model.extent() / SECTION_POINTS, 5.0)
    if layers["sections"]:
        model.sections = shapes_of(layers["sections"], "line", step)
    if layers["cut"]:
        model.rings = shapes_of(layers["cut"], "polygon", step)
        # Маске хватает вершин многоугольника: точка в многоугольнике
        # считается проходом по рёбрам, у сгущённого кольца их сотни.
        model.mask_rings = shapes_of(layers["cut"], "polygon", None)
    if layers["tunnels"]:
        colors = symbol_colors(layers["tunnels"])
        for row, pts in lines_of(layers["tunnels"], TUNNEL_STEP):
            if colors and row["__fid"] in colors:
                row = dict(row, color="#%02x%02x%02x" % colors[row["__fid"]])
            start = _number(row, "depth", 0.0)
            model.tunnels.append((
                str(row.get("name") or ""), pts,
                (start, _number(row, "depth_end", start)),
                _number(row, "diameter", TUNNEL_DIAMETER),
                _color(row.get("color"), TUNNEL_COLOR)))
    if layers["images"]:
        for row, pts in lines_of(layers["images"], step):
            name = str(row.get("name") or "")
            path = str(row.get("image") or "")
            if base and path and not os.path.isabs(path):
                path = os.path.join(base, path)
            rgba = image_rgba(path)
            if rgba is None:
                model.missing.append(os.path.basename(path) or name)
                continue
            model.images.append((name, pts, _number(row, "top", 0.0),
                                 _number(row, "bottom", -100.0), rgba))
    return model


def _to_latlon(lat0, lon0, east, north):
    """Смещения в метрах от устья в широты и долготы."""
    lat = lat0 + np.degrees(np.asarray(north) / ellipsoid.A)
    lon = lon0 + np.degrees(np.asarray(east) / (
        ellipsoid.A * math.cos(math.radians(lat0))))
    return lat, lon


Pick = namedtuple("Pick", "kind name xyz values")
Pick.__doc__ = """Ось скважины или тоннеля для окна «Объекты»: kind -
"hole" или "tunnel", xyz - точки оси на экране в ECEF (n, 3), values -
числа в точках оси (n, k), их значения называет SubsurfaceManager."""


def build(model, scale, ground, cut):
    """Сетки, подписи и оси: словарь имя - Mesh, список подписей
    устьев, список Pick для опроса щелчком.

    ground(lats, lons) - настоящие отметки рельефа. cut - вырез
    блока включён."""
    meshes = {}
    picks = []
    radius = max(MIN_TUBE, model.extent() * TUBE_SHARE)
    wells = []
    marks = []
    wells_alpha = model.alpha.get("collar", 1.0)
    for n, (hole, lat0, lon0) in enumerate(model.holes):
        g0 = float(ground(np.array([lat0]), np.array([lon0]))[0])
        empty = model.hole_colors.get(str(hole.hole_id), EMPTY_COLOR)
        pieces = [(i.start, i.end, _with_alpha(model.color(i.code),
                                               wells_alpha))
                  for i in hole.intervals] or [
                      (0.0, hole.eoh, _with_alpha(empty, wells_alpha))]
        for start, end, color in pieces:
            pts = drillholes.piece(hole.axis, start, end)
            lat, lon = _to_latlon(lat0, lon0, pts[:, 0], pts[:, 1])
            alt = core.display(pts[:, 2], scale, g0)
            wells.append(core.tube(core.ecef(lat, lon, alt), radius, color))
        text = model.hole_labels.get(str(hole.hole_id))
        if text:
            marks.append(Place(MARK_ID - n, text, "layer", 1, lat0, lon0))
        # Ось целиком: глубина по стволу, отметка, глубина под устьем.
        nodes = hole.axis
        lat, lon = _to_latlon(lat0, lon0, nodes[:, 1], nodes[:, 2])
        picks.append(Pick("hole", hole, core.ecef(
            lat, lon, core.display(nodes[:, 3], scale, g0)),
            np.column_stack([nodes[:, 0], nodes[:, 3],
                             g0 - nodes[:, 3]])))
    # Тоннели - трубки по оси под рельефом, радиус - половина диаметра.
    for name, pts, (start, end), diameter, color in model.tunnels:
        lats, lons = pts[:, 0], pts[:, 1]
        g = ground(lats, lons)
        z = core.tunnel_z(g, start, end, core.along(lats, lons))
        xyz = core.ecef(lats, lons, core.display(z, scale, g))
        wells.append(core.tube(xyz, diameter / 2.0, _with_alpha(
            color, model.alpha.get("tunnels", 1.0))))
        picks.append(Pick("tunnel", (name, diameter), xyz,
                          np.column_stack([z, g - z])))
    meshes["wells"] = core.merge(wells, "wells")
    bottom = model.bottom()
    surfaces = []
    for h in model.horizons:
        valid = np.isfinite(h.grid.z)
        if cut:
            for ring in model.mask_rings:
                valid &= ~core.inside(h.lats, h.lons, ring)
        g = ground(h.lats.ravel(), h.lons.ravel()).reshape(h.lats.shape) \
            if not scale else 0.0
        alt = core.display(np.nan_to_num(h.grid.z), scale, g)
        if h.colors is not None:
            # Раскраска растра QGIS: прозрачные пиксели - дыры кровли.
            colors = h.colors.copy()
            valid &= colors[..., 3] > 0
            colors[..., 3] = (colors[..., 3] * h.alpha).astype(np.uint8)
        else:
            colors = np.array(_with_alpha(model.color(h.code), h.alpha),
                              dtype=np.uint8)
        surfaces.append(core.grid_surface(
            core.ecef(h.lats, h.lons, alt), valid, colors))
    meshes["horizons"] = core.merge(surfaces, "horizons")
    lines = list(model.sections)
    if cut:
        # Край выреза - замкнутая линия разреза.
        lines += [np.vstack([r, r[:1]]) for r in model.rings]
    walls = []
    # Цвет пласта между соседними поверхностями: над первой кровлей -
    # верхний пласт, под кровлей - пласт этой кровли.
    top = model.beds[0] if model.beds else ""
    walls_alpha = model.alpha.get("sections", 1.0)
    colors = [_with_alpha(model.color(top), walls_alpha)] + [
        _with_alpha(model.color(h.code), walls_alpha)
        for h in model.horizons]
    for line in lines:
        lats, lons = line[:, 0], line[:, 1]
        g = ground(lats, lons)
        stack = [g] + [h.at(lats, lons) for h in model.horizons] \
            + [np.full(len(lats), bottom)]
        stack = core.stack(stack)
        shown = core.display(stack, scale, g)
        walls += core.fence(lats, lons, shown, colors)
    if cut:
        for ring in model.rings:
            g = float(np.mean(ground(ring[:, 0], ring[:, 1])))
            alt = float(core.display(bottom, scale, g))
            walls.append(core.floor_part(ring, alt, colors[-1]))
    meshes["sections"] = core.merge(walls, "sections")
    return meshes, marks, picks


class CutMask:
    """Маска слоя вида «cut»: рамка модели (box - юг, север, запад,
    восток) и кольца выреза блока, пустой список - выреза нет."""

    def __init__(self, box, rings):
        self.box = box
        self.rings = rings


def cut_rgba(mask, lats, lons, radius):
    """Картинка тайла маски. Красный канал - внутри рамки модели, там
    поверхность прозрачна. Альфа - внутри выреза, там её нет."""
    south, north, west, east = mask.box
    out = np.zeros(np.shape(lats) + (4,), dtype=np.uint8)
    region = (lats >= south) & (lats <= north) & (lons >= west) \
        & (lons <= east)
    out[region, 0] = 255
    hit = np.zeros(np.shape(lats), dtype=bool)
    for ring in mask.rings:
        hit |= core.inside(lats, lons, ring)
    out[hit, 3] = 255
    return out


def read_settings():
    text = QgsProject.instance().readEntry(ENTRY, SETTINGS_KEY, "")[0]
    try:
        stored = json.loads(text) if text else {}
    except ValueError:
        stored = {}
    out = dict(DEFAULTS)
    out.update({k: v for k, v in stored.items() if k in DEFAULTS})
    return out


def write_settings(settings):
    QgsProject.instance().writeEntry(ENTRY, SETTINGS_KEY,
                                     json.dumps(settings))




class SubsurfaceDialog(QDialog):
    """Окно «Подземный режим»: как показывать подземное. Данные - слои
    проекта, их показывают флажки «Слоёв проекта». Сигналы: options -
    прозрачность, вырез и камера сменились, template_requested - путь
    файла шаблона."""

    template_requested = pyqtSignal(str)
    options = pyqtSignal(dict)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Подземный режим"))
        layout = QVBoxLayout(self)
        intro = QLabel(tr(
            "Скважины, кровли пластов, разрезы, тоннели и картинки разрезов "
            "- обычные слои проекта. Отмеченные в разделе «Слои проекта» "
            "встают под поверхность глобуса. Чтобы посмотреть, как это "
            "выглядит, откройте демо «Пермские отложения» и проведите тур "
            "кнопкой ▶ под «Моими метками». Чтобы начать со своими данными, "
            "создайте шаблон у точки взгляда."), self)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        options = QFormLayout()
        self.opacity = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.opacity.setRange(10, 100)
        self.opacity.setValue(int(round(settings["opacity"] * 100)))
        self.opacity.setToolTip(tr(
            "Непрозрачность поверхности. Меньше - сквозь рельеф видны "
            "скважины и кровли пластов."))
        self.opacity.valueChanged.connect(self._options)
        options.addRow(tr("Непрозрачность поверхности"), self.opacity)
        self.cut = QCheckBox(tr("Вырез блока"), self)
        self.cut.setChecked(settings["cut"])
        self.cut.setToolTip(tr(
            "Убрать поверхность и кровли внутри многоугольника выреза. "
            "По краю выреза видны пласты, на дне - низ модели."))
        self.cut.toggled.connect(self._options)
        options.addRow(self.cut)
        self.under = QCheckBox(tr("Камера под землёй"), self)
        self.under.setChecked(settings["under"])
        self.under.setToolTip(tr(
            "Камера опускается ниже рельефа до низа модели в её рамке. "
            "Над моделью камера ходит по её низу, а не по рельефу."))
        self.under.toggled.connect(self._options)
        options.addRow(self.under)
        layout.addLayout(options)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(self)
        template = QPushButton(tr("Создать шаблон…"), self)
        template.setToolTip(tr(
            "Записать файл GeoPackage со всеми таблицами режима и примером "
            "у точки взгляда - скважина, разрез, тоннель и вырез - и "
            "добавить его в проект группой слоёв. Таблицы заполняются "
            "своими данными, глобус показывает их после правки."))
        template.clicked.connect(self._template)
        buttons.addButton(template, enum(QDialogButtonBox, "ButtonRole",
                                         "ActionRole"))
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def _template(self):
        start = QgsProject.instance().homePath() or os.path.expanduser("~")
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Создать шаблон"), os.path.join(start, "subsurface.gpkg"),
            tr("GeoPackage (*.gpkg)"))
        if not path:
            return
        if not path.lower().endswith(".gpkg"):
            path += ".gpkg"
        self.template_requested.emit(path)

    def _options(self, *args):
        self.options.emit(self.settings())

    def settings(self):
        return {"opacity": self.opacity.value() / 100.0,
                "cut": self.cut.isChecked(),
                "under": self.under.isChecked()}


class SubsurfaceManager(QObject):
    """Подземный режим окна глобуса: модель, высоты, сетки, вырез."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.settings = read_settings()
        self.model = None
        self.picks = []  # оси скважин и тоннелей для окна «Объекты»
        # Роли и кровли отмеченных слоёв проекта, по которым построено.
        self._project_key = None
        self._mask_key = None  # рамка и кольца выреза нынешней маски
        # Метки «Моих меток», по которым режется модель: ключ - "cut"
        # (многоугольник выреза) или "section" (стенка разреза).
        self.place_parts = {}
        self._places_key = None
        self.dialog = None
        self.tiles = None
        self.job = None
        self.scale = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)

    def open_dialog(self):
        if self.dialog is None:
            self.dialog = SubsurfaceDialog(self.settings, self.window)
            self.dialog.options.connect(self.set_options)
            self.dialog.template_requested.connect(self.make_template)
        self.dialog.show()
        self.dialog.raise_()

    def toggle_place(self, key, kind):
        """Метка key - вырез ("cut") или стенка разреза ("section")
        модели, повторный вызов убирает. Возвращает, включена ли."""
        if self.place_parts.get(key) == kind:
            del self.place_parts[key]
            on = False
        else:
            self.place_parts[key] = kind
            on = True
            if kind == "cut" and not self.settings.get("cut"):
                self.settings = dict(self.settings, cut=True)
                if self.dialog is not None:
                    self.dialog.cut.setChecked(True)
        self._places_key = self._place_shapes_key()
        self.apply()
        return on

    def _place_shapes_key(self):
        places = self.window.myplaces
        out = []
        for key, kind in sorted(self.place_parts.items()):
            place = places.find(key)
            if place is not None:
                out.append((key, kind, tuple(map(tuple,
                                                 place.shape.points))))
        return tuple(out)

    def places_changed(self):
        """«Мои метки» изменились: форма метки выреза или разреза могла
        стать другой, модель собирается заново."""
        if not self.place_parts:
            return
        key = self._place_shapes_key()
        if key != self._places_key:
            self._places_key = key
            self.apply()

    def _with_places(self, model):
        """Модель с вырезами и стенками разрезов по меткам: копия списков
        rings, mask_rings и sections, данные слоёв не меняются."""
        if not self.place_parts:
            return model
        out = copy.copy(model)
        out.rings = list(model.rings)
        out.mask_rings = list(model.mask_rings)
        out.sections = list(model.sections)
        step = max(model.extent() / SECTION_POINTS, 5.0) / 111000.0
        for key, kind in self.place_parts.items():
            place = self.window.myplaces.find(key)
            if place is None or len(place.shape.points) < 2:
                continue
            pts = np.array(place.shape.points, dtype=np.float64)
            if kind == "cut" and len(pts) >= 3:
                closed = np.vstack([pts, pts[:1]])
                out.rings.append(core.densify(closed, step)[:-1])
                out.mask_rings.append(pts)
            elif kind == "section":
                out.sections.append(core.densify(pts, step))
        return out

    def from_project(self):
        """Модель построена из отмеченных слоёв проекта."""
        return self.model is not None and self._project_key is not None

    def sync_project(self, layer_ids, restyle=False):
        """Отмеченные слои проекта в порядке карты: геологические из них
        строят модель, как обычные слои глобуса. restyle - слои
        перерисованы в QGIS (стиль, прозрачность, данные), модель
        собирается заново. Возвращает номера слоёв, которые ушли
        в подземное, - наложение их не рисует."""
        project = QgsProject.instance()
        layers = [project.mapLayer(i) for i in layer_ids]
        layers = [layer for layer in layers if layer is not None]
        roles, roofs = project_roles(layers)
        used = set(roles.values()) | set(roofs)
        if used:
            # Таблицы без геометрии - интервалы, инклинометрия, пласты -
            # в списке глобуса без флажка. Они берутся из проекта, сперва
            # из той же группы, что отмеченные геологические слои.
            for role, layer_id in table_roles(used).items():
                roles.setdefault(role, layer_id)
        key = (tuple(sorted(roles.items())), tuple(roofs))
        if key == self._project_key and not restyle:
            return used
        self._project_key = key
        solid = {"collar", "tunnels", "images", "sections", "cut"}
        if not (set(roles) & solid or roofs):
            if self.model is not None:
                self.clear()
            return used
        self.start(dict(self.settings, layers=roles, horizons=roofs))
        return used

    def make_template(self, path):
        """Шаблон данных у точки взгляда, файл path, и его постройка."""
        pose = self.view.navigator.pose
        lat, lon = pose.lat, pose.lon
        ground = float(self._ground(np.array([lat]), np.array([lon]))[0])
        try:
            write_template(path, lat, lon, ground)
        except RuntimeError as error:
            self._status(tr("Шаблон не записан: {error}", error=str(error)))
            return
        self.window.subsurface_layers(
            tr("Шаблон подземного"), path, ROLES, (),
            opacity=self.settings["opacity"], cut=True)

    def _status(self, text):
        if self.dialog is not None:
            self.dialog.status.setText(text)

    def start(self, settings):
        """Прочитать данные и дождаться высот рельефа под моделью."""
        self.settings = dict(settings)
        write_settings(self.settings)
        self.model = load(self.settings)
        box = self.model.box()
        if box is None:
            self.model = None
            self._status(tr("Данных нет: нужны устья скважин, "
                            "кровли пластов или тоннели."))
            return
        south, north, west, east = box
        lat, lon = (south + north) / 2, (west + east) / 2
        radius = self.model.extent() / 2 + 200.0
        _, keys = viewshed.height_tiles(lat, lon, radius, 20.0,
                                        ellipsoid.A,
                                        self.view.store.max_level)
        self.job = {"keys": keys, "at": time.monotonic()}
        self.timer.start()
        self._poll()

    def _poll(self):
        job = self.job
        if job is None:
            self.timer.stop()
            return
        missing = [k for k in job["keys"]
                   if not self.window._has_height_tile(k)]
        if missing and time.monotonic() - job["at"] < WAIT:
            self.view.want_tool_heights(missing)
            self._status(tr("Загрузка высот: {done} из {total}",
                            done=len(job["keys"]) - len(missing),
                            total=len(job["keys"])))
            return
        self.timer.stop()
        self.job = None
        self.apply()

    def _ground(self, lats, lons):
        return np.asarray(self.view.store.heights_at(
            np.asarray(lats), np.asarray(lons), scaled=False),
            dtype=np.float64)

    def apply(self):
        """Собрать сетки по модели, масштабу и вырезу и показать."""
        model = self.model
        if model is None:
            return
        scale = self.view.store.scale
        self.scale = scale
        model = self._with_places(model)
        cut = self.settings["cut"] and bool(model.rings)
        meshes, marks, self.picks = build(model, scale, self._ground, cut)
        self.view.image_walls.set_walls(build_images(model, scale,
                                                     self._ground))
        self._show_legend(model)
        for name in ("wells", "horizons", "sections"):
            self.view.subsurface.set_mesh(name, meshes.get(name))
        self.view.subsurface_marks = marks
        self._set_cut(cut, model)
        self.set_options(self.settings, rebuild=False)
        vertices = sum(len(m.vertices) for m in meshes.values()
                       if m is not None)
        text = tr("Скважин {holes}, кровель {horizons}, разрезов "
                  "{sections}. Вершин {vertices}.",
                  holes=len(model.holes), horizons=len(model.horizons),
                  sections=len(model.sections), vertices=vertices)
        if model.tunnels:
            text += " " + tr("Тоннелей {count}.", count=len(model.tunnels))
        if model.images:
            text += " " + tr("Разрезов с картинками {count}.",
                             count=len(model.images))
        if model.missing:
            text += " " + tr("Не найдены {names}.",
                             names=", ".join(model.missing))
        if model.skipped:
            text += " " + tr("Пропущено строк - {count}.",
                             count=sum(model.skipped.values()))
        self._status(text)
        self.view.update()

    def _set_cut(self, on, model=None):
        """Маска при модели есть всегда: рамка модели для прозрачности,
        кольца выреза - если вырез включён (on). Та же рамка и те же
        кольца - прежняя маска остаётся: после правки стиля слоя модель
        собирается заново, а поверхность не мигает непрозрачной."""
        # model - модель с вырезами по меткам (_with_places).
        model = model or self.model
        rings = model.mask_rings if (on and model) else []
        key = None if model is None else (
            model.box(), tuple(r.tobytes() for r in rings))
        if key is not None and key == self._mask_key \
                and self.tiles is not None:
            return
        self._mask_key = key
        old = self.tiles
        if old is not None:
            old.abort()
            old.deleteLater()
        self.tiles = None
        if self.model is None:
            self.view.set_gibs("cut", False)
            return
        mask = CutMask(model.box(), rings)
        tiles = ResultTiles(mask, ellipsoid.A, cut_rgba, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("cut", key, levels))
        self.view.set_gibs("cut", True, tiles, keep=old is not None)
        self.tiles = tiles

    def set_options(self, settings, rebuild=True):
        """Прозрачность, вырез и камера под землёй без чтения данных."""
        cut_changed = settings["cut"] != self.settings["cut"]
        for key in ("opacity", "cut", "under"):
            self.settings[key] = settings[key]
        write_settings(self.settings)
        if self.model is None:
            return
        self.view.surface_alpha = float(self.settings["opacity"])
        self.view.floor = self._floor() if self.settings["under"] else None
        if rebuild and cut_changed:
            self.apply()
            return
        self.view.update()

    def _floor(self):
        """Пол навигации: низ модели в её рамке с запасом 20 %."""
        south, north, west, east = self.model.box()
        dlat, dlon = (north - south) * 0.2, (east - west) * 0.2
        south, north = south - dlat, north + dlat
        west, east = west - dlon, east + dlon
        bottom = self.model.bottom()
        store = self.view.store
        ground = self._ground

        def floor(lat, lon):
            if not (south <= lat <= north and west <= lon <= east):
                return None
            if store.scale:
                return bottom * store.scale
            # Рельеф выключен: низ модели - глубина под поверхностью.
            return bottom - float(ground([lat], [lon])[0])
        return floor

    def relief_changed(self):
        """Масштаб рельефа сменился - сетки заново."""
        if self.model is not None and self.view.store.scale != self.scale:
            self.apply()

    def identify(self, px, py, radius):
        """Скважины и тоннели у пикселя кадра (px, py) для окна
        «Объекты»: [(название, [(поле, значение)], None)]. Ближе radius
        пикселей к оси на экране. Значения - в точке оси под курсором."""
        if self.model is None or not self.picks:
            return []
        camera = self.view.camera
        found = []
        for pick in self.picks:
            pixels, front = camera.project(pick.xyz)
            near = core.nearest_on_screen(pixels, front, px, py)
            if near is None or near[0] > radius:
                continue
            gap, i, t = near
            j = min(i + 1, len(pick.values) - 1)
            at = pick.values[i] * (1.0 - t) + pick.values[j] * t
            found.append((gap, self._pick_feature(pick, at)))
        found.sort(key=lambda item: item[0])
        return [feature for _, feature in found]

    def _pick_feature(self, pick, at):
        def metres(value):
            return tr("{value} м", value="{:.1f}".format(float(value)))
        if pick.kind == "tunnel":
            name, diameter = pick.name
            return (name or tr("Тоннель"), [
                (tr("Глубина оси"), metres(at[1])),
                (tr("Отметка оси"), metres(at[0])),
                (tr("Диаметр"), metres(diameter))], None)
        hole = pick.name
        md = float(at[0])
        values = [(tr("Глубина по стволу"), metres(md)),
                  (tr("Глубина под устьем"), metres(at[2])),
                  (tr("Отметка"), metres(at[1])),
                  (tr("Глубина забоя"), metres(hole.eoh))]
        for interval in hole.intervals:
            if interval.start <= md <= interval.end:
                values.insert(0, (tr("Пласт"), interval.code or "-"))
                break
        return (tr("Скважина {name}", name=hole.hole_id), values, None)

    def _show_legend(self, model):
        """Шкала пластов: пласты сверху вниз, тоннели, разрезы
        с картинками."""
        items = [(model.color(code), code) for code in model.beds if code]
        names = []
        for name, _, _, _, color in model.tunnels:
            if name not in names:
                names.append(name)
                items.append((color, name or tr("Тоннель")))
        legend = self.window.beds_legend
        legend.set_items(items)
        legend.setVisible(bool(items))
        self.window._place_attribution()

    def clear(self):
        self.window.beds_legend.hide()
        self._project_key = None
        self.job = None
        self.timer.stop()
        self.model = None
        self.picks = []
        self.view.image_walls.set_walls([])
        self.view.subsurface.clear()
        self.view.subsurface_marks = []
        self._set_cut(False)
        self.view.surface_alpha = 1.0
        self.view.floor = None
        self._status("")
        self.view.update()

    def project_reloaded(self):
        """Другой проект: подземное прежнего убирается, настройки -
        его. Окно строится заново, в нём слои нового проекта."""
        self.clear()
        self.settings = read_settings()
        if self.dialog is not None:
            self.dialog.close()
            self.dialog.deleteLater()
            self.dialog = None

    def close(self):
        self.timer.stop()
        if self.tiles is not None:
            self.tiles.abort()
        if self.dialog is not None:
            self.dialog.close()
