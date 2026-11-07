# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подводные кабели OSM (core/cables.py), файл data/cables.json. Линии -
слой QGIS в памяти в картинке наложения. Строка реестра каталога
(core/rows.py) и исполнитель.
"""
import os
import time

from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import cables as cables_core
from ..core import infra
from ..core.rows import Row
from ..i18n import tr

KEY = "cables"
DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "cables.json")


def cable_names():
    return {"telecom": tr("Линия связи"), "power": tr("Силовой кабель")}


class CableTool(QObject):
    """Данные кабелей и слой QGIS, читаются при первом включении."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.data = None
        self.layer = None

    shown_key = None

    def on(self):
        window = self.window
        return window.planet.earth \
            and bool(getattr(window, "extras", {}).get(KEY)) \
            and self.layer is not None

    def turn(self, key, on):
        from ..net.overlay import cable_layer
        window = self.window
        if on and self.data is None:
            try:
                with open(DATA, encoding="utf-8") as fh:
                    self.data = cables_core.Cables.from_text(fh.read())
            except (OSError, ValueError) as error:
                journal.note("cables: {}".format(error))
                window.message = (tr("Подводные кабели не прочитаны."),
                                  time.monotonic())
                window._show_state()
                return False
        if on and self.layer is None:
            self.layer = cable_layer(self.data, cable_names())
        window._update_overlay(keep=True)
        window.view.update()
        return True

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
        return [cables_core.ATTRIBUTION] if self.on() else []

    def identify(self, lat, lon, tolerance=0.0):
        """Подводный кабель у точки щелчка, когда строка включена."""
        from .identify import Group
        window = self.window
        if not (window.planet.earth and window.extras.get(KEY)
                and self.data is not None):
            return []
        found = cables_core.nearest(self.data, lat, lon, tolerance)
        if found is None:
            return []
        values = [(tr("Вид"), cable_names()[found.kind])]
        if found.operator:
            values.append((tr("Владелец"), found.operator))
        kv = infra.kilovolts(found.voltage)
        if kv is not None:
            values.append((tr("Напряжение"), tr(
                "{value} кВ", value="{:g}".format(kv))))
        values.append((tr("Объект OSM"), "https://www.openstreetmap.org/"
                       + found.osm))
        return [(Group(tr("Подводные кабели")), [
            (found.name or tr("Без названия"), values, None)])]

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "infra", lambda: (tr("Подводные кабели"), tr(
        "Подводные линии связи (бирюзовые) и силовые кабели "
        "(лиловые) из OpenStreetMap, видны с любой высоты. В OSM "
        "нанесена часть кабелей мира, больше всего в Атлантике "
        "и у Европы. Щелчок по линии показывает название, владельца "
        "и ссылку на объект OpenStreetMap.")), CableTool,
        source="OpenStreetMap", colors=((60, 200, 200), (170, 110, 220)),
        words=("подводные кабели", "кабели", "submarine cables"),
        after="osm_mines", qgis_layer=True),
)
