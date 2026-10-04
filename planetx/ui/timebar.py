# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шкала времени меток вверху вида, как шкала времени Google Earth.

Шкала охватывает время видимых «Моих меток» (core/when.py) от самого
раннего до самого позднего. Она не висит на виде всё время. Её
открывает кнопка на панели значков, а сама шкала открывается при
перелёте к метке или виду с датой. Закрытая шкала метки не скрывает,
решение автора от 30 сентября 2026 года. Два бегунка
задают промежуток, метки вне него скрыты, метки без времени видны
всегда. Бегунки тянутся по одному или вместе за середину промежутка,
щелчок по полосе переносит промежуток туда. Кнопка проигрывания
двигает промежуток вдоль шкалы. Шкала своя, на «Временный контроллер»
QGIS не опирается, решение автора от 30 сентября 2026 года.

Шкала - одно время вида, решение автора от 5 октября 2026 года.
Покрытия - темы NASA - берут момент, правый бегунок, события - метки
и землетрясения - промежуток. Без событий шкала - один бегунок
(point). Шаги ◂ ▸ двигают момент по дням ряда покрытия (stepper),
показ при покрытии идёт по этим дням и ждёт загрузки дня (ready).
"""
import math
import time

from qgis.PyQt.QtCore import QEvent, QRectF, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen
from qgis.PyQt.QtWidgets import (QComboBox, QFrame, QHBoxLayout, QLabel,
                                 QToolButton, QWidget)

from ..core import when
from ..i18n import tr
from ..qt_compat import enum

MARGIN = 12  # пикселей от верхнего края вида
STYLE = ("QFrame#planetxTime { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
TRACK_WIDTH = 320  # логических пикселей
HANDLE = 6.0  # полуширина бегунка
PLAY_PERIOD = 40  # мс между шагами проигрывания
STEP_PERIOD = 900  # мс на шаг показа по дням ряда покрытия
# Проигрывание проходит шкалу за столько секунд при скорости 1.
PLAY_SECONDS = 20.0
SPEEDS = (0.25, 0.5, 1.0, 2.0, 4.0)
SELECTION = QColor(255, 214, 0, 150)
# Шкала длиннее - у дат до нашей эры подписан только год.
LONG_SPAN = 3 * 366 * 86400


def time_text(seconds, span):
    """Дата для подписи: время суток показывается, если промежуток
    шкалы короче двух суток."""
    if not math.isfinite(seconds):
        return "…"
    if seconds >= 0.0:
        fmt = "%Y-%m-%d %H:%M" if span < 2 * 86400 else "%Y-%m-%d"
        return time.strftime(fmt, time.localtime(seconds))
    # До 1970 года - дата UTC своим счётом: time.localtime на Windows
    # таких моментов не берёт. Годы до нашей эры - словами.
    year, month, day = when.civil(seconds)[:3]
    if year > 0:
        return "%04d-%02d-%02d" % (year, month, day)
    if span > LONG_SPAN:
        return tr("{date} до н. э.", date=str(1 - year))
    return tr("{date} до н. э.",
              date="%d-%02d-%02d" % (1 - year, month, day))


class RangeTrack(QWidget):
    """Полоса шкалы с двумя бегунками. Сигнал moved - новый промежуток
    (от, до) в секундах. point - один бегунок: промежуток нулевой
    ширины, щелчок и протяжка ставят момент."""

    moved = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.extent = (0.0, 1.0)
        self.lo, self.hi = 0.0, 1.0
        self.drag = None  # "lo", "hi", "point" или ("body", сдвиг)
        self.point = False
        self.setFixedSize(TRACK_WIDTH, 22)
        self.setMouseTracking(True)

    def set_extent(self, lo, hi):
        self.extent = (lo, hi if hi > lo else lo + 1.0)
        self.update()

    def set_range(self, lo, hi):
        a, b = self.extent
        self.lo = min(max(lo, a), b)
        self.hi = min(max(hi, self.lo), b)
        self.update()

    def _x(self, t):
        a, b = self.extent
        return HANDLE + (t - a) / (b - a) * (self.width() - 2 * HANDLE)

    def _t(self, x):
        a, b = self.extent
        share = (x - HANDLE) / max(1.0, self.width() - 2 * HANDLE)
        return a + min(max(share, 0.0), 1.0) * (b - a)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        mid = self.height() / 2.0
        painter.setPen(QPen(QColor(120, 120, 120), 2.0))
        painter.drawLine(int(HANDLE), int(mid),
                         int(self.width() - HANDLE), int(mid))
        x0, x1 = self._x(self.lo), self._x(self.hi)
        if not self.point:
            painter.fillRect(QRectF(x0, mid - 4.0, max(x1 - x0, 1.0), 8.0),
                             SELECTION)
        painter.setPen(QPen(QColor(60, 60, 60), 1.0))
        painter.setBrush(SELECTION if self.point else QColor(255, 255, 255))
        for x in ((x1,) if self.point else (x0, x1)):
            painter.drawRoundedRect(QRectF(x - HANDLE / 2.0, mid - 8.0,
                                           HANDLE, 16.0), 2.0, 2.0)

    def mousePressEvent(self, event):
        x = event.position().x() if hasattr(event, "position") \
            else event.pos().x()
        if self.point:
            t = self._t(x)
            self._set(t, t)
            self.drag = "point"
            return
        x0, x1 = self._x(self.lo), self._x(self.hi)
        if abs(x - x1) <= HANDLE and (abs(x - x1) <= abs(x - x0)
                                      or x > x1):
            self.drag = "hi"
        elif abs(x - x0) <= HANDLE:
            self.drag = "lo"
        elif x0 < x < x1:
            self.drag = ("body", self._t(x) - self.lo)
        else:
            # Щелчок по полосе: промежуток той же ширины встаёт серединой
            # в точку щелчка.
            width = self.hi - self.lo
            centre = self._t(x)
            self._set(centre - width / 2.0, centre + width / 2.0)
            self.drag = ("body", width / 2.0)

    def mouseMoveEvent(self, event):
        if self.drag is None:
            return
        x = event.position().x() if hasattr(event, "position") \
            else event.pos().x()
        t = self._t(x)
        if self.drag == "point":
            self._set(t, t)
        elif self.drag == "lo":
            self._set(min(t, self.hi), self.hi)
        elif self.drag == "hi":
            self._set(self.lo, max(t, self.lo))
        else:
            width = self.hi - self.lo
            start = t - self.drag[1]
            self._set(start, start + width)

    def mouseReleaseEvent(self, event):
        self.drag = None

    def _set(self, lo, hi):
        """Промежуток в пределах шкалы. Сдвиг целиком держит ширину."""
        a, b = self.extent
        width = hi - lo
        if lo < a:
            lo, hi = a, a + width
        if hi > b:
            lo, hi = b - width, b
        self.lo, self.hi = max(lo, a), min(hi, b)
        self.update()
        self.moved.emit(self.lo, self.hi)


class TimeBar(QFrame):
    """Панель шкалы времени. Сигнал range_changed - промежуток (от, до)
    в секундах UTC."""

    range_changed = pyqtSignal(float, float)
    closed = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("planetxTime")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 6, 3)
        layout.setSpacing(4)
        # Кнопки в том же порядке и виде, что на панели тура: синие
        # значки ⏮ ▶ ⏭ 🔁, ⏹ закрывает шкалу. Просьба автора
        # от 1 октября 2026 года.
        self.track = RangeTrack(self)
        self._range_tip = tr(
            "Промежуток времени меток и землетрясений. Бегунки тянутся "
            "по одному или вместе за середину, щелчок по полосе переносит "
            "промежуток. Тема NASA показана на день правого бегунка. "
            "Метки вне промежутка скрыты, метки без времени видны "
            "всегда.")
        self._point_tip = tr(
            "Момент времени темы NASA. Щелчок по полосе или протяжка "
            "бегунка ставят день, кнопки ◂ и ▸ сдвигают его на шаг ряда "
            "темы.")
        self.track.setToolTip(self._range_tip)
        self.track.moved.connect(self._moved)
        layout.addWidget(self.track)
        self.label = QLabel(self)
        layout.addWidget(self.label)
        # Шаги по дням ряда покрытия: stepper(момент, ±1) - момент
        # соседнего дня или None. Ставит окно, без него кнопок нет.
        self.stepper = None
        self.ready = None
        self.steps = []
        for text, tip, delta in (
                ("◂", tr("На шаг ряда темы назад."), -1),
                ("▸", tr("На шаг ряда темы вперёд."), 1)):
            button = QToolButton(self)
            button.setText(text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(lambda _=False, d=delta: self.step(d))
            button.hide()
            layout.addWidget(button)
            self.steps.append(button)
        buttons = []
        for text, tip, slot in (
                ("⏮", tr("К началу шкалы"), self.to_start),
                ("▶\ufe0f", tr(
                    "Проиграть: промежуток идёт вдоль шкалы, метки "
                    "появляются и скрываются по своему времени."),
                 self.toggle),
                ("⏭", tr("К концу шкалы"), self.to_end)):
            button = QToolButton(self)
            button.setText(text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(slot)
            layout.addWidget(button)
            buttons.append(button)
        self.play = buttons[1]
        self.loop = QToolButton(self)
        self.loop.setText("🔁")
        self.loop.setCheckable(True)
        self.loop.setAutoRaise(True)
        self.loop.setToolTip(tr(
            "Проигрывание по кругу. Дойдя до конца шкалы, промежуток "
            "начинает с начала."))
        layout.addWidget(self.loop)
        self.speed = QComboBox(self)
        for value in SPEEDS:
            self.speed.addItem("×{:g}".format(value), value)
        self.speed.setCurrentIndex(SPEEDS.index(1.0))
        self.speed.setToolTip(tr(
            "Скорость проигрывания. При ×1 промежуток проходит шкалу "
            "за 20 секунд."))
        layout.addWidget(self.speed)
        close = QToolButton(self)
        close.setText("⏹")
        close.setToolTip(tr("Закрыть шкалу времени. Закрытая шкала метки "
                            "не скрывает."))
        close.setAutoRaise(True)
        close.clicked.connect(self._close_clicked)
        layout.addWidget(close)
        self.timer = QTimer(self)
        self.timer.setInterval(PLAY_PERIOD)
        self.timer.timeout.connect(self._step)
        self._last = None
        # Место панели: функция без аргументов, отдаёт левый верхний
        # угол. Ставит окно - под панелью значков.
        self.anchor = None
        self.known = False  # охват задан, у видимых меток есть время
        parent.installEventFilter(self)
        self.hide()

    def shown(self):
        return not self.isHidden()

    def extent(self):
        return self.track.extent

    def range(self):
        return self.track.lo, self.track.hi

    def set_extent(self, extent):
        """Охват шкалы по временам меток или None - шкалы нет.
        Промежуток, которого не было, - вся шкала."""
        if extent is None:
            self.known = False
            self.close_bar()
            return
        fresh = not self.known
        self.known = True
        old = self.track.extent
        self.track.set_extent(*extent)
        if self.track.point:
            # Момент остаётся на месте, в пределах нового охвата.
            self.track.set_range(self.track.hi, self.track.hi)
        elif fresh or old != self.track.extent:
            self.track.set_range(*self.track.extent)
        self._label()
        if self.shown():
            self.adjustSize()
            self._place()

    def open_bar(self):
        """Показать шкалу. Без охвата показывать нечего."""
        if not self.known:
            return
        self.show()
        self.raise_()
        self.adjustSize()
        self._place()

    def close_bar(self):
        self.stop()
        self.hide()

    def set_point(self, on, at=None):
        """Один бегунок в момент at или на месте правого. Выход из
        режима - промежуток во всю шкалу с правым бегунком на месте."""
        on = bool(on)
        if on == self.track.point and at is None:
            return
        self.track.point = on
        self.track.setToolTip(self._point_tip if on else self._range_tip)
        moment = self.track.hi if at is None else at
        if on:
            self.track.set_range(moment, moment)
        else:
            self.track.set_range(self.track.extent[0], moment)
        self._moved(self.track.lo, self.track.hi)

    def set_stepper(self, stepper):
        """Шаги по дням ряда покрытия, None - кнопок нет."""
        self.stepper = stepper
        for button in self.steps:
            button.setVisible(stepper is not None)
        self.adjustSize()

    def step(self, delta):
        """Правый бегунок - на соседний день ряда покрытия, ширина
        промежутка та же. Возвращает, сдвинулся ли."""
        if self.stepper is None:
            return False
        moment = self.stepper(self.track.hi, delta)
        if moment is None:
            return False
        width = self.track.hi - self.track.lo
        self.track.set_range(moment - width, moment)
        self._moved(self.track.lo, self.track.hi)
        return True

    def set_range(self, lo, hi):
        """Промежуток снаружи: вид метки с датой, остановка тура.
        Бесконечный край - край шкалы."""
        a, b = self.track.extent
        lo = a if not math.isfinite(lo) else lo
        hi = b if not math.isfinite(hi) else hi
        if self.track.point:
            lo = hi
        self.track.set_range(lo, hi)
        self._moved(self.track.lo, self.track.hi)

    def _moved(self, lo, hi):
        self._label()
        self.range_changed.emit(lo, hi)

    def _label(self):
        a, b = self.track.extent
        lo, hi = self.track.lo, self.track.hi
        span = b - a
        if hi - lo < 1.0:
            self.label.setText(time_text(lo, span))
        else:
            self.label.setText("{} - {}".format(time_text(lo, span),
                                                time_text(hi, span)))

    def _close_clicked(self):
        self.close_bar()
        self.closed.emit()

    def to_start(self):
        """Промежуток той же ширины - в начало шкалы."""
        a, _ = self.track.extent
        width = self.track.hi - self.track.lo
        self.track.set_range(a, a + width)
        self._moved(self.track.lo, self.track.hi)

    def to_end(self):
        """Промежуток той же ширины - в конец шкалы."""
        self.stop()
        _, b = self.track.extent
        width = self.track.hi - self.track.lo
        self.track.set_range(b - width, b)
        self._moved(self.track.lo, self.track.hi)

    def toggle(self):
        if self.timer.isActive():
            self.stop()
            return
        a, b = self.track.extent
        if self.track.hi >= b:
            # Проигрывание с начала шкалы, ширина промежутка та же.
            width = self.track.hi - self.track.lo
            self.track.set_range(a, a + width)
        self._last = time.monotonic()
        # При покрытии показ идёт по дням его ряда, с ожиданием дня.
        self.timer.setInterval(STEP_PERIOD if self.stepper is not None
                               else PLAY_PERIOD)
        self.timer.start()
        self.play.setText("⏸")

    def stop(self):
        self.timer.stop()
        self.play.setText("▶\ufe0f")

    def _step(self):
        if self.stepper is not None:
            if self.ready is not None and not self.ready():
                return
            if not self.step(1):
                if self.loop.isChecked():
                    self.to_start()
                else:
                    self.stop()
            return
        now = time.monotonic()
        dt = now - (self._last or now)
        self._last = now
        a, b = self.track.extent
        shift = (b - a) * dt * self.speed.currentData() / PLAY_SECONDS
        lo, hi = self.track.lo + shift, self.track.hi + shift
        if hi >= b:
            if self.loop.isChecked():
                # По кругу: промежуток той же ширины снова с начала.
                width = hi - lo
                lo, hi = a, a + width
            else:
                lo, hi = lo - (hi - b), b
                self.stop()
        self.track.set_range(lo, hi)
        self._moved(self.track.lo, self.track.hi)

    def _place(self):
        if self.anchor is not None:
            self.move(*self.anchor())
            return
        parent = self.parentWidget()
        self.move(max(0, (parent.width() - self.width()) // 2), MARGIN)

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize"):
            self._place()
        return False
