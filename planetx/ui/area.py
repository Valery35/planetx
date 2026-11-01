# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Участок окон анализа участка - многоугольник, как у Google Earth.

Решение автора от 28 октября 2026 года для уклона и экспозиции,
затопления и стока воды, инсоляции, изменений местности
и классификации. При открытии окна участок - квадрат с серединой
в точке окна, его вершины тянутся мышью, кружок на середине стороны
ставит новую вершину. «Квадрат» возвращает квадрат стороной из поля,
«Нарисовать» - вершины щелчками по глобусу, подсказка «Замкнуть фигуру»
у первой вершины, щелчок по ней замыкает участок. Расчёт идёт по рамке
участка, вне многоугольника результатов нет. Образец - окно
классификации, из него участок вынесен сюда.

Участок общий, слово автора от 30 октября 2026 года - нарисовал один
раз и считаешь по нему разными окнами. Его хранит окно глобуса
(GlobeWindow.site), смена тела его снимает.

Вопрос автора от 2 ноября 2026 года - участком служит многоугольник слоя
проекта. «Из слоя» берёт выделенные объекты, у слоя из одного объекта -
его, иначе многоугольник под щелчком по глобусу. Участок - одно кольцо
вершин: из составного объекта берётся крупнейшая часть, дыры не
учитываются, вершин не больше RING_POINTS, контур сложнее HANDLES_MOST
вершин идёт без ручек.
"""
import math

import numpy as np
from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsCsException,
                       QgsFeatureRequest, QgsGeometry, QgsPointXY,
                       QgsProject, QgsRectangle, QgsSettings,
                       QgsVectorLayer, QgsWkbTypes)
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QMenu,
                                 QPushButton, QWidget)

from ..core import aef, editing
from ..core.features import Shape
from ..i18n import tr
from .handles import PropVertices

COLOR = (255, 255, 255, 255)  # контур участка на глобусе
RING_POINTS = 500  # вершин участка из слоя
HANDLES_MOST = 100  # вершин с ручками, сотни кружков закрыли бы контур
THIN_STEPS = 40  # попыток упростить кольцо
THIN_FIRST = 1e-5  # первый допуск упрощения, градусы
THIN_GROWTH = 1.5  # рост допуска с каждой попыткой


def polygon_layers():
    """Слои проекта с многоугольниками по названию."""
    layers = [layer for layer in QgsProject.instance().mapLayers().values()
              if isinstance(layer, QgsVectorLayer) and layer.isValid()
              and layer.geometryType() == Qgis.GeometryType.Polygon]
    return sorted(layers, key=lambda layer: layer.name().lower())


def _thin(part):
    """Кольца многоугольника part, у наружного не больше RING_POINTS
    вершин."""
    rings = part.asPolygon()
    tolerance = THIN_FIRST
    for _ in range(THIN_STEPS):
        if len(rings[0]) <= RING_POINTS + 1:
            break
        thin = part.simplify(tolerance).asPolygon()
        if thin:
            rings = thin
        tolerance *= THIN_GROWTH
    return rings


def ring_of(geometries, crs):
    """Участок из геометрий слоя в системе crs: (вершины (широта, долгота),
    сколько частей отброшено, сколько дыр не учтено) или None."""
    whole = geometries[0] if len(geometries) == 1 \
        else QgsGeometry.unaryUnion(geometries)
    if whole is None or whole.isNull():
        return None
    whole = QgsGeometry(whole)
    if QgsWkbTypes.isCurvedType(whole.wkbType()):
        whole = QgsGeometry(whole.constGet().segmentize())
    wgs = QgsCoordinateReferenceSystem("EPSG:4326")
    try:
        done = whole.transform(
            QgsCoordinateTransform(crs, wgs, QgsProject.instance()))
    except QgsCsException:
        return None
    if done != Qgis.GeometryOperationResult.Success:
        return None
    parts = [part for part in (whole.asGeometryCollection()
                               if whole.isMultipart() else [whole])
             if part.type() == Qgis.GeometryType.Polygon]
    if not parts:
        return None
    rings = _thin(max(parts, key=lambda part: part.area()))
    points = [(point.y(), point.x()) for point in rings[0]]
    if len(points) > 1 and points[0] == points[-1]:
        points = points[:-1]
    if len(points) < 3:
        return None
    return points, len(parts) - 1, len(rings) - 1


class Area(QObject):
    """Участок окна dialog у окна глобуса window. side - сторона
    квадрата по умолчанию, км, most - наибольший размер участка, км,
    key - настройка, где помнится сторона. Сигнал changed - вершины
    или замыкание. У окна должно быть поле status."""

    changed = pyqtSignal()
    shared = True  # участок общий с другими окнами, не контур образца

    def __init__(self, window, dialog, side, most, key=None):
        super().__init__(dialog)
        self.window = window
        self.dialog = dialog
        self.most = float(most)
        self.key = key
        self.point = None  # середина квадрата (широта, долгота)
        self.ring = []  # вершины участка (широта, долгота)
        self.drawing = False  # участок рисуется щелчками
        self.picking = None  # номер слоя, щелчок берёт его многоугольник
        # Точка у курсора, которую щелчок убирает, - у классификации
        # точки классов (ui/aefclass.py): функция (px, py) -> что-то
        # или None, подсказка - point_hint.
        self.point_under = None
        self.point_hint = ""
        if key:
            side = float(QgsSettings().value(key, side))
        self.side = QDoubleSpinBox(dialog)
        self.side.setRange(0.1, self.most)
        self.side.setDecimals(1)
        self.side.setValue(min(max(side, 0.1), self.most))
        self.side.setSuffix(tr(" км"))
        self._side_hint()
        square = QPushButton(tr("Квадрат"), dialog)
        square.setToolTip(tr("Участок - квадрат стороной из поля слева."))
        square.clicked.connect(self.reset_square)
        draw = QPushButton(tr("Нарисовать"), dialog)
        draw.setToolTip(tr(
            "Нарисовать участок многоугольником щелчками по глобусу. "
            "Щелчок по первой вершине замыкает его. Результат считается "
            "только внутри участка."))
        draw.clicked.connect(self.start_drawing)
        layered = QPushButton(tr("Из слоя"), dialog)
        layered.setToolTip(tr(
            "Участок - многоугольник слоя проекта: выделенные объекты, "
            "у слоя из одного объекта - он, иначе многоугольник под "
            "щелчком по глобусу. Из составного объекта берётся крупнейшая "
            "часть, дыры не учитываются."))
        menu = QMenu(layered)
        menu.aboutToShow.connect(lambda: self._fill_layers(menu))
        layered.setMenu(menu)
        self.widget = QWidget(dialog)
        row = QHBoxLayout(self.widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.side, 1)
        row.addWidget(square)
        row.addWidget(draw)
        row.addWidget(layered)
        self.side.valueChanged.connect(self._side_changed)
        areas = getattr(window, "areas", None)
        if areas is not None:
            areas.append(self)

    # --- состояние ------------------------------------------------------

    def _side_hint(self):
        self.side.setToolTip(tr(
            "Сторона квадрата участка с серединой в точке окна. Вершины "
            "участка тянутся мышью, кружок на середине стороны ставит "
            "новую вершину. Участок не больше {km} км.",
            km="{:g}".format(self.most)))

    def set_most(self, km):
        """Новый наибольший размер участка, км: у классификации он
        зависит от источника."""
        self.most = float(km)
        self.side.setMaximum(self.most)
        self._side_hint()

    def _side_changed(self, value):
        if self.key:
            QgsSettings().setValue(self.key, value)
        self.reset_square()

    def open_at(self, lat, lon):
        """Окно открыто у точки. Участок общий у окон анализа: точка
        внутри прежнего участка берёт его, иначе новый квадрат. Вершины
        на виде."""
        self.point = (lat, lon)
        self.picking = None
        site = self.window.site
        if site and aef.ring_inside(np.array([lat]), np.array([lon]),
                                    site)[0]:
            self.ring = list(site)
            self.drawing = False
            self.edited()
            self.begin()
            self.dialog.status.setText(tr(
                "Участок общий с прошлым расчётом. «Квадрат» и «Нарисовать» "
                "начинают новый."))
            return
        self.reset_square()
        self.begin()

    def set_square(self, lat, lon, side_m):
        """Участок - квадрат side_m метров с серединой lat, lon."""
        self.point = (lat, lon)
        self.side.blockSignals(True)
        self.side.setValue(min(max(side_m / 1000.0, 0.1), self.most))
        self.side.blockSignals(False)
        self.reset_square()

    def reset_square(self):
        """Участок - квадрат стороной из поля у точки окна."""
        if self.point is None:
            return
        self.ring = aef.square_ring(self.point[0], self.point[1],
                                    self.side.value() * 1000.0)
        self.drawing = False
        self.picking = None
        self.edited()
        self.begin()

    def start_drawing(self):
        """Участок рисуется заново щелчками по глобусу."""
        self.ring = []
        self.drawing = True
        self.picking = None
        self.dialog.status.setText(tr(
            "Щёлкайте по глобусу вершины участка. Щелчок по первой "
            "вершине замыкает его."))
        self.edited()
        self.begin()

    def _fill_layers(self, menu):
        """Меню «Из слоя»: слои с многоугольниками на момент открытия."""
        menu.clear()
        layers = polygon_layers()
        if not layers:
            menu.addAction(tr("В проекте нет слоёв с многоугольниками")
                           ).setEnabled(False)
        for layer in layers:
            count = layer.selectedFeatureCount()
            text = tr("{name}, выделено {count}", name=layer.name(),
                      count=count) if count else layer.name()
            menu.addAction(text).triggered.connect(
                lambda checked=False, item=layer: self.from_layer(item))

    def from_layer(self, layer):
        """Участок из слоя: выделенные объекты, единственный объект или
        многоугольник под следующим щелчком."""
        features = layer.selectedFeatures()
        if not features and layer.featureCount() == 1:
            features = list(layer.getFeatures())
        shapes = [feature.geometry() for feature in features
                  if feature.hasGeometry()]
        if shapes:
            if self._take(shapes, layer):
                self._show_ring()
            return
        self.drawing = False
        self.picking = layer.id()
        self.dialog.status.setText(tr(
            "Щёлкните по глобусу внутри многоугольника слоя «{name}».",
            name=layer.name()))

    def _pick(self, lat, lon):
        """Многоугольник выбранного слоя под щелчком."""
        layer = QgsProject.instance().mapLayer(self.picking)
        if layer is None:
            self.picking = None
            return
        point = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        try:
            point.transform(QgsCoordinateTransform(wgs, layer.crs(),
                                                   QgsProject.instance()))
        except QgsCsException:
            return
        spot = point.asPoint()
        request = QgsFeatureRequest().setFilterRect(
            QgsRectangle(spot.x(), spot.y(), spot.x(), spot.y()))
        for feature in layer.getFeatures(request):
            if feature.hasGeometry() and feature.geometry().contains(point):
                self._take([feature.geometry()], layer)
                return
        self.dialog.status.setText(tr(
            "Под щелчком нет многоугольника этого слоя."))

    def _take(self, shapes, layer):
        """Геометрии слоя становятся участком. Точка окна вне участка
        переходит внутрь него: от неё считают затопление и сток."""
        taken = ring_of(shapes, layer.crs())
        if taken is None:
            self.dialog.status.setText(tr(
                "Многоугольник слоя не удалось прочитать."))
            return False
        ring, parts, holes = taken
        self.picking = None
        self.drawing = False
        self.ring = ring
        spot = self.point
        moved = spot is None or not self.inside(
            np.array([spot[0]]), np.array([spot[1]]))[0]
        if moved:
            inner = QgsGeometry.fromPolygonXY([[
                QgsPointXY(lon, lat) for lat, lon in ring]]
            ).pointOnSurface().asPoint()
            self.point = (inner.y(), inner.x())
            if getattr(self.dialog, "point", None) is not None:
                self.dialog.point = self.point
        self.edited()
        self.begin()
        notes = [tr("Участок взят из слоя «{name}».", name=layer.name())]
        if parts:
            notes.append(tr("Отброшено частей: {count}, взята крупнейшая.",
                            count=parts))
        if holes:
            notes.append(tr("Дыр не учтено: {count}.", count=holes))
        if moved:
            notes.append(tr("Точка окна перенесена внутрь участка."))
        problem = self.check()
        if problem:
            notes.append(problem)
        self.dialog.status.setText(" ".join(notes))
        return True

    def _show_ring(self):
        """Перелёт к участку: выделенный объект может быть вне вида."""
        west, south, east, north = self.box()
        self.window._fly_extent(
            QgsRectangle(west, south, east, north),
            QgsCoordinateReferenceSystem("EPSG:4326"))

    def edited(self):
        self.changed.emit()
        window = self.window
        if self.closed():
            self._share()
        window._refresh_shapes()
        window.handles.sync()

    def _share(self):
        """Участок - общий для окон анализа: его берут открытые окна
        и окна, которые откроются внутри него."""
        self.window.site = list(self.ring)
        for other in self.window.areas:
            if other is not self and other.shared and other.visible() \
                    and not other.drawing:
                other.ring = list(self.ring)
                other.changed.emit()

    def closed(self):
        return not self.drawing and len(self.ring) >= 3

    def box(self):
        """Рамка участка в градусах (запад, юг, восток, север)."""
        if self.closed():
            return aef.ring_box(self.ring)[0]
        lat, lon = self.point
        return aef.square(lat, lon, self.side.value() * 1000.0)

    def size(self):
        """Наибольший размер участка, м."""
        if self.closed():
            return aef.ring_box(self.ring)[1]
        return self.side.value() * 1000.0

    def centre(self):
        """Середина рамки участка (широта, долгота)."""
        west, south, east, north = self.box()
        return (south + north) / 2.0, (west + east) / 2.0

    def reach(self):
        """Расстояние от середины рамки до самой дальней вершины, м."""
        lat, lon = self.centre()
        scale = math.cos(math.radians(lat))
        return max((math.hypot((p[0] - lat) * 111320.0,
                               (p[1] - lon) * 111320.0 * scale)
                    for p in self.ring), default=0.0)

    def inside(self, lats, lons):
        """Точки внутри многоугольника участка."""
        return aef.ring_inside(lats, lons, self.ring)

    def check(self):
        """Текст, почему по участку считать нельзя, или None."""
        if self.point is None:
            return tr("Нет точки окна.")
        if not self.closed():
            return tr("Замкните участок щелчком по его первой вершине.")
        if self.size() > self.most * 1000.0 + 1.0:
            return tr("Участок больше {km} км, уменьшите его.",
                      km="{:g}".format(self.most))
        return None

    # --- глобус ---------------------------------------------------------

    def visible(self):
        return self.dialog.isVisible()

    def taking(self):
        """Щелчок по глобусу - вершина рисуемого участка."""
        return (self.drawing or self.picking is not None) \
            and self.visible()

    def add(self, lat, lon):
        if self.picking is not None:
            self._pick(lat, lon)
            return
        self.ring.append((lat, lon))
        self.edited()

    def shapes(self):
        """Контур участка на глобусе, пока открыто окно."""
        if not self.visible():
            return []
        if self.closed():
            return [Shape("polygon", list(self.ring), color=COLOR,
                          width=2.0)]
        if len(self.ring) >= 2:
            return [Shape("line", list(self.ring), color=COLOR, width=2.0)]
        return []

    def begin(self):
        """Вершины участка тянутся мышью, пока открыто окно. Окно «Новая
        метка» и линейка главнее."""
        window = self.window
        if window._place_open() or window._ruler_open():
            return
        tool = AreaVertices(window, self.dialog, AreaEdit(self))
        window.view.vertex_tool = tool
        window.handles.tool = tool
        window.handles.sync()

    def end(self):
        """Окно закрыто: ручки и контур снимаются."""
        self.drawing = False
        self.picking = None
        self.window._end_prop_vertices(self.dialog)
        self.window._refresh_shapes()


class FixedArea:
    """Участок-квадрат без окна: водосбор метки (ui/hydro.py). Тот же
    протокол, что у Area, для расчёта."""

    def __init__(self, lat, lon, side_m):
        self.point = (lat, lon)
        self.ring = aef.square_ring(lat, lon, side_m)
        self.side_m = side_m

    def check(self):
        return None

    def box(self):
        return aef.ring_box(self.ring)[0]

    def size(self):
        return self.side_m

    def centre(self):
        return self.point

    def inside(self, lats, lons):
        return aef.ring_inside(lats, lons, self.ring)


class AreaEdit:
    """Участок в протоколе фигуры, который ждут ручки вершин
    (ui/handles.py): точки, вид, перенос, вставка, замыкание."""

    mode = "polygon"

    def __init__(self, area):
        self.area = area

    @property
    def points(self):
        return self.area.ring

    @property
    def finished(self):
        return not self.area.drawing

    def move(self, index, lat, lon):
        self.area.ring[index] = (lat, lon)
        self.area.edited()

    def insert(self, index, lat, lon):
        self.area.ring.insert(index, (lat, lon))
        self.area.edited()

    def finish(self):
        self.area.drawing = False
        self.area.dialog.status.setText("")
        self.area.edited()


class AreaVertices(PropVertices):
    """Вершины участка, пока открыто окно. Щелчок по первой вершине
    рисуемого участка замыкает его, у курсора подсказка «Замкнуть
    фигуру», как у Google Earth."""

    def closed(self):
        return self.edit.finished and len(self.edit.points) >= 3

    def screen(self):
        """Контур из слоя сложнее HANDLES_MOST вершин идёт без ручек."""
        if len(self.edit.points) > HANDLES_MOST:
            return self._project([]) + self._project([])
        return super().screen()

    def hover(self, px, py):
        """Подсказка у вершины участка или у точки, которую щелчок
        убирает (Area.point_under)."""
        area = self.edit.area
        hot = self.under(px, py) if px >= 0.0 else None
        point = None
        if hot is None and px >= 0.0 and area.point_under is not None \
                and self.dialog.isVisible() and not area.drawing:
            point = area.point_under(px, py)
        cursor = (px, py) if hot is not None or point is not None else None
        if hot != self.hot or cursor != self.cursor \
                or point != getattr(self, "point", None):
            self.hot = hot
            self.point = point
            self.cursor = cursor
            self.window.handles.update()

    def hint(self):
        if getattr(self, "point", None) is not None and self.hot is None:
            return self.edit.area.point_hint
        return super().hint()

    def drop(self):
        index, self.index = self.index, None
        if index is None or self._moved or self._fresh:
            return
        edit = self.edit
        if editing.click_result(edit.mode, len(edit.points), index,
                                edit.finished) == editing.CLOSE:
            edit.finish()
