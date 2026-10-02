# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шкалы в углу вида: температура суши и моря в градусах Цельсия,
уклон и экспозиция поверхности (core/slope.py), часы прямого солнца
(core/insolation.py).

Цвета и подписи берутся из core/temperature.py. Виджет рисует себя
сам, фон полупрозрачный, как у подписи источников.
"""
from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter
from qgis.PyQt.QtWidgets import QWidget

from ..core import insolation, slope, temperature
from ..i18n import tr
from ..qt_compat import enum

BAR_WIDTH = 180  # длина полосы шкалы, логических пикселей
BAR_HEIGHT = 9
PAD = 6
BACKGROUND = QColor(255, 255, 255, 190)
TEXT = QColor(30, 30, 30)


class TemperatureLegend(QWidget):
    """Две шкалы: суша и море."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.rows = ((tr("Суша, °C"), temperature.LAND_STOPS,
                      temperature.LAND_TICKS),
                     (tr("Море, °C"), temperature.SEA_STOPS,
                      temperature.SEA_TICKS))
        line = QFontMetrics(self.font()).height()
        self.row_height = line * 2 + BAR_HEIGHT + 2
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          len(self.rows) * self.row_height + PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        for n, (title, stops, ticks) in enumerate(self.rows):
            top = PAD // 2 + n * self.row_height
            painter.setPen(TEXT)
            painter.drawText(PAD, top + metrics.ascent(), title)
            bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
            gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
            for value, rgb in stops:
                gradient.setColorAt(temperature.share(stops, value),
                                    QColor(*rgb))
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(gradient)
            painter.drawRect(bar)
            painter.setPen(TEXT)
            for tick in ticks:
                x = bar.left() + temperature.share(stops, tick) * BAR_WIDTH
                painter.drawLine(int(x), int(bar.bottom()), int(x),
                                 int(bar.bottom()) + 2)
                text = "{:+d}".format(tick) if tick else "0"
                width = metrics.horizontalAdvance(text)
                painter.drawText(int(x - width / 2),
                                 int(bar.bottom()) + 2 + metrics.ascent(),
                                 text)
        painter.end()


class InsolationLegend(QWidget):
    """Шкала инсоляции - часы прямого света в сутки от 0 до top."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)
        self.top = 1.0

    def set_top(self, top):
        self.top = float(top)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(),
                         tr("Прямое солнце, ч в сутки"))
        bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for share, rgb in insolation.STOPS:
            gradient.setColorAt(share, QColor(*rgb))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(gradient)
        painter.drawRect(bar)
        painter.setPen(TEXT)
        for share in (0.0, 0.5, 1.0):
            x = bar.left() + share * BAR_WIDTH
            text = "{:g}".format(round(share * self.top, 1))
            width = metrics.horizontalAdvance(text)
            left = min(max(x - width / 2, 0.0), self.width() - width)
            painter.drawText(int(left),
                             int(bar.bottom()) + 2 + metrics.ascent(), text)
        painter.end()


class SlopeLegend(QWidget):
    """Шкала уклона - классы с границами в градусах, или экспозиции -
    цвета сторон света. mode - "slope" или "aspect"."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)
        self.mode = "slope"

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def _cells(self):
        """Клетки шкалы: (цвет, подпись под левым краем клетки)."""
        if self.mode == "aspect":
            names = (tr("С"), tr("СВ"), tr("В"), tr("ЮВ"), tr("Ю"),
                     tr("ЮЗ"), tr("З"), tr("СЗ"))
            return ([(slope.FLAT_COLOR, "")]
                    + [(rgb, name) for (_, rgb), name in
                       zip(slope.ASPECT_STOPS[:-1], names)])
        return [(rgb, "{:g}".format(low)) for low, rgb in slope.SLOPE_STOPS]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        title = tr("Экспозиция, ровное - серое") if self.mode == "aspect" \
            else tr("Уклон, °")
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), title)
        cells = self._cells()
        width = BAR_WIDTH / len(cells)
        y = top + line + 1
        for n, (rgb, label) in enumerate(cells):
            x = PAD + 4 + n * width
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(*rgb))
            painter.drawRect(QRectF(x, y, width, BAR_HEIGHT))
            if label:
                painter.setPen(TEXT)
                left = x if self.mode == "slope" \
                    else x + (width - metrics.horizontalAdvance(label)) / 2
                painter.drawText(int(left),
                                 int(y + BAR_HEIGHT) + 2 + metrics.ascent(),
                                 label)
        painter.end()
