# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Классификация участка по эмбеддингам AlphaEarth: окно
«Классификация».

Просьба автора от 28 октября 2026 года по образцу «Классификации»
Google Earth. Пользователь заводит классы с цветом и названием, ставит
щелчком по глобусу контрольные точки класса, модуль берёт векторы
AlphaEarth участка на выбранный год и относит каждую клетку к классу
ближайших контрольных точек (core.aef.classify). Файлы и указатели -
те же, что у изменений местности (ui/aef.py). Показ - слой вида
«viewshed», общий с видимостью из точки: карта изменений на слое
«emag» остаётся видна.
"""
import math
import os

import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QButtonGroup, QColorDialog, QComboBox,
                                 QDialog, QDialogButtonBox, QFileDialog,
                                 QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QRadioButton, QSlider,
                                 QToolButton, QVBoxLayout, QWidget)

from ..core import aef
from ..core.cog import tile_points
from ..core.features import Shape
from ..core.mipmap import mip_chain
from ..i18n import tr
from ..qt_compat import enum
from .aef import _INDEX, _poll_job, _run_job, index_of, open_cog, \
    zstd_ready
from .hydro import _spin
from .threadtiles import ThreadTiles
from .viewshed import fit_status

LAYER = "viewshed"  # слой вида, общий с видимостью из точки
SETTINGS = "PlanetX/aef_class/"
# Цвета новых классов по порядку - выбор помощника.
COLORS = ((60, 160, 70), (40, 110, 220), (240, 190, 40), (200, 60, 50),
          (150, 90, 200), (120, 120, 120), (240, 130, 40), (60, 200, 200))
OPACITY = 0.6
AREA_COLOR = (255, 255, 255, 255)
CLASS_SIDE = 10.0  # км, наибольшая сторона участка классификации


def group_name():
    return tr("PlanetX - классификация")


class ClassTiles(ThreadTiles):
    """Картинки тайлов классов участка: загрузчик слоя вида, пустой
    тайл - вне участка."""

    def __init__(self, result, opacity, parent=None):
        super().__init__(2, 4, "aef class", parent)
        self.result = result
        self.opacity = opacity

    def work(self, key):
        result = self.result
        z, x, y = key
        n = 1 << z
        west, south, east, north = result["box"]
        tw = x / n * 360.0 - 180.0
        te = (x + 1) / n * 360.0 - 180.0
        tn = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
        ts = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * (y + 1)
                                                         / n))))
        if tw > east or te < west or ts > north or tn < south:
            return None, None
        lon, lat = tile_points(z, x, y)
        index = result["index"]
        xs, ys = index.project(lon.ravel(), lat.ravel())
        step = result["step"]
        cols = np.floor((xs - result["x0"]) / step).astype(int)
        rows = np.floor((result["y0"] - ys) / step).astype(int)
        classes = result["classes"]
        ok = (cols >= 0) & (rows >= 0) & (cols < classes.shape[1]) \
            & (rows < classes.shape[0])
        code = np.full(cols.shape, -1, dtype=np.int16)
        code[ok] = classes[rows[ok], cols[ok]]
        palette = np.zeros((len(result["colors"]) + 1, 4), dtype=np.uint8)
        for n_, color in enumerate(result["colors"]):
            palette[n_] = tuple(color[:3]) + (int(255 * self.opacity),)
        rgba = palette[np.where(code >= 0, code, len(result["colors"]))]
        rgba = rgba.reshape(lon.shape + (4,))
        return rgba, mip_chain(rgba)


class ClassRow(QWidget):
    """Строка класса: выбор, цвет, название, количество точек,
    удаление."""

    removed = pyqtSignal(object)
    edited = pyqtSignal()

    def __init__(self, color, name, parent=None):
        super().__init__(parent)
        self.color = QColor(*color)
        self.pick = QRadioButton(self)
        self.pick.setToolTip(tr("Щелчок по глобусу ставит точку этого "
                                "класса."))
        self.swatch = QToolButton(self)
        self.swatch.setToolTip(tr("Цвет класса на глобусе и в растре."))
        self.swatch.clicked.connect(self._choose)
        self.name = QLineEdit(name, self)
        self.name.textEdited.connect(lambda _: self.edited.emit())
        self.count = QLabel("0", self)
        self.count.setToolTip(tr("Контрольных точек класса."))
        remove = QToolButton(self)
        remove.setText("✕")
        remove.setToolTip(tr("Убрать класс и его точки."))
        remove.clicked.connect(lambda: self.removed.emit(self))
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for widget in (self.pick, self.swatch, self.name, self.count,
                       remove):
            layout.addWidget(widget)
        self.points = []
        self._paint()

    def rgb(self):
        return (self.color.red(), self.color.green(), self.color.blue())

    def _paint(self):
        self.swatch.setStyleSheet(
            "QToolButton {{ background: {}; min-width: 18px; }}".format(
                self.color.name()))

    def _choose(self):
        color = QColorDialog.getColor(self.color, self)
        if color.isValid():
            self.color = color
            self._paint()
            self.edited.emit()

    def set_points(self, points):
        self.points = points
        self.count.setText(str(len(points)))


class ClassDialog(QDialog):
    """Окно «Классификация». Сигналы build, export, changed - точки,
    классы или цвета, opacity, clear."""

    build = pyqtSignal()
    export = pyqtSignal()
    changed = pyqtSignal()
    opacity = pyqtSignal(float)
    clear = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Классификация"))
        self.point = None
        settings = QgsSettings()
        self.place = QLabel(self)
        self.year = QComboBox(self)
        for year in aef.YEARS:
            self.year.addItem(str(year), year)
        self.year.setCurrentIndex(self.year.findData(int(settings.value(
            SETTINGS + "year", aef.YEARS[-1]))))
        self.year.setToolTip(tr(
            "Год, по векторам которого клетки делятся на классы. Точки "
            "ставятся по снимку глобуса, он может быть другого года."))
        self.side = _spin(self, 0.5, CLASS_SIDE, float(settings.value(
            SETTINGS + "side", 3.0)), tr(" км"))
        self.side.setToolTip(tr(
            "Сторона квадрата классификации с серединой в точке окна. "
            "Точки вне квадрата не учитываются."))
        self.level = QComboBox(self)
        for level, pixel in aef.DETAIL_LEVELS:
            self.level.addItem(tr("{pixel} м", pixel=pixel), level)
        self.level.setCurrentIndex(self.level.findData(int(
            settings.value(SETTINGS + "level", 0))))
        self.level.setToolTip(tr(
            "Пиксель классификации. Блок файла за год - 40-50 МБ при "
            "любом пикселе. Блок пикселя 10 м покрывает 10 км, 80 м - "
            "82 км."))
        self.volume = QLabel(self)
        self.rows_box = QVBoxLayout()
        self.group = QButtonGroup(self)
        self.rows = []
        add = QPushButton(tr("Добавить класс"), self)
        add.clicked.connect(lambda: self.add_class())
        self.alpha = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.alpha.setRange(0, 100)
        self.alpha.setValue(int(round(100 * float(settings.value(
            SETTINGS + "opacity", OPACITY)))))
        self.alpha.setToolTip(tr("Непрозрачность классов на глобусе."))
        self.alpha.valueChanged.connect(
            lambda v: self.opacity.emit(v / 100.0))
        hint = QLabel(tr(
            "Щёлкните по глобусу, чтобы поставить точку выбранного "
            "класса. Нужно хотя бы два класса по три точки."), self)
        hint.setWordWrap(True)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Год"), self.year)
        form.addRow(tr("Участок"), self.side)
        form.addRow(tr("Пиксель"), self.level)
        form.addRow("", self.volume)
        form.addRow(tr("Непрозрачность"), self.alpha)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Каждая клетка участка относится к классу ближайших "
            "контрольных точек по векторам AlphaEarth."))
        run.clicked.connect(self.build)
        self.to_project = QPushButton(tr("В проект QGIS…"), self)
        self.to_project.setToolTip(tr(
            "Классы участка растром GeoTIFF в системе UTM в проект QGIS."))
        self.to_project.clicked.connect(self.export)
        undo = QPushButton(tr("Убрать точку"), self)
        undo.setToolTip(tr("Убрать последнюю точку выбранного класса."))
        undo.clicked.connect(self._undo)
        remove = QPushButton(tr("Убрать"), self)
        remove.setToolTip(tr("Убрать классы с глобуса, точки остаются."))
        remove.clicked.connect(self.clear)
        for button in (run, self.to_project, undo, remove):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel(tr("Классы"), self))
        layout.addLayout(self.rows_box)
        layout.addWidget(add)
        layout.addWidget(hint)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        for _ in range(2):
            self.add_class()
        self.rows[0].pick.setChecked(True)
        for box in (self.year, self.level):
            box.currentIndexChanged.connect(lambda _: self._remember())
        self.side.valueChanged.connect(lambda _: self._remember())
        self.set_ready(False)

    def add_class(self, name=None):
        color = COLORS[len(self.rows) % len(COLORS)]
        row = ClassRow(color, name or tr("Класс {n}", n=len(self.rows) + 1),
                       self)
        row.removed.connect(self._remove)
        row.edited.connect(self.changed)
        self.group.addButton(row.pick)
        self.rows.append(row)
        self.rows_box.addWidget(row)
        row.pick.setChecked(True)
        return row

    def _remove(self, row):
        if row not in self.rows:
            return
        self.rows.remove(row)
        self.group.removeButton(row.pick)
        row.setParent(None)
        row.deleteLater()
        if self.rows and self.active() is None:
            self.rows[0].pick.setChecked(True)
        self.changed.emit()

    def active(self):
        for row in self.rows:
            if row.pick.isChecked():
                return row
        return None

    def _undo(self):
        row = self.active()
        if row is not None and row.points:
            row.set_points(row.points[:-1])
            self.changed.emit()

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "year", self.year.currentData())
        settings.setValue(SETTINGS + "side", self.side.value())
        settings.setValue(SETTINGS + "level", self.level.currentData())
        settings.setValue(SETTINGS + "opacity", self.alpha.value() / 100.0)
        self.volume_changed()

    def box(self):
        lat, lon = self.point
        return aef.square(lat, lon, self.side.value() * 1000.0)

    def volume_changed(self):
        if self.point is None:
            return
        lat, lon = self.point
        index = _INDEX.get(aef.zone_of(lon, lat))
        if index is None:
            self.volume.setText("")
            return
        level = self.level.currentData()
        parts = aef.detail_parts(index, self.box(), level)
        self.volume.setText(tr("Загрузка около {mb} МБ", mb="{:.0f}".format(
            aef.detail_megabytes(parts, level) / 2.0)))

    def set_ready(self, ready):
        self.to_project.setEnabled(ready)


class ClassTool(QObject):
    """Классификация участка у окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.result = None
        self.grid = None  # (ключ участка, данные vectors)
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.shapes = []

    def open_here(self, lat, lon):
        """Окно «Классификация» для точки - пункт подменю «Анализ
        участка» меню на глобусе."""
        dialog = self.dialog
        if dialog is None:
            dialog = ClassDialog(self.window)
            dialog.build.connect(self.build)
            dialog.export.connect(self.export)
            dialog.changed.connect(self._update_shapes)
            dialog.opacity.connect(lambda _: self.show())
            dialog.clear.connect(self.clear)
            dialog.finished.connect(lambda _: self._update_shapes())
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        zone = aef.zone_of(lon, lat)
        _run_job(self, lambda: index_of(zone),
                 lambda _: dialog.volume_changed())
        dialog.show()
        dialog.raise_()
        self._update_shapes()
        return dialog

    def taking(self):
        """Окно открыто и выбран класс: щелчок по глобусу - точка."""
        dialog = self.dialog
        return dialog is not None and dialog.isVisible() \
            and dialog.active() is not None

    def add_point(self, lat, lon):
        row = self.dialog.active()
        row.set_points(row.points + [(lat, lon)])
        self._update_shapes()

    def _update_shapes(self):
        shapes = []
        dialog = self.dialog
        if dialog is not None and dialog.isVisible():
            if dialog.point is not None:
                west, south, east, north = dialog.box()
                shapes.append(Shape("polygon", [
                    (south, west), (south, east), (north, east),
                    (north, west)], color=AREA_COLOR, width=2.0))
            for row in dialog.rows:
                for lat, lon in row.points:
                    shapes.append(Shape("point", [(lat, lon)],
                                        color=row.rgb() + (255,),
                                        width=10.0))
        self.shapes = shapes
        self.window.class_shapes = shapes
        self.window._refresh_shapes()

    # --- расчёт ---------------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or dialog.point is None:
            return
        if not zstd_ready():
            dialog.status.setText(tr(
                "Нет библиотеки zstd, файлы AlphaEarth не прочитать."))
            return
        rows = [row for row in dialog.rows if row.points]
        if len(rows) < aef.MIN_CLASSES or any(
                len(row.points) < aef.MIN_POINTS for row in rows):
            dialog.status.setText(tr(
                "Нужно хотя бы два класса по три точки."))
            return
        box = dialog.box()
        year = dialog.year.currentData()
        level = dialog.level.currentData()
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        points = [(n, p) for n, row in enumerate(rows) for p in row.points]
        colors = [row.rgb() for row in rows]
        names = [row.name.text() for row in rows]
        key = (box, year, level)
        cached = self.grid if self.grid and self.grid[0] == key else None

        def work():
            index = index_of(zone)
            if index is None:
                return None
            found = cached[1] if cached else aef.vectors(
                open_cog, index, box, level, year)
            if found is None:
                return None
            x0, y0, step, grid = found
            samples, labels, outside = [], [], 0
            for label, (plat, plon) in points:
                r, c = aef.pixel_of(index, x0, y0, step, plat, plon)
                if 0 <= r < grid.shape[1] and 0 <= c < grid.shape[2]:
                    samples.append(grid[:, r, c])
                    labels.append(label)
                else:
                    outside += 1
            if not samples:
                return {"index": index, "found": found, "outside": outside,
                        "classes": None}
            classes, score = aef.classify(
                grid, np.stack(samples, axis=1), labels)
            return {"index": index, "found": found, "outside": outside,
                    "classes": classes, "score": score}

        dialog.status.setText(tr("Загружаются векторы участка…"))
        _run_job(self, work, lambda out: self._built(
            out, key, box, year, colors, names))

    def _built(self, out, key, box, year, colors, names):
        dialog = self.dialog
        if out is None:
            dialog.status.setText(tr("Для участка нет данных."))
            return
        self.grid = (key, out["found"])
        if out["classes"] is None:
            dialog.status.setText(tr("Все точки вне участка."))
            return
        x0, y0, step, _ = out["found"]
        classes = out["classes"]
        self.result = {"index": out["index"], "x0": x0, "y0": y0,
                       "step": step, "classes": classes, "colors": colors,
                       "names": names, "box": box, "year": year}
        counts = [int((classes == n).sum()) for n in range(len(colors))]
        total = max(sum(counts), 1)
        parts = ", ".join("{} {:.0f}%".format(name, 100.0 * c / total)
                          for name, c in zip(names, counts))
        text = tr("Классы {year} года: {parts}.", year=year, parts=parts)
        if out["outside"]:
            text += " " + tr("Точек вне участка: {n}.", n=out["outside"])
        dialog.status.setText(text)
        dialog.set_ready(True)
        self.show()

    def _poll(self):
        _poll_job(self)

    def result_pixel(self, lat, lon):
        """Строка и столбец сетки классов для точки."""
        res = self.result
        return aef.pixel_of(res["index"], res["x0"], res["y0"],
                            res["step"], lat, lon)

    # --- показ ----------------------------------------------------------

    def show(self):
        window = self.window
        result = self.result
        self._drop_tiles()
        if result is None:
            return
        window._show_viewshed(None)
        opacity = self.dialog.alpha.value() / 100.0 if self.dialog \
            else OPACITY
        tiles = ClassTiles(result, opacity, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             window.view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        layer = window.view.gibs[LAYER]
        lat = (result["box"][1] + result["box"][3]) / 2.0
        pixel = 2 * math.pi * 6378137.0 * math.cos(math.radians(lat)) / 256
        layer.max_level = max(1, min(18, int(math.ceil(
            math.log2(pixel / result["step"])))))
        layer.empty.clear()
        window.view.set_gibs(LAYER, True, tiles)

    def _drop_tiles(self):
        if self.tiles is not None:
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def drop(self):
        """Слой вида занимает видимость - классы снимаются без снятия
        слоя."""
        self._drop_tiles()
        self.result = None
        if self.dialog is not None:
            self.dialog.set_ready(False)

    def clear(self):
        shown = self.tiles is not None
        self.drop()
        if shown:
            self.window.view.set_gibs(LAYER, False)

    # --- выгрузка -------------------------------------------------------

    def export(self, path=None):
        result = self.result
        if result is None:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self.window, tr("Классификация в проект QGIS"),
                os.path.join(QgsProject.instance().homePath()
                             or os.path.expanduser("~"),
                             "classes_{}.tif".format(result["year"])),
                tr("GeoTIFF (*.tif)"))
        if not path:
            return None
        if not write_classes(path, result):
            self.dialog.status.setText(tr("Растр не записан в «{path}».",
                                          path=path))
            return None
        add_classes(path, tr("Классификация {year}", year=result["year"]),
                    result)
        self.dialog.status.setText(tr("Растр классов в проекте."))
        return path

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


