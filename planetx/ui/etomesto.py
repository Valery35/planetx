# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Старые карты «Это Место»»: каталог карт сайта etomesto.com
у точки, core/etomesto.py.

Пункт «Старые карты «Это Место» здесь…» меню на глобусе. Окно одно,
новая точка заменяет прежнюю. Список - год и название, строка поиска
отбирает по словам. Двойной щелчок или «Открыть на сайте» открывают
страницу карты браузером системы, модуль карт сайта не показывает.
"""
from qgis.PyQt.QtCore import Qt, QUrl
from qgis.PyQt.QtGui import QDesktopServices
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QLabel,
                                 QLineEdit, QPushButton, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout)

from ..core import etomesto
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum

NAME_ROLE = enum(Qt, "ItemDataRole", "UserRole")


class EtomestoDialog(QDialog):
    """Немодальное окно каталога карт «Это Место» у точки."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Старые карты «Это Место»"))
        self.setModal(False)
        self.point = None
        self.items = []
        self.reply = None
        self.intro = QLabel(tr(
            "Карты сайта «Это Место» (etomesto.com), которые накрывают "
            "точку. Карта открывается на сайте, там её можно наложить "
            "на современную и скачать по правилам сайта."), self)
        self.intro.setWordWrap(True)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("Поиск по названию или году"))
        self.search.setToolTip(tr(
            "Оставляет карты, в названии или годе которых есть все слова."))
        self.search.textChanged.connect(self._fill)
        self.list = QTreeWidget(self)
        self.list.setColumnCount(2)
        self.list.setHeaderLabels([tr("Год"), tr("Название")])
        self.list.setRootIsDecorated(False)
        self.list.setSortingEnabled(True)
        # От старых карт к новым, как список сайта.
        self.list.sortByColumn(0, enum(Qt, "SortOrder", "AscendingOrder"))
        self.list.itemDoubleClicked.connect(lambda *a: self.open_page())
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.open_button = QPushButton(tr("Открыть на сайте"), self)
        self.open_button.setToolTip(tr(
            "Открывает страницу выбранной карты на etomesto.com в браузере."))
        self.open_button.clicked.connect(self.open_page)
        buttons = QDialogButtonBox(self)
        buttons.addButton(self.open_button,
                          enum(QDialogButtonBox, "ButtonRole",
                               "ActionRole"))
        close = buttons.addButton(enum(QDialogButtonBox, "StandardButton",
                                       "Close"))
        close.clicked.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(self.intro)
        layout.addWidget(self.search)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.resize(560, 520)

    def show_point(self, lat, lon):
        """Список карт у точки, прежний запрос снимается."""
        self.point = (lat, lon)
        self.items = []
        self.list.clear()
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()
        self.status.setText(tr("Запрос к «Это Место»…"))
        point = self.point
        self.reply = fetch_bytes(
            etomesto.list_url(lat, lon),
            lambda data, error: self._arrived(point, data, error),
            fresh=True)

    def _arrived(self, point, data, error):
        if point != self.point:
            return  # ответ прежней точки
        self.reply = None
        if data is None:
            self.status.setText(tr("Сайт не ответил: {error}",
                                   error=error or "-"))
            return
        self.items = etomesto.parse_list(data)
        self._fill()

    def _fill(self, *args):
        words = self.search.text()
        shown = [i for i in self.items if etomesto.matches(i, words)]
        self.list.setSortingEnabled(False)
        self.list.clear()
        for year, title, name in shown:
            row = QTreeWidgetItem(["" if year is None else str(year),
                                   title])
            row.setData(0, NAME_ROLE, name)
            row.setToolTip(1, title)
            self.list.addTopLevelItem(row)
        self.list.setSortingEnabled(True)
        self.list.resizeColumnToContents(0)
        if self.point is not None and self.items:
            self.status.setText(tr(
                "Карт у точки {total}, показано {shown}. Двойной щелчок "
                "открывает карту на сайте.", total=len(self.items),
                shown=len(shown)))
        elif self.point is not None:
            self.status.setText(tr("У этой точки карт на сайте нет."))
        self.open_button.setEnabled(bool(shown))

    def page(self):
        """Адрес страницы выбранной карты или None."""
        item = self.list.currentItem()
        if item is None or self.point is None:
            return None
        return etomesto.page_url(item.data(0, NAME_ROLE), *self.point)

    def open_page(self):
        url = self.page()
        if url is not None:
            QDesktopServices.openUrl(QUrl(url))

    def closeEvent(self, event):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()
        super().closeEvent(event)
