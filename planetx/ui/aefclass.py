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

Источник клеток - AlphaEarth или растр проекта QGIS, просьба Василия
Швалёва от 31 октября 2026 года. Каналы растра - признаки клетки
(core/rasterclass.py). Растр читает рабочий поток через GDAL с пересчётом
на сетку участка в UTM, дальше всё общее с AlphaEarth: окно тайлов,
запись растра классов, точки и подгруппа расчёта.

Источник «Подложка глобуса» - вопрос Василия Швалёва от 1 ноября 2026
года: тайлы текущей подложки под участком собираются в растр в памяти
(core/tilemosaic.py), дальше всё, как у растра проекта.

Флажок «Делить на объекты» - просьба автора от 1 ноября 2026 года.
Участок растра сначала делится на объекты, похожие по цвету и текстуре
(core/segments.py), класс получает объект по средним и разбросам
каналов, итог - многоугольники GeoPackage.
"""
import math

import numpy as np
from qgis.core import QgsProject, QgsRasterLayer, QgsSettings
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QButtonGroup, QCheckBox, QColorDialog,
                                 QComboBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QLabel,
                                 QLineEdit, QPushButton, QRadioButton,
                                 QSlider, QSpinBox, QToolButton,
                                 QVBoxLayout, QWidget)

from ..core import aef, editing, rasterclass, segments, tilemosaic, tracing
from ..core.cog import tile_points
from ..core.ellipsoid import geodetic_to_ecef
from ..core.features import Shape
from ..core.mipmap import mip_chain
from ..i18n import tr
from ..net import ranges
from ..qt_compat import enum
from .aef import _INDEX, _poll_job, _run_job, index_of, open_cog, \
    stop_point, zstd_ready
from .area import Area
from .handles import GRAB_PIXELS
from .inset import warm
from .results import (Session, accepted, add_vector, built_text,
                      keep_buttons, result_path, set_abstract, show_layer,
                      titled, write_vector)
from .sitelayer import SiteTool, add_preview, class_rows, result_level
from .threadtiles import ThreadTiles
from .tilemosaic import dataset as tile_dataset
from .viewshed import fit_status

SETTINGS = "PlanetX/aef_class/"
# Цвета новых классов по порядку - выбор помощника.
COLORS = ((60, 160, 70), (40, 110, 220), (240, 190, 40), (200, 60, 50),
          (150, 90, 200), (120, 120, 120), (240, 130, 40), (60, 200, 200))
OPACITY = 0.6
CLASS_SIDE = 10.0  # км, наибольшая сторона участка AlphaEarth
# км, у растра проекта. Защита от больших сеток - rasterclass.too_big.
RASTER_SIDE = 1000.0
AUTO = -1  # пиксель «Авто» в списке
BASEMAP = "@basemap"  # источник «Подложка глобуса» в списке
PIXEL_DEFAULT = 10.0  # м, пиксель «Авто», если растр его не называет
COVERED = 0.995  # доля участка, ниже которой итог называет покрытие
BORDER = (20, 20, 20, 255)  # граница объектов на глобусе
# Пиксели снимка мельче 10 м - только у растра проекта и подложки: у
# AlphaEarth мельче 10 м данных нет. Номера ниже AUTO, уровни AlphaEarth
# с 0.
FINE_PIXELS = ((-4, 1), (-3, 2), (-2, 5))
# Клеток образца с контура: поровну по клеткам внутри, голос класса
# делится на количество его образцов (core/rasterclass.py). Выбор помощника.
RING_CELLS = 40
PIXELS = dict(FINE_PIXELS + aef.DETAIL_LEVELS)


def fill_pixels(box, raster, wanted=None):
    """Список «Пиксель»: «Авто», у растра и подложки - ещё 1, 2 и 5 м,
    затем 10-80 м. Выбор wanted (иначе прежний) остаётся, если он есть
    в новом списке, иначе «Авто». Сигналы списка на время молчат."""
    if wanted is None:
        wanted = box.currentData()
    box.blockSignals(True)
    box.clear()
    box.addItem(tr("Авто"), AUTO)
    for level, pixel in (FINE_PIXELS if raster else ()) + aef.DETAIL_LEVELS:
        box.addItem(tr("{pixel} м", pixel=pixel), level)
    box.setCurrentIndex(max(0, box.findData(wanted)))
    box.blockSignals(False)


def pixel_text(window, source, layer, level, box, side):
    """Строка под полем «Пиксель» у растра и подложки: шаг сетки, у «Авто» -
    каким он выйдет, и количество клеток участка."""
    lat = (box[1] + box[3]) / 2.0
    if level != AUTO:
        pixel = PIXELS[level]
    elif source == BASEMAP:
        pixel = rasterclass.auto_pixel(tilemosaic.tile_pixel(
            lat, window._earth_source().max_level), side)
    else:
        native = layer.rasterUnitsPerPixelX()
        if layer.crs().isGeographic():
            native *= 111320.0 * math.cos(math.radians(lat))
        pixel = rasterclass.auto_pixel(native or PIXEL_DEFAULT, side)
    cells = (side / pixel) ** 2
    text = tr("Пиксель {pixel} м, клеток около {cells} тыс.",
              pixel="{:.3g}".format(pixel),
              cells=int(round(cells / 1000.0)))
    if cells > segments.MAX_CELLS:
        text += " " + tr("На объекты участок не разделится, нужен пиксель "
                         "крупнее или участок меньше.")
    return text


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
        count = len(result["colors"])
        palette = np.zeros((count + 2, 4), dtype=np.uint8)
        palette[count + 1] = BORDER
        hidden = result.get("hidden") or ()
        for n_, color in enumerate(result["colors"]):
            # Непрозрачность - у слоя вида (ClassTool.set_opacity), класс
            # со снятым флажком «Видно» прозрачен.
            palette[n_] = tuple(color[:3]) + (
                0 if tuple(color[:3]) in hidden else 255,)
        code = np.where(code >= 0, code, count)
        parts = result.get("parts")
        if parts is not None:
            # Граница - по пикселям тайла: клетка границы на редкой выборке
            # дала бы пунктир.
            found = np.full(cols.shape, -1, dtype=np.int32)
            found[ok] = parts[rows[ok], cols[ok]]
            code[segments.borders(found.reshape(lon.shape)).ravel()] = \
                count + 1
        rgba = palette[code]
        rgba = rgba.reshape(lon.shape + (4,))
        return rgba, mip_chain(rgba)


class SourceBox(QComboBox):
    """Список источников: AlphaEarth, подложка глобуса и растры проекта.
    Заполняется при открытии списка - слежения за проектом у закрытого
    окна нет."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.refill()

    def refill(self):
        chosen = self.currentData()
        self.blockSignals(True)
        self.clear()
        self.addItem(tr("Эмбеддинги AlphaEarth"), "")
        self.addItem(tr("Подложка глобуса"), BASEMAP)
        for layer in project_rasters():
            self.addItem(layer.name(), layer.id())
        self.setCurrentIndex(max(0, self.findData(chosen)))
        self.blockSignals(False)
        if self.currentData() != (chosen or ""):
            self.currentIndexChanged.emit(self.currentIndex())

    def showPopup(self):
        self.refill()
        super().showPopup()


