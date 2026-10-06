# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Погода на глобусе: поля прогноза GFS и прогноз MET Norway в точке.

Расчёт и адреса - core/weather.py. Поле - тема группы «Погода» раздела
«Слои», оно занимает место темы NASA (слой вида «theme»), тема одна
на все группы. Час прогноза берётся из момента шкалы времени, шаги
шкалы идут по часам прогноза. Поле просится так: индекс .idx файла
часа, затем его участок заголовком Range. GRIB2 читает GDAL из QGIS
в главном потоке, это 0.05 с. Поля помнятся в памяти, не больше
MAX_GRIDS, по 4 МБ.

Прогноз в точке - окно «Погода здесь» по пункту меню на глобусе.
"""
import time
import uuid
from collections import OrderedDict

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog, QLabel, QTableWidget,
                                 QTableWidgetItem, QTabWidget, QVBoxLayout)

from ..core import ellipsoid, weather
from ..i18n import tr
from ..net.overlay import fetch_bytes, fetch_json
from ..qt_compat import enum
from .viewshed import ResultTiles

MAX_GRIDS = 12
LEVEL = 6  # уровень тайлов поля: пиксель около 2.4 км, сетка 28 км
PAST_DAYS = 10  # шкала погоды уходит в прошлое на столько суток


def field_names():
    """Поле: ключ темы - (название, подсказка)."""
    return {
        "weather_temperature": (tr("Температура воздуха"), tr(
            "Температура воздуха на высоте 2 м по модели NOAA GFS, шаг "
            "сетки 0.25°, около 28 км. Прогноз - до 16 суток вперёд, "
            "прошлое - анализ модели. Момент задаёт шкала времени.")),
        "weather_precipitation": (tr("Осадки"), tr(
            "Интенсивность осадков в момент шкалы по модели NOAA GFS, "
            "мм/ч. Слабее 0.1 мм/ч поле прозрачно.")),
        "weather_wind": (tr("Ветер"), tr(
            "Скорость ветра на высоте 10 м по модели NOAA GFS, м/с.")),
        "weather_clouds": (tr("Облачность"), tr(
            "Общая облачность по модели NOAA GFS, доля неба в процентах. "
            "Это расчёт модели, а не снимок облаков.")),
    }


def units_text(field):
    """Единицы поля на языке интерфейса."""
    return {"мм/ч": tr("мм/ч"), "м/с": tr("м/с")}.get(field.units,
                                                      field.units)


def field_of(key):
    """Field поля темы key или None, если тема не погодная."""
    if not key.startswith("weather_"):
        return None
    return weather.BY_KEY.get(key[len("weather_"):])


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
        self.grids = OrderedDict()  # (выпуск, час, поле) - Grid
        self.replies = {}
        self.moment = None
        self.wanted = None
        self.shown = None
        self.error = ""
        self._tried = []

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
        if self.newest is None:
            self._find_run()
            return
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
        час его прогноза. None - выпуск ещё не найден."""
        if self.newest is None:
            return None
        return (self.newest - PAST_DAYS * 86400.0,
                self.newest + weather.LAST * 3600.0)

    def step(self, moment, delta):
        """Момент соседнего часа: в прошлом и в первых сутках - по часу,
        в дальнем прогнозе - по часам свежего выпуска."""
        if self.newest is None:
            return None
        hourly = self.newest + weather.HOURLY * 3600.0
        target = round(moment / 3600.0) * 3600.0 + delta * 3600.0
        if target <= hourly:
            low, _ = self.span()
            return target if target >= low else None
        return weather.step_moment(self.newest, moment, delta)

    # Загрузка.

    def _find_run(self):
        """Свежий выложенный выпуск: индекс часа 0 по порядку
        кандидатов, первый ответивший."""
        if "find" in self.replies:
            return
        if not self._tried:
            self._tried = weather.candidate_runs(time.time())
        run = self._tried[0]
        self.replies["find"] = fetch_bytes(
            weather.file_url(run, 0) + ".idx",
            lambda data, error, run=run: self._found(run, data, error))
        self._count()

    def _found(self, run, data, error):
        if self.replies.pop("find", None) is None:
            return
        self._count()
        if data:
            self.indexes[(run, 0)] = data.decode("ascii", "replace")
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
                self.replies[name] = fetch_bytes(
                    weather.file_url(run, hour) + ".idx",
                    lambda data, error, run=run, hour=hour:
                    self._index_done(run, hour, data, error))
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
        self.replies[name] = fetch_bytes(
            weather.file_url(run, hour),
            lambda data, error, name=name: self._grid_done(name, data,
                                                           error),
            headers={"Range": value})
        self._count()

    def _index_done(self, run, hour, data, error):
        if self.replies.pop(("idx", run, hour), None) is None:
            return
        self._count()
        if data is None:
            self.error = tr("Индекс прогноза не получен: {error}",
                            error=error)
            self.changed.emit()
            return
        self.indexes[(run, hour)] = data.decode("ascii", "replace")
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
        field = weather.BY_KEY[self.wanted[2]]
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
        return weather.make_grid(weather.values_of(field, bands), geo,
                                 run, hour)
    finally:
        gdal.Unlink(path)


# Прогноз в точке.

