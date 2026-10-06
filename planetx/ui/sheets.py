# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Номенклатура листа»: номера листов карт в точке по пункту
меню на глобусе. Расчёт - core/sheets.py. Щелчок по строке копирует
номер в буфер обмена. Окно одно, новая точка заменяет прежнюю."""
from qgis.PyQt.QtWidgets import (QAbstractItemView, QApplication, QDialog,
                                 QLabel, QTableWidget, QTableWidgetItem,
                                 QVBoxLayout)

from ..core import sheets
from ..i18n import tr
from ..qt_compat import enum
from .identify import point_text


def system_names():
    """Система разграфки: название в окне."""
    return {
        "imw": tr("Международная карта мира (IMW)"),
        "russian": tr("Российская номенклатура"),
        "jog": tr("NATO, JOG"),
        "mgrs": tr("MGRS, квадрат 100 км"),
    }


def scale_text(scale):
    """«1:1 000 000» или пустая строка."""
    if scale is None:
        return ""
    return "1:" + "{:,}".format(scale).replace(",", " ")


class SheetsDialog(QDialog):
    """Номера листов в точке, по строке на систему и масштаб."""

    def __init__(self, parent, coords="decimal"):
        super().__init__(parent)
        self.coords = coords
        self.setWindowTitle(tr("Номенклатура листа"))
        self.resize(520, 300)
        layout = QVBoxLayout(self)
        self.place = QLabel(self)
        layout.addWidget(self.place)
        self.table = QTableWidget(0, 3, self)
        self.table.setHorizontalHeaderLabels(
            [tr("Система"), tr("Масштаб"), tr("Номер листа")])
        self.table.setEditTriggers(enum(QTableWidget, "EditTrigger",
                                        "NoEditTriggers"))
        self.table.setSelectionBehavior(enum(
            QAbstractItemView, "SelectionBehavior", "SelectRows"))
        self.table.verticalHeader().setVisible(False)
        self.table.setToolTip(tr(
            "Щелчок по строке копирует номер листа в буфер обмена."))
        self.table.cellClicked.connect(self._copy)
        layout.addWidget(self.table)
        self.status = QLabel(tr(
            "Щелчок по строке копирует номер листа. По российской "
            "номенклатуре нумеруются и листы Госгеолкарты-1000 и 200."),
            self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.rows = []

    def show_point(self, lat, lon):
        """Номера листов для новой точки."""
        self.place.setText(point_text(lat, lon, fmt=self.coords))
        names = system_names()
        mark = " ({})".format(tr("Ю. П."))
        self.rows = sheets.sheets(lat, lon, south_mark=mark)
        self.table.setRowCount(len(self.rows))
        for r, (system, scale, number) in enumerate(self.rows):
            values = (names[system], scale_text(scale),
                      number or tr("нет листа"))
            for c, value in enumerate(values):
                self.table.setItem(r, c, QTableWidgetItem(value))
        self.table.resizeColumnsToContents()

    def _copy(self, row, column):
        number = self.rows[row][2] if 0 <= row < len(self.rows) else None
        if not number:
            return
        QApplication.clipboard().setText(number)
        self.status.setText(tr("Скопировано: {number}", number=number))
