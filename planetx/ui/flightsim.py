# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Режим полёта: свой самолёт с клавиатуры, пункт «Полёт» меню
на глобусе. Ядро - core/flightsim.py.

Клавиши на виде: стрелка вверх - нос вниз, вниз - нос вверх, влево
и вправо - крен, PageUp и PageDown - тяга, V - вид из кабины и обратно,
Esc - выход. Камера идёт следом сзади и сверху (core.movers.chase_on -
высота над рельефом в точке взгляда), колесо меняет расстояние, средняя
кнопка - наклон, как у камеры следом за самолётом ADS-B. Из кабины глаз
стоит в самолёте, взгляд - по курсу с тангажом и креном самолёта: точка
взгляда позы - в воздухе в COCKPIT_LOOK метрах впереди, наклон 90° плюс
тангаж, горизонт на своём месте, как в имитаторе Google Earth Pro.
Самолёт - истребитель или винтовой (core.flightsim.KINDS).
Самолёт - условная модель aircraft.unit_plane_parts. Показания -
индикатор на стекле ui/flighthud.py, клавиша H прячет его, внизу вида -
подсказка клавиш.
"""
import math
import time

from qgis.PyQt.QtCore import QEvent, QObject, QRectF, QTimer, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter
from qgis.PyQt.QtWidgets import QWidget

from .. import journal
from ..core import aircraft, flightsim, models, movers
from ..core.navigation import Pose
from ..core.tour import bearing
from ..core.trains import destination
from ..i18n import tr
from ..qt_compat import enum, enum_int
from ..render.models import Model as ModelItem
from .chase import wheel_reach
from .flighthud import FlightHud

TICK = 33  # мс между шагами полёта
GROUP = "flightsim"
COLOR = (0.96, 0.45, 0.15)
CHASE_REACH = 150.0  # м от камеры до самолёта при старте
CHASE_TILT = 75.0
COCKPIT_LOOK = 1000.0  # м от глаза до точки взгляда в кабине
# Знак крена позы вида при крене самолёта вправо, сверен шагом
# flight_sim: правая сторона земли на кадре поднимается.
COCKPIT_ROLL = -1.0
END_SHOW = 3.0  # с надписи о касании земли
# Строка показаний: логические пиксели окна, отступ снизу над подписью
# источников. Выбор помощника, утверждает автор.
TEXT_SIZE = 15
PAD = 10
BOTTOM = 44
BACK = (15, 25, 40, 175)

KEY_PRESS = enum(QEvent, "Type", "KeyPress")
KEY_RELEASE = enum(QEvent, "Type", "KeyRelease")
WHEEL = enum(QEvent, "Type", "Wheel")


def _key(name):
    return enum_int(enum(Qt, "Key", name))


def _keys():
    key = _key
    return {key("Key_Up"): ("pitch", -1), key("Key_Down"): ("pitch", 1),
            key("Key_Left"): ("roll", -1), key("Key_Right"): ("roll", 1),
            key("Key_PageUp"): ("throttle", 1),
            key("Key_PageDown"): ("throttle", -1)}


class FlightReadout(QWidget):
    """Строка показаний полёта внизу вида, мышь проходит сквозь."""

    def __init__(self, view):
        super().__init__(view)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.lines = []
        self.resize(view.size())
        view.installEventFilter(self)
        self.hide()

    def set_lines(self, lines):
        self.lines = list(lines)
        self.setVisible(bool(self.lines))
        if self.lines:
            self.raise_()
            self.update()

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize"):
            self.resize(watched.size())
        return False

    def paintEvent(self, event):
        if not self.lines:
            return
        painter = QPainter(self)
        try:
            painter.setRenderHint(enum(QPainter, "RenderHint",
                                       "Antialiasing"))
            font = QFont(painter.font())
            font.setPixelSize(TEXT_SIZE)
            painter.setFont(font)
            metrics = painter.fontMetrics()
            line = metrics.height()
            width = max(metrics.horizontalAdvance(text)
                        if hasattr(metrics, "horizontalAdvance")
                        else metrics.width(text) for text in self.lines)
            box_w = width + 2 * PAD
            box_h = line * len(self.lines) + 2 * PAD
            left = (self.width() - box_w) / 2.0
            top = self.height() - BOTTOM - box_h
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(*BACK))
            painter.drawRoundedRect(QRectF(left, top, box_w, box_h), 6.0, 6.0)
            center = enum(Qt, "AlignmentFlag", "AlignHCenter")
            for n, text in enumerate(self.lines):
                painter.setPen(QColor(255, 255, 255) if n == 0
                               else QColor(200, 210, 222))
                painter.drawText(QRectF(left, top + PAD + n * line, box_w,
                                        line), center, text)
        finally:
            painter.end()


class FlightSim(QObject):
    """Полёт своего самолёта на виде окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.plane = None
        self.held = {}
        self.keys = _keys()
        self._last = None
        self._ended = None
        self.reach = CHASE_REACH
        self.model_size = (16.0, 16.0, 16.0)
        self.cockpit = False
        self._tilt = CHASE_TILT
        self.readout = FlightReadout(self.view)
        self.hud = FlightHud(self.view)
        self.hud_on = True
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._tick)
        base = models.frame(0.0, 0.0)
        parts = models.merge(aircraft.unit_plane_parts(COLOR))
        arrays = models.vertices(parts, 0.0, 0.0)
        self._base = base
        self._shared = [(array, None, part.rgba, None)
                        for array, part in zip(arrays, parts)]

    @property
    def flying(self):
        return self.plane is not None and not self.plane.crashed

    def _ground(self, lat, lon):
        scale = self.view.store.scale
        return self.view.label_height(lat, lon) / scale if scale else 0.0

    def start(self, lat, lon, kind=flightsim.FIGHTER):
        """Полёт с точки lat, lon: на START_HEIGHT над поверхностью,
        курс - азимут вида, kind - вид самолёта core.flightsim.KINDS."""
        self.stop()
        for live in getattr(self.window, "live_managers", ()):
            if getattr(live, "followed", None) is not None:
                live.set_follow(None)
        heading = self.view.navigator.pose.heading
        ground = self._ground(lat, lon)
        self.plane = flightsim.Plane(lat, lon,
                                     ground + flightsim.START_HEIGHT, heading,
                                     kind=kind)
        length = self.plane.spec.length
        self.model_size = (length, length, length)
        self.held = {}
        self._ended = None
        self.reach = CHASE_REACH
        self.cockpit = False
        self._last = time.monotonic()
        self.view.navigator.show(Pose(lat, lon, CHASE_REACH, heading,
                                      CHASE_TILT))
        self.view.installEventFilter(self)
        self.view.setFocus()
        self.view.models.set_models([ModelItem(
            (GROUP, "plane"), self._shared, (0.0, 0.0, "absolute", 0.0),
            0.6 * length, 1.0, None, self._base, mover=self._mover,
            live=True, mesh=(GROUP, "plane"))], group=GROUP)
        self.timer.start()
        journal.note("Полёт: старт {:.4f}, {:.4f}".format(lat, lon))
        self._tick()

    def stop(self):
        """Конец полёта: модель, строка и клавиши сняты, камера стоит."""
        if self.plane is None:
            return
        self.timer.stop()
        self.view.navigator.air = False
        self.plane = None
        self.held = {}
        self.view.removeEventFilter(self)
        self.view.models.set_models([], group=GROUP)
        self.readout.set_lines([])
        self.hud.set_state(None)
        self.view.update()

    def close(self):
        self.stop()

    def _mover(self, now):
        plane = self.plane
        if plane is None or self.cockpit:
            return None
        return plane.lat, plane.lon, models.moved(
            self._base, plane.lat, plane.lon, plane.heading, plane.pitch,
            plane.roll, self.model_size), plane.alt

    def _input(self, axis):
        return sum(sign for kind, sign in self.held.values() if kind == axis)

    def _tick(self):
        plane = self.plane
        if plane is None:
            return
        now = time.monotonic()
        dt = min(now - self._last, 0.5)
        self._last = now
        if self._ended is not None:
            if now - self._ended >= END_SHOW:
                self.stop()
            return
        flightsim.step(plane, dt, pitch_in=self._input("pitch"),
                       roll_in=self._input("roll"),
                       throttle_in=self._input("throttle"),
                       ground=self._ground(plane.lat, plane.lon))
        ground = self._ground(plane.lat, plane.lon)
        self._follow(ground)
        if plane.crashed:
            self._ended = now
            self.held = {}
            self.hud.set_state(None)
            self.readout.set_lines([tr("Касание земли - полёт окончен.")])
            journal.note("Полёт: касание земли")
            return
        out = flightsim.readout(plane, ground)
        out["pitch"] = plane.pitch
        out["roll"] = plane.roll
        hud = self.cockpit and self.hud_on
        self.hud.set_state(out if hud else None)
        lines = [tr("↑ ↓ - нос вниз и вверх · ← → - крен · PageUp, "
                    "PageDown - тяга · V - вид из кабины · H - приборы · "
                    "Esc - выход")]
        if not hud:
            lines.insert(0, tr(
                "{speed} км/ч · высота {alt} м, над землёй {height} м · "
                "курс {heading}° · подъём {climb} м/с · тяга {throttle} %",
                speed="{:.0f}".format(out["speed"]),
                alt="{:.0f}".format(out["alt"]),
                height="{:.0f}".format(out["height"]),
                heading="{:.0f}".format(out["heading"]),
                climb="{:+.1f}".format(out["climb"]),
                throttle="{:.0f}".format(out["throttle"])))
        self.readout.set_lines(lines)

    def _follow(self, ground):
        plane = self.plane
        pose = self.view.navigator.pose
        if self.cockpit:
            self._cockpit()
            return
        look_lat, look_lon, look, distance = movers.chase_on(
            plane.lat, plane.lon, plane.heading,
            plane.alt * self.view.store.scale, self.view.label_height,
            self.reach, pose.tilt)
        self.view.navigator.show(Pose(look_lat, look_lon, distance, look,
                                      pose.tilt))
        self.view.update()

    def _cockpit(self):
        """Глаз в самолёте, взгляд по курсу с тангажом, кадр повёрнут на
        крен. Точка взгляда - в воздухе, поза ставится мимо show: show
        посадил бы её на рельеф и поднял бы глаз над ним."""
        plane = self.plane
        rad = math.radians(plane.pitch)
        look_lat, look_lon = destination(plane.lat, plane.lon,
                                         plane.heading,
                                         COCKPIT_LOOK * math.cos(rad))
        look = (bearing(look_lat, look_lon, plane.lat, plane.lon)
                + 180.0) % 360.0
        height = plane.alt * self.view.store.scale \
            + COCKPIT_LOOK * math.sin(rad)
        navigator = self.view.navigator
        navigator.stop()
        navigator.set_pose(Pose(look_lat, look_lon, COCKPIT_LOOK, look,
                                90.0 + plane.pitch, h=height,
                                terrain=self.view.terrain_at,
                                roll=COCKPIT_ROLL * plane.roll))
        navigator.air = True
        self.view.update()

    def set_cockpit(self, on):
        """Вид из кабины или сзади. Сзади - прежний наклон позы."""
        on = bool(on)
        if self.plane is None or on == self.cockpit:
            return
        pose = self.view.navigator.pose
        if on:
            self._tilt = pose.tilt
        self.cockpit = on
        self.view.navigator.air = False
        if not on:
            plane = self.plane
            self.view.navigator.show(Pose(plane.lat, plane.lon, CHASE_REACH,
                                          plane.heading, self._tilt))
        self._follow(self._ground(self.plane.lat, self.plane.lon))

    def eventFilter(self, watched, event):
        """Клавиши полёта на виде. Прочие клавиши остаются виду."""
        kind = event.type()
        if watched is not self.view or self.plane is None:
            return False
        if kind == WHEEL:
            # Колесо - расстояние от камеры до самолёта: поза вида
            # ставится каждый шаг и гасила бы приближение вида.
            notches = event.angleDelta().y() / 120.0
            if notches and not self.cockpit:
                self.reach = wheel_reach(self.reach, notches)
            return True
        if kind not in (KEY_PRESS, KEY_RELEASE):
            return False
        key = enum_int(event.key())
        if key == _key("Key_Escape"):
            if kind == KEY_PRESS:
                self.stop()
            return True
        if key == _key("Key_V"):
            if kind == KEY_PRESS and not event.isAutoRepeat():
                self.set_cockpit(not self.cockpit)
            return True
        if key == _key("Key_H"):
            if kind == KEY_PRESS and not event.isAutoRepeat():
                self.hud_on = not self.hud_on
                self._tick()
            return True
        found = self.keys.get(key)
        if found is None:
            return False
        if event.isAutoRepeat():
            return True
        if kind == KEY_PRESS:
            self.held[key] = found
        else:
            self.held.pop(key, None)
        return True
