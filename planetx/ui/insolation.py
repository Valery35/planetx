# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Инсоляция»: промежуток дат и участок многоугольником
(ui/area.py).

Расчёт - core/insolation.py в круге, накрывающем участок, его ведёт
окно глобуса. Вне многоугольника часов нет. Картинки тайлов слоя даёт
ui/viewshed.ResultTiles.
"""
import calendar

from qgis.PyQt.QtCore import QDate, pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QDateEdit, QDialog,
                                 QDialogButtonBox, QFormLayout, QLabel,
                                 QPushButton, QVBoxLayout)

from ..i18n import tr
from ..qt_compat import enum
from .area import Area
from .results import keep_buttons
from .viewshed import fit_status

SIDE = 10.0  # км, сторона участка по умолчанию
MOST = 40.0  # км, наибольший участок


def day_start(date):
    """Начало суток даты QDate, секунды UTC."""
    return calendar.timegm((date.year(), date.month(), date.day(), 0, 0, 0))


class InsolationDialog(QDialog):
    """Окно «Инсоляция». Сигнал build - начало первых и последних
    суток (секунды UTC). OK записывает инсоляцию в проект QGIS,
    «Отмена» убирает её (ui/results.py)."""

    build = pyqtSignal(float, float)

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Инсоляция"))
        self.point = None
        self.place = QLabel(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, SIDE, MOST,
                         "PlanetX/insolation/side")
        self.area.side.setToolTip(self.area.side.toolTip() + " " + tr(
            "Больше - шаг сетки крупнее. Тени гор берутся с расстояния "
            "не меньше половины участка и не меньше 5 км."))
        today = QDate.currentDate()
        self.first = QDateEdit(today, self)
        self.last = QDateEdit(today, self)
        for edit in (self.first, self.last):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("dd.MM.yyyy")
        self.first.setToolTip(tr(
            "Первые сутки промежутка. Итог - среднее количество часов "
            "прямого солнца в сутки за промежуток."))
        self.last.setToolTip(tr(
            "Последние сутки промежутка, включительно. Длинный промежуток "
            "считается по 15 суткам, взятым равномерно."))
        self.first.dateChanged.connect(self._first_changed)
        self.last.dateChanged.connect(self._last_changed)
        self.buildings = QCheckBox(tr("Учитывать здания"), self)
        self.buildings.setChecked(True)
        self.buildings.setToolTip(tr(
            "Здания OpenFreeMap дают тени и сами получают солнце крышей. "
            "Высота у части зданий условная. Здание уже шага сетки может "
            "не попасть в расчёт."))
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Первые сутки"), self.first)
        form.addRow(tr("Последние сутки"), self.last)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow("", self.buildings)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.clicked.connect(lambda: self.build.emit(
            float(day_start(self.first.date())),
            float(day_start(self.last.date()))))
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(run, role)
        self.ok = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def _first_changed(self, date):
        if self.last.date() < date:
            self.last.setDate(date)

    def _last_changed(self, date):
        if self.first.date() > date:
            self.first.setDate(date)
