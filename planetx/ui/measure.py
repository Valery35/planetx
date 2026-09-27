# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейка, как в Google Earth: линия, путь, многоугольник, круг.

Точки ставятся щелчками по глобусу, перетаскивание по-прежнему двигает
Землю. За курсором тянется резинка к следующей точке. Длина, периметр
и площадь считаются на эллипсоиде WGS84 через QgsDistanceArea.
«Сохранить» кладёт фигуру в «Мои метки» вместе с текстом измерения.
"""
import math

from qgis.core import (QgsCoordinateReferenceSystem, QgsDistanceArea,
                       QgsGeometry, QgsPointXY, QgsProject)
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QLabel,
                                 QPushButton, QTabBar, QVBoxLayout,
                                 QWidget)

from ..core.features import Shape
from ..core.measure import (AREA_UNITS, CIRCLE_POINTS, LENGTH_UNITS, convert,
                            number)
from ..i18n import tr
from ..qt_compat import enum

MODES = ("line", "path", "polygon", "circle")
COLOR = (255, 214, 0, 255)  # жёлтая линия, как у линейки Google Earth
FILL = (255, 214, 0, 50)
WIDTH = 2.0


def unit_names():
    return {"m": tr("Метры"), "km": tr("Километры"), "mi": tr("Мили"),
            "nmi": tr("Морские мили"), "m2": tr("Кв. метры"),
            "ha": tr("Гектары"), "km2": tr("Кв. километры"),
            "mi2": tr("Кв. мили")}


def unit_short():
    return {"m": tr("м"), "km": tr("км"), "mi": tr("мили"),
            "nmi": tr("мор. мили"), "m2": tr("м²"), "ha": tr("га"),
            "km2": tr("км²"), "mi2": tr("кв. мили")}


def _distance_area():
    da = QgsDistanceArea()
    da.setSourceCrs(QgsCoordinateReferenceSystem("EPSG:4326"),
                    QgsProject.instance().transformContext())
    da.setEllipsoid("WGS84")
    return da


def _xy(points):
    return [QgsPointXY(lon, lat) for lat, lon in points]


def ellipsoid_ring(da, lat, lon, radius, points=CIRCLE_POINTS):
    """Окружность радиуса radius метров по геодезическим линиям WGS84.

    На сфере радиус расходился с мерой эллипсоида на 0.24 % на широте
    58°, 27 сентября 2026 года.
    """
    center = QgsPointXY(lon, lat)
    ring = []
    for i in range(points):
        azimuth = 2.0 * math.pi * i / points
        p = da.computeSpheroidProject(center, radius, azimuth)
        ring.append((p.y(), p.x()))
    return ring


class Ruler(QObject):
    """Точки линейки и величины. Сигнал changed - после каждой правки."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "line"
        self.points = []
        self.cursor = None
        self.da = _distance_area()

    def set_mode(self, mode):
        self.mode = mode
        self.clear()

    def clear(self):
        self.points = []
        self.changed.emit()

    def _limit(self):
        """Точек у вида: метка - одна, линия и круг - две."""
        return {"point": 1, "line": 2, "circle": 2}.get(self.mode)

    def add(self, lat, lon):
        """Щелчок по глобусу: новая точка по правилам вида линейки."""
        limit = self._limit()
        if limit and len(self.points) >= limit:
            self.points = []  # третий щелчок начинает заново
        self.points.append((lat, lon))
        self.changed.emit()

    def set_cursor(self, point):
        """Точка под курсором или None. Резинка тянется к ней."""
        if point != self.cursor:
            self.cursor = point
            if self.points:
                self.changed.emit()

    def _points(self, rubber):
        points = list(self.points)
        limit = self._limit()
        if rubber and self.cursor is not None and points \
                and not (limit and len(points) >= limit):
            points.append(self.cursor)
        return points

    def shape(self, rubber=True, name="", color=COLOR, width=WIDTH,
              fill=FILL):
        """Фигура для глобуса или для «Моих меток», или None."""
        points = self._points(rubber)
        if self.mode == "point":
            return Shape("point", points[:1], color, width, None, name) \
                if points else None
        if self.mode == "circle":
            if len(points) < 2:
                return None
            radius = self.da.measureLine(_xy(points[:2]))
            ring = ellipsoid_ring(self.da, points[0][0], points[0][1],
                                  radius)
            return Shape("polygon", ring, color, width, fill, name)
        if len(points) < 2:
            return None
        if self.mode == "polygon" and len(points) >= 3:
            return Shape("polygon", points, color, width, fill, name)
        return Shape("line", points, color, width, None, name)

    def values(self, rubber=True):
        """Величины в метрах и кв. метрах: длина, периметр, площадь,
        радиус. Нет величины - None."""
        points = self._points(rubber)
        out = {"length": None, "perimeter": None, "area": None,
               "radius": None}
        if len(points) < 2:
            return out
        if self.mode in ("line", "path"):
            out["length"] = self.da.measureLine(_xy(points))
            return out
        if self.mode == "circle":
            out["radius"] = self.da.measureLine(_xy(points[:2]))
            points = ellipsoid_ring(self.da, points[0][0], points[0][1],
                                    out["radius"])
        elif len(points) < 3:
            out["perimeter"] = 2.0 * self.da.measureLine(_xy(points))
            out["area"] = 0.0
            return out
        ring = _xy(points)
        polygon = QgsGeometry.fromPolygonXY([ring + ring[:1]])
        out["perimeter"] = self.da.measurePerimeter(polygon)
        out["area"] = self.da.measureArea(polygon)
        return out


