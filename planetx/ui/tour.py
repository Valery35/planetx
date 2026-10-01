# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Показ тура: панель управления внизу вида и проигрыватель.

Тур строится в core/tour.py и проигрывается навигатором как перелёт.
Пауза останавливает навигатор и запоминает время тура. Продолжение
сдвигает начало отсчёта, если камера стоит в позе тура, иначе строит
путь заново от позы камеры - её сдвинули мышью. Кнопки «назад»
и «дальше» строят тур заново от позы камеры, поэтому камера всегда
летит, а не прыгает. Ползунок слева на панели показывает время тура
и перематывает его: пока его тянут, камера стоит в позе тура на этом
времени. Решение автора от 29 сентября 2026 года.
"""
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QEvent, QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QDoubleSpinBox, QFrame, QHBoxLayout,
                                 QLabel, QSlider, QToolButton)

from ..core.tour import PAUSE, Tour, clock
from ..i18n import tr
from ..qt_compat import enum

PAUSE_KEY = "PlanetX/tour_pause"
LOOP_KEY = "PlanetX/tour_loop"
MARGIN = 12  # пикселей от нижнего края вида
STYLE = ("QFrame#planetxTour { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
# Поза камеры сдвинута мышью, если ушла дальше этой доли расстояния.
MOVED = 1e-3
SLIDER_STEPS = 1000  # делений ползунка на весь тур
SLIDER_WIDTH = 220  # логических пикселей


class TourBar(QFrame):
    """Панель тура. Сигналы - по одному на кнопку."""

    back = pyqtSignal()
    toggle = pyqtSignal()
    forward = pyqtSignal()
    close_clicked = pyqtSignal()
    record = pyqtSignal()
    # Ползунок: нажат, сдвинут на долю тура от 0 до 1, отпущен.
    seek_started = pyqtSignal()
    seek = pyqtSignal(float)
    seek_finished = pyqtSignal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("planetxTour")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 3, 6, 3)
        layout.setSpacing(3)
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setFixedWidth(SLIDER_WIDTH)
        self.slider.setToolTip(tr(
            "Сколько тура прошло. Ползунок перематывает тур. Камера сразу "
            "встаёт в эту точку, тур идёт дальше с неё."))
        self.slider.sliderPressed.connect(self.seek_started)
        self.slider.sliderMoved.connect(
            lambda value: self.seek.emit(value / SLIDER_STEPS))
        self.slider.sliderReleased.connect(self.seek_finished)
        # Щелчок по полосе, а не по бегунку, тоже переставляет время.
        self.slider.actionTriggered.connect(self._stepped)
        layout.addWidget(self.slider)
        self.clock = QLabel(self)
        layout.addWidget(self.clock)
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
        # Тур по кругу, для показа на экране без присмотра.
        self.loop = QToolButton(self)
        # Значок из того же набора эмодзи, что ⏮ ⏸ ⏭, синий в Windows.
        self.loop.setText("🔁")
        self.loop.setCheckable(True)
        self.loop.setAutoRaise(True)
        self.loop.setToolTip(tr(
            "Тур по кругу. После последней остановки тур начинается "
            "с первой. Остановить его - пауза или крестик."))
        layout.addWidget(self.loop)
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
        # Справа ⏹ закрывает тур, синим значком, как прочие кнопки.
        close = QToolButton(self)
        close.setText("⏹")
        close.setToolTip(tr("Закончить тур"))
        close.setAutoRaise(True)
        close.clicked.connect(self.close_clicked)
        layout.addWidget(close)
        parent.installEventFilter(self)
        self.hide()

    def _stepped(self, action):
        """Шаг ползунка щелчком по полосе или клавишами."""
        if not self.slider.isSliderDown():
            self.seek_started.emit()
            self.seek.emit(self.slider.sliderPosition() / SLIDER_STEPS)
            self.seek_finished.emit()

    def set_time(self, t, duration):
        """Ползунок и часы: время тура t из duration секунд. Пока
        ползунок тянут, его положение не трогается."""
        if not self.slider.isSliderDown():
            self.slider.blockSignals(True)
            self.slider.setValue(int(round(
                SLIDER_STEPS * t / duration)) if duration > 0 else 0)
            self.slider.blockSignals(False)
        self.clock.setText("%s / %s" % (clock(t), clock(duration)))

    def set_state(self, playing, index, count, name):
        # ▶ с селектором U+FE0F рисуется синим значком, как ⏮ ⏸ ⏭ 🔁.
        self.play.setText("⏸" if playing else "▶️")
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
    # Тур пришёл к новой остановке, core.tour.Stop.
    stop_reached = pyqtSignal(object)

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
        self.bar.loop.setChecked(QgsSettings().value(LOOP_KEY, False,
                                                     type=bool))
        self.bar.loop.toggled.connect(
            lambda on: QgsSettings().setValue(LOOP_KEY, bool(on)))
        # Сколько раз тур начался заново по кругу, для проверок.
        self.laps = 0
        self.bar.back.connect(lambda: self.play_from(self.index - 1))
        self.bar.forward.connect(lambda: self.play_from(self.index + 1))
        self.bar.toggle.connect(self.toggle)
        self.bar.close_clicked.connect(self.stop)
        self.bar.seek_started.connect(self._seek_started)
        self.bar.seek.connect(self.seek)
        self.bar.seek_finished.connect(self._seek_finished)
        self._resume = False  # тур шёл, когда взяли ползунок
        self.stops = []
        self.tour = None
        self.offset = 0  # номер первой остановки нынешнего тура
        self.t = 0.0  # время тура на последнем кадре
        self.playing = False
        self._reached = None  # номер остановки, о которой сказано
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
        self._reached = None
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
        if not self._moved():
            # Камера в позе тура: время тура идёт дальше.
            self._resume_at(self.t)
        else:
            self.play_from(self.index)

    def _resume_at(self, t):
        self.nav.start_flight(self.tour, time.monotonic() - t)
        self.playing = True
        self._show()
        self.view.update()

    def _seek_started(self):
        if self.tour is None:
            return
        self._resume = self.playing
        if self.playing:
            self.nav.stop()
            self.playing = False

    def seek(self, share):
        """Перемотать тур на долю share от 0 до 1: камера встаёт в позу
        тура на этом времени."""
        if self.tour is None:
            return
        self.t = min(max(share, 0.0), 1.0) * self.tour.duration
        self.nav.show(self.tour.pose_at(self.t))
        self._show()
        self.view.update()

    def _seek_finished(self):
        if self.tour is None:
            return
        if self._resume and self.t < self.tour.duration:
            self._resume_at(self.t)
        self._resume = False

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
                if self.bar.loop.isChecked() and self.nav.grab is None:
                    # Тур дошёл до конца сам: по кругу с первой остановки.
                    self.laps += 1
                    self.play_from(0)
                    return
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
        if stop is not None and self.index != self._reached:
            self._reached = self.index
            self.stop_reached.emit(stop)
        self.bar.set_state(self.playing, self.index, len(self.stops),
                           stop.name if stop else "")
        if self.tour is not None:
            self.bar.set_time(min(self.t, self.tour.duration),
                              self.tour.duration)