def write_classes(path, result):
    """Классы GeoTIFF Byte в UTM: номер класса + 1, 0 - нет данных."""
    from osgeo import gdal, osr
    from .inset import warm
    warm()
    index = result["index"]
    srs = osr.SpatialReference()
    srs.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    classes = result["classes"]
    rows, cols = classes.shape
    data = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, gdal.GDT_Byte, ["COMPRESS=DEFLATE"])
    if data is None:
        return False
    step = result["step"]
    data.SetGeoTransform((result["x0"], step, 0.0, result["y0"], 0.0,
                          -step))
    data.SetProjection(srs.ExportToWkt())
    band = data.GetRasterBand(1)
    band.SetNoDataValue(0)
    band.WriteArray((classes + 1).astype(np.uint8))
    data = None
    return True


def add_classes(path, title, result):
    """Растр классов в проект с цветами и названиями классов."""
    from qgis.core import (QgsPalettedRasterRenderer, QgsRasterLayer)
    from .export import _to_group
    layer = QgsRasterLayer(path, title, "gdal")
    if not layer.isValid():
        return None
    classes = [QgsPalettedRasterRenderer.Class(
        n + 1, QColor(*color), name)
        for n, (color, name) in enumerate(zip(result["colors"],
                                              result["names"]))]
    layer.setRenderer(QgsPalettedRasterRenderer(layer.dataProvider(), 1,
                                                classes))
    meta = layer.metadata()
    meta.setRights([aef.CREDIT])
    layer.setMetadata(meta)
    return _to_group(layer, group_name())
