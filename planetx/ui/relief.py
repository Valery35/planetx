# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Анализ рельефа участка: окно «Уклон и экспозиция».

Участок - многоугольник (ui/area.py). Расчёт - core/relief.py по высотам
рамки участка, их даёт общая часть GridHeights из ui/hydro.py - с моделью
30 м и своим рельефом, вне многоугольника высот нет. Показ на глобусе -
слой вида «slope», тот же, что у строк «Уклон» и «Экспозиция»: свой
участок занимает слой, строки при этом гаснут, включённая строка снимает
участок. Растры - GeoTIFF в EPSG:3857, вершины и ямы - точечный слой
GeoPackage, всё - в подгруппу расчёта (ui/results.py).
"""
import os

import numpy as np
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QLabel, QPushButton,
                                 QVBoxLayout)

from ..core import ellipsoid, hydro, relief, slope
from ..i18n import tr
from ..qt_compat import enum
from .export import add_raster
from .area import Area
from .hydro import GridHeights, _spin, number
from .results import (Session, accepted, add_vector, built_text,
                      keep_buttons,
                      result_path, show_layer, write_vector)
from .viewshed import ResultTiles, display_level, fit_status

LAYER = "slope"  # слой вида, общий со строками «Уклон» и «Экспозиция»
PEAK_COLOR = (200, 40, 40, 255)
PIT_COLOR = (40, 90, 220, 255)
SIDE = 4.0  # км, сторона участка по умолчанию
MOST = 100.0  # км, наибольший участок


def side_names():
    """Названия сторон света по relief.SIDES."""
    return {"N": tr("север"), "NE": tr("северо-восток"),
            "E": tr("восток"), "SE": tr("юго-восток"), "S": tr("юг"),
            "SW": tr("юго-запад"), "W": tr("запад"),
            "NW": tr("северо-запад")}


def summary_text(rep):
    """Сводка уклона и экспозиции строками окна."""
    lines = [tr("Уклон от {low}° до {high}°, медиана {median}°.",
                low=number(rep.low), high=number(rep.high),
                median=number(rep.median))]
    bounds = [b for b, _ in rep.classes] + [90.0]
    parts = []
    for i, (low, area) in enumerate(rep.classes):
        if area <= 0.0:
            continue
        parts.append(tr("{low}-{high}° - {area} км²",
                        low="{:g}".format(low),
                        high="{:g}".format(bounds[i + 1]),
                        area=number(area / 1e6)))
    lines.append(tr("Площади по уклону: {parts}.", parts=", ".join(parts)))
    names = side_names()
    order = sorted(range(len(relief.SIDES)), key=lambda i: -rep.sides[i])
    sides = [tr("{side} {share}", side=names[relief.SIDES[i]],
                share="{:.0f}%".format(100.0 * rep.sides[i]))
             for i in order[:3] if rep.sides[i] > 0.0]
    if sides:
        lines.append(tr("Чаще всего склоны смотрят на {sides}.",
                        sides=", ".join(sides)))
    if rep.flat >= 0.005:
        lines.append(tr("Ровного места {share}.",
                        share="{:.0f}%".format(100.0 * rep.flat)))
    return " ".join(lines)


class ReliefDialog(QDialog):
    """Окно «Уклон и экспозиция». Сигналы build, mode - "slope" или
    "aspect", peaks. OK записывает растры в проект QGIS, «Отмена»
    убирает участок (ui/results.py)."""

    build = pyqtSignal()
    mode = pyqtSignal(str)
    peaks = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Уклон и экспозиция"))
        self.point = None
        self.place = QLabel(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, SIDE, MOST, "PlanetX/relief/side")
        self.shown = QComboBox(self)
        self.shown.addItem(tr("Уклон"), "slope")
        self.shown.addItem(tr("Экспозиция"), "aspect")
        self.shown.setToolTip(tr(
            "Что показывает участок на глобусе - крутизну склона или "
            "сторону света, куда он обращён. Строки «Уклон» и "
            "«Экспозиция» раздела «Слои» на это время гаснут."))
        self.shown.currentIndexChanged.connect(
            lambda _: self.mode.emit(self.shown.currentData()))
        self.peak_radius = _spin(self, 20.0, 5000.0, relief.PEAK_RADIUS,
                                 tr(" м"), decimals=0)
        self.peak_radius.setToolTip(tr(
            "Вершина выше всего вокруг себя в этом радиусе, яма ниже. "
            "Больше - остаются только крупные вершины и ямы."))
        self.peak_drop = _spin(self, 0.5, 2000.0, relief.PEAK_DROP,
                               tr(" м"), decimals=1)
        self.peak_drop.setToolTip(tr(
            "Наименьший перепад вершины над низшей точкой вокруг неё "
            "или ямы под высшей. Меньше - больше мелких бугров и "
            "западин."))
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Показывать"), self.shown)
        form.addRow(tr("Радиус вершины"), self.peak_radius)
        form.addRow(tr("Перепад от"), self.peak_drop)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Уклон и экспозиция участка по высотам, ядро 3 × 3 - "
            "раскраска на глобусе и сводка по классам уклона и "
            "сторонам света."))
        run.clicked.connect(self.build)
        self.find_button = QPushButton(tr("Вершины и ямы"), self)
        self.find_button.setToolTip(tr(
            "Вершины и замкнутые понижения участка - слой точек в проект "
            "QGIS с отметкой и перепадом."))
        self.find_button.clicked.connect(self.peaks)
        for button in (run, self.find_button):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        self.set_ready(False)

    def set_ready(self, ready):
        for button in (self.to_project, self.find_button):
            button.setEnabled(ready)


class ReliefTool(GridHeights):
    """Уклон, экспозиция, вершины и ямы участка у точки."""

    def __init__(self, window):
        super().__init__(window)
        self.dialog = None
        self.session = Session(window, tr("Уклон и экспозиция"))
        self.state = None  # сетка, высоты, результат, тело, неполнота
        self.tiles = None

    def relief_here(self, lat, lon):
        """Окно «Уклон и экспозиция» для точки - пункт подменю «Анализ
        рельефа» меню на глобусе."""
        dialog = self.dialog
        if dialog is None:
            dialog = ReliefDialog(self.window)
            dialog.build.connect(lambda: self._start(
                self.dialog, self._built))
            dialog.mode.connect(self.set_mode)
            dialog.peaks.connect(self.find_peaks)
            dialog.finished.connect(self._done)
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        return dialog

    # --- расчёт ------------------------------------------------------------

    def _built(self, dialog, grid, z, partial):
        mode = dialog.shown.currentData()
        result = relief.analyse(z, grid, ellipsoid.A, mode)
        rep = relief.summary(result)
        if rep is None:
            dialog.status.setText(tr("На участке нет высот."))
            return None
        self.state = {"grid": grid, "z": z, "result": result,
                      "partial": partial, "body": self.window.body_key()}
        dialog.set_ready(True)
        window = self.window
        # Строки «Уклон» и «Экспозиция» занимают тот же слой вида.
        # Выключенная строка показывает квадрат сама (_set_surface).
        rows = [key for key in ("slope", "aspect") if window.extras.get(key)]
        for key in rows:
            window.set_extra(key, False)
        if not rows:
            self.show()
        text = summary_text(rep) + " " + tr("Шаг сетки {step} м.",
                                            step=number(grid.cell))
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        dialog.status.setText(text + " " + built_text())
        return result

    def set_mode(self, mode):
        """Показ уклона или экспозиции без пересчёта."""
        state = self.state
        if state is None:
            return
        state["result"] = state["result"]._replace(mode=mode)
        self.show()

    # --- показ на глобусе --------------------------------------------------

    def show(self):
        """Участок на глобусе слоем «slope», если расчёт есть и тело
        прежнее. Зовётся и окном глобуса, когда строки «Уклон»
        и «Экспозиция» выключены (_set_surface)."""
        window = self.window
        state = self.state
        self._drop_tiles()
        if state is None or state["body"] != window.body_key() \
                or window.view.sky_view is not None:
            return False
        result = state["result"]
        tiles = ResultTiles(result, ellipsoid.A, relief.tile_rgba,
                            parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             window.view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        window.view.gibs[LAYER].max_level = display_level(
            result.grid.cell, result.lat, ellipsoid.A)
        window.view.set_gibs(LAYER, True, tiles)
        window.slope_legend.set_mode(result.mode)
        window.slope_legend.show()
        window._place_attribution()
        return True

    def _drop_tiles(self):
        if self.tiles is not None:
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def clear(self, quiet=False):
        """Убрать участок с глобуса. quiet - слой займёт строка
        «Уклон» или «Экспозиция», слой вида не трогается."""
        self.job = None
        self.timer.stop()
        self.window.spinner.set_job(self.busy_key())
        shown = self.tiles is not None
        self._drop_tiles()
        self.state = None
        if not quiet and shown:
            self.window.view.set_gibs(LAYER, False)
            self.window.slope_legend.hide()
        if self.dialog is not None:
            self.dialog.set_ready(False)
            if not quiet:
                self.dialog.status.setText("")

    # --- выгрузка ----------------------------------------------------------

    def _done(self, code):
        """Окно закрыто: OK - растры в подгруппу расчёта в проекте QGIS,
        иначе участок просто убирается (ui/results.py)."""
        if accepted(code):
            self.export()
        self.clear()
        self.session.reset()
        self.dialog.area.end()

    def export(self, path=None):
        """Растры уклона и экспозиции GeoTIFF в проект QGIS, отмечены на
        глобусе. path - файл уклона, без него - новый файл результата
        (ui/results.py), экспозиция - рядом с _aspect. Уклон слоем
        выше - его видно, экспозиция под ним."""
        state = self.state
        if state is None:
            return None
        if path is None:
            path = result_path("slope")
        result = state["result"]
        aspect_path = os.path.splitext(path)[0] + "_aspect.tif"
        if not (write_grid(path, result.grid, result.slope)
                and write_grid(aspect_path, result.grid, result.aspect)):
            self.dialog.status.setText(tr("Растры не записаны в «{path}».",
                                          path=path))
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        group = self.session.group_for(self.dialog.area.ring)
        first, second = (aspect_path, path) if result.mode == "slope" \
            else (path, aspect_path)
        layers = {}
        for file in (first, second):
            if file == path:
                layers[file] = add_raster(
                    path, tr("{name} - уклон, °", name=name),
                    [(b, c) for b, c in slope.SLOPE_STOPS],
                    group=group)
            else:
                layers[file] = add_raster(
                    aspect_path, tr("{name} - экспозиция, °", name=name),
                    [(b, c) for b, c in slope.ASPECT_STOPS],
                    group=group)
        # На глобусе - то, что показывал участок, второй растр только
        # в проекте.
        show_layer(self.window, layers[second])
        return path

    def find_peaks(self):
        """Вершины и ямы участка точечным слоем в подгруппу расчёта."""
        state = self.state
        dialog = self.dialog
        if state is None:
            return None
        grid = state["grid"]
        found = relief.extremes(state["z"], grid,
                                dialog.peak_radius.value(),
                                dialog.peak_drop.value())
        if not found:
            dialog.status.setText(tr("Вершин и ям с таким перепадом "
                                     "на участке нет."))
            return None
        items = []
        counts = {"peak": 0, "pit": 0}
        for row, col, height, drop, kind in found:
            counts[kind] += 1
            lat, lon = hydro.latlon(grid, row, col, ellipsoid.A)
            items.append(([(float(lat), float(lon))], {
                "kind": kind, "height": round(float(height), 1),
                "drop": round(float(drop), 1)}))
        path = result_path("peaks", ".gpkg")
        layer = None
        if write_vector(path, "peaks", "point", items,
                        [("kind", "str"), ("height", "real"),
                         ("drop", "real")]):
            layer = add_vector(
                self.window, path, "peaks",
                tr("Вершины и ямы {point}", point="{:.4f}, {:.4f}".format(
                    grid.lat, grid.lon)),
                self.session.group_for(dialog.area.ring), PEAK_COLOR,
                classes=("kind", [("peak", PEAK_COLOR[:3], tr("Вершина")),
                                  ("pit", PIT_COLOR[:3], tr("Яма"))]))
        dialog.status.setText(tr(
            "В проект добавлено вершин {peaks} и ям {pits}.",
            peaks=counts["peak"], pits=counts["pit"])
            if layer is not None else
            tr("Слой не записан в «{path}».", path=path))
        return layer


def write_grid(path, grid, values):
    """Значения сетки grid в GeoTIFF float32 EPSG:3857, NaN - нет
    данных. True, если записано."""
    from osgeo import gdal, osr
    from .inset import warm
    warm()
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    rows, cols = values.shape
    data = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    if data is None:
        return False
    data.SetGeoTransform((grid.x0 - grid.step / 2.0, grid.step, 0.0,
                          grid.y0 + grid.step / 2.0, 0.0, -grid.step))
    data.SetProjection(srs.ExportToWkt())
    band = data.GetRasterBand(1)
    band.SetNoDataValue(float("nan"))
    band.WriteArray(np.asarray(values, dtype=np.float32))
    data = None
    return True