class ClassRow(QWidget):
    """Строка класса: выбор, цвет, название, количество точек,
    удаление."""

    removed = pyqtSignal(object)
    edited = pyqtSignal()
    seen = pyqtSignal()  # флажок «Видно»

    def __init__(self, color, name, parent=None):
        super().__init__(parent)
        self.color = QColor(*color)
        self.pick = QRadioButton(self)
        self.pick.setToolTip(tr("Щелчок по глобусу ставит точку этого "
                                "класса."))
        self.visible = QCheckBox(self)
        self.visible.setChecked(True)
        self.visible.setToolTip(tr(
            "Класс виден на глобусе. Снятый флажок открывает местность под "
            "классом, класс остаётся в расчёте и в проекте."))
        self.visible.toggled.connect(lambda _: self.seen.emit())
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
        for widget in (self.pick, self.visible, self.swatch, self.name,
                       self.count, remove):
            layout.addWidget(widget)
        self.points = []
        self.rings = []  # контуры образцов - у окна «Распознавание»
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
        self._count()

    def set_rings(self, rings):
        self.rings = rings
        self._count()

    def samples(self):
        """Есть ли у класса образцы - точки или контуры."""
        return bool(self.points or self.rings)

    def enough(self):
        """Образцов хватает: три точки или контур."""
        return len(self.points) >= aef.MIN_POINTS or bool(self.rings)

    def _count(self):
        if self.rings:
            self.count.setText(tr("{points} т., {rings} о.",
                                  points=len(self.points),
                                  rings=len(self.rings)))
            self.count.setToolTip(tr("Точек и областей образцов класса."))
        else:
            self.count.setText(str(len(self.points)))
            self.count.setToolTip(tr("Контрольных точек класса."))


