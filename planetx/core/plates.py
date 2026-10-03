# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Границы литосферных плит PB2002. Без Qt.

Модель Peter Bird 2003, «An updated digital model of plate boundaries»,
G-cubed 4(3), 1027. Данные в GIS - Hugo Ahlenius, Nordpil,
github.com/fraxen/tectonicplates, Open Data Commons Attribution 1.0.
Файл data/plates.json собирает tools/build_plates.py.

Класс шага границы по Bird:
- OSR - океанический спрединговый хребет, CRB - континентальный рифт;
- OTF - океанический трансформный разлом, CTF - континентальный;
- SUB - зона субдукции, OCB - океаническое схождение, CCB -
  континентальная коллизия.
Скорость - относительная скорость плит на границе, мм/год.

На глобусе границы - слой в памяти QGIS в картинках наложения, как
векторная основа (net.overlay.plate_layer). Своими линиями глобуса
1679 линий со сгущением по дуге дали бы около миллиона вершин при
бюджете 200 тысяч. Названия плит - надписи глобуса класса «plate».
"""
import json
import math
from collections import namedtuple

try:  # внутри плагина QGIS
    from . import pick
except ImportError:  # headless-тесты
    import pick

ATTRIBUTION = ("Plate boundaries: Bird 2003, PB2002, Hugo Ahlenius, Nordpil",
               "https://github.com/fraxen/tectonicplates")
# Класс шага - группа: раздвиг, сдвиг, схождение.
GROUP = {"OSR": "divergent", "CRB": "divergent",
         "OTF": "transform", "CTF": "transform",
         "SUB": "convergent", "OCB": "convergent", "CCB": "convergent"}
# Цвета групп RGBA, выбор помощника.
COLORS = {"divergent": (230, 70, 50, 255),
          "transform": (60, 200, 90, 255),
          "convergent": (70, 140, 255, 255)}
WIDTH = 2.5  # толщина линии, пиксели картинки тайла
RADIUS = 6371000.0  # средний радиус Земли, м - для отбора линий
# Длиннейший шаг границы PB2002 короче 1°: линия, у которой нет
# вершины ближе допуска с этим запасом, точно дальше допуска.
STEP_MAX = math.radians(1.0)

Boundary = namedtuple("Boundary", "code pair speed lats lons")
Boundary.__doc__ = """Линия границы: класс шага, пара плит «AF-AN»,
скорость мм/год, широты и долготы точек, градусы."""
Plate = namedtuple("Plate", "code name lat lon")


class Plates:
    """Границы и подписи плит из текста data/plates.json."""

    def __init__(self, boundaries, plates):
        self.boundaries = boundaries
        self.plates = plates

    @classmethod
    def from_text(cls, text):
        data = json.loads(text)
        lines = []
        for item in data.get("boundaries", ()):
            code = item.get("class")
            pts = item.get("points") or []
            if code not in GROUP or len(pts) < 2:
                continue
            lines.append(Boundary(code, str(item.get("pair", "")),
                                  float(item.get("speed", 0.0)),
                                  tuple(float(p[0]) for p in pts),
                                  tuple(float(p[1]) for p in pts)))
        names = [Plate(str(c), str(n), float(la), float(lo))
                 for c, n, la, lo in data.get("plates", ())]
        return cls(lines, names)


def group(code):
    return GROUP.get(code)


def color(code):
    return COLORS[GROUP[code]]


def _angle(lat1, lon1, lat2, lon2):
    """Угол между точками на сфере, радианы."""
    p1, p2 = math.radians(lat1), math.radians(lat2)
    d = math.radians(lon2 - lon1)
    c = (math.sin(p1) * math.sin(p2)
         + math.cos(p1) * math.cos(p2) * math.cos(d))
    return math.acos(max(-1.0, min(1.0, c)))


def in_view(boundary, lat, lon, reach):
    """Задевает ли линия круг радиуса reach радиан вокруг точки
    взгляда. Шаги линии короче сотни километров, концов шагов хватает."""
    if reach >= math.pi:
        return True
    return any(_angle(lat, lon, la, lo) <= reach
               for la, lo in zip(boundary.lats, boundary.lons))


def describe(boundary):
    """Ключ группы, класс, пара плит и скорость для подписи и окна
    «Объекты». Тексты на языке интерфейса даёт окно."""
    return GROUP[boundary.code], boundary.code, boundary.pair, \
        boundary.speed


def nearest(plates, lat, lon, metres):
    """Ближайшая к точке граница ближе metres или None. Расстояние -
    до отрезков линии (core.pick), точки границы стоят через десятки
    километров."""
    near = [b for b in plates.boundaries
            if in_view(b, lat, lon, metres / RADIUS + STEP_MAX)]
    found = pick.picked([("line", list(zip(b.lats, b.lons)))
                         for b in near], lat, lon, metres)
    return near[found[0]] if found else None
