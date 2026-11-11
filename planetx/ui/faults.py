# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Активные разломы GEM Global Active Faults (core/faults.py). Файл
базы около 11 МБ скачивается в профиль при первом включении, разбор -
в рабочем потоке. Линии - слой QGIS в памяти в картинке наложения над
границами плит. Строка реестра каталога (core/rows.py) и исполнитель.
"""
import os
import time

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsApplication

from .. import journal
from ..core import faults as faults_core
from ..core.rows import Row
from ..i18n import tr
from ..net.gdalnet import executor
from .legend import FaultLegend, fault_names
from .overpass import brief_error

KEY = "faults"
# Опрос задачи разбора, мс.
POLL = 200


def _read(path, data):
    """Рабочий поток: байты базы разломов в файл профиля, если они
    пришли, затем разбор файла (core.faults.parse)."""
    if data is not None:
        part = path + ".part"
        with open(part, "wb") as fh:
            fh.write(data)
        os.replace(part, path)
    with open(path, "rb") as fh:
        return faults_core.parse(fh.read())


def file_path():
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, faults_core.FILE)


class FaultTool(QObject):
    """Данные разломов, слой QGIS и шкала видов смещения."""

    shown_key = None
    # Слой - над векторной основой, сразу под слоями проекта.
    overlay_top = True
    # Линии опрашиваются и щелчком без режима опроса.
    click_lines = True

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.data = None
        self.layer = None
        self._reply = None
        self._job = None
        self.legend = FaultLegend(window.view)
        self.legend.hide()
        self.legend.closer = lambda: window.set_extra(KEY, False)
        window.legend_panel.add(self.legend)

    def on(self):
        window = self.window
        return window.planet.earth \
            and bool(getattr(window, "extras", {}).get(KEY)) \
            and self.layer is not None

    def sync_legend(self):
        """Шкала видна при включённой строке на Земле."""
        window = self.window
        self.legend.setVisible(bool(window.extras.get(KEY))
                               and window.planet.earth)

    def turn(self, key, on):
        """Первое включение скачивает файл базы около 11 МБ в профиль,
        разбор - в рабочем потоке."""
        window = self.window
        self.legend.setVisible(on and window.planet.earth)
        if not on:
            if self._reply is not None:
                reply, self._reply = self._reply, None
                reply.abort()
            window._update_overlay(keep=True)
            return True
        if self.layer is not None:
            window._update_overlay(keep=True)
            return True
        if self._reply is not None or self._job is not None:
            return True
        path = file_path()
        if os.path.exists(path):
            self._parse(path, None)
            return True
        from ..net.overlay import fetch_bytes
        self._reply = fetch_bytes(faults_core.URL, self._arrived)
        window.view.data_pending += 1
        window.message = (tr("Загрузка активных разломов GEM, около 11 МБ…"),
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
            journal.note("faults: {}".format(brief_error(error)))
            window.message = (tr("Разломы не загрузились, проверьте сеть "
                                 "и включите строку снова."),
                              time.monotonic())
            window._show_state()
            return
        self._parse(file_path(), bytes(data))

    def _parse(self, path, data):
        """Разбор файла базы в рабочем потоке. data - пришедшие байты,
        они записываются в path, None - файл path уже есть."""
        self._job = executor("deposits", 1).submit(_read, path, data)
        self.window.view.data_pending += 1
        QTimer.singleShot(POLL, self._poll)

    def _poll(self):
        job = self._job
        if job is None:
            return
        if not job.done():
            QTimer.singleShot(POLL, self._poll)
            return
        from ..net.overlay import fault_layer
        window = self.window
        self._job = None
        window.view.data_pending = max(0, window.view.data_pending - 1)
        try:
            self.data = job.result()
        except (OSError, ValueError, KeyError, TypeError) as error:
            journal.note("faults parse: {}".format(error))
            window.message = (tr("Разломы не разобраны."), time.monotonic())
            window._show_state()
            return
        self.layer = fault_layer(self.data, fault_names())
        window.message = (tr("Разломов {count}.", count=len(self.data)),
                          time.monotonic())
        window._show_state()
        if window.extras.get(KEY):
            window._update_overlay(keep=True)
        window._show_attribution()
        window.view.update()

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
        return [faults_core.ATTRIBUTION] if self.on() else []

    def identify(self, lat, lon, tolerance=0.0):
        """Активный разлом у точки щелчка, когда строка включена."""
        from .identify import Group
        window = self.window
        if not (window.planet.earth and window.extras.get(KEY)
                and self.data is not None):
            return []
        found = faults_core.nearest(self.data, lat, lon, tolerance)
        if found is None:
            return []
        values = [(tr("Вид смещения"), fault_names()[found.kind])]
        if found.slip_type:
            values.append((tr("Запись в базе"), found.slip_type))
        if found.rate is not None:
            values.append((tr("Скорость смещения"), tr(
                "{value} мм/год", value="{:g}".format(found.rate))))
        if found.dip is not None:
            dip = "{:g}°".format(found.dip)
            if found.dip_dir:
                dip += " ({})".format(found.dip_dir)
            values.append((tr("Падение"), dip))
        if found.catalog:
            values.append((tr("Каталог"), found.catalog))
        values.append((tr("Набор"), "GEM Global Active Faults"))
        return [(Group(tr("Активные разломы")), [
            (found.name or tr("Без названия"), values, None)])]

    def credit(self):
        return None

    def close(self):
        if self._reply is not None:
            reply, self._reply = self._reply, None
            reply.abort()


ROWS = (
    Row(KEY, "seismic", lambda: (tr("Активные разломы"), tr(
        "Около 13.7 тысячи активных разломов мира по базе GEM Global "
        "Active Faults, сведённой из региональных каталогов. "
        "Цвет показывает вид смещения. Это сброс, взброс или надвиг, "
        "сдвиг, срединный хребет и складка. Щелчок по линии показывает "
        "название, вид "
        "смещения, скорость в мм/год, падение и каталог-источник. "
        "Первое включение скачивает около 11 МБ.")), FaultTool,
        source="GEM Global Active Faults",
        colors=((225, 45, 40), (40, 120, 230), (30, 170, 70)),
        words=("разломы", "активные разломы", "сбросы", "надвиги",
               "сдвиги", "gem", "faults", "active faults"),
        after="plates", qgis_layer=True),
)
