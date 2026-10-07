# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Погода: прогноз модели NOAA GFS полями.

Просьба автора от 6 октября 2026 года - температура и прогноз погоды.
В NASA GIBS прогнозов нет. Поля - модель GFS 0.25° из открытых данных
NOAA на AWS (registry.opendata.aws/noaa-gfs-bdp-pds): «open to the
public and can be used as desired», NOAA просит указывать источник,
сверено 6 октября 2026 года. Сервер NOMADS просит 10 с между запросами
фильтра GRIB, поэтому поле берётся с зеркала AWS по диапазону байт из
индекса .idx - так NOAA сама советует выбирать поля. Поле на весь мир -
0.5-0.8 МБ GRIB2, сетка 1440 × 721, GDAL из QGIS читает его за 0.05 с.

Выпуск модели - каждые 6 часов, файлы появляются через 3.5-5 часов.
Часы прогноза - до 120 по одному, дальше до 384 через три. Момент
шкалы до выпуска берётся из прежнего выпуска, архив на AWS хранится
годами.

Прогноз MET Norway в точке убран 8 октября 2026 года, см. AGENTS.md.

Модуль Qt не знает.
"""
import datetime
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from .themes import overlay_rgba
except ImportError:  # headless-тесты
    from themes import overlay_rgba

BUCKET = "https://noaa-gfs-bdp-pds.s3.amazonaws.com"
FILE = ("{bucket}/gfs.{day}/{hour:02d}/atmos/"
        "gfs.t{hour:02d}z.pgrb2.0p25.f{step:03d}")
CYCLE = 6  # часов между выпусками
DELAY = 4  # часов от выпуска до первой попытки взять его файлы
RUNS_BACK = 4  # выпусков назад, если свежий ещё не выложен
HOURLY = 120  # до этого часа прогноз по одному часу
LAST = 384  # последний час прогноза
OPACITY = 0.7  # непрозрачность раскраски поля

ATTRIBUTION = ("NOAA GFS", "https://registry.opendata.aws/noaa-gfs-bdp-pds/")


class Field:
    """Поле прогноза: ключ, строки индекса, единицы, раскраска.

    lines - начала строк индекса GRIB (переменная и уровень), ramp -
    пары (значение, (R, G, B, A)), clear - значение, ниже которого поле
    прозрачно (осадки), scale - множитель к значению из файла."""

    __slots__ = ("key", "lines", "units", "ramp", "clear", "scale")

    def __init__(self, key, lines, units, ramp, clear=None, scale=1.0):
        self.key = key
        self.lines = lines
        self.units = units
        self.ramp = ramp
        self.clear = clear
        self.scale = scale


FIELDS = (
    Field("temperature", (":TMP:2 m above ground:",), "°C", (
        (-40.0, (60, 0, 130, 255)), (-25.0, (40, 60, 220, 255)),
        (-10.0, (60, 160, 240, 255)), (0.0, (230, 240, 250, 255)),
        (10.0, (120, 210, 90, 255)), (20.0, (250, 210, 50, 255)),
        (30.0, (240, 110, 30, 255)), (40.0, (180, 20, 30, 255)))),
    # Осадки - интенсивность в момент, кг/м²/с, в мм/ч.
    Field("precipitation", (":PRATE:surface:",), "мм/ч", (
        (0.1, (150, 210, 255, 150)), (1.0, (40, 140, 240, 220)),
        (4.0, (20, 60, 200, 240)), (10.0, (150, 40, 200, 250)),
        (30.0, (230, 30, 120, 255))), clear=0.1, scale=3600.0),
    # Ветер - U и V на 10 м подряд в файле, скорость по ним.
    Field("wind", (":UGRD:10 m above ground:", ":VGRD:10 m above ground:"),
          "м/с", (
              (0.0, (230, 245, 255, 0)), (3.0, (170, 220, 250, 140)),
              (8.0, (80, 200, 120, 210)), (14.0, (250, 210, 50, 240)),
              (20.0, (240, 90, 30, 250)), (30.0, (170, 20, 120, 255)))),
    Field("clouds", (":TCDC:entire atmosphere:",), "%", (
        (5.0, (255, 255, 255, 0)), (40.0, (240, 240, 245, 120)),
        (80.0, (225, 225, 235, 210)), (100.0, (210, 210, 220, 240)))),
)
BY_KEY = {field.key: field for field in FIELDS}

Grid = namedtuple("Grid", "values west north step run hour box")
Grid.__doc__ = """Поле на сетке широт и долгот.

