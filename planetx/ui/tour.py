# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Показ тура: панель управления внизу вида и проигрыватель.

Тур строится в core/tour.py и проигрывается навигатором как перелёт.
Пауза останавливает навигатор и запоминает время тура. Продолжение
на остановке сдвигает начало отсчёта, в полёте - строит путь заново
от позы камеры, если её сдвинули мышью. Кнопки «назад» и «дальше»
строят тур заново от позы камеры, поэтому камера всегда летит,
а не прыгает.
"""
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QEvent, QObject, pyqtSignal
from qgis.PyQt.QtWidgets import (QDoubleSpinBox, QFrame, QHBoxLayout,
                                 QLabel, QToolButton)

from ..core.tour import PAUSE, Tour
from ..i18n import tr
from ..qt_compat import enum

PAUSE_KEY = "PlanetX/tour_pause"
MARGIN = 12  # пикселей от нижнего края вида
STYLE = ("QFrame#planetxTour { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
# Поза камеры сдвинута мышью, если ушла дальше этой доли расстояния.
MOVED = 1e-3


class TourBar(QFrame):
    """Панель тура. Сигналы - по одному на кнопку."""

    back = pyqtSignal()
    toggle = pyqtSignal()
    forward = pyqtSignal()
    close_clicked = pyqtSignal()
    record = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("planetxTour")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 6, 3)
        layout.setSpacing(3)
        buttons = []
        for text, tip, signal in (
                ("⏮", tr("Предыдущая остановка"), self.back),
                ("⏸", tr("Пауза"), self.toggle),
                ("⏭", tr("Следующая остановка"), self.forward)):
            button = QToolButton(self)
            button.setText(text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(signal)
            layout.addWidget(button)
            buttons.append(button)
        self.play = buttons[1]
        self.info = QLabel(self)
        layout.addWidget(self.info)
        self.pause = QDoubleSpinBox(self)
        self.pause.setRange(0.0, 60.0)
        self.pause.setDecimals(1)
        self.pause.setSuffix(tr(" с"))
        self.pause.setToolTip(tr(
            "Сколько секунд камера стоит на каждой остановке. Новая пауза "
            "действует с перехода кнопками или с нового запуска тура."))
        layout.addWidget(QLabel(tr("Пауза"), self))
        layout.addWidget(self.pause)
        self.rec = QToolButton(self)
        self.rec.setText("⏺")
        self.rec.setToolTip(tr(
            "Записать тур кадрами PNG, 25 кадров в секунду тура, в размере "
            "окна. Каждый кадр ждёт загрузки тайлов, поэтому запись идёт "
            "дольше тура. Кадры с теми же номерами в папке заменяются."))
        self.rec.setAutoRaise(True)
        self.rec.clicked.connect(self.record)
        layout.addWidget(self.rec)
        # Крестик справа, как у Google Earth, закрывает тур.
        close = QToolButton(self)
        close.setText("✕")
        close.setToolTip(tr("Закончить тур"))
        close.setAutoRaise(True)
        close.clicked.connect(self.close_clicked)
        layout.addWidget(close)
        parent.installEventFilter(self)
        self.hide()

    def set_state(self, playing, index, count, name):
        self.play.setText("⏸" if playing else "▶")
        self.play.setToolTip(tr("Пауза") if playing else tr("Продолжить"))
        self.info.setText(tr("Остановка {n} из {count}: {name}",
                             n=index + 1, count=count,
                             name=name or tr("Без названия")))
        self.adjustSize()
        self._place()

    def _place(self):
        parent = self.parentWidget()
        self.move(max(0, (parent.width() - self.width()) // 2),
                  parent.height() - self.height() - MARGIN)

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize"):
            self._place()
        return False


class TourPlayer(QObject):
    """Проигрыватель тура по остановкам core.tour.Stop.

    stops - функция без аргументов, отдаёт остановки на момент запуска.
    """

    message = pyqtSignal(str)

    def __init__(self, view, stops, parent=None):
        super().__init__(parent)
        self.view = view
        self.nav = view.navigator
        self.stops_source = stops
        self.bar = TourBar(view)
        self.bar.pause.setValue(QgsSettings().value(PAUSE_KEY, PAUSE,
                                                    type=float))
        self.bar.pause.valueChanged.connect(
            lambda v: QgsSettings().setValue(PAUSE_KEY, float(v)))
        self.bar.back.connect(lambda: self.play_from(self.index - 1))
        self.bar.forward.connect(lambda: self.play_from(self.index + 1))
        self.bar.toggle.connect(self.toggle)
        self.bar.close_clicked.connect(self.stop)
        self.stops = []
        self.tour = None
        self.offset = 0  # номер первой остановки нынешнего тура
        self.t = 0.0  # время тура на последнем кадре
        self.playing = False
        view.changed.connect(self.tick)

    @property
    def index(self):
        """Номер остановки в общем списке."""
        if self.tour is None:
            return 0
        return self.offset + max(0, self.tour.index_at(self.t))

    def start(self, stops=None):
        """Тур с первой остановки. Без stops - остановки из источника.
        Остановок нет - сообщение."""
        self.stops = list(self.stops_source() if stops is None else stops)
        if not self.stops:
            self.message.emit(tr(
                "В туре нет остановок. Отметьте флажком метки в «Моих "
                "метках»."))
            return
        self.bar.show()
        self.play_from(0)

    def play_from(self, k):
        """Лететь от позы камеры к остановке k и дальше по списку."""
        if not self.stops:
            return
        k = min(max(k, 0), len(self.stops) - 1)
        self.offset = k
        self.tour = Tour(self.nav.pose, self.stops[k:],
                         self.bar.pause.value(), self.view.camera.fov_y)
        self.t = 0.0
        self.nav.start_flight(self.tour, time.monotonic())
        self.playing = True
        self._show()
        self.view.update()

    def toggle(self):
        if self.tour is None:
            return
        if self.playing:
            self.nav.stop()
            self.playing = False
            self._show()
            return
        if self.t >= self.tour.duration:
            self.play_from(0)  # тур кончился - заново
            return
        if self.tour.arrived(self.t) and not self._moved():
            # На остановке камера на месте: время тура идёт дальше.
            self.nav.start_flight(self.tour, time.monotonic() - self.t)
            self.playing = True
            self._show()
            self.view.update()
        else:
            self.play_from(self.index)

    def _moved(self):
        pose = self.nav.pose
        want = self.tour.pose_at(self.t)
        return (abs(pose.distance - want.distance) > MOVED * want.distance
                or abs(pose.lat - want.lat) > MOVED
                or abs(pose.lon - want.lon) > MOVED)

    def stop(self):
        if self.playing:
            self.nav.stop()
        self.playing = False
        self.tour = None
        self.bar.hide()

    def tick(self):
        """Кадр вида: время тура, конец тура или перехват мышью."""
        if self.tour is None or not self.playing:
            return
        flight = self.nav.flight
        if flight is not None and flight[1] is self.tour:
            self.t = time.monotonic() - flight[0]
        else:
            # Тур кончился или камеру взяли мышью: панель встаёт на паузу.
            self.playing = False
            if self.t >= self.tour.arrivals[-1]:
                self.t = self.tour.duration
        self._show()

    def pause_for_record(self):
        """Остановить показ перед записью, панель остаётся."""
        if self.playing:
            self.nav.stop()
        self.playing = False

    def show_recording(self, n, count):
        """Панель во время записи: номер кадра."""
        self.bar.info.setText(tr("Запись: кадр {n} из {count}", n=n,
                                 count=count))
        self.bar.adjustSize()
        self.bar._place()

    def _show(self):
        stop = self.stops[self.index] if self.stops else None
        self.bar.set_state(self.playing, self.index, len(self.stops),
                           stop.name if stop else "")
