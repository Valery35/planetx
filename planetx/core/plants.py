# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Электростанции мира, Global Power Plant Database WRI. Расчёт без Qt.

Просьба автора от 11 октября 2026 года - «трубопроводы, ЛЭП», строка
«Электростанции» группы «Инфраструктура» витрины. База WRI версии 1.3 -
34 936 электростанций с мощностью, видом топлива, годом ввода и
владельцем, из них 545 в России, CC BY 4.0, данные на 2021 год. Архив
4.2 МБ скачивается при первом включении, разбор - в рабочем потоке,
итог - файл в профиле QGIS, как у месторождений. У части станций место
в базе неверное, например Березниковская ТЭЦ-10 стоит под Пензой -
это ошибка источника.

Цвет точки - вид топлива (FUELS), размер - мощность в логарифме от
SIZE_MIN до SIZE_MAX логических пикселей. Записи для опроса - одна
строка с разделителями, как в core/deposits.py.
"""
import csv
import io
import math
import zipfile

import numpy as np

try:  # внутри плагина QGIS
    from .deposits import END, SEPARATOR
except ImportError:  # headless-тесты
    from deposits import END, SEPARATOR

URL = ("https://wri-dataportal-prod.s3.amazonaws.com/manual/"
       "global_power_plant_database_v_1_3.zip")
ATTRIBUTION = ("Power plants: WRI Global Power Plant Database, CC BY 4.0",
               "https://datasets.wri.org/dataset/globalpowerplantdatabase")
# Вид топлива: ключ, значения primary_fuel, цвет. Выбор помощника.
FUELS = (
    ("coal", ("Coal", "Petcoke"), (60, 60, 60)),
    ("gas", ("Gas", "Cogeneration"), (240, 150, 40)),
    ("oil", ("Oil",), (150, 80, 40)),
    ("nuclear", ("Nuclear",), (220, 40, 160)),
    ("hydro", ("Hydro", "Wave and Tidal"), (40, 120, 230)),
    ("wind", ("Wind",), (120, 220, 230)),
    ("solar", ("Solar",), (250, 220, 40)),
    ("bio", ("Biomass", "Waste", "Geothermal"), (70, 170, 70)),
    ("other", ("Storage", "Other"), (200, 200, 200)),
)
SIZE_MIN = 3.0
SIZE_MAX = 14.0
MW_LOW = 1.0  # мощность, МВт, при которой точка наименьшая
MW_HIGH = 5000.0  # мощность, МВт, при которой точка наибольшая


def fuel_of(name):
    """Номер вида топлива по значению primary_fuel."""
    for n, (_, values, _) in enumerate(FUELS):
        if name in values:
            return n
    return len(FUELS) - 1


def colors(fuels):
    table = np.array([f[2] for f in FUELS], dtype=np.uint8)
    return table[np.asarray(fuels, dtype=np.int64)]


def sizes(capacity):
    """Размер точки по мощности, логарифм от MW_LOW до MW_HIGH."""
    mw = np.clip(np.asarray(capacity, dtype=np.float64), MW_LOW, MW_HIGH)
    share = np.log(mw / MW_LOW) / math.log(MW_HIGH / MW_LOW)
    return (SIZE_MIN + share * (SIZE_MAX - SIZE_MIN)).astype(np.float32)


class Plants:
    """Электростанции массивами: lat, lon, fuel, capacity (МВт), blob
    и offsets - записи для опроса."""

    __slots__ = ("lat", "lon", "fuel", "capacity", "blob", "offsets")

    def __init__(self, lat, lon, fuel, capacity, blob, offsets):
        self.lat = np.asarray(lat, dtype=np.float64)
        self.lon = np.asarray(lon, dtype=np.float64)
        self.fuel = np.asarray(fuel, dtype=np.uint8)
        self.capacity = np.asarray(capacity, dtype=np.float64)
        self.blob = blob
        self.offsets = np.asarray(offsets, dtype=np.int64)

    def __len__(self):
        return len(self.lat)

    def text(self, n):
        """Поля записи n: название, страна, топливо (как в базе), год
        ввода, владелец, адрес источника."""
        part = self.blob[self.offsets[n]:self.offsets[n + 1]]
        return part.rstrip(END).split(SEPARATOR)


def _number(cell):
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def parse(data):
    """Электростанции из байтов архива ZIP или CSV базы WRI."""
    if data[:2] == b"PK":
        archive = zipfile.ZipFile(io.BytesIO(data))
        member = next(m for m in archive.namelist()
                      if m.lower().endswith(".csv"))
        data = archive.read(member)
    text = data.decode("utf-8", "replace")
    lat, lon, fuel, capacity, parts = [], [], [], [], []
    for row in csv.DictReader(io.StringIO(text)):
        y, x = _number(row.get("latitude")), _number(row.get("longitude"))
        if y is None or x is None or not (-90 <= y <= 90) \
                or not (-180 <= x <= 180):
            continue
        lat.append(y)
        lon.append(x)
        fuel.append(fuel_of(row.get("primary_fuel") or ""))
        capacity.append(_number(row.get("capacity_mw")) or 0.0)
        year = _number(row.get("commissioning_year"))
        fields = (row.get("name"), row.get("country_long"),
                  row.get("primary_fuel"),
                  "" if year is None else str(int(year)),
                  row.get("owner"), row.get("url"))
        parts.append(SEPARATOR.join(
            str(f or "").replace(SEPARATOR, " ").replace(END, " ")
            for f in fields) + END)
    lengths = [len(p) for p in parts]
    offsets = np.concatenate([[0], np.cumsum(lengths)]) if lengths \
        else np.zeros(1)
    return Plants(lat, lon, fuel, capacity, "".join(parts), offsets)


def save(plants, path):
    np.savez_compressed(
        path, lat=plants.lat.astype(np.float32),
        lon=plants.lon.astype(np.float32), fuel=plants.fuel,
        capacity=plants.capacity.astype(np.float32),
        offsets=plants.offsets,
        blob=np.frombuffer(plants.blob.encode("utf-8"), dtype=np.uint8))


def load(path):
    with np.load(path, allow_pickle=False) as data:
        return Plants(data["lat"].astype(np.float64),
                      data["lon"].astype(np.float64), data["fuel"],
                      data["capacity"].astype(np.float64),
                      data["blob"].tobytes().decode("utf-8"),
                      data["offsets"])
