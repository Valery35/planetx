# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вулканы голоцена, Smithsonian Global Volcanism Program. Без Qt.

Просьба автора от 16 октября 2026 года после списка геофизики. Список
Volcanoes of the World - около 1200 вулканов, извергавшихся за последние
12 тысяч лет, с типом, высотой, годом последнего извержения
и тектонической обстановкой. База составлена служащими США, но общие
условия Smithsonian разрешают только некоммерческое использование,
поэтому модуль список не распространяет: строка скачивает его
запросом WFS (URL) при первом включении, итог - файл профиля, как
у электростанций.

Цвет точки - время последнего извержения (PERIODS), размер - высота
вулкана над уровнем моря от SIZE_MIN до SIZE_MAX. Записи для опроса -
одна строка с разделителями, как в core/deposits.py.
"""
import csv
import io
import math

import numpy as np

try:  # внутри плагина QGIS
    from .deposits import END, SEPARATOR
except ImportError:  # headless-тесты
    from deposits import END, SEPARATOR

URL = ("https://webservices.volcano.si.edu/geoserver/GVP-VOTW/ows?"
       "service=WFS&version=2.0.0&request=GetFeature&typeName=GVP-VOTW:"
       "Smithsonian_VOTW_Holocene_Volcanoes&outputFormat=csv")
ATTRIBUTION = ("Volcanoes: Global Volcanism Program, Smithsonian "
               "Institution", "https://volcano.si.edu/")
PAGE = "https://volcano.si.edu/volcano.cfm?vn={}"
# Последнее извержение: ключ, с какого года (включительно), цвет. Выбор
# помощника, утверждает автор.
PERIODS = (
    ("recent", 1900, (230, 40, 30)),
    ("historic", 1500, (245, 140, 40)),
    ("holocene", -10000, (240, 210, 70)),
    ("unknown", None, (170, 170, 170)),
)
SIZE_MIN = 5.0
SIZE_MAX = 12.0
HEIGHT_LOW = 0.0  # м, наименьшая точка
HEIGHT_HIGH = 6000.0  # м, наибольшая


def period_of(year):
    """Номер периода по году последнего извержения, NaN - неизвестен."""
    if year is None or not math.isfinite(year):
        return len(PERIODS) - 1
    for n, (_, start, _) in enumerate(PERIODS[:-1]):
        if year >= start:
            return n
    return len(PERIODS) - 2


def colors(periods):
    table = np.array([p[2] for p in PERIODS], dtype=np.uint8)
    return table[np.asarray(periods, dtype=np.int64)]


def sizes(elevation):
    h = np.clip(np.nan_to_num(np.asarray(elevation, dtype=np.float64)),
                HEIGHT_LOW, HEIGHT_HIGH)
    share = (h - HEIGHT_LOW) / (HEIGHT_HIGH - HEIGHT_LOW)
    return (SIZE_MIN + share * (SIZE_MAX - SIZE_MIN)).astype(np.float32)


class Volcanoes:
    """Вулканы массивами: lat, lon, period, elevation (м), last (год
    последнего извержения, NaN - неизвестен), blob и offsets - записи для
    опроса."""

    __slots__ = ("lat", "lon", "period", "elevation", "last", "blob",
                 "offsets")

    def __init__(self, lat, lon, period, elevation, last, blob, offsets):
        self.lat = np.asarray(lat, dtype=np.float64)
        self.lon = np.asarray(lon, dtype=np.float64)
        self.period = np.asarray(period, dtype=np.uint8)
        self.elevation = np.asarray(elevation, dtype=np.float64)
        self.last = np.asarray(last, dtype=np.float64)
        self.blob = blob
        self.offsets = np.asarray(offsets, dtype=np.int64)

    def __len__(self):
        return len(self.lat)

    def text(self, n):
        """Поля записи n: номер, название, тип, страна, обстановка,
        достоверность."""
        part = self.blob[self.offsets[n]:self.offsets[n + 1]]
        return part.rstrip(END).split(SEPARATOR)


def _number(cell):
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def parse(data):
    """Вулканы из ответа WFS в CSV."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) \
        else data
    rows = list(csv.DictReader(io.StringIO(text)))
    if rows and "Volcano_Name" not in rows[0]:
        raise ValueError("not a GVP volcano list")
    lat, lon, period, elevation, last, parts = [], [], [], [], [], []
    for row in rows:
        y, x = _number(row.get("Latitude")), _number(row.get("Longitude"))
        if y is None or x is None or not (-90 <= y <= 90) \
                or not (-180 <= x <= 180):
            continue
        year = _number(row.get("Last_Eruption_Year"))
        lat.append(y)
        lon.append(x)
        last.append(np.nan if year is None else year)
        period.append(period_of(year))
        height = _number(row.get("Elevation"))
        elevation.append(np.nan if height is None else height)
        fields = (row.get("Volcano_Number"), row.get("Volcano_Name"),
                  row.get("Primary_Volcano_Type"), row.get("Country"),
                  row.get("Tectonic_Setting"), row.get("Evidence_Category"))
        parts.append(SEPARATOR.join(
            str(f or "").replace(SEPARATOR, " ").replace(END, " ")
            for f in fields) + END)
    lengths = [len(p) for p in parts]
    offsets = np.concatenate([[0], np.cumsum(lengths)]) if lengths \
        else np.zeros(1)
    return Volcanoes(lat, lon, period, elevation, last, "".join(parts),
                     offsets)


def save(found, path):
    np.savez_compressed(
        path, lat=found.lat.astype(np.float32),
        lon=found.lon.astype(np.float32), period=found.period,
        elevation=found.elevation.astype(np.float32),
        last=found.last.astype(np.float32), offsets=found.offsets,
        blob=np.frombuffer(found.blob.encode("utf-8"), dtype=np.uint8))


def load(path):
    with np.load(path, allow_pickle=False) as data:
        return Volcanoes(data["lat"].astype(np.float64),
                         data["lon"].astype(np.float64), data["period"],
                         data["elevation"].astype(np.float64),
                         data["last"].astype(np.float64),
                         data["blob"].tobytes().decode("utf-8"),
                         data["offsets"])

