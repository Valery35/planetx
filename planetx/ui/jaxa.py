# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Данные JAXA» подменю «Анализ участка»: наборы JAXA Earth по
участку за месяцы.

Слово автора от 9 ноября 2026 года «JAXA в анализ». Набор и месяцы
выбираются в окне, «Построить» читает файлы COG уровня 1 под участком
(core/jaxa.py) мостом сети модуля (net/ranges.py) в рабочем потоке,
месяцы - в MONTH_WORKERS потоков. График - медиана участка по месяцам
и отрезок от 10-го до 90-го процентиля (график окна «Ряд по датам»,
ui/series.py). Щелчок по точке выбирает месяц. OK пишет в проект растр
выбранного месяца и таблицу ряда, «Карта тренда» - наклон Тейла-Сена
за год по пикселям (core/trend.py) по всем месяцам или по одному
месяцу года. На глобусе наборы показывает PlanetX Lite, здесь показа
нет: на глобусе виден только контур участка.
"""
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
from qgis.core import QgsProject, QgsVectorLayer
from qgis.PyQt.QtCore import QObject, QTimer, QUrl
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QFormLayout, QHBoxLayout,
                                 QLabel, QPushButton, QVBoxLayout)

from .. import journal
from ..core import cog, jaxa, stats, trend
from ..i18n import tr
from ..net import ranges
from ..net.overlay import fetch_bytes
from ..qt_compat import enum
from .aef import _poll_job, _run_job, stop_point
from .area import Area
from .export import add_raster, write_grid
from .results import (Session, accepted, built_text, keep_buttons,
                      result_path, set_abstract, show_layer,
                      write_lat_lon)
from .series import TREND_RAMP, SeriesChart
from .viewshed import fit_status

SETTINGS = "PlanetX/jaxa/"
SIDE = 50.0  # км, участок по умолчанию
MOST = 1000.0  # км, наибольший участок
MONTHS = 36  # месяцев ряда по умолчанию - последние
MONTH_WORKERS = 6  # месяцев, читаемых сразу: время уходит на ответы сети
POLL = 100  # мс между проверками расчёта


def set_titles():
    """Названия наборов окна по ключам."""
    return {
        "lst": tr("Температура поверхности суши днём, SGLI"),
        "sst": tr("Температура поверхности моря днём, SGLI"),
        "ndvi": tr("Вегетационный индекс NDVI, SGLI"),
        "chla": tr("Хлорофилл-а в воде, SGLI"),
        "precip": tr("Осадки GSMaP, средняя интенсивность"),
        "smc": tr("Влажность почвы, AMSR2"),
        "aod": tr("Оптическая толща аэрозоля, MODIS"),
    }


def unit_text(dataset):
    """Единица набора для подписей, пусто у безразмерных."""
    return {"°C": "°C", "мг/м³": tr("мг/м³"), "мм/ч": tr("мм/ч"),
            "%": "%"}.get(dataset.units, "")


def value_label(dataset, value):
    """Значение набора с единицей через неразрывный пробел."""
    unit = unit_text(dataset)
    text = stats.rounded(value)
    return "{} {}".format(text, unit) if unit else text


class JaxaChart(SeriesChart):
    """График ряда набора: подписи в единицах набора, доля участка со
    значением вместо доли без облаков."""

    dataset = None

    def value_label(self, value):
        if self.dataset is None:
            return super().value_label(value)
        return value_label(self.dataset, value)

    def hover_line(self, when, p):
        return tr("{when}: медиана {median}, 10-90 % {low} - {high}, "
                  "со значением {share} % участка", when=when,
                  median=self.value_label(p.median),
                  low=self.value_label(p.low), high=self.value_label(p.high),
                  share="{:.0f}".format(p.share))


class JaxaDialog(QDialog):
    """Окно «Данные JAXA»."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Данные JAXA"))
        self.point = None
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, SIDE, MOST, SETTINGS + "side")
        self.dataset = QComboBox(self)
        titles = set_titles()
        for dataset in jaxa.SETS:
            self.dataset.addItem(titles[dataset.key], dataset.key)
        self.dataset.setToolTip(tr(
            "Месячные наборы JAXA Earth на весь мир. Пиксель - около 2.8 км "
            "у наборов SGLI, 5.5 км у аэрозоля, 11 км у осадков и влажности "
            "почвы."))
        self.first = QComboBox(self)
        self.last = QComboBox(self)
        for box in (self.first, self.last):
            box.setToolTip(tr(
                "Месяцы ряда. Один месяц набора - около 0.1-1 МБ под "
                "участком."))
        period = QHBoxLayout()
        period.addWidget(self.first, 1)
        period.addWidget(QLabel("-", self))
        period.addWidget(self.last, 1)
        form = QFormLayout()
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Набор"), self.dataset)
        form.addRow(tr("Месяцы"), period)
        hint = QLabel(tr(
            "Наблюдения Земли JAXA по месяцам - медиана участка, разброс "
            "и растры в проект QGIS. Источник - JAXA Earth, "
            "data.earth.jaxa.jp."), self)
        hint.setWordWrap(True)
        self.chart = JaxaChart(self)
        self.chart.setMinimumSize(520, 220)
        self.season = QCheckBox(tr("Один месяц года"), self)
        self.season.setToolTip(tr(
            "Карта тренда только по месяцам того же месяца года, что "
            "у выбранного: тренд между годами без сезонного хода."))
        self.season.setChecked(True)
        buttons = QDialogButtonBox(self)
        self.run = QPushButton(tr("Построить"), self)
        self.run.setDefault(True)
        self.run.setToolTip(tr(
            "Читает месяцы набора под участком и строит ряд: точка - "
            "медиана участка, отрезок - от 10-го до 90-го процентиля."))
        self.trend = QPushButton(tr("Карта тренда…"), self)
        self.trend.setToolTip(tr(
            "Тренд набора в каждом пикселе участка по месяцам ряда - наклон "
            "Тейла-Сена за год и значимость по тесту Манна-Кендалла, "
            "растром в проект QGIS. Пиксель без {count} месяцев со "
            "значением тренда не получает.", count=trend.MIN_SCENES))
        self.trend.setEnabled(False)
        for button in (self.run, self.trend):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        self.to_project.setToolTip(tr(
            "Записать в проект QGIS растр выбранного месяца и таблицу ряда "
            "и закрыть окно. Месяц выбирается щелчком по точке графика, "
            "без щелчка - последний со значением."))
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.season)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def current(self):
        return jaxa.BY_KEY.get(self.dataset.currentData())

    def set_dates(self, dates):
        """Месяцы набора в списках периода: по умолчанию последние
        MONTHS."""
        for box in (self.first, self.last):
            box.blockSignals(True)
            box.clear()
            for date in dates:
                box.addItem(date, date)
            box.blockSignals(False)
        if dates:
            self.first.setCurrentIndex(max(0, len(dates) - MONTHS))
            self.last.setCurrentIndex(len(dates) - 1)

    def period(self):
        first, last = self.first.currentData(), self.last.currentData()
        if not first or not last:
            return None
        return (first, last) if first <= last else (last, first)


