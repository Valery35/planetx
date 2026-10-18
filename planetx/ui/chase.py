# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Колесо и Esc камеры следом за поездом, судном или самолётом.

Камера следом ставит позу вида каждые 50 мс (navigation.Navigator.show),
а show гасит движение, в том числе накопленное приближение колеса, -
колесо в камере следом не действовало. Замечание автора от 19 октября
2026 года - «после включения камеры следом теряется приближение-
удаление». Пока камера идёт следом, колесо меняет здесь расстояние от
глаза до объекта (reach), Esc отпускает камеру.
"""
from qgis.PyQt.QtCore import QEvent, QObject, Qt

from ..core import movers
from ..qt_compat import enum, enum_int

WHEEL_STEP = 0.8  # множитель расстояния на щелчок колеса, как у вида
START_REACH = 1500.0  # м от глаза до объекта при включении
MAX_REACH = 2.0e7

WHEEL = enum(QEvent, "Type", "Wheel")
KEY_PRESS = enum(QEvent, "Type", "KeyPress")


def wheel_reach(reach, notches):
    """Расстояние после notches щелчков колеса, вверх - ближе."""
    reach = reach * WHEEL_STEP ** notches
    return min(max(reach, movers.CHASE_MIN), MAX_REACH)


class ChaseControl(QObject):
    """Перехват колеса и Esc на виде, пока камера идёт следом."""

    def __init__(self, view, release):
        super().__init__(view)
        self.view = view
        self.release = release
        self.reach = START_REACH
        self.active = False

    def start(self, reach=START_REACH):
        self.reach = min(max(float(reach), movers.CHASE_MIN), MAX_REACH)
        if not self.active:
            self.view.installEventFilter(self)
            self.active = True

    def stop(self):
        if self.active:
            self.view.removeEventFilter(self)
            self.active = False

    def eventFilter(self, watched, event):
        if watched is not self.view or not self.active:
            return False
        kind = event.type()
        if kind == WHEEL:
            notches = event.angleDelta().y() / 120.0
            if notches:
                self.reach = wheel_reach(self.reach, notches)
                self.view.update()
            return True
        if kind == KEY_PRESS and enum_int(event.key()) == enum_int(
                enum(Qt, "Key", "Key_Escape")):
            self.release()
            return True
        return False
