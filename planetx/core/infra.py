# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""ЛЭП, подстанции и трубопроводы OpenStreetMap. Расчёт без Qt.

Просьба автора от 11 октября 2026 года - «трубопроводы, ЛЭП», строка
«ЛЭП и трубопроводы OSM» группы «Инфраструктура» витрины. Линии
power=line и man_made=pipeline с геометрией, подстанции power=substation
серединой - запросом Overpass по тайлам вида, как шахты OSM
(core/mining.py, ui/overpass.py). Класс ЛЭП - по наибольшему напряжению
тега voltage, класс трубопровода - по тегу substance. Классы, цвета
и толщины - выбор помощника, утверждает автор.

Кабели - просьба автора от 11 октября 2026 года, «лэп и кабели в слои».
Силовой кабель power=cable (подземный и подводный) и линия связи
communication=line - свои классы CABLES, пунктиром.
"""
import re

NUMBER = re.compile(r"^\d+(\.\d+)?$")
TIMEOUT = 90  # с, предел запроса на сервере Overpass
# Классы ЛЭП: ключ, наименьшее напряжение, кВ, цвет, толщина в пикселях
# картинки тайла.
VOLTAGES = (("v500", 500.0, (220, 30, 30), 3.5),
            ("v220", 220.0, (240, 120, 20), 2.8),
            ("v110", 110.0, (230, 200, 30), 2.0),
            ("v35", 0.0, (170, 170, 170), 1.4))
# Классы трубопроводов: ключ, значения substance, цвет.
SUBSTANCES = (("gas", ("gas", "natural_gas", "cng", "lng", "fuel_gas"),
               (245, 215, 60)),
              ("oil", ("oil", "crude_oil", "fuel", "petroleum", "diesel",
                       "gasoline", "kerosene"), (120, 70, 40)),
              ("water", ("water", "drinking_water", "hot_water", "steam",
                         "heat", "wastewater", "sewage"), (60, 140, 230)),
              ("other", (), (170, 90, 200)))
PIPE_WIDTH = 2.4  # пиксели картинки тайла
# Кабели: ключ, цвет, толщина в пикселях картинки тайла.
CABLES = (("cable", (150, 60, 170), 2.4),
          ("telecom", (20, 170, 170), 1.6))


def query(bounds):
    """Запрос Overpass QL: линии с геометрией и подстанции серединой."""
    box = "({:.5f},{:.5f},{:.5f},{:.5f})".format(*bounds)
    return ("[out:json][timeout:{t}];"
            "(way[\"power\"=\"line\"]{b};way[\"man_made\"=\"pipeline\"]{b};"
            "way[\"power\"=\"cable\"]{b};"
            "way[\"communication\"=\"line\"]{b};);"
            "out geom tags;"
            "(nwr[\"power\"=\"substation\"]{b};);out center tags;"
            ).format(t=TIMEOUT, b=box)


def kilovolts(text):
    """Наибольшее напряжение тега voltage в кВ или None. Значения через
    точку с запятой - цепи разного напряжения на одной опоре."""
    best = None
    for part in str(text or "").replace(",", ";").split(";"):
        part = part.strip().lower().replace(" ", "")
        if part.endswith("kv"):
            scale, part = 1.0, part[:-2]
        else:
            scale = 0.001
        if not NUMBER.match(part):
            continue
        value = float(part) * scale
        best = value if best is None else max(best, value)
    return best


def voltage_class(kv):
    """Ключ класса ЛЭП по напряжению, кВ (None - нижний класс)."""
    for key, low, _, _ in VOLTAGES:
        if kv is not None and kv >= low:
            return key
    return VOLTAGES[-1][0]


def substance_class(text):
    value = str(text or "").lower()
    for key, values, _ in SUBSTANCES:
        if value in values:
            return key
    return SUBSTANCES[-1][0]


def parse(answer):
    """Объекты ответа: словари kind (line, cable, telecom, pipe,
    substation), points
    [(широта, долгота)], style (ключ класса), name, operator, voltage
    (кВ или None), substance, osm (тип/номер)."""
    out = []
    for element in (answer or {}).get("elements", ()):
        tags = element.get("tags") or {}
        osm = "{}/{}".format(element.get("type"), element.get("id"))
        common = {"name": tags.get("name:ru") or tags.get("name") or "",
                  "operator": tags.get("operator") or "", "osm": osm,
                  "voltage": kilovolts(tags.get("voltage")),
                  "substance": tags.get("substance") or "",
                  "location": tags.get("location") or ""}
        if tags.get("power") == "substation":
            center = element.get("center") or element
            if center.get("lat") is None:
                continue
            out.append(dict(common, kind="substation",
                            points=[(center["lat"], center["lon"])],
                            style=voltage_class(common["voltage"])))
            continue
        geometry = element.get("geometry") or []
        points = [(g["lat"], g["lon"]) for g in geometry
                  if g and "lat" in g]
        if len(points) < 2:
            continue
        if tags.get("power") == "line":
            out.append(dict(common, kind="line", points=points,
                            style=voltage_class(common["voltage"])))
        elif tags.get("power") == "cable":
            out.append(dict(common, kind="cable", points=points,
                            style="cable"))
        elif tags.get("communication") == "line":
            out.append(dict(common, kind="telecom", points=points,
                            style="telecom"))
        elif tags.get("man_made") == "pipeline":
            out.append(dict(common, kind="pipe", points=points,
                            style=substance_class(common["substance"])))
    return out


def unique(items):
    """Объекты без повторов одного объекта из соседних запросов."""
    seen, out = set(), []
    for item in items:
        if item["osm"] in seen:
            continue
        seen.add(item["osm"])
        out.append(item)
    return out
