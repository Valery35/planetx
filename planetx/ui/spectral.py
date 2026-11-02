# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Минералы по спектру: окно «Минералы по спектру» подменю «Анализ
участка».

Просьба автора от 2 ноября 2026 года. Источник - многоканальный растр
проекта, каналы узнаются по подписям (core/spectra.py). Щелчок по глобусу
показывает спектр пикселя и ближайшие эталоны библиотеки USGS, отмеченные
эталоны - классы участка по углу между спектрами. Участок, сетка и показ -
как у классификации (ui/aefclass.py), OK записывает классы и угол до
эталона растрами в подгруппу расчёта.
"""
import math
import os

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsPointXY, QgsProject, QgsSettings)
from qgis.PyQt.QtCore import QObject, QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPen, QPolygonF
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QHBoxLayout,
                                 QLabel, QLineEdit, QListWidget,
                                 QListWidgetItem, QPushButton, QVBoxLayout,
                                 QWidget)

from ..core import aef, spectra
from ..i18n import tr
from ..qt_compat import enum
from .aef import _poll_job, _run_job, stop_point, write_utm
from .aefclass import (AUTO, COLORS, PIXELS, RASTER_SIDE, ClassTiles,
                       add_classes, fill_pixels, pixel_text, problem_text,
                       project_rasters, read_raster, write_classes)
from .area import Area
from .export import add_raster
from .results import Session, accepted, built_text, keep_buttons, \
    result_path, show_layer
from .sitelayer import SiteTool, result_level
from .viewshed import fit_status

SETTINGS = "PlanetX/spectral/"
DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data",
                    "spectra.json")
OPACITY = 0.6
NEAREST = 5  # ближайших эталонов под графиком
FEW_BANDS = 6  # меньше каналов - предупреждение, спектр слишком груб
# Цвета линий графика: спектр пикселя и ближайшие эталоны - выбор
# помощника.
PIXEL_COLOR = QColor(250, 250, 250)
CURVE_COLORS = ((255, 170, 60), (90, 200, 255), (140, 230, 120),
                (240, 110, 200), (230, 220, 90))
# Шкала угла до эталона в проекте, градусы: малый - ярче.
ANGLE_STOPS = [(0.0, (40, 30, 120)), (5.0, (60, 160, 200)),
               (10.0, (240, 220, 80)), (20.0, (200, 60, 40))]
_LIBRARY = []


def library():
    """Библиотека эталонов, читается один раз."""
    if not _LIBRARY:
        _LIBRARY.append(spectra.load(DATA))
    return _LIBRARY[0]


def group_names():
    return (("", tr("Все группы")), ("minerals", tr("Минералы")),
            ("soils", tr("Почвы и смеси")), ("vegetation", tr("Растения")),
            ("coatings", tr("Покрытия")),
            ("artificial", tr("Искусственные материалы")),
            ("liquids", tr("Вода, снег и жидкости")))


def band_labels(path):
    """Подписи каналов файла растра через GDAL, по порядку."""
    from osgeo import gdal
    from .inset import warm
    warm()
    data = gdal.Open(path)
    if data is None:
        return []
    return [data.GetRasterBand(n).GetDescription()
            for n in range(1, data.RasterCount + 1)]


class RasterBox(QComboBox):
    """Многоканальные растры проекта. Заполняется при открытии списка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.refill()

    def refill(self):
        chosen = self.currentData()
        self.blockSignals(True)
        self.clear()
        for layer in project_rasters():
            if layer.bandCount() >= spectra.MIN_BANDS:
                self.addItem(layer.name(), layer.id())
        self.setCurrentIndex(max(0, self.findData(chosen)))
        self.blockSignals(False)
        if self.currentData() != chosen:
            self.currentIndexChanged.emit(self.currentIndex())

    def showPopup(self):
        self.refill()
        super().showPopup()