ROWS = ("length", "perimeter", "area", "radius")


def row_titles():
    return {"length": tr("Длина"), "perimeter": tr("Периметр"),
            "area": tr("Площадь"), "radius": tr("Радиус")}
# Какие строки видны у вида линейки.
SHOWN = {"line": ("length",), "path": ("length",),
         "polygon": ("perimeter", "area"),
         "circle": ("radius", "perimeter", "area")}


class RulerDialog(QDialog):
    """Окно «Линейка». Сигнал save_requested - кнопка «Сохранить»."""

    save_requested = pyqtSignal()

    def __init__(self, ruler, parent=None):
        super().__init__(parent)
        self.ruler = ruler
        self.setWindowTitle(tr("Линейка"))
        self.setModal(False)
        self.tabs = QTabBar(self)
        for title in (tr("Линия"), tr("Путь"), tr("Многоугольник"),
                      tr("Круг")):
            self.tabs.addTab(title)
        self.tabs.currentChanged.connect(
            lambda i: self.ruler.set_mode(MODES[i]))
        self.hint = QLabel(self)
        self.hint.setWordWrap(True)
        names = unit_names()
        form = QFormLayout()
        self.values = {}
        self.units = {}
        self.rows = {}
        titles = row_titles()
        for key in ROWS:
            units = AREA_UNITS if key == "area" else LENGTH_UNITS
            combo = QComboBox(self)
            for code, _ in units:
                combo.addItem(names[code], code)
            combo.setCurrentIndex(2 if key == "area" else 1)
            combo.currentIndexChanged.connect(self.show_values)
            value = QLabel("0.00", self)
            row = QWidget(self)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(value, 1)
            line.addWidget(combo, 0)
            form.addRow(titles[key], row)
            self.values[key] = value
            self.units[key] = combo
            self.rows[key] = (form.labelForField(row), row)
        buttons = QDialogButtonBox(self)
        self.save = QPushButton(tr("Сохранить"), self)
        self.save.setToolTip(tr(
            "Сохранить фигуру в «Мои метки» вместе с измерением."))
        clear = QPushButton(tr("Очистить"), self)
        clear.setToolTip(tr("Убрать точки линейки с глобуса."))
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(self.save, role)
        buttons.addButton(clear, role)
        self.save.clicked.connect(self.save_requested)
        clear.clicked.connect(self.ruler.clear)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.hint)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.ruler.changed.connect(self.show_values)
        self.show_values()

    def show_values(self):
        mode = self.ruler.mode
        hints = {
            "line": tr("Щелчками по глобусу отметьте начало и конец "
                       "линии. Третий щелчок начинает новую линию."),
            "path": tr("Щелчками по глобусу отметьте точки пути."),
            "polygon": tr("Щелчками по глобусу отметьте вершины "
                          "многоугольника."),
            "circle": tr("Первый щелчок по глобусу - центр круга, "
                         "второй задаёт радиус.")}
        self.hint.setText(hints[mode])
        values = self.ruler.values()
        short = unit_short()
        for key in ROWS:
            label, row = self.rows[key]
            shown = key in SHOWN[mode]
            label.setVisible(shown)
            row.setVisible(shown)
            if not shown:
                continue
            code = self.units[key].currentData()
            units = AREA_UNITS if key == "area" else LENGTH_UNITS
            value = values[key]
            self.values[key].setText(
                number(convert(value, code, units)) if value is not None
                else "-")
            self.values[key].setToolTip(short[code])
        self.save.setEnabled(self.ruler.shape(rubber=False) is not None)

    def summary(self):
        """Текст измерения для «Моих меток», без резинки."""
        values = self.ruler.values(rubber=False)
        short = unit_short()
        titles = row_titles()
        parts = []
        for key in ROWS:
            if key not in SHOWN[self.ruler.mode] or values[key] is None:
                continue
            code = self.units[key].currentData()
            units = AREA_UNITS if key == "area" else LENGTH_UNITS
            title = titles[key]
            if parts:
                title = title[:1].lower() + title[1:]
            parts.append("{} {} {}".format(
                title, number(convert(values[key], code, units)),
                short[code]))
        return ", ".join(parts)
