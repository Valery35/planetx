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
сам, подробный участок задаёт окно: загрузка блока полного разрешения
- около 40 МБ на год, окно называет объём до неё.
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
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFileDialog, QFormLayout, QHBoxLayout,
                                 QLabel, QPushButton, QVBoxLayout)

from .. import journal
from ..core import aef, cog
from ..core.coords import from_utm
from ..core.features import Shape
from ..core.kml import KFolder, KPlace
from ..core.mipmap import mip_chain
from ..i18n import tr
from ..net import ranges
from ..qt_compat import enum
from .export import add_raster
from .hydro import _spin
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
DETAIL_COLOR = (255, 230, 40, 255)  # рамка подробного участка
SPOT_COLOR = (255, 210, 30, 255)
SPOTS = 10  # мест сильных изменений в «Мои метки»

_COGS = OrderedDict()
_COGS_LOCK = threading.Lock()
_OPENING = {}
_INDEX = {}  # зона: ZoneIndex или None - указателя нет
_INDEX_LOCK = threading.Lock()
_ZSTD = []
_EXPORT = []  # пул расчёта участка, один поток на всё время QGIS


def group_name():
    """Группа слоёв проекта изменений местности."""
    return tr("PlanetX - изменения местности")


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
                                 detail_level=s["level"])
        if values is None:
            return None, None
        rgba = aef.colors(values, s["low"], s["high"])
        return rgba, mip_chain(rgba)


# --- окно ----------------------------------------------------------------


