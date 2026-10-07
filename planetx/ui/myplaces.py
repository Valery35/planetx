# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""«Мои метки» - сохранённые объекты глобуса, как в Google Earth.

Хранятся в одном файле GeoPackage в папке профиля QGIS и видны в любом
проекте. Решение автора от 27 сентября 2026 года. В файле три слоя
в WGS84: точки, линии, многоугольники. Файл - обычный источник QGIS,
его слои можно добавить в проект.

Запись идёт в сам источник через dataProvider, без буфера правки.

Сохранённый вид - точка на месте взгляда с полем view: расстояние
до точки, азимут и наклон камеры. Закладки QGIS для этого не нужны,
решение автора от 27 сентября 2026 года. Поле view появилось после 0.4.1,
в прежний файл оно добавляется при открытии.

Папки лежат в таблице folders без геометрии: название, родитель,
номер среди соседей, флажок и раскрыта ли папка. У метки поле folder -
номер её папки, пусто - корень. Порядок меток и папок одного родителя
задаёт поле position, по нему идёт и тур (core/placetree.py). Поля
position и folder и таблица папок добавлены 28 сентября 2026 года,
в прежний файл - при открытии.
"""
import base64
import json
import os
import time

from qgis.core import (QgsApplication, QgsCoordinateReferenceSystem,
                       QgsFeature, QgsGeometry, QgsPointXY,
                       QgsProject, QgsVectorFileWriter, QgsVectorLayer)
from qgis.PyQt.QtCore import QObject, pyqtSignal

from ..core import (ellipsoid, icons, lookat, overlays, placetree,
                    region, when)
from ..core.features import Shape
from ..core.kml import KFolder, KOverlay, KPlace
from ..i18n import tr
from ..qt_compat import enum

FILE_NAME = "myplaces.gpkg"
# Слой файла по виду объекта и вид геометрии слоя.
TABLES = {"point": ("points", "Point"), "line": ("lines", "LineString"),
          "polygon": ("polygons", "Polygon")}
FIELDS = (("name", "string"), ("description", "string"),
          ("color", "string"), ("width", "double"), ("fill", "string"),
          ("visible", "integer"), ("measure", "string"),
          ("created", "string"), ("view", "string"),
          ("position", "integer"), ("folder", "integer"),
          ("height", "double"), ("extrude", "integer"),
          ("icon", "string"), ("time", "string"),
          ("view_time", "string"),
          # Записанный тур длиннее 255 знаков, поле без предела длины.
          ("tour", "string(0)"),
          # Высоты вершин 3D-пути и 3D-многоугольника, JSON.
          ("alts", "string(0)"),
          # Тело метки: earth, mars или moon. Пустое - Земля.
          ("body", "string"),
          # Region KML - видна только вблизи, core/region.py, JSON.
          ("region", "string"))
FOLDER_TABLE = "folders"
# Наложения картинок, 5 октября 2026 года: геометрия - углы картинки
# на поверхности, у картинки на экране и фото пусто. params - свойства
# core.overlays, image - номер картинки в таблице images, href - адрес
# картинки из KML, пока её нет. Картинки - текст base64 в том же файле,
# решение автора того же дня.
OVERLAY_TABLE = "overlays"
OVERLAY_FIELDS = (("name", "string"), ("description", "string"),
                  ("kind", "string"), ("visible", "integer"),
                  ("position", "integer"), ("folder", "integer"),
                  ("created", "string"), ("view", "string"),
                  ("time", "string"), ("body", "string"),
                  ("image", "integer"), ("href", "string(0)"),
                  ("params", "string(0)"))
IMAGE_TABLE = "images"
IMAGE_FIELDS = (("name", "string"), ("data", "string(0)"))
# description, view, radio и expandable - окно свойств папки, как
# у Google Earth, 2 октября 2026 года. Прежний файл получает их при
# открытии, пустые значения - описания и вида нет, папка обычная.
FOLDER_FIELDS = (("name", "string"), ("parent", "integer"),
                 ("position", "integer"), ("visible", "integer"),
                 ("expanded", "integer"), ("description", "string"),
                 ("view", "string"), ("radio", "integer"),
                 ("expandable", "integer"), ("region", "string"))
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


def _int(value):
    """Целое из поля или None, если поле пустое."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value):
    """Число из поля или 0, если поле пустое."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _folder_key(fid):
    """Ключ папки по номеру, None и 0 - корень."""
    return "{}:{}".format(placetree.FOLDER, fid) if fid else None


def _folder_fid(key):
    return int(key.split(":")[1]) if key else None


def _geometry(kind, points):
    xy = [QgsPointXY(lon, lat) for lat, lon in points]
    if kind == "point":
        return QgsGeometry.fromPointXY(xy[0])
    if kind == "line":
        return QgsGeometry.fromPolylineXY(xy)
    return QgsGeometry.fromPolygonXY([xy + xy[:1]])


def _add_missing(layer, fields=None):
    """Добавить в слой файла поля, которых в нём ещё нет, None - поля
    меток FIELDS на момент вызова.

    Поле берётся из слоя в памяти, так его тип задаётся одинаково
    в Qt 5 и Qt 6.
    """
    fields = FIELDS if fields is None else fields
    names = set(layer.fields().names())
    missing = [(n, t) for n, t in fields if n not in names]
    if not missing:
        return
    spec = "&".join("field={}:{}".format(n, t) for n, t in missing)
    memory = QgsVectorLayer("Point?" + spec, "fields", "memory")
    if layer.dataProvider().addAttributes(list(memory.fields())):
        layer.updateFields()


def tour_text(samples):
    """Записанный тур для поля файла: JSON, 7 знаков в градусах."""
    if not samples:
        return ""
    return json.dumps([[round(t, 3), round(lat, 7), round(lon, 7),
                        round(d, 2), round(h, 3), round(k, 3)]
                       for t, lat, lon, d, h, k in samples])


def tour_from_text(text):
    """Записанный тур из поля файла или None."""
    if not text:
        return None
    try:
        data = json.loads(str(text))
    except ValueError:
        return None
    samples = [tuple(float(v) for v in row) for row in data
               if isinstance(row, list) and len(row) == 6]
    return samples if len(samples) >= 2 else None


def alts_text(alts):
    """Высоты вершин 3D-объекта для поля файла: JSON, миллиметры."""
    if not alts:
        return ""
    return json.dumps([round(float(a), 3) for a in alts])


def alts_from_text(text, count):
    """Высоты вершин из поля файла, если их столько же, сколько вершин,
    иначе None."""
    if not text:
        return None
    try:
        data = json.loads(str(text))
    except ValueError:
        return None
    if not isinstance(data, list) or len(data) != count:
        return None
    try:
        return tuple(float(a) for a in data)
    except (TypeError, ValueError):
        return None


def _value(feature, layer, name):
    """Значение поля или None, если поля в слое нет."""
    return feature[name] if layer.fields().indexOf(name) >= 0 else None


def _kplace(place):
    """Метка «Моих меток» как метка core.kml."""
    shape = place.shape
    return KPlace(shape.name, shape.kind, list(shape.points),
                  color=shape.color, width=shape.width, fill=shape.fill,
                  visible=place.visible, view=place.view,
                  description=place.description or place.measure,
                  height=shape.height, extrude=shape.extrude,
                  icon=shape.icon, time=place.time,
                  view_time=place.view_time, tour=place.tour,
                  alts=shape.alts, region=place.region)


class Place:
    """Метка из файла: ключ (вид, номер объекта), объект и видимость."""

    def __init__(self, kind, fid, shape, visible, measure="", view=None,
                 position=None, folder=None, description="",
                 time=None, view_time=None, tour=None, body="earth",
                 region=None):
        self.kind = kind
        # Region KML: метка видна только вблизи, core.region или None.
        self.region = region
        # Тело, на котором стоит метка: earth, mars или moon.
        self.body = body
        # Записанный тур: позы core.tour.RecordedStop или None.
        self.tour = tour
        # Время метки и её вида, пары строк core.when или None.
        self.time = time
        self.view_time = view_time
        self.description = description
        self.position = position
        self.fid = fid
        self.shape = shape
        self.visible = visible
        self.measure = measure
        self.view = view
        self.folder = folder  # ключ папки или None - корень

    @property
    def key(self):
        return "{}:{}".format(self.kind, self.fid)

    @property
    def name(self):
        return self.shape.name



def _kfolder(folder):
    """Папка «Моих меток» папкой core.kml, без детей."""
    return KFolder(folder.name, folder.visible,
                   description=folder.description, view=folder.view,
                   radio=folder.radio, expandable=folder.expandable,
                   region=folder.region)

class Folder:
    """Папка «Моих меток»."""

    def __init__(self, fid, name, parent, position, visible, expanded,
                 description="", view=None, radio=False, expandable=True,
                 region=None):
        self.region = region  # Region KML папки, core.region или None
        self.fid = fid
        self.name = name
        self.parent = parent  # ключ папки-родителя или None - корень
        self.position = position
        self.visible = visible
        self.expanded = expanded
        self.description = description
        self.view = view  # вид core.lookat или None
        self.radio = radio  # содержимое - группа переключателей
        self.expandable = expandable  # папку можно раскрыть

    @property
    def key(self):
        return _folder_key(self.fid)


class OverlayItem:
    """Наложение из файла: картинка на поверхности, на экране или фото.

    overlay - core.overlays.Overlay, image - номер картинки в таблице
    images. shape - углы картинки на поверхности многоугольником для
    правки вершин окном свойств, у прочих - точка."""

    tour = None
    measure = ""
    view_time = None

    def __init__(self, fid, overlay, name, visible, position=None,
                 folder=None, description="", view=None, time=None,
                 image=None, href="", body="earth"):
        self.fid = fid
        self.overlay = overlay
        self.visible = visible
        self.position = position
        self.folder = folder
        self.description = description
        self.view = view
        self.time = time
        self.image = image
        self.href = href
        self.body = body
        points = overlay.corners or ([overlay.camera[:2]]
                                     if overlay.camera else [(0.0, 0.0)])
        self.shape = Shape("polygon" if overlay.kind == "ground" else "point",
                           [tuple(p) for p in points],
                           color=(255, 255, 255, 255), width=1.0,
                           name=name)

    @property
    def kind(self):
        return self.overlay.kind

    @property
    def key(self):
        return "{}:{}".format(self.kind, self.fid)

    @property
    def name(self):
        return self.shape.name

class MyPlaces(QObject):
    """Файл «Моих меток», метки и папки в памяти."""

    changed = pyqtSignal()

    def __init__(self, path=None, parent=None):
        super().__init__(parent)
        self.path = path or store_path()
        self.places = []
        self.folders = []
        self.overlays = []
        self.layers = {}
        self.folder_layer = None
        self.overlay_layer = None
        self.image_layer = None
        self._images = {}  # номер картинки - байты, прочитанные

    # Файл.

    def _write_table(self, table, uri, first):
        options = QgsVectorFileWriter.SaveVectorOptions()
        options.driverName = "GPKG"
        options.layerName = table
        if not first:
            options.actionOnExistingFile = enum(
                QgsVectorFileWriter, "ActionOnExistingFile",
                "CreateOrOverwriteLayer")
        memory = QgsVectorLayer(uri, table, "memory")
        QgsVectorFileWriter.writeAsVectorFormatV3(
            memory, self.path, QgsProject.instance().transformContext(),
            options)

    @staticmethod
    def _spec(fields):
        return "&".join("field={}:{}".format(n, t) for n, t in fields)

    def _create(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        for n, (kind, (table, geometry)) in enumerate(TABLES.items()):
            self._write_table(table, "{}?crs=EPSG:4326&{}".format(
                geometry, self._spec(FIELDS)), n == 0)
        self._write_table(FOLDER_TABLE, "None?" + self._spec(FOLDER_FIELDS),
                          False)

    def _open(self, table):
        return QgsVectorLayer("{}|layername={}".format(self.path, table),
                              table, "ogr")

    def load(self):
        """Открыть файл, создать его при первом запуске, прочитать метки."""
        if not os.path.exists(self.path):
            self._create()
        self.layers = {}
        for kind, (table, _) in TABLES.items():
            layer = self._open(table)
            if layer.isValid():
                _add_missing(layer)
                self.layers[kind] = layer
        folders = self._open(FOLDER_TABLE)
        if not folders.isValid():
            # Файл до папок: таблица добавляется в него.
            self._write_table(FOLDER_TABLE,
                              "None?" + self._spec(FOLDER_FIELDS), False)
            folders = self._open(FOLDER_TABLE)
        if folders.isValid():
            _add_missing(folders, FOLDER_FIELDS)
            self.folder_layer = folders
        self.overlay_layer = self._table(
            OVERLAY_TABLE, "Polygon?crs=EPSG:4326&", OVERLAY_FIELDS)
        self.image_layer = self._table(IMAGE_TABLE, "None?", IMAGE_FIELDS)
        self._read()

    def _table(self, table, geometry, fields):
        """Таблица файла, при нужде созданная, с недостающими полями."""
        layer = self._open(table)
        if not layer.isValid():
            self._write_table(table, geometry + self._spec(fields), False)
            layer = self._open(table)
        if not layer.isValid():
            return None
        _add_missing(layer, fields)
        return layer

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
                    name=str(feature["name"] or ""),
                    height=max(_float(_value(feature, layer, "height")),
                               0.0),
                    extrude=bool(_int(_value(feature, layer, "extrude"))),
                    icon=icons.normal(str(_value(feature, layer, "icon")
                                          or icons.DEFAULT)),
                    alts=alts_from_text(_value(feature, layer, "alts"),
                                        len(points)))
                visible = _int(feature["visible"])
                self.places.append(Place(
                    kind, feature.id(), shape,
                    bool(1 if visible is None else visible),
                    str(feature["measure"] or ""),
                    lookat.parse(_value(feature, layer, "view"),
                                 points[0] if points else None),
                    _int(_value(feature, layer, "position")),
                    _folder_key(_int(_value(feature, layer, "folder"))),
                    str(feature["description"] or ""),
                    when.unpack(_value(feature, layer, "time")),
                    when.unpack(_value(feature, layer, "view_time")),
                    tour_from_text(_value(feature, layer, "tour")),
                    str(_value(feature, layer, "body") or "earth"),
                    region.parse(_value(feature, layer, "region"))))
        self.overlays = []
        layer = self.overlay_layer
        if layer is not None:
            for feature in layer.getFeatures():
                kind = str(feature["kind"] or "")
                if kind not in overlays.KINDS:
                    continue
                corners = _points("polygon", feature.geometry()) \
                    if kind == "ground" else None
                overlay = overlays.from_params(kind, feature["params"],
                                               corners)
                if kind == "ground" and len(overlay.corners) != 4:
                    continue
                if kind == "photo" and not overlay.camera:
                    continue
                visible = _int(feature["visible"])
                self.overlays.append(OverlayItem(
                    feature.id(), overlay, str(feature["name"] or ""),
                    bool(1 if visible is None else visible),
                    _int(feature["position"]),
                    _folder_key(_int(feature["folder"])),
                    str(feature["description"] or ""),
                    lookat.parse(feature["view"], None),
                    when.unpack(feature["time"]), _int(feature["image"]),
                    str(feature["href"] or ""),
                    str(feature["body"] or "earth")))
        self.folders = []
        if self.folder_layer is not None:
            layer = self.folder_layer
            for feature in layer.getFeatures():
                visible = _int(feature["visible"])
                expandable = _int(_value(feature, layer, "expandable"))
                self.folders.append(Folder(
                    feature.id(), str(feature["name"] or ""),
                    _folder_key(_int(feature["parent"])),
                    _int(feature["position"]),
                    bool(1 if visible is None else visible),
                    bool(_int(feature["expanded"]) or 0),
                    str(_value(feature, layer, "description") or ""),
                    lookat.parse(_value(feature, layer, "view"), None),
                    bool(_int(_value(feature, layer, "radio")) or 0),
                    bool(1 if expandable is None else expandable),
                    region.parse(_value(feature, layer, "region"))))
        # Метка или папка в папке, которой нет, стоит в корне.
        known = {f.key for f in self.folders}
        for place in self.places + self.overlays:
            if place.folder not in known:
                place.folder = None
        for folder in self.folders:
            if folder.parent not in known or folder.parent == folder.key:
                folder.parent = None
        order = {n.key: i for i, n in enumerate(placetree.walk(self.nodes()))}
        self.places.sort(key=lambda p: order.get(p.key, 0))
        self.changed.emit()

    def nodes(self):
        """Узлы дерева для core/placetree.py."""
        return ([placetree.Node(p.key, p.folder, p.position, p.name)
                 for p in self.places + self.overlays]
                + [placetree.Node(f.key, f.parent, f.position, f.name)
                   for f in self.folders])

    def tree(self, parent=None):
        """Дети папки parent по порядку: (Folder, дети) или Place."""
        by_key = {p.key: p for p in self.places + self.overlays}
        by_key.update({f.key: f for f in self.folders})
        out = []
        for node in placetree.children(self.nodes(), parent):
            item = by_key[node.key]
            if placetree.is_folder(node.key):
                out.append((item, self.tree(node.key)))
            else:
                out.append(item)
        return out

    # Метки.

    def shapes(self):
        """Видимые метки для глобуса."""
        return [p.shape for p in self.places if p.visible]

    def find(self, key):
        if placetree.is_folder(key):
            return next((f for f in self.folders if f.key == key), None)
        return next((p for p in self.places + self.overlays
                     if p.key == key), None)

    def places_in(self, folder=None):
        """Метки папки folder и её вложенных папок по порядку списка."""
        inside = set(placetree.descendants(self.nodes(), folder)) \
            if folder else None
        return [p for p in self.places if inside is None or p.key in inside]

    def add(self, shape, measure="", view=None, folder=None, period=None,
            view_period=None, tour=None, body=None):
        """Записать новую метку в конец папки folder, None - корень.

        Возвращает её ключ или None. view - вид метки core.lookat.
        body - тело метки, None - текущее тело глобуса. У метки неба
        body "sky": точка - склонение и прямое восхождение.
        """
        layer = self.layers.get(shape.kind)
        if layer is None or not shape.points:
            return None
        if folder is not None and self.find(folder) is None:
            folder = None
        feature = QgsFeature(layer.fields())
        feature.setGeometry(_geometry(shape.kind, shape.points))
        values = {"name": shape.name, "description": "",
                  "color": _color_text(shape.color),
                  "width": float(shape.width),
                  "fill": _color_text(shape.fill), "visible": 1,
                  "measure": measure,
                  "created": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "view": lookat.text(view),
                  "position": placetree.next_position(self.nodes(), folder),
                  "folder": _folder_fid(folder),
                  "height": float(shape.height or 0.0),
                  "extrude": int(bool(shape.extrude)),
                  "icon": shape.icon, "time": when.pack(period),
                  "view_time": when.pack(view_period),
                  "tour": tour_text(tour), "alts": alts_text(shape.alts),
                  "body": body or ellipsoid.BODY.key}
        for name, value in values.items():
            if layer.fields().indexOf(name) >= 0:
                feature[name] = value
        ok, added = layer.dataProvider().addFeatures([feature])
        self._read()
        return "{}:{}".format(shape.kind, added[0].id()) if ok else None

    def add_folder(self, name, parent=None, after=None):
        """Новая папка в папке parent: в конце или сразу под узлом after
        той же папки. Возвращает её ключ."""
        layer = self.folder_layer
        if layer is None:
            return None
        feature = QgsFeature(layer.fields())
        for field, value in (
                ("name", name), ("parent", _folder_fid(parent)),
                ("position", placetree.next_position(self.nodes(), parent)),
                ("visible", 1), ("expanded", 1)):
            feature[field] = value
        ok, added = layer.dataProvider().addFeatures([feature])
        key = _folder_key(added[0].id()) if ok else None
        siblings = [n.key for n in placetree.children(self.nodes(), parent)]
        if key is not None and after in siblings:
            self._read_quiet()
            self.move(key, parent, siblings.index(after) + 1)
            return key
        self._read()
        return key

    def _read_quiet(self):
        """Перечитать файл без сигнала: следом идёт ещё правка."""
        self.blockSignals(True)
        try:
            self._read()
        finally:
            self.blockSignals(False)

    def _layer_of(self, key):
        if placetree.is_folder(key):
            return self.folder_layer
        kind = key.split(":")[0]
        if kind in overlays.KINDS:
            return self.overlay_layer
        return self.layers.get(kind)

    def _write(self, changes, read=True):
        """Записать {ключ: {поле: значение}} одной правкой на слой."""
        per_layer = {}
        for key, values in changes.items():
            layer = self._layer_of(key)
            item = self.find(key)
            if layer is None or item is None:
                continue
            attrs = {layer.fields().indexOf(n): v for n, v in values.items()
                     if layer.fields().indexOf(n) >= 0}
            if attrs:
                per_layer.setdefault(id(layer), (layer, {}))[1][
                    item.fid] = attrs
        for layer, values in per_layer.values():
            layer.dataProvider().changeAttributeValues(values)
        if read:
            self._read()

    def move(self, key, parent, index):
        """Перенести метку или папку в папку parent перед её ребёнком
        номер index, как перетаскиванием мышью."""
        self.move_many([key], parent, index)

    def move_many(self, keys, parent, index):
        """Перенести выбранные метки и папки подряд, одной правкой."""
        plan = placetree.move_many_plan(self.nodes(), keys, parent, index)
        if not plan:
            return
        changes = {}
        for item, (new_parent, position) in plan.items():
            field = "parent" if placetree.is_folder(item) else "folder"
            changes[item] = {field: _folder_fid(new_parent),
                             "position": position}
        self._write(changes)

    def update(self, key, values):
        """Свойства метки из окна свойств: {поле файла: значение}."""
        self._write({key: values})

    def set_shape(self, key, shape):
        """Новая форма метки key после правки вершин на глобусе:
        геометрия, название, цвет и толщина. Вид объекта прежний,
        иначе запись не идёт и возвращается False. Текст измерения
        стирается, он относился к прежней форме."""
        layer = self._layer_of(key)
        item = self.find(key)
        if isinstance(item, OverlayItem):
            # Углы картинки на поверхности после правки в окне свойств.
            if item.kind != "ground" or len(shape.points) != 4:
                return False
            overlay = overlays.from_params("ground", item.overlay.params(),
                                           list(shape.points))
            return self.set_overlay(key, overlay, name=shape.name)
        if layer is None or item is None or not shape.points \
                or shape.kind != item.kind:
            return False
        if not layer.dataProvider().changeGeometryValues(
                {item.fid: _geometry(shape.kind, shape.points)}):
            return False
        self._write({key: {"name": shape.name,
                           "color": _color_text(shape.color),
                           "width": float(shape.width),
                           "fill": _color_text(shape.fill),
                           "measure": ""}})
        return True

    def set_visible_many(self, states):
        """Флажки меток и папок разом: {ключ: включена}."""
        self._write({key: {"visible": 1 if on else 0}
                     for key, on in states.items()})

    def with_contents(self, keys):
        """Ключи вместе со всем содержимым выбранных папок."""
        nodes = self.nodes()
        out = []
        for key in placetree.top_keys(nodes, keys):
            out.append(key)
            if placetree.is_folder(key):
                out += placetree.descendants(nodes, key)
        return out

    def set_visible(self, key, on):
        self.set_visible_many({key: on})

    def set_expanded(self, key, on):
        """Раскрыта ли папка. Список не перестраивается."""
        folder = self.find(key)
        if folder is None or folder.expanded == bool(on):
            return
        folder.expanded = bool(on)
        self._write({key: {"expanded": 1 if on else 0}}, read=False)

    def sort_folder(self, folder=None):
        """Сортировать содержимое папки от А до Я, как Google Earth."""
        plan = placetree.sort_plan(self.nodes(), folder)
        self._write({key: {"position": n} for key, n in plan.items()})

    def remove(self, key):
        """Удалить метку или папку со всем содержимым, как в Google Earth."""
        self.remove_many([key])

    def remove_many(self, chosen):
        """Удалить выбранные метки и папки с содержимым, список
        перечитывается один раз."""
        keys = self.with_contents(chosen)
        per_layer = {}
        for item_key in keys:
            layer = self._layer_of(item_key)
            item = self.find(item_key)
            if layer is not None and item is not None:
                per_layer.setdefault(id(layer), (layer, []))[1].append(
                    item.fid)
        # Картинки удалённых наложений уходят из файла вместе с ними.
        images = [item.image for item in self.overlays
                  if item.key in keys and item.image is not None]
        for layer, fids in per_layer.values():
            layer.dataProvider().deleteFeatures(fids)
        if images and self.image_layer is not None:
            self.image_layer.dataProvider().deleteFeatures(images)
            for fid in images:
                self._images.pop(fid, None)
        self._read()

    # Наложения.

    def image(self, fid):
        """Байты картинки номер fid или None."""
        if fid is None or self.image_layer is None:
            return None
        if fid not in self._images:
            feature = self.image_layer.getFeature(fid)
            text = feature["data"] if feature.isValid() else None
            try:
                self._images[fid] = base64.b64decode(str(text)) \
                    if text else None
            except ValueError:
                self._images[fid] = None
        return self._images[fid]

    def _add_image(self, data, name=""):
        """Записать картинку, вернуть её номер или None."""
        layer = self.image_layer
        if layer is None or not data:
            return None
        feature = QgsFeature(layer.fields())
        feature["name"] = name
        feature["data"] = base64.b64encode(data).decode("ascii")
        ok, added = layer.dataProvider().addFeatures([feature])
        if not ok:
            return None
        self._images[added[0].id()] = bytes(data)
        return added[0].id()

    def _overlay_feature(self, item, folder, position, stamp, body):
        """Объект таблицы наложений из KOverlay."""
        layer = self.overlay_layer
        overlay = item.overlay
        feature = QgsFeature(layer.fields())
        if overlay.kind == "ground":
            feature.setGeometry(_geometry("polygon", overlay.corners))
        values = {"name": item.name, "description": item.description,
                  "kind": overlay.kind, "visible": int(item.visible),
                  "position": position, "folder": _folder_fid(folder),
                  "created": stamp, "view": lookat.text(item.view),
                  "time": when.pack(item.time),
                  "body": body or ellipsoid.BODY.key,
                  "image": self._add_image(item.image, item.name),
                  "href": "" if item.image else item.href,
                  "params": overlay.params()}
        for name, value in values.items():
            feature[name] = value
        return feature

    def add_overlay(self, item, folder=None):
        """Записать наложение KOverlay в конец папки folder. Возвращает
        ключ или None."""
        if self.overlay_layer is None:
            return None
        if folder is not None and self.find(folder) is None:
            folder = None
        feature = self._overlay_feature(
            item, folder, placetree.next_position(self.nodes(), folder),
            time.strftime("%Y-%m-%d %H:%M:%S"), None)
        ok, added = self.overlay_layer.dataProvider().addFeatures([feature])
        self._read()
        return "{}:{}".format(item.overlay.kind, added[0].id()) \
            if ok else None

    def set_overlay(self, key, overlay=None, image=None, link=None,
                    **values):
        """Новые свойства наложения key: overlay - core.overlays.Overlay,
        image - байты новой картинки в файл, link - ссылка на файл или
        адрес вместо картинки в файле, values - поля name, description,
        view, time."""
        item = self.find(key)
        layer = self.overlay_layer
        if not isinstance(item, OverlayItem) or layer is None:
            return False
        changes = dict(values)
        if "view" in changes:
            changes["view"] = lookat.text(changes["view"])
        if "time" in changes:
            changes["time"] = when.pack(changes["time"])
        if overlay is not None:
            changes["params"] = overlay.params()
            if overlay.kind == "ground" and not layer.dataProvider() \
                    .changeGeometryValues({item.fid: _geometry(
                        "polygon", overlay.corners)}):
                return False
        old = item.image
        if image is not None:
            changes["image"] = self._add_image(image, item.name)
            changes["href"] = ""
        elif link is not None:
            # Картинка - по ссылке, копия из файла меток уходит.
            changes["image"] = None
            changes["href"] = link
        if old is not None and "image" in changes \
                and self.image_layer is not None:
            self.image_layer.dataProvider().deleteFeatures([old])
            self._images.pop(old, None)
        self._write({key: changes})
        return True

    def koverlay(self, item):
        """Наложение файла как KOverlay core.kml, с картинкой."""
        return KOverlay(item.name, item.overlay, self.image(item.image),
                        item.href, item.visible, item.description, item.view,
                        item.time)

    # KML и KMZ.

    def import_tree(self, tree, parent=None, wrap=True, body=None):
        """Записать дерево core.kml в папку parent новой папкой.

        Папки создаются по одной, метки пишутся одной правкой на слой,
        список перечитывается один раз. Возвращает ключ новой папки.
        wrap False - содержимое дерева ложится в parent само, без новой
        папки, так идёт вставка из буфера обмена. Тогда возвращается
        None.
        """
        if self.folder_layer is None:
            return None
        per_kind = {}
        found = []  # наложения: (KOverlay, папка, место)

        def folder(node, parent_key, position):
            layer = self.folder_layer
            feature = QgsFeature(layer.fields())
            for field, value in (
                    ("name", node.name), ("parent", _folder_fid(parent_key)),
                    ("position", position), ("visible", int(node.visible)),
                    ("expanded", 0),
                    ("description", getattr(node, "description", "")),
                    ("view", lookat.text(getattr(node, "view", None))),
                    ("radio", int(bool(getattr(node, "radio", False)))),
                    ("expandable",
                     int(bool(getattr(node, "expandable", True)))),
                    ("region", region.text(getattr(node, "region", None)))):
                if layer.fields().indexOf(field) >= 0:
                    feature[field] = value
            ok, added = layer.dataProvider().addFeatures([feature])
            if not ok:
                return None
            key = _folder_key(added[0].id())
            for n, child in enumerate(node.children):
                if isinstance(child, KFolder):
                    folder(child, key, n)
                elif isinstance(child, KOverlay):
                    found.append((child, key, n))
                else:
                    per_kind.setdefault(child.kind, []).append(
                        (child, key, n))
            return key

        start = placetree.next_position(self.nodes(), parent)
        if wrap:
            top = folder(tree, parent, start)
        else:
            top = None
            for n, child in enumerate(tree.children):
                if isinstance(child, KFolder):
                    folder(child, parent, start + n)
                elif isinstance(child, KOverlay):
                    found.append((child, parent, start + n))
                else:
                    per_kind.setdefault(child.kind, []).append(
                        (child, parent, start + n))
        stamp = time.strftime("%Y-%m-%d %H:%M:%S")
        for kind, items in per_kind.items():
            layer = self.layers.get(kind)
            if layer is None:
                continue
            features = []
            for place, key, position in items:
                feature = QgsFeature(layer.fields())
                feature.setGeometry(_geometry(kind, place.points))
                values = {
                    "name": place.name, "description": place.description,
                    "color": _color_text(place.color),
                    "width": float(place.width),
                    "fill": _color_text(place.fill),
                    "visible": int(place.visible), "measure": "",
                    "created": stamp,
                    "view": lookat.text(place.view),
                    "position": position, "folder": _folder_fid(key),
                    "height": float(place.height or 0.0),
                    "extrude": int(bool(place.extrude)),
                    "icon": place.icon, "time": when.pack(place.time),
                    "view_time": when.pack(place.view_time),
                    "tour": tour_text(place.tour),
                    "alts": alts_text(getattr(place, "alts", None)),
                    "body": body or ellipsoid.BODY.key,
                    "region": region.text(getattr(place, "region", None))}
                for name, value in values.items():
                    if layer.fields().indexOf(name) >= 0:
                        feature[name] = value
                features.append(feature)
            layer.dataProvider().addFeatures(features)
        if found and self.overlay_layer is not None:
            self.overlay_layer.dataProvider().addFeatures(
                [self._overlay_feature(item, key, position, stamp, body)
                 for item, key, position in found])
        # Новая папка раскрыта, вложенные - свёрнуты.
        if top is not None:
            self.folder_layer.dataProvider().changeAttributeValues(
                {_folder_fid(top): {self.folder_layer.fields().indexOf(
                    "expanded"): 1}})
        self._read()
        return top

    def export_tree(self, folder=None):
        """Папка folder (None - все «Мои метки») деревом core.kml."""
        item = self.find(folder) if folder else None
        root = _kfolder(item) if item else KFolder(tr("Мои метки"))

        def fill(target, nodes):
            for node in nodes:
                if isinstance(node, tuple):
                    sub, kids = node
                    child = _kfolder(sub)
                    fill(child, kids)
                    target.children.append(child)
                elif isinstance(node, OverlayItem):
                    target.children.append(self.koverlay(node))
                else:
                    target.children.append(_kplace(node))
        fill(root, self.tree(folder))
        return root

    def export_keys(self, keys, name="PlanetX"):
        """Выделенные метки и папки деревом core.kml для буфера обмена.
        Метки внутри выделенной папки идут с ней, а не второй раз."""
        root = KFolder(name)
        for key in placetree.top_keys(self.nodes(), keys):
            if placetree.is_folder(key):
                root.children.append(self.export_tree(key))
            else:
                place = self.find(key)
                if isinstance(place, OverlayItem):
                    root.children.append(self.koverlay(place))
                elif place is not None:
                    root.children.append(_kplace(place))
        return root

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
