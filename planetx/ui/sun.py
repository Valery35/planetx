# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Солнце (core/sun.py) - свет рельефа, зданий и атмосферы на момент
шкалы времени, огни городов NASA Black Marble на ночной стороне (слой
вида «lights») и тени в кадре (render/shadowmap.py, пункт «Тени» меню
строки). Строка реестра (core/rows.py) и исполнитель.
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer

from ..core import basemap, sun as sun_core
from ..core.rows import Row
from ..i18n import tr

KEY = "sun"
SHADOWS_KEY = "PlanetX/sun_shadows"  # тени в кадре, по умолчанию да
SUN_PERIOD = 60000  # мс между пересчётами солнца по часам компьютера


class SunTool(QObject):
    """Направление на солнце в вид, огни городов, часы солнца."""

    shown_key = None

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.lights_on = False
        # Пока строка включена и шкала закрыта, солнце идёт по часам.
        self.timer = QTimer(self)
        self.timer.setInterval(SUN_PERIOD)
        self.timer.timeout.connect(self.update)
        # Пункт «Тени» меню строки.
        panel = window.panel
        panel.sun_shadows = self.shadows()
        window.view.shadows = panel.sun_shadows
        panel.sun_shadows_changed.connect(self.set_shadows)

    @staticmethod
    def shadows():
        """Тени в кадре при строке «Солнце», по умолчанию да."""
        return QgsSettings().value(SHADOWS_KEY, True, type=bool)

    def set_shadows(self, on):
        window = self.window
        QgsSettings().setValue(SHADOWS_KEY, bool(on))
        window.panel.sun_shadows = bool(on)
        window.view.shadows = bool(on)
        window.view.update()

    def on(self):
        # Шкала времени бывает раньше строк раздела «Слои».
        window = self.window
        return bool(getattr(window, "extras", {}).get(KEY)) \
            and window.planet.earth

    def turn(self, key, on):
        self.update()
        self.window._update_timebar()
        return True

    def update(self):
        """Направление на солнце в вид, огни городов при смене."""
        from .globe.base import prepare_lights
        window = self.window
        on = self.on()
        window.view.sun = sun_core.direction(window.sun_time()) \
            if on else None
        if on != self.lights_on:
            self.lights_on = on
            window._set_gibs("lights", on, (basemap.Source(
                "NASA Black Marble", sun_core.LIGHTS_URL,
                sun_core.LIGHTS_LEVEL, sun_core.LIGHTS_ATTRIBUTION,
                builtin=True), prepare_lights) if on else None, cache=True)
        if on and not window.timebar.shown():
            self.timer.start()
        else:
            self.timer.stop()
        window.view.update()

    def time_changed(self):
        self.update()

    def needs_clock(self):
        return self.on()

    @staticmethod
    def thumb(key, tile, base):
        """Превью каталога: подложка с ночной половиной и огнями."""
        from .nasamaps import sun_image
        return sun_image(base, tile)

    def credits(self):
        return [sun_core.LIGHTS_ATTRIBUTION] \
            if "lights" in self.window.gibs_loaders else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        self.timer.stop()


ROWS = (
    Row(KEY, "sky", lambda: (tr("Солнце"), tr(
        "Свет рельефа, зданий и воздуха по положению солнца. "
        "Ночная сторона Земли тёмная. Время солнца - конец "
        "промежутка открытой шкалы времени, без неё - часы "
        "компьютера. Без флажка свет падает с северо-запада, "
        "как на карте рельефа.")), SunTool, source="NASA Black Marble",
        words=("ночь", "день", "освещение", "тень", "огни городов", "sun",
               "night", "city lights"),
        preview=sun_core.LIGHTS_URL),
)
