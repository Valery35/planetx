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
import json
import math
import os
import time

import numpy as np
from osgeo import gdal, osr
from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsCsException, QgsPointXY,
                       QgsProject, QgsRasterLayer, QgsVectorLayer)
from qgis.gui import QgsMapLayerComboBox
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QDialog,
                                 QDialogButtonBox, QFileDialog, QFormLayout,
                                 QHBoxLayout, QLabel, QLineEdit, QListWidget,
                                 QListWidgetItem, QPushButton, QRadioButton,
                                 QSlider, QVBoxLayout, QWidget)

from ..core import drillholes, ellipsoid, viewshed
from ..core import subsurface as core
from ..core.places import Place
from ..i18n import tr
from ..qt_compat import enum
from .project import ENTRY
from .viewshed import ResultTiles, fit_status

SETTINGS_KEY = "subsurface"
ROLES = ("collar", "interval", "survey", "beds", "sections", "cut")
MAX_NODES = 300  # узлов растра кровли на сторону, больше - прорежение
TUBE_SHARE = 1.0 / 400.0  # радиус ствола - доля поперечника модели
MIN_TUBE = 2.0  # м
SECTION_POINTS = 400  # точек стенки разреза на линию, не больше
BOTTOM_MARGIN = 20.0  # м ниже самой глубокой кровли, если скважин нет
EMPTY_COLOR = (150, 150, 150)
POLL = 250  # мс между проверками высот
WAIT = 30.0  # с ожидания высот
MARK_ID = -700000  # номера подписей устьев
DEFAULTS = {"source": "gpkg", "path": "", "layers": {}, "horizons": [],
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


def shapes_of(layer, kind, step):
    """Линии или кольца слоя в широтах и долготах, точки через step
    единиц системы слоя. Кольцо - без повтора первой точки."""
    to_wgs = QgsCoordinateTransform(layer.crs(), _wgs(),
                                    QgsProject.instance())
    if step is not None and layer.crs().isGeographic():
        step = step / 111000.0
    out = []
    for feature in layer.getFeatures():
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
        for shape in self.sections + self.rings:
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


def _gpkg_layer(path, name):
    layer = QgsVectorLayer("{}|layername={}".format(path, name), name, "ogr")
    return layer if layer.isValid() else None


def load(settings):
    """Модель по настройкам окна. Таблиц может не быть, кроме устьев
    или кровель - нужно хотя бы что-то одно."""
    model = Model()
    layers = {}
    rasters = []
    if settings["source"] == "gpkg":
        path = settings["path"]
        for role in ROLES:
            layers[role] = _gpkg_layer(path, role)
        base = os.path.dirname(path)
    else:
        project = QgsProject.instance()
        for role in ROLES:
            layer_id = settings["layers"].get(role)
            layers[role] = project.mapLayer(layer_id) if layer_id else None
        for layer_id in settings["horizons"]:
            layer = project.mapLayer(layer_id)
            if isinstance(layer, QgsRasterLayer):
                rasters.append((layer.name(), layer.source()))
        base = ""
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
            if surface and settings["source"] == "gpkg":
                rasters.append((code, os.path.join(base, str(surface))))
    for code, path in rasters:
        try:
            model.horizons.append(Horizon(code, path))
        except RuntimeError:
            model.missing.append(os.path.basename(path))
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
    for role in ("collar", "beds"):
        if settings["source"] == "gpkg" and layers[role] is None:
            model.missing.append(role)
    return model


def _to_latlon(lat0, lon0, east, north):
    """Смещения в метрах от устья в широты и долготы."""
    lat = lat0 + np.degrees(np.asarray(north) / ellipsoid.A)
    lon = lon0 + np.degrees(np.asarray(east) / (
        ellipsoid.A * math.cos(math.radians(lat0))))
    return lat, lon


def build(model, scale, ground, cut):
    """Сетки и подписи: словарь имя - Mesh, список подписей устьев.

    ground(lats, lons) - настоящие отметки рельефа. cut - вырез
    блока включён."""
    meshes = {}
    radius = max(MIN_TUBE, model.extent() * TUBE_SHARE)
    wells = []
    marks = []
    for n, (hole, lat0, lon0) in enumerate(model.holes):
        g0 = float(ground(np.array([lat0]), np.array([lon0]))[0])
        pieces = [(i.start, i.end, model.color(i.code))
                  for i in hole.intervals] or [(0.0, hole.eoh, EMPTY_COLOR)]
        for start, end, color in pieces:
            pts = drillholes.piece(hole.axis, start, end)
            lat, lon = _to_latlon(lat0, lon0, pts[:, 0], pts[:, 1])
            alt = core.display(pts[:, 2], scale, g0)
            wells.append(core.tube(core.ecef(lat, lon, alt), radius, color))
        marks.append(Place(MARK_ID - n, hole.hole_id, "layer", 1, lat0,
                           lon0))
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
        surfaces.append(core.grid_surface(
            core.ecef(h.lats, h.lons, alt), valid, model.color(h.code)))
    meshes["horizons"] = core.merge(surfaces, "horizons")
    lines = list(model.sections)
    if cut:
        # Край выреза - замкнутая линия разреза.
        lines += [np.vstack([r, r[:1]]) for r in model.rings]
    walls = []
    # Цвет пласта между соседними поверхностями: над первой кровлей -
    # верхний пласт, под кровлей - пласт этой кровли.
    top = model.beds[0] if model.beds else ""
    colors = [model.color(top)] + [model.color(h.code)
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
    return meshes, marks


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


def _filter(name):
    """Фильтр слоёв для QgsMapLayerComboBox в QGIS 3 и 4."""
    holder = getattr(Qgis, "LayerFilter", None)
    if holder is None:
        from qgis.core import QgsMapLayerProxyModel
        holder = QgsMapLayerProxyModel
    return getattr(holder, name)


class SubsurfaceDialog(QDialog):
    """Окно «Подземный режим». Сигналы: build - настройки, clear -
    убрать всё, options - прозрачность, вырез и камера сменились."""

    build = pyqtSignal(dict)
    clear = pyqtSignal()
    options = pyqtSignal(dict)

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Подземный режим"))
        layout = QVBoxLayout(self)
        self.by_file = QRadioButton(tr("Файл GeoPackage"), self)
        self.by_file.setToolTip(tr(
            "Таблицы collar, interval, survey, beds, sections и cut "
            "в одном файле, как у Isoliner. Кровли пластов - растры, "
            "их файлы названы в поле surface таблицы beds."))
        self.by_project = QRadioButton(tr("Слои проекта"), self)
        self.by_project.setToolTip(tr(
            "Таблицы и растры кровель - слои текущего проекта."))
        group = QButtonGroup(self)
        group.addButton(self.by_file)
        group.addButton(self.by_project)
        layout.addWidget(self.by_file)
        row = QHBoxLayout()
        self.path = QLineEdit(settings["path"], self)
        browse = QPushButton(tr("Обзор…"), self)
        browse.clicked.connect(self._browse)
        row.addWidget(self.path)
        row.addWidget(browse)
        layout.addLayout(row)
        layout.addWidget(self.by_project)
        self.project_box = QWidget(self)
        form = QFormLayout(self.project_box)
        self.combos = {}
        for role, title, kind, tip in (
                ("collar", tr("Устья"), "PointLayer",
                 tr("Точки устьев с полями hole_id, z - отметка устья, eoh - "
                    "глубина забоя по стволу.")),
                ("interval", tr("Интервалы"), "NoGeometry",
                 tr("Таблица hole_id, from, to, code. Глубины по стволу, "
                    "code - пласт или литология, от него цвет.")),
                ("survey", tr("Инклинометрия"), "NoGeometry",
                 tr("Таблица hole_id, depth, azimuth, dip или zenith. "
                    "Без неё скважины вертикальные.")),
                ("beds", tr("Пласты"), "NoGeometry",
                 tr("Таблица code, ord, color - порядок пластов сверху "
                    "вниз и их цвета. Без неё цвет - по коду.")),
                ("sections", tr("Разрезы"), "LineLayer",
                 tr("Линии, вдоль которых строятся стенки разреза "
                    "между кровлями пластов.")),
                ("cut", tr("Вырез"), "PolygonLayer",
                 tr("Многоугольник выреза блока. Внутри него поверхность "
                    "и кровли убираются, по краю встают стенки."))):
            combo = QgsMapLayerComboBox(self.project_box)
            combo.setFilters(_filter(kind))
            combo.setAllowEmptyLayer(True)
            combo.setToolTip(tip)
            layer_id = settings["layers"].get(role)
            layer = QgsProject.instance().mapLayer(layer_id) \
                if layer_id else None
            combo.setLayer(layer)
            form.addRow(title, combo)
            self.combos[role] = combo
        self.rasters = QListWidget(self.project_box)
        self.rasters.setToolTip(tr(
            "Растры отметок кровель пластов. Код пласта - имя слоя."))
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                item = QListWidgetItem(layer.name(), self.rasters)
                item.setData(enum(Qt, "ItemDataRole", "UserRole"),
                             layer.id())
                item.setFlags(item.flags()
                              | enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
                item.setCheckState(enum(Qt, "CheckState", "Checked")
                                   if layer.id() in settings["horizons"]
                                   else enum(Qt, "CheckState", "Unchecked"))
        form.addRow(tr("Кровли"), self.rasters)
        layout.addWidget(self.project_box)
        self.by_file.toggled.connect(self.project_box.setDisabled)
        (self.by_file if settings["source"] == "gpkg"
         else self.by_project).setChecked(True)
        self.project_box.setDisabled(self.by_file.isChecked())
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
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.clicked.connect(lambda: self.build.emit(self.settings()))
        remove = QPushButton(tr("Убрать"), self)
        remove.setToolTip(tr("Убрать подземное с глобуса."))
        remove.clicked.connect(self.clear)
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(run, role)
        buttons.addButton(remove, role)
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("Файл GeoPackage"), self.path.text(),
            tr("GeoPackage (*.gpkg)"))
        if path:
            self.path.setText(path)
            self.by_file.setChecked(True)

    def _options(self, *args):
        self.options.emit(self.settings())

    def settings(self):
        checked = enum(Qt, "CheckState", "Checked")
        role = enum(Qt, "ItemDataRole", "UserRole")
        return {
            "source": "gpkg" if self.by_file.isChecked() else "project",
            "path": self.path.text().strip(),
            "layers": {r: c.currentLayer().id() for r, c in
                       self.combos.items() if c.currentLayer() is not None},
            "horizons": [self.rasters.item(i).data(role)
                         for i in range(self.rasters.count())
                         if self.rasters.item(i).checkState() == checked],
            "opacity": self.opacity.value() / 100.0,
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
            self.dialog.build.connect(self.start)
            self.dialog.clear.connect(self.clear)
            self.dialog.options.connect(self.set_options)
        self.dialog.show()
        self.dialog.raise_()

    def _status(self, text):
        if self.dialog is not None:
            self.dialog.status.setText(text)

    def start(self, settings):
        """Прочитать данные и дождаться высот рельефа под моделью."""
        self.settings = dict(settings)
        write_settings(self.settings)
        if settings["source"] == "gpkg" and not os.path.exists(
                settings["path"]):
            self._status(tr("Файл не найден."))
            return
        self.model = load(self.settings)
        box = self.model.box()
        if box is None:
            self.model = None
            self._status(tr("Данных нет: нужны устья скважин или "
                            "кровли пластов."))
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
        cut = self.settings["cut"] and bool(model.rings)
        meshes, marks = build(model, scale, self._ground, cut)
        for name in ("wells", "horizons", "sections"):
            self.view.subsurface.set_mesh(name, meshes.get(name))
        self.view.subsurface_marks = marks
        self._set_cut(cut)
        self.set_options(self.settings, rebuild=False)
        vertices = sum(len(m.vertices) for m in meshes.values()
                       if m is not None)
        text = tr("Скважин {holes}, кровель {horizons}, разрезов "
                  "{sections}. Вершин {vertices}.",
                  holes=len(model.holes), horizons=len(model.horizons),
                  sections=len(model.sections), vertices=vertices)
        if model.missing:
            text += " " + tr("Не найдены {names}.",
                             names=", ".join(model.missing))
        if model.skipped:
            text += " " + tr("Пропущено строк - {count}.",
                             count=sum(model.skipped.values()))
        self._status(text)
        self.view.update()

    def _set_cut(self, on):
        """Маска при модели есть всегда: рамка модели для прозрачности,
        кольца выреза - если вырез включён (on)."""
        old = self.tiles
        if old is not None:
            old.abort()
            old.deleteLater()
        self.tiles = None
        if self.model is None:
            self.view.set_gibs("cut", False)
            return
        mask = CutMask(self.model.box(),
                       self.model.mask_rings if on else [])
        tiles = ResultTiles(mask, ellipsoid.A, cut_rgba, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("cut", key, levels))
        self.tiles = tiles
        self.view.set_gibs("cut", True, tiles)

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

    def clear(self):
        self.job = None
        self.timer.stop()
        self.model = None
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
