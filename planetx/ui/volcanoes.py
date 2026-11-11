# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вулканы голоцена Global Volcanism Program (core/volcanoes.py). Список
около 2 МБ скачивается при первом включении, итог - файл профиля. Точки
рисует вид (render.quakes.VolcanoPoints, поле вида volcanoes). Строка
реестра каталога (core/rows.py) и исполнитель.
"""
import os
import time

import numpy as np
from qgis.PyQt.QtCore import QObject
from qgis.core import QgsApplication

from .. import journal
from ..core import volcanoes as volcanoes_core
from ..core.rows import Row
from ..i18n import tr
from .overpass import brief_error

KEY = "volcanoes"
# Опрос щелчком: не больше точек у пикселя, радиус - в допусках опроса.
PICK_MOST = 10
PICK_SHARE = 2.0


def file_path():
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "volcanoes.npz")


def nearest_points(view, layer, px, py, radius, most):
    """Номера записей точек слоя вида layer у пикселя кадра px, py не
    дальше radius пикселей, ближние первыми."""
    if layer.data is None:
        return []
    eye = np.asarray(view.camera.eye, dtype=np.float64)
    seen = layer.visible(eye)
    if not len(seen):
        return []
    pixels, front = view.camera.project(layer.focus[seen])
    gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
    near = np.nonzero(front & (gap <= radius))[0]
    near = near[np.argsort(gap[near])][:most]
    return [int(layer.order[seen[n]]) for n in near]


class VolcanoTool(QObject):
    """Список вулканов, его загрузка и шкала времени извержений."""

    shown_key = None

    def __init__(self, window):
        from .legend import VolcanoLegend
        super().__init__(window)
        self.window = window
        self.data = None
        self._reply = None
        self.legend = VolcanoLegend(window.view)
        self.legend.hide()
        self.legend.closer = lambda: window.set_extra(KEY, False)
        window.legend_panel.add(self.legend)

    @property
    def layer(self):
        return self.window.view.volcanoes

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(window.extras.get(KEY))
                               and window.planet.earth)

    def turn(self, key, on):
        """Первое включение скачивает список GVP около 2 МБ."""
        window = self.window
        self.legend.setVisible(on and window.planet.earth)
        if not on:
            if self._reply is not None:
                reply, self._reply = self._reply, None
                reply.abort()
            self._place()
            return True
        if self.data is None:
            path = file_path()
            if os.path.exists(path):
                try:
                    self.data = volcanoes_core.load(path)
                except (OSError, ValueError, KeyError) as error:
                    journal.note("volcanoes file: {}".format(error))
        if self.data is not None:
            self._place()
            return True
        if self._reply is not None:
            return True
        from ..net.overlay import fetch_bytes
        self._reply = fetch_bytes(volcanoes_core.URL, self._arrived)
        window.view.data_pending += 1
        window.message = (tr("Загрузка списка вулканов GVP, около 2 МБ…"),
                          time.monotonic())
        window._show_state()
        return True

    def _arrived(self, data, error):
        window = self.window
        window.view.data_pending = max(0, window.view.data_pending - 1)
        if self._reply is None:
            return  # снят выключением строки
        self._reply = None
        found = None
        if data is not None:
            try:
                # Около 1200 строк - разбор в главном потоке, десятки мс.
                found = volcanoes_core.parse(bytes(data))
                volcanoes_core.save(found, file_path())
            except (OSError, ValueError, KeyError) as problem:
                error = str(problem)
                found = None
        if found is None:
            journal.note("volcanoes: {}".format(brief_error(error or "")))
            window.message = (tr("Список вулканов не загрузился, проверьте "
                                 "сеть и включите строку снова."),
                              time.monotonic())
            window._show_state()
            return
        self.data = found
        window.message = (tr("Вулканов {count}.", count=len(found)),
                          time.monotonic())
        window._show_state()
        self._place()

    def _place(self):
        window = self.window
        on = window.extras.get(KEY, False) and window.planet.earth
        self.layer.set_volcanoes(self.data if on else None,
                                 window.view.store.scale,
                                 window._surface_ground)
        window._show_attribution()
        window.view.update()

    def credits(self):
        return [volcanoes_core.ATTRIBUTION] \
            if self.layer.data is not None else []

    def identify(self, lat, lon, tolerance=0.0):
        return []  # точки опрашиваются по пикселю, pick

    def pick(self, px, py):
        """Вулканы у точки щелчка на экране, не больше PICK_MOST."""
        from .globe.base import IDENTIFY_PIXELS
        from .identify import Group
        view = self.window.view
        data = self.layer.data
        radius = IDENTIFY_PIXELS * view.devicePixelRatioF() * PICK_SHARE
        features = []
        for record in nearest_points(view, self.layer, px, py, radius,
                                     PICK_MOST):
            number, name, kind, country, setting, evidence = \
                (data.text(record) + [""] * 6)[:6]
            values = []
            if kind:
                values.append((tr("Тип"), kind))
            year = float(data.last[record])
            if np.isfinite(year):
                year = int(year)
                values.append((tr("Последнее извержение"), str(year)
                               if year > 0 else tr("{year} до н. э.",
                                                   year=-year)))
            else:
                values.append((tr("Последнее извержение"),
                               tr("дата неизвестна")))
            height = float(data.elevation[record])
            if np.isfinite(height):
                values.append((tr("Высота"), tr("{value} м",
                                                value="{:.0f}".format(
                                                    height))))
            if country:
                values.append((tr("Страна"), country))
            if setting:
                values.append((tr("Обстановка"), setting))
            if evidence:
                values.append((tr("Достоверность"), evidence))
            values.append((tr("Набор"), "Global Volcanism Program"))
            if number:
                values.append((tr("Источник"),
                               volcanoes_core.PAGE.format(number)))
            features.append((name, values, None))
        return [(Group(tr("Вулканы")), features)] if features else []

    @staticmethod
    def point_rows(layer, index):
        """Поля и значения точек index для «В проект QGIS…»."""
        fields = [(name, "str") for name in (
            "number", "name", "type", "country", "setting",
            "evidence")] + [("elevation_m", "real"),
                            ("last_eruption", "real")]
        rows = [(layer.data.text(int(layer.order[n])) + [""] * 6)[:6]
                + [float(layer.data.elevation[layer.order[n]]),
                   float(layer.data.last[layer.order[n]])]
                for n in index]
        return fields, rows

    def credit(self):
        return None

    def close(self):
        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.abort()


ROWS = (
    Row(KEY, "seismic", lambda: (tr("Вулканы"), tr(
        "Около 1200 вулканов, извергавшихся за последние 12 тысяч лет, "
        "по списку Global Volcanism Program Смитсоновского института. "
        "Цвет - время последнего извержения, размер - высота вулкана. "
        "Щелчок по точке показывает тип вулкана, год последнего "
        "извержения, тектоническую обстановку и страницу вулкана на "
        "сайте GVP. Первое включение скачивает около 2 МБ.")), VolcanoTool,
        source="Smithsonian GVP",
        colors=((230, 40, 30), (245, 140, 40), (240, 210, 70)),
        words=("вулканы", "вулкан", "извержения", "gvp", "volcanoes",
               "volcano"),
        after="platemotion", points="volcanoes"),
)
