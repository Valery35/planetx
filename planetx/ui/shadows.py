# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Тени»: участок многоугольником (ui/area.py), тени и солнце
на момент шкалы времени.

Расчёт - core/shadows.py, его ведёт окно глобуса (ui/globe/tools.py):
горизонт участка считается при «Построить», карта на момент - при
каждом движении шкалы времени. Картинки тайлов слоя даёт
ui/viewshed.ResultTiles.
"""
import time

from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QLabel, QPushButton,
                                 QVBoxLayout)

from ..i18n import tr
from ..qt_compat import enum
from .area import Area
from .results import keep_buttons
from .viewshed import fit_status

SIDE = 3.0  # км, сторона участка по умолчанию
MOST = 40.0  # км, наибольший участок


def moment_text(moment):
    """Момент для окна: местное время компьютера и UTC."""
    local = time.strftime("%d.%m.%Y %H:%M", time.localtime(moment))
    utc = time.strftime("%H:%M", time.gmtime(moment))
    return tr("{local} (UTC {utc})", local=local, utc=utc)


class ShadowsDialog(QDialog):
    """Окно «Тени». Сигнал build - построить горизонт участка. OK
    записывает карту на текущий момент в проект QGIS, «Отмена» убирает
    её (ui/results.py)."""

    build = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Тени"))
        self.point = None
        self.place = QLabel(self)
        self.moment = QLabel(self)
        self.moment.setToolTip(tr(
            "Момент - правый бегунок шкалы времени, без шкалы - часы "
            "компьютера. После «Построить» тени идут за шкалой: двигайте "
            "бегунок или пустите показ ▶."))
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, SIDE, MOST, "PlanetX/shadows/side")
        self.area.side.setToolTip(self.area.side.toolTip() + " " + tr(
            "Больше - шаг сетки крупнее. Тени гор берутся с расстояния "
            "не меньше половины участка и не меньше 5 км."))
        self.buildings = QCheckBox(tr("Учитывать здания"), self)
        self.buildings.setChecked(True)
        self.buildings.setToolTip(tr(
            "Здания OpenFreeMap, свои 3D-модели и выдавленные многоугольники "
            "дают тени. Высота у части зданий OpenFreeMap условная. Здание "
            "уже шага сетки может не попасть в расчёт."))
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Момент"), self.moment)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow("", self.buildings)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.clicked.connect(self.build.emit)
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(run, role)
        self.ok = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def set_moment(self, moment):
        self.moment.setText(moment_text(moment))
