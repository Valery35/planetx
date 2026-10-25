# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек лидара по сети у точки: запрос каталогов IGN LiDAR HD
и USGS 3DEP (core/lidarnet.py) и слои облаков в проект QGIS.

Каталоги спрашиваются оба сразу, точку покрывает один из них. Слой -
QgsPointCloudLayer файла COPC по адресу в сети, группа «PlanetX - облака
точек лидара», он отмечен на глобусе. Точки на глобус читает
ui/pointcloud.py, тот же путь, что у облаков с диска.
"""
from qgis.core import QgsPointCloudLayer, QgsProject
from qgis.PyQt.QtCore import QObject, pyqtSignal

from .. import journal
from ..core import lidarnet
from ..i18n import tr
from ..net.overlay import fetch_bytes, post_json

class LidarSearch(QObject):
    """Поиск плиток у точки, сигнал found(плитки, текст отказа)."""

    found = pyqtSignal(object, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.replies = {}
        self.tiles = []
        self.errors = []
        self.point = None

    def search(self, lat, lon):
        """Оба каталога у точки, прежний поиск снимается."""
        self.abort()
        self.point = (lat, lon)
        self.tiles = []
        self.errors = []
        box = lidarnet.box_around(lat, lon)
        self.replies[lidarnet.IGN] = fetch_bytes(
            lidarnet.ign_url(box),
            lambda data, error: self._done(lidarnet.IGN, data, error))
        self.replies[lidarnet.USGS] = post_json(
            lidarnet.PC_SEARCH, {"Content-Type": "application/json"},
            lidarnet.pc_body(box),
            lambda data, error: self._done(lidarnet.USGS, data, error))

    def busy(self):
        return bool(self.replies)

    def abort(self):
        replies, self.replies = self.replies, {}
        for reply in replies.values():
            reply.abort()

    def _done(self, source, data, error):
        if self.replies.pop(source, None) is None:
            return
        try:
            if source == lidarnet.IGN:
                self.tiles += lidarnet.parse_ign(data) if data else []
            else:
                self.tiles += lidarnet.parse_pc(data) if data else []
        except (ValueError, TypeError, KeyError) as error_parse:
            error = str(error_parse)
        if error:
            journal.note("lidar {}: {}".format(source, error))
            self.errors.append(error)
        if self.replies:
            return
        lat, lon = self.point
        chosen = lidarnet.choose(self.tiles, lat, lon)
        self.found.emit(chosen, "" if chosen else "; ".join(self.errors))


def add_layers(tiles, key=""):
    """Слои облаков плиток в группу проекта, новые сверху. Тот же файл
    заново не добавляется. Возвращает номера слоёв плиток и плитки, чей
    слой не открылся. Сервер IGN 25 октября 2026 года отказывал в части
    первых запросов к файлу подряд, повтор через секунды проходил."""
    project = QgsProject.instance()
    known = {node.layer().source().split("?")[0]: node.layerId()
             for node in _group().findLayers() if node.layer() is not None}
    ids = []
    failed = []
    for tile in tiles:
        if tile.url in known:
            ids.append(known[tile.url])
            continue
        source = lidarnet.with_key(tile.url, key)
        name = "{} {}".format(tile.name, tile.date).strip()
        # Открытие слоя ждёт сервер с циклом событий внутри, группа
        # за это время могла уйти из проекта - она ищется после.
        layer = QgsPointCloudLayer(source, name, "copc")
        if not layer.isValid():
            journal.note("lidar layer not valid {}: {}".format(
                tile.url, layer.error().summary()[-200:]))
            failed.append(tile)
            continue
        meta = layer.metadata()
        meta.setRights([lidarnet.CREDITS[tile.source][0]])
        layer.setMetadata(meta)
        project.addMapLayer(layer, False)
        _group().addLayer(layer)
        ids.append(layer.id())
    return ids, failed


def _group():
    """Группа облаков лидара вверху проекта, нет - заводится."""
    root = QgsProject.instance().layerTreeRoot()
    title = tr("PlanetX - облака точек лидара")
    group = root.findGroup(title)
    return group if group is not None else root.insertGroup(0, title)