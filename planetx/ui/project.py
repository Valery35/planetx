# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слои текущего проекта для глобуса и слежение за их изменениями.

В списке глобуса все слои проекта в порядке отрисовки дерева слоёв,
с учётом своего порядка слоёв, если он задан. Какие из них видны
на глобусе, решают отметки списка, они хранятся в проекте. Изменением
считаются порядок, добавление и удаление слоя и перерисовка слоя QGIS.
Перерисовку слой просит при правке данных и стиля.
"""
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QObject, pyqtSignal

ENTRY = "PlanetX"  # запись проекта с настройками глобуса
AUTO_REFRESH = "auto_refresh"  # обновлять глобус без кнопки
SHOWN = "layers"  # номера слоёв, отмеченных в списке глобуса


def map_layers(project=None):
    """Все годные слои проекта сверху вниз, как их рисует карта."""
    project = project or QgsProject.instance()
    return [layer for layer in project.layerTreeRoot().layerOrder()
            if layer.isValid()]


def read_flag(name, default, project=None):
    project = project or QgsProject.instance()
    value, ok = project.readBoolEntry(ENTRY, name, default)
    return bool(value) if ok else default


def write_flag(name, value, project=None):
    project = project or QgsProject.instance()
    project.writeEntryBool(ENTRY, name, bool(value))


def read_shown(project=None):
    """Отмеченные слои из проекта или None, если записи ещё нет."""
    project = project or QgsProject.instance()
    value, ok = project.readListEntry(ENTRY, SHOWN, [])
    return set(value) if ok else None


def write_shown(ids, project=None):
    project = project or QgsProject.instance()
    project.writeEntry(ENTRY, SHOWN, sorted(ids))


class ProjectWatch(QObject):
    """Сигнал changed при любом изменении слоёв проекта.

    Живёт вместе с окном. Связи со слоями и проектом Qt рвёт сам,
    когда объект уничтожается.
    """

    changed = pyqtSignal()
    # Проект открыт заново или очищен, настройки нужно перечитать.
    reloaded = pyqtSignal()
    # Слой переименован: список нужно перерисовать, глобус - нет.
    renamed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        self._wired = set()
        project.layersAdded.connect(self._added)
        project.layersRemoved.connect(self._changed)
        project.readProject.connect(self._reloaded)
        project.cleared.connect(self._reloaded)
        root.layerOrderChanged.connect(self._changed)
        root.customLayerOrderChanged.connect(self._changed)
        root.hasCustomLayerOrderChanged.connect(self._changed)
        self._wire(project.mapLayers().values())

    def _wire(self, layers):
        for layer in layers:
            if layer.id() in self._wired:
                continue
            self._wired.add(layer.id())
            layer.repaintRequested.connect(self._changed)
            layer.nameChanged.connect(self.renamed)

    def _added(self, layers):
        self._wire(layers)
        self.changed.emit()

    def _reloaded(self, *args):
        self._wired.clear()
        self._wire(QgsProject.instance().mapLayers().values())
        self.reloaded.emit()
        self.changed.emit()

    def _changed(self, *args):
        self.changed.emit()
