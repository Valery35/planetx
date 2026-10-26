# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Погода на глобусе: поля прогноза GFS.

Расчёт и адреса - core/weather.py. Поле - тема группы «Погода» раздела
«Слои», оно занимает место темы NASA (слой вида «theme»), тема одна
на все группы. Час прогноза берётся из момента шкалы времени, шаги
шкалы идут по часам прогноза. Поле просится так: индекс .idx файла
часа, затем его участок заголовком Range. GRIB2 читает GDAL из QGIS
в главном потоке, это 0.05 с. Поля помнятся в памяти, не больше
MAX_GRIDS, по 4 МБ.

Прогноз в точке по пункту «Погода здесь» убран 8 октября 2026 года,
см. AGENTS.md.
"""
import time
import uuid
from collections import OrderedDict

from qgis.PyQt.QtCore import QObject, pyqtSignal

from ..core import aurora, ellipsoid, weather
from ..core.mirrors import Mirrors
from ..i18n import tr
from ..net.overlay import fetch_bytes, fetch_mirror
from .viewshed import ResultTiles

MAX_GRIDS = 12
MIRRORS = Mirrors(weather.BUCKETS)  # зеркала GFS, одно состояние на QGIS
LEVEL = 6  # уровень тайлов поля: пиксель около 2.4 км, сетка 28 км
PAST_DAYS = 10  # шкала погоды уходит в прошлое на столько суток
AURORA = "weather_aurora"  # тема полярного сияния (core/aurora.py)
AURORA_WANTED = (0.0, 0, "aurora")  # ключ поля сияния в grids


def field_names():
    """Поле: ключ темы - (название, подсказка)."""
    return {
        "weather_temperature": (tr("Температура воздуха"), tr(
            "Температура воздуха на высоте 2 м по модели NOAA GFS, шаг "
            "сетки 0.25°, около 28 км. Прогноз - до 16 суток вперёд, "
            "прошлое - анализ модели. Момент задаёт шкала времени.")),
        "weather_precipitation": (tr("Осадки, прогноз GFS"), tr(
            "Интенсивность осадков в момент шкалы по модели NOAA GFS, "
            "мм/ч. Слабее 0.1 мм/ч поле прозрачно.")),
        "weather_wind": (tr("Ветер"), tr(
            "Скорость ветра на высоте 10 м по модели NOAA GFS, м/с.")),
        "weather_clouds": (tr("Облачность, прогноз GFS"), tr(
            "Общая облачность по модели NOAA GFS, доля неба в процентах. "
            "Это расчёт модели, а не снимок облаков.")),
        AURORA: (tr("Полярное сияние"), tr(
            "Вероятность видимого полярного сияния по модели OVATION "
            "службы NOAA SWPC на ближайшие 30-90 минут, сетка 1°. "
            "Прогноз один - на сейчас, шкала времени его не меняет. "
            "Огни городов на ночной стороне даёт строка «Солнце».")),
    }


def units_text(field):
    """Единицы поля на языке интерфейса."""
    return {"мм/ч": tr("мм/ч"), "м/с": tr("м/с")}.get(field.units,
                                                      field.units)


def value_text(field, value):
    """Число поля на глобусе: «7°», «1.2», «5», «80%». Единицы стоят
    в шкале поля в углу вида."""
    if field.key == "temperature":
        return "{:.0f}°".format(value).replace("-0°", "0°")
    if field.key == "precipitation":
        return "{:.1f}".format(value)
    if field.key in ("clouds", "aurora"):
        return "{:.0f}%".format(value)
    return "{:.0f}".format(value)


def field_of(key):
    """Field поля темы key или None, если тема не погодная."""
    if key == AURORA:
        return aurora.FIELD
    if not key.startswith("weather_"):
        return None
    return weather.BY_KEY.get(key[len("weather_"):])


def field_valid_text(field, grid):
    """Срок поля для шкалы и имени слоя."""
    if field.key == "aurora":
        return aurora.valid_text(grid)
    return weather.valid_text(grid.run, grid.hour)


def field_attribution(key):
    """Подпись источника поля темы key: (текст, адрес)."""
    return aurora.ATTRIBUTION if key == AURORA else weather.ATTRIBUTION


class WeatherManager(QObject):
    """Поле прогноза GFS на глобусе. Сигнал changed - поле показано,
    пришла ошибка или ждём данных."""

    changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.key = ""
        self.newest = None  # свежий выложенный выпуск, секунды UTC
        self.indexes = {}  # (выпуск, час) - текст индекса
        self.sources = {}  # (выпуск, час) - зеркало индекса
        self.grids = OrderedDict()  # (выпуск, час, поле) - Grid
        self.replies = {}
        self.moment = None
        self.wanted = None
        self.shown = None
        self.error = ""
        self._tried = []
        self._aurora_at = None  # time.monotonic() прихода прогноза сияния

    # Тема.

    def active(self):
        return bool(self.key)

    def show(self, key, moment):
        """Показать поле темы key на момент moment (None - сейчас)."""
        self.key = key
        self.shown = None
        self.error = ""
        self.set_moment(moment)

    def hide(self):
        self.key = ""
        self.wanted = None
        self.shown = None
        self._abort()

    def set_moment(self, moment):
        if not self.key:
            return
        self.moment = time.time() if moment is None else float(moment)
        if self.key == AURORA:
            self._aurora()
            return
        if self.newest is None:
            self._find_run()
            return
        # Момент вне ряда прогноза - край ряда. Шкала после исторической
        # карты стояла в 1813 году, и выпуск выходил до 1970 года.
        low, high = self.span()
        self.moment = min(max(self.moment, low), high)
        run = weather.source_run(self.newest, self.moment)
        hour = weather.pick_hour(run, self.moment)
        field = field_of(self.key)
        self.wanted = (run, hour, field.key)
        if self.wanted in self.grids:
            self.grids.move_to_end(self.wanted)
            self._display()
            return
        self._fetch(run, hour)

    def ready(self):
        """Показано ли поле нужного часа: показ по шкале ждёт этого."""
        return self.wanted is not None and self.wanted == self.shown

    def span(self):
        """Охват шкалы: PAST_DAYS суток до свежего выпуска и последний
        час его прогноза. None - выпуск ещё не найден. У сияния - час
        вокруг момента прогноза."""
        if self.key == AURORA:
            grid = self.grids.get(AURORA_WANTED)
            return None if grid is None else (grid.run - 3600.0,
                                              grid.run + 3600.0)
        if self.newest is None:
            return None
        return (self.newest - PAST_DAYS * 86400.0,
                self.newest + weather.LAST * 3600.0)

    def step(self, moment, delta):
        """Момент соседнего часа: в прошлом и в первых сутках - по часу,
        в дальнем прогнозе - по часам свежего выпуска. У сияния шагов
        нет."""
        if self.newest is None or self.key == AURORA:
            return None
        hourly = self.newest + weather.HOURLY * 3600.0
        target = round(moment / 3600.0) * 3600.0 + delta * 3600.0
        if target <= hourly:
            low, _ = self.span()
            return target if target >= low else None
        return weather.step_moment(self.newest, moment, delta)

    # Загрузка.

    def _aurora(self):
        """Прогноз сияния: из памяти, пока он моложе aurora.REFRESH,
        иначе запрос файла мимо кэша."""
        self.wanted = AURORA_WANTED
        fresh = self._aurora_at is not None \
            and time.monotonic() - self._aurora_at < aurora.REFRESH
        if fresh and AURORA_WANTED in self.grids:
            if self.shown != AURORA_WANTED:
                self._display()
            return
        if "aurora" in self.replies:
            return
        self.replies["aurora"] = fetch_bytes(
            aurora.URL, self._aurora_done, fresh=True)
        self._count()

    def _aurora_done(self, data, error):
        if self.replies.pop("aurora", None) is None:
            return
        self._count()
        grid = aurora.parse(data) if data else None
        if grid is None:
            self.error = tr("Прогноз сияния не получен: {error}",
                            error=error or tr("файл не прочитан"))
            self.changed.emit()
            return
        self.grids[AURORA_WANTED] = grid
        self._aurora_at = time.monotonic()
        if self.key == AURORA:
            self.wanted = AURORA_WANTED
            self.window._update_timebar()
            self._display()

    def _find_run(self):
        """Свежий выложенный выпуск: индекс часа 0 по порядку
        кандидатов, первый ответивший."""
        if "find" in self.replies:
            return
        if not self._tried:
            self._tried = weather.candidate_runs(time.time())
        run = self._tried[0]
        self.replies["find"] = fetch_mirror(
            MIRRORS, weather.file_path(run, 0) + ".idx",
            lambda data, error, base, run=run: self._found(run, data, error,
                                                           base))
        self._count()

    def _found(self, run, data, error, base):
        if self.replies.pop("find", None) is None:
            return
        self._count()
        if data:
            self.indexes[(run, 0)] = data.decode("ascii", "replace")
            self.sources[(run, 0)] = base
            self.newest = run
            self._tried = []
            self.window._update_timebar()
            self.set_moment(self.moment)
            return
        self._tried.pop(0)
        if self._tried:
            self._find_run()
            return
        self.error = tr("Прогноз GFS не найден: {error}", error=error)
        self.changed.emit()

    def _fetch(self, run, hour):
        index = self.indexes.get((run, hour))
        if index is None:
            name = ("idx", run, hour)
            if name not in self.replies:
                self.replies[name] = fetch_mirror(
                    MIRRORS, weather.file_path(run, hour) + ".idx",
                    lambda data, error, base, run=run, hour=hour:
                    self._index_done(run, hour, data, error, base))
                self._count()
            return
        field = field_of(self.key)
        found = weather.byte_range(index, field, hour)
        if found is None:
            self.error = tr("В файле прогноза нет поля «{name}».",
                            name=field_names()[self.key][0])
            self.changed.emit()
            return
        start, end = found
        name = ("grid", run, hour, field.key)
        if name in self.replies:
            return
        value = "bytes={}-{}".format(start, "" if end is None else end)
        self.replies[name] = fetch_mirror(
            MIRRORS, weather.file_path(run, hour),
            lambda data, error, base, name=name: self._grid_done(
                name, data, error),
            base=self.sources.get((run, hour)), headers={"Range": value})
        self._count()

    def _index_done(self, run, hour, data, error, base):
        if self.replies.pop(("idx", run, hour), None) is None:
            return
        self._count()
        if data is None:
            self.error = tr("Индекс прогноза не получен: {error}",
                            error=error)
            self.changed.emit()
            return
        self.indexes[(run, hour)] = data.decode("ascii", "replace")
        self.sources[(run, hour)] = base
        if self.wanted is not None and self.wanted[:2] == (run, hour):
            self._fetch(run, hour)

    def _grid_done(self, name, data, error):
        if self.replies.pop(name, None) is None:
            return
        self._count()
        _, run, hour, key = name
        if data is None:
            self.error = tr("Поле прогноза не получено: {error}",
                            error=error)
            self.changed.emit()
            return
        grid = read_grid(data, weather.BY_KEY[key], run, hour)
        if grid is None:
            self.error = tr("Поле прогноза не прочитано.")
            self.changed.emit()
            return
        self.grids[(run, hour, key)] = grid
        while len(self.grids) > MAX_GRIDS:
            self.grids.popitem(last=False)
        if self.wanted == (run, hour, key):
            self._display()

    def _display(self):
        grid = self.grids[self.wanted]
        key = self.wanted[2]
        field = aurora.FIELD if key == "aurora" else weather.BY_KEY[key]
        tiles = ResultTiles(weather.job(field, grid), ellipsoid.A,
                            weather.tile_rgba, parent=self.window)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("theme", key, levels))
        self.shown = self.wanted
        self.error = ""
        self.window._show_weather_tiles(tiles, field, grid)
        self.changed.emit()

    def _count(self):
        """Ждущие ответы - в счётчик загрузки вида."""
        count = len(self.replies)
        counted = getattr(self, "_counted", 0)
        self.view.data_pending = max(
            0, self.view.data_pending + count - counted)
        self._counted = count

    def _abort(self):
        replies, self.replies = self.replies, {}
        self._count()
        for reply in replies.values():
            reply.abort()

    def close(self):
        self._abort()


def read_grid(data, field, run, hour):
    """Grid из байтов GRIB2 через GDAL или None. Файл - в памяти GDAL,
    своё имя на каждый вызов."""
    from osgeo import gdal
    path = "/vsimem/planetx_{}.grib2".format(uuid.uuid4().hex)
    gdal.FileFromMemBuffer(path, bytes(data))
    try:
        dataset = gdal.Open(path)
        if dataset is None or dataset.RasterCount < len(field.lines):
            return None
        bands = [dataset.GetRasterBand(n + 1).ReadAsArray()
                 for n in range(len(field.lines))]
        if any(band is None for band in bands):
            return None
        geo = dataset.GetGeoTransform()
        dataset = None
        return weather.make_grid(
            weather.values_of(field, bands), geo, run, hour,
            bands if field.key == "wind" else None)
    finally:
        gdal.Unlink(path)
