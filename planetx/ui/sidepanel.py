# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Панель свойств справа от вида глобуса.

Решение автора от 11 октября 2026 года, шаг 4 плана «интерфейс над
возможностями» в AGENTS.md - одна панель вместо отдельных окон свойств
метки, папки, картинки, батиметрии и выдавливания. Окно свойств
остаётся своим классом QDialog со своими кнопками, панель только
встраивает его как виджет. Конец правки - сигнал finished окна, как
и раньше, поэтому записи и предпросмотр не меняются.

В панели одно окно. Новое закрывает прежнее его «Отменой» - правки
прежнего, не записанные «OK», не сохраняются. Ширину панели задаёт
разделитель, она помнится в настройках.
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (QFrame, QHBoxLayout, QLabel, QScrollArea,
                                 QToolButton, QVBoxLayout, QWidget)

from ..i18n import tr
from ..qt_compat import enum

WIDTH_KEY = "PlanetX/side_panel_width"
WIDTH = 360  # логических пикселей по умолчанию, выбор помощника


class SidePanel(QWidget):
    """Панель с одним встроенным окном свойств. changed - окно в панели
    сменилось или ушло, окно глобуса подстраивает разделитель."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.dialog = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(2)
        head = QHBoxLayout()
        self.title = QLabel(self)
        font = QFont(self.title.font())
        font.setBold(True)
        self.title.setFont(font)
        self.title.setWordWrap(True)
        head.addWidget(self.title, 1)
        close = QToolButton(self)
        close.setText("✕")
        close.setAutoRaise(True)
        close.setToolTip(tr("Закрыть свойства без записи правок, как "
                            "кнопка «Отмена»."))
        close.clicked.connect(self.close_dialog)
        head.addWidget(close)
        layout.addLayout(head)
        line = QFrame(self)
        line.setFrameShape(enum(QFrame, "Shape", "HLine"))
        layout.addWidget(line)
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(enum(QFrame, "Shape", "NoFrame"))
        layout.addWidget(self.scroll, 1)
        self.hide()

    def host(self, dialog):
        """Встроить окно свойств. Прежнее окно закрывается «Отменой».
        То же окно второй раз - только показ."""
        if dialog is self.dialog:
            self.show()
            return
        self.close_dialog()
        self.dialog = dialog
        # Окно стоит в своей высоте, лишнее место панели - под ним.
        # Прежде прокрутка растягивала окно на всю высоту панели, и его
        # строки расходились пустотами, замечание автора от 17 октября
        # 2026 года.
        holder = QWidget(self.scroll)
        column = QVBoxLayout(holder)
        column.setContentsMargins(0, 0, 0, 0)
        dialog.setParent(holder, enum(Qt, "WindowType", "Widget"))
        column.addWidget(dialog)
        column.addStretch(1)
        self.scroll.setWidget(holder)
        self.title.setText(dialog.windowTitle())
        dialog.windowTitleChanged.connect(self._retitle)
        dialog.finished.connect(lambda *a, d=dialog: self._released(d))
        dialog.show()
        self.show()
        self.changed.emit()

    def close_dialog(self):
        """Закрыть окно в панели «Отменой»."""
        if self.dialog is not None:
            self.dialog.reject()

    def _retitle(self, text):
        self.title.setText(text)

    def _released(self, dialog):
        """Окно закончило работу: панель пустеет и прячется."""
        if dialog is not self.dialog:
            return
        self.dialog = None
        taken = self.scroll.takeWidget()
        if taken is not None:
            taken.hide()
            taken.deleteLater()
        self.hide()
        self.changed.emit()


def saved_width():
    """Ширина панели из настроек."""
    return int(QgsSettings().value(WIDTH_KEY, WIDTH, type=int) or WIDTH)


def save_width(width):
    if width > 0:
        QgsSettings().setValue(WIDTH_KEY, int(width))
