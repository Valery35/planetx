# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Индикатор на стекле режима полёта, как в имитаторе Google Earth Pro:
шкала тангажа с линией горизонта, повёрнутая на крен, знак самолёта
в середине, лента курса сверху, ленты скорости слева и высоты справа,
вертикальная скорость, тяга и высота над землёй. Слой поверх вида,
мышь проходит сквозь. Деления считает core/flightsim.py.

Шкала тангажа стоит в фокусном расстоянии кадра, поэтому из кабины
линия горизонта шкалы ложится на горизонт Земли. Цвет, размеры
и шаги лент - выбор помощника, утверждает автор.
"""
import math

from qgis.PyQt.QtCore import QEvent, QPointF, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QPen
from qgis.PyQt.QtWidgets import QWidget

from ..core import flightsim
from ..i18n import tr
from ..qt_compat import enum

GREEN = (90, 255, 110, 235)
SHADOW = (0, 30, 0, 150)
LADDER_STEP = 5.0  # ° между ступенями шкалы тангажа
LADDER_REACH = 25.0
HEADING_STEP = 5.0  # ° между делениями ленты курса
HEADING_HALF = 30.0
SPEED_STEP = 20.0  # км/ч
SPEED_HALF = 100.0
ALT_STEP = 100.0  # м
ALT_HALF = 500.0
BASE = 800.0  # логических пикселей кадра на масштаб 1
CARDINALS = {0: "N", 90: "E", 180: "S", 270: "W"}


class FlightHud(QWidget):
    """Индикатор на стекле. set_state(None) прячет его."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.state = None
        self.resize(view.size())
        view.installEventFilter(self)
        self.hide()

    def set_state(self, state):
        """state - словарь speed (км/ч), alt, height (м), heading, pitch,
        roll (°), climb (м/с), throttle (%)."""
        self.state = state
        self.setVisible(state is not None)
        if state is not None:
            self.raise_()
            self.update()

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize"):
            self.resize(watched.size())
        return False

    def focal(self):
        """Фокусное расстояние кадра в логических пикселях."""
        fov = getattr(getattr(self.view, "camera", None), "fov_y", 45.0)
        return self.height() / 2.0 / math.tan(math.radians(fov) / 2.0)

    def paintEvent(self, event):
        if self.state is None:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(enum(QPainter, "RenderHint",
                                       "Antialiasing"))
            # Тень под знаками - чтобы шкала читалась над снегом
            # и облаками.
            self._draw(painter, QColor(*SHADOW), 1.2)
            self._draw(painter, QColor(*GREEN), 0.0)
        finally:
            painter.end()

    def _draw(self, painter, color, shift):
        s = self.state
        w, h = float(self.width()), float(self.height())
        k = min(max(min(w, h) / BASE, 0.6), 1.4)
        painter.save()
        painter.translate(shift, shift)
        pen = QPen(color)
        pen.setWidthF(1.6 * k)
        painter.setPen(pen)
        painter.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
        font = QFont(painter.font())
        font.setPixelSize(max(int(13 * k), 9))
        font.setBold(True)
        painter.setFont(font)
        cx, cy = w / 2.0, h / 2.0
        self._ladder(painter, pen, cx, cy, k, s["pitch"], s["roll"])
        self._plane(painter, cx, cy, k)
        self._heading(painter, cx, 36.0 * k, k, s["heading"])
        self._tape(painter, cx - 250.0 * k, cy, k, s["speed"], SPEED_STEP,
                   SPEED_HALF, left=True, unit=tr("км/ч"))
        self._tape(painter, cx + 250.0 * k, cy, k, s["alt"], ALT_STEP,
                   ALT_HALF, left=False, unit=tr("м"))
        self._text(painter, cx + 250.0 * k, cy + 140.0 * k,
                   tr("Подъём {climb} м/с",
                      climb="{:+.1f}".format(s["climb"])), k)
        self._throttle(painter, cx - 330.0 * k, cy + 150.0 * k, k,
                       s["throttle"])
        self._text(painter, cx, h - 92.0 * k,
                   tr("Над землёй {height} м",
                      height="{:.0f}".format(s["height"])), k)
        painter.restore()

    def _ladder(self, painter, pen, cx, cy, k, pitch, roll):
        focal = self.focal()
        painter.save()
        # Шкала тангажа - в поле между лентами, под лентой курса.
        top = 70.0 * k
        painter.setClipRect(QRectF(cx - 225.0 * k, top, 450.0 * k,
                                   self.height() - top - 110.0 * k))
        painter.translate(cx, cy)
        painter.rotate(-roll)
        gap = 55.0 * k
        for mark, angle in flightsim.ladder(pitch, LADDER_STEP,
                                            LADDER_REACH):
            y = -flightsim.ladder_offset(angle, focal)
            half = (190.0 if mark == 0 else
                    110.0 if mark % 10 == 0 else 85.0) * k
            dashed = QPen(pen)
            if mark < 0:
                dashed.setStyle(enum(Qt, "PenStyle", "DashLine"))
            painter.setPen(dashed)
            painter.drawLine(QPointF(-half, y), QPointF(-gap, y))
            painter.drawLine(QPointF(gap, y), QPointF(half, y))
            if mark != 0:
                tip = 8.0 * k if mark < 0 else -8.0 * k
                painter.drawLine(QPointF(-half, y), QPointF(-half, y - tip))
                painter.drawLine(QPointF(half, y), QPointF(half, y - tip))
                if mark % 10 == 0:
                    label = "{:.0f}".format(abs(mark))
                    painter.drawText(QRectF(-half - 40 * k, y - 10 * k,
                                            34 * k, 20 * k),
                                     self._align("AlignRight"), label)
                    painter.drawText(QRectF(half + 6 * k, y - 10 * k,
                                            34 * k, 20 * k),
                                     self._align("AlignLeft"), label)
        painter.restore()
        painter.setPen(pen)

    def _plane(self, painter, cx, cy, k):
        """Знак самолёта - крылья и точка, неподвижен в середине."""
        wing, drop = 45.0 * k, 10.0 * k
        painter.drawLine(QPointF(cx - wing, cy), QPointF(cx - 14 * k, cy))
        painter.drawLine(QPointF(cx - 14 * k, cy),
                         QPointF(cx - 7 * k, cy + drop))
        painter.drawLine(QPointF(cx - 7 * k, cy + drop),
                         QPointF(cx, cy))
        painter.drawLine(QPointF(cx, cy), QPointF(cx + 7 * k, cy + drop))
        painter.drawLine(QPointF(cx + 7 * k, cy + drop),
                         QPointF(cx + 14 * k, cy))
        painter.drawLine(QPointF(cx + 14 * k, cy), QPointF(cx + wing, cy))

    def _heading(self, painter, cx, top, k, heading):
        scale = 6.0 * k  # пикселей на градус
        for mark, offset in flightsim.heading_tape(heading, HEADING_STEP,
                                                   HEADING_HALF):
            x = cx + offset * scale
            whole = round(mark) % 10 == 0
            painter.drawLine(QPointF(x, top),
                             QPointF(x, top + (12.0 if whole else 6.0) * k))
            if whole:
                label = CARDINALS.get(int(round(mark)) % 360,
                                      "{:02d}".format(int(round(mark)) //
                                                      10))
                painter.drawText(QRectF(x - 20 * k, top + 13 * k, 40 * k,
                                        18 * k),
                                 self._align("AlignHCenter"), label)
        # Значение курса в рамке над лентой.
        box = QRectF(cx - 26 * k, top - 26 * k, 52 * k, 20 * k)
        painter.drawRect(box)
        painter.drawText(box, self._align("AlignCenter"),
                         "{:03.0f}".format(heading % 360.0))
        painter.drawLine(QPointF(cx, top - 6 * k), QPointF(cx, top))

    def _tape(self, painter, x, cy, k, value, step, half, left, unit):
        scale = 120.0 * k / half  # пикселей на единицу
        side = -1.0 if left else 1.0
        painter.drawLine(QPointF(x, cy - 120 * k), QPointF(x, cy + 120 * k))
        for mark, offset in flightsim.tape(value, step, half):
            y = cy - offset * scale
            painter.drawLine(QPointF(x, y), QPointF(x + side * 10 * k, y))
            if abs(y - cy) < 18.0 * k:
                continue  # подпись закрыла бы рамка значения
            rect = QRectF(x + side * 14 * k - (60 * k if left else 0), y -
                          9 * k, 60 * k, 18 * k)
            painter.drawText(rect, self._align("AlignRight" if left
                                               else "AlignLeft"),
                             "{:.0f}".format(mark))
        box = QRectF(x - (78 * k if left else -6 * k), cy - 12 * k,
                     72 * k, 24 * k)
        painter.drawRect(box)
        painter.drawText(box, self._align("AlignCenter"),
                         "{:.0f}".format(value))
        painter.drawText(QRectF(x - 40 * k, cy - 148 * k, 80 * k, 18 * k),
                         self._align("AlignHCenter"), unit)

    def _throttle(self, painter, x, y, k, throttle):
        height = 90.0 * k
        painter.drawRect(QRectF(x - 6 * k, y - height, 12 * k, height))
        level = y - height * min(max(throttle, 0.0), 100.0) / 100.0
        painter.drawLine(QPointF(x - 12 * k, level),
                         QPointF(x + 12 * k, level))
        self._text(painter, x, y + 14 * k,
                   tr("Тяга {throttle} %",
                      throttle="{:.0f}".format(throttle)), k)

    def _text(self, painter, x, y, text, k):
        painter.drawText(QRectF(x - 120 * k, y - 10 * k, 240 * k, 20 * k),
                         self._align("AlignHCenter"), text)

    @staticmethod
    def _align(name):
        if name == "AlignCenter":
            return enum(Qt, "AlignmentFlag", "AlignCenter")
        return enum(Qt, "AlignmentFlag", name) | enum(
            Qt, "AlignmentFlag", "AlignVCenter")
