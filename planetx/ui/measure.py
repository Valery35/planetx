# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линейка, как в Google Earth: линия, путь, многоугольник, круг,
3D-путь и 3D-многоугольник.

Точки ставятся щелчками по глобусу, перетаскивание по-прежнему двигает
Землю. Точку линейки можно схватить и перетащить, Backspace убирает
последнюю. За курсором тянется резинка к следующей точке. Длина,
периметр и площадь считаются на эллипсоиде WGS84 через QgsDistanceArea.
Длина по рельефу и профиль высот - по точкам вдоль линии
(core/measure.py). «Сохранить» кладёт фигуру в «Мои метки» вместе
с текстом измерения.

У 3D-пути и 3D-многоугольника точка ставится на рельеф или на здание
под курсором, со своей высотой над эллипсоидом. Отрезки прямые
в пространстве, длина - сумма хорд, площадь - в плоскости
многоугольника (core.measure.chord_length, polygon_area_3d). Высоты
лежат в alts рядом с points.
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
from ..core.measure import (AREA_UNITS, CIRCLE_POINTS, LENGTH_UNITS,
                            SLOPE_PIXELS, chord_length, convert,
                            height_level, number, pixel_size,
                            polygon_area_3d, profile, sample_line,
                            tiles_along)
from ..i18n import tr
from ..qt_compat import enum

MODES = ("line", "path", "polygon", "circle", "path3d", "polygon3d")
SOLID = ("path3d", "polygon3d")  # точки со своими высотами
COLOR = (255, 214, 0, 255)  # жёлтая линия, как у линейки Google Earth
FILL = (255, 214, 0, 50)
WIDTH = 2.0
GRAB_PIXELS = 8.0  # логических пикселей вокруг точки, в них она хватается


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
    """Точки линейки и величины. Сигнал changed - после каждой правки.

    heights - настоящие высоты массива точек (широты, долготы),
    has_heights(ключ) - есть ли тайл высот, ask_heights(ключи) - попросить
    недостающие. Их ставит окно, без них длины по рельефу и профиля нет.
    """

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.mode = "line"
        self.points = []
        # Высоты точек над эллипсоидом у 3D-пути и 3D-многоугольника,
        # по одной на точку, у прочих видов не нужны.
        self.alts = []
        self.cursor = None
        self.cursor_alt = None
        self.da = _distance_area()
        self.heights = None
        self.has_heights = None
        self.ask_heights = None
        # Точки, выборка, ключи высот, окно уклона.
        self._samples = (None, None, None, None)

    def set_mode(self, mode):
        self.mode = mode
        self.clear()

    def solid(self):
        """Вид со своими высотами точек."""
        return self.mode in SOLID

    def clear(self):
        self.points = []
        self.alts = []
        self.changed.emit()

    def _limit(self):
        """Точек у вида: метка - одна, линия и круг - две."""
        return {"point": 1, "line": 2, "circle": 2}.get(self.mode)

    def add(self, lat, lon, alt=None):
        """Щелчок по глобусу: новая точка по правилам вида линейки.
        alt - высота над эллипсоидом, у видов без высот не нужна."""
        limit = self._limit()
        if limit and len(self.points) >= limit:
            self.points = []  # третий щелчок начинает заново
            self.alts = []
        self.points.append((lat, lon))
        self.alts.append(0.0 if alt is None else float(alt))
        self.changed.emit()

    def move(self, index, lat, lon, alt=None):
        """Точку index перетащили в (lat, lon) на высоту alt."""
        if 0 <= index < len(self.points):
            self.points[index] = (lat, lon)
            if alt is not None:
                self.alts[index] = float(alt)
            self.changed.emit()

    def remove_last(self):
        """Backspace: убрать последнюю точку."""
        if self.points:
            self.points.pop()
            self.alts.pop()
            self.changed.emit()

    def set_cursor(self, point, alt=None):
        """Точка под курсором или None. Резинка тянется к ней."""
        if point != self.cursor or alt != self.cursor_alt:
            self.cursor = point
            self.cursor_alt = alt
            if self.points:
                self.changed.emit()

    def _rubber(self, rubber):
        limit = self._limit()
        return rubber and self.cursor is not None and bool(self.points) \
            and not (limit and len(self.points) >= limit)

    def _points(self, rubber):
        points = list(self.points)
        if self._rubber(rubber):
            points.append(self.cursor)
        return points

    def _alts(self, rubber):
        alts = list(self.alts)
        if self._rubber(rubber):
            alts.append(0.0 if self.cursor_alt is None
                        else float(self.cursor_alt))
        return alts

    def _solid_points(self, rubber):
        """Точки (широта, долгота, высота) у видов со своими высотами."""
        return [(lat, lon, alt) for (lat, lon), alt
                in zip(self._points(rubber), self._alts(rubber))]

    def shape(self, rubber=True, name="", color=COLOR, width=WIDTH,
              fill=FILL):
        """Фигура для глобуса или для «Моих меток», или None."""
        points = self._points(rubber)
        if self.solid():
            if len(points) < 2:
                return None
            alts = tuple(self._alts(rubber))
            if self.mode == "polygon3d" and len(points) >= 3:
                return Shape("polygon", points, color, width, fill, name,
                             alts=alts)
            return Shape("line", points, color, width, None, name,
                         alts=alts)
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

    def profile(self, rubber=False):
        """Профиль высот линии или пути и признак, что высоты все на
        месте. None - профиля нет."""
        return line_profile(self._points(rubber), self)

    def values(self, rubber=True):
        """Величины: длина на карте и по рельефу, курс, периметр,
        площадь, радиус. Нет величины - None. ground_ready - высоты
        для длины по рельефу все на месте."""
        points = self._points(rubber)
        out = {"length": None, "ground": None, "heading": None,
               "perimeter": None, "area": None, "radius": None,
               "ground_ready": True}
        if len(points) < 2:
            return out
        if self.mode == "path3d":
            out["length"] = chord_length(self._solid_points(rubber))
            return out
        if self.mode == "polygon3d":
            solid = self._solid_points(rubber)
            if len(solid) < 3:
                out["perimeter"] = 2.0 * chord_length(solid)
                out["area"] = 0.0
            else:
                out["perimeter"] = chord_length(solid, closed=True)
                out["area"] = polygon_area_3d(solid)
            return out
        if self.mode in ("line", "path"):
            out["length"] = self.da.measureLine(_xy(points))
            found = self.profile(rubber)
            if found is not None:
                out["ground"] = found[0].ground
                out["ground_ready"] = found[1]
            if self.mode == "line":
                a, b = _xy(points[:2])
                out["heading"] = math.degrees(self.da.bearing(a, b)) % 360.0
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