def symbol_text(code):
    """Погода словами по коду MET: «lightrain_day» - «небольшой дождь»."""
    base = weather.symbol_base(code)
    thunder = base.endswith("andthunder")
    if thunder:
        base = base[:-len("andthunder")]
    words = {
        "clearsky": tr("ясно"), "fair": tr("малооблачно"),
        "partlycloudy": tr("переменная облачность"),
        "cloudy": tr("облачно"), "fog": tr("туман"),
        "lightrain": tr("небольшой дождь"), "rain": tr("дождь"),
        "heavyrain": tr("сильный дождь"),
        "lightrainshowers": tr("небольшой ливень"),
        "rainshowers": tr("ливень"), "heavyrainshowers": tr("сильный ливень"),
        "lightsleet": tr("небольшой мокрый снег"),
        "sleet": tr("мокрый снег"), "heavysleet": tr("сильный мокрый снег"),
        "lightsleetshowers": tr("заряды мокрого снега"),
        "sleetshowers": tr("заряды мокрого снега"),
        "heavysleetshowers": tr("заряды мокрого снега"),
        "lightsnow": tr("небольшой снег"), "snow": tr("снег"),
        "heavysnow": tr("сильный снег"),
        "lightsnowshowers": tr("снежные заряды"),
        "snowshowers": tr("снежные заряды"),
        "heavysnowshowers": tr("снежные заряды")}
    text = words.get(base, base)
    return tr("{weather}, гроза", weather=text) if thunder else text


def direction_text(degrees):
    """Откуда дует ветер: «С», «СВ» и так далее."""
    if degrees is None:
        return ""
    names = (tr("С"), tr("СВ"), tr("В"), tr("ЮВ"), tr("Ю"), tr("ЮЗ"),
             tr("З"), tr("СЗ"))
    return names[int((float(degrees) + 22.5) % 360.0 // 45.0)]


def number(value, digits=0):
    return "" if value is None else "{:.{}f}".format(value, digits)


HOURS_SHOWN = 48  # строк прогноза по часам


class PointForecast(QDialog):
    """Окно «Погода здесь»: прогноз MET Norway по часам и по суткам."""

    def __init__(self, parent, lat, lon):
        super().__init__(parent)
        self.setWindowTitle(tr("Погода здесь"))
        self.resize(560, 520)
        layout = QVBoxLayout(self)
        self.place = QLabel("{:.4f}, {:.4f}".format(lat, lon), self)
        layout.addWidget(self.place)
        self.tabs = QTabWidget(self)
        self.hours = self._table([tr("Время"), tr("Погода"), tr("°C"),
                                  tr("Осадки, мм"), tr("Ветер, м/с"),
                                  tr("Облачность, %")])
        self.days = self._table([tr("Сутки"), tr("°C мин"), tr("°C макс"),
                                 tr("Осадки, мм"), tr("Ветер до, м/с")])
        self.tabs.addTab(self.hours, tr("По часам"))
        self.tabs.addTab(self.days, tr("По суткам"))
        layout.addWidget(self.tabs)
        self.status = QLabel(tr("Прогноз загружается…"), self)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        credit = QLabel('<a href="{}">{}</a>'.format(
            weather.MET_ATTRIBUTION[1], tr(
                "Данные: MET Norway, лицензия CC BY 4.0")), self)
        credit.setOpenExternalLinks(True)
        layout.addWidget(credit)
        self.reply = fetch_json(weather.met_url(lat, lon), self._done)

    def _table(self, headers):
        table = QTableWidget(0, len(headers), self)
        table.setHorizontalHeaderLabels(headers)
        table.setEditTriggers(enum(QTableWidget, "EditTrigger",
                                   "NoEditTriggers"))
        table.verticalHeader().setVisible(False)
        return table

    def _done(self, data, error):
        self.reply = None
        rows = weather.parse_met(data) if data is not None else []
        if not rows:
            self.status.setText(tr("Прогноз не получен: {error}",
                                   error=error or tr("пустой ответ")))
            return
        self.rows = rows
        offset = -time.altzone if time.localtime().tm_isdst \
            else -time.timezone
        self._fill(self.hours, [
            (time.strftime("%d.%m %H:%M", time.localtime(row.time)),
             symbol_text(row.symbol), number(row.temperature, 1),
             number(row.precipitation, 1),
             "{} {}".format(number(row.wind, 1),
                            direction_text(row.direction)).strip(),
             number(row.clouds))
            for row in rows[:HOURS_SHOWN]])
        self._fill(self.days, [
            (time.strftime("%a %d.%m", time.localtime(day + 43200)),
             number(low, 1), number(high, 1), number(rain, 1),
             number(wind, 1))
            for day, low, high, rain, wind in weather.daily(rows, offset)])
        self.status.setText(tr(
            "Время - часы компьютера. Прогноз до {last}.",
            last=time.strftime("%d.%m %H:%M", time.localtime(
                rows[-1].time))))

    @staticmethod
    def _fill(table, rows):
        table.setRowCount(len(rows))
        align = enum(Qt, "AlignmentFlag", "AlignCenter")
        for r, values in enumerate(rows):
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if c:
                    item.setTextAlignment(align)
                table.setItem(r, c, item)
        table.resizeColumnsToContents()

    def closeEvent(self, event):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()
        super().closeEvent(event)
