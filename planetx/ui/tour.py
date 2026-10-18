# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Показ тура: панель управления под шкалой времени и проигрыватель.

Тур строится в core/tour.py и проигрывается навигатором как перелёт.
Пауза останавливает навигатор и запоминает время тура. Продолжение
сдвигает начало отсчёта, если камера стоит в позе тура, иначе строит
путь заново от позы камеры - её сдвинули мышью. Кнопки «назад»
и «дальше» строят тур заново от позы камеры, поэтому камера всегда
летит, а не прыгает. Ползунок слева на панели показывает время тура
и перематывает его: пока его тянут, камера стоит в позе тура на этом
времени. Решение автора от 29 сентября 2026 года.

С 17 октября 2026 года, просьба автора, во время показа клавиша
«вправо» ведёт к следующей остановке, «влево» - к предыдущей, пробел
ставит на паузу и продолжает, Esc заканчивает тур. Камеру, взятую
мышью на паузе остановки, тур не останавливает. Пока идёт пауза
остановки, вид вертят свободно, после неё тур летит от этой позы
к следующей остановке. Взятая мышью в перелёте камера ставит тур на
паузу, как прежде.
"""
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QEvent, QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QDoubleSpinBox, QFrame, QHBoxLayout,
                                 QLabel, QSlider, QToolButton, QVBoxLayout)

from ..core.tour import PAUSE, Tour, clock
from ..i18n import tr
from ..qt_compat import enum
from .style import plate, set_glyph
from . import stopcaption
from .stopcaption import StopCaption, plain

PAUSE_KEY = "PlanetX/tour_pause"
LOOP_KEY = "PlanetX/tour_loop"
MARGIN = 12  # пикселей от нижнего края вида, если шкалы времени нет
# Плашка и значки - общий вид элементов поверх глобуса, ui/style.py.
# Поза камеры сдвинута мышью, если ушла дальше этой доли расстояния.
MOVED = 1e-3
SLIDER_STEPS = 1000  # делений ползунка на весь тур
SLIDER_WIDTH = 220  # логических пикселей
CAPTION_WIDTH = 480  # строка описания остановки, не уже, пикселей
# Свободная камера на паузе остановки: шаг проверки конца паузы, мс.
FREE_TICK = 200
KEY_PRESS = enum(QEvent, "Type", "KeyPress")
# Клавиши с этими модификаторами остаются виду - его стрелки двигают
# и поворачивают камеру.
HELD = (enum(Qt, "KeyboardModifier", "ControlModifier"),
        enum(Qt, "KeyboardModifier", "ShiftModifier"),
        enum(Qt, "KeyboardModifier", "AltModifier"))


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
        plate(self, "planetxTour")
        column = QVBoxLayout(self)
        column.setContentsMargins(4, 3, 6, 3)
        column.setSpacing(2)
        layout = QHBoxLayout()
        layout.setSpacing(3)
        column.addLayout(layout)
        # Описание остановки под кнопками: тур объясняет, что на виде.
        self.caption = QLabel(self)
        self.caption.setWordWrap(True)
        self.caption.hide()
        column.addWidget(self.caption)
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
            set_glyph(button, text)
            button.setToolTip(tip)
            button.setAutoRaise(True)
            button.clicked.connect(signal)
            layout.addWidget(button)
            buttons.append(button)
        self.play = buttons[1]
        # Тур по кругу, для показа на экране без присмотра.
        self.loop = QToolButton(self)
        set_glyph(self.loop, "🔁")
        self.loop.setCheckable(True)
        self.loop.setAutoRaise(True)
        self.loop.setToolTip(tr(
            "Тур по кругу. После последней остановки тур начинается "
            "с первой. Остановить его - пауза или крестик."))
        layout.addWidget(self.loop)
        # Подписи остановок крупно на кадре (ui/stopcaption.py).
        self.captions = QToolButton(self)
        set_glyph(self.captions, "🔤")
        self.captions.setCheckable(True)
        self.captions.setAutoRaise(True)
        self.captions.setToolTip(tr(
            "Подписи остановок на кадре. На остановке внизу кадра "
            "крупно стоят название и описание метки, в перелёте подписи "
            "нет. Подписи попадают и в запись тура."))
        layout.addWidget(self.captions)
        self.info = QLabel(self)
        layout.addWidget(self.info)
        # Под шкалой времени панель растягивается на её ширину, лишнее
        # место - между названием остановки и паузой.
        layout.addStretch(1)
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
        set_glyph(self.rec, "⏺")
        self.rec.setToolTip(tr(
            "Записать тур, 25 кадров в секунду тура: сразу видео MP4 "
            "в размере окна или кадры PNG в папку в выбранном размере. "
            "Каждый кадр ждёт загрузки тайлов, поэтому запись идёт "
            "дольше тура."))
        self.rec.setAutoRaise(True)
        self.rec.clicked.connect(self.record)
        layout.addWidget(self.rec)
        # Справа ⏹ закрывает тур, значком набора, как прочие кнопки.
        close = QToolButton(self)
        set_glyph(close, "⏹")
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

    def set_state(self, playing, index, count, name, description=""):
        # ▶ с селектором U+FE0F рисуется синим значком, как ⏮ ⏸ ⏭ 🔁.
        set_glyph(self.play, "⏸" if playing else "▶️")
        self.play.setToolTip(tr("Пауза") if playing else tr("Продолжить"))
        self.info.setText(tr("Остановка {n} из {count}: {name}",
                             n=index + 1, count=count,
                             name=name or tr("Без названия")))
        # С подписями на кадре строка описания под кнопками не нужна.
        if self.captions.isChecked():
            description = ""
        self.caption.setText(description)
        self.caption.setVisible(bool(description))
        if description:
            # Строка описания не шире кнопок с ползунком, но не уже
            # CAPTION_WIDTH.
            self.caption.setFixedWidth(max(CAPTION_WIDTH, self.layout()
                                           .itemAt(0).sizeHint().width()))
        self.adjustSize()
        self._place()

    def attach(self, timebar):
        """Панель тура - строкой под шкалой времени, одной панелью
        с ней, а без шкалы - на её месте. Решение автора от 7 октября
        2026 года - две панели мультипликации, вверху и внизу вида,
        лишние."""
        self.follow = timebar
        timebar.installEventFilter(self)

    def _place(self):
        follow = getattr(self, "follow", None)
        if follow is not None and follow.anchor is not None:
            x, y = follow.anchor()
            if not follow.isHidden():
                # Общая граница: панель тура заходит под шкалу на пиксель.
                x, y = follow.x(), follow.y() + follow.height() - 1
                self.setMinimumWidth(follow.width())
            else:
                self.setMinimumWidth(0)
            self.adjustSize()
            self.move(x, y)
            self.raise_()
            return
        parent = self.parentWidget()
        self.move(max(0, (parent.width() - self.width()) // 2),
                  parent.height() - self.height() - MARGIN)

    def eventFilter(self, watched, event):
        kinds = [enum(QEvent, "Type", "Resize")]
        if watched is getattr(self, "follow", None):
            kinds += [enum(QEvent, "Type", name)
                      for name in ("Show", "Hide", "Move")]
        if event.type() in kinds and not self.isHidden():
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
        self.stop_caption = StopCaption(view)
        self.bar.captions.setChecked(QgsSettings().value(
            stopcaption.KEY, True, type=bool))
        self.bar.captions.toggled.connect(self._captions_toggled)
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
        # Часы тура: время тура t - monotonic() - _start.
        self._start = 0.0
        # Свободная камера на паузе остановки: номер остановки в общем
        # списке и время тура конца её паузы, иначе None.
        self._free = None
        self._free_timer = QTimer(self)
        self._free_timer.setInterval(FREE_TICK)
        self._free_timer.timeout.connect(self._free_tick)
        view.changed.connect(self.tick)
        view.installEventFilter(self)

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
        self._end_free()
        self.offset = k
        self._reached = None
        self.tour = Tour(self.nav.pose, self.stops[k:],
                         self.bar.pause.value(), self.view.camera.fov_y)
        self.t = 0.0
        self._start = time.monotonic()
        self.nav.start_flight(self.tour, self._start)
        self.playing = True
        self._show()
        self.view.update()

    def toggle(self):
        if self.tour is None:
            return
        if self.playing:
            self._end_free()
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
        self._start = time.monotonic() - t
        self.nav.start_flight(self.tour, self._start)
        self.playing = True
        self._show()
        self.view.update()

    def _seek_started(self):
        if self.tour is None:
            return
        self._end_free()
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
        self._end_free()
        if self.playing:
            self.nav.stop()
        self.playing = False
        self.tour = None
        self.bar.hide()
        self.stop_caption.set_caption("", "", 0.0)

    def _captions_toggled(self, on):
        QgsSettings().setValue(stopcaption.KEY, bool(on))
        self._show()

    def caption_at(self, t):
        """Подпись на кадре на время нынешнего тура t: (название,
        описание, непрозрачность) или None."""
        if self.tour is None or not self.bar.captions.isChecked():
            return None
        found = self.tour.caption_at(t)
        if found is None:
            return None
        i, alpha = found
        stop = self.tour.stops[i]
        return (stop.name or "", plain(getattr(stop, "description", "")),
                alpha)

    def _show_caption(self):
        found = self.caption_at(self.t)
        if found is None:
            self.stop_caption.set_caption("", "", 0.0)
        else:
            self.stop_caption.set_caption(*found)

    def tick(self):
        """Кадр вида: время тура, конец тура или перехват мышью."""
        if self.tour is None or not self.playing:
            return
        if self._free is not None:
            self._free_tick()
            return
        flight = self.nav.flight
        if flight is not None and flight[1] is self.tour:
            self.t = time.monotonic() - flight[0]
        elif self._take_free():
            return
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

    def _take_free(self):
        """Камеру взяли мышью, колесом или клавишами. На паузе остановки
        тур не встаёт: время паузы идёт дальше, вид свободен. Истина,
        если так и вышло."""
        now = time.monotonic() - self._start
        end = self.tour.pause_end(now)
        if end is None:
            return False
        self._free = (self.offset + self.tour.index_at(now), end)
        self.t = now
        self._free_timer.start()
        self._show()
        return True

    def _free_tick(self):
        """Свободная камера на паузе: часы панели и конец паузы. Пока
        камеру держат мышью, тур ждёт отпускания."""
        if self._free is None or self.tour is None:
            self._free_timer.stop()
            return
        index, end = self._free
        now = time.monotonic() - self._start
        # Время остаётся на остановке: на самом конце паузы index_at
        # отдал бы следующую.
        self.t = min(now, end - 1e-6)
        if now >= end and self.nav.grab is None:
            self._end_free()
            if index + 1 < len(self.stops):
                self.play_from(index + 1)
                return
            if self.bar.loop.isChecked():
                self.laps += 1
                self.play_from(0)
                return
            self.t = self.tour.duration
            self.playing = False
        self._show()

    def _end_free(self):
        self._free = None
        self._free_timer.stop()

    def eventFilter(self, watched, event):
        """Клавиши показа тура на виде: вправо, влево, пробел, Esc."""
        if watched is not self.view or event.type() != KEY_PRESS \
                or self.tour is None \
                or getattr(self.view, "shot", None) is not None:
            return False
        mods = event.modifiers()
        if any(mods & held for held in HELD):
            return False
        key = event.key()
        if key == enum(Qt, "Key", "Key_Right"):
            self.play_from(self.index + 1)
        elif key == enum(Qt, "Key", "Key_Left"):
            self.play_from(self.index - 1)
        elif key == enum(Qt, "Key", "Key_Space"):
            self.toggle()
        elif key == enum(Qt, "Key", "Key_Escape"):
            self.stop()
        else:
            return False
        return True

    def pause_for_record(self):
        """Остановить показ перед записью, панель остаётся."""
        self._end_free()
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
                           stop.name if stop else "",
                           getattr(stop, "description", "") if stop else "")
        if self.tour is not None:
            self.bar.set_time(min(self.t, self.tour.duration),
                              self.tour.duration)
        self._show_caption()
