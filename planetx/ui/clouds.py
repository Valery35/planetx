# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака NASA GIBS (core/clouds.py) - слой вида «clouds», прозрачность
по белизне снимка. Строка реестра каталога (core/rows.py) и исполнитель.
"""
import time

from qgis.PyQt.QtCore import QObject

from ..core import clouds
from ..core.rows import Row
from ..i18n import tr

KEY = "clouds"


class CloudsTool(QObject):
    """Строка «Облака»."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window

    shown_key = None

    def turn(self, key, on):
        self.window._set_gibs("clouds", on)
        return True

    def export_jobs(self, path):
        """«В проект QGIS…» - картинка WMS GIBS по рамке вида на день
        снимка: (слой, день, файл)."""
        return [(clouds.LAYER, clouds.image_date(time.time()), path)]

    @staticmethod
    def thumb(tile, base):
        """Превью каталога, как на глобусе: прозрачность по белизне
        снимка поверх подложки."""
        from ..core import themes
        from .nasamaps import _over, _rgba_array, _rgba_image
        if tile is not None:
            tile = _rgba_image(clouds.cloud_rgba(
                _rgba_array(tile), themes.THUMB_TILE), premultiplied=True)
        return _over(base, tile)

    def credits(self):
        return [clouds.ATTRIBUTION] \
            if "clouds" in self.window.gibs_loaders else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "sky", lambda: (tr("Облака"), tr(
        "Облака по снимкам VIIRS из NASA GIBS за последние "
        "полные сутки. Они лежат полупрозрачной пеленой "
        "поверх снимка. Снег и лёд тоже белые и остаются "
        "видны.")), CloudsTool, source="NASA GIBS, VIIRS",
        words=("облачность", "clouds"), fades=("clouds",),
        preview=lambda: clouds.url_template(time.time()), after="air"),
)
