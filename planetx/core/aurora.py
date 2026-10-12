# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Полярное сияние: прогноз OVATION службы NOAA SWPC.

Просьба автора от 12 октября 2026 года по письму пользователя. В NASA
GIBS слоя сияния нет. Служба космической погоды NOAA публикует
прогноз модели OVATION на ближайшие 30-90 минут - вероятность видимого
сияния в процентах на сетке 1° (360 долгот от 0° до 359°, 181 широта
от -90° до 90°), файл JSON с ключами «Forecast Time» и «coordinates»,
тройки (долгота, широта, вероятность). Файл обновляется каждые
5 минут, данные NOAA - общественное достояние США. Огней городов
в файле нет, они - отдельный слой (core/sun.py).

Поле идёт тем же путём, что поля прогноза GFS (core/weather.py,
ui/weather.py): Grid, раскраска Field, картинки тайлов ResultTiles.

Модуль Qt не знает.
"""
import calendar
import json
import time

import numpy as np

try:  # внутри плагина QGIS
    from .weather import Field, Grid
except ImportError:  # headless-тесты
    from weather import Field, Grid

URL = "https://services.swpc.noaa.gov/json/ovation_aurora_latest.json"
ATTRIBUTION = ("NOAA SWPC OVATION",
               "https://www.swpc.noaa.gov/products/"
               "aurora-30-minute-forecast")
# Полученный прогноз не просится заново раньше этого срока, файл
# на сервере меняется каждые 5 минут. Выбор помощника, утверждает автор.
REFRESH = 600.0  # с
ROWS, COLS = 181, 360
# Ниже CLEAR % поле прозрачно, зелёный - слабое сияние, к красному -
# сильное. Цвета - выбор помощника, утверждает автор.
FIELD = Field("aurora", (), "%", (
    (3.0, (60, 255, 140, 0)), (10.0, (60, 255, 140, 150)),
    (30.0, (150, 255, 90, 210)), (50.0, (250, 230, 60, 230)),
    (70.0, (250, 120, 40, 245)), (90.0, (230, 40, 90, 255))), clear=3.0)


def forecast_seconds(text):
    """Секунды UTC из записи «2026-10-12T03:15:00Z» или None."""
    text = (text or "").strip().rstrip("Z").replace(" ", "T")[:19]
    if len(text) == 16:
        text += ":00"
    try:
        parsed = time.strptime(text, "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    return float(calendar.timegm(parsed))


def parse(data):
    """Grid из байтов файла OVATION или None. Строки сетки - с севера
    на юг, столбцы - долготы от 0°. run - момент прогноза, hour 0."""
    try:
        doc = json.loads(bytes(data).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(doc, dict):
        return None
    triples = doc.get("coordinates")
    if not isinstance(triples, list) or not triples:
        return None
    try:
        points = np.asarray(triples, dtype=np.float64)
    except (TypeError, ValueError):
        return None
    if points.ndim != 2 or points.shape[1] < 3:
        return None
    lon = np.rint(points[:, 0]).astype(np.int64) % COLS
    lat = np.rint(points[:, 1]).astype(np.int64)
    inside = (lat >= -90) & (lat <= 90) & np.isfinite(points[:, 2])
    values = np.zeros((ROWS, COLS), dtype=np.float32)
    values[90 - lat[inside], lon[inside]] = points[inside, 2]
    run = forecast_seconds(doc.get("Forecast Time"))
    if run is None:
        run = forecast_seconds(doc.get("Observation Time"))
    if run is None:
        return None
    return Grid(values, 0.0, 90.0, 1.0, run, 0,
                (-90.0, 90.0, -180.0, 180.0))



def valid_text(grid):
    """Момент прогноза UTC с минутами."""
    return time.strftime("%Y-%m-%d %H:%M", time.gmtime(grid.run))
