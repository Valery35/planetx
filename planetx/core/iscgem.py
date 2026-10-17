# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Исторические землетрясения - каталог ISC-GEM с 1904 года.

ISC-GEM Global Instrumental Earthquake Catalogue (International
Seismological Centre, GEM Foundation, CC BY-SA 3.0) - 74 153 сильных
события 1904-2024 годов на 17 октября 2026 года, 13 МБ CSV, с
пересчитанными местами и моментными магнитудами.
Сайт ISC отдаёт файл после анкеты, поэтому модуль берёт тот же каталог
у ComCat USGS (catalog=iscgem), запросами по промежуткам лет - не больше
20 тысяч событий на запрос. Каталог собирается один раз в файл профиля
(save, load), записи - core.quakes.Quake.

Промежутки и срок обновления - выбор помощника, утверждает автор.

Модуль Qt не знает.
"""
import csv
import io
from datetime import datetime, timezone

import numpy as np

try:  # внутри плагина QGIS
    from .quakes import Quake
except ImportError:  # headless-тесты
    from quakes import Quake

QUERY = ("https://earthquake.usgs.gov/fdsnws/event/1/query?format=csv"
         "&catalog=iscgem&orderby=time-asc&starttime={}&endtime={}")
EVENT = "https://earthquake.usgs.gov/earthquakes/eventpage/{}"
ATTRIBUTION = ("Historical earthquakes: ISC-GEM, ISC and GEM Foundation, "
               "CC BY-SA 3.0", "https://doi.org/10.31905/d808b825")
FIRST_YEAR = 1900
# До 1960 года событий около 8.6 тысячи, дальше - до 1.3 тысячи в год.
SPLIT_YEAR = 1960
STEP_YEARS = 5
REFETCH_DAYS = 180  # каталог обновляется раз в год, файл старше - заново
FILE = "iscgem.npz"


def periods(last_year):
    """Промежутки запросов (начало, конец) датами ISO до last_year
    включительно: один до SPLIT_YEAR, дальше по STEP_YEARS лет."""
    out = [(FIRST_YEAR, SPLIT_YEAR)]
    year = SPLIT_YEAR
    while year <= last_year:
        out.append((year, min(year + STEP_YEARS, last_year + 1)))
        year += STEP_YEARS
    return [("{}-01-01".format(a), "{}-01-01".format(b)) for a, b in out]


def query_url(start, end):
    return QUERY.format(start, end)


def _seconds(text):
    """Время ComCat 1906-01-02T04:26:27.250Z в секунды UTC или None."""
    try:
        moment = datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%S.%fZ")
    except ValueError:
        try:
            moment = datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%SZ")
        except ValueError:
            return None
    return moment.replace(tzinfo=timezone.utc).timestamp()


def _number(text):
    """Число поля CSV или None - поле пустое или не число."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse(data):
    """События из ответа CSV ComCat. Строка без координат, глубины или
    магнитуды пропускается. Неизвестная глубина считается нулевой."""
    text = data.decode("utf-8", "replace") if isinstance(data, bytes) \
        else str(data)
    out = []
    for row in csv.DictReader(io.StringIO(text)):
        lat, lon, mag = (_number(row.get(name)) for name in (
            "latitude", "longitude", "mag"))
        if lat is None or lon is None or mag is None:
            continue
        depth = _number(row.get("depth")) or 0.0
        ident = (row.get("id") or "").strip()
        out.append(Quake(lat, lon, depth, mag,
                         _seconds(row.get("time") or ""),
                         (row.get("place") or "").strip(),
                         EVENT.format(ident) if ident else ""))
    return out


def save(events, path):
    """Каталог в файл npz без объектов Python: числа массивами, места
    и адреса одной строкой с разделителем."""
    numbers = np.array([(q.lat, q.lon, q.depth, q.mag,
                         np.nan if q.time is None else q.time)
                        for q in events], dtype=np.float64).reshape(-1, 5)
    text = "\n".join(q.place.replace("\n", " ") + "\t" + q.url
                     for q in events)
    np.savez_compressed(path, numbers=numbers,
                        text=np.frombuffer(text.encode("utf-8"),
                                           dtype=np.uint8))


def load(path):
    """Каталог из файла save."""
    with np.load(path) as data:
        numbers = data["numbers"]
        text = bytes(data["text"]).decode("utf-8")
    lines = text.split("\n") if text else []
    out = []
    for row, line in zip(numbers, lines):
        place, _, url = line.partition("\t")
        time = None if np.isnan(row[4]) else float(row[4])
        out.append(Quake(float(row[0]), float(row[1]), float(row[2]),
                         float(row[3]), time, place, url))
    return out
