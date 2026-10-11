# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подводные кабели OpenStreetMap. Без Qt.

Просьба автора от 11 октября 2026 года - подводные кабели строкой
раздела «Слои». Карта TeleGeography не подходит: под CC BY-SA 4.0 у неё
только изображения карт, геометрия кабелей - платная подписка
(www2.telegeography.com/license-telegeography-map, сверено в тот же
день). Данные - OpenStreetMap под ODbL: линии связи и силовые кабели под
водой, файл data/cables.json собирает tools/build_cables.py. В OSM
нанесена часть кабелей мира, больше всего - в Атлантике и у Европы.

На глобусе кабели - слой в памяти QGIS в картинках наложения, как
границы плит (net.overlay.cable_layer). Цвета и толщина - выбор
помощника, утверждает автор.
"""
import json
import math
from collections import namedtuple

try:  # внутри плагина QGIS
    from . import pick
except ImportError:  # headless-тесты
    import pick

ATTRIBUTION = ("Submarine cables: © OpenStreetMap contributors",
               "https://www.openstreetmap.org/copyright")
KINDS = ("telecom", "power")
COLORS = {"telecom": (0, 190, 200, 255), "power": (190, 70, 210, 255)}
WIDTH = 2.0  # толщина линии, пиксели картинки тайла

Cable = namedtuple("Cable", "kind name operator voltage osm lats lons")
Cable.__doc__ = """Кабель: вид (telecom, power), название, владелец,
напряжение из OSM, объект OSM «way/номер», широты и долготы точек."""


class Cables:
    """Кабели из текста data/cables.json и дата выборки из OSM."""

    def __init__(self, cables, date=""):
        self.cables = cables
        self.date = date
        self.boxes = [(min(c.lats), min(c.lons), max(c.lats), max(c.lons))
                      for c in cables]

    @classmethod
    def from_text(cls, text):
        data = json.loads(text)
        cables = []
        for item in data.get("cables", ()):
            kind = item.get("kind")
            pts = item.get("points") or []
            if kind not in KINDS or len(pts) < 2:
                continue
            cables.append(Cable(kind, str(item.get("name", "")),
                                str(item.get("operator", "")),
                                str(item.get("voltage", "")),
                                str(item.get("osm", "")),
                                tuple(float(p[0]) for p in pts),
                                tuple(float(p[1]) for p in pts)))
        return cls(cables, str(data.get("date", "")))

    def __len__(self):
        return len(self.cables)


def nearest(cables, lat, lon, metres):
    """Ближайший к точке кабель ближе metres или None. Сначала отбор
    по рамкам линий с запасом допуска, потом расстояние до отрезков
    (core.pick). Отрезки упрощённых линий в океане длиной в сотни
    километров, поэтому отбор - по рамке, а не по вершинам."""
    reach = math.degrees(metres / 6371000.0)
    reach_lon = reach / max(math.cos(math.radians(lat)), 0.01)
    near = [c for c, (s, w, n, e) in zip(cables.cables, cables.boxes)
            if s - reach <= lat <= n + reach
            and w - reach_lon <= lon <= e + reach_lon]
    found = pick.picked([("line", list(zip(c.lats, c.lons)))
                         for c in near], lat, lon, metres)
    return near[found[0]] if found else None
