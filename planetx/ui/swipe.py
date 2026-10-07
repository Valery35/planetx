# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шторка сравнения двух дней темы NASA поверх вида.

Просьба автора от 7 октября 2026 года - «шторку сравнения двух дат».
Левее шторки тема показана на свой день (слой вида «compare»,
render/gibs.py), правее - на день шкалы времени. Белую линию по
границе рисует шейдер тайла, поэтому она есть и на снимке вида
и в записи тура. Здесь - полоса, за которую тянется шторка, кружок
посередине и бирки с днями: слева со шагами ◂ ▸ по ряду темы,
справа - день шкалы. Окно глобуса ставит дни и слушает сигналы.
"""
from qgis.PyQt.QtCore import QEvent, QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QCursor, QPainter, QPen
from qgis.PyQt.QtWidgets import (QFrame, QHBoxLayout, QLabel, QToolButton,
                                 QWidget)

from ..i18n import tr
from ..qt_compat import enum

GRIP = 28  # ширина полосы, за которую тянется шторка, логических пикселей
KNOB = 11.0  # радиус кружка посередине
EDGE = 0.02  # шторка не подходит к краю вида ближе этой доли ширины
GAP = 10  # от линии до бирки
RAISE = 46  # бирки выше середины вида
STYLE = ("QFrame#planetxSwipe { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")


class SwipeBar(QWidget):
    """Полоса шторки во всю высоту вида. Сигналы moved - новая доля
    ширины вида, stepped - шаг дня левой части (-1 или 1), closed -
    шторка закрыта крестиком."""

    moved = pyqtSignal(float)
    stepped = pyqtSignal(int)
    closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.share = 0.5
        self.setCursor(QCursor(enum(Qt, "CursorShape", "SizeHorCursor")))
        self.setToolTip(tr("Шторка сравнения: тянется мышью."))
        self.left = QFrame(parent)
        self.left.setObjectName("planetxSwipe")
        self.left.setStyleSheet(STYLE)
        row = QHBoxLayout(self.left)
        row.setContentsMargins(2, 1, 2, 1)
        row.setSpacing(2)
        for text, tip, delta in (
                ("◂", tr("День левой части на шаг ряда темы назад."), -1),
                ("▸", tr("День левой части на шаг ряда темы вперёд."), 1)):
            button = QToolButton(self.left)
            button.setText(text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(
                lambda _=False, d=delta: self.stepped.emit(d))
            row.addWidget(button)
            if delta < 0:
                self.left_day = QLabel(self.left)
                row.addWidget(self.left_day)
        close = QToolButton(self.left)
        close.setText("✕")
        close.setToolTip(tr("Убрать шторку сравнения."))
        close.setAutoRaise(True)
        close.clicked.connect(self.closed.emit)
        row.addWidget(close)
        self.right = QLabel(parent)
        self.right.setObjectName("planetxSwipe")
        self.right.setStyleSheet(STYLE.replace("QFrame", "QLabel")
                                 + " QLabel { padding: 3px 6px; }")
        self._drag = False
        parent.installEventFilter(self)
        self.set_shown(False)

    def set_shown(self, on):
        for widget in (self, self.left, self.right):
            widget.setVisible(bool(on))
        if on:
            self._place()
            for widget in (self, self.left, self.right):
                widget.raise_()

    def set_days(self, left, right):
        """Дни левой и правой части, строки YYYY-MM-DD."""
        self.left_day.setText(left or "…")
        self.right.setText(right or "…")
        self.left.adjustSize()
        self.right.adjustSize()
        self._place()

    def _place(self):
        parent = self.parentWidget()
        width, height = parent.width(), parent.height()
        x = int(round(self.share * width))
        self.setGeometry(x - GRIP // 2, 0, GRIP, height)
        y = height // 2 - RAISE - self.left.height() // 2
        self.left.move(max(0, x - GAP - self.left.width()), y)
        self.right.move(min(width - self.right.width(), x + GAP),
                        y + (self.left.height() - self.right.height()) // 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        mid = self.width() / 2.0
        painter.setPen(QPen(QColor(0, 0, 0, 90), 3.0))
        painter.drawLine(QPointF(mid, 0.0), QPointF(mid, self.height()))
        painter.setPen(QPen(QColor(255, 255, 255), 1.5))
        painter.drawLine(QPointF(mid, 0.0), QPointF(mid, self.height()))
        centre = QPointF(mid, self.height() / 2.0)
        painter.setPen(QPen(QColor(0, 0, 0, 120), 1.0))
        painter.setBrush(QColor(255, 255, 255))
        painter.drawEllipse(centre, KNOB, KNOB)
        painter.setPen(QPen(QColor(40, 40, 40), 1.0))
        painter.drawText(QRectF(centre.x() - KNOB, centre.y() - KNOB,
                                2 * KNOB, 2 * KNOB),
                         int(enum(Qt, "AlignmentFlag", "AlignCenter")), "⇆")

    def _share_at(self, event):
        x = event.position().x() if hasattr(event, "position") \
            else event.pos().x()
        width = max(1, self.parentWidget().width())
        return min(max((self.x() + x) / width, EDGE), 1.0 - EDGE)

    def mousePressEvent(self, event):
        self._drag = True

    def mouseMoveEvent(self, event):
        if not self._drag:
            return
        self.share = self._share_at(event)
        self._place()
        self.moved.emit(self.share)

    def mouseReleaseEvent(self, event):
        self._drag = False

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize") \
                and not self.isHidden():
            self._place()
        return False