def line_profile(points, source):
    """Профиль высот ломаной points по высотам source (Ruler или другой
    объект с heights, has_heights, ask_heights и _samples).

    Возвращает (Profile, все ли высоты на месте) или None. Недостающие
    тайлы высот просятся у окна. Выборка точек помнится для тех же
    points: резинка двигается по кадрам, пересчёт стоил бы миллисекунды.
    """
    if len(points) < 2 or source.heights is None:
        return None
    key = tuple(points)
    if source._samples[0] != key:
        latlon = sample_line(points)
        level = height_level(points)
        keys = tiles_along(latlon, level)
        window = SLOPE_PIXELS * pixel_size(float(latlon[:, 0].mean()), level)
        source._samples = (key, latlon, keys, window)
    _, latlon, keys, window = source._samples
    missing = [k for k in keys if source.has_heights is not None
               and not source.has_heights(k)]
    if missing and source.ask_heights is not None:
        source.ask_heights(missing)
    heights = source.heights(latlon[:, 0], latlon[:, 1])
    return profile(latlon, heights, window), not missing


ROWS = ("length", "ground", "heading", "perimeter", "area", "radius")


def row_titles(mode="line"):
    return {"length": tr("Длина на карте") if mode in ("line", "path")
            else tr("Длина"),
            "ground": tr("Длина по рельефу"), "heading": tr("Курс"),
            "perimeter": tr("Периметр"), "area": tr("Площадь"),
            "radius": tr("Радиус")}


# Какие строки видны у вида линейки.
SHOWN = {"line": ("length", "ground", "heading"),
         "path": ("length", "ground"),
         "polygon": ("perimeter", "area"),
         "circle": ("radius", "perimeter", "area"),
         "path3d": ("length",),
         "polygon3d": ("perimeter", "area")}


def heading_text(value):
    """Курс в градусах с одним знаком после точки."""
    return "{:.1f}°".format(value)


