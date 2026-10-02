# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Инсоляция»: промежуток дат и радиус круга вокруг метки.

Расчёт - core/insolation.py, его ведёт окно глобуса. Картинки тайлов
слоя даёт ui/viewshed.ResultTiles.
"""
import calendar

from qgis.PyQt.QtCore import QDate, pyqtSignal
from qgis.PyQt.QtWidgets import (QDateEdit, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QLabel,
                                 QPushButton, QVBoxLayout)

from ..i18n import tr
from ..qt_compat import enum
from .viewshed import fit_status


def day_start(date):
    """Начало суток даты QDate, секунды UTC."""
    return calendar.timegm((date.year(), date.month(), date.day(), 0, 0, 0))


class InsolationDialog(QDialog):
    """Окно «Инсоляция». Сигналы build - начало первых и последних
    суток (секунды UTC) и радиус в метрах, clear - убрать слой."""

    build = pyqtSignal(float, float, float)
    clear = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Инсоляция"))
        self.point = None
        self.place = QLabel(self)
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
        self.radius = QDoubleSpinBox(self)
        self.radius.setRange(0.2, 30.0)
        self.radius.setDecimals(1)
        self.radius.setSuffix(tr(" км"))
        self.radius.setValue(5.0)
        self.radius.setToolTip(tr(
            "Радиус круга расчёта. Больше - шаг сетки крупнее. Тени "
            "гор берутся с расстояния не меньше радиуса и не меньше "
            "5 км."))
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Первые сутки"), self.first)
        form.addRow(tr("Последние сутки"), self.last)
        form.addRow(tr("Радиус"), self.radius)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.clicked.connect(lambda: self.build.emit(
            float(day_start(self.first.date())),
            float(day_start(self.last.date())),
            self.radius.value() * 1000.0))
        remove = QPushButton(tr("Убрать"), self)
        remove.setToolTip(tr("Убрать слой инсоляции с глобуса."))
        remove.clicked.connect(self.clear)
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(run, role)
        buttons.addButton(remove, role)
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
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
