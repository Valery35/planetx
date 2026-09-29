# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шкала температуры в углу вида: суша и море, в градусах Цельсия.

Цвета и подписи берутся из core/temperature.py. Виджет рисует себя
сам, фон полупрозрачный, как у подписи источников.
"""
from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter
from qgis.PyQt.QtWidgets import QWidget

from ..core import temperature
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
