# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Течения: струйки и заливка скорости NOAA CoastWatch по дням
(ui/flow.py, менеджер струек общий с ветром погоды). Строка реестра
каталога (core/rows.py) и исполнитель.
"""
import numpy as np
from qgis.PyQt.QtCore import QObject

from ..core import flow as flow_core
from ..core import when
from ..core.rows import Row
from ..i18n import tr
from .flow import CURRENTS_ATTRIBUTION

KEY = "currents"


class CurrentsTool(QObject):
    """Строка «Течения» и её шкала."""

    def __init__(self, window):
        from .legend import CurrentLegend
        super().__init__(window)
        self.window = window
        self.legend = CurrentLegend(window.view)
        self.legend.hide()
        window.legend_panel.add(self.legend)
        self.legend.closer = lambda: window.set_extra(KEY, False)

    shown_key = None

    def on(self):
        window = self.window
        return bool(getattr(window, "extras", {}).get(KEY)) \
            and window.planet.earth

    def flow(self):
        return getattr(self.window, "flow", None)

    def turn(self, key, on):
        """Струйки течений, заливка скорости и шкала."""
        window = self.window
        on = on and window.planet.earth
        window.flow.moment = window.theme_moment()
        window.flow.set_currents(on)
        self.legend.setVisible(on)
        window._update_timebar()
        return True

    def sync_legend(self):
        self.legend.setVisible(self.on())

    def time_marks(self):
        """Ряд дней NOAA с 2017 года - на шкале времени."""
        flow = self.flow()
        if flow is None or not self.on() or flow.currents_span() is None:
            return []
        return [when.stamp(when.text(t)) for t in flow.currents_span()]

    def export_picture(self, key, title, path, box):
        """«В проект QGIS…» - скорость и составляющие U, V сеткой
        GeoTIFF со шкалой заливки."""
        from . import export as layer_export
        flow = self.flow()
        grid = flow.fields[KEY] if flow is not None else None
        if grid is None:
            return None
        speed = np.hypot(grid.u, grid.v)
        count = layer_export.write_grid(
            path, [speed, grid.u, grid.v], grid.west, grid.north,
            grid.step, box)
        if count is None or layer_export.add_raster(
                path, "{} {}".format(title, flow.currents_day),
                flow_core.CURRENT_STOPS, CURRENTS_ATTRIBUTION[0]) is None:
            return None
        return count

    def credits(self):
        flow = self.flow()
        return [CURRENTS_ATTRIBUTION] if self.on() and flow is not None \
            and flow.fields[KEY] is not None else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "water", lambda: (tr("Течения"), tr(
        "Поверхностные течения океана белыми бегущими струйками над "
        "заливкой скорости. Геострофические течения NOAA CoastWatch по "
        "спутниковой альтиметрии за последние готовые сутки, сетка "
        "0.5°. Первое включение за сеанс скачивает около 4 МБ.")),
        CurrentsTool, source="NOAA CoastWatch",
        colors=tuple(c for _, c in flow_core.CURRENT_STOPS),
        words=("течения", "океан", "гольфстрим", "currents", "ocean"),
        fades=("currents",), flow="currents", after="geoid"),
)