class JaxaTool(QObject):
    """Наборы JAXA Earth по участку у окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.job = None
        self.stopped = None
        self.replies = []
        self.dates = {}  # ключ набора - месяцы
        self.months = []  # ряд: jaxa.Month
        self.built = None  # набор, сетка, кольцо и рамка ряда
        self.chosen = None  # месяц, выбранный щелчком
        self.progress = [0, 0]
        self.trend_job = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._tick)
        self.session = Session(window, tr("Данные JAXA"))

    def open_here(self, lat, lon):
        """Окно для точки - пункт подменю «Анализ участка»."""
        dialog = self.dialog
        if dialog is None:
            dialog = JaxaDialog(self.window)
            dialog.run.clicked.connect(lambda _=False: self.build())
            dialog.trend.clicked.connect(lambda _=False: self.make_trend())
            dialog.dataset.currentIndexChanged.connect(
                lambda _: self._load_dates())
            dialog.chart.picked.connect(self._pick)
            dialog.finished.connect(self._closed)
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        self._load_dates()
        return dialog

    # --- месяцы набора ---------------------------------------------------

    def _load_dates(self):
        dialog = self.dialog
        dataset = dialog.current()
        if dataset is None:
            return
        if dataset.key in self.dates:
            dialog.set_dates(self.dates[dataset.key])
            return
        dialog.set_dates([])
        dialog.status.setText(tr("Месяцы набора…"))
        self.replies.append(fetch_bytes(
            jaxa.collection_url(dataset),
            lambda data, error: self._dates(dataset, data, error),
            prefer_cache=False))

    def _dates(self, dataset, data, error):
        dialog = self.dialog
        if dialog is None:
            return
        dates = jaxa.parse_dates(data.decode("utf-8", "replace")) \
            if data else []
        if not dates:
            dialog.status.setText(tr("Каталог JAXA не ответил: {error}",
                                     error=error or "-"))
            return
        self.dates[dataset.key] = dates
        if dialog.current() is dataset:
            dialog.set_dates(dates)
            dialog.status.setText(tr(
                "Месяцев в наборе: {count}, с {first} по {last}.",
                count=len(dates), first=dates[0], last=dates[-1]))

    # --- расчёт ----------------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or self.job is not None:
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        dataset = dialog.current()
        period = dialog.period()
        if dataset is None or period is None:
            dialog.status.setText(tr("Нет месяцев набора."))
            return
        dates = jaxa.between(self.dates.get(dataset.key, []), *period)
        ring = list(dialog.area.ring)
        box = dialog.area.box()
        grid = jaxa.grid_for(box, dataset.step)
        mask = jaxa.area_mask(grid, dialog.area.inside)
        ranges.bridge()
        self.progress = [0, len(dates)]
        progress = self.progress

        def work():
            return read_months(dataset, dates, grid, mask, progress,
                               lambda: stop_point(self))

        dialog.status.setText(tr("Чтение месяцев: {done} из {total}…",
                                 done=0, total=len(dates)))
        _run_job(self, work, lambda months: self._built(
            months, dataset, grid, ring, box), tr("Данные JAXA"))

    def _tick(self):
        dialog = self.dialog
        if self.job is not None and dialog is not None:
            done, total = self.progress
            dialog.status.setText(tr("Чтение месяцев: {done} из {total}…",
                                     done=done, total=total))
        _poll_job(self)

    def _built(self, months, dataset, grid, ring, box):
        dialog = self.dialog
        if dialog is None:
            return
        self.months = months
        self.built = (dataset, grid, ring, box)
        self.chosen = None
        shown = [m for m in months if m.point is not None]
        dialog.chart.dataset = dataset
        dialog.chart.set_rows([(m.day, m.date, m.date, m.point)
                               for m in shown], dataset.key)
        dialog.to_project.setEnabled(bool(shown))
        dialog.trend.setEnabled(len(shown) >= trend.MIN_SCENES)
        if not shown:
            dialog.status.setText(tr(
                "Значений набора на участке нет за {count} месяцев: участок "
                "вне набора, например суша у набора моря.",
                count=len(months)) + " " + built_text())
            return
        last = shown[-1]
        dialog.status.setText(tr(
            "Месяцев со значением {shown} из {count}. Последний {date} - "
            "медиана {median}.", shown=len(shown), count=len(months),
            date=last.date, median=value_label(dataset, last.point.median))
            + " " + built_text())

    def _pick(self, date):
        month = next((m for m in self.months if m.date == date), None)
        if month is None or self.dialog is None or self.built is None:
            return
        self.chosen = date
        self.dialog.status.setText(tr(
            "Выбран месяц {date}: медиана {median}. OK запишет его растр.",
            date=date, median=value_label(self.built[0],
                                          month.point.median)))

    def chosen_month(self):
        """Месяц для растра: выбранный щелчком или последний со
        значением."""
        shown = [m for m in self.months if m.point is not None]
        if not shown:
            return None
        return next((m for m in shown if m.date == self.chosen), shown[-1])

    # --- тренд -----------------------------------------------------------

    def make_trend(self):
        dialog = self.dialog
        month = self.chosen_month()
        if dialog is None or month is None or self.trend_job is not None:
            return
        chosen = [m for m in self.months if m.point is not None]
        if dialog.season.isChecked():
            chosen = jaxa.same_month(chosen, month.date)
        if len(chosen) < trend.MIN_SCENES:
            dialog.status.setText(tr(
                "Для тренда нужно не меньше {count} месяцев со значением, "
                "в ряду {have}. Расширьте период или снимите флажок «Один "
                "месяц года».", count=trend.MIN_SCENES, have=len(chosen)))
            return
        stack = np.stack([m.values for m in chosen])
        days = [m.day for m in chosen]
        pool = ThreadPoolExecutor(max_workers=1)
        self.trend_job = (pool.submit(trend.trend, stack, days), chosen)
        pool.shutdown(wait=False)
        dialog.trend.setEnabled(False)
        dialog.status.setText(tr("Считается карта тренда по {count} "
                                 "месяцам…", count=len(chosen)))
        QTimer.singleShot(POLL, self._trend_poll)

    def _trend_poll(self):
        job, chosen = self.trend_job
        if not job.done():
            QTimer.singleShot(POLL, self._trend_poll)
            return
        self.trend_job = None
        dialog = self.dialog
        if dialog is None or self.built is None:
            return
        dialog.trend.setEnabled(True)
        slope, p_value, count = job.result()
        dataset, grid, ring, _ = self.built
        shown = np.isfinite(slope)
        total = int(shown.sum())
        if not total:
            dialog.status.setText(tr("Тренда нет ни в одном пикселе."))
            return
        path = result_path("jaxa_trend_" + dataset.key)
        west = grid.west - grid.step / 2.0
        north = grid.north + grid.step / 2.0
        frame = (west, north - grid.rows * grid.step,
                 west + grid.cols * grid.step, north)
        if write_grid(path, [slope, p_value, count.astype(float)],
                      grid.west, grid.north, grid.step, frame) is None:
            dialog.status.setText(tr("Растры не записаны в «{path}».",
                                     path=path))
            return
        low, high = trend.limits(slope)
        colors = TREND_RAMP[::-1] if dataset.units == "°C" else TREND_RAMP
        stops = [(low, colors[0]), (0.0, colors[1]), (high, colors[2])]
        name = set_titles()[dataset.key]
        title = tr("Тренд «{name}» {first} - {last}, за год", name=name,
                   first=chosen[0].date, last=chosen[-1].date)
        significant = int((p_value[shown] < trend.SIGNIFICANT).sum())
        note = tr(
            "Пикселей с трендом {total}, значимых (p < {p}) {share} %, "
            "медиана наклона {median} за год.", total=total,
            p=trend.SIGNIFICANT,
            share="{:.0f}".format(100.0 * significant / total),
            median=value_label(dataset, float(np.median(slope[shown]))))
        layer = add_raster(path, title, stops,
                           group=self.session.group_for(ring),
                           abstract=" ".join((note, credit_text())))
        show_layer(self.window, layer)
        dialog.status.setText(tr("Карта тренда в проекте.") + " " + note)

    # --- выгрузка --------------------------------------------------------

    def _closed(self, code=0):
        if accepted(code):
            self.export()
        self.stop()
        self.session.reset()
        self.months = []
        self.built = None
        self.replies = []
        self.dialog.chart.set_rows([], "")
        self.dialog.to_project.setEnabled(False)
        self.dialog.trend.setEnabled(False)
        self.dialog.area.end()

    def export(self):
        """Растр выбранного месяца и таблица ряда в подгруппу расчёта."""
        month = self.chosen_month()
        if month is None or self.built is None:
            return None
        dataset, grid, ring, _ = self.built
        name = set_titles()[dataset.key]
        group = self.session.group_for(ring)
        path = result_path("jaxa_{}_{}".format(dataset.key, month.date))
        if not write_lat_lon(path, month.values, grid.north, grid.west,
                             grid.step, grid.step):
            return None
        unit = unit_text(dataset)
        layer = add_raster(
            path, tr("{name}, {date}", name=name, date=month.date),
            list(dataset.stops), group=group,
            abstract=" ".join((tr("Медиана участка {median}.",
                                  median=value_label(dataset,
                                                     month.point.median)),
                               credit_text())))
        show_layer(self.window, layer)
        table = result_path("jaxa_{}_series".format(dataset.key), ".csv")
        title = "{} ({})".format(name, unit) if unit else name
        try:
            with open(table, "w", encoding="utf-8", newline="") as fh:
                fh.write(jaxa.csv_text(dataset, self.months, title))
        except OSError as error:
            journal.note("jaxa csv {}: {}".format(table, error))
            return path
        add_table(table, tr("Ряд «{name}» {first} - {last}", name=name,
                            first=self.months[0].date,
                            last=self.months[-1].date), group)
        return path

    def stop(self):
        if self.stopped is not None:
            self.stopped.set()
        self.job = None
        self.timer.stop()
        self.window.spinner.set_job("aef:" + type(self).__name__)

    def close(self):
        self.stop()
        self.replies = []
        if self.dialog is not None:
            self.dialog.close()


def credit_text():
    return tr("Данные - {credit}, {url}.", credit=jaxa.CREDIT,
              url=jaxa.CREDIT_URL)


def add_table(path, title, group):
    """Таблица CSV без геометрии слоем проекта в группу group."""
    uri = "{}?type=csv&detectTypes=yes&geomType=none".format(
        QUrl.fromLocalFile(path).toString())
    layer = QgsVectorLayer(uri, title, "delimitedtext")
    if not layer.isValid():
        return None
    set_abstract(layer, [credit_text()])
    QgsProject.instance().addMapLayer(layer, False)
    group.addLayer(layer)
    return layer


def read_months(dataset, dates, grid, mask, progress, tick):
    """Месяцы dates набора по участку в рабочем потоке: MONTH_WORKERS
    месяцев сразу. progress[0] - готово месяцев, tick() останавливает
    расчёт исключением."""
    lock = threading.Lock()

    def one(date):
        tick()
        files = {}

        def block(west, south, c0, r0, c1, r1):
            url = jaxa.quad_url(dataset, date, west, south)
            if url not in files:
                files[url] = open_quad(dataset, url)
            found = files[url]
            return None if found is None \
                else found.pixels(0, c0, r0, c1, r1)

        month = jaxa.month_of(dataset, date, grid, mask, block)
        with lock:
            progress[0] += 1
        return month

    with ThreadPoolExecutor(max_workers=MONTH_WORKERS) as pool:
        futures = [pool.submit(one, date) for date in dates]
        months = []
        try:
            for future in as_completed(futures):
                months.append(future.result())
        finally:
            for future in futures:
                future.cancel()
    return sorted(months, key=lambda m: m.date)


def open_quad(dataset, url):
    """Файл квадрата или None - его нет на сервере. Файл не той сетки -
    CogError."""
    try:
        found = cog.Cog(lambda start, length: ranges.fetch(
            url, start, length), head=jaxa.HEAD, cache=4 << 20)
    except ranges.Missing:
        return None
    if not jaxa.step_fits(dataset, found.transform):
        raise cog.CogError("grid " + url)
    return found
