# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Активные разломы GEM Global Active Faults. Без Qt.

Решение автора от 17 октября 2026 года по списку открытых данных
помощника - разломы строкой «Недр». База GEM Global Active Faults
(Styron, Pagani 2020, Earthquake Spectra 36(1_suppl)), лицензия
CC BY-SA 4.0, сверено 17 октября 2026 года на странице хранилища
GEMScienceTools/gem-global-active-faults. Модуль данные не несёт,
файл gem_active_faults_harmonized.geojson (около 10.6 МБ, 13 696
линий) скачивается при первом включении в папку PlanetX профиля.

На глобусе разломы - слой в памяти QGIS в картинках наложения, как
границы плит (net.overlay.fault_layer). Цвет - вид смещения по полю
slip_type. Классы и цвета - выбор помощника, утверждает автор.
"""
import json
import math
from collections import namedtuple

try:  # внутри плагина QGIS
    from . import pick
except ImportError:  # headless-тесты
    import pick

URL = ("https://raw.githubusercontent.com/GEMScienceTools/"
       "gem-global-active-faults/master/geojson/"
       "gem_active_faults_harmonized.geojson")
FILE = "gem_active_faults.geojson"
ATTRIBUTION = ("Active faults: GEM Global Active Faults, Styron and Pagani "
               "2020, CC BY-SA 4.0",
               "https://github.com/GEMScienceTools/gem-global-active-faults")
PAGE = "https://doi.org/10.1177/8755293020944182"

# Виды смещения по полю slip_type: сброс, взброс и надвиг, сдвиг,
# срединный хребет, складка, прочее.
KINDS = ("normal", "reverse", "strike", "ridge", "fold", "other")
COLORS = {"normal": (40, 120, 230, 255), "reverse": (225, 45, 40, 255),
          "strike": (30, 170, 70, 255), "ridge": (240, 150, 30, 255),
          "fold": (150, 90, 200, 255), "other": (120, 120, 120, 255)}
WIDTH = 1.6  # толщина линии, пиксели картинки тайла

Fault = namedtuple("Fault", "kind name slip_type rate dip dip_dir "
                            "catalog lats lons")
Fault.__doc__ = """Разлом: вид (KINDS), название, slip_type как в базе,
скорость смещения в мм/год (наиболее вероятная, None - нет), падение
в градусах (None - нет), сторона падения, каталог источника, широты
и долготы точек."""


def kind_of(slip_type):
    """Вид смещения по полю slip_type базы."""
    text = (slip_type or "").lower()
    if not text:
        return "other"
    if text.startswith("spreading"):
        return "ridge"
    if text in ("anticline", "syncline"):
        return "fold"
    if text.startswith("normal"):
        return "normal"
    if text.startswith(("reverse", "subduction", "blind")):
        return "reverse"
    if text.startswith(("dextral", "sinistral", "strike")):
        return "strike"
    return "other"


def first_value(text):
    """Наиболее вероятное значение записи вида «(1.55,0.8,2.22)» или
    None."""
    if text is None:
        return None
    if isinstance(text, (int, float)):
        return float(text)
    head = str(text).strip().strip("()").split(",")[0].strip()
    try:
        value = float(head)
    except ValueError:
        return None
    return value if math.isfinite(value) else None


class Faults:
    """Разломы и рамки их линий."""

    def __init__(self, faults):
        self.faults = faults
        self.boxes = [(min(f.lats), min(f.lons), max(f.lats), max(f.lons))
                      for f in faults]

    def __len__(self):
        return len(self.faults)


def parse(data):
    """Разломы из байтов GeoJSON базы. Линии из частей MultiLineString
    идут отдельными разломами с теми же полями."""
    collection = json.loads(data.decode("utf-8") if isinstance(
        data, (bytes, bytearray)) else data)
    faults = []
    for feature in collection.get("features", ()):
        geometry = feature.get("geometry") or {}
        props = feature.get("properties") or {}
        kind = geometry.get("type")
        if kind == "LineString":
            parts = [geometry.get("coordinates") or ()]
        elif kind == "MultiLineString":
            parts = geometry.get("coordinates") or ()
        else:
            continue
        slip = props.get("slip_type") or ""
        name = str(props.get("name") or props.get("fs_name") or "")
        rate = first_value(props.get("net_slip_rate"))
        if rate is None:
            rate = first_value(props.get("strike_slip_rate"))
        dip = first_value(props.get("average_dip"))
        for part in parts:
            points = [p for p in part if len(p) >= 2]
            if len(points) < 2:
                continue
            faults.append(Fault(
                kind_of(slip), name, str(slip), rate, dip,
                str(props.get("dip_dir") or ""),
                str(props.get("catalog_name") or ""),
                tuple(float(p[1]) for p in points),
                tuple(float(p[0]) for p in points)))
    return Faults(faults)


def nearest(data, lat, lon, metres):
    """Ближайший к точке разлом ближе metres или None. Отбор по рамкам
    линий с запасом допуска, потом расстояние до отрезков (core.pick)."""
    reach = math.degrees(metres / 6371000.0)
    reach_lon = reach / max(math.cos(math.radians(lat)), 0.01)
    near = [f for f, (s, w, n, e) in zip(data.faults, data.boxes)
            if s - reach <= lat <= n + reach
            and w - reach_lon <= lon <= e + reach_lon]
    found = pick.picked([("line", list(zip(f.lats, f.lons)))
                         for f in near], lat, lon, metres)
    return near[found[0]] if found else None
