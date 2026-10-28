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
from qgis.PyQt.QtWidgets import QMenu, QWidget

from ..i18n import tr
from ..qt_compat import enum
from .style import ACCENT, PLATE

SIZE = 26  # сторона значка, логических пикселей
TICK = 40  # мс между кадрами вращения
TURN = 360.0  # градусов дуги в секунду
ARC = 270  # длина дуги, градусов
SHOW_DELAY = 0.4  # с загрузки до появления значка
# Плашка - общий вид элементов поверх глобуса, ui/style.py.
BACKGROUND = PLATE
LOADING = ACCENT
STALLED = QColor(230, 130, 20)


BUSY_SIZE = 20  # сторона значка ожидания у строки поиска


class BusySpinner(QWidget):
    """Значок ожидания у строки «Поиск»: вращающаяся дуга, пока ждётся
    ответ модели помощника или службы поиска мест. Просьба автора от
    4 октября 2026 года. Вне ожидания значок спрятан и места в строке
    не занимает."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(BUSY_SIZE, BUSY_SIZE)
        self.angle = 0.0
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._turn)
        self.hide()

    def set_busy(self, on, tip=""):
        """Показать или спрятать значок, tip - что именно ждётся."""
        self.setToolTip(tip)
        if on:
            if not self.timer.isActive():
                self.timer.start()
            self.show()
        else:
            self.timer.stop()
            self.hide()

    def busy(self):
        return self.timer.isActive()

    def _turn(self):
        self.angle = (self.angle + TURN * TICK / 1000.0) % 360.0
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        pen = QPen(LOADING, 2.5)
        pen.setCapStyle(enum(Qt, "PenCapStyle", "RoundCap"))
        painter.setPen(pen)
        painter.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
        painter.drawArc(QRectF(3.0, 3.0, BUSY_SIZE - 6.0, BUSY_SIZE - 6.0),
                        int(-self.angle * 16), ARC * 16)
        painter.end()


class LoadSpinner(QWidget):
    """Вращающаяся дуга, пока идёт загрузка или долгий расчёт
    инструмента. Расчёты - jobs: ключ - (что идёт, остановка или None).
    Щелчок по значку с расчётами даёт меню «Остановить», просьба автора
    от 28 октября 2026 года. Загрузку тайлов вид ведёт сам, её значок
    не останавливает."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(SIZE, SIZE)
        self.angle = 0.0
        self.stalled = False
        self.since = None  # момент начала загрузки
        self.missing = 0
        self.stall = 0.0
        self.jobs = {}
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._turn)
        self.hide()

    def set_state(self, missing, stalled):
        """Сколько ждёт кадр и сколько секунд стоит загрузка."""
        self.missing = missing
        self.stall = stalled
        self._refresh()

    def set_job(self, key, text=None, cancel=None):
        """Расчёт key идёт - text, что именно, cancel() останавливает
        его. text None - расчёт кончился."""
        if text is None:
            self.jobs.pop(key, None)
        else:
            self.jobs[key] = (text, cancel)
        self._refresh()

    def _refresh(self):
        if self.missing <= 0 and not self.jobs:
            self.since = None
            self.timer.stop()
            self.hide()
            return
        if self.since is None:
            self.since = time.monotonic()
        self.stalled = self.stall > 0 and not self.jobs
        lines = [text for text, _ in self.jobs.values()]
        if self.missing > 0:
            lines.append(
                tr("Загрузка стоит {seconds} с", seconds=int(self.stall))
                if self.stall > 0 else
                tr("Идёт загрузка: {count}", count=self.missing))
        if any(cancel for _, cancel in self.jobs.values()):
            lines.append(tr("Щелчок - остановить расчёт."))
        self.setToolTip("\n".join(lines))
        self.setCursor(enum(Qt, "CursorShape", "PointingHandCursor")
                       if self.jobs else
                       enum(Qt, "CursorShape", "ArrowCursor"))
        if not self.timer.isActive():
            self.timer.start()
        self.update()

    def mousePressEvent(self, event):
        stops = [(text, cancel) for text, cancel in self.jobs.values()
                 if cancel is not None]
        if not stops:
            return
        menu = QMenu(self)
        for text, cancel in stops:
            menu.addAction(tr("Остановить «{what}»", what=text)) \
                .triggered.connect(lambda _=False, c=cancel: c())
        if len(stops) > 1:
            menu.addSeparator()
            menu.addAction(tr("Остановить всё")).triggered.connect(
                lambda _=False: [c() for _, c in stops])
        menu.exec(self.mapToGlobal(self.rect().bottomLeft()))

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