class RulerDialog(QDialog):
    """Окно «Линейка». Сигналы: save_requested - кнопка «Сохранить»,
    profile_requested - кнопка «Профиль высот»."""

    save_requested = pyqtSignal()
    profile_requested = pyqtSignal()

    def __init__(self, ruler, parent=None):
        super().__init__(parent)
        self.ruler = ruler
        self.setWindowTitle(tr("Линейка"))
        self.setModal(False)
        self.tabs = QTabBar(self)
        for title in (tr("Линия"), tr("Путь"), tr("Многоугольник"),
                      tr("Круг"), tr("3D-путь"), tr("3D-многоугольник")):
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
        for key in ROWS:
            value = QLabel("0.00", self)
            row = QWidget(self)
            line = QHBoxLayout(row)
            line.setContentsMargins(0, 0, 0, 0)
            line.addWidget(value, 1)
            if key == "heading":
                # Курс - в градусах, выбора единиц нет.
                value.setToolTip(tr(
                    "Азимут начала линии от севера по часовой стрелке "
                    "на эллипсоиде WGS84."))
            else:
                units = AREA_UNITS if key == "area" else LENGTH_UNITS
                combo = QComboBox(self)
                for code, _ in units:
                    combo.addItem(names[code], code)
                combo.setCurrentIndex(2 if key == "area" else 1)
                combo.currentIndexChanged.connect(self.show_values)
                line.addWidget(combo, 0)
                self.units[key] = combo
            label = QLabel(self)
            form.addRow(label, row)
            self.values[key] = value
            self.rows[key] = (label, row)
        self.rows["ground"][0].setToolTip(tr(
            "Длина вдоль поверхности рельефа с подъёмами и спусками. "
            "Высоты берутся из Mapzen Terrain Tiles, недостающие "
            "загружаются. Пока они загружаются, перед числом стоит «≈»."))
        buttons = QDialogButtonBox(self)
        self.profile = QPushButton(tr("Профиль высот"), self)
        self.profile.setToolTip(tr(
            "График высоты вдоль линии или пути с наибольшей и наименьшей "
            "высотой, набором и потерей высоты и уклонами."))
        self.profile.clicked.connect(self.profile_requested)
        self.save = QPushButton(tr("Сохранить"), self)
        self.save.setToolTip(tr(
            "Сохранить фигуру в «Мои метки» вместе с измерением."))
        clear = QPushButton(tr("Очистить"), self)
        clear.setToolTip(tr("Убрать точки линейки с глобуса."))
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(self.profile, role)
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

    def length_unit(self):
        """Код единицы длины, выбранной в окне."""
        return self.units["length"].currentData()

    def show_values(self):
        mode = self.ruler.mode
        hints = {
            "line": tr("Щелчками по глобусу отметьте начало и конец "
                       "линии. Третий щелчок начинает новую линию."),
            "path": tr("Щелчками по глобусу отметьте точки пути."),
            "polygon": tr("Щелчками по глобусу отметьте вершины "
                          "многоугольника."),
            "circle": tr("Первый щелчок по глобусу - центр круга, "
                         "второй задаёт радиус."),
            "path3d": tr("Щелчками отметьте точки пути на рельефе, "
                         "крышах и стенах зданий. Отрезки идут по прямой "
                         "в пространстве, длина учитывает перепад "
                         "высот."),
            "polygon3d": tr("Щелчками отметьте вершины на рельефе, "
                            "крышах и стенах зданий. Площадь считается "
                            "в плоскости многоугольника, например "
                            "у стены или склона.")}
        self.hint.setText(hints[mode] + " " + tr(
            "Точку можно перетащить мышью, Backspace убирает последнюю."))
        values = self.ruler.values()
        short = unit_short()
        titles = row_titles(mode)
        for key in ROWS:
            label, row = self.rows[key]
            shown = key in SHOWN[mode]
            label.setVisible(shown)
            row.setVisible(shown)
            if not shown:
                continue
            label.setText(titles[key])
            value = values[key]
            if key == "heading":
                self.values[key].setText(
                    heading_text(value) if value is not None else "-")
                continue
            code = self.units[key].currentData()
            units = AREA_UNITS if key == "area" else LENGTH_UNITS
            text = number(convert(value, code, units)) \
                if value is not None else "-"
            if key == "ground" and value is not None \
                    and not values["ground_ready"]:
                text = "≈ " + text
            self.values[key].setText(text)
            self.values[key].setToolTip(short[code])
        self.save.setEnabled(self.ruler.shape(rubber=False) is not None)
        self.profile.setVisible(mode in ("line", "path"))
        self.profile.setEnabled(len(self.ruler.points) >= 2)

    def summary(self):
        """Текст измерения для «Моих меток», без резинки."""
        values = self.ruler.values(rubber=False)
        short = unit_short()
        titles = row_titles(self.ruler.mode)
        parts = []
        for key in ROWS:
            if key not in SHOWN[self.ruler.mode] or values[key] is None:
                continue
            title = titles[key]
            if parts:
                title = title[:1].lower() + title[1:]
            if key == "heading":
                parts.append("{} {}".format(title,
                                            heading_text(values[key])))
                continue
            code = self.units[key].currentData()
            units = AREA_UNITS if key == "area" else LENGTH_UNITS
            parts.append("{} {} {}".format(
                title, number(convert(values[key], code, units)),
                short[code]))
        return ", ".join(parts)
