# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вершины рисуемого или изменяемого объекта: кружки и перетаскивание.

DrawVertices - точки окна «Новая метка», которые тянутся мышью
(render/view.py, vertex_tool). Кружок в середине отрезка ставит на нём
новую вершину. Щелчок по первой вершине замыкает фигуру, по последней
завершает путь (core/editing.py). Handles - прозрачный слой поверх вида,
как подписи неба (ui/skylabels.py), рисует кружки и подсказку у курсора.
"""
import math

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetricsF, QPainter, QPen
from qgis.PyQt.QtWidgets import QWidget

from ..core import editing
from ..core.ellipsoid import geodetic_to_ecef
from ..core.measure import segment_midpoints
from ..i18n import tr
from ..qt_compat import enum

GRAB_PIXELS = 9.0  # логических пикселей вокруг кружка, в них он хватается
CLICK_PIXELS = 4.0  # дальше - уже перетаскивание, как у вида
VERTEX_RADIUS = 5.0
MIDDLE_RADIUS = 4.0
MAX_HANDLES = 1500  # кружков на экране, не больше
EDGE = QColor(40, 40, 40)
FILL = QColor(255, 255, 255)
MIDDLE_FILL = QColor(255, 255, 255, 110)
HOT = QColor(255, 214, 64)
HINT_BACK = QColor(255, 221, 87)
HINT_TEXT = QColor(30, 30, 30)
HINT_FONT = 12.0
HINT_OFFSET = (14.0, 18.0)


class DrawVertices:
    """Вершины и середины отрезков объекта окна «Новая метка»."""

    def __init__(self, window):
        self.window = window
        self.index = None
        self.hot = None  # что под курсором: (вид, номер) или None
        self.cursor = None
        self._press = None
        self._moved = False
        self._fresh = False  # вершина только что вставлена серединой

    @property
    def tool(self):
        return self.window.drawer

    def active(self):
        window = self.window
        return window._place_open() and window.view.sky_view is None \
            and bool(self.tool.points)

    def closed(self):
        return self.tool.mode == "polygon" and len(self.tool.points) >= 3

    def middles(self):
        """Середины отрезков, (широта, долгота). У метки их нет."""
        tool = self.tool
        if tool.mode == "point" or len(tool.points) < 2:
            return []
        return segment_midpoints(tool.points, self.closed())

    def _project(self, points):
        if not points:
            return np.zeros((0, 2)), np.zeros(0, dtype=bool)
        view = self.window.view
        lats = np.array([p[0] for p in points])
        lons = np.array([p[1] for p in points])
        xyz = geodetic_to_ecef(lats, lons, view.store.heights_at(lats, lons))
        pixels, front = view.camera.project(xyz)
        return np.asarray(pixels, dtype=np.float64).reshape(-1, 2), \
            np.asarray(front, dtype=bool)

    def screen(self):
        """Вершины и середины в пикселях кадра с признаком «перед
        камерой»: (вершины, перед, середины, перед)."""
        return self._project(self.tool.points) + self._project(self.middles())

    def under(self, px, py):
        if not self.active():
            return None
        radius = GRAB_PIXELS * self.window.view.devicePixelRatioF()
        return editing.pick(*self.screen(), px, py, radius)

    # Протокол vertex_tool вида.

    def grab(self, px, py):
        found = self.under(px, py)
        if found is None:
            return False
        kind, index = found
        tool = self.tool
        self._fresh = kind == editing.MIDDLE
        if self._fresh:
            tool.insert(index + 1, *self.middles()[index])
            index += 1
        self.index = index
        self._press = (px, py)
        self._moved = False
        self.hot = None
        return True

    def move(self, px, py):
        window = self.window
        if self.index is None:
            return
        limit = CLICK_PIXELS * window.view.devicePixelRatioF()
        if not self._moved and self._press is not None and math.hypot(
                px - self._press[0], py - self._press[1]) <= limit:
            return
        self._moved = True
        found = window._ground(px, py)
        if found is not None:
            self.tool.move(self.index, *found)

    def drop(self):
        index, self.index = self.index, None
        if index is None or self._moved or self._fresh:
            return
        tool = self.tool
        result = editing.click_result(tool.mode, len(tool.points), index,
                                      tool.finished)
        if result == editing.CLOSE and tool.mode == "path" \
                and self.window.editing_key is None:
            self.window.place_dialog.to_polygon()
        if result is not None:
            tool.finish()

    # Подсказка у курсора.

    def hover(self, px, py):
        """Курсор над видом без нажатых кнопок, (-1, -1) - ушёл."""
        hot = self.under(px, py) if px >= 0.0 else None
        cursor = (px, py) if hot is not None else None
        if hot != self.hot or cursor != self.cursor:
            self.hot = hot
            self.cursor = cursor
            self.window.handles.update()

    def hint(self):
        """Текст подсказки для того, что под курсором, или пусто."""
        if self.hot is None:
            return ""
        kind, index = self.hot
        tool = self.tool
        if kind == editing.MIDDLE:
            return tr("Добавить вершину")
        result = editing.click_result(tool.mode, len(tool.points), index,
                                      tool.finished)
        if result == editing.CLOSE:
            return tr("Замкнуть фигуру")
        if result == editing.FINISH:
            return tr("Завершить путь")
        return ""


class Handles(QWidget):
    """Кружки вершин и середин отрезков поверх вида view."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.tool = None  # DrawVertices, ставит окно
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.shown = (0, 0, "")  # вершин, середин и подсказка, для проверок
        self.hide()

    def sync(self):
        """Показать слой, пока есть что править, и перерисовать."""
        on = self.tool is not None and self.tool.active()
        if on:
            self.setGeometry(0, 0, self.view.width(), self.view.height())
            if not self.isVisible():
                self.show()
            self.update()
        elif self.isVisible():
            self.shown = (0, 0, "")
            self.hide()

    def _circles(self, painter, pixels, front, radius, fill, hot, width,
                 height):
        count = 0
        for n, ((x, y), ahead) in enumerate(zip(pixels, front)):
            if not ahead or not (0.0 <= x <= width and 0.0 <= y <= height):
                continue
            if count >= MAX_HANDLES:
                break
            painter.setBrush(HOT if n == hot else fill)
            painter.drawEllipse(QPointF(float(x), float(y)), radius, radius)
            count += 1
        return count

    def draw(self, painter, width, height, scale):
        """Кружки и подсказка на холст в пикселях кадра. scale -
        пикселей кадра на логический пиксель."""
        tool = self.tool
        vertices, vfront, middles, mfront = tool.screen()
        hot_kind, hot_index = tool.hot or (None, None)
        if tool.index is not None:
            hot_kind, hot_index = editing.VERTEX, tool.index
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        pen = QPen(EDGE)
        pen.setWidthF(1.2 * scale)
        painter.setPen(pen)
        shown_middles = self._circles(
            painter, middles, mfront, MIDDLE_RADIUS * scale, MIDDLE_FILL,
            hot_index if hot_kind == editing.MIDDLE else None, width,
            height)
        shown_vertices = self._circles(
            painter, vertices, vfront, VERTEX_RADIUS * scale, FILL,
            hot_index if hot_kind == editing.VERTEX else None, width,
            height)
        text = tool.hint()
        if text and tool.cursor is not None:
            font = QFont()
            font.setPixelSize(max(6, int(round(HINT_FONT * scale))))
            painter.setFont(font)
            metrics = QFontMetricsF(font)
            w = metrics.horizontalAdvance(text) if hasattr(
                metrics, "horizontalAdvance") else metrics.width(text)
            pad = 6.0 * scale
            rect = QRectF(tool.cursor[0] + HINT_OFFSET[0] * scale,
                          tool.cursor[1] + HINT_OFFSET[1] * scale,
                          w + 2.0 * pad, metrics.height() + pad)
            # Подсказка у правого или нижнего края уходит внутрь кадра.
            if rect.right() > width:
                rect.moveRight(tool.cursor[0] - HINT_OFFSET[0] * scale)
            if rect.bottom() > height:
                rect.moveBottom(tool.cursor[1] - HINT_OFFSET[1] * scale)
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(HINT_BACK)
            painter.drawRoundedRect(rect, 3.0 * scale, 3.0 * scale)
            painter.setPen(HINT_TEXT)
            painter.drawText(rect, enum(Qt, "AlignmentFlag", "AlignCenter"),
                             text)
        return shown_vertices, shown_middles, text

    def paintEvent(self, event):
        if self.tool is None or not self.tool.active():
            return
        cam = self.view.camera
        ratio = self.view.devicePixelRatioF()
        p = QPainter(self)
        try:
            # Проекция - в пикселях кадра, холст виджета - в логических.
            p.scale(1.0 / ratio, 1.0 / ratio)
            self.shown = self.draw(p, cam.width, cam.height, ratio)
        finally:
            p.end()
