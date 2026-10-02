# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Разрез»: разрез Земли вниз вдоль пути.

Шаг 4 плана «сверху вниз», 2 октября 2026 года. График - расстояние
вдоль линии и глубина вниз: слои коры CRUST1.0, оболочки PREM, плиты
Slab2, очаги землетрясений из полосы вдоль линии. Цвета - те же, что
на гранях разреза Земли (core/cutaway.py) и у шкалы очагов. Расчёт -
core/section.py, данные просит окно глобуса. Курсор над графиком
отмечает точку на глобусе, как у профиля высот.
"""
import math

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDoubleSpinBox,
                                 QFormLayout, QHBoxLayout, QLabel,
                                 QVBoxLayout, QWidget)

from ..core import cutaway, quakes, section
from ..i18n import tr
from ..qt_compat import enum
from .elevation import NBSP, axis_text, distance_text, nice_step
from .legend import CutawayLegend

GRID = QColor(128, 128, 128, 90)
MARGIN = (60, 12, 14, 30)  # слева, сверху, справа, снизу, пиксели
CENTER = enum(Qt, "AlignmentFlag", "AlignCenter")
VCENTER = enum(Qt, "AlignmentFlag", "AlignVCenter")
RIGHT = enum(Qt, "AlignmentFlag", "AlignRight") | VCENTER
LEFT = enum(Qt, "AlignmentFlag", "AlignLeft") | VCENTER
QUAKE_SHRINK = 0.6  # очаг на графике меньше, чем на глобусе


def km_text(value):
    return tr("{value} км", value="{:g}".format(round(value, 1))).replace(
        " ", NBSP)


class SectionChart(QWidget):
    """График разреза. Сигнал hovered - номер точки линии под курсором
    или -1."""

    hovered = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.section = None
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 260)

    def set_section(self, value):
        self.section = value
        self.hover = None
        self.update()

    def _plot(self):
        left, top, right, bottom = MARGIN
        return QRectF(left, top, max(1.0, self.width() - left - right),
                      max(1.0, self.height() - top - bottom))

    def _mapper(self):
        rect = self._plot()
        s = self.section
        x1 = max(float(s.distance[-1]), 1.0)
        y1 = s.depth

        def to_screen(d, depth):
            depth = min(max(depth, 0.0), y1)
            return QPointF(rect.left() + d / x1 * rect.width(),
                           rect.top() + depth / y1 * rect.height())
        return rect, x1, y1, to_screen

    def _fill(self, painter, to_screen, top, bottom, color):
        """Слой между линиями top и bottom (глубины по точкам линии),
        кусками там, где обе определены и слой не нулевой."""
        s = self.section
        good = np.isfinite(top) & np.isfinite(bottom) & (bottom > top)
        start = None
        for i in range(len(good) + 1):
            on = i < len(good) and bool(good[i])
            if on and start is None:
                start = i
            elif not on and start is not None:
                run = range(start, i)
                path = QPainterPath(to_screen(float(s.distance[start]),
                                              float(top[start])))
                for k in run:
                    path.lineTo(to_screen(float(s.distance[k]),
                                          float(top[k])))
                for k in reversed(run):
                    path.lineTo(to_screen(float(s.distance[k]),
                                          float(bottom[k])))
                path.closeSubpath()
                painter.fillPath(path, QColor(*color))
                start = None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        s = self.section
        if s is None:
            painter.drawText(self._plot(), CENTER, tr("Нет данных"))
            return
        rect, x1, y1, to_screen = self._mapper()
        n = len(s.distance)
        # Оболочки PREM: верхняя мантия от Мохо, остальные - ровные.
        moho = section.moho(s)
        for key, top, bottom, color in section.shells_below(s):
            upper = moho if key == "upper_mantle" else np.full(n, top)
            self._fill(painter, to_screen, upper, np.full(n, bottom), color)
        # Кора: слои CRUST1.0 или слой PREM до Мохо.
        if s.bounds is not None:
            depths = -s.bounds
            for k, key in enumerate(cutaway.crust_layers()):
                self._fill(painter, to_screen, depths[:, k],
                           depths[:, k + 1], cutaway.CRUST_COLORS[key])
        else:
            crust = [c for c in cutaway.SHELLS if c[0] == "crust"][0]
            self._fill(painter, to_screen, np.zeros(n), moho, crust[3])
        # Плита поверх мантии и коры.
        self._fill(painter, to_screen, s.slab_top, s.slab_bottom,
                   cutaway.SLAB_COLOR)
        # Очаги: цвет по глубине, размер по магнитуде, как на глобусе.
        if s.quakes:
            depth = np.array([q[1] for q in s.quakes])
            colors = quakes.depth_colors(depth)
            sizes = quakes.sizes([q[2] for q in s.quakes]) * QUAKE_SHRINK
            painter.setPen(QPen(QColor(40, 40, 40), 0.8))
            for (d, z, _, _), rgb, size in zip(s.quakes, colors, sizes):
                if z > y1:
                    continue
                painter.setBrush(QColor(*(int(v) for v in rgb)))
                painter.drawEllipse(to_screen(d, z), size / 2.0, size / 2.0)
        # Сетка и подписи осей.
        grid = QPen(GRID, 1.0)
        text = QPen(self.palette().text().color())
        step = nice_step(y1, 5)
        z = 0.0
        while z <= y1 + 1e-9:
            point = to_screen(0.0, z)
            painter.setPen(grid)
            painter.drawLine(QPointF(rect.left(), point.y()),
                             QPointF(rect.right(), point.y()))
            painter.setPen(text)
            painter.drawText(QRectF(0, point.y() - 8, MARGIN[0] - 6, 16),
                             RIGHT, km_text(z))
            z += step
        step = nice_step(x1, 6)
        d = 0.0
        while d <= x1 + 1e-9:
            point = to_screen(d, y1)
            painter.setPen(grid)
            painter.drawLine(QPointF(point.x(), rect.top()),
                             QPointF(point.x(), rect.bottom()))
            painter.setPen(text)
            painter.drawText(QRectF(point.x() - 40, rect.bottom() + 4, 80,
                                    16), CENTER,
                             axis_text(d * 1000.0, step * 1000.0))
            d += step
        if self.hover is not None:
            i = self.hover
            top = to_screen(float(s.distance[i]), 0.0)
            painter.setPen(QPen(QColor(220, 60, 40), 1.2))
            painter.drawLine(QPointF(top.x(), rect.top()),
                             QPointF(top.x(), rect.bottom()))
            painter.setPen(text)
            painter.drawText(QRectF(rect.left() + 6, rect.top() + 2,
                                    rect.width() - 12, 16), LEFT,
                             self._hover_text(i))

    def _hover_text(self, i):
        s = self.section
        parts = [distance_text(float(s.distance[i]) * 1000.0),
                 tr("Мохо {depth}", depth=km_text(
                     float(section.moho(s)[i])))]
        if math.isfinite(s.slab_top[i]):
            parts.append(tr("плита {top}-{bottom}",
                            top=km_text(float(s.slab_top[i])),
                            bottom=km_text(float(s.slab_bottom[i]))))
        return ", ".join(parts)

    def mouseMoveEvent(self, event):
        s = self.section
        if s is None:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        rect = self._plot()
        share = (pos.x() - rect.left()) / rect.width()
        if not 0.0 <= share <= 1.0:
            self.leaveEvent(event)
            return
        i = int(np.clip(np.searchsorted(s.distance,
                                        share * float(s.distance[-1])),
                        0, len(s.distance) - 1))
        if i != self.hover:
            self.hover = i
            self.update()
            self.hovered.emit(i)

    def leaveEvent(self, event):
        if self.hover is not None:
            self.hover = None
            self.update()
            self.hovered.emit(-1)


class SectionDialog(QDialog):
    """Окно «Разрез». provider(depth, width) даёт core.section.Section
    или None. Сигнал point_hovered - (широта, долгота, км вдоль линии)
    или None."""

    point_hovered = pyqtSignal(object)

    def __init__(self, title, provider, parent=None):
        super().__init__(parent)
        self.setModal(False)
        self.provider = provider
        self.depth = QComboBox(self)
        for value in section.DEPTHS:
            self.depth.addItem(km_text(value), value)
        self.depth.setCurrentIndex(section.DEPTHS.index(section.DEPTH))
        self.depth.setToolTip(tr(
            "До какой глубины идёт разрез. 700 км - низ переходной зоны, "
            "глубже землетрясений почти нет. 2891 км - граница ядра, "
            "6371 км - центр Земли."))
        self.depth.currentIndexChanged.connect(self.refresh)
        self.band = QDoubleSpinBox(self)
        self.band.setRange(10.0, 1000.0)
        self.band.setDecimals(0)
        self.band.setSingleStep(10.0)
        self.band.setSuffix(" " + tr("км"))
        self.band.setValue(section.WIDTH)
        self.band.setKeyboardTracking(False)
        self.band.setToolTip(tr(
            "Ширина полосы вдоль линии, из которой очаги землетрясений "
            "переносятся на разрез. Шире полоса - больше очагов, но "
            "дальние очаги лежат не там, где линия."))
        self.band.valueChanged.connect(self.refresh)
        form = QFormLayout()
        form.addRow(tr("Глубина"), self.depth)
        form.addRow(tr("Полоса очагов"), self.band)
        self.chart = SectionChart(self)
        self.chart.hovered.connect(self._hovered)
        self.legend = CutawayLegend(self)
        self.stats = QLabel(self)
        self.stats.setWordWrap(True)
        row = QHBoxLayout()
        row.addWidget(self.chart, 1)
        row.addWidget(self.legend, 0, enum(Qt, "AlignmentFlag", "AlignTop"))
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addLayout(row, 1)
        layout.addWidget(self.stats)
        self.set_title(title)
        self.resize(900, 460)
        self.refresh()

    def set_title(self, title):
        self.setWindowTitle(tr("Разрез: {name}", name=title) if title
                            else tr("Разрез"))

    def set_source(self, title, provider):
        self.set_title(title)
        self.provider = provider
        self.refresh()

    def settings(self):
        return float(self.depth.currentData()), float(self.band.value())

    def refresh(self, *args):
        depth, width = self.settings()
        found, notes = self.provider(depth, width)
        self.chart.set_section(found)
        if found is None:
            self.stats.setText(tr("Нужен путь хотя бы из двух точек."))
            return
        self.legend.set_crust(found.bounds is not None)
        self.legend.set_slabs(bool(np.any(np.isfinite(found.slab_top))))
        text = tr("Длина {length}, глубина {depth}. Очагов землетрясений "
                  "в полосе {count}.",
                  length=distance_text(float(found.distance[-1]) * 1000.0),
                  depth=km_text(found.depth), count=len(found.quakes))
        if notes:
            text += " " + notes
        self.stats.setText(text)

    def _hovered(self, index):
        s = self.chart.section
        if index < 0 or s is None:
            self.point_hovered.emit(None)
            return
        self.point_hovered.emit((float(s.lats[index]), float(s.lons[index]),
                                 float(s.distance[index])))