class ChangeDialog(QDialog):
    """Окно «Изменения местности». Сигналы changed - годы или
    промежуток степени, detail, export, spots, clear."""

    changed = pyqtSignal()
    detail = pyqtSignal()
    export = pyqtSignal()
    spots = pyqtSignal()
    clear = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Изменения местности"))
        self.point = None
        settings = QgsSettings()
        self.place = QLabel(self)
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
        self.side = _spin(self, 0.5, aef.DETAIL_SIDE / 1000.0, float(
            settings.value(SETTINGS + "side", 3.0)), tr(" км"))
        self.side.setToolTip(tr(
            "Сторона квадрата подробного участка с серединой в точке "
            "окна."))
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
        self.status = QLabel(self)
        self.status.setWordWrap(True)
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
        form.addRow(tr("Подробный участок"), self.side)
        form.addRow(tr("Пиксель участка"), self.level)
        form.addRow("", self.volume)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Подробно"), self)
        run.setToolTip(tr(
            "Степень изменения квадрата с выбранным пикселем. Вне "
            "участка глобус показывает обзор с пикселем 160 м и крупнее."))
        run.clicked.connect(self.detail)
        self.to_project = QPushButton(tr("В проект QGIS…"), self)
        self.to_project.setToolTip(tr(
            "Степень изменения подробного участка растром GeoTIFF "
            "в системе UTM в проект QGIS."))
        self.to_project.clicked.connect(self.export)
        self.find_button = QPushButton(tr("Места изменений"), self)
        self.find_button.setToolTip(tr(
            "Места самых сильных изменений участка точками в «Моих "
            "метках». Дальше их удобно смотреть архивом снимков "
            "Wayback и шторкой."))
        self.find_button.clicked.connect(self.spots)
        remove = QPushButton(tr("Убрать участок"), self)
        remove.setToolTip(tr("Убрать подробный участок, обзор остаётся."))
        remove.clicked.connect(self.clear)
        for button in (run, self.to_project, self.find_button, remove):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
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
        for box in (self.side,):
            box.valueChanged.connect(lambda _: self._remember())
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
        settings.setValue(SETTINGS + "side", self.side.value())
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
        level = self.level.currentData()
        box = aef.square(lat, lon, self.side.value() * 1000.0)
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
        self.detail = None  # (рамка градусами, обзор)
        self.shown = False
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.shapes = []

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
        self._update_shapes()

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
                    "level": self.detail[1] if self.detail else 0}
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
            dialog.export.connect(self.export)
            dialog.spots.connect(self.find_spots)
            dialog.clear.connect(self.clear_detail)
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        if not self.window.extras.get(KEY):
            self.window.set_extra(KEY, True)
        self._load_index(lat, lon)
        dialog.show()
        dialog.raise_()
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
        """Подробный участок квадратом у точки окна."""
        dialog = self.dialog
        if dialog is None or dialog.point is None:
            return
        lat, lon = dialog.point
        box = aef.square(lat, lon, dialog.side.value() * 1000.0)
        self.detail = (box, dialog.level.currentData())
        dialog.set_ready(True)
        dialog.status.setText(tr(
            "Участок грузится при приближении к нему. {volume}.",
            volume=dialog.volume.text()))
        if not self.window.extras.get(KEY):
            self.window.set_extra(KEY, True)
        else:
            self.restart(keep=True)
        self._update_shapes()

    def clear_detail(self):
        self.detail = None
        if self.dialog is not None:
            self.dialog.set_ready(False)
            self.dialog.status.setText("")
        self.restart(keep=True)
        self._update_shapes()

    def _update_shapes(self):
        shapes = []
        if self.shown and self.detail is not None:
            west, south, east, north = self.detail[0]
            shapes.append(Shape("polygon", [(south, west), (south, east),
                                            (north, east), (north, west)],
                                color=DETAIL_COLOR, width=2.5))
        if shapes == self.shapes:
            return
        self.shapes = shapes
        self.window.change_shapes = shapes
        self.window._refresh_shapes()

    # --- участок в рабочем потоке --------------------------------------

    def _run(self, work, done):
        if not _EXPORT:
            _EXPORT.append(ThreadPoolExecutor(max_workers=1))
        self.job = (_EXPORT[0].submit(work), done)
        self.timer.start()

    def _poll(self):
        if self.job is None:
            self.timer.stop()
            return
        future, done = self.job
        if not future.done():
            return
        self.job = None
        self.timer.stop()
        try:
            result = future.result()
        except (OSError, cog.CogError) as error:
            if self.dialog is not None:
                self.dialog.status.setText(tr(
                    "Данные не получены: {error}", error=error))
            return
        done(result)

    def _mosaic(self):
        """Степень изменения участка (зона, мозаика) в рабочем потоке."""
        box, level = self.detail
        lat = (box[1] + box[3]) / 2.0
        lon = (box[0] + box[2]) / 2.0
        index = index_of(aef.zone_of(lon, lat))
        if index is None:
            return None
        found = aef.mosaic(self.changes, index, box, level)
        return None if found is None else (index, found)

    def export(self, path=None):
        """Степень изменения участка GeoTIFF в проект QGIS. path - файл,
        без него окно выбора."""
        if self.detail is None or self.changes is None:
            return None
        before, after = self.years()
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self.window, tr("Изменения местности в проект QGIS"),
                os.path.join(QgsProject.instance().homePath()
                             or os.path.expanduser("~"),
                             "change_{}_{}.tif".format(before, after)),
                tr("GeoTIFF (*.tif)"))
        if not path:
            return None
        self.dialog.status.setText(tr("Считается степень изменения "
                                      "участка…"))
        self._run(self._mosaic, lambda found: self._write(path, found))
        return path

    def _write(self, path, found):
        dialog = self.dialog
        if found is None:
            dialog.status.setText(tr("Для участка нет данных."))
            return
        index, (x0, y0, step, values) = found
        if not write_utm(path, index, x0, y0, step, values):
            dialog.status.setText(tr("Растр не записан в «{path}».",
                                     path=path))
            return
        before, after = self.years()
        title = tr("Изменения {before}-{after}", before=before, after=after)
        add_raster(path, title, [(v, c) for v, c in aef.STOPS],
                   rights=aef.CREDIT, group=group_name())
        dialog.status.setText(tr("Растр {cols} × {rows} пикселей в проекте.",
                                 cols=values.shape[1], rows=values.shape[0]))

    def find_spots(self):
        """Места сильных изменений участка папкой в «Мои метки»."""
        if self.detail is None or self.changes is None:
            return
        self.dialog.status.setText(tr("Ищутся места изменений…"))
        self._run(self._mosaic, self._spots)

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
        children = []
        for n, (row, col, value) in enumerate(spots, start=1):
            lat, lon = from_utm(index.number, index.south,
                                x0 + (col + 0.5) * step,
                                y0 - (row + 0.5) * step)
            children.append(KPlace(
                tr("Изменение {n}: {value}", n=n,
                   value="{:.2f}".format(value)), "point",
                [(float(lat), float(lon))], color=SPOT_COLOR,
                description=tr(
                    "Степень изменения {value} между {before} и {after} "
                    "годами по эмбеддингам AlphaEarth.",
                    value="{:.2f}".format(value), before=before,
                    after=after)))
        window = self.window
        key = window.myplaces.import_tree(
            KFolder(tr("Изменения {before}-{after}", before=before,
                       after=after), True, children),
            parent=window.panel.current_folder(), body=window.body_key())
        dialog.status.setText(tr("В «Мои метки» записано мест: {n}.",
                                 n=len(children)))
        return key

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


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
