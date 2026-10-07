# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои пункты меню на глобусе: окно списка и открытие адреса.

Пункты - core/menulinks.py, хранятся в настройке LINKS_KEY. Подменю
«Открыть в браузере» меню на глобусе (ui/globemenu.py) показывает их
и пункт «Свои пункты…», он открывает это окно. Адрес открывает
браузер системы, модуль сам в сеть не ходит.
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QAbstractItemView, QDialog,
                                 QDialogButtonBox, QHBoxLayout, QLabel,
                                 QPushButton, QTableWidget, QTableWidgetItem,
                                 QVBoxLayout)

from ..core import menulinks
from ..i18n import tr
from ..qt_compat import enum

LINKS_KEY = "PlanetX/menu_links"


def saved():
    """Свои пункты из настроек: список пар (название, шаблон)."""
    return menulinks.load(QgsSettings().value(LINKS_KEY, "", type=str))


def save(items):
    QgsSettings().setValue(LINKS_KEY, menulinks.dump(items))


def open_link(template, lat, lon, zoom):
    """Адрес точки - браузеру системы."""
    QDesktopServices.openUrl(QUrl(menulinks.fill(template, lat, lon, zoom)))


def reason_text(reason):
    """Причина, по которой пункт не годится, словами."""
    return {
        "name": tr("У пункта нет названия."),
        "scheme": tr("Адрес начинается не с https:// или http://."),
        "place": tr("В адресе нет {lat} или {lon}."),
        "braces": tr("В адресе лишние фигурные скобки или места кроме "
                     "{lat}, {lon} и {zoom}."),
    }[reason]


class MenuLinksDialog(QDialog):
    """Список своих пунктов: название и адрес-шаблон, правка в таблице."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setWindowTitle(tr("Свои пункты меню"))
        self.resize(640, 320)
        layout = QVBoxLayout(self)
        help_text = QLabel(tr(
            "Пункт подменю «Открыть в браузере» меню на глобусе открывает "
            "адрес с точкой под курсором. В адресе {{lat}} и {{lon}} - "
            "широта и долгота в градусах, {{zoom}} - масштаб карты по "
            "виду. "
            "Пример: {example}", example=menulinks.EXAMPLE[1]), self)
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.table = QTableWidget(0, 2, self)
        self.table.setHorizontalHeaderLabels([tr("Название"), tr("Адрес")])
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.setSelectionBehavior(enum(
            QAbstractItemView, "SelectionBehavior", "SelectRows"))
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        row = QHBoxLayout()
        add = QPushButton(tr("Добавить"), self)
        add.setToolTip(tr("Новая строка с примером адреса, его можно "
                          "заменить своим."))
        add.clicked.connect(self._add)
        remove = QPushButton(tr("Удалить"), self)
        remove.setToolTip(tr("Удалить выделенные строки."))
        remove.clicked.connect(self._remove)
        row.addWidget(add)
        row.addWidget(remove)
        row.addStretch(1)
        layout.addLayout(row)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        for name, template in saved():
            self._append(name, template)

    def _append(self, name, template):
        r = self.table.rowCount()
        self.table.insertRow(r)
        self.table.setItem(r, 0, QTableWidgetItem(name))
        self.table.setItem(r, 1, QTableWidgetItem(template))

    def _add(self):
        self._append(*menulinks.EXAMPLE)
        self.table.setCurrentCell(self.table.rowCount() - 1, 0)

    def _remove(self):
        rows = sorted({index.row() for index
                       in self.table.selectedIndexes()}, reverse=True)
        for r in rows:
            self.table.removeRow(r)

    def items(self):
        """Строки таблицы: пары (название, шаблон), пустые пропущены."""
        out = []
        for r in range(self.table.rowCount()):
            cells = [self.table.item(r, c) for c in range(2)]
            name, template = (cell.text().strip() if cell else ""
                              for cell in cells)
            if name or template:
                out.append((name, template))
        return out

    def accept(self):
        items = self.items()
        for n, (name, template) in enumerate(items):
            reason = menulinks.check(name, template)
            if reason:
                self.table.setCurrentCell(n, 1 if reason != "name" else 0)
                self.status.setText(tr("Строка {n}: {reason}", n=n + 1,
                                       reason=reason_text(reason)))
                return
        save(items)
        super().accept()