class ClassDialog(QDialog):
    """Окно «Классификация». Сигналы build, changed - точки, классы,
    цвета или участок, opacity. OK записывает классы в проект QGIS,
    «Отмена» убирает их (ui/results.py)."""

    build = pyqtSignal()
    changed = pyqtSignal()
    opacity = pyqtSignal(float)
    source_changed = pyqtSignal()
    seen = pyqtSignal()  # флажок «Видно» класса
    source_class = None  # SourceBox, у наследника свой список

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Классификация"))
        self.point = None
        settings = QgsSettings()
        self.source = (self.source_class or SourceBox)(self)
        self.source.setToolTip(tr(
            "Откуда берутся признаки клетки. Эмбеддинги AlphaEarth "
            "загружаются из сети. У растра проекта каждый канал - признак, "
            "каналы приводятся к одному разбросу, поэтому их единицы могут "
            "быть разными. Подложка глобуса - картинка текущей подложки "
            "под участком: снимок собран из разных съёмок, классы могут "
            "идти по их границам."))
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
        self.wanted_pixel = int(settings.value(SETTINGS + "pixel", AUTO))
        fill_pixels(self.level, True, self.wanted_pixel)
        self.level.setToolTip(tr(
            "Пиксель классификации. У AlphaEarth блок файла за год - "
            "40-50 МБ при любом пикселе, блок пикселя 10 м покрывает 10 км, "
            "80 м - 82 км, «Авто» берёт пиксель с наименьшей загрузкой, при "
            "котором на участке от 14 до 640 тысяч клеток. У растра проекта "
            "и подложки есть пиксели 1, 2 и 5 м, «Авто» - пиксель растра "
            "или верхнего уровня подложки, если на участке клеток не больше "
            "640 тысяч. Деление на объекты принимает до 4 млн клеток."))
        self.volume = QLabel(self)
        self.split = QCheckBox(tr("Делить на объекты"), self)
        self.split.setChecked(_flag(settings.value(SETTINGS + "split",
                                                   False)))
        self.split.setToolTip(tr(
            "Участок сначала делится на объекты, похожие по цвету "
            "и текстуре, класс получает объект целиком. Итог - "
            "многоугольники."))
        self.split_join = QCheckBox(
            tr("Сливать соседние объекты одного класса"), self)
        self.split_join.setChecked(_flag(settings.value(
            SETTINGS + "split_join", False)))
        self.split_join.setToolTip(tr(
            "Соседние объекты одного класса становятся одним "
            "многоугольником. Без флажка каждое поле или выдел остаётся "
            "отдельным объектом со своими значениями."))
        self.split_scale = QSpinBox(self)
        self.split_scale.setRange(1, 500)
        self.split_scale.setValue(int(settings.value(
            SETTINGS + "split_scale", segments.SCALE)))
        self.split_scale.setToolTip(tr(
            "Допустимая разнородность объекта. Чем больше, тем крупнее "
            "объекты и тем больше несхожего они объединяют. Масштаб "
            "отнесён к участку, поэтому смена пикселя размер объектов "
            "почти не меняет."))
        self.split_weight = QSpinBox(self)
        self.split_weight.setRange(0, 100)
        self.split_weight.setSuffix(" %")
        self.split_weight.setValue(int(settings.value(
            SETTINGS + "split_weight", 100 * segments.WEIGHT)))
        self.split_weight.setToolTip(tr(
            "Доля текстуры среди признаков, остальное - цвет. Текстура "
            "- разброс яркости вокруг клетки, она отделяет лес от луга "
            "того же цвета."))
        self.split_least = QSpinBox(self)
        self.split_least.setRange(1, 100000)
        self.split_least.setValue(int(settings.value(
            SETTINGS + "split_least", segments.LEAST)))
        self.split_least.setToolTip(tr(
            "Объект меньше этого количества клеток сливается с самым "
            "похожим соседом."))
        self.rows_box = QVBoxLayout()
        self.group = QButtonGroup(self)
        self.rows = []
        add = QPushButton(tr("Добавить класс"), self)
        add.clicked.connect(lambda: self.add_class())
        self.add_button = add
        self.from_trace = QPushButton(tr("Классы из трассировки"), self)
        self.from_trace.setToolTip(tr(
            "Классы с названиями и цветами из окна «Трассировка» после "
            "«Построить». Классы без точек заменяются, точки ставятся "
            "щелчками по глобусу."))
        self.from_trace.clicked.connect(self.take_traced)
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
        self.hint = hint
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Источник"), self.source)
        form.addRow(tr("Год"), self.year)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Пиксель"), self.level)
        form.addRow("", self.volume)
        form.addRow("", self.split)
        form.addRow(tr("Масштаб объектов"), self.split_scale)
        form.addRow(tr("Доля текстуры"), self.split_weight)
        form.addRow(tr("Наименьший объект, клеток"), self.split_least)
        form.addRow("", self.split_join)
        form.addRow(tr("Непрозрачность"), self.alpha)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Каждая клетка участка относится к классу ближайших "
            "контрольных точек по векторам AlphaEarth или каналам растра."))
        run.clicked.connect(self.build)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(QLabel(tr("Классы"), self))
        layout.addLayout(self.rows_box)
        adding = QHBoxLayout()
        adding.addWidget(add)
        adding.addWidget(self.from_trace)
        self.adding = adding
        layout.addLayout(adding)
        layout.addWidget(hint)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        add_preview(self, layout, buttons)
        fit_status(self, layout)
        for _ in range(2):
            self.add_class()
        self.rows[0].pick.setChecked(True)
        self.level.currentIndexChanged.connect(lambda _: self._pixel())
        self.year.currentIndexChanged.connect(lambda _: self._remember())
        self.alpha.valueChanged.connect(lambda _: self._remember())
        self.source.currentIndexChanged.connect(lambda _: self._source())
        self.split.toggled.connect(lambda _: self._split_changed())
        self.split_join.toggled.connect(lambda _: self._remember())
        for box in (self.split_scale, self.split_weight, self.split_least):
            box.valueChanged.connect(lambda _: self._remember())
        self._split_changed()
        self.set_ready(False)

    def raster_id(self):
        """Номер слоя растра в списке, пусто у AlphaEarth."""
        return self.source.currentData() or ""

    def raster(self):
        """Выбранный растр проекта, None - AlphaEarth или слоя уже нет."""
        return QgsProject.instance().mapLayer(self.raster_id())

    def _source(self):
        self.year.setEnabled(not self.raster_id())
        self.area.set_most(RASTER_SIDE if self.raster_id() else CLASS_SIDE)
        fill_pixels(self.level, bool(self.raster_id()), self.wanted_pixel)
        self.volume_changed()
        self._split_changed()
        self.source_changed.emit()

    def _pixel(self):
        """Пиксель выбран вручную: он вернётся и после смены источника."""
        self.wanted_pixel = self.level.currentData()
        self._remember()

    def _split_changed(self):
        on = self.split.isChecked()
        for box in (self.split_scale, self.split_weight, self.split_least,
                    self.split_join):
            box.setEnabled(on)
        self._remember()

    def split_params(self):
        """Масштаб, доля текстуры, наименьший объект и слияние соседей,
        None - деления на объекты нет."""
        if not self.split.isChecked():
            return None
        return (self.split_scale.value(),
                self.split_weight.value() / 100.0,
                self.split_least.value(), self.split_join.isChecked())

    def add_class(self, name=None):
        color = COLORS[len(self.rows) % len(COLORS)]
        row = ClassRow(color, name or tr("Класс {n}", n=len(self.rows) + 1),
                       self)
        row.removed.connect(self._remove)
        row.edited.connect(self.changed)
        row.seen.connect(self.seen)
        self.group.addButton(row.pick)
        self.rows.append(row)
        self.rows_box.addWidget(row)
        row.pick.setChecked(True)
        return row

    def take_traced(self, tool=None):
        """Классы трассировки вместо классов без точек: названия и цвета
        окна «Трассировка» (решение автора от 3 ноября 2026 года - таблица
        классов общая у окон). tool - другое окно трассировки, например
        «Выделение объектов»; сигнал clicked даёт сюда False."""
        tool = tool or getattr(self.parent(), "trace_tool", None)
        pairs = tool.class_pairs() if tool is not None else []
        if not pairs:
            self.status.setText(tr(
                "В окне «Трассировка» нет построенных классов."))
            return
        for row in [row for row in self.rows if not row.points]:
            self._remove(row)
        have = {row.name.text() for row in self.rows}
        for rgb, name in pairs:
            if name in have:
                continue
            row = self.add_class(name)
            row.color = QColor(*rgb)
            row._paint()
        if self.rows and self.active() is None:
            self.rows[0].pick.setChecked(True)
        self.changed.emit()
        self.status.setText(tr("Классов из трассировки: {n}.",
                               n=len(pairs)))

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
        settings.setValue(SETTINGS + "pixel", self.wanted_pixel)
        settings.setValue(SETTINGS + "opacity", self.alpha.value() / 100.0)
        settings.setValue(SETTINGS + "split", self.split.isChecked())
        settings.setValue(SETTINGS + "split_scale",
                          self.split_scale.value())
        settings.setValue(SETTINGS + "split_weight",
                          self.split_weight.value())
        settings.setValue(SETTINGS + "split_least",
                          self.split_least.value())
        settings.setValue(SETTINGS + "split_join",
                          self.split_join.isChecked())
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
        source = self.raster_id()
        if source:
            layer = None if source == BASEMAP else self.raster()
            if source != BASEMAP and layer is None:
                self.volume.setText("")
                return
            head = self.area.window._earth_source().name \
                if layer is None else tr("Каналов растра: {n}",
                                         n=layer.bandCount())
            self.volume.setText(head + ". " + pixel_text(
                self.area.window, source, layer, self.level.currentData(),
                self.area.box(), self.area.size()))
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


