# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Электростанции WRI Global Power Plant Database (core/plants.py).
Архив около 4 МБ скачивается при первом включении, разбор - в рабочем
потоке, итог - файл профиля. Точки рисует вид (render.quakes.PlantPoints,
поле вида plants). Строка реестра каталога (core/rows.py) и исполнитель.
"""
import os
import time
import zipfile

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsApplication

from .. import journal
from ..core import plants as plants_core
from ..core.rows import Row
from ..i18n import tr
from ..net.gdalnet import executor
from .deposits import parse_plants
from .overpass import brief_error
from .volcanoes import PICK_MOST, PICK_SHARE, nearest_points

KEY = "plants"
POLL = 200  # опрос задачи разбора, мс


def file_path():
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "power_plants.npz")


class PlantTool(QObject):
    """База электростанций, её загрузка и шкала видов топлива."""

    shown_key = None

    def __init__(self, window):
        from .legend import PlantLegend
        super().__init__(window)
        self.window = window
        self.data = None
        self._reply = None
        self._job = None
        self.legend = PlantLegend(window.view)
        self.legend.hide()
        self.legend.closer = lambda: window.set_extra(KEY, False)
        window.legend_panel.add(self.legend)

    @property
    def layer(self):
        return self.window.view.plants

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(window.extras.get(KEY))
                               and window.planet.earth)

    def busy(self):
        return self._reply is not None or self._job is not None

    def turn(self, key, on):
        """Первое включение скачивает архив около 4 МБ."""
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
                    self.data = plants_core.load(path)
                except (OSError, ValueError, KeyError) as error:
                    journal.note("plants file: {}".format(error))
        if self.data is not None:
            self._place()
            return True
        if self.busy():
            return True
        from ..net.overlay import fetch_bytes
        self._reply = fetch_bytes(plants_core.URL, self._arrived)
        window.view.data_pending += 1
        window.message = (tr("Загрузка электростанций WRI, около 4 МБ…"),
                          time.monotonic())
        window._show_state()
        return True

    def _arrived(self, data, error):
        window = self.window
        window.view.data_pending = max(0, window.view.data_pending - 1)
        if self._reply is None:
            return  # снят выключением строки
        self._reply = None
        if data is None:
            journal.note("plants: {}".format(brief_error(error)))
            window.message = (tr("Электростанции не загрузились, проверьте "
                                 "сеть и включите строку снова."),
                              time.monotonic())
            window._show_state()
            return
        self._job = executor("deposits", 1).submit(
            parse_plants, bytes(data), file_path())
        window.view.data_pending += 1
        QTimer.singleShot(POLL, self._poll)

    def _poll(self):
        job = self._job
        if job is None:
            return
        if not job.done():
            QTimer.singleShot(POLL, self._poll)
            return
        window = self.window
        self._job = None
        window.view.data_pending = max(0, window.view.data_pending - 1)
        try:
            self.data = job.result()
        except (OSError, ValueError, KeyError, StopIteration,
                zipfile.BadZipFile) as error:
            journal.note("plants parse: {}".format(error))
            window.message = (tr("Электростанции не разобраны."),
                              time.monotonic())
            window._show_state()
            return
        window.message = (tr("Электростанций {count}.",
                             count=len(self.data)), time.monotonic())
        window._show_state()
        self._place()

    def _place(self):
        window = self.window
        on = window.extras.get(KEY, False) and window.planet.earth
        self.layer.set_plants(self.data if on else None,
                              window.view.store.scale,
                              window._surface_ground)
        window._show_attribution()
        window.view.update()

    def credits(self):
        return [plants_core.ATTRIBUTION] \
            if self.layer.data is not None else []

    def identify(self, lat, lon, tolerance=0.0):
        return []  # точки опрашиваются по пикселю, pick

    def pick(self, px, py):
        """Электростанции у точки щелчка на экране, не больше
        PICK_MOST."""
        from .globe.base import IDENTIFY_PIXELS
        from .identify import Group
        from .legend import fuel_names
        view = self.window.view
        data = self.layer.data
        radius = IDENTIFY_PIXELS * view.devicePixelRatioF() * PICK_SHARE
        fuels = fuel_names()
        keys = [f[0] for f in plants_core.FUELS]
        features = []
        for record in nearest_points(view, self.layer, px, py, radius,
                                     PICK_MOST):
            name, country, fuel, year, owner, url = \
                (data.text(record) + [""] * 6)[:6]
            values = [(tr("Мощность"), tr("{value} МВт", value="{:g}".format(
                round(float(data.capacity[record]), 1)))),
                      (tr("Топливо"), "{} ({})".format(
                          fuels[keys[int(data.fuel[record])]], fuel))]
            if year:
                values.append((tr("Год ввода"), year))
            if owner:
                values.append((tr("Владелец"), owner))
            if country:
                values.append((tr("Страна"), country))
            values.append((tr("Набор"), "WRI Global Power Plant Database"))
            if url:
                values.append((tr("Источник"), url))
            features.append((name, values, None))
        return [(Group(tr("Электростанции")), features)] if features else []

    @staticmethod
    def point_rows(layer, index):
        """Поля и значения точек index для «В проект QGIS…»."""
        fields = [(name, "str") for name in (
            "name", "country", "fuel", "year", "owner",
            "source")] + [("capacity_mw", "real")]
        rows = [(layer.data.text(int(layer.order[n])) + [""] * 6)[:6]
                + [float(layer.data.capacity[layer.order[n]])]
                for n in index]
        return fields, rows

    def credit(self):
        return None

    def close(self):
        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.abort()


ROWS = (
    Row(KEY, "infra", lambda: (tr("Электростанции"), tr(
        "Около 35 тысяч электростанций мира из базы WRI Global Power "
        "Plant Database, данные на 2021 год. Цвет - вид топлива, "
        "размер - мощность. Щелчок по точке показывает название, "
        "мощность, год ввода и владельца. У части станций место "
        "в базе указано неверно. Первое включение скачивает около "
        "4 МБ.")), PlantTool,
        source="WRI",
        words=("электростанции", "энергетика", "тэц", "гэс", "аэс",
               "power plants"),
        after="osm_mines", points="plants"),
)