values - (строки, столбцы) float32, строки с севера на юг. west, north -
центр левого верхнего узла, step - шаг в градусах. run - выпуск модели
(секунды UTC), hour - час прогноза. box - (юг, север, запад, восток)
для ResultTiles.
"""


# Выпуски и часы.

def hours():
    """Часы прогноза GFS: до HOURLY по одному, дальше через три."""
    return list(range(0, HOURLY + 1)) + list(range(HOURLY + 3, LAST + 1, 3))


def run_time(seconds):
    """Выпуск модели не позже момента seconds, секунды UTC."""
    step = CYCLE * 3600
    return math.floor(seconds / step) * step


def candidate_runs(now):
    """Выпуски, которые стоит пробовать к моменту now: самый свежий
    из тех, что уже могли выложить, и RUNS_BACK прежних."""
    newest = run_time(now - DELAY * 3600)
    return [newest - n * CYCLE * 3600 for n in range(RUNS_BACK + 1)]


def pick_hour(run, moment):
    """Час прогноза выпуска run, ближайший к моменту moment. Момент до
    выпуска - час 0, после последнего часа - последний."""
    offset = (moment - run) / 3600.0
    best = min(hours(), key=lambda h: (abs(h - offset), h))
    return best


def source_run(newest, moment):
    """Выпуск для момента: прошлое - выпуск не позже момента, будущее -
    самый свежий выложенный newest."""
    return min(newest, run_time(moment))


def step_moment(run, moment, delta):
    """Момент соседнего часа прогноза выпуска run, шаг шкалы времени.
    None - за краем ряда."""
    all_hours = hours()
    hour = pick_hour(run, moment)
    index = all_hours.index(hour) + delta
    if not 0 <= index < len(all_hours):
        return None
    return run + all_hours[index] * 3600.0


def file_url(run, hour):
    day = datetime.datetime.fromtimestamp(run, datetime.timezone.utc)
    return FILE.format(bucket=BUCKET, day=day.strftime("%Y%m%d"),
                       hour=day.hour, step=hour)


def byte_range(index_text, field, hour):
    """Диапазон байт (начало, конец включительно) строк поля field часа
    hour в индексе .idx или None. Строки поля идут подряд (U и V ветра),
    берётся весь их участок. Час 0 - анализ «anl», прочие - «N hour
    fcst», осреднённые за промежуток строки не берутся."""
    kind = "anl" if hour == 0 else "{} hour fcst".format(hour)
    lines = [line for line in str(index_text).splitlines() if line.strip()]
    starts = []
    for line in lines:
        parts = line.split(":")
        try:
            starts.append(int(parts[1]))
        except (IndexError, ValueError):
            starts.append(None)
    found = []
    for want in field.lines:
        for n, line in enumerate(lines):
            if want in line and line.rstrip(":").endswith(":" + kind):
                found.append(n)
                break
        else:
            return None
    first, last = min(found), max(found)
    if starts[first] is None:
        return None
    end = starts[last + 1] - 1 if last + 1 < len(starts) \
        and starts[last + 1] is not None else None
    return starts[first], end


def values_of(field, bands):
    """Значения поля из массивов полос файла: ветер - скорость по U
    и V, прочее - первая полоса с множителем."""
    if field.key == "wind":
        u, v = bands[0], bands[1]
        return np.hypot(u, v).astype(np.float32)
    return (np.asarray(bands[0], dtype=np.float32) * field.scale)


def make_grid(values, geo, run, hour):
    """Grid из массива и геопреобразования GDAL (центры узлов)."""
    west = geo[0] + geo[1] / 2.0
    north = geo[3] + geo[5] / 2.0
    return Grid(np.asarray(values, dtype=np.float32), west, north,
                abs(geo[1]), run, hour, (-90.0, 90.0, -180.0, 180.0))


def sample(grid, lats, lons):
    """Значения поля в точках, билинейно, долгота по кругу."""
    rows, cols = grid.values.shape
    y = (grid.north - np.asarray(lats, dtype=np.float64)) / grid.step
    x = ((np.asarray(lons, dtype=np.float64) - grid.west) / grid.step) \
        % cols
    y = np.clip(y, 0.0, rows - 1.0)
    y0 = np.minimum(np.floor(y).astype(np.int64), rows - 2)
    x0 = np.floor(x).astype(np.int64) % cols
    x1 = (x0 + 1) % cols
    fy = y - y0
    fx = x - np.floor(x)
    v = grid.values
    top = v[y0, x0] * (1.0 - fx) + v[y0, x1] * fx
    bottom = v[y0 + 1, x0] * (1.0 - fx) + v[y0 + 1, x1] * fx
    return top * (1.0 - fy) + bottom * fy


def colorize(field, values):
    """RGBA uint8 по раскраске поля, без премножения."""
    stops = np.array([s for s, _ in field.ramp], dtype=np.float64)
    colors = np.array([c for _, c in field.ramp], dtype=np.float64)
    flat = np.asarray(values, dtype=np.float64).ravel()
    out = np.empty((flat.size, 4), dtype=np.float64)
    for channel in range(4):
        out[:, channel] = np.interp(flat, stops, colors[:, channel])
    if field.clear is not None:
        out[flat < field.clear, 3] = 0.0
    out[~np.isfinite(flat)] = 0.0
    return np.rint(out).astype(np.uint8).reshape(
        np.shape(values) + (4,))


Job = namedtuple("Job", "field grid box")
Job.__doc__ = """Поле для ResultTiles: Field, Grid и рамка всего мира."""


def job(field, grid):
    return Job(field, grid, grid.box)


def tile_rgba(task, lats, lons, radius=None):
    """Картинка тайла для ResultTiles: task - Job."""
    rgba = colorize(task.field, sample(task.grid, lats, lons))
    return overlay_rgba(rgba, OPACITY)


def legend(field):
    """Шкала поля для legend.ThemeLegend: полоса цветов с подписями."""
    stops = [s for s, _ in field.ramp]
    lo, hi = stops[0], stops[-1]
    colors = [tuple(int(v) for v in colorize(field, np.array([value]))[0][:3])
              for value in np.linspace(lo, hi, 64)]

    def text(value):
        return "{:g}".format(value)
    return {"kind": "continuous", "units": field.units, "colors": colors,
            "labels": [((s - lo) / (hi - lo), text(s)) for s in stops],
            "names": []}


def valid_text(run, hour):
    """Срок поля: момент UTC, на который дан прогноз."""
    return datetime.datetime.fromtimestamp(
        run + hour * 3600, datetime.timezone.utc).strftime("%Y-%m-%d %H:00")