class ClassTool(SiteTool, QObject):
    """Классификация участка у окна глобуса. Наследник (ui/recognize.py)
    задаёт dialog_class, shapes_attr, tool_title и more_bands."""

    dialog_class = None  # ClassDialog, ставится после класса окна
    shapes_attr = "class_shapes"  # поле окна глобуса с точками классов
    vectorize = False  # многоугольники классов - у «Распознавания»

    def tool_title(self):
        return tr("Классификация")

    @property
    def legend_title(self):
        return self.tool_title()

    def more_bands(self, box, side):
        """Каналы второго снимка на сетке первого, как у трассировки:
        (ключ, add(index, found)), None - нет, False - отказ, причина
        в строке итога. Главный поток, add - в рабочем."""
        return None

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.result = None
        self.grid = None  # (ключ участка, данные vectors)
        self.pieces = None  # (ключ участка и настроек, объекты)
        self.job = None
        self.progress = [0, 0]  # блоков загружено, всего
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(self._poll)
        self.shapes = []
        self.settings = []  # настройки последнего «Построить» для слоя
        self.session = Session(window, self.tool_title())

    def open_here(self, lat, lon):
        """Окно «Классификация» для точки - пункт подменю «Анализ
        участка» меню на глобусе."""
        dialog = self.dialog
        if dialog is None:
            dialog = self.dialog_class(self.window)
            dialog.build.connect(self.build)
            dialog.changed.connect(self._update_shapes)
            dialog.opacity.connect(self.set_opacity)
            dialog.seen.connect(lambda: self.show(keep=True))
            dialog.finished.connect(self._closed)
            dialog.source_changed.connect(self._want_index)
            dialog.area.point_under = self.point_under
            self.dialog = dialog
        dialog.source.refill()
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        self._want_index()
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        self._update_shapes()
        return dialog

    def _want_index(self):
        """Указатель зоны - только для оценки загрузки AlphaEarth, у растра
        проекта сеть не нужна."""
        dialog = self.dialog
        if dialog.raster_id() or dialog.point is None or self.job is not None:
            return
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        _run_job(self, lambda: index_of(zone),
                 lambda _: dialog.volume_changed())

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
        setattr(self.window, self.shapes_attr, shapes)
        self.window._refresh_shapes()
        self.window.handles.sync()

    # --- расчёт ---------------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or dialog.point is None:
            return
        layer = dialog.raster()
        tiled = dialog.raster_id() == BASEMAP
        if dialog.raster_id() and layer is None and not tiled:
            dialog.status.setText(tr("Растра больше нет в проекте."))
            return
        if not dialog.raster_id() and not zstd_ready():
            dialog.status.setText(tr(
                "Нет библиотеки zstd, файлы AlphaEarth не прочитать."))
            return
        rows = self.used_rows()
        if rows is None:
            dialog.status.setText(self.too_few_text())
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
        rings = [(n, r) for n, row in enumerate(rows) for r in row.rings]
        colors = [row.rgb() for row in rows]
        names = [row.name.text() for row in rows]
        self.settings = class_settings(len(rows), len(points),
                                       dialog.split_params(), len(rings))
        if dialog.raster_id():
            self._build_raster(layer, ring, box, side, level, zone, points,
                               colors, names, rings)
            return
        key = (box, year, level)
        cached = self.grid if self.grid and self.grid[0] == key else None
        params = dialog.split_params()
        split_key = self._split_key(key, ring, params)
        pieces = self._pieces(split_key)
        progress = self.progress = [0, 0]
        rules = self.rules_job()

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
            if params is not None:
                values = aef.LUT[grid.astype(np.int16) + 128]
                inside = aef.ring_mask(index, x0, y0, step, grid.shape[1:],
                                       ring)
                share = rasterclass.covered(values, inside)
                if share <= 0.0:
                    return None
                return self._objects(found, values, inside, share, index,
                                     points, params, pieces)
            if rules is not None:
                values = aef.LUT[grid.astype(np.int16) + 128]
                inside = aef.ring_mask(index, x0, y0, step, grid.shape[1:],
                                       ring)
                samples, labels, outside = ring_samples(
                    index, found, values, points, rings)
                classes = rules(values, inside, samples, labels,
                                (index, x0, y0, step))
                if classes is None or not (classes >= 0).any():
                    return {"problem": "flat", "found": found}
                return {"index": index, "found": found, "outside": outside,
                        "classes": classes}
            samples, labels, outside = ring_samples(index, found, grid,
                                                    points, rings)
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
        _run_job(self, self._with_shapes(work), lambda out: self._built(
            out, key, box, year, colors, names, None, split_key),
            tr("Классификация"))

    @staticmethod
    def _split_key(key, ring, params):
        """Ключ готовых объектов: участок и настройки деления."""
        return (key, tuple(ring), params[:3] if params else None)

    def _pieces(self, split_key):
        return self.pieces[1] if self.pieces \
            and self.pieces[0] == split_key else None

    def _objects(self, found, grid, inside, share, index, points, params,
                 pieces, drawing=False):
        """Объекты участка и их классы: контрольная точка берёт
        признаки своего объекта. grid - float32 с NaN без данных,
        drawing - у снимка к признакам добавляется рисунок объекта
        (segments.pattern), у эмбеддингов его нет. Рабочий поток."""
        x0, y0, step, _ = found
        if segments.too_big(*grid.shape[1:]):
            return {"problem": "pieces", "found": found}
        parts = pieces
        if parts is None:
            scale, weight, least = params[:3]
            cells = int((rasterclass.usable(grid) & inside).sum())
            parts = segments.segment(
                grid, inside, segments.site_scale(scale, cells), weight,
                least, progress=lambda _: stop_point(self))
        stop_point(self)
        if int(parts.max()) < 1:
            return {"problem": "whole", "found": found, "parts": parts}
        table = segments.table(grid, parts)
        signs = np.concatenate((table, segments.pattern(grid, parts))) \
            if drawing else table
        samples, labels, outside = [], [], 0
        for label, (plat, plon) in points:
            r, c = aef.pixel_of(index, x0, y0, step, plat, plon)
            if 0 <= r < grid.shape[1] and 0 <= c < grid.shape[2] \
                    and parts[r, c] >= 0:
                samples.append(signs[:, 0, parts[r, c]])
                labels.append(label)
            else:
                outside += 1
        if len(set(labels)) < aef.MIN_CLASSES:
            return {"problem": "points", "found": found, "parts": parts}
        kinds = rasterclass.classify(
            signs, np.stack(samples, axis=1), labels,
            progress=lambda done, total: stop_point(self))[0][0]
        if not (kinds >= 0).any():
            return {"problem": "flat", "found": found, "parts": parts}
        classes = np.where(parts >= 0, kinds[np.maximum(parts, 0)], -1)
        shown = parts
        if params[3]:
            shown, kinds = segments.dissolve(parts, kinds)
            table = segments.table(grid, shown)
        return {"index": index, "found": found, "outside": outside,
                "classes": classes, "covered": share, "parts": parts,
                "shown": shown, "kinds": kinds, "table": table}

    def _with_shapes(self, work):
        """work рабочего потока с многоугольниками классов: у окна
        «Распознавание» (vectorize) классы клеток без деления на объекты
        ещё и сглаживаются в многоугольники (tracing.class_shapes)."""
        if not self.vectorize:
            return work
        least = self.dialog.least_cells()
        corner = self.dialog.corner_value()

        def run():
            out = work()
            if isinstance(out, dict) and out.get("classes") is not None \
                    and out.get("parts") is None \
                    and not out.get("problem"):
                stop_point(self)
                out["shapes"] = tracing.class_shapes(
                    out["classes"], least, corner,
                    progress=lambda: stop_point(self))
            return out

        return run

    def too_few_text(self):
        return tr("Нужно хотя бы два класса по три точки.")

    def used_rows(self):
        """Классы расчёта - строки с образцами, None - образцов мало."""
        rows = [row for row in self.dialog.rows if row.samples()]
        if len(rows) < aef.MIN_CLASSES or not all(
                row.enough() for row in rows):
            return None
        return rows

    def rules_job(self):
        """Классы правилами вместо образцов: функция рабочего потока
        (каналы, участок, образцы, номера классов образцов) -> классы
        клеток. Без правил - None, классы по образцам. Пятый аргумент -
        место сетки (указатель зоны, x0, y0, шаг)."""
        return None

    def _build_raster(self, layer, ring, box, side, level, zone, points,
                      colors, names, rings=()):
        """Классы по каналам растра проекта или подложки. Слой QGIS
        остаётся в главном потоке, рабочий поток читает файл через GDAL.
        rings - контуры образцов [(класс, вершины)], у каждого - не больше
        RING_CELLS клеток поровну по контуру."""
        dialog = self.dialog
        reader = raster_reader(self, layer, box, side, level)
        if reader is None:
            return
        read, key, name, credit = reader
        more = self.more_bands(box, side)
        if more is False:
            return
        add = None
        if more:
            key, add = key + (more[0],), more[1]
        cached = self.grid if self.grid and self.grid[0] == key else None
        index = aef.ZoneIndex(zone, [])
        params = dialog.split_params()
        split_key = self._split_key(key, ring, params)
        pieces = self._pieces(split_key)
        rules = self.rules_job()

        def count(done, total):
            stop_point(self)

        def work():
            found = cached[1] if cached else read(index)
            if isinstance(found, str):
                return {"problem": found}
            if add is not None and not cached:
                found = add(index, found)
                if isinstance(found, str):
                    return {"problem": found}
            stop_point(self)
            x0, y0, step, grid = found
            inside = aef.ring_mask(index, x0, y0, step, grid.shape[1:], ring)
            share = rasterclass.covered(grid, inside)
            if share <= 0.0:
                return {"problem": "outside"}
            if params is not None:
                return self._objects(found, grid, inside, share, index,
                                     points, params, pieces, drawing=True)
            samples, labels, outside = ring_samples(index, found, grid,
                                                    points, rings)
            if rules is not None:
                classes = rules(grid, inside, samples, labels,
                                (index, x0, y0, step))
                if classes is None or not (classes >= 0).any():
                    return {"problem": "flat", "found": found}
                return {"index": index, "found": found, "outside": outside,
                        "classes": classes, "covered": share}
            if len(set(labels)) < aef.MIN_CLASSES:
                return {"problem": "points", "found": found}
            classes, _ = rasterclass.classify(
                grid, np.stack(samples, axis=1), labels, inside,
                progress=count)
            if not (classes >= 0).any():
                return {"problem": "flat", "found": found}
            return {"index": index, "found": found, "outside": outside,
                    "classes": classes, "covered": share}

        dialog.status.setText(tr("Загружаются тайлы подложки…")
                              if dialog.raster_id() == BASEMAP
                              else tr("Читается растр участка…"))
        _run_job(self, self._with_shapes(work), lambda out: self._built(
            out, key, box, None, colors, names, name, split_key, credit),
            self.tool_title())

    def _built(self, out, key, box, year, colors, names, raster=None,
               split_key=None, credit=None):
        dialog = self.dialog
        if out is None:
            dialog.status.setText(tr("Для участка нет данных."))
            return
        if out.get("found") is not None:
            self.grid = (key, out["found"])
        if out.get("parts") is not None:
            self.pieces = (split_key, out["parts"])
        if out.get("problem"):
            dialog.status.setText(problem_text(out["problem"]))
            return
        if out["classes"] is None:
            dialog.status.setText(tr("Все точки вне участка."))
            return
        x0, y0, step, _ = out["found"]
        classes = out["classes"]
        self.result = {"index": out["index"], "x0": x0, "y0": y0,
                       "step": step, "classes": classes, "colors": colors,
                       "names": names, "box": box, "year": year,
                       "raster": raster, "credit": credit,
                       "label": raster or str(year),
                       "ring": list(self.dialog.area.ring),
                       "settings": self.settings + [tr(
                           "пиксель {pixel} м",
                           pixel="{:.3g}".format(step))]}
        if out.get("parts") is not None:
            self.result.update(parts=out["shown"], kinds=out["kinds"],
                               table=out["table"])
        if out.get("shapes") is not None:
            self.result.update(shapes=out["shapes"]["shapes"],
                               shape_kinds=out["shapes"]["kinds"],
                               shape_parts=out["shapes"]["parts"])
        counts = [int((classes == n).sum()) for n in range(len(colors))]
        total = max(sum(counts), 1)
        parts = ", ".join("{} {:.0f}%".format(name, 100.0 * c / total)
                          for name, c in zip(names, counts))
        tiled = key[0] == BASEMAP
        if raster is None:
            text = tr("Классы {year} года: {parts}.", year=year, parts=parts)
        else:
            pixel = "{:.3g}".format(step)
            text = tr("Классы подложки «{name}»: {parts}. Пиксель {pixel} м.",
                      name=raster, parts=parts, pixel=pixel) if tiled else \
                tr("Классы растра «{name}»: {parts}. Пиксель {pixel} м.",
                   name=raster, parts=parts, pixel=pixel)
            if out["covered"] < COVERED:
                share = "{:.0f}".format(100.0 * out["covered"])
                text += " " + (
                    tr("Подложка покрывает {share} % участка.", share=share)
                    if tiled else
                    tr("Растр покрывает {share} % участка.", share=share))
        if out.get("parts") is not None:
            sizes = segments.areas(out["shown"])
            mean = float(sizes.mean()) * step * step / 1e4
            text += " " + tr(
                "Объектов {n}, средний {area} га.", n=len(sizes),
                area="{:.0f}".format(mean) if mean >= 10.0
                else "{:.2g}".format(mean))
        if out["outside"] and tiled:
            text += " " + tr("Точек без данных подложки: {n}.",
                             n=out["outside"])
        elif out["outside"] and raster is not None:
            text += " " + tr("Точек без данных растра: {n}.",
                             n=out["outside"])
        elif out["outside"]:
            text += " " + tr("Точек вне участка: {n}.", n=out["outside"])
        dialog.status.setText(text + " " + built_text())
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

    def show(self, keep=False):
        """keep - перерисовка классов поверх прежних картинок, флажок
        «Видно» строки класса."""
        result = self.result
        if not keep:
            self._drop_tiles()
        if result is None:
            return
        if self.dialog is not None:
            result["hidden"] = {row.rgb() for row in self.dialog.rows
                                if not row.visible.isChecked()}
        self.put_tiles(ClassTiles(result, parent=self),
                       result_level(result),
                       self.dialog.alpha.value() / 100.0 if self.dialog
                       else OPACITY, keep=keep)

    def forget(self):
        self.result = None
        if self.dialog is not None:
            self.dialog.set_ready(False)

    # --- выгрузка -------------------------------------------------------

    def export(self, path=None):
        """Классы растром в проект QGIS, отмечены на глобусе. path -
        файл, без него - новый файл результата (ui/results.py)."""
        result = self.result
        if result is None:
            return None
        tag = result["year"] or "raster"
        if result.get("parts") is not None:
            return self._export_objects(path, tag)
        if path is None:
            path = result_path("classes_{}".format(tag))
        if not write_classes(path, result):
            self.dialog.status.setText(tr("Растр не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        layer = add_classes(path, titled(
            tr("Классификация {year}", year=result["label"]),
            result["settings"]), result, group)
        if layer is not None:
            layer.setOpacity(self.dialog.alpha.value() / 100.0)
            set_abstract(layer, class_abstract(result))
        show_layer(self.window, layer)
        self._export_points(tag, result["label"], group)
        self.dialog.status.setText(tr("Растр классов в проекте."))
        return path

    def _export_objects(self, path, tag):
        """Объекты многоугольниками GeoPackage в подгруппу расчёта:
        цвета по классу, в полях средние и разбросы каналов."""
        result = self.result
        path = path or result_path("objects_{}".format(tag), ".gpkg")
        if not write_objects(path, result):
            self.dialog.status.setText(tr("Слой не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        layer = add_vector(
            self.window, path, "objects",
            titled(tr("Объекты {year}", year=result["label"]),
                   result["settings"]), group,
            result["colors"][0], classes=("class", [
                (n + 1, tuple(rgb), name) for n, (rgb, name) in enumerate(
                    zip(result["colors"], result["names"]))]))
        if layer is not None:
            layer.setOpacity(self.dialog.alpha.value() / 100.0)
            set_abstract(layer, class_abstract(result))
        set_credit(layer, result)
        self._export_points(tag, result["label"], group)
        self.dialog.status.setText(tr("Объекты в проекте."))
        return path

    def _export_points(self, tag, label, group):
        """Контрольные точки слоем GeoPackage в подгруппу расчёта: поля
        class (номер с 1) и name, цвет точки - цвет класса. tag - часть
        имени файла, label - подпись слоя."""
        rows = [row for row in self.dialog.rows if row.points]
        items = [([point], {"class": n, "name": row.name.text()})
                 for n, row in enumerate(self.dialog.rows, 1)
                 for point in row.points]
        if not items:
            return None
        path = result_path("class_points_{}".format(tag), ".gpkg")
        if not write_vector(path, "points", "point", items,
                            [("class", "int"), ("name", "str")]):
            return None
        return add_vector(
            self.window, path, "points",
            tr("Контрольные точки {year}", year=label), group,
            rows[0].rgb(), classes=("class", [
                (n, row.rgb(), row.name.text())
                for n, row in enumerate(self.dialog.rows, 1)
                if row.points]))

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


ClassTool.dialog_class = ClassDialog


def ring_samples(index, found, grid, points, rings):
    """Образцы классов по сетке grid: клетки контрольных точек и до
    RING_CELLS клеток каждого контура поровну по клеткам внутри. Итог -
    (векторы образцов, номера классов, образцов вне данных). Рабочий
    поток."""
    x0, y0, step = found[:3]
    samples, labels, outside = [], [], 0
    fine = np.issubdtype(grid.dtype, np.floating)
    for label, (plat, plon) in points:
        r, c = aef.pixel_of(index, x0, y0, step, plat, plon)
        if 0 <= r < grid.shape[1] and 0 <= c < grid.shape[2] \
                and (not fine or np.isfinite(grid[:, r, c]).all()):
            samples.append(grid[:, r, c])
            labels.append(label)
        else:
            outside += 1
    if rings:
        good = rasterclass.usable(grid) if fine \
            else np.ones(grid.shape[1:], dtype=bool)
        flat = grid.reshape(grid.shape[0], -1)
        for label, sample in rings:
            cells = np.flatnonzero(aef.ring_mask(
                index, x0, y0, step, grid.shape[1:], sample) & good)
            if not len(cells):
                outside += 1
                continue
            take = cells[np.linspace(
                0, len(cells) - 1, min(RING_CELLS, len(cells)))
                .astype(np.int64)]
            for cell in take:
                samples.append(flat[:, cell])
                labels.append(label)
    return samples, labels, outside


def class_settings(classes, points, params, areas=0):
    """Настройки классификации строками для названия слоя: классов,
    точек, областей образцов, деление на объекты (params - split_params
    окна)."""
    out = [tr("классов {n}", n=classes)]
    if points or not areas:
        out.append(tr("точек {n}", n=points))
    if areas:
        out.append(tr("областей {n}", n=areas))
    if params is not None:
        scale, weight, least, join = params
        out.append(tr("объекты: масштаб {scale}, текстура {weight} %, от "
                      "{least} клеток", scale=scale,
                      weight=int(round(100 * weight)), least=least))
        if join:
            out.append(tr("соседи слиты"))
    return out


def class_abstract(result):
    """Описание слоя классификации: источник, настройки, классы с долей."""
    return [tr("Источник - {source}.", source=result["label"]),
            tr("Настройки - {settings}.",
               settings=", ".join(result["settings"])),
            tr("Классы - {rows}.", rows=", ".join(
                text for _, text in class_rows(
                    result["classes"], result["colors"], result["names"])))]


def _flag(value):
    """Логическая настройка: в QGIS 3 она приходит строкой."""
    return value in (True, "true", 1, "1")


def project_rasters():
    """Растры проекта, которые GDAL читает из файла, в порядке имён."""
    layers = QgsProject.instance().mapLayers().values()
    return sorted((layer for layer in layers
                   if isinstance(layer, QgsRasterLayer)
                   and layer.providerType() == "gdal"
                   and layer.isValid()),
                  key=lambda layer: layer.name().lower())


def problem_text(code):
    """Текст строки итога для кода отказа расчёта по растру."""
    return {"unreadable": tr("Растр не прочитан."),
            "tiles": tr("Тайлы подложки не получены."),
            "big": tr("Сетка участка слишком велика, возьмите пиксель "
                      "крупнее или «Авто»."),
            "whole": tr("Весь участок вышел одним объектом, уменьшите "
                        "масштаб объектов."),
            "pieces": tr("Для объектов сетка участка слишком велика, "
                         "возьмите пиксель крупнее или «Авто»."),
            "outside": tr("Участок вне охвата растра."),
            "second": tr("Второй снимок не прочитан или не накрывает "
                         "участок."),
            "points": tr("Нужно хотя бы два класса с точками на клетках "
                         "с данными."),
            "flat": tr("Каналы растра на участке не меняются, классы "
                       "различить нельзя.")}[code]


def _warp_target(data, wkt, index):
    """Растр в системе UTM зоны: система файла берётся у слоя QGIS."""
    from osgeo import gdal, osr
    srs = osr.SpatialReference()
    srs.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    utm = srs.ExportToWkt()
    return utm, gdal.AutoCreateWarpedVRT(data, wkt, utm)


def _warp_grid(data, wkt, utm, frame, pixel):
    """Каналы набора GDAL data на сетке frame (x0, y0, столбцы, строки):
    float32 (каналы, строки с севера, столбцы), NaN без данных, или None.
    Значения «нет данных» каналов учитываются порознь, канал прозрачности
    признаком не считается: прозрачная клетка остаётся без данных."""
    from osgeo import gdal
    x0, y0, cols, rows = frame
    out = gdal.Warp(
        "", data, format="MEM", srcSRS=wkt, dstSRS=utm,
        outputBounds=(x0, y0 - rows * pixel, x0 + cols * pixel, y0),
        width=cols, height=rows, resampleAlg="bilinear",
        outputType=gdal.GDT_Float32, dstNodata="nan",
        warpOptions=["UNIFIED_SRC_NODATA=NO"])
    if out is None:
        return None
    bands, clear = [], None
    for number in range(1, out.RasterCount + 1):
        band = out.GetRasterBand(number)
        values = band.ReadAsArray().astype(np.float32)
        if band.GetColorInterpretation() == gdal.GCI_AlphaBand:
            clear = ~(values > 0.0)
        else:
            bands.append(values)
    out = None
    if not bands:
        return None
    grid = np.stack(bands)
    if clear is not None:
        grid[:, clear] = np.nan
    return grid


def read_raster(path, wkt, index, box, side, pixel):
    """Каналы растра на сетке участка box в метрах UTM. Рабочий поток.
    path - файл, wkt - система слоя, pixel - шаг метров, None - «Авто».
    Итог - (x0, y0 - левый верхний угол, шаг м, сетка _warp_grid) или код
    отказа (problem_text)."""
    from osgeo import gdal
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            data = gdal.Open(path)
            if data is None:
                return "unreadable"
            utm, warped = _warp_target(data, wkt, index)
            if pixel is None:
                native = PIXEL_DEFAULT if warped is None \
                    else abs(warped.GetGeoTransform()[1])
                pixel = rasterclass.auto_pixel(native, side)
            warped = None
            frame = aef.grid_frame(index, box, pixel)
            if rasterclass.too_big(frame[3], frame[2], data.RasterCount):
                return "big"
            grid = _warp_grid(data, wkt, utm, frame, pixel)
        except RuntimeError:
            return "unreadable"
    finally:
        gdal.PopErrorHandler()
    if grid is None:
        return "unreadable"
    return frame[0], frame[1], float(pixel), grid


def read_basemap(source, index, box, side, pixel, tick):
    """Подложка source на сетке участка, как read_raster. Уровень тайлов -
    по шагу сетки, «Авто» - пиксель верхнего уровня подложки, если клеток
    на участке не больше 640 тысяч. tick зовётся перед пакетом запросов."""
    from osgeo import gdal
    lat = (box[1] + box[3]) / 2.0
    if pixel is None:
        pixel = rasterclass.auto_pixel(
            tilemosaic.tile_pixel(lat, source.max_level), side)
    frame = aef.grid_frame(index, box, pixel)
    if rasterclass.too_big(frame[3], frame[2], 3):
        return "big"
    z = tilemosaic.level_for(lat, pixel, source.max_level)
    tiles = tilemosaic.span(box, z)
    if tilemosaic.tile_count(tiles) > tilemosaic.MAX_TILES:
        return "big"
    try:
        made = tile_dataset(source, z, tiles, tick)
    except OSError:
        return "tiles"
    if made is None:
        return "tiles"
    data, wkt = made
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            utm = _warp_target(data, wkt, index)[0]
            grid = _warp_grid(data, wkt, utm, frame, pixel)
        except RuntimeError:
            return "unreadable"
    finally:
        gdal.PopErrorHandler()
    if grid is None:
        return "unreadable"
    return frame[0], frame[1], float(pixel), grid


def raster_reader(tool, layer, box, side, level):
    """Чтение источника окна, кроме AlphaEarth: (read(index), ключ сетки,
    название, подпись прав) или None - отказ, причина в строке итога.
    Главный поток, read идёт в рабочем."""
    dialog = tool.dialog
    pixel = None if level == AUTO else float(PIXELS[level])
    warm()
    if dialog.raster_id() == BASEMAP:
        source = tool.window._earth_source()
        if not tool.window.accept_basemap_use(source):
            dialog.status.setText(tr("Расчёт по подложке не запущен."))
            return None
        ranges.bridge()

        def read(index):
            return read_basemap(source, index, box, side, pixel,
                                lambda: stop_point(tool))

        return (read, (BASEMAP, source.url, box, pixel), source.name,
                source.attribution[0])
    crs = layer.crs()
    if not crs.isValid():
        dialog.status.setText(tr("У растра не задана система координат."))
        return None
    path, wkt = layer.source(), crs.toWkt()

    def read(index):
        return read_raster(path, wkt, index, box, side, pixel)

    return read, (layer.id(), path, box, pixel), layer.name(), None


def set_credit(layer, result):
    """Подпись источника в правах слоя результата."""
    credit = aef.CREDIT if result["raster"] is None \
        else result.get("credit")
    if layer is None or not credit:
        return
    meta = layer.metadata()
    meta.setRights([credit])
    layer.setMetadata(meta)


def write_classes(path, result):
    """Классы GeoTIFF Byte в UTM: номер класса + 1, 0 - нет данных."""
    from osgeo import gdal, osr
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


def write_objects(path, result):
    """Объекты слоем objects файла GeoPackage в UTM: поля object, class
    (номер с 1), name, area_ha, у растра проекта mean_N и sd_N каналов,
    у похожих областей similar в процентах. Объект связный, поэтому один
    объект - один многоугольник."""
    from osgeo import gdal, ogr, osr
    warm()
    index = result["index"]
    srs = osr.SpatialReference()
    srs.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    parts = result["parts"]
    rows, cols = parts.shape
    step = result["step"]
    grid = gdal.GetDriverByName("MEM").Create("", cols, rows, 1,
                                              gdal.GDT_Int32)
    grid.SetGeoTransform((result["x0"], step, 0.0, result["y0"], 0.0,
                          -step))
    grid.SetProjection(srs.ExportToWkt())
    band = grid.GetRasterBand(1)
    band.SetNoDataValue(-1)
    band.WriteArray(parts)
    data = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    if data is None:
        return False
    layer = data.CreateLayer("objects", srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("object", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("class", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("name", ogr.OFTString))
    layer.CreateField(ogr.FieldDefn("area_ha", ogr.OFTReal))
    alike = result.get("similar")
    if alike is not None:
        layer.CreateField(ogr.FieldDefn("similar", ogr.OFTReal))
    table = result["table"][:, 0]
    bands = 0 if result["raster"] is None else table.shape[0] // 2
    half = table.shape[0] // 2
    for number in range(1, bands + 1):
        layer.CreateField(ogr.FieldDefn("mean_{}".format(number),
                                        ogr.OFTReal))
        layer.CreateField(ogr.FieldDefn("sd_{}".format(number),
                                        ogr.OFTReal))
    if gdal.Polygonize(band, band.GetMaskBand(), layer, 0) != 0:
        return False
    kinds = result["kinds"]
    sizes = segments.areas(parts)
    layer.StartTransaction()
    for feature in list(layer):
        number = feature.GetField("object")
        kind = int(kinds[number])
        feature.SetField("class", kind + 1)
        if kind >= 0:
            feature.SetField("name", result["names"][kind])
        feature.SetField("area_ha", float(sizes[number]) * step * step
                         / 1e4)
        if alike is not None:
            feature.SetField("similar", round(100.0 * float(alike[number]),
                                              1))
        for band_n in range(bands):
            feature.SetField("mean_{}".format(band_n + 1),
                             float(table[band_n, number]))
            feature.SetField("sd_{}".format(band_n + 1),
                             float(table[band_n + half, number]))
        layer.SetFeature(feature)
    layer.CommitTransaction()
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
    set_credit(layer, result)
    return _to_group(layer, group)
