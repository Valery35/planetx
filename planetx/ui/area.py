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
"""
import math

import numpy as np
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import (QDoubleSpinBox, QHBoxLayout, QPushButton,
                                 QWidget)

from ..core import aef, editing
from ..core.features import Shape
from ..i18n import tr
from .handles import PropVertices

COLOR = (255, 255, 255, 255)  # контур участка на глобусе


class Area(QObject):
    """Участок окна dialog у окна глобуса window. side - сторона
    квадрата по умолчанию, км, most - наибольший размер участка, км,
    key - настройка, где помнится сторона. Сигнал changed - вершины
    или замыкание. У окна должно быть поле status."""

    changed = pyqtSignal()

    def __init__(self, window, dialog, side, most, key=None):
        super().__init__(dialog)
        self.window = window
        self.dialog = dialog
        self.most = float(most)
        self.key = key
        self.point = None  # середина квадрата (широта, долгота)
        self.ring = []  # вершины участка (широта, долгота)
        self.drawing = False  # участок рисуется щелчками
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
        self.side.setToolTip(tr(
            "Сторона квадрата участка с серединой в точке окна. Вершины "
            "участка тянутся мышью, кружок на середине стороны ставит "
            "новую вершину. Участок не больше {km} км.",
            km="{:g}".format(self.most)))
        square = QPushButton(tr("Квадрат"), dialog)
        square.setToolTip(tr("Участок - квадрат стороной из поля слева."))
        square.clicked.connect(self.reset_square)
        draw = QPushButton(tr("Нарисовать"), dialog)
        draw.setToolTip(tr(
            "Нарисовать участок многоугольником щелчками по глобусу. "
            "Щелчок по первой вершине замыкает его. Результат считается "
            "только внутри участка."))
        draw.clicked.connect(self.start_drawing)
        self.widget = QWidget(dialog)
        row = QHBoxLayout(self.widget)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.side, 1)
        row.addWidget(square)
        row.addWidget(draw)
        self.side.valueChanged.connect(self._side_changed)
        areas = getattr(window, "areas", None)
        if areas is not None:
            areas.append(self)

    # --- состояние ------------------------------------------------------

    def _side_changed(self, value):
        if self.key:
            QgsSettings().setValue(self.key, value)
        self.reset_square()

    def open_at(self, lat, lon):
        """Окно открыто у точки. Участок общий у окон анализа: точка
        внутри прежнего участка берёт его, иначе новый квадрат. Вершины
        на виде."""
        self.point = (lat, lon)
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
        self.edited()
        self.begin()

    def start_drawing(self):
        """Участок рисуется заново щелчками по глобусу."""
        self.ring = []
        self.drawing = True
        self.dialog.status.setText(tr(
            "Щёлкайте по глобусу вершины участка. Щелчок по первой "
            "вершине замыкает его."))
        self.edited()
        self.begin()

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
            if other is not self and other.visible() and not other.drawing:
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
        return self.drawing and self.visible()

    def add(self, lat, lon):
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
