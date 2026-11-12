# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Пожары NASA FIRMS (core/fires.py): сводка VIIRS NOAA-20 за 24 часа
загружается при каждом включении. Очаги рисует вид (render.quakes.
FirePoints, поле вида fires). Пожары входят в общий выбор тем, их
карточку в каталоге даёт выбор тем, поэтому строка реестра стоит вне
каталога слоёв (catalog=False). Строка реестра и исполнитель.
"""
import datetime
import math
import time

import numpy as np
from qgis.PyQt.QtCore import QObject

from ..core import fires as fires_core, quakes as quakes_core, when
from ..core.rows import Row
from ..i18n import tr

KEY = "fires"
# Очагов у щелчка в окне «Объекты» не больше.
PICK_MOST = 20


def _stamp(seconds):
    if seconds is None or not math.isfinite(seconds):
        return ""
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    return (epoch + datetime.timedelta(seconds=seconds)).strftime(
        "%Y-%m-%d %H:%M")


class FireTool(QObject):
    """Сводка пожаров, её загрузка и очаги на виде."""

    shown_key = None
    # Выгрузка точек «В проект QGIS…» берёт только промежуток шкалы.
    point_window = True

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.data = None
        self.reply = None

    @property
    def legend(self):
        return self.window.fire_legend

    @property
    def layer(self):
        return self.window.view.fires

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(window.extras.get(KEY))
                               and window.planet.earth
                               and window.view.sky_view is None)

    def turn(self, key, on):
        """Пожары - строка группы «Планета огня» в общем выборе тем.
        Включённые пожары снимают тему."""
        window = self.window
        if on and (window.theme_key or window.extras.get("temperature")):
            window.set_theme(KEY)
        self.sync_legend()
        window._place_attribution()
        if not on:
            if self.reply is not None:
                self.reply.abort()
            self.reply = None
            self.place()
            return True
        if self.reply is None:
            from ..net.overlay import fetch_bytes
            self.reply = fetch_bytes(fires_core.FEED, self._done,
                                     prefer_cache=False)
            window.view.data_pending += 1
        return True

    def _done(self, data, error):
        window = self.window
        if self.reply is not None:
            window.view.data_pending = max(0, window.view.data_pending - 1)
        self.reply = None
        if data is not None:
            self.data = fires_core.parse(data.decode("utf-8", "replace"))
        else:
            window.message = (tr("Сводка пожаров не загрузилась: {error}",
                                 error=error), time.monotonic())
            window._show_state()
        self.place()

    def place(self):
        """Очаги на глобус по нынешнему масштабу рельефа."""
        window = self.window
        on = window.extras.get(KEY, False) and window.planet.earth
        self.layer.set_fires(self.data if on else None,
                             window.view.store.scale, window._surface_ground)
        window._update_timebar()
        self.time_changed()
        window._show_attribution()
        window.view.update()

    def relief_changed(self):
        self.place()

    def time_changed(self):
        self.layer.window = getattr(self.window, "_time_range", None)

    def time_marks(self):
        """Охват шкалы времени: первый и последний снимок сводки."""
        data = self.layer.fires
        span = fires_core.span(data) if data is not None else None
        return [when.stamp(when.text(t)) for t in span] \
            if span is not None else []

    def time_events(self):
        return bool(self.window.extras.get(KEY)
                    and self.layer.fires is not None)

    def credits(self):
        return [fires_core.ATTRIBUTION] \
            if self.layer.fires is not None else []

    def identify(self, lat, lon, tolerance=0.0):
        return []  # очаги опрашиваются по пикселю, pick

    def pick(self, px, py):
        """Очаги пожаров у точки щелчка на экране, не больше
        PICK_MOST."""
        from .globe.base import IDENTIFY_PIXELS
        from .identify import Group
        layer = self.layer
        data = layer.fires
        if data is None:
            return []
        view = self.window.view
        eye = np.asarray(view.camera.eye, dtype=np.float64)
        shown = quakes_core.facing(eye, layer.focus, layer.lats,
                                   layer.lons) \
            & quakes_core.in_window(layer.times, layer.window)
        radius = IDENTIFY_PIXELS * view.devicePixelRatioF() * 2.0
        pixels, front = view.camera.project(layer.focus)
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        near = np.nonzero(front & shown & (gap <= radius))[0]
        near = near[np.argsort(gap[near])][:PICK_MOST]
        features = []
        for n in near:
            n = int(n)
            values = [(tr("Мощность излучения"), tr(
                "{value} МВт", value="{:.1f}".format(data.frp[n])))]
            if not np.isnan(data.time[n]):
                values.append((tr("Время снимка, UTC"),
                               when.text(float(data.time[n]))))
            if data.confidence[n]:
                values.append((tr("Достоверность"), data.confidence[n]))
            values.append((tr("Снимок"), tr("ночной") if data.night[n]
                           else tr("дневной")))
            features.append(("{:.4f}, {:.4f}".format(data.lat[n],
                                                     data.lon[n]),
                             values, None))
        return [(Group(tr("Пожары")), features)] if features else []

    @staticmethod
    def point_rows(layer, index):
        """Поля и значения очагов index для «В проект QGIS…»."""
        fires = layer.fires
        fields = [("frp_mw", "real"), ("time", "str"),
                  ("confidence", "str")]
        rows = [(float(fires.frp[n]), _stamp(float(fires.time[n])),
                 fires.confidence[n]) for n in index]
        return fields, rows

    def credit(self):
        return None

    def close(self):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()


ROWS = (
    Row(KEY, "fire", lambda: (tr("Пожары"), tr(
        "Очаги пожаров за последние 24 часа по снимкам VIIRS спутника "
        "NOAA-20, сводка NASA FIRMS. Цвет и размер точки показывают "
        "мощность излучения.")), FireTool,
        words=("пожары", "огонь", "fires", "firms"),
        points="fires", catalog=False),
)
