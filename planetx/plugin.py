# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Регистрация плагина в интерфейсе QGIS."""
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QIcon

from . import journal
from .i18n import tr
from .meta import plugin_version
from .qt_compat import QAction, enum

MINIMIZED = enum(Qt, "WindowState", "WindowMinimized")

ICON = os.path.join(os.path.dirname(__file__), "icon.svg")
ABOUT_ICON = os.path.join(os.path.dirname(__file__), "about.svg")
# Имя объекта панели. По нему QGIS запоминает, где пользователь её
# поставил, и возвращает туда при следующем запуске.
TOOLBAR = "PlanetXToolBar"


class PlanetXPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.about_action = None
        self.toolbar = None
        self.window = None

    def initGui(self):
        journal.start(plugin_version())
        self.action = QAction(QIcon(ICON), "PlanetX", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToWebMenu("PlanetX", self.action)
        self.about_action = QAction(QIcon(ABOUT_ICON),
                                    tr("О модуле PlanetX"),
                                    self.iface.mainWindow())
        self.about_action.triggered.connect(self.about)
        self.iface.addPluginToWebMenu("PlanetX", self.about_action)
        # Своя панель инструментов. Кнопка на общей панели модулей
        # отдельно не передвигается, а своя панель перетаскивается
        # мышью куда угодно. Панель «Интернет» QGIS по умолчанию прячет.
        self.toolbar = self.iface.addToolBar("PlanetX")
        self.toolbar.setObjectName(TOOLBAR)
        self.toolbar.setToolTip("PlanetX")
        self.toolbar.addAction(self.action)
        self.toolbar.addAction(self.about_action)

    def _window_gone(self, window):
        # Ссылка снимается в момент закрытия. Закрытое окно Qt уничтожает
        # позже, и к этому времени меню могло открыть новое, его ссылку
        # трогать нельзя.
        if self.window is window:
            self.window = None

    def _drop_deleted(self):
        # Окно, которое Qt уничтожил без сигнала closed, снимается.
        # Так бывало, когда closeEvent падал до сигнала.
        if self.window is None:
            return
        try:
            self.window.isVisible()
        except RuntimeError:
            self.window = None

    def unload(self):
        self._drop_deleted()
        if self.window is not None:
            self.window.close()
            self.window = None
        if self.action is not None:
            self.iface.removePluginWebMenu("PlanetX", self.action)
            self.action = None
        if self.about_action is not None:
            self.iface.removePluginWebMenu("PlanetX", self.about_action)
            self.about_action = None
        if self.toolbar is not None:
            self.iface.mainWindow().removeToolBar(self.toolbar)
            self.toolbar.deleteLater()
            self.toolbar = None
        # Загрузчик мог поставить обработчик запросов QGIS. Он общий для
        # всех запросов и после выгрузки плагина оставаться не должен.
        import sys
        loader = sys.modules.get(__package__ + ".net.loader")
        if loader is not None:
            loader.remove_user_agent()
        journal.stop()

    def about(self):
        from .ui.about import show_about
        show_about(self.iface.mainWindow())

    def run(self):
        # Импорт здесь, а не наверху модуля. PyOpenGL и виджет OpenGL
        # нужны только при открытии окна, меню работает и без них.
        try:
            from .ui.window import GlobeWindow
        except ImportError as error:
            from qgis.PyQt.QtWidgets import QMessageBox
            QMessageBox.warning(
                self.iface.mainWindow(), "PlanetX",
                tr("Для глобуса нужен модуль Python {name}. В этой сборке "
                   "QGIS его нет.", name=error.name or str(error)))
            return
        self._drop_deleted()
        if self.window is None:
            window = GlobeWindow(self.iface.mainWindow())
            window.resize(1600, 930)
            window.closed.connect(
                lambda window=window: self._window_gone(window))
            self.window = window
            journal.note(tr("Окно глобуса открыто."))
        # Окно глобуса принадлежит главному окну QGIS, своей кнопки
        # на панели задач Windows у него нет. Свёрнутое окно
        # разворачивается значком PlanetX, show() одно этого не делает.
        if self.window.isMinimized():
            self.window.setWindowState(
                self.window.windowState() & ~MINIMIZED)
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()
