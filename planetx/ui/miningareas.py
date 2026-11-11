# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Контуры горных разработок Maus и соавторы 2022 (core/mining.py).
GeoPackage около 25 МБ скачивается в профиль при первом включении,
дальше читается без сети. Контуры - слой QGIS в картинке наложения.
Строка реестра каталога (core/rows.py) и исполнитель.
"""
import os
import time

from qgis.PyQt.QtCore import QObject
from qgis.core import QgsApplication

from .. import journal
from ..core import mining
from ..core.rows import Row
from ..i18n import tr
from .overpass import brief_error

KEY = "mining"


def file_path():
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, mining.POLYGONS_FILE)


class MiningTool(QObject):
    """Слой контуров и его загрузка."""

    shown_key = None

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.layer = None
        self._reply = None

    def on(self):
        window = self.window
        return window.planet.earth \
            and bool(getattr(window, "extras", {}).get(KEY)) \
            and self.layer is not None

    def turn(self, key, on):
        """Первое включение скачивает GeoPackage в профиль."""
        window = self.window
        if not on:
            if self._reply is not None:
                reply, self._reply = self._reply, None
                reply.abort()
                window.view.data_pending = max(
                    0, window.view.data_pending - 1)
            window._update_overlay(keep=True)
            return True
        if self.layer is None:
            path = file_path()
            if os.path.exists(path):
                self._open(path)
            elif self._reply is None:
                from ..net.overlay import fetch_bytes
                self._reply = fetch_bytes(mining.POLYGONS_URL, self._arrived)
                window.view.data_pending += 1
                window.message = (tr("Загрузка контуров горных разработок, "
                                     "около 25 МБ…"), time.monotonic())
                window._show_state()
                return True
        window._update_overlay(keep=True)
        return True

    def _arrived(self, data, error):
        window = self.window
        if self._reply is None:
            return  # снят выключением строки
        window.view.data_pending = max(0, window.view.data_pending - 1)
        self._reply = None
        if data is None:
            journal.note("mining polygons: {}".format(brief_error(error)))
            window.message = (tr("Контуры горных разработок не загрузились, "
                                 "проверьте сеть и включите строку снова."),
                              time.monotonic())
            window._show_state()
            return
        path = file_path()
        try:
            with open(path + ".part", "wb") as stream:
                stream.write(data)
            os.replace(path + ".part", path)
        except OSError as error:
            window.message = (tr("Контуры горных разработок не записаны: "
                                 "{error}", error=str(error)),
                              time.monotonic())
            window._show_state()
            return
        self._open(path)
        if window.extras.get(KEY):
            window._update_overlay(keep=True)
            window._show_attribution()

    def _open(self, path):
        """Слой QGIS контуров из файла профиля со своим стилем."""
        from qgis.core import QgsFillSymbol, QgsVectorLayer
        from .nasamaps import MINING_FILL, MINING_LINE
        window = self.window
        layer = QgsVectorLayer(path, "Mining areas", "ogr")
        if not layer.isValid():
            window.message = (tr("Файл контуров горных разработок не "
                                 "читается: {path}", path=path),
                              time.monotonic())
            window._show_state()
            return
        symbol = QgsFillSymbol.createSimple({
            "color": "{},{},{},{}".format(*MINING_FILL),
            "outline_color": "{},{},{},{}".format(*MINING_LINE),
            "outline_width": "0.35"})
        layer.renderer().setSymbol(symbol)
        self.layer = layer

    def overlay_layers(self):
        if not self.on():
            return []
        self.layer.setOpacity(self.window._layer_opacity(KEY))
        return [self.layer]

    def qgis_layers(self):
        return {KEY: [self.layer]}

    def export_parts(self, key, title):
        return [(KEY, self.layer, title)]

    def credits(self):
        return [mining.POLYGONS_ATTRIBUTION] if self.on() else []

    def identify(self, lat, lon, tolerance=0.0):
        """Контур горной разработки под точкой щелчка."""
        from qgis.core import (QgsFeatureRequest, QgsGeometry, QgsPointXY,
                               QgsRectangle)
        from .identify import Group
        if not self.on():
            return []
        point = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
        step = 0.0005
        request = QgsFeatureRequest().setFilterRect(QgsRectangle(
            lon - step, lat - step, lon + step, lat + step))
        features = []
        for feature in self.layer.getFeatures(request):
            if not feature.geometry().intersects(point):
                continue
            values = [(tr("Страна"), str(feature["COUNTRY_NAME"] or "")),
                      (tr("Площадь"), tr("{value} км²", value="{:.2f}".format(
                          float(feature["AREA"] or 0.0)))),
                      (tr("Набор"), "Maus et al. 2022, PANGAEA")]
            features.append((tr("Горная разработка"), values, None))
        return [(Group(tr("Горные разработки")), features)] \
            if features else []

    def credit(self):
        return None

    def close(self):
        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.abort()


ROWS = (
    Row(KEY, "resources", lambda: (tr("Горные разработки"), tr(
        "Контуры карьеров, отвалов, хвостохранилищ и промплощадок "
        "мира по снимкам Sentinel-2 2019 года - около 45 тысяч "
        "участков, Maus и соавторы, 2022. Щелчок по контуру "
        "показывает страну и площадь. Первое включение скачивает "
        "около 25 МБ.")), MiningTool,
        source="Maus et al. 2022",
        words=("карьеры", "отвалы", "горные работы", "mining", "pits"),
        after="deposits", qgis_layer=True),
)
