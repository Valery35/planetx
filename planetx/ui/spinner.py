# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Значок загрузки в углу вида: вращающаяся дуга.

Виден, пока кадр ждёт тайлы, высоты, картинки слоёв или надписи,
то есть пока в строке состояния стоит «загрузка N». Короткая
подгрузка значок не зажигает, он появляется через SHOW_DELAY.
Вставшая загрузка красит дугу оранжевым. Подсказка значка повторяет
количество ждущего. Решение автора от 29 сентября 2026 года.
"""
import time

from qgis.PyQt.QtCore import QRectF, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import QWidget

from ..i18n import tr
from ..qt_compat import enum

SIZE = 26  # сторона значка, логических пикселей
TICK = 40  # мс между кадрами вращения
TURN = 360.0  # градусов дуги в секунду
ARC = 270  # длина дуги, градусов
SHOW_DELAY = 0.4  # с загрузки до появления значка
BACKGROUND = QColor(255, 255, 255, 200)
LOADING = QColor(40, 110, 200)
STALLED = QColor(230, 130, 20)


class LoadSpinner(QWidget):
    """Вращающаяся дуга, пока идёт загрузка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SIZE, SIZE)
        self.angle = 0.0
        self.stalled = False
        self.since = None  # момент начала загрузки
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._turn)
        self.hide()

    def set_state(self, missing, stalled):
        """Сколько ждёт кадр и сколько секунд стоит загрузка."""
        if missing <= 0:
            self.since = None
            self.timer.stop()
            self.hide()
            return
        if self.since is None:
            self.since = time.monotonic()
        self.stalled = stalled > 0
        self.setToolTip(
            tr("Загрузка стоит {seconds} с", seconds=int(stalled))
            if self.stalled else
            tr("Идёт загрузка: {count}", count=missing))
        if not self.timer.isActive():
            self.timer.start()
        self.update()

    def _turn(self):
        if self.since is None:
            return
        if not self.isVisible():
            if time.monotonic() - self.since < SHOW_DELAY:
                return
            self.show()
            self.raise_()
        self.angle = (self.angle + TURN * TICK / 1000.0) % 360.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawEllipse(QRectF(0.5, 0.5, SIZE - 1.0, SIZE - 1.0))
        pen = QPen(STALLED if self.stalled else LOADING, 3.0)
        pen.setCapStyle(enum(Qt, "PenCapStyle", "RoundCap"))
        painter.setPen(pen)
        painter.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
        # Углы дуги Qt - в шестнадцатых долях градуса, против часовой.
        painter.drawArc(QRectF(6.0, 6.0, SIZE - 12.0, SIZE - 12.0),
                        int(-self.angle * 16), ARC * 16)
        painter.end()