class SpectrumChart(QWidget):
    """График: спектр пикселя по длинам волн и ближайшие эталоны
    в его масштабе."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.waves = []
        self.pixel = None
        self.curves = []  # [(значения, цвет)]

    def set_data(self, waves, pixel, curves):
        self.waves, self.pixel, self.curves = list(waves), pixel, curves
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        text = self.palette().color(self.foregroundRole())
        rect = self.rect().adjusted(34, 8, -8, -18)
        painter.setPen(QPen(text, 1))
        painter.drawRect(rect)
        if self.pixel is None or len(self.waves) < 2:
            painter.drawText(rect, enum(Qt, "AlignmentFlag", "AlignCenter"),
                             tr("Щёлкните по снимку на глобусе"))
            return
        series = [self.pixel] + [c for c, _ in self.curves]
        top = max(float(np.nanmax(s)) for s in series) or 1.0
        low_w, high_w = min(self.waves), max(self.waves)
        span = (high_w - low_w) or 1.0

        def point(w, v):
            x = rect.left() + (w - low_w) / span * rect.width()
            y = rect.bottom() - max(0.0, v) / (top * 1.05) * rect.height()
            return QPointF(x, y)

        order = np.argsort(self.waves)
        waves = np.asarray(self.waves)[order]
        for values, color in self.curves:
            pen = QPen(QColor(*color), 1.5)
            painter.setPen(pen)
            painter.drawPolyline(QPolygonF(
                [point(w, v) for w, v in zip(waves,
                                             np.asarray(values)[order])]))
        painter.setPen(QPen(PIXEL_COLOR if text.lightness() > 128
                            else QColor(20, 20, 20), 2.5))
        values = np.asarray(self.pixel)[order]
        painter.drawPolyline(QPolygonF(
            [point(w, v) for w, v in zip(waves, values)]))
        painter.setPen(QPen(text, 1))
        for w in (low_w, high_w):
            p = point(w, 0.0)
            painter.drawText(int(p.x()) - 14, rect.bottom() + 14,
                             "{:.2f}".format(w))
        painter.drawText(2, rect.top() + 10, "{:.2g}".format(top))
        painter.drawText(rect.right() - 30, rect.bottom() + 14,
                         tr("мкм"))


class SpectralDialog(QDialog):
    """Окно «Минералы по спектру»."""

    build = pyqtSignal()
    changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Минералы по спектру"))
        self.point = None
        self.chosen = []  # id эталонов-классов по порядку выбора
        settings = QgsSettings()
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.source = RasterBox(self)
        self.source.setToolTip(tr(
            "Многоканальный растр проекта в отражении, например «Все "
            "каналы сцены» окна «Космоснимки». Каналы узнаются по их "
            "подписям, тепловые каналы не участвуют."))
        self.sensor = QComboBox(self)
        self.sensor.addItem(tr("Авто"), "")
        for key in ("aster", "sentinel2", "landsat8"):
            self.sensor.addItem(library().sensors[key]["name"], key)
        self.sensor.setToolTip(tr(
            "Датчик, на каналы которого пересчитаны эталоны. «Авто» "
            "узнаёт его по длинам волн в подписях каналов растра. Если "
            "подписей нет, датчик выбирается вручную, каналы берутся по "
            "номерам в подписях или по порядку."))
        self.bands = QLabel(self)
        self.bands.setWordWrap(True)
        self.area = Area(window, self, 3.0, RASTER_SIDE, SETTINGS + "side")
        self.level = QComboBox(self)
        self.wanted_pixel = int(settings.value(SETTINGS + "pixel", AUTO))
        fill_pixels(self.level, True, self.wanted_pixel)
        self.level.setToolTip(tr(
            "Пиксель сетки участка. «Авто» - пиксель растра, если на "
            "участке клеток не больше 640 тысяч."))
        self.volume = QLabel(self)
        self.volume.setWordWrap(True)
        self.group = QComboBox(self)
        for key, name in group_names():
            self.group.addItem(name, key)
        self.search_box = QLineEdit(self)
        self.search_box.setPlaceholderText(tr("Слова названия, например "
                                        "kaolinite"))
        self.search_box.setToolTip(tr(
            "Названия эталонов - по-английски, как в библиотеке USGS. "
            "Все слова должны быть в названии."))
        self.list = QListWidget(self)
        self.list.setMinimumHeight(140)
        self.picked = QLabel(self)
        forget = QPushButton(tr("Снять все"), self)
        forget.clicked.connect(self._forget)
        self.limit = QDoubleSpinBox(self)
        self.limit.setRange(0.5, 45.0)
        self.limit.setSingleStep(0.5)
        self.limit.setSuffix(" °")
        self.limit.setValue(float(settings.value(SETTINGS + "limit",
                                                 spectra.LIMIT)))
        self.limit.setToolTip(tr(
            "Наибольший угол между спектрами клетки и эталона. Клетка "
            "дальше от всех отмеченных эталонов остаётся без класса. "
            "Меньше - строже."))
        self.chart = SpectrumChart(self)
        self.near = QListWidget(self)
        self.near.setMaximumHeight(110)
        self.near.setToolTip(tr(
            "Эталоны, ближайшие к спектру пикселя под щелчком, с углом "
            "до него. Флажок добавляет эталон в классы."))
        picked_row = QHBoxLayout()
        picked_row.addWidget(self.picked, 1)
        picked_row.addWidget(forget)
        form = QFormLayout()
        form.addRow(tr("Растр"), self.source)
        form.addRow(tr("Каналы"), self.sensor)
        form.addRow("", self.bands)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Пиксель"), self.level)
        form.addRow("", self.volume)
        form.addRow(tr("Группа"), self.group)
        form.addRow(tr("Поиск"), self.search_box)
        form.addRow(tr("Эталоны"), self.list)
        form.addRow("", picked_row)
        form.addRow(tr("Угол до"), self.limit)
        form.addRow(tr("Спектр"), self.chart)
        form.addRow(tr("Ближайшие"), self.near)
        hint = QLabel(tr(
            "Щёлкните по снимку на глобусе - график покажет спектр пикселя "
            "и ближайшие эталоны. Отмеченные эталоны становятся классами "
            "участка."), self)
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Каждая клетка участка получает отмеченный эталон с наименьшим "
            "углом между спектрами."))
        run.clicked.connect(self.build)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        self.source.currentIndexChanged.connect(lambda _: self._source())
        self.sensor.currentIndexChanged.connect(lambda _: self._source())
        self.level.currentIndexChanged.connect(lambda _: self._pixel())
        self.area.changed.connect(self._volume)
        self.group.currentIndexChanged.connect(lambda _: self._fill())
        self.search_box.textChanged.connect(lambda _: self._fill())
        self.list.itemChanged.connect(self._item)
        self.near.itemChanged.connect(self._item)
        self.limit.valueChanged.connect(lambda _: self._remember())
        self.pairs = (None, [])
        self.labels = []
        self._source()
        self._fill()
        self.to_project.setEnabled(False)

    # --- источник --------------------------------------------------------

    def raster(self):
        return QgsProject.instance().mapLayer(self.source.currentData()
                                              or "")

    def _source(self):
        layer = self.raster()
        self.labels = band_labels(layer.source()) if layer else []
        self.pairs = spectra.pairs_for(library(), self.labels,
                                       self.sensor.currentData() or None)
        sensor, pairs = self.pairs
        if layer is None:
            text = tr("В проекте нет растров с тремя каналами и больше.")
        elif sensor is None:
            text = tr("Каналы не узнаны по подписям, выберите датчик.")
        else:
            text = tr("{sensor}: каналов {n} из {total}",
                      sensor=library().sensors[sensor]["name"],
                      n=len(pairs), total=len(self.labels))
            if len(pairs) < FEW_BANDS:
                text += ". " + tr(
                    "Каналов мало, разные минералы дадут одинаковый "
                    "спектр - возьмите снимок «Все каналы сцены» окна "
                    "«Космоснимки».")
        self.bands.setText(text)
        self._volume()
        self.changed.emit()

    def _pixel(self):
        self.wanted_pixel = self.level.currentData()
        self._remember()
        self._volume()

    def _volume(self):
        layer = self.raster()
        if layer is None or self.point is None or self.area.check():
            self.volume.setText("")
            return
        self.volume.setText(pixel_text(
            self.area.window, layer.id(), layer, self.level.currentData(),
            self.area.box(), self.area.size()))

    # --- эталоны ---------------------------------------------------------

    def _fill(self):
        """Список эталонов по группе и словам поиска."""
        found = spectra.search(library(), self.search_box.text(),
                               self.group.currentData() or None)
        self.list.blockSignals(True)
        self.list.clear()
        for entry in found[:2000]:
            self.list.addItem(self._entry_item(entry, None))
        self.list.blockSignals(False)
        self._picked_text()

    def _entry_item(self, entry, angle):
        text = entry["name"] + "  ·  " + entry["instrument"]
        if angle is not None:
            text = "{:.1f}°  ".format(angle) + text
        item = QListWidgetItem(text)
        item.setData(enum(Qt, "ItemDataRole", "UserRole"), entry["id"])
        item.setFlags(item.flags()
                      | enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
        item.setCheckState(enum(Qt, "CheckState", "Checked")
                           if entry["id"] in self.chosen
                           else enum(Qt, "CheckState", "Unchecked"))
        item.setToolTip(" ".join(p for p in (
            entry["name"], entry["instrument"], entry["kind"]) if p))
        return item

    def _item(self, item):
        ident = item.data(enum(Qt, "ItemDataRole", "UserRole"))
        on = item.checkState() == enum(Qt, "CheckState", "Checked")
        if on and ident not in self.chosen:
            self.chosen.append(ident)
        elif not on and ident in self.chosen:
            self.chosen.remove(ident)
        for box in (self.list, self.near):
            if box is item.listWidget():
                continue
            box.blockSignals(True)
            for n in range(box.count()):
                other = box.item(n)
                if other.data(enum(Qt, "ItemDataRole",
                                   "UserRole")) == ident:
                    other.setCheckState(item.checkState())
            box.blockSignals(False)
        self._picked_text()

    def _forget(self):
        self.chosen = []
        self._fill()
        for n in range(self.near.count()):
            self.near.item(n).setCheckState(enum(Qt, "CheckState",
                                                 "Unchecked"))
        self._picked_text()

    def _picked_text(self):
        self.picked.setText(tr("Отмечено эталонов: {n}",
                               n=len(self.chosen)))

    def show_spectrum(self, values, found):
        """Спектр пикселя values (каналы датчика по парам) и ближайшие
        эталоны found [(запись, угол, кривая)]."""
        sensor, pairs = self.pairs
        waves = [library().sensors[sensor]["um"][j] for _, j in pairs]
        curves = [(curve, CURVE_COLORS[n % len(CURVE_COLORS)])
                  for n, (_, _, curve) in enumerate(found)]
        self.chart.set_data(waves, values, curves)
        self.near.blockSignals(True)
        self.near.clear()
        for n, (entry, angle, _) in enumerate(found):
            item = self._entry_item(entry, angle)
            item.setForeground(QColor(*CURVE_COLORS[n % len(CURVE_COLORS)]))
            self.near.addItem(item)
        self.near.blockSignals(False)

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "pixel", self.wanted_pixel)
        settings.setValue(SETTINGS + "limit", self.limit.value())


class SpectralTool(SiteTool, QObject):
    """Минералы по спектру у окна глобуса."""

    @property
    def legend_title(self):
        return tr("Минералы по спектру")

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.result = None
        self.grid = None  # (ключ участка, сетка)
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(lambda: _poll_job(self))
        self.session = Session(window, tr("Минералы по спектру"))

    def open_here(self, lat, lon):
        dialog = self.dialog
        if dialog is None:
            dialog = SpectralDialog(self.window)
            dialog.build.connect(self.build)
            dialog.finished.connect(self._closed)
            self.dialog = dialog
        dialog.source.refill()
        dialog.point = (lat, lon)
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        dialog._source()
        self.window._refresh_shapes()
        return dialog

    def _closed(self, code=0):
        if accepted(code) and self.result is not None:
            self.export()
        self.clear()
        self.session.reset()
        self.dialog.area.end()

    def taking(self):
        """Окно открыто, участок не рисуется: щелчок - спектр пикселя."""
        dialog = self.dialog
        return dialog is not None and dialog.isVisible() \
            and not dialog.area.drawing

    # --- спектр под щелчком ---------------------------------------------

    def click(self, lat, lon):
        dialog = self.dialog
        layer = dialog.raster()
        sensor, pairs = dialog.pairs
        if layer is None or sensor is None:
            dialog.status.setText(dialog.bands.text())
            return
        values = pixel_values(layer, lat, lon)
        if values is None:
            dialog.status.setText(tr("Точка вне растра или без данных."))
            return
        spectrum = np.array([values[n] for n, _ in pairs], dtype=float)
        if not np.isfinite(spectrum).all():
            dialog.status.setText(tr("Точка вне растра или без данных."))
            return
        lib = library()
        ids, refs = lib.values(sensor, [s["id"] for s in lib.spectra])
        refs = refs[:, [j for _, j in pairs]]
        found = [(lib.by_id[ids[n]], angle,
                  spectra.scaled(refs[n], spectrum))
                 for n, angle in spectra.nearest(spectrum, refs, NEAREST)]
        dialog.show_spectrum(spectrum, found)
        dialog.status.setText(tr(
            "Спектр точки {lat}, {lon}. Ближайший эталон - {name}, "
            "{angle}°.", lat="{:.5f}".format(lat), lon="{:.5f}".format(lon),
            name=found[0][0]["name"] if found else "-",
            angle="{:.1f}".format(found[0][1]) if found else "-"))

    # --- расчёт ---------------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or dialog.point is None or self.job is not None:
            return
        layer = dialog.raster()
        if layer is None:
            dialog.status.setText(tr("В проекте нет подходящего растра."))
            return
        sensor, pairs = dialog.pairs
        if sensor is None:
            dialog.status.setText(dialog.bands.text())
            return
        lib = library()
        ids, refs = lib.values(sensor, dialog.chosen)
        if not ids:
            dialog.status.setText(tr("Отметьте хотя бы один эталон."))
            return
        refs = refs[:, [j for _, j in pairs]]
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        crs = layer.crs()
        if not crs.isValid():
            dialog.status.setText(tr("У растра не задана система "
                                     "координат."))
            return
        ring = list(dialog.area.ring)
        box = dialog.area.box()
        side = dialog.area.size()
        level = dialog.level.currentData()
        pixel = None if level == AUTO else float(PIXELS[level])
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        path, wkt = layer.source(), crs.toWkt()
        key = (layer.id(), path, box, pixel)
        cached = self.grid if self.grid and self.grid[0] == key else None
        bands = [n for n, _ in pairs]
        limit = dialog.limit.value()

        def work():
            index = aef.ZoneIndex(zone, [])
            found = cached[1] if cached else read_raster(
                path, wkt, index, box, side, pixel)
            if isinstance(found, str):
                return {"problem": found}
            stop_point(self)
            x0, y0, step, grid = found
            inside = aef.ring_mask(index, x0, y0, step, grid.shape[1:],
                                   ring)
            cube = grid[bands].astype(np.float64)
            cube[:, ~inside] = np.nan
            kinds, angle = spectra.classify(
                cube, refs, limit,
                progress=lambda done, total: stop_point(self))
            cells = int(np.isfinite(angle).sum())
            if not cells:
                return {"problem": "outside", "found": found}
            return {"index": index, "found": found, "kinds": kinds,
                    "angle": angle, "cells": cells}

        dialog.status.setText(tr("Считаются углы между спектрами…"))
        _run_job(self, work, lambda out: self._built(
            out, key, box, ring, layer.name(), ids),
            tr("Минералы по спектру"))

    def _built(self, out, key, box, ring, name, ids):
        dialog = self.dialog
        if out.get("found") is not None:
            self.grid = (key, out["found"])
        if out.get("problem"):
            dialog.status.setText(problem_text(out["problem"]))
            return
        x0, y0, step, _ = out["found"]
        lib = library()
        names = [lib.by_id[i]["name"] for i in ids]
        colors = [COLORS[n % len(COLORS)] for n in range(len(ids))]
        kinds = out["kinds"]
        self.result = {"index": out["index"], "x0": x0, "y0": y0,
                       "step": step, "classes": kinds.astype(np.int16),
                       "angle": out["angle"], "box": box, "ring": ring,
                       "colors": colors, "names": names, "ids": ids,
                       "raster": name, "label": name, "year": None}
        counts = np.bincount(kinds[kinds >= 0].ravel(),
                             minlength=len(ids))
        cells = max(out["cells"], 1)
        parts = ["{} {:.0f}%".format(names[n], 100.0 * counts[n] / cells)
                 for n in np.argsort(-counts) if counts[n]]
        none = 100.0 * (cells - counts.sum()) / cells
        dialog.status.setText(
            tr("Классы: {list}. Без класса {none} %.",
               list=", ".join(parts[:6]) or "-",
               none="{:.0f}".format(none)) + " " + built_text())
        dialog.to_project.setEnabled(bool(counts.sum()))
        self.show()

    # --- показ ----------------------------------------------------------

    def show(self):
        result = self.result
        self._drop_tiles()
        if result is None:
            return
        self.put_tiles(ClassTiles(result, parent=self), result_level(result),
                       OPACITY)

    def forget(self):
        self.result = None
        if self.dialog is not None:
            self.dialog.to_project.setEnabled(False)

    # --- выгрузка -------------------------------------------------------

    def export(self, path=None):
        """Классы и угол до эталона растрами в подгруппу расчёта."""
        result = self.result
        if result is None:
            return None
        path = path or result_path("spectral_classes")
        if not write_classes(path, result):
            self.dialog.status.setText(tr("Растр не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        layer = add_classes(path, tr("Минералы по спектру {name}",
                                     name=result["label"]), result, group)
        if layer is not None:
            layer.setOpacity(OPACITY)
        show_layer(self.window, layer)
        angle_path = result_path("spectral_angle")
        if write_utm(angle_path, result["index"], result["x0"],
                     result["y0"], result["step"], result["angle"]):
            add_raster(angle_path, tr("Угол до эталона, °"), ANGLE_STOPS,
                       group=group, abstract=library().source)
        self.dialog.status.setText(tr("Классы и угол в проекте."))
        return path

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


def pixel_values(layer, lat, lon):
    """Значения всех каналов растра в точке: список по порядку каналов,
    NaN без данных, None - точка вне растра."""
    transform = QgsCoordinateTransform(
        QgsCoordinateReferenceSystem("EPSG:4326"), layer.crs(),
        QgsProject.instance())
    try:
        point = transform.transform(QgsPointXY(lon, lat))
    except QgsCsException:
        return None
    if not layer.extent().contains(point):
        return None
    provider = layer.dataProvider()
    out = []
    for n in range(1, layer.bandCount() + 1):
        value, ok = provider.sample(point, n)
        out.append(float(value) if ok else math.nan)
    return out
