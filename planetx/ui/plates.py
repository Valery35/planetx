# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Границы литосферных плит PB2002 (core/plates.py), файл
data/plates.json. Линии - слой QGIS в памяти в картинке наложения,
названия плит - надписи глобуса. Строка реестра каталога (core/rows.py)
и исполнитель.
"""
import os
import time

from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import plates as plates_core
from ..core.places import Place as MarkPlace
from ..core.rows import Row
from ..i18n import tr

KEY = "plates"
DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "plates.json")
# Номера надписей названий плит, отрицательные - свои метки глобуса.
MARK_BASE = -300000


def plate_names():
    """Подписи групп и классов границ плит на языке интерфейса."""
    return ({"divergent": tr("Раздвиг плит"),
             "transform": tr("Сдвиг плит"),
             "convergent": tr("Схождение плит")},
            {"OSR": tr("Океанический спрединговый хребет"),
             "CRB": tr("Континентальный рифт"),
             "OTF": tr("Океанический трансформный разлом"),
             "CTF": tr("Континентальный трансформный разлом"),
             "SUB": tr("Зона субдукции"),
             "OCB": tr("Океаническая граница схождения"),
             "CCB": tr("Континентальная коллизия")})


class PlateTool(QObject):
    """Данные границ и слой QGIS, читаются при первом включении."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.data = None
        self.layer = None

    shown_key = None
    # Слой - над векторной основой, сразу под слоями проекта.
    overlay_top = True

    def on(self):
        window = self.window
        return window.planet.earth \
            and bool(getattr(window, "extras", {}).get(KEY)) \
            and self.data is not None

    def turn(self, key, on):
        from ..net.overlay import plate_layer
        window = self.window
        if on and self.data is None:
            try:
                with open(DATA, encoding="utf-8") as fh:
                    self.data = plates_core.Plates.from_text(fh.read())
            except (OSError, ValueError) as error:
                journal.note("plates: {}".format(error))
                window.message = (tr("Границы плит не прочитаны: {error}",
                                     error=str(error)), time.monotonic())
                window._show_state()
                return False
        if on and self.layer is None:
            self.layer = plate_layer(self.data, plate_names()[0])
        window.view.plate_marks = [
            MarkPlace(MARK_BASE - n, p.name, "plate", 1, p.lat, p.lon)
            for n, p in enumerate(self.data.plates)] \
            if on and self.data is not None else []
        window._update_overlay(keep=True)
        window.view.update()
        return True

    def overlay_layers(self):
        if not self.on() or self.layer is None:
            return []
        self.layer.setOpacity(self.window._layer_opacity(KEY))
        return [self.layer]

    def qgis_layers(self):
        return {KEY: [self.layer]}

    def export_parts(self, key, title):
        return [(KEY, self.layer, title)]

    def credits(self):
        return [plates_core.ATTRIBUTION] if self.on() else []

    def identify(self, lat, lon, tolerance=0.0):
        """Граница плит у точки щелчка, когда строка включена."""
        from .identify import Group
        if not self.on():
            return []
        found = plates_core.nearest(self.data, lat, lon, tolerance)
        if found is None:
            return []
        groups, classes = plate_names()
        values = [(tr("Тип"), classes.get(found.code, found.code)),
                  (tr("Плиты"), found.pair),
                  (tr("Скорость"), tr("{value} мм/год",
                                      value="{:.0f}".format(found.speed)))]
        return [(Group(tr("Граница плит")), [
            (groups[plates_core.group(found.code)], values, None)])]

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "seismic", lambda: (tr("Границы плит"), tr(
        "Границы литосферных плит по модели PB2002. Красные - "
        "раздвиг плит на хребтах и рифтах, зелёные - сдвиг "
        "по трансформным разломам, синие - схождение "
        "в зонах субдукции и коллизии. Названия плит стоят "
        "надписями. Тип границы и скорость плит показывает "
        "окно «Объекты».")), PlateTool,
        source="PB2002", words=("тектоника", "плиты", "plates",
                                "tectonics"),
        after="iscgem", qgis_layer=True),
)
