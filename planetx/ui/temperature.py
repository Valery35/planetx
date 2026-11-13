# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Температура суши и моря NASA GIBS (core/temperature.py) - слои вида
«sea» и «land» со шкалой в углу вида. Температура - карта витрины
в общем выборе тем, как пожары, её карточку в каталоге даёт выбор тем
(catalog=False). Строка реестра (core/rows.py) и исполнитель.
"""
import os

from qgis.PyQt.QtCore import QObject

from ..core import basemap, temperature
from ..core.mipmap import mip_chain
from ..core.rows import Row
from ..i18n import tr

KEY = "temperature"
# Слои вида: имя - слой GIBS.
LAYERS = (("sea", temperature.SEA), ("land", temperature.LAND))


def prepare(key, rgba):
    """Работа рабочего потока для тайла температуры: раскраска GIBS
    с непрозрачностью и уровни мипмапов."""
    return mip_chain(temperature.overlay_rgba(rgba))


class TemperatureTool(QObject):
    """Строка «Температура» и шкала суши и моря."""

    shown_key = None

    def __init__(self, window):
        from .legend import TemperatureLegend
        super().__init__(window)
        self.window = window
        self.legend = TemperatureLegend(window.view)
        self.legend.hide()
        # Крестик на шкале убирает карту витрины.
        self.legend.closer = lambda: window.set_theme("")
        window.legend_panel.add(self.legend)

    def turn(self, key, on):
        """Температура в общем выборе карт витрины: включённая снимает
        тему и пожары."""
        window = self.window
        if on and (window.theme_key or window.extras.get("fires")):
            window.set_theme(KEY)
        window._mark_gallery()
        for name, layer in LAYERS:
            window._set_gibs(name, on, (basemap.Source(
                "NASA GIBS", temperature.url_template(layer),
                temperature.MAX_LEVEL, temperature.ATTRIBUTION,
                builtin=True), prepare) if on else None)
        self.sync_legend()
        window._place_attribution()
        return True

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(window.extras.get(KEY))
                               and window.planet.earth
                               and window.view.sky_view is None)

    def export_jobs(self, path):
        """«В проект QGIS…» - две картинки WMS GIBS по рамке вида: море
        и суша, последний готовый день."""
        stem = os.path.splitext(path)[0]
        return [(temperature.SEA, None, stem + "_sea.tif"),
                (temperature.LAND, None, stem + "_land.tif")]

    def credits(self):
        return [temperature.ATTRIBUTION] \
            if "sea" in self.window.gibs_loaders else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "weather", lambda: (tr("Температура поверхности"), tr(
        "Температура суши днём по MODIS за 8 суток и моря по GHRSST MUR "
        "за сутки, данные NASA GIBS.")), TemperatureTool,
        source="NASA GIBS", words=("температура", "жара", "temperature"),
        fades=("sea", "land"), catalog=False),
)
