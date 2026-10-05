# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Пожары: разбор сводки NASA FIRMS, цвет и размер по мощности
излучения. Расчёт без Qt.

Просьба автора от 5 октября 2026 года, источник и сводку выбрал автор
в тот же день - открытая сводка FIRMS прибора VIIRS спутника NOAA-20
за 24 часа (FEED), около 78 тысяч очагов, 375 м. Векторные тайлы
пожаров NASA GIBS отвечают 404 на всех путях. Строка сводки - широта,
долгота, дата и время снимка UTC (acq_date, acq_time ЧЧММ), мощность
излучения FRP в мегаваттах, достоверность, день или ночь.

Очаги лежат массивами NumPy, по одному на поле, - точек десятки тысяч.
Цвет по мощности - шкала FRP_STOPS в логарифме, слабые жёлтые,
мощные тёмно-красные. Размер точки растёт с логарифмом мощности.
"""
import calendar
import math

import numpy as np

FEED = ("https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
        "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Global_24h.csv")
ATTRIBUTION = ("Fires: NASA FIRMS VIIRS NOAA-20",
               "https://firms.modaps.eosdis.nasa.gov/")
# Мощность излучения, МВт - цвет. Выбор помощника, утверждает автор.
FRP_STOPS = ((1.0, (255, 230, 80)), (10.0, (255, 150, 30)),
             (100.0, (230, 40, 20)), (1000.0, (120, 0, 0)))
FRP_TICKS = (1, 10, 100, 1000)  # подписи шкалы, МВт
MIN_SIZE = 3.0  # логических пикселей у очага 1 МВт и слабее
SIZE_PER_DECADE = 2.5  # логических пикселей на порядок мощности
MAX_SIZE = 11.0


class Fires:
    """Очаги сводки: массивы lat, lon, frp (МВт), time (секунды UTC),
    confidence (строки), night (признак ночного снимка)."""

    __slots__ = ("lat", "lon", "frp", "time", "confidence", "night")

    def __init__(self, lat=(), lon=(), frp=(), time=(), confidence=(),
                 night=()):
        self.lat = np.asarray(lat, dtype=np.float64)
        self.lon = np.asarray(lon, dtype=np.float64)
        self.frp = np.asarray(frp, dtype=np.float64)
        self.time = np.asarray(time, dtype=np.float64)
        self.confidence = list(confidence)
        self.night = np.asarray(night, dtype=bool)

    def __len__(self):
        return len(self.lat)


def _seconds(date, hhmm):
    """Секунды UTC по дате ГГГГ-ММ-ДД и времени ЧЧММ или None."""
    try:
        year, month, day = (int(v) for v in date.split("-"))
        hhmm = int(hhmm)
    except ValueError:
        return None
    return float(calendar.timegm((year, month, day, hhmm // 100,
                                  hhmm % 100, 0)))


def _floats(*cells):
    """Числа из ячеек или None, если хоть одна не конечное число."""
    out = []
    for cell in cells:
        try:
            value = float(cell)
        except ValueError:
            return None
        if not math.isfinite(value):
            return None
        out.append(value)
    return out


def parse(text):
    """Очаги из текста CSV сводки FIRMS. Строка без координат или
    мощности пропускается. Время без даты - NaN."""
    lines = (text or "").splitlines()
    if not lines:
        return Fires()
    head = [name.strip() for name in lines[0].split(",")]
    try:
        i_lat, i_lon = head.index("latitude"), head.index("longitude")
        i_frp = head.index("frp")
        i_date, i_time = head.index("acq_date"), head.index("acq_time")
    except ValueError:
        return Fires()
    i_conf = head.index("confidence") if "confidence" in head else None
    i_dn = head.index("daynight") if "daynight" in head else None
    need = max(i_lat, i_lon, i_frp, i_date, i_time)
    lat, lon, frp, when, conf, night = [], [], [], [], [], []
    for line in lines[1:]:
        cells = line.split(",")
        if len(cells) <= need:
            continue
        values = _floats(cells[i_lat], cells[i_lon], cells[i_frp])
        if values is None:
            continue
        a, b, f = values
        seconds = _seconds(cells[i_date], cells[i_time])
        lat.append(a)
        lon.append(b)
        frp.append(f)
        when.append(float("nan") if seconds is None else seconds)
        conf.append(cells[i_conf].strip() if i_conf is not None else "")
        night.append(i_dn is not None and cells[i_dn].strip() == "N")
    return Fires(lat, lon, frp, when, conf, night)


def colors(frp):
    """Цвета очагов по мощности (n, 3) uint8, шкала FRP_STOPS
    в логарифме мощности."""
    value = np.log10(np.maximum(np.asarray(frp, dtype=np.float64), 1e-3))
    bounds = np.log10([s[0] for s in FRP_STOPS])
    table = np.array([s[1] for s in FRP_STOPS], dtype=np.float64)
    rgb = np.stack([np.interp(value, bounds, table[:, c])
                    for c in range(3)], axis=-1)
    return np.rint(rgb).astype(np.uint8)


def sizes(frp):
    """Размер точки в логических пикселях по мощности."""
    decades = np.log10(np.maximum(np.asarray(frp, dtype=np.float64), 1.0))
    return np.clip(MIN_SIZE + SIZE_PER_DECADE * decades, MIN_SIZE,
                   MAX_SIZE)


def span(fires):
    """Самое раннее и самое позднее время снимков или None."""
    values = fires.time[~np.isnan(fires.time)] if len(fires) else []
    if not len(values):
        return None
    return float(np.min(values)), float(np.max(values))
