# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Плавающая панель значков в левом верхнем углу вида.

Устройство взято из 3D-сцены Isoliner3D. Сюда идут действия над видом:
обновление, синхронизация с картой, определение объектов. В фазе 3
к ним добавятся снимок кадра, измерения и KML.
"""
import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QToolButton

from ..i18n import tr

ROOT = os.path.dirname(os.path.dirname(__file__))
ICON_SIZE = QSize(20, 20)
STYLE = ("QFrame#planetxToolbar { background: rgba(250, 250, 250, 225); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
DIRTY_STYLE = "QToolButton { background: #ff9f1c; border-radius: 3px; }"


class ViewToolbar(QFrame):
    """Панель значков. Сигналы - по одному на кнопку."""

    refresh_clicked = pyqtSignal()
    about_clicked = pyqtSignal()
    sync_toggled = pyqtSignal(bool)
    identify_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("planetxToolbar")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.refresh = self._button(
            QgsApplication.getThemeIcon("/mActionRefresh.svg"),
            tr("Обновить глобус"), self.refresh_clicked)
        self.sync = self._button(
            QIcon(os.path.join(ROOT, "sync.svg")),
            tr("Синхронизация с окном карты QGIS. Направление - "
               "в свойствах вида."), self.sync_toggled, checkable=True)
        self.identify = self._button(
            QgsApplication.getThemeIcon("/mActionIdentify.svg"),
            tr("Определить объекты. Щелчок по глобусу показывает "
               "координаты и высоту точки и объекты слоёв проекта, "
               "отмеченных на глобусе."), self.identify_toggled,
            checkable=True)
        self._button(QIcon(os.path.join(ROOT, "about.svg")),
                     tr("О модуле"), self.about_clicked)
        self.adjustSize()

    def _button(self, icon, tip, signal, checkable=False):
        button = QToolButton(self)
        button.setIcon(icon)
        button.setIconSize(ICON_SIZE)
        button.setAutoRaise(True)
        button.setToolTip(tip)
        if checkable:
            button.setCheckable(True)
            button.toggled.connect(signal)
        else:
            button.clicked.connect(signal)
        self.layout().addWidget(button)
        return button

    def set_dirty(self, dirty):
        """Кнопка «Обновить» горит, пока глобус не показывает выбранное."""
        self.refresh.setStyleSheet(DIRTY_STYLE if dirty else "")
        self.refresh.setToolTip(tr(
            "Обновить глобус: настройки или слои изменились") if dirty
            else tr("Обновить глобус"))
