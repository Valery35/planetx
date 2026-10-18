# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Растущие треки из точечных слоёв проекта и камера следом.

Трек - точечный слой проекта с полем времени и, если объектов
несколько, полем объекта. Настройки трека слоя хранятся в проекте.
Время задаёт шкала времени глобуса: к правому бегунку у объекта растёт
пройденный путь, в текущей точке стоит метка с названием объекта.
Шкала закрыта - треки целиком. Временной контроллер QGIS не
слушается, решение автора от 30 сентября 2026 года.

Здесь же время слоёв проекта: слой с действующими временными
свойствами QGIS рисуется на глобусе в промежутке шкалы.

Камера следом держит объект в центре, азимут - по ходу движения,
расстояние и наклон остаются. Между шагами времени камера доезжает
до новой точки плавно (core.track.Glide).

Модель по треку - просьба автора от 18 октября 2026 года. У трека
может быть файл 3D-модели (.glb, .gltf, .dae, .obj): у каждого объекта
модель едет по пути на момент шкалы, азимут - по ходу движения плюс
поворот модели из окна. Вершины модели считаются один раз, вид только
переносит и поворачивает их (render.models.Model.mover).
"""
import json
import math
import os
import time

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsDateTimeRange, QgsFeatureRequest,
                       QgsProject, QgsVectorLayer, QgsWkbTypes)
from qgis.gui import QgsColorButton
from qgis.PyQt.QtCore import (QDate, QDateTime, QObject, Qt, QTime,
                              pyqtSignal)
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QDoubleSpinBox,
                                 QFileDialog, QFormLayout, QHBoxLayout,
                                 QLineEdit, QPushButton, QToolButton,
                                 QVBoxLayout)

from .. import journal
from ..core import models
from ..core.features import Shape
from ..core.navigation import Pose
from ..core.track import Glide, Track
from ..i18n import tr
from ..qt_compat import enum, enum_int
from ..render.models import Model as ModelItem
from .overlays import image_rgba
from .project import ENTRY

TRACK_KEY = "tracks"  # запись проекта: настройки треков по слоям, JSON
TRACK_COLOR = (255, 80, 40, 255)
TRACK_WIDTH = 3.0
# Переход камеры между шагами времени, секунд, в этих пределах.
GLIDE_MIN = 0.05
GLIDE_MAX = 1.0
MODEL_SIDE = 2048  # картинки модели трека не больше, пикселей
# Высота точек трека: из Z точки или поля, над уровнем моря или над
# землёй, в метрах или футах (ADS-B самолётов - в футах).
HEIGHT_Z = "@z"
FOOT = 0.3048
HEIGHT_MODES = ("absolute", "relative")
MODEL_FILTER = "*.glb *.gltf *.dae *.obj"


JULIAN_1970 = 2440588  # юлианский день 1 января 1970 года


def seconds(value):
    """Время поля в секундах от 1970 года или None.

    Считается по показаниям часов, без часового пояса. Временной
    контроллер QGIS 3.36 отдаёт промежуток с тем же временем на часах,
    но в UTC, а время точек остаётся местным. Треки уходили на смещение
    пояса, 28 сентября 2026 года.
    """
    if isinstance(value, QDateTime):
        if not value.isValid():
            return None
        return (value.date().toJulianDay() - JULIAN_1970) * 86400.0 \
            + value.time().msecsSinceStartOfDay() / 1000.0
    if isinstance(value, QDate):
        if not value.isValid():
            return None
        return (value.toJulianDay() - JULIAN_1970) * 86400.0
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str) and value.strip():
        parsed = QDateTime.fromString(value.strip(),
                                      enum(Qt, "DateFormat", "ISODate"))
        return seconds(parsed) if parsed.isValid() else None
    return None


def clock(value):
    """QDateTime с показаниями часов value секунд от 1970 года, без
    часового пояса, как у seconds. Бесконечность - пустое время,
    открытый край промежутка QGIS."""
    if value is None or not math.isfinite(value):
        return QDateTime()
    days = math.floor(value / 86400.0)
    msecs = int(round((value - days * 86400.0) * 1000.0))
    if msecs >= 86400000:
        days, msecs = days + 1, msecs - 86400000
    return QDateTime(QDate.fromJulianDay(JULIAN_1970 + int(days)),
                     QTime.fromMSecsSinceStartOfDay(msecs))


def date_range(lo, hi):
    """Промежуток QGIS из секунд шкалы времени."""
    return QgsDateTimeRange(clock(lo), clock(hi))


def timed_layer(layer):
    """Действуют ли у слоя временные свойства QGIS."""
    props = layer.temporalProperties() if layer is not None else None
    return props is not None and props.isActive()


def layer_span(layer):
    """Охват времени слоя в секундах (от, до) или None.

    У векторного слоя - наименьшее и наибольшее значение полей начала
    и конца, иначе постоянный промежуток временных свойств. Слой со
    временем по выражению охвата не даёт. Поиск наименьшего значения
    у поставщика бывает просмотром всех объектов, поэтому охват
    спрашивается при смене слоёв, а не при движении шкалы.
    """
    if not timed_layer(layer):
        return None
    props = layer.temporalProperties()
    values = []
    if isinstance(layer, QgsVectorLayer):
        fields = layer.fields()
        for name in {props.startField(), props.endField()}:
            index = fields.indexOf(name) if name else -1
            if index >= 0:
                values += [seconds(layer.minimumValue(index)),
                           seconds(layer.maximumValue(index))]
    values = [v for v in values if v is not None]
    if not values and hasattr(props, "fixedTemporalRange"):
        fixed = props.fixedTemporalRange()
        values = [v for v in (seconds(fixed.begin()), seconds(fixed.end()))
                  if v is not None]
    return (min(values), max(values)) if values else None


def point_layer(layer):
    """Точечный векторный слой: номер Qgis.GeometryType 0."""
    return isinstance(layer, QgsVectorLayer) \
        and enum_int(layer.geometryType()) == 0


def read_track(layer, time_field, object_field="", height="", unit=1.0):
    """Трек core.track.Track из точек слоя. Точки без времени
    пропускаются. height - HEIGHT_Z (Z точки), имя поля или пустая
    строка - без высоты, unit - метров в единице высоты."""
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    transform = QgsCoordinateTransform(layer.crs(), wgs,
                                       QgsProject.instance())
    names = [n for n in (time_field, object_field) if n]
    if height and height != HEIGHT_Z:
        names.append(height)
    request = QgsFeatureRequest().setSubsetOfAttributes(names,
                                                        layer.fields())
    items = []
    for feature in layer.getFeatures(request):
        t = seconds(feature[time_field])
        geometry = feature.geometry()
        alt = None
        if height == HEIGHT_Z:
            alt = _z_of(geometry)
        elif height:
            alt = _number(feature[height])
        point = _wgs_point(geometry, transform)
        if t is None or point is None:
            continue
        key = feature[object_field] if object_field else layer.name()
        items.append((str(key), t, point.y(), point.x(),
                      None if alt is None else alt * unit))
    return Track(items)


def _z_of(geometry):
    """Z первой точки геометрии или None."""
    if geometry is None or geometry.isEmpty():
        return None
    for vertex in geometry.vertices():
        z = vertex.z()
        return z if z == z else None
    return None


def _number(value):
    """Число поля или None: пустое значение, текст не числом."""
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _wgs_point(geometry, transform):
    """Точка геометрии в WGS84 или None, если её нет или пересчёт
    не удался."""
    if geometry is None or geometry.isEmpty():
        return None
    try:
        geometry.transform(transform)
    except QgsCsException:
        return None
    if geometry.isMultipart():
        points = geometry.asMultiPoint()
        return points[0] if points else None
    return geometry.asPoint()


def _has_z(layer):
    """Есть ли у геометрии слоя Z."""
    return QgsWkbTypes.hasZ(layer.wkbType())


def default_time_field(layer):
    """Поле времени из временных свойств слоя, если оно задано."""
    props = layer.temporalProperties()
    field = props.startField() if hasattr(props, "startField") else ""
    return field if field in layer.fields().names() else ""


class TrackDialog(QDialog):
    """Окно «Трек» слоя: поле времени, поле объекта, цвет, камера."""

    def __init__(self, layer, settings=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Трек: {name}", name=layer.name()))
        settings = settings or {}
        names = layer.fields().names()
        form = QFormLayout()
        self.time = QComboBox(self)
        self.time.addItems(names)
        chosen = settings.get("time") or default_time_field(layer)
        if chosen in names:
            self.time.setCurrentText(chosen)
        self.time.setToolTip(tr(
            "Поле с датой и временем точки. Годятся поля даты и времени, "
            "текст в виде ISO 8601 и число секунд от 1970 года."))
        form.addRow(tr("Время"), self.time)
        self.object = QComboBox(self)
        self.object.addItem(tr("Один объект"), "")
        for name in names:
            self.object.addItem(name, name)
        index = self.object.findData(settings.get("object", ""))
        self.object.setCurrentIndex(max(index, 0))
        self.object.setToolTip(tr(
            "Поле, которое отличает объекты друг от друга, например номер "
            "машины. У каждого объекта свой путь и своя метка."))
        form.addRow(tr("Объект"), self.object)
        self.color = QgsColorButton(self)
        self.color.setAllowOpacity(True)
        self.color.setColor(QColor(*settings.get("color", TRACK_COLOR)))
        self.color.setToolTip(tr("Цвет пройденного пути."))
        form.addRow(tr("Цвет"), self.color)
        self.follow = QCheckBox(tr("Камера следом"), self)
        self.follow.setChecked(bool(settings.get("follow", False)))
        self.follow.setToolTip(tr(
            "Камера держит первый объект трека в центре, азимут - по ходу "
            "движения. Расстояние и наклон меняются колесом и мышью."))
        form.addRow("", self.follow)
        self.model = QLineEdit(settings.get("model", ""), self)
        self.model.setPlaceholderText(tr("без модели"))
        self.model.setToolTip(tr(
            "Файл 3D-модели glTF, Collada или OBJ. Модель едет по пути "
            "каждого объекта трека, перёд смотрит по ходу движения. Пустое "
            "поле - объект показан меткой."))
        browse = QToolButton(self)
        browse.setText("…")
        browse.setToolTip(tr("Выбрать файл модели."))
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.model, 1)
        row.addWidget(browse)
        form.addRow(tr("3D-модель"), row)
        self.model_scale = QDoubleSpinBox(self)
        self.model_scale.setRange(0.01, 10000.0)
        self.model_scale.setDecimals(2)
        self.model_scale.setValue(float(settings.get("model_scale", 1.0)))
        self.model_scale.setToolTip(tr(
            "Множитель размера модели. С множителем 1 модель стоит в "
            "своих метрах, больший множитель делает её заметной издалека."))
        form.addRow(tr("Масштаб модели"), self.model_scale)
        self.model_turn = QDoubleSpinBox(self)
        self.model_turn.setRange(-180.0, 180.0)
        self.model_turn.setDecimals(1)
        self.model_turn.setSuffix("°")
        self.model_turn.setValue(float(settings.get("model_turn", 0.0)))
        self.model_turn.setToolTip(tr(
            "Поворот модели по часовой стрелке к ходу движения. Нужен, "
            "если перёд модели в файле смотрит не на север, например "
            "180° у модели glTF, повёрнутой передом к зрителю."))
        form.addRow(tr("Поворот модели"), self.model_turn)
        self.height_source = QComboBox(self)
        self.height_source.addItem(tr("По земле"), "")
        if _has_z(layer):
            self.height_source.addItem(tr("Z точки"), HEIGHT_Z)
        for field in layer.fields():
            if field.isNumeric():
                self.height_source.addItem(field.name(), field.name())
        index = self.height_source.findData(settings.get("height", ""))
        self.height_source.setCurrentIndex(max(index, 0))
        self.height_source.setToolTip(tr(
            "Откуда высота точки: Z точки или числовое поле. «По земле» - "
            "объект и модель стоят на рельефе."))
        form.addRow(tr("Высота"), self.height_source)
        self.height_mode = QComboBox(self)
        self.height_mode.addItem(tr("над уровнем моря"), "absolute")
        self.height_mode.addItem(tr("над землёй"), "relative")
        index = self.height_mode.findData(settings.get("height_mode",
                                                       "absolute"))
        self.height_mode.setCurrentIndex(max(index, 0))
        self.height_mode.setToolTip(tr(
            "Над уровнем моря - высота полёта по барометру или GPS, путь "
            "рисуется в воздухе. Над землёй - подъём над рельефом под "
            "точкой, например у дрона."))
        form.addRow(tr("Отсчёт высоты"), self.height_mode)
        self.height_unit = QComboBox(self)
        self.height_unit.addItem(tr("метры"), 1.0)
        self.height_unit.addItem(tr("футы"), FOOT)
        index = self.height_unit.findData(float(settings.get("height_unit",
                                                             1.0)))
        self.height_unit.setCurrentIndex(max(index, 0))
        self.height_unit.setToolTip(tr(
            "Единицы высоты. Высоту самолётов ADS-B передают в футах."))
        form.addRow(tr("Единицы высоты"), self.height_unit)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        self.remove = QPushButton(tr("Убрать трек"), self)
        self.remove.setToolTip(tr("Слой больше не показывается треком."))
        buttons.addButton(self.remove, enum(QDialogButtonBox, "ButtonRole",
                                            "DestructiveRole"))
        self.removed = False
        self.remove.clicked.connect(self._remove)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def _remove(self):
        self.removed = True
        self.accept()

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, tr("3D-модель трека"), os.path.dirname(self.model.text()),
            tr("3D-модели ({patterns})", patterns=MODEL_FILTER))
        if path:
            self.model.setText(path)

    def settings(self):
        color = self.color.color()
        return {"time": self.time.currentText(),
                "object": self.object.currentData() or "",
                "color": [color.red(), color.green(), color.blue(),
                          color.alpha()],
                "follow": self.follow.isChecked(),
                "model": self.model.text().strip(),
                "model_scale": self.model_scale.value(),
                "model_turn": self.model_turn.value(),
                "height": self.height_source.currentData() or "",
                "height_mode": self.height_mode.currentData(),
                "height_unit": float(self.height_unit.currentData())}


class TrackManager(QObject):
    """Треки слоёв проекта, время шкалы глобуса и камера следом."""

    changed = pyqtSignal()
    # Точки треков перечитаны: охват шкалы времени мог смениться.
    reloaded = pyqtSignal()

    def __init__(self, view, parent=None):
        super().__init__(parent)
        self.view = view
        self.settings = {}  # номер слоя -> настройки
        self.tracks = {}  # номер слоя -> Track
        self.moment = None  # секунды или None - треки целиком
        self._wanted = None  # момент шкалы, его возвращает release
        self._shapes = []
        self._last_step = None
        # Модели треков: путь файла - (время правки, разбор или None),
        # место объектов на момент - (номер слоя, объект) - (широта,
        # долгота, азимут).
        self._model_cache = {}
        self._at = {}
        # Момент держит запись тура, шкала его не меняет.
        self.held = False
        self.load()

    # Настройки в проекте.

    def load(self):
        text, ok = QgsProject.instance().readEntry(ENTRY, TRACK_KEY, "")
        try:
            data = json.loads(text) if ok and text else {}
        except ValueError:
            data = {}
        self.settings = data if isinstance(data, dict) else {}
        self.reload()

    def _save(self):
        QgsProject.instance().writeEntry(ENTRY, TRACK_KEY,
                                         json.dumps(self.settings))

    def set_track(self, layer, settings):
        """Показать слой треком с настройками или убрать, None."""
        if settings is None:
            self.settings.pop(layer.id(), None)
        else:
            self.settings[layer.id()] = settings
        self._save()
        self.reload()

    def reload(self):
        """Перечитать точки всех треков, например после правки слоёв."""
        self.tracks = {}
        project = QgsProject.instance()
        for layer_id, settings in list(self.settings.items()):
            layer = project.mapLayer(layer_id)
            if layer is None or not point_layer(layer) \
                    or settings.get("time") not in layer.fields().names():
                continue
            height = settings.get("height", "")
            if height and height != HEIGHT_Z \
                    and height not in layer.fields().names():
                height = ""
            self.tracks[layer_id] = read_track(
                layer, settings["time"], settings.get("object", ""),
                height, float(settings.get("height_unit", 1.0)))
        self.reloaded.emit()
        self._apply()
        self._set_models()

    # Время.

    def set_time(self, moment):
        """Момент правого бегунка шкалы времени, None - шкала закрыта,
        треки целиком. Тот же момент второй раз ничего не делает."""
        if moment == self._wanted and not self.held:
            return
        self._wanted = moment
        self._apply()

    def _apply(self):
        if self.held:
            return
        self.moment = self._wanted
        self._build()
        self._follow()
        self.changed.emit()

    def data_span(self):
        """Охват времени всех треков в секундах или None, если треков
        нет. По нему запись тура ведёт треки при закрытой шкале."""
        starts = [t.start for t in self.tracks.values()
                  if t.start is not None]
        ends = [t.end for t in self.tracks.values() if t.end is not None]
        if not starts:
            return None
        return min(starts), max(ends)

    def set_moment(self, moment):
        """Момент треков от шкалы записи тура, без камеры следом.

        Камеру кадра ставит тур. Перелёт следом шёл бы по настенным
        часам, и повтор записи дал бы другие позы.
        """
        self.held = True
        self.moment = moment
        self._build()
        self.changed.emit()

    def release(self):
        """Конец записи: момент снова от шкалы времени."""
        self.held = False
        self._apply()

    def _build(self):
        shapes = []
        at = {}
        for layer_id, track in self.tracks.items():
            settings = self.settings.get(layer_id, {})
            color = tuple(settings.get("color", TRACK_COLOR))
            absolute = settings.get("height_mode",
                                    "absolute") == "absolute"
            for position in track.at(self.moment):
                heading = position.heading
                if heading != heading:
                    # Курса ещё нет: модель стоит, как стояла.
                    heading = self._at.get((layer_id, position.key),
                                           (0.0, 0.0, 0.0))[2]
                at[(layer_id, position.key)] = (position.lat, position.lon,
                                                heading, position.alt)
                flying = position.alts is not None \
                    and not any(a != a for a in position.alts)
                if len(position.path) >= 2:
                    # Над уровнем моря путь лежит в воздухе на своих
                    # высотах, над землёй - на рельефе.
                    shapes.append(Shape(
                        "line", position.path, color=color,
                        width=TRACK_WIDTH,
                        alts=position.alts if flying and absolute
                        else None))
                if flying and absolute:
                    # Маркер точки поднимается на height над поверхностью,
                    # высоты alts он не читает.
                    scale = self.view.store.scale
                    ground = self.view.label_height(
                        position.lat, position.lon) / scale if scale else 0.0
                    point = Shape("point", [(position.lat, position.lon)],
                                  name=position.key,
                                  height=max(position.alt - ground, 0.0))
                elif flying:
                    point = Shape("point", [(position.lat, position.lon)],
                                  name=position.key, height=position.alt)
                else:
                    point = Shape("point", [(position.lat, position.lon)],
                                  name=position.key)
                shapes.append(point)
        self._shapes = shapes
        self._at = at

    def shapes(self):
        """Пути и метки объектов для глобуса."""
        return list(self._shapes)

    # Модели.

    def _model(self, path):
        """Разбор файла модели: (части, {путь: RGBA}, анимация) или None.
        Файл читается заново, если сменилось время правки."""
        try:
            stamp = os.path.getmtime(path)
        except OSError:
            return None
        cached = self._model_cache.get(path)
        if cached is not None and cached[0] == stamp:
            return cached[1]
        found = None
        package = models.package_file(path)
        if package:
            try:
                parts, pictures, moving = models.read_animated(package)
                found = (parts, {key: image_rgba(raw, MODEL_SIDE)
                                 for key, raw in pictures.items()}, moving)
            except models.ModelError as error:
                journal.note("track model unreadable: {}".format(error))
        self._model_cache[path] = (stamp, found)
        return found

    def _set_models(self):
        """Модели объектов треков на вид, группа «tracks»."""
        items = []
        used = set()
        for layer_id, track in self.tracks.items():
            settings = self.settings.get(layer_id, {})
            path = settings.get("model") or ""
            found = self._model(path) if path else None
            if found is None:
                continue
            used.add(path)
            parts, pictures, moving = found
            scale = float(settings.get("model_scale", 1.0)) or 1.0
            scales = (scale, scale, scale)
            turn = float(settings.get("model_turn", 0.0))
            base = models.frame(0.0, 0.0, 0.0, 0.0, 0.0, scales)
            arrays = models.vertices(parts, 0.0, 0.0, 0.0, 0.0, 0.0, scales)
            radius = models.radius(parts, scales)
            mesh = ("track", path, scale)
            mode = "clampToGround"
            if settings.get("height"):
                mode = "relativeToGround" if settings.get(
                    "height_mode") == "relative" else "absolute"
            shared = [(array, pictures.get(part.image), part.rgba,
                       part.track) for array, part in zip(arrays, parts)]
            for key in track.objects:
                items.append(ModelItem(
                    ("track", layer_id, key), shared,
                    (0.0, 0.0, mode, 0.0), radius, 1.0, moving,
                    base, mover=self._mover(layer_id, key, base, turn,
                                            scales),
                    mesh=mesh))
        self._model_cache = {path: value for path, value
                             in self._model_cache.items() if path in used}
        self.view.models.set_models(items, group="tracks")
        self.view.update()

    def _mover(self, layer_id, key, base, turn, scales):
        def mover(now):
            del now
            found = self._at.get((layer_id, key))
            if found is None:
                return None
            lat, lon, heading, alt = found
            linear = models.moved(base, lat, lon, heading + turn, 0.0, 0.0,
                                  scales)
            if alt != alt:
                return lat, lon, linear
            return lat, lon, linear, alt
        return mover

    # Камера.

    def _follow(self):
        target = None
        for layer_id, track in self.tracks.items():
            if self.settings.get(layer_id, {}).get("follow"):
                positions = track.at(self.moment)
                if positions:
                    target = positions[0]
                    break
        if target is None:
            self._last_step = None
            return
        nav = self.view.navigator
        now = time.monotonic()
        step = GLIDE_MAX if self._last_step is None \
            else min(max(now - self._last_step, GLIDE_MIN), GLIDE_MAX)
        self._last_step = now
        start = nav.pose
        heading = start.heading if target.heading != target.heading \
            else target.heading
        end = Pose(target.lat, target.lon, start.distance, heading,
                   start.tilt)
        nav.start_flight(Glide(start, end, step), now)
        self.view.update()
