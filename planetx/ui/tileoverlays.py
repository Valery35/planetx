# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложения тайлов (core/tileoverlays.py) - морские знаки и карты
Waymarked Trails. Слой XYZ QGIS в картинке наложения над векторной
основой, включать можно несколько сразу. Строки реестра каталога
(core/rows.py) и исполнитель.
"""
import time

from qgis.core import QgsRasterLayer
from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import tileoverlays
from ..core.rows import Row
from ..i18n import tr


class TileOverlayTool(QObject):
    """Слои XYZ наложений: ключ строки - слой QGIS."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.layers = {}

    shown_key = None  # общего слоя вида у наложений нет

    def _title(self, key):
        return ROW_NAMES[key]()[0]

    def turn(self, key, on):
        """Тайлы читает QGIS при отрисовке наложения, только видимые."""
        window = self.window
        if on and key not in self.layers:
            layer = QgsRasterLayer(tileoverlays.layer_source(key),
                                   self._title(key), "wms")
            if not layer.isValid():
                journal.note("tile overlay {}: invalid".format(key))
                window.message = (tr("Наложение «{title}» не открыто.",
                                     title=self._title(key)),
                                  time.monotonic())
                window._show_state()
                return False
            self.layers[key] = layer
        window._update_overlay(keep=True)
        window.view.update()
        return True

    def shown(self):
        window = self.window
        return [key for key in self.layers
                if window.planet.earth
                and getattr(window, "extras", {}).get(key)]

    def overlay_layers(self):
        """Слои картинки наложения с непрозрачностью строк."""
        out = []
        for key in self.shown():
            layer = self.layers[key]
            layer.setOpacity(self.window._layer_opacity(key))
            out.append(layer)
        return out

    def qgis_layers(self):
        return {key: [layer] for key, layer in self.layers.items()}

    def credits(self):
        return [(tileoverlays.OVERLAYS[key].attribution,
                 tileoverlays.OVERLAYS[key].terms) for key in self.shown()]

    def export(self, key, title):
        """В проект слоем XYZ, файл не пишется."""
        from . import export as layer_export
        overlay = tileoverlays.OVERLAYS[key]
        layer = layer_export.add_xyz(overlay.url, title, overlay.max_level,
                                     overlay.attribution)
        return None if layer is None else 1

    def identify(self, lat, lon):
        return []

    def credit(self):
        return None

    def close(self):
        pass


WAYMARKED = "Waymarked Trails"
ROW_NAMES = {
    "sea_marks": lambda: (tr("Морские знаки"), tr(
        "Морские навигационные знаки OpenSeaMap - буи, маяки, створы, "
        "фарватеры и якорные стоянки. Знаки видны вблизи, с уровня "
        "карты около 1:500 000. Карта не заменяет навигационную.")),
    "hiking": lambda: (tr("Пешие маршруты"), tr(
        "Размеченные пешие маршруты из OpenStreetMap по Waymarked "
        "Trails - международные, национальные, региональные "
        "и местные тропы цветом своего уровня.")),
    "cycling": lambda: (tr("Велосипедные маршруты"), tr(
        "Размеченные велосипедные маршруты из OpenStreetMap по "
        "Waymarked Trails - от международных веломаршрутов до "
        "местных.")),
    "mtb": lambda: (tr("Маршруты для горного велосипеда"), tr(
        "Размеченные маршруты для горного велосипеда из OpenStreetMap "
        "по Waymarked Trails.")),
    "slopes": lambda: (tr("Горнолыжные трассы"), tr(
        "Горнолыжные трассы и лыжные маршруты из OpenStreetMap по "
        "Waymarked Trails - спуски цветом сложности и равнинные "
        "лыжни.")),
    "riding": lambda: (tr("Конные маршруты"), tr(
        "Размеченные конные маршруты из OpenStreetMap по Waymarked "
        "Trails.")),
}
_ROWS = (
    # ключ, строка перед ней, источник, цвета превью, слова поиска
    ("sea_marks", "aspect", "OpenSeaMap",
     ((230, 40, 40), (40, 160, 60), (250, 220, 40)),
     ("морские знаки", "буи", "маяки", "фарватер", "openseamap",
      "sea marks", "buoys")),
    ("hiking", "sea_marks", WAYMARKED, ((200, 30, 30), (240, 240, 240)),
     ("пешие маршруты", "тропы", "туризм", "походы", "hiking", "trails")),
    ("cycling", "hiking", WAYMARKED, ((120, 60, 200), (240, 240, 240)),
     ("велосипед", "веломаршруты", "cycling", "bike routes")),
    ("mtb", "cycling", WAYMARKED, ((200, 120, 30), (240, 240, 240)),
     ("горный велосипед", "маунтинбайк", "mtb", "mountain bike")),
    ("slopes", "mtb", WAYMARKED,
     ((40, 90, 200), (220, 30, 30), (240, 240, 240)),
     ("горные лыжи", "горнолыжные трассы", "лыжни", "лыжи", "ski slopes",
      "pistes")),
    ("riding", "slopes", WAYMARKED, ((150, 90, 40), (240, 240, 240)),
     ("конные маршруты", "лошади", "riding", "horse")),
)
ROWS = tuple(Row(key, "tiles", ROW_NAMES[key], TileOverlayTool,
                 source=source, colors=colors, words=words, after=after,
                 qgis_layer=True)
             for key, after, source, colors, words in _ROWS)
