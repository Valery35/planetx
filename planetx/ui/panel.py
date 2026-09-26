# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Левая панель окна глобуса: координаты, список, строка состояния.

Устройство взято из 3D-сцены Isoliner3D. Строки списка:

- «Глобус» - двойной щелчок открывает свойства вида;
- «Подложка · имя» - меню выбора подложки, двойной щелчок - свойства;
- «Слои проекта» - флажок, под ним слои проекта, как на карте QGIS,
  с типом слоя. У слоя в меню «Подлететь».

Панель только показывает и сообщает сигналами, решает окно.
"""
from qgis.core import QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (QHBoxLayout, QLabel, QLineEdit, QMenu,
                                 QPushButton, QTreeWidget, QTreeWidgetItem,
                                 QVBoxLayout, QWidget)

from ..i18n import tr
from ..qt_compat import enum, enum_int

# Роли данных строки: вид строки и значение - номер подложки или слой.
KIND_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
VALUE_ROLE = KIND_ROLE + 1
CHECKABLE = enum(Qt, "ItemFlag", "ItemIsUserCheckable")
CHECKED = enum(Qt, "CheckState", "Checked")
UNCHECKED = enum(Qt, "CheckState", "Unchecked")
GLOBE, BASEMAP, PROJECT, LAYER = range(4)


def layer_kind(layer):
    """Тип слоя словами, как в списке 3D-сцены Isoliner3D."""
    if isinstance(layer, QgsRasterLayer):
        return tr("растр")
    if isinstance(layer, QgsVectorLayer):
        # Номер Qgis.GeometryType: 0 точки, 1 линии, 2 полигоны.
        kinds = {0: tr("точки"), 1: tr("линии"), 2: tr("полигоны")}
        return kinds.get(enum_int(layer.geometryType()), tr("таблица"))
    return tr("слой")


class LayerPanel(QWidget):

    fly_text = pyqtSignal(str)
    properties_requested = pyqtSignal()
    basemap_chosen = pyqtSignal(int)
    project_toggled = pyqtSignal(bool)
    fly_to_layer = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.place = QLineEdit(self)
        self.place.setPlaceholderText(tr("Широта, долгота"))
        self.place.setToolTip(tr(
            "Координаты в градусах, например 58.0105, 56.2294.\n"
            "Enter запускает перелёт. Перелёт прерывается мышью."))
        self.place.returnPressed.connect(
            lambda: self.fly_text.emit(self.place.text()))
        go = QPushButton(tr("Лететь"), self)
        go.clicked.connect(lambda: self.fly_text.emit(self.place.text()))
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.place, 1)
        top.addWidget(go, 0)

        self.tree = QTreeWidget(self)
        self.tree.setHeaderHidden(True)
        self.tree.setRootIsDecorated(True)
        self.tree.setContextMenuPolicy(
            enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.tree.customContextMenuRequested.connect(self._menu)
        self.tree.itemDoubleClicked.connect(self._double_clicked)
        self.tree.itemChanged.connect(self._changed)
        self.globe = self._row(tr("Глобус"), GLOBE, tr(
            "Свойства вида: двойной щелчок"))
        bold = QFont(self.globe.font(0))
        bold.setBold(True)
        self.globe.setFont(0, bold)
        self.basemap = self._row("", BASEMAP, tr(
            "Подложка: выбор в меню по правой кнопке, двойной щелчок "
            "открывает свойства вида"))
        self.project = self._row(tr("Слои проекта"), PROJECT, tr(
            "Включённые слои проекта поверх подложки, в том же порядке, "
            "что на карте QGIS. Подписей нет. Когда слои меняются, глобус "
            "обновляет их кнопкой «Обновить слои» или сам, если в "
            "свойствах вида включено автоматическое обновление."),
            checkable=True)
        self.sources = []

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.status.setTextInteractionFlags(
            enum(Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(top)
        layout.addWidget(self.tree, 1)
        layout.addWidget(self.status, 0)

    def _row(self, text, kind, tip, checkable=False, parent=None):
        item = QTreeWidgetItem(parent or self.tree, [text])
        item.setData(0, KIND_ROLE, kind)
        item.setToolTip(0, tip)
        if checkable:
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, UNCHECKED)
        return item

    # Состояние от окна. Сигналы при этом не идут.

    def set_sources(self, names, index):
        self.sources = list(names)
        self.set_basemap(index)

    def set_basemap(self, index):
        self.tree.blockSignals(True)
        self.basemap.setText(0, tr("Подложка · {name}",
                                   name=self.sources[index]))
        self.basemap.setData(0, VALUE_ROLE, index)
        self.tree.blockSignals(False)

    def set_checked(self, item, on):
        self.tree.blockSignals(True)
        item.setCheckState(0, CHECKED if on else UNCHECKED)
        self.tree.blockSignals(False)

    def set_layers(self, layers):
        """Слои проекта под строкой «Слои проекта», сверху вниз."""
        self.tree.blockSignals(True)
        self.project.takeChildren()
        for layer in layers:
            item = self._row(tr("{name} · {kind}", name=layer.name(),
                                kind=layer_kind(layer)), LAYER,
                             tr("Подлететь: меню по правой кнопке"),
                             parent=self.project)
            item.setData(0, VALUE_ROLE, layer.id())
        self.project.setExpanded(True)
        self.tree.blockSignals(False)

    def set_status(self, text):
        self.status.setText(text)

    # События списка.

    def _changed(self, item, column):
        kind = item.data(0, KIND_ROLE)
        if kind == PROJECT:
            self.project_toggled.emit(item.checkState(0) == CHECKED)

    def _double_clicked(self, item, column):
        if item.data(0, KIND_ROLE) in (GLOBE, BASEMAP):
            self.properties_requested.emit()

    def _menu(self, point):
        item = self.tree.itemAt(point)
        if item is None:
            return
        kind = item.data(0, KIND_ROLE)
        menu = QMenu(self)
        if kind == BASEMAP:
            current = item.data(0, VALUE_ROLE)
            for index, name in enumerate(self.sources):
                action = menu.addAction(name)
                action.setCheckable(True)
                action.setChecked(index == current)
                action.triggered.connect(
                    lambda _=False, index=index: self.basemap_chosen.emit(
                        index))
        elif kind == LAYER:
            from qgis.core import QgsProject
            layer = QgsProject.instance().mapLayer(
                item.data(0, VALUE_ROLE))
            if layer is not None:
                menu.addAction(tr("Подлететь")).triggered.connect(
                    lambda _=False, layer=layer:
                    self.fly_to_layer.emit(layer))
        else:
            menu.addAction(tr("Свойства вида…")).triggered.connect(
                self.properties_requested)
        menu.exec(self.tree.viewport().mapToGlobal(point))
