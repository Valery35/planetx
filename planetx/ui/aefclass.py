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
«emag» остаётся видна. Участок - многоугольник (ui/area.py), образец
общего участка окон анализа.
"""
import math

import numpy as np
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QButtonGroup, QColorDialog, QComboBox,
                                 QDialog, QDialogButtonBox, QFormLayout,
                                 QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QRadioButton, QSlider,
                                 QToolButton, QVBoxLayout, QWidget)

from ..core import aef, editing
from ..core.cog import tile_points
from ..core.ellipsoid import geodetic_to_ecef
from ..core.features import Shape
from ..core.mipmap import mip_chain
from ..i18n import tr
from ..qt_compat import enum
from .aef import _INDEX, _poll_job, _run_job, index_of, open_cog, \
    stop_point, zstd_ready
from .area import Area
from .handles import GRAB_PIXELS
from .results import (Session, accepted, add_vector, keep_buttons,
                      result_path, show_layer, write_vector)
from .threadtiles import ThreadTiles
from .viewshed import fit_status

LAYER = "viewshed"  # слой вида, общий с видимостью из точки
SETTINGS = "PlanetX/aef_class/"
# Цвета новых классов по порядку - выбор помощника.
COLORS = ((60, 160, 70), (40, 110, 220), (240, 190, 40), (200, 60, 50),
          (150, 90, 200), (120, 120, 120), (240, 130, 40), (60, 200, 200))
OPACITY = 0.6
CLASS_SIDE = 10.0  # км, наибольшая сторона участка классификации
AUTO = -1  # пиксель «Авто» в списке


class ClassTiles(ThreadTiles):
    """Картинки тайлов классов участка: загрузчик слоя вида, пустой
    тайл - вне участка."""

    def __init__(self, result, parent=None):
        super().__init__(2, 4, "aef class", parent)
        self.result = result

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
            # Непрозрачность - у слоя вида (ClassTool.set_opacity).
            palette[n_] = tuple(color[:3]) + (255,)
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
    """Окно «Классификация». Сигналы build, changed - точки, классы,
    цвета или участок, opacity. OK записывает классы в проект QGIS,
    «Отмена» убирает их (ui/results.py)."""

    build = pyqtSignal()
    changed = pyqtSignal()
    opacity = pyqtSignal(float)

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Классификация"))
        self.point = None
        settings = QgsSettings()
        self.place = QLabel(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, 3.0, CLASS_SIDE, SETTINGS + "side")
        self.area.changed.connect(self.area_edited)
        self.area.point_hint = tr("Убрать точку")
        self.year = QComboBox(self)
        for year in aef.YEARS:
            self.year.addItem(str(year), year)
        self.year.setCurrentIndex(self.year.findData(int(settings.value(
            SETTINGS + "year", aef.YEARS[-1]))))
        self.year.setToolTip(tr(
            "Год, по векторам которого клетки делятся на классы. Точки "
            "ставятся по снимку глобуса, он может быть другого года."))
        self.level = QComboBox(self)
        self.level.addItem(tr("Авто"), AUTO)
        for level, pixel in aef.DETAIL_LEVELS:
            self.level.addItem(tr("{pixel} м", pixel=pixel), level)
        self.level.setCurrentIndex(max(0, self.level.findData(int(
            settings.value(SETTINGS + "pixel", AUTO)))))
        self.level.setToolTip(tr(
            "Пиксель классификации. Блок файла за год - 40-50 МБ при "
            "любом пикселе. Блок пикселя 10 м покрывает 10 км, 80 м - "
            "82 км. «Авто» берёт пиксель с наименьшей загрузкой, при котором "
            "на участке от 14 до 640 тысяч клеток."))
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
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Год"), self.year)
        form.addRow(tr("Участок"), self.area.widget)
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
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
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
        self.alpha.valueChanged.connect(lambda _: self._remember())
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

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "year", self.year.currentData())
        settings.setValue(SETTINGS + "pixel", self.level.currentData())
        settings.setValue(SETTINGS + "opacity", self.alpha.value() / 100.0)
        self.volume_changed()

    # --- участок ---------------------------------------------------------

    def area_edited(self):
        self.volume_changed()
        self.changed.emit()

    def volume_changed(self):
        if self.point is None:
            return
        problem = self.area.check()
        if problem:
            self.volume.setText(problem)
            return
        lat, lon = self.point
        index = _INDEX.get(aef.zone_of(lon, lat))
        if index is None:
            self.volume.setText("")
            return
        level = self.pixel_level(index)
        parts = aef.detail_parts(index, self.area.box(), level)
        self.volume.setText(tr(
            "Пиксель {pixel} м, загрузка около {mb} МБ",
            pixel=dict(aef.DETAIL_LEVELS)[level], mb="{:.0f}".format(
                aef.detail_megabytes(parts, level) / 2.0)))

    def pixel_level(self, index):
        """Уровень пикселя, у «Авто» - по участку."""
        level = self.level.currentData()
        if level == AUTO:
            level = aef.auto_level(index, self.area.box(),
                                   self.area.size())
        return level

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
        self.progress = [0, 0]  # блоков загружено, всего
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.shapes = []
        self.session = Session(window, tr("Классификация"))

    def open_here(self, lat, lon):
        """Окно «Классификация» для точки - пункт подменю «Анализ
        участка» меню на глобусе."""
        dialog = self.dialog
        if dialog is None:
            dialog = ClassDialog(self.window)
            dialog.build.connect(self.build)
            dialog.changed.connect(self._update_shapes)
            dialog.opacity.connect(self.set_opacity)
            dialog.finished.connect(self._closed)
            dialog.area.point_under = self.point_under
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        zone = aef.zone_of(lon, lat)
        _run_job(self, lambda: index_of(zone),
                 lambda _: dialog.volume_changed())
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        self._update_shapes()
        return dialog

    def _closed(self, code=0):
        """Окно закрыто: OK - классы растром в проект QGIS, иначе
        предпросмотр убирается (ui/results.py). Точки и классы окна
        остаются до следующего открытия."""
        if accepted(code) and self.result is not None:
            self.export()
        self.clear()
        self.session.reset()
        self.dialog.area.end()
        self._update_shapes()

    def taking(self):
        """Окно открыто и выбран класс: щелчок по глобусу - точка класса.
        Вершины рисуемого участка ставит участок (ui/area.py)."""
        dialog = self.dialog
        return dialog is not None and dialog.isVisible() \
            and not dialog.area.drawing and dialog.active() is not None

    def point_under(self, px, py):
        """Точка класса под пикселем кадра: (строка класса, номер точки)
        или None."""
        dialog = self.dialog
        found = [(row, n, p) for row in dialog.rows
                 for n, p in enumerate(row.points)]
        if not found:
            return None
        view = self.window.view
        lats = np.array([p[0] for _, _, p in found])
        lons = np.array([p[1] for _, _, p in found])
        xyz = geodetic_to_ecef(lats, lons, view.label_heights(lats, lons))
        pixels, front = view.camera.project(xyz)
        hit = editing.pick(pixels, front, [], [], px, py,
                           GRAB_PIXELS * view.devicePixelRatioF())
        if hit is None:
            return None
        row, n, _ = found[hit[1]]
        return row, n

    def click(self, px, py, lat, lon):
        """Щелчок по глобусу при открытом окне: точка класса под курсором
        убирается, на пустом месте ставится точка выбранного класса."""
        dialog = self.dialog
        under = self.point_under(px, py)
        if under is not None:
            row, n = under
            row.set_points(row.points[:n] + row.points[n + 1:])
            self._update_shapes()
            return
        if dialog.active() is None:
            return
        self.add_point(lat, lon)

    def add_point(self, lat, lon):
        dialog = self.dialog
        if dialog.area.drawing:
            dialog.area.add(lat, lon)
            return
        row = dialog.active()
        row.set_points(row.points + [(lat, lon)])
        self._update_shapes()

    def _update_shapes(self):
        shapes = []
        dialog = self.dialog
        if dialog is not None and dialog.isVisible():
            for row in dialog.rows:
                for lat, lon in row.points:
                    shapes.append(Shape("point", [(lat, lon)],
                                        color=row.rgb() + (255,),
                                        width=10.0))
        self.shapes = shapes
        self.window.class_shapes = shapes
        self.window._refresh_shapes()
        self.window.handles.sync()

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
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        side = dialog.area.size()
        ring = list(dialog.area.ring)
        box = dialog.area.box()
        year = dialog.year.currentData()
        level = dialog.level.currentData()
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        points = [(n, p) for n, row in enumerate(rows) for p in row.points]
        colors = [row.rgb() for row in rows]
        names = [row.name.text() for row in rows]
        key = (box, year, level)
        cached = self.grid if self.grid and self.grid[0] == key else None
        progress = self.progress = [0, 0]

        def count(done, total):
            stop_point(self)  # остановка меню значка - перед блоком
            progress[:] = [done, total]

        def work():
            index = index_of(zone)
            if index is None:
                return None
            pick = aef.auto_level(index, box, side) if level == AUTO \
                else level
            found = cached[1] if cached else aef.vectors(
                open_cog, index, box, pick, year, progress=count)
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
            # Вне многоугольника участка классов нет.
            inside = aef.ring_mask(index, x0, y0, step, classes.shape, ring)
            classes[~inside] = -1
            score[~inside] = np.nan
            return {"index": index, "found": found, "outside": outside,
                    "classes": classes, "score": score}

        dialog.status.setText(tr("Загружаются векторы участка…"))
        _run_job(self, work, lambda out: self._built(
            out, key, box, year, colors, names), tr("Классификация"))

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
                       "names": names, "box": box, "year": year,
                       "ring": list(self.dialog.area.ring)}
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
        done, total = self.progress
        if self.job is not None and total > 1 and self.dialog is not None:
            self.dialog.status.setText(tr(
                "Загружаются векторы участка, блок {n} из {total}…",
                n=min(done + 1, total), total=total))
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
        tiles = ClassTiles(result, parent=self)
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
        self.set_opacity(self.dialog.alpha.value() / 100.0 if self.dialog
                         else OPACITY)

    def set_opacity(self, value):
        """Непрозрачность классов - доля прозрачности слоя вида, без
        пересборки картинок тайлов."""
        if self.tiles is None:
            return
        self.window.view.gibs[LAYER].fade = 1.0 - value
        self.window.view.update()

    def _drop_tiles(self):
        if self.tiles is not None:
            # Слой вида общий с видимостью из точки, её прозрачность своя.
            self.window.view.gibs[LAYER].fade = 0.0
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
        """Классы растром в проект QGIS, отмечены на глобусе. path -
        файл, без него - новый файл результата (ui/results.py)."""
        result = self.result
        if result is None:
            return None
        if path is None:
            path = result_path("classes_{}".format(result["year"]))
        if not write_classes(path, result):
            self.dialog.status.setText(tr("Растр не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        layer = add_classes(path, tr("Классификация {year}",
                                     year=result["year"]), result, group)
        if layer is not None:
            layer.setOpacity(self.dialog.alpha.value() / 100.0)
        show_layer(self.window, layer)
        self._export_points(result["year"], group)
        self.dialog.status.setText(tr("Растр классов в проекте."))
        return path

    def _export_points(self, year, group):
        """Контрольные точки слоем GeoPackage в подгруппу расчёта: поля
        class (номер с 1) и name, цвет точки - цвет класса."""
        rows = [row for row in self.dialog.rows if row.points]
        items = [([point], {"class": n, "name": row.name.text()})
                 for n, row in enumerate(self.dialog.rows, 1)
                 for point in row.points]
        if not items:
            return None
        path = result_path("class_points_{}".format(year), ".gpkg")
        if not write_vector(path, "points", "point", items,
                            [("class", "int"), ("name", "str")]):
            return None
        return add_vector(
            self.window, path, "points",
            tr("Контрольные точки {year}", year=year), group,
            rows[0].rgb(), classes=("class", [
                (n, row.rgb(), row.name.text())
                for n, row in enumerate(self.dialog.rows, 1)
                if row.points]))

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


def add_classes(path, title, result, group):
    """Растр классов в проект в группу group с цветами и названиями
    классов."""
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
    return _to_group(layer, group)
