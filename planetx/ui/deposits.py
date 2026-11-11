# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Месторождения USGS и шахты OSM: файл в профиле QGIS, разбор в рабочем
потоке, строки реестра каталога (core/rows.py) и исполнитель.

Архивы USGS скачиваются один раз, разбор (core.deposits.parse) идёт
в постоянном пуле «deposits» (net/gdalnet.py), итог пишется файлом
PlanetX/deposits.npz профиля, как файлы групп спутников. Это отступление
от правила «своего кэша на диске плагин не заводит», написанного для
тайлов: архив MRDS - 23 МБ, ответ USGS без заголовков кэширования.
"""
import os
import time
import zipfile

from qgis.PyQt.QtCore import QObject, QTimer
from qgis.core import QgsApplication

from .. import journal
from ..core import deposits, mining, plants
from ..core.rows import Row
from ..i18n import tr
from ..net.gdalnet import executor
from .volcanoes import PICK_SHARE, nearest_points


def deposits_path():
    """Файл месторождений в профиле QGIS."""
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX")
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "deposits.npz")


def parse_deposits(mrds, major, minfac, path):
    """Разбор архивов и запись файла path. Рабочий поток, Qt не
    трогает. Возвращает core.deposits.Deposits."""
    data = deposits.parse(mrds, major, minfac)
    deposits.save(data, path)
    return data


def parse_plants(data, path):
    """Разбор архива электростанций WRI и запись файла path. Рабочий
    поток, Qt не трогает. Возвращает core.plants.Plants."""
    found = plants.parse(data)
    plants.save(found, path)
    return found


KEY = "deposits"
OSM = "osm_mines"
POLL = 200  # опрос задачи разбора, мс
DEPOSITS_MOST = 20  # точек окна «Объекты» у пикселя


class DepositTool(QObject):
    """Строки «Месторождения» (архивы USGS) и «Шахты и карьеры OSM»
    (тайлы Overpass у вида): точки видов deposits и osm_mines, общая шкала
    групп полезных ископаемых."""

    shown_key = None

    def __init__(self, window):
        from .legend import DepositLegend
        from .overpass import OverpassTiles
        super().__init__(window)
        self.window = window
        self.data = None
        self._replies = {}
        self._bytes = {}
        self._job = None
        self.tiles = OverpassTiles(window.view, "mines", mining.query,
                                   mining.parse, self._place_osm,
                                   window._overpass_failed)
        self.legend = DepositLegend(window.view)
        self.legend.hide()
        self.legend.closer = self._close
        window.legend_panel.add(self.legend)

    def _close(self):
        """Крестик шкалы убирает месторождения и шахты OSM."""
        self.window.set_extra(KEY, False)
        self.window.set_extra(OSM, False)

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(
            window.planet.earth and window.view.sky_view is None
            and (window.extras.get(KEY) or window.extras.get(OSM))))

    def busy(self):
        return bool(self._replies) or self._job is not None

    def turn(self, key, on):
        self.sync_legend()
        if key == OSM:
            if not on:
                self.tiles.stop()
            self._place_osm()
            if on:
                self.window._want_overpass()
            return True
        return self._turn_deposits(on)

    def want(self, lat, lon, altitude):
        if self.window.extras.get(OSM):
            self.tiles.want(lat, lon, altitude)

    # Месторождения USGS.

    def _turn_deposits(self, on):
        """Первое включение скачивает архивы MRDS, крупных месторождений
        и рудников мира, разбор - в рабочем потоке, итог - файл профиля
        (core/deposits.py). Дальше файл читается без сети."""
        window = self.window
        if not on:
            for reply in list(self._replies.values()):
                reply.abort()
            self._replies.clear()
            self.relief_changed()
            return True
        if self.data is None:
            path = deposits_path()
            if os.path.exists(path):
                try:
                    self.data = deposits.load(path)
                except (OSError, ValueError, KeyError) as error:
                    journal.note("deposits file: {}".format(error))
        if self.data is not None:
            self.relief_changed()
            return True
        if self.busy():
            return True
        from ..net.overlay import fetch_bytes
        self._bytes = {}
        for name, url in (("mrds", deposits.MRDS_URL),
                          ("major", deposits.MAJOR_URL),
                          ("minfac", deposits.MINFAC_URL)):
            self._replies[name] = fetch_bytes(
                url, lambda data, error, name=name:
                self._arrived(name, data, error))
            window.view.data_pending += 1
        window.message = (tr("Загрузка месторождений USGS, около 25 МБ…"),
                          time.monotonic())
        window._show_state()
        return True

    def _arrived(self, name, data, error):
        window = self.window
        if self._replies.pop(name, None) is not None:
            window.view.data_pending = max(0, window.view.data_pending - 1)
        if data is None:
            for reply in list(self._replies.values()):
                reply.abort()
            self._replies.clear()
            window.message = (tr("Месторождения не загрузились: {error}",
                                 error=error), time.monotonic())
            window._show_state()
            return
        self._bytes[name] = bytes(data)
        if self._replies:
            return
        mrds = self._bytes.pop("mrds", None)
        major = self._bytes.pop("major", None)
        minfac = self._bytes.pop("minfac", None)
        self._job = executor("deposits", 1).submit(
            parse_deposits, mrds, major, minfac, deposits_path())
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
            window.message = (tr("Месторождения не разобраны: {error}",
                                 error=error), time.monotonic())
            window._show_state()
            return
        self.relief_changed()

    def relief_changed(self):
        """Месторождения на глобус по нынешнему масштабу рельефа."""
        window = self.window
        on = window.extras.get(KEY, False) and window.planet.earth
        window.view.deposits.set_deposits(
            self.data if on else None, window.view.store.scale,
            window._surface_ground)
        window._show_attribution()
        window.view.update()

    # Шахты и карьеры OSM.

    def _place_osm(self):
        window = self.window
        on = window.extras.get(OSM, False) and window.planet.earth
        items = self.tiles.all_items()
        window.view.osm_mines.set_deposits(
            mining.to_deposits(items) if on and items else None,
            window.view.store.scale, window._surface_ground)
        window._show_attribution()
        window.view.update()

    def credits(self):
        view = self.window.view
        return ([deposits.ATTRIBUTION] if view.deposits.data is not None
                else []) + ([mining.OSM_ATTRIBUTION]
                            if view.osm_mines.data is not None else [])

    def identify(self, lat, lon, tolerance=0.0):
        return []  # точки опрашиваются по пикселю, pick

    def pick(self, px, py):
        return self._pick(px, py, False) + self._pick(px, py, True)

    def _pick(self, px, py, osm):
        """Месторождения у точки щелчка на экране, не больше
        DEPOSITS_MOST. osm - шахты и карьеры OpenStreetMap."""
        from .globe.base import IDENTIFY_PIXELS
        from .identify import Group
        from .legend import deposit_group_names, mine_kind_names
        view = self.window.view
        layer = view.osm_mines if osm else view.deposits
        data = layer.data
        radius = IDENTIFY_PIXELS * view.devicePixelRatioF() * PICK_SHARE
        names = deposit_group_names()
        keys = [g[0] for g in deposits.GROUPS] + ["other"]
        features = []
        for record in nearest_points(view, layer, px, py, radius,
                                     DEPOSITS_MOST):
            name, country, commodities, kind, status, number, operator, \
                capacity, precision, osm_id = \
                (data.text(record) + [""] * 10)[:10]
            if osm:
                kind = mine_kind_names().get(kind, kind)
            values = [(tr("Полезные ископаемые"), commodities),
                      (tr("Группа"), names[keys[int(data.group[record])]])]
            if kind:
                values.append((tr("Тип"), kind))
            if status:
                values.append((tr("Стадия или модель"), status))
            if operator:
                values.append((tr("Оператор"), operator))
            if capacity:
                values.append((tr("Мощность (год сведений)"), capacity))
            if country:
                values.append((tr("Страна"), country))
            if precision == "A":
                values.append((tr("Место"), tr("примерное, по району")))
            source = "OpenStreetMap" if osm else tr(
                "Крупные месторождения мира, USGS OFR 2005-1294") \
                if data.major[record] else tr(
                    "Рудники и заводы мира, USGS mineral operations") \
                if data.facility[record] else "USGS MRDS"
            values.append((tr("Набор"), source))
            if osm_id:
                values.append((tr("Объект OpenStreetMap"),
                               mining.OSM_PAGE.format(*osm_id.split("/"))))
            if number:
                values.append((tr("Запись USGS"),
                               deposits.MRDS_PAGE.format(number)))
            features.append((name or "{:.4f}, {:.4f}".format(
                data.lat[record], data.lon[record]), values, None))
        title = tr("Шахты и карьеры OSM") if osm else tr("Месторождения")
        return [(Group(title), features)] if features else []

    @staticmethod
    def point_rows(layer, index):
        """Поля и значения точек index для «В проект QGIS…»."""
        fields = [(name, "str") for name in (
            "name", "country", "commodities", "type", "status",
            "record", "operator", "capacity", "precision", "osm")]
        rows = [(layer.data.text(int(layer.order[n])) + [""] * 10)[:10]
                for n in index]
        return fields, rows

    def credit(self):
        return None

    def close(self):
        for reply in list(self._replies.values()):
            reply.abort()
        self._replies.clear()
        self.tiles.stop()


ROWS = (
    Row(KEY, "resources", lambda: (tr("Месторождения"), tr(
        "Месторождения, рудники и проявления полезных ископаемых "
        "USGS - база MRDS, около 300 тысяч точек, больше всего в США, "
        "3 тысячи крупных месторождений мира и 6.5 тысячи рудников "
        "и заводов мира с оператором и мощностью. Цвет - группа "
        "полезного ископаемого, большая точка - крупное "
        "месторождение, рудник или завод. Щелчок по точке показывает "
        "название, ископаемые, тип и ссылку на запись USGS. Первое "
        "включение скачивает около 25 МБ.")), DepositTool,
        source="USGS",
        words=("полезные ископаемые", "руды", "рудники", "usgs", "mrds",
               "minerals", "deposits"),
        after="geoid", points="deposits"),
    Row(OSM, "resources", lambda: (tr("Шахты и карьеры OSM"), tr(
        "Шахты, рудники, стволы и карьеры из OpenStreetMap с "
        "названиями и ископаемым. Загружаются по месту вида, когда "
        "камера ниже 150 км. Цвет - группа ископаемого, как у "
        "месторождений. Щелчок по точке показывает название, "
        "оператора и ссылку на объект OpenStreetMap.")), DepositTool,
        source="OpenStreetMap",
        words=("шахты", "карьеры", "mines", "quarries"),
        after="mining", points="osm_mines"),
)
