# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Транспорт вживую: поезда Финляндии (ui/trains.py), суда Балтики
и самолёты (ui/live.py). Исполнитель строки держит менеджер живых
объектов и шкалу, окну они видны прежними именами (train_manager,
train_legend и другие): их берут меню на глобусе, запись облёта
и режим полёта. Строки реестра каталога (core/rows.py) и исполнители.
"""
from qgis.PyQt.QtCore import QObject

from ..core import aircraft as aircraft_core, trains as trains_core, \
    vessels as vessels_core
from ..core.rows import Row
from ..i18n import tr


class LiveRow(QObject):
    """Строка живых объектов: менеджер, шкала, опрос щелчком."""

    shown_key = None
    key = ""
    attr = ""  # имя менеджера и шкалы у окна: <attr>_manager, _legend
    core = None  # модуль ядра с ATTRIBUTION

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.manager = self.make_manager(window)
        self.manager.changed.connect(window._show_attribution)
        self.legend = self.make_legend(window.view)
        self.legend.hide()
        window.legend_panel.add(self.legend)
        self.legend.closer = lambda: window.set_extra(self.key, False)
        setattr(window, self.attr + "_manager", self.manager)
        setattr(window, self.attr + "_legend", self.legend)

    def title(self):
        return ""

    def turn(self, key, on):
        self.manager.set_on(on)
        self.legend.setVisible(on)
        return True

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(window.extras.get(self.key))
                               and window.planet.earth)

    def credits(self):
        manager = self.manager
        if manager.on and manager.count() and self.window.planet.earth:
            return [self.core.ATTRIBUTION]
        return []

    def identify(self, lat, lon, tolerance=0.0):
        return []  # объекты опрашиваются по пикселю, pick

    def pick(self, px, py):
        from .identify import Group
        features = [(name, values, None)
                    for name, values in self.manager.identify(px, py)]
        return [(Group(self.title()), features)] if features else []

    def credit(self):
        return None

    def close(self):
        self.manager.close()


class TrainRow(LiveRow):
    key, attr, core = "trains", "train", trains_core

    @staticmethod
    def make_manager(window):
        from .trains import TrainManager
        return TrainManager(window)

    @staticmethod
    def make_legend(view):
        from .legend import TrainLegend
        return TrainLegend(view)

    def title(self):
        return tr("Поезда")


class VesselRow(LiveRow):
    key, attr, core = "vessels", "vessel", vessels_core

    @staticmethod
    def make_manager(window):
        from .live import VesselManager
        return VesselManager(window)

    @staticmethod
    def make_legend(view):
        from .legend import VesselLegend
        return VesselLegend(view)

    def title(self):
        return tr("Суда")


class AircraftRow(LiveRow):
    key, attr, core = "aircraft", "aircraft", aircraft_core

    @staticmethod
    def make_manager(window):
        from .live import AircraftManager
        return AircraftManager(window)

    @staticmethod
    def make_legend(view):
        from .legend import AircraftLegend
        return AircraftLegend(view)

    def title(self):
        return tr("Самолёты")


ROWS = (
    Row("trains", "transport", lambda: (tr("Поезда Финляндии"), tr(
        "Поезда Финляндии в реальном времени по открытым данным "
        "Fintraffic Digitraffic, положения обновляются раз в 10 с. "
        "Издалека поезд - точка цвета категории с номером, вблизи - "
        "модель вагона, которая едет по рельсам OpenStreetMap между "
        "обновлениями. Щелчок по поезду показывает вид, номер "
        "и скорость.")), TrainRow, source="Fintraffic Digitraffic",
        words=("поезда", "железная дорога", "финляндия", "vr", "trains",
               "railway", "finland", "digitraffic"),
        after="geoid"),
    Row("vessels", "transport", lambda: (tr("Суда Балтики"), tr(
        "Суда Финского и Ботнического заливов и Балтики у Финляндии "
        "по сигналам AIS, открытые данные Fintraffic Digitraffic, "
        "положения раз в 20 с. Издалека судно - точка цвета типа "
        "с названием, вблизи - условная модель своей длины, которая "
        "идёт своим курсом. Щелчок показывает тип, позывной, "
        "назначение, размеры и скорость.")), VesselRow,
        source="Fintraffic Digitraffic, AIS",
        words=("суда", "корабли", "ais", "балтика", "морской трафик",
               "ships", "vessels", "marine traffic"),
        after="trains"),
    Row("aircraft", "transport", lambda: (tr("Самолёты"), tr(
        "Самолёты по сигналам ADS-B сети добровольцев adsb.lol "
        "в круге у точки взгляда, раз в 10 с. Самолёт в воздухе "
        "стоит на своей высоте, вблизи - условная модель размера "
        "своей категории с креном. Щелчок показывает позывной, тип, "
        "бортовой номер, высоту и скорость. Над Россией приёмников "
        "сети почти нет.")), AircraftRow, source="adsb.lol",
        words=("самолёты", "самолеты", "авиация", "рейсы", "ads-b",
               "flightradar", "aircraft", "planes", "flights"),
        after="vessels"),
)
