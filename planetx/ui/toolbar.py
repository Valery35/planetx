# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Плавающая панель значков в левом верхнем углу вида.

Устройство взято из 3D-сцены Isoliner3D. Сюда идут действия над видом:
обновление, синхронизация с картой, определение объектов, закладки
QGIS. В фазе 3
к ним добавятся снимок кадра, измерения и KML.
"""
import os

from qgis.core import QgsApplication, QgsProject
from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QMenu, QToolButton

from ..i18n import tr
from ..qt_compat import enum

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
    # Выбранная закладка QGIS, QgsBookmark.
    bookmark_chosen = pyqtSignal(object)
    save_view_requested = pyqtSignal()
    identify_toggled = pyqtSignal(bool)
    ruler_clicked = pyqtSignal()
    place_clicked = pyqtSignal()

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
        self._button(
            QgsApplication.getThemeIcon("/mActionMeasure.svg"),
            tr("Линейка. Длина, периметр и площадь на эллипсоиде, "
               "сохранение измерения в «Мои метки»."), self.ruler_clicked)
        self._button(
            QgsApplication.getThemeIcon("/mActionAddMarker.svg"),
            tr("Новая метка, путь или многоугольник в «Мои метки»."),
            self.place_clicked)
        self.bookmarks = QToolButton(self)
        self.bookmarks.setIcon(
            QgsApplication.getThemeIcon("/mActionShowBookmarks.svg"))
        self.bookmarks.setIconSize(ICON_SIZE)
        self.bookmarks.setAutoRaise(True)
        self.bookmarks.setToolTip(tr(
            "Закладки проекта и закладки пользователя QGIS. Выбор "
            "закладки запускает перелёт к её охвату."))
        self.bookmarks.setPopupMode(
            enum(QToolButton, "ToolButtonPopupMode", "InstantPopup"))
        menu = QMenu(self.bookmarks)
        menu.aboutToShow.connect(lambda: self._fill_bookmarks(menu))
        self.bookmarks.setMenu(menu)
        layout.addWidget(self.bookmarks)
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

    def _fill_bookmarks(self, menu):
        """Меню закладок собирается при каждом открытии."""
        menu.clear()
        menu.addAction(tr("Сохранить вид…")).triggered.connect(
            self.save_view_requested)
        groups = ((tr("Проект"), QgsProject.instance().bookmarkManager()),
                  (tr("Пользователь"), QgsApplication.bookmarkManager()))
        empty = True
        for title, manager in groups:
            marks = sorted(manager.bookmarks(),
                           key=lambda b: (b.group(), b.name().lower()))
            if not marks:
                continue
            menu.addSection(title)
            for bookmark in marks:
                name = bookmark.name()
                if bookmark.group():
                    name = "{} / {}".format(bookmark.group(), name)
                action = menu.addAction(name)
                action.triggered.connect(
                    lambda _=False, b=bookmark: self.bookmark_chosen.emit(b))
                empty = False
        if empty:
            menu.addSeparator()
            menu.addAction(tr("Закладок нет")).setEnabled(False)

    def set_dirty(self, dirty):
        """Кнопка «Обновить» горит, пока глобус не показывает выбранное."""
        self.refresh.setStyleSheet(DIRTY_STYLE if dirty else "")
        self.refresh.setToolTip(tr(
            "Обновить глобус: настройки или слои изменились") if dirty
            else tr("Обновить глобус"))
