# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Изменения местности по эмбеддингам AlphaEarth: строка «Изменения
местности» раздела «Слои» и окно «Изменения местности».

Расчёт - core/aef.py. Файлы COG Google читаются частями мостом сети
модуля (net/ranges.py), сжатие ZSTD раскодирует библиотека zstd из
состава QGIS через ctypes. Указатель файлов зоны - planetx-terrain/aef.
Показ - слой вида «emag», общий с картами значений, Macrostrat
и картами картинками: на глобусе одна такая карта. Обзор вида идёт
сам, подробный участок задаёт окно многоугольником (ui/area.py), вне
него подробных значений нет: загрузка блока полного разрешения - около
40 МБ на год, окно называет объём до неё.
"""
import ctypes
import ctypes.util
import os
import sys
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QLabel,
                                 QPushButton, QVBoxLayout)

from .. import journal
from ..core import aef, cog
from ..core.coords import from_utm
from ..core.mipmap import mip_chain
from ..i18n import tr
from ..net import ranges
from ..qt_compat import enum
from .area import Area
from .export import add_raster
from .hydro import _spin
from .results import (Session, accepted, add_vector, built_text,
                      keep_buttons,
                      result_path, show_layer, write_vector)
from .threadtiles import ThreadTiles
from .viewshed import fit_status

LAYER = "emag"  # слой вида, общий с картами значений
KEY = "aef_change"  # строка раздела «Слои»
# Указатели зон: planetx-terrain, шаги проверки ставят локальную копию.
INDEX_BASE = "https://raw.githubusercontent.com/Valery35/planetx-terrain/main/"
WORKERS = 6  # рабочих потоков тайлов: больше ждут сеть, чем считают
IN_FLIGHT = 8
COGS_KEPT = 64  # открытых файлов: заголовок 128 КБ, тайлы не помнятся
SETTINGS = "PlanetX/aef/"
SPOT_COLOR = (255, 210, 30, 255)
SPOTS = 10  # мест сильных изменений в слое проекта

_COGS = OrderedDict()
_COGS_LOCK = threading.Lock()
_OPENING = {}
_INDEX = {}  # зона: ZoneIndex или None - указателя нет
_INDEX_LOCK = threading.Lock()
_ZSTD = []
_EXPORT = []  # пул расчёта участка, один поток на всё время QGIS


# --- ZSTD ---------------------------------------------------------------


def _zstd_library():
    """Библиотека zstd: у QGIS в Windows - zstd.dll рядом с qgis-bin.exe,
    в Linux и macOS - системная."""
    names = []
    if sys.platform == "win32":
        names.append(os.path.join(os.path.dirname(sys.executable),
                                  "zstd.dll"))
        names.append("zstd.dll")
    found = ctypes.util.find_library("zstd")
    if found:
        names.append(found)
    names += ["libzstd.so.1", "libzstd.1.dylib"]
    lib = None
    for name in names:
        try:
            lib = ctypes.CDLL(name)
        except OSError as error:
            journal.note("zstd {}: {}".format(name, error))
            lib = None
        if lib is not None:
            break
    if lib is not None:
        lib.ZSTD_decompress.restype = ctypes.c_size_t
        lib.ZSTD_decompress.argtypes = (ctypes.c_void_p, ctypes.c_size_t,
                                        ctypes.c_char_p, ctypes.c_size_t)
        lib.ZSTD_isError.restype = ctypes.c_uint
        lib.ZSTD_isError.argtypes = (ctypes.c_size_t,)
        return lib
    return None


def zstd_ready():
    """Раскодирование ZSTD поставлено в core/cog.py. False - библиотеки
    zstd нет."""
    if not _ZSTD:
        lib = _zstd_library()
        _ZSTD.append(lib)
        if lib is not None:
            def decode(raw, need, lib=lib):
                out = ctypes.create_string_buffer(need)
                size = lib.ZSTD_decompress(out, need, raw, len(raw))
                if lib.ZSTD_isError(size):
                    raise cog.CogError("zstd")
                return out.raw[:size]
            cog.set_zstd(decode)
    return _ZSTD[0] is not None


# --- файлы и указатели ----------------------------------------------------


def open_cog(year, zone, name):
    """Файл года из памяти или открыть, None - его нет или он не
    разбирается. Ошибки сети идут вызывающему."""
    url = aef.file_url(year, zone, name)
    with _COGS_LOCK:
        if url in _COGS:
            _COGS.move_to_end(url)
            return _COGS[url]
        lock = _OPENING.setdefault(url, threading.Lock())
    with lock:
        with _COGS_LOCK:
            if url in _COGS:
                return _COGS[url]
        try:
            found = cog.Cog(lambda start, length: ranges.fetch(
                url, start, length), head=aef.HEAD, cache=1 << 20,
                fetch_many=lambda spans: ranges.fetch_many(url, spans))
        except (cog.CogError, ranges.Missing) as error:
            journal.note("aef file {}: {}".format(url, error))
            found = None
        with _COGS_LOCK:
            _COGS[url] = found
            _OPENING.pop(url, None)
            while len(_COGS) > COGS_KEPT:
                _COGS.popitem(last=False)
        return found


def index_of(zone):
    """Указатель зоны, None - его нет. Файл идёт через кэш QGIS."""
    with _INDEX_LOCK:
        if zone in _INDEX:
            return _INDEX[zone]
    url = INDEX_BASE + aef.INDEX.format(zone=zone)
    try:
        found = aef.ZoneIndex.parse(ranges.fetch(url, 0, None))
    except ranges.Missing:
        found = None
    except (ValueError, KeyError) as error:
        journal.note("aef index {}: {}".format(zone, error))
        found = None
    with _INDEX_LOCK:
        _INDEX[zone] = found
    return found


class ChangeTiles(ThreadTiles):
    """Картинки тайлов степени изменения: загрузчик слоя вида
    (ui/threadtiles.py), сигнал loaded (ключ, картинка, уровни
    мипмапов), пустой тайл - (None, None)."""

    def __init__(self, changes, settings, parent=None):
        super().__init__(WORKERS, IN_FLIGHT, "aef", parent)
        self.changes = changes
        self.settings = settings

    def work(self, key):
        s = self.settings
        values = aef.tile_values(self.changes, index_of, *key,
                                 detail=s["detail"],
                                 detail_level=s["level"], ring=s["ring"])
        if values is None:
            return None, None
        rgba = aef.colors(values, s["low"], s["high"])
        return rgba, mip_chain(rgba)


# --- окно ----------------------------------------------------------------


class ChangeDialog(QDialog):
    """Окно «Изменения местности». Сигналы changed - годы или
    промежуток степени, detail, spots. OK записывает участок в проект
    QGIS, «Отмена» снимает его (ui/results.py)."""

    changed = pyqtSignal()
    detail = pyqtSignal()
    spots = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Изменения местности"))
        self.point = None
        settings = QgsSettings()
        self.place = QLabel(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, 3.0, aef.DETAIL_SIDE / 1000.0,
                         SETTINGS + "side")
        self.before = QComboBox(self)
        self.after = QComboBox(self)
        for year in aef.YEARS:
            self.before.addItem(str(year), year)
            self.after.addItem(str(year), year)
        self.before.setCurrentIndex(self.before.findData(int(
            settings.value(SETTINGS + "before", aef.YEARS[0]))))
        self.after.setCurrentIndex(self.after.findData(int(
            settings.value(SETTINGS + "after", aef.YEARS[-1]))))
        tip = tr("Годы сравнения. Каждая клетка 10 м за год описана "
                 "64 числами - сводкой снимков Sentinel, Landsat и радара. "
                 "Степень изменения - насколько отличаются описания двух "
                 "лет.")
        self.before.setToolTip(tip)
        self.after.setToolTip(tip)
        self.low = _spin(self, 0.0, 1.0, float(settings.value(
            SETTINGS + "low", 0.0)), "", decimals=2)
        self.high = _spin(self, 0.0, 1.0, float(settings.value(
            SETTINGS + "high", 1.0)), "", decimals=2)
        for box in (self.low, self.high):
            box.setSingleStep(0.05)
            box.setToolTip(tr(
                "Показывать клетки со степенью изменения в этом "
                "промежутке, прочие прозрачны. У неизменённой местности "
                "степень около 0.05, у стройки, вырубки, нового карьера - "
                "0.5 и выше."))
        self.level = QComboBox(self)
        for level, pixel in aef.DETAIL_LEVELS:
            self.level.addItem(tr("{pixel} м", pixel=pixel), level)
        self.level.setCurrentIndex(self.level.findData(int(
            settings.value(SETTINGS + "level", 0))))
        self.level.setToolTip(tr(
            "Пиксель подробного участка. Файлы набора хранят блоки "
            "1024 × 1024 пикселя, блок за год - 40-50 МБ при любом "
            "пикселе: 10 м покрывают 10 км блоком, 80 м - 82 км."))
        self.volume = QLabel(self)
        span = QHBoxLayout()
        span.addWidget(self.low)
        span.addWidget(QLabel(tr("до"), self))
        span.addWidget(self.high)
        years = QHBoxLayout()
        years.addWidget(self.before)
        years.addWidget(QLabel(tr("и"), self))
        years.addWidget(self.after)
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Годы"), years)
        form.addRow(tr("Степень от"), span)
        form.addRow(tr("Подробный участок"), self.area.widget)
        form.addRow(tr("Пиксель участка"), self.level)
        form.addRow("", self.volume)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Подробно"), self)
        run.setToolTip(tr(
            "Степень изменения участка с выбранным пикселем. Вне "
            "участка глобус показывает обзор с пикселем 160 м и крупнее."))
        run.clicked.connect(self.detail)
        self.find_button = QPushButton(tr("Места изменений"), self)
        self.find_button.setToolTip(tr(
            "Места самых сильных изменений участка слоем точек в проект "
            "QGIS. Дальше их удобно смотреть архивом снимков Wayback "
            "и шторкой."))
        self.find_button.clicked.connect(self.spots)
        for button in (run, self.find_button):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        credit = QLabel(tr(
            "Данные - AlphaEarth Foundations Satellite Embedding, "
            "CC BY 4.0.") + " " + aef.CREDIT, self)
        credit.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(credit)
        layout.addWidget(buttons)
        fit_status(self, layout)
        for box in (self.before, self.after):
            box.currentIndexChanged.connect(lambda _: self._changed())
        for box in (self.low, self.high):
            box.valueChanged.connect(lambda _: self._changed())
        self.area.changed.connect(self.volume_changed)
        self.level.currentIndexChanged.connect(lambda _: self._remember())
        self.set_ready(False)

    def years(self):
        return self.before.currentData(), self.after.currentData()

    def _changed(self):
        self._remember()
        self.changed.emit()

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "before", self.before.currentData())
        settings.setValue(SETTINGS + "after", self.after.currentData())
        settings.setValue(SETTINGS + "low", self.low.value())
        settings.setValue(SETTINGS + "high", self.high.value())
        settings.setValue(SETTINGS + "level", self.level.currentData())
        self.volume_changed()

    def volume_changed(self):
        """Оценка загрузки подробного участка под полями."""
        if self.point is None:
            self.volume.setText("")
            return
        lat, lon = self.point
        index = _INDEX.get(aef.zone_of(lon, lat))
        if index is None:
            self.volume.setText("")
            return
        if not self.area.closed():
            self.volume.setText(tr("Участок не замкнут."))
            return
        level = self.level.currentData()
        box = self.area.box()
        parts = aef.detail_parts(index, box, level)
        self.volume.setText(tr("Загрузка около {mb} МБ", mb="{:.0f}".format(
            aef.detail_megabytes(parts, level))))

    def set_ready(self, ready):
        for button in (self.to_project, self.find_button):
            button.setEnabled(ready)


class ChangeTool(QObject):
    """Строка «Изменения местности» и её окно у окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.changes = None
        self.detail = None  # (рамка градусами, обзор, многоугольник)
        self.shown = False
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.session = Session(window, tr("Изменения местности"))

    # --- строка и слой --------------------------------------------------

    def years(self):
        settings = QgsSettings()
        if self.dialog is not None:
            return self.dialog.years()
        return (int(settings.value(SETTINGS + "before", aef.YEARS[0])),
                int(settings.value(SETTINGS + "after", aef.YEARS[-1])))

    def span(self):
        if self.dialog is not None:
            return self.dialog.low.value(), self.dialog.high.value()
        settings = QgsSettings()
        return (float(settings.value(SETTINGS + "low", 0.0)),
                float(settings.value(SETTINGS + "high", 1.0)))

    def set_shown(self, on):
        """Строка раздела «Слои»: обзор вида на слое «emag» или ничего."""
        self.shown = bool(on)
        if on and not zstd_ready():
            self.window.message = (tr(
                "Изменения местности: нет библиотеки zstd, файлы "
                "AlphaEarth не прочитать."), time.monotonic())
            self.window._show_state()
            self.shown = False
        if self.shown:
            self.restart(keep=False)
        else:
            self._drop_tiles()
            view = self.window.view
            view.gibs[LAYER].min_level = 0
            if self.window.gibs_loaders.get(LAYER) is None:
                view.set_gibs(LAYER, False)
            self.window.field_legend.setVisible(False)

    def restart(self, keep=True):
        """Новый загрузчик тайлов по годам, промежутку и участку окна.
        keep - прежние картинки видны до замены."""
        if not self.shown:
            return
        before, after = self.years()
        if self.changes is None or (self.changes.before,
                                    self.changes.after) != (before, after):
            self.changes = aef.Changes(before, after, open_cog)
            keep = False
        low, high = self.span()
        settings = {"low": low, "high": high,
                    "detail": self.detail[0] if self.detail else None,
                    "level": self.detail[1] if self.detail else 0,
                    "ring": self.detail[2] if self.detail else None}
        window = self.window
        view = window.view
        self._drop_tiles()
        old = window.gibs_loaders.pop(LAYER, None)
        if old is not None:
            old.abort()
            old.deleteLater()
        tiles = ChangeTiles(self.changes, settings, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        window.gibs_loaders[LAYER] = tiles
        layer = view.gibs[LAYER]
        layer.max_level = aef.DETAIL_ZOOM if self.detail \
            else aef.PREVIEW_ZOOM
        layer.min_level = aef.MIN_ZOOM
        layer.empty.clear()
        view.set_gibs(LAYER, True, tiles, keep=keep)
        legend = window.field_legend
        legend.set_field(_Scale)
        legend.title = tr("Степень изменения {before}-{after}",
                          before=before, after=after)
        legend.show()
        window._place_attribution()
        window._show_attribution()

    def _drop_tiles(self):
        if self.tiles is not None:
            if self.window.gibs_loaders.get(LAYER) is self.tiles:
                self.window.gibs_loaders.pop(LAYER)
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    # --- окно -----------------------------------------------------------

    def open_here(self, lat, lon):
        """Окно «Изменения местности» для точки - пункт подменю «Анализ
        участка» меню на глобусе. Строка раздела «Слои» включается."""
        dialog = self.dialog
        if dialog is None:
            dialog = ChangeDialog(self.window)
            dialog.changed.connect(lambda: self.restart(keep=True))
            dialog.detail.connect(self.make_detail)
            dialog.spots.connect(self.find_spots)
            dialog.finished.connect(self._done)
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        if not self.window.extras.get(KEY):
            self.window.set_extra(KEY, True)
        self._load_index(lat, lon)
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        return dialog

    def _load_index(self, lat, lon):
        """Указатель зоны точки - для оценки загрузки участка."""
        zone = aef.zone_of(lon, lat)
        if zone in _INDEX:
            self.dialog.volume_changed()
            return
        self._run(lambda: index_of(zone), lambda _: (
            self.dialog.volume_changed() if self.dialog else None))

    def make_detail(self):
        """Подробный участок - многоугольник окна."""
        dialog = self.dialog
        if dialog is None or dialog.point is None:
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        self.detail = (dialog.area.box(), dialog.level.currentData(),
                       list(dialog.area.ring))
        dialog.set_ready(True)
        dialog.status.setText(tr(
            "Участок грузится при приближении к нему. {volume}.",
            volume=dialog.volume.text()) + " " + built_text())
        if not self.window.extras.get(KEY):
            self.window.set_extra(KEY, True)
        else:
            self.restart(keep=True)

    def clear_detail(self):
        self.detail = None
        if self.dialog is not None:
            self.dialog.set_ready(False)
            self.dialog.status.setText("")
        self.restart(keep=True)

    # --- участок в рабочем потоке --------------------------------------

    def _run(self, work, done, text=None):
        _run_job(self, work, done, text)

    def _poll(self):
        _poll_job(self)

    def _mosaic(self):
        """Степень изменения участка (зона, мозаика) в рабочем потоке,
        вне многоугольника - NaN."""
        box, level, ring = self.detail
        lat = (box[1] + box[3]) / 2.0
        lon = (box[0] + box[2]) / 2.0
        index = index_of(aef.zone_of(lon, lat))
        if index is None:
            return None
        found = aef.mosaic(self.changes, index, box, level)
        if found is None:
            return None
        x0, y0, step, values = found
        values[~aef.ring_mask(index, x0, y0, step, values.shape, ring)] = \
            np.nan
        return index, (x0, y0, step, values)

    def _done(self, code):
        """Окно закрыто: OK - степень изменения участка растром в подгруппу
        расчёта в проекте QGIS, участок снимается после записи, иначе
        сразу (ui/results.py). Обзор - строка раздела «Слои», он
        остаётся."""
        self.dialog.area.end()
        if accepted(code) and self.detail is not None:
            self.export(then=self._finish)
        else:
            self._finish()

    def _finish(self):
        self.clear_detail()
        self.session.reset()

    def export(self, path=None, then=None):
        """Степень изменения участка GeoTIFF в проект QGIS, растр
        отмечен на глобусе. path - файл, без него - новый файл
        результата (ui/results.py). then() - после записи."""
        if self.detail is None or self.changes is None:
            return None
        before, after = self.years()
        if path is None:
            path = result_path("change_{}_{}".format(before, after))
        self.dialog.status.setText(tr("Считается степень изменения "
                                      "участка…"))
        self._run(self._mosaic, lambda found: self._write(path, found, then),
                  tr("Изменения местности - участок в проект"))
        return path

    def _write(self, path, found, then=None):
        dialog = self.dialog
        if found is None:
            dialog.status.setText(tr("Для участка нет данных."))
        else:
            index, (x0, y0, step, values) = found
            if not write_utm(path, index, x0, y0, step, values):
                dialog.status.setText(tr("Растр не записан в «{path}».",
                                         path=path))
            else:
                before, after = self.years()
                title = tr("Изменения {before}-{after}", before=before,
                           after=after)
                show_layer(self.window, add_raster(
                    path, title, [(v, c) for v, c in aef.STOPS],
                    rights=aef.CREDIT,
                    group=self.session.group_for(self.detail[2])))
                dialog.status.setText(tr(
                    "Растр {cols} × {rows} пикселей в проекте.",
                    cols=values.shape[1], rows=values.shape[0]))
        if then is not None:
            then()

    def find_spots(self):
        """Места сильных изменений участка слоем точек в проект QGIS."""
        if self.detail is None or self.changes is None:
            return
        self.dialog.status.setText(tr("Ищутся места изменений…"))
        self._run(self._mosaic, self._spots,
                  tr("Изменения местности - места изменений"))

    def _spots(self, found):
        dialog = self.dialog
        if found is None:
            dialog.status.setText(tr("Для участка нет данных."))
            return None
        index, (x0, y0, step, values) = found
        low, _ = self.span()
        spots = aef.hot_spots(values, SPOTS, spacing=max(
            3, int(200.0 / step)), low=max(low, 0.3))
        if not spots:
            dialog.status.setText(tr("Изменений сильнее 0.3 на участке нет."))
            return None
        before, after = self.years()
        items = []
        for n, (row, col, value) in enumerate(spots, start=1):
            lat, lon = from_utm(index.number, index.south,
                                x0 + (col + 0.5) * step,
                                y0 - (row + 0.5) * step)
            items.append(([(float(lat), float(lon))], {
                "n": n, "change": round(float(value), 3),
                "years": "{}-{}".format(before, after)}))
        path = result_path("change_spots", ".gpkg")
        layer = None
        if write_vector(path, "spots", "point", items,
                        [("n", "int"), ("change", "real"),
                         ("years", "str")]):
            layer = add_vector(
                self.window, path, "spots",
                tr("Места изменений {before}-{after}", before=before,
                   after=after), self.session.group_for(self.detail[2]),
                SPOT_COLOR)
        dialog.status.setText(tr("В проект добавлено мест изменений: {n}.",
                                 n=len(items)) if layer is not None else
                              tr("Слой не записан в «{path}».", path=path))
        return layer

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


class Stopped(Exception):
    """Расчёт остановлен меню значка загрузки."""


def _run_job(owner, work, done, text=None):
    """work() в общем рабочем потоке, done(итог) - в главном. У owner
    поля job, timer (его timeout зовёт _poll_job), dialog и window.
    text - что идёт, для значка загрузки, с ним расчёт можно остановить.
    owner.stopped - событие остановки, work проверяет его сам
    (stop_point)."""
    if not _EXPORT:
        _EXPORT.append(ThreadPoolExecutor(max_workers=1))
    owner.stopped = threading.Event()
    owner.job = (_EXPORT[0].submit(work), done)
    owner.busy_text = text
    if text:
        owner.window.spinner.set_job(_busy_key(owner), text,
                                     lambda: _stop_job(owner))
    owner.timer.start()


def _busy_key(owner):
    return "aef:" + type(owner).__name__


def _stop_job(owner):
    """Остановить расчёт owner: итог не ждётся, работа в потоке
    кончается на ближайшей stop_point."""
    owner.stopped.set()
    owner.job = None
    owner.timer.stop()
    owner.window.spinner.set_job(_busy_key(owner))
    if owner.dialog is not None:
        owner.dialog.status.setText(tr("Расчёт остановлен."))


def stop_point(owner):
    """В рабочем потоке: расчёт остановлен - Stopped."""
    stopped = getattr(owner, "stopped", None)
    if stopped is not None and stopped.is_set():
        raise Stopped()


def _poll_job(owner):
    if owner.job is None:
        owner.timer.stop()
        return
    future, done = owner.job
    if not future.done():
        return
    owner.job = None
    owner.timer.stop()
    if getattr(owner, "busy_text", None):
        owner.window.spinner.set_job(_busy_key(owner))
    try:
        result = future.result()
    except Stopped:
        return
    except (OSError, cog.CogError) as error:
        if owner.dialog is not None:
            owner.dialog.status.setText(tr(
                "Данные не получены: {error}", error=error))
        return
    done(result)


class _Scale:
    """Шкала степени изменения для FieldLegend."""
    key = KEY
    stops = aef.STOPS
    ticks = (0, 0.5, 1)


def write_utm(path, index, x0, y0, step, values):
    """Степень изменения GeoTIFF float32 в системе UTM зоны, NaN - нет
    данных. True, если записано."""
    from osgeo import gdal, osr
    from .inset import warm
    warm()
    srs = osr.SpatialReference()
    srs.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    rows, cols = values.shape
    data = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    if data is None:
        return False
    data.SetGeoTransform((x0, step, 0.0, y0, 0.0, -step))
    data.SetProjection(srs.ExportToWkt())
    band = data.GetRasterBand(1)
    band.SetNoDataValue(float("nan"))
    band.WriteArray(np.asarray(values, dtype=np.float32))
    data = None
    return True
