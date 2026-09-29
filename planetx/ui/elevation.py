# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Профиль высот, как «Показать профиль высот» Google Earth.

Немодальное окно с графиком высоты вдоль линии или пути. Под графиком
наименьшая и наибольшая высота, набор и потеря высоты, средний
и наибольший уклон. Курсор над графиком отмечает точку на глобусе.
Расчёт - core/measure.py, высоты - тайлы Mapzen Terrain, недостающие
просятся у окна глобуса.
"""
import math

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import QDialog, QLabel, QVBoxLayout, QWidget

from ..i18n import tr
from ..qt_compat import enum
from .measure import line_profile

LINE = QColor(255, 214, 0)  # жёлтый, как линия линейки
FILL = QColor(255, 214, 0, 70)
GRID = QColor(128, 128, 128, 90)
MARGIN = (54, 12, 14, 30)  # слева, сверху, справа, снизу, пиксели
CENTER = enum(Qt, "AlignmentFlag", "AlignCenter")
VCENTER = enum(Qt, "AlignmentFlag", "AlignVCenter")
RIGHT = enum(Qt, "AlignmentFlag", "AlignRight") | VCENTER
LEFT = enum(Qt, "AlignmentFlag", "AlignLeft") | VCENTER


class HeightSource:
    """Высоты для профиля пути из «Моих меток». То же устройство, что
    у линейки: heights, has_heights, ask_heights и память выборки."""

    def __init__(self, heights, has_heights, ask_heights):
        self.heights = heights
        self.has_heights = has_heights
        self.ask_heights = ask_heights
        self._samples = (None, None, None, None)


def nice_step(span, count=5):
    """Шаг делений оси: 1, 2 или 5 на степень десяти, около count делений."""
    if span <= 0.0:
        return 1.0
    raw = span / count
    power = 10.0 ** math.floor(math.log10(raw))
    for factor in (1.0, 2.0, 5.0, 10.0):
        if raw <= factor * power:
            return factor * power
    return 10.0 * power


NBSP = "\u00a0"  # число и единица не разрываются переносом


def distance_text(metres):
    if metres >= 100000.0:
        text = tr("{value} км", value="{:.0f}".format(metres / 1000.0))
    elif metres >= 1000.0:
        text = tr("{value} км", value="{:.1f}".format(metres / 1000.0))
    else:
        text = tr("{value} м", value="{:.0f}".format(metres))
    return text.replace(" ", NBSP)


def axis_text(metres, step):
    """Подпись деления оси расстояний: знаков после точки столько,
    сколько нужно шагу делений."""
    if step >= 1000.0:
        digits = 0 if step % 1000.0 == 0 else 1
        return tr("{value} км", value="{:.{d}f}".format(
            metres / 1000.0, d=digits)).replace(" ", NBSP)
    return tr("{value} м", value="{:.0f}".format(metres)).replace(" ", NBSP)


def height_text(metres):
    return tr("{value} м", value="{:.0f}".format(metres)).replace(" ", NBSP)


def percent(value):
    return "{:.1f}{}%".format(100.0 * value, NBSP)


class ProfileChart(QWidget):
    """График: высота по расстоянию. Сигнал hovered - доля пути под
    курсором 0-1 или -1, когда курсора над графиком нет."""

    hovered = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.profile = None
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumSize(420, 180)

    def set_profile(self, profile):
        self.profile = profile
        self.update()

    def _plot(self):
        left, top, right, bottom = MARGIN
        return QRectF(left, top, max(1.0, self.width() - left - right),
                      max(1.0, self.height() - top - bottom))

    def _ranges(self):
        p = self.profile
        low, high = p.low, p.high
        pad = max((high - low) * 0.08, 1.0)
        return 0.0, max(p.flat, 1.0), low - pad, high + pad

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        rect = self._plot()
        p = self.profile
        if p is None or len(p.distance) < 2:
            painter.drawText(rect, CENTER,
                             tr("Нет данных"))
            return
        x0, x1, y0, y1 = self._ranges()

        def to_screen(d, h):
            return QPointF(rect.left() + (d - x0) / (x1 - x0) * rect.width(),
                           rect.bottom() - (h - y0) / (y1 - y0)
                           * rect.height())
        # Сетка и подписи осей: линии цветом сетки, подписи цветом текста.
        grid = QPen(GRID, 1.0)
        text = QPen(self.palette().text().color())
        step = nice_step(y1 - y0, 4)
        h = math.ceil(y0 / step) * step
        while h <= y1:
            point = to_screen(x0, h)
            painter.setPen(grid)
            painter.drawLine(QPointF(rect.left(), point.y()),
                             QPointF(rect.right(), point.y()))
            painter.setPen(text)
            painter.drawText(QRectF(0, point.y() - 8, MARGIN[0] - 6, 16),
                             RIGHT, height_text(h))
            h += step
        step = nice_step(x1 - x0, 6)
        d = 0.0
        while d <= x1:
            point = to_screen(d, y0)
            painter.setPen(grid)
            painter.drawLine(QPointF(point.x(), rect.top()),
                             QPointF(point.x(), rect.bottom()))
            painter.setPen(text)
            painter.drawText(QRectF(point.x() - 40, rect.bottom() + 4, 80,
                                    16), CENTER, axis_text(d, step))
            d += step
        # Кривая высоты с заливкой.
        path = QPainterPath(to_screen(p.distance[0], y0))
        for dist, height in zip(p.distance, p.height):
            path.lineTo(to_screen(float(dist), float(height)))
        path.lineTo(to_screen(float(p.distance[-1]), y0))
        path.closeSubpath()
        painter.fillPath(path, FILL)
        painter.setPen(QPen(LINE.darker(130), 1.6))
        for i in range(len(p.distance) - 1):
            painter.drawLine(to_screen(float(p.distance[i]),
                                       float(p.height[i])),
                             to_screen(float(p.distance[i + 1]),
                                       float(p.height[i + 1])))
        if self.hover is not None:
            i = self.hover
            point = to_screen(float(p.distance[i]), float(p.height[i]))
            painter.setPen(QPen(QColor(220, 60, 40), 1.2))
            painter.drawLine(QPointF(point.x(), rect.top()),
                             QPointF(point.x(), rect.bottom()))
            painter.drawEllipse(point, 3.5, 3.5)
            slope = self._slope(i)
            text = tr("{distance}, высота {height}, уклон {slope}",
                      distance=distance_text(float(p.distance[i])),
                      height=height_text(float(p.height[i])),
                      slope=percent(slope))
            painter.setPen(QPen(self.palette().text().color()))
            painter.drawText(QRectF(rect.left() + 6, rect.top() + 2,
                                    rect.width() - 12, 16),
                             LEFT, text)

    def _slope(self, i):
        """Уклон у точки i на отрезке не короче окна профиля."""
        p = self.profile
        last = len(p.distance) - 1
        j = int(min(max(np.searchsorted(p.distance, p.distance[i]
                                        + p.window), i + 1), last))
        k = i if j > i else max(i - 1, 0)
        run = float(p.distance[j] - p.distance[k])
        return abs(float(p.height[j] - p.height[k])) / run if run else 0.0

    def mouseMoveEvent(self, event):
        p = self.profile
        if p is None or len(p.distance) < 2:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        rect = self._plot()
        share = (pos.x() - rect.left()) / rect.width()
        if not 0.0 <= share <= 1.0:
            self.leaveEvent(event)
            return
        i = int(np.clip(np.searchsorted(p.distance, share * p.flat), 0,
                        len(p.distance) - 1))
        if i != self.hover:
            self.hover = i
            self.update()
            self.hovered.emit(float(i))

    def leaveEvent(self, event):
        if self.hover is not None:
            self.hover = None
            self.update()
            self.hovered.emit(-1.0)



class ProfileDialog(QDialog):
    """Окно «Профиль высот». points - функция, дающая точки линии,
    source - высоты (Ruler или HeightSource). Сигнал point_hovered -
    точка под курсором графика (широта, долгота, высота) или None."""

    point_hovered = pyqtSignal(object)

    def __init__(self, title, points, source, parent=None):
        super().__init__(parent)
        self.setModal(False)
        self.points = points
        self.source = source
        self.chart = ProfileChart(self)
        self.chart.hovered.connect(self._hovered)
        self.stats = QLabel(self)
        self.stats.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.stats)
        self.set_title(title)
        self.resize(640, 320)
        self.refresh()

    def set_title(self, title):
        self.setWindowTitle(tr("Профиль высот: {name}", name=title)
                            if title else tr("Профиль высот"))

    def set_points(self, title, points, source):
        self.set_title(title)
        self.points = points
        self.source = source
        self.refresh()

    def refresh(self):
        found = line_profile(self.points(), self.source)
        if found is None:
            self.chart.set_profile(None)
            self.stats.setText(tr("Отметьте на глобусе хотя бы две точки."))
            return
        p, ready = found
        self.chart.set_profile(p)
        text = tr(
            "Длина по карте {flat}, по рельефу {ground}. Наименьшая "
            "высота {low}, наибольшая {high}. Набор высоты {gain}, "
            "потеря {loss}. Средний уклон {mean}, наибольший {max}.",
            flat=distance_text(p.flat), ground=distance_text(p.ground),
            low=height_text(p.low), high=height_text(p.high),
            gain=height_text(p.gain), loss=height_text(p.loss),
            mean=percent(p.mean_slope), max=percent(p.max_slope))
        if not ready:
            text += " " + tr("Высоты ещё загружаются, числа уточнятся.")
        self.stats.setText(text)

    def _hovered(self, index):
        p = self.chart.profile
        if index < 0 or p is None:
            self.point_hovered.emit(None)
            return
        i = int(index)
        lat, lon = p.latlon[i]
        self.point_hovered.emit((float(lat), float(lon),
                                 float(p.height[i])))
