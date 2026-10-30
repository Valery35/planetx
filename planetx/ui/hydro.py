# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вода по рельефу: окна «Затопление» и «Сток воды».

Расчёт - core/hydro.py. Участок - многоугольник (ui/area.py), сетка -
его рамка. Высоты - тайлы высот вида под рамкой (их просит вид, как
у видимости), окно ждёт их не дольше WAIT секунд, потом снимает высоты
узлов из хранилища вида - с моделью 30 м и своим рельефом, если они
включены. Вне многоугольника высот нет: вода уходит туда, как за край
сетки, затопление туда не идёт.

Затопление - поверхность воды на уровне сеткой «flood» воды водоёмов
вида (GlobeView.lake_water), уровень меняется без пересчёта.
Линии стока, водосборы, речная сеть и бассейны ложатся слоями
GeoPackage в проект QGIS в подгруппу расчёта (ui/results.py) и сразу
отмечены на глобусе. Уровень моря по всему
глобусу - проход воды тайлов на высоте GlobeView.sea_level.
"""
import math
import os
import time

import numpy as np
from qgis.core import (QgsLineSymbol, QgsProject, QgsProperty,
                       QgsSingleSymbolRenderer, QgsVectorLayer)
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout,
                                 QLabel,
                                 QPushButton, QSlider, QSpinBox,
                                 QVBoxLayout)

from ..core import bathymetry, ellipsoid, hydro, subsurface, viewshed
from ..i18n import tr
from ..net.overlay import STROKE_WIDTH
from ..qt_compat import enum
from .export import _property, _to_group, add_raster
from .area import Area, FixedArea
from .results import (Session, accepted, add_vector, built_text,
                      keep_buttons, result_path, show_layer, stats_text,
                      write_vector)
from .viewshed import fit_status

WAIT = 30.0  # с ожидания тайлов высот, дальше - по тем, что есть
POLL = 300  # мс между проверками пришедших тайлов
TILE = 256
# Подъём воды ползунком над высотой точки и подъём по умолчанию, м -
# выбор помощника, утверждает автор.
RISE = 50.0
DEFAULT_RISE = 2.0
SLIDER_STEPS = 500
FLOOD_KEY = "flood"
LINE_COLOR = (30, 110, 255, 255)
BASIN_COLOR = (20, 90, 220, 255)
BASIN_FILL = (60, 140, 255, 60)
DEPTH_COLORS = ((200, 230, 255), (0, 40, 140))
# Уровень моря окна «Уровень моря», м: от последнего ледникового
# максимума (около -120 м) до таяния всех ледников (около +70 м)
# с запасом - выбор помощника, утверждает автор.
# Водосбор метки у края участка считается на участке в GROW раз шире,
# пока полусторона не дойдёт до SHAPE_MOST метров. Выбор помощника,
# утверждает автор.
GROW = 2.5
SHAPE_MOST = 50000.0
SEA_LOW = -130
SEA_HIGH = 100
RIVER_COLOR = "30,110,255"
# Выполаживание по умолчанию: уклон 2° на 50 м, как в инструменте 2.23
# Isoliner. Линий от метки - не больше LINES_MOST самых длинных. Выбор
# помощника, утверждает автор.
FLAT_SLOPE = 2.0
FLAT_LENGTH = 50.0
LINES_MOST = 300
# Стороны участков по умолчанию и наибольший участок, км.
FLOOD_SIDE = 10.0
FLOW_SIDE = 20.0
MOST = 100.0


def number(value, digits=3):
    """Число для строки итога: digits значащих цифр, без степени."""
    if value is None or not math.isfinite(value):
        return "-"
    if value == 0.0:
        return "0"
    places = max(0, digits - 1 - int(math.floor(math.log10(abs(value)))))
    return "{:.{}f}".format(value, places)


def _spin(parent, low, high, value, suffix, decimals=1):
    box = QDoubleSpinBox(parent)
    box.setRange(low, high)
    box.setDecimals(decimals)
    box.setValue(value)
    box.setSuffix(suffix)
    return box


class FloodDialog(QDialog):
    """Окно «Затопление». Сигналы build, level - уровень воды в метрах.
    OK записывает затопление в проект QGIS, «Отмена» убирает воду окна
    (ui/results.py)."""

    build = pyqtSignal()
    level = pyqtSignal(float)

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Затопление"))
        self.base = None
        self.point = None
        self.place = QLabel(self)
        self.ground = QLabel("-", self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, FLOOD_SIDE, MOST,
                         "PlanetX/flood/side")
        self.water = _spin(self, -11000.0, 9000.0, 0.0, tr(" м"))
        self.water.setSingleStep(0.5)
        self.water.setKeyboardTracking(False)
        self.water.setEnabled(False)
        self.water.setToolTip(tr(
            "Отметка поверхности воды над уровнем моря. Вода заливает "
            "всё ниже отметки внутри участка, куда она доходит от "
            "точки. Котловины за более высоким гребнем остаются "
            "сухими."))
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setEnabled(False)
        self.slider.setToolTip(tr(
            "Подъём воды над высотой точки, до {rise} м.",
            rise=number(RISE)))
        self.water.valueChanged.connect(self._spun)
        self.slider.valueChanged.connect(self._slid)
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Высота точки"), self.ground)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Уровень воды"), self.water)
        form.addRow(tr("Подъём"), self.slider)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.clicked.connect(self.build)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def ready(self, base, level):
        """Сетка построена: высота точки base, уровень level."""
        self.base = base
        self.ground.setText(tr("{h} м", h=number(base, 4)))
        for widget in (self.water, self.slider, self.to_project):
            widget.setEnabled(True)
        self.water.blockSignals(True)
        self.water.setValue(level)
        self.water.blockSignals(False)
        self._sync_slider(level)

    def reset(self):
        self.base = None
        self.ground.setText("-")
        for widget in (self.water, self.slider, self.to_project):
            widget.setEnabled(False)

    def _sync_slider(self, level):
        self.slider.blockSignals(True)
        share = (level - self.base) / RISE if self.base is not None else 0
        self.slider.setValue(int(round(min(max(share, 0.0), 1.0)
                                       * SLIDER_STEPS)))
        self.slider.blockSignals(False)

    def _spun(self, value):
        if self.base is None:
            return
        self._sync_slider(value)
        self.level.emit(value)

    def _slid(self, steps):
        if self.base is None:
            return
        value = self.base + RISE * steps / float(SLIDER_STEPS)
        self.water.blockSignals(True)
        self.water.setValue(value)
        self.water.blockSignals(False)
        self.level.emit(self.water.value())


class FlowDialog(QDialog):
    """Окно «Сток воды». Сигналы line, basin, rivers и basins."""

    line = pyqtSignal()
    basin = pyqtSignal()
    rivers = pyqtSignal()
    basins = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Сток воды"))
        self.point = None
        self.place = QLabel(self)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, FLOW_SIDE, MOST, "PlanetX/flow/side")
        self.area.side.setToolTip(self.area.side.toolTip() + " " + tr(
            "Линия стока кончается у края участка, водосбор больше "
            "участка учитывается не целиком."))
        self.net = _spin(self, 0.1, 1000.0, hydro.NET_AREA / 1e6,
                         tr(" км²"), decimals=1)
        self.net.setToolTip(tr(
            "Речная сеть - водотоки с водосбором не меньше этой площади. "
            "Меньше - сеть гуще, с ручьями и оврагами."))
        self.order = QSpinBox(self)
        self.order.setRange(1, 10)
        self.order.setValue(1)
        self.order.setToolTip(tr(
            "Наименьший порядок водотока по Стралеру в речной сети. "
            "Исток - порядок 1, после слияния двух водотоков одного "
            "порядка - на единицу больше. Больше - в проект идут только "
            "крупные реки, порядки считаются по всей сети."))
        self.snap = _spin(self, 0.0, 2000.0, hydro.SNAP_METRES, tr(" м"),
                          decimals=0)
        self.snap.setToolTip(tr(
            "В этом радиусе от точки ищется русло - место с наибольшим "
            "водосбором, водосбор строится от него. Щелчок рядом с "
            "рекой так даёт водосбор реки. 0 - водосбор ровно от точки."))
        self.on_stream = QCheckBox(tr("Обрывать на водотоке"), self)
        self.on_stream.setToolTip(tr(
            "Линия стока кончается, дойдя до водотока с водосбором "
            "от площади поля «Водотоки от». Без флажка линия идёт до "
            "края участка."))
        self.on_flat = QCheckBox(tr("Обрывать на выполаживании"), self)
        self.on_flat.setToolTip(tr(
            "Линия стока кончается там, где средний уклон на длине "
            "участка ниже порога - у подножия склона, на террасе, на "
            "пойме. Короткая полка на крутом склоне линию не обрывает."))
        self.flat_slope = _spin(self, 0.1, 45.0, FLAT_SLOPE, "°")
        self.flat_slope.setToolTip(tr(
            "Уклон, ниже которого рельеф считается выположенным."))
        self.flat_len = _spin(self, 10.0, 5000.0, FLAT_LENGTH, tr(" м"),
                              decimals=0)
        self.flat_len.setToolTip(tr(
            "Длина участка, на которой меряется средний уклон. Больше - "
            "линию обрывает только долгое выполаживание."))
        self.merge = QCheckBox(tr("Обрывать при слиянии"), self)
        self.merge.setChecked(True)
        self.merge.setToolTip(tr(
            "Линии от метки кончаются, вливаясь в линию, построенную "
            "раньше, и общее русло идёт одной линией. Без флажка каждая "
            "линия идёт до конца, и по общему руслу проходят все."))
        for box in (self.flat_slope, self.flat_len):
            box.setEnabled(False)
            self.on_flat.toggled.connect(box.setEnabled)
        self.item = None
        form = QFormLayout()
        self.place_label = QLabel(tr("Точка"), self)
        form.addRow(self.place_label, self.place)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Водотоки от"), self.net)
        form.addRow(tr("Порядок от"), self.order)
        form.addRow(tr("Радиус поиска русла"), self.snap)
        form.addRow("", self.on_stream)
        form.addRow("", self.on_flat)
        form.addRow(tr("Уклон выполаживания"), self.flat_slope)
        form.addRow(tr("Длина участка"), self.flat_len)
        form.addRow("", self.merge)
        buttons = QDialogButtonBox(self)
        line = QPushButton(tr("Линия стока"), self)
        line.setToolTip(tr(
            "Путь воды от точки вниз по рельефу - слой линии в проект "
            "QGIS. Впадины заполнены до перелива, поэтому линия "
            "проходит через озёра и бессточные котловины. У пути "
            "и многоугольника - линии от всех их узлов одним слоем."))
        line.clicked.connect(self.line)
        basin = QPushButton(tr("Водосбор"), self)
        basin.setToolTip(tr(
            "Площадь, с которой вода стекает к точке, и главный "
            "водоток - два слоя в проект QGIS с площадью, высотами, "
            "длиной и уклоном водотока. Водосбор строится от русла "
            "рядом с точкой."))
        basin.clicked.connect(self.basin)
        rivers = QPushButton(tr("Речная сеть"), self)
        rivers.setToolTip(tr(
            "Водотоки участка с порядком по Стралеру - слой линий "
            "GeoPackage в проект QGIS, толщина линии растёт с порядком."))
        rivers.clicked.connect(self.rivers)
        basins = QPushButton(tr("Бассейны"), self)
        basins.setToolTip(tr(
            "Участок, поделённый на бассейны устьев - мест, где водотоки "
            "с водосбором от площади поля «Водотоки от» уходят из "
            "участка. Слой многоугольников GeoPackage в проект QGIS."))
        basins.clicked.connect(self.basins)
        self.basin_button = basin
        for button in (line, basin, rivers, basins):
            buttons.addButton(button, enum(QDialogButtonBox, "ButtonRole",
                                           "ActionRole"))
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def set_item(self, item):
        """Метка «Моих меток», от которой идут линии стока, или None -
        расчёт у точки."""
        self.item = item
        self.merge.setVisible(item is not None)
        self.basin_button.setEnabled(item is None)
        self.place_label.setText(tr("Метка") if item is not None
                                 else tr("Точка"))

    def net_area(self):
        """Площадь водотоков, м²."""
        return self.net.value() * 1e6

    def stops(self):
        """Остановки линии стока: (площадь водотока или None,
        (уклон, длина) или None)."""
        area = self.net_area() if self.on_stream.isChecked() else None
        flat = (self.flat_slope.value(), self.flat_len.value()) \
            if self.on_flat.isChecked() else None
        return area, flat


class SeaLevelDialog(QDialog):
    """Окно «Уровень моря». Сигнал level - уровень, м над нынешним."""

    level = pyqtSignal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Уровень моря"))
        self.value = _spin(self, SEA_LOW, SEA_HIGH, 0.0, tr(" м"))
        self.value.setKeyboardTracking(False)
        self.value.setToolTip(tr(
            "Уровень моря над нынешним. Вода заливает всё ниже уровня, "
            "ниже нуля открывает шельф. Около -120 м - последний "
            "ледниковый максимум, около +70 м - таяние всех ледников."))
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setRange(SEA_LOW, SEA_HIGH)
        self.slider.setToolTip(self.value.toolTip())
        self.value.valueChanged.connect(self._spun)
        self.slider.valueChanged.connect(self._slid)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Уровень"), self.value)
        form.addRow("", self.slider)
        buttons = QDialogButtonBox(self)
        reset = QPushButton(tr("Нынешний"), self)
        reset.setToolTip(tr("Вернуть нынешний уровень моря."))
        reset.clicked.connect(lambda: self.value.setValue(0.0))
        buttons.addButton(reset, enum(QDialogButtonBox, "ButtonRole",
                                      "ActionRole"))
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)

    def _spun(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(value)))
        self.slider.blockSignals(False)
        self.level.emit(value)

    def _slid(self, value):
        self.value.setValue(float(value))


class _Message:
    """Строка состояния окна глобуса вместо строки окна: расчёт по метке
    «Моих меток» идёт без своего окна."""

    def __init__(self, window, point):
        self.window = window
        self.point = point
        self.status = self

    def setText(self, text):
        if text:
            self.window.message = (text, time.monotonic())
            self.window._show_state()


class GridHeights(QObject):
    """Высоты участка окна расчёта - общая часть воды по рельефу
    и анализа рельефа (ui/relief.py)."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)

    def _start(self, dialog, done, area=None):
        """Высоты рамки участка area (без него - участок окна dialog),
        потом done(dialog, сетка, высоты, загружены ли не все). Вне
        многоугольника участка высоты - NaN."""
        window = self.window
        if window._surface_source() is None \
                or window.view.sky_view is not None:
            dialog.status.setText(tr("Для этого тела высот нет."))
            return
        area = area or dialog.area
        problem = area.check()
        if problem:
            dialog.status.setText(problem)
            return
        lat, lon = area.centre()
        radius_m = area.size() / 2.0
        store = window.view.store
        pixel = 2.0 * math.pi * ellipsoid.A * math.cos(math.radians(lat)) \
            / (TILE * 2 ** store.max_level)
        grid = hydro.make_grid(lat, lon, radius_m, pixel, ellipsoid.A)
        _, keys = viewshed.height_tiles(lat, lon, radius_m * math.sqrt(2.0),
                                        grid.cell, ellipsoid.A,
                                        store.max_level)
        self.job = {"dialog": dialog, "grid": grid, "keys": keys,
                    "done": done, "started": time.monotonic(),
                    "area": area}
        title = dialog.windowTitle() if hasattr(dialog, "windowTitle") \
            else tr("Высоты участка")
        window.spinner.set_job(self.busy_key(), title, self.stop)
        self.timer.start()
        self._poll()

    def busy_key(self):
        """Ключ расчёта у значка загрузки."""
        return "grid:" + type(self).__name__

    def stop(self):
        """Остановить загрузку высот - меню значка загрузки."""
        job, self.job = self.job, None
        self.timer.stop()
        self.window.spinner.set_job(self.busy_key())
        if job is not None:
            job["dialog"].status.setText(tr("Расчёт остановлен."))

    def _poll(self):
        job = self.job
        if job is None:
            self.timer.stop()
            self.window.spinner.set_job(self.busy_key())
            return
        window = self.window
        dialog = job["dialog"]
        missing = [k for k in job["keys"] if not window._has_height_tile(k)]
        if missing and time.monotonic() - job["started"] < WAIT:
            window.view.want_tool_heights(missing)
            dialog.status.setText(tr("Загрузка высот: {done} из {total}",
                                     done=len(job["keys"]) - len(missing),
                                     total=len(job["keys"])))
            return
        self.timer.stop()
        self.job = None
        self.window.spinner.set_job(self.busy_key())
        grid = job["grid"]
        lats, lons = hydro.nodes(grid, ellipsoid.A)
        z = np.asarray(window._true_heights(lats.ravel(), lons.ravel()),
                       dtype=np.float64).reshape(lats.shape)
        z[~job["area"].inside(lats, lons)] = np.nan
        job["done"](dialog, grid, z, bool(missing))


class HydroTool(GridHeights):
    """Затопление, линия стока и водосбор у точки окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.state = None  # затопление: сетка, высоты, уровни, уровень
        # Затопления в проекте: номер слоя глубин - (сетка, маска,
        # уровень), вода на глобусе - пока слой есть и отмечен.
        self.kept = {}
        self.kept_shown = set()
        self.flood_dialog = None
        self.flow_dialog = None
        self.sea_dialog = None
        self.flood_session = Session(window, tr("Затопление"))
        self.flow_session = Session(window, tr("Сток воды"))

    # --- окна --------------------------------------------------------------

    def flood_here(self, lat, lon):
        """Окно «Затопление» для точки - пункт меню на глобусе."""
        dialog = self.flood_dialog
        if dialog is None:
            dialog = FloodDialog(self.window)
            dialog.build.connect(self._build_flood)
            dialog.level.connect(self.set_level)
            dialog.finished.connect(self._done)
            self.flood_dialog = dialog
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        dialog.reset()
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        return dialog

    def flow_here(self, lat, lon):
        """Окно «Сток воды» для точки - пункт меню на глобусе."""
        dialog = self.flow_dialog
        if dialog is None:
            dialog = FlowDialog(self.window)
            dialog.line.connect(lambda: self._start(
                self.flow_dialog, self._flow_line))
            dialog.basin.connect(lambda: self._start(
                self.flow_dialog, self._basin))
            dialog.rivers.connect(lambda: self._start(
                self.flow_dialog, self._rivers))
            dialog.basins.connect(lambda: self._start(
                self.flow_dialog, self._outlet_basins))
            dialog.finished.connect(self._flow_closed)
            self.flow_dialog = dialog
        dialog.set_item(None)
        dialog.point = (lat, lon)
        dialog.place.setText(self.window._point_title(lat, lon, None))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        return dialog

    def _flow_closed(self, code=0):
        """Окно «Сток воды» закрыто: следующий расчёт - новая подгруппа,
        контур участка снимается."""
        self.flow_session.reset()
        self.flow_dialog.area.end()

    def flow_from(self, item):
        """Окно «Сток воды» для пути или многоугольника «Моих меток»:
        «Линия стока» строит линии от узлов под меткой (инструмент 2.23
        Isoliner), участок - квадрат, он накрывает метку."""
        points = list(item.shape.points)
        if not points:
            return None
        lat, lon, side = hydro.shape_grid(points, ellipsoid.A)
        dialog = self.flow_here(lat, lon)
        dialog.set_item(item)
        dialog.place.setText(item.name or tr("Без названия"))
        dialog.area.set_square(lat, lon, max(
            dialog.area.side.value() * 1000.0, 2.0 * side))
        return dialog

    def sea_level_here(self):
        """Окно «Уровень моря» - пункт подменю «Анализ участка»."""
        dialog = self.sea_dialog
        if dialog is None:
            dialog = SeaLevelDialog(self.window)
            dialog.level.connect(self.set_sea_level)
            self.sea_dialog = dialog
        dialog.value.setValue(self.window.view.sea_level)
        self._sea_text()
        dialog.show()
        dialog.raise_()
        return dialog

    def set_sea_level(self, level):
        """Уровень моря level м над нынешним по всему глобусу. Ниже нуля
        нужны глубины морей - они включаются."""
        window = self.window
        view = window.view
        view.sea_level = float(level)
        if level < 0.0 and window.planet.earth and not view.sea_floor \
                and not window._geoid_on():
            window.set_sea_depths(True)
        view.update()
        self._sea_text()

    def _sea_text(self):
        dialog = self.sea_dialog
        if dialog is None:
            return
        level = self.window.view.sea_level
        if level == 0.0:
            text = tr("Нынешний уровень моря.")
        else:
            text = tr("Вода заливает всё ниже уровня по всему глобусу. "
                      "Связь с морем не проверяется, поэтому низины "
                      "внутри материков тоже заливаются.")
        if not self.window._relief_target():
            text += " " + tr("Вода видна при включённом рельефе.")
        dialog.status.setText(text)

    def catchment_of(self, item, side=None):
        """Водосбор пути или многоугольника «Моих меток» - всё, откуда
        вода приходит в метку (инструмент 2.16 Isoliner). Итог -
        слой многоугольника в проект. Водосбор у края
        участка считается заново на участке в GROW раз шире, не шире
        SHAPE_MOST."""
        points = list(item.shape.points)
        if not points:
            return
        lat, lon, least = hydro.shape_grid(points, ellipsoid.A)
        side = max(least, side or 0.0)
        sink = _Message(self.window, (lat, lon))
        area = FixedArea(lat, lon, 2.0 * side)
        sink.area = area
        self._start(sink, lambda dialog, grid, z, partial:
                    self._shape_basin(dialog, grid, z, partial, item,
                                      side), area)

    # --- затопление --------------------------------------------------------

    def _rivers(self, dialog, grid, z, partial, path=None):
        """Речная сеть участка слоем GeoPackage в проект QGIS. path -
        файл, без него - окно выбора."""
        area = dialog.net.value() * 1e6
        streams = hydro.rivers(z, grid.cell, area, dialog.order.value())
        if not streams:
            dialog.status.setText(tr("Водотоков с таким водосбором "
                                     "и порядком на участке нет."))
            return None
        if path is None:
            path = result_path("rivers", ".gpkg")
        lines = []
        for stream in streams:
            lats, lons = hydro.latlon(grid, stream.rows, stream.cols,
                                      ellipsoid.A)
            lines.append((list(zip(lons.tolist(), lats.tolist())),
                          stream.order, stream.area / 1e6))
        if not write_rivers(path, lines):
            dialog.status.setText(tr("Речная сеть не записана в "
                                     "«{path}».", path=path))
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        layer = QgsVectorLayer(path + "|layername=rivers", name, "ogr")
        if layer.isValid():
            style_rivers(layer)
            show_layer(self.window,
                       _to_group(layer, self._group_of(dialog)))
        top = max(s.order for s in streams)
        text = tr("В проект добавлено водотоков {count}, наибольший "
                  "порядок {order}.", count=len(streams), order=top)
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        dialog.status.setText(text + " " + built_text())
        return path

    def _shape_basin(self, dialog, grid, z, partial, item, side=None):
        kind = item.shape.kind
        seeds, length = hydro.shape_seeds(grid, kind, item.shape.points,
                                          ellipsoid.A)
        if not seeds:
            dialog.status.setText(tr("Метка за краем данных высот."))
            return None
        result = hydro.shape_catchment(z, seeds, grid.cell, length)
        if result.edge and side is not None \
                and side < SHAPE_MOST * 0.99:
            self.catchment_of(item, min(side * GROW, SHAPE_MOST))
            return None
        rings = hydro.outline(result.mask)
        if not rings:
            dialog.status.setText(tr("К метке вода не стекает: водосбора "
                                     "нет."))
            return None
        window = self.window
        name = tr("Водосбор «{name}»", name=item.name or tr("Без названия"))
        rep = result.report
        text = tr("Площадь {area} км², высоты {low}-{high} м, средняя "
                  "{mean} м.", area=number(rep.get("area_km2")),
                  low=number(rep.get("z_min"), 4),
                  high=number(rep.get("z_max"), 4),
                  mean=number(rep.get("z_mean"), 4))
        if result.edge:
            text += " " + tr("Водосбор доходит до края участка, его часть "
                             "за краем не учтена. Нужен больший участок.")
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        ring = rings[0]
        lats, lons = hydro.latlon(grid, ring[:, 0], ring[:, 1], ellipsoid.A)
        session = Session(self.window, tr("Водосбор метки"))
        layer = self._vector(
            "catchment", "polygon",
            [(list(zip(lats.tolist(), lons.tolist())), _basin_fields(rep))],
            BASIN_FIELDS, name, BASIN_COLOR, fill=BASIN_FILL,
            group=session.group_for(dialog.area.ring))
        dialog.status.setText(self._added(layer, name, text))
        return layer

    def _group_of(self, dialog):
        """Подгруппа расчёта окна dialog в проекте (ui/results.py)."""
        session = self.flood_session if dialog is self.flood_dialog \
            else self.flow_session
        return session.group_for(dialog.area.ring)

    def _vector(self, stem, kind, items, fields, title, color, width=None,
                fill=None, group=None):
        """Объекты результата слоем GeoPackage в подгруппу расчёта окна
        стока, отмечен на глобусе. None - не записан."""
        path = result_path(stem, ".gpkg")
        if not write_vector(path, stem, kind, items, fields):
            return None
        if group is None:
            group = self._group_of(self.flow_dialog)
        return add_vector(self.window, path, stem, title, group,
                          color, width=width, fill=fill)

    def _added(self, layer, name, text):
        """Строка итога: слой в проекте или не записан."""
        if layer is None:
            return tr("Слой «{name}» не записан.", name=name)
        return tr("В проект добавлен слой «{name}». {text}", name=name,
                  text=text) + " " + built_text()

    def _build_flood(self):
        self.flood_dialog.reset()
        self._start(self.flood_dialog, self._flood_ready)

    def _flood_ready(self, dialog, grid, z, partial):
        seed = hydro.index_of(grid, dialog.point[0], dialog.point[1],
                              ellipsoid.A)
        base = float(z[seed])
        if not math.isfinite(base):
            dialog.status.setText(tr("Точка вне участка или в ней нет "
                                     "высот."))
            return
        levels = hydro.spill_levels(z, seed)
        old = self.state
        level = base + DEFAULT_RISE
        if old is not None and old["point"] == dialog.point:
            level = old["level"]
        self.state = {"grid": grid, "z": z, "levels": levels,
                      "point": dialog.point, "partial": partial,
                      "level": level, "flood": None, "built": built_text()}
        dialog.ready(base, level)
        self.set_level(level)

    def set_level(self, level):
        """Вода уровня level: поверхность на глобусе и итог в окне."""
        state = self.state
        if state is None:
            return
        state["level"] = float(level)
        grid = state["grid"]
        result = hydro.flood(state["z"], state["levels"], level, grid.cell)
        state["flood"] = result
        self._show_water()
        dialog = self.flood_dialog
        if not result.mask.any():
            text = tr("Уровень не выше точки, воды нет.")
        else:
            text = tr("Затоплено {area} км², объём воды {volume} млн м³, "
                      "наибольшая глубина {depth} м.",
                      area=number(result.area / 1e6),
                      volume=number(result.volume / 1e6),
                      depth=number(result.depth))
            text += " " + stats_text(tr("Глубина"),
                                     level - state["z"][result.mask],
                                     tr(" м"))
            if result.edge:
                text += " " + tr("Вода дошла до края участка и может идти "
                                 "дальше. Нужен больший участок.")
        text += " " + tr("Шаг сетки {step} м.", step=number(grid.cell))
        if state["partial"]:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        if not self.window._relief_target():
            text += " " + tr("Вода видна при включённом рельефе.")
        text += " " + state.get("built", "")
        if dialog is not None:
            dialog.status.setText(text.strip())

    def _show_water(self):
        """Поверхность воды затопления в воде водоёмов вида."""
        water = self.window.view.lake_water
        water.set_mesh(FLOOD_KEY, self.water_mesh())
        self.window.view.update()

    def water_mesh(self):
        """Сетка поверхности воды затопления окна или None: высота на
        экране - уровень, умноженный на масштаб рельефа."""
        state = self.state
        scale = self.window._relief_target()
        if state is None or state["flood"] is None or not scale:
            return None
        return flood_mesh(state["grid"], state["flood"].mask, state["level"],
                          scale, FLOOD_KEY)

    def kept_meshes(self):
        """Вода записанных в проект затоплений, слой глубин которых есть
        и отмечен на глобусе: {ключ сетки: сетка}."""
        scale = self.window._relief_target()
        if not scale:
            return {}
        out = {}
        for layer_id, (grid, mask, level) in self.kept.items():
            if layer_id in self.kept_shown:
                out[FLOOD_KEY + layer_id] = flood_mesh(
                    grid, mask, level, scale, FLOOD_KEY + layer_id)
        return out

    def sync_kept(self, layer_ids):
        """Отмеченные слои проекта сменились: вода записанных затоплений
        следует за своими слоями глубин, удалённый слой забывается."""
        project = QgsProject.instance()
        for layer_id in list(self.kept):
            if project.mapLayer(layer_id) is None:
                del self.kept[layer_id]
        shown = set(layer_ids) & set(self.kept)
        if shown != self.kept_shown:
            self.kept_shown = shown
            self.window._update_water()

    def _done(self, code):
        """Окно «Затопление» закрыто: OK - глубины и контур в проект QGIS,
        вода остаётся на глобусе вместе со слоем глубин, иначе вода
        окна убирается (ui/results.py)."""
        if accepted(code):
            self.export_flood()
        self.clear_flood()
        self.flood_session.reset()
        self.flood_dialog.area.end()

    def clear_flood(self):
        self.state = None
        if self.job is not None and self.job["dialog"] is self.flood_dialog:
            self.job = None
            self.timer.stop()
            self.window.spinner.set_job(self.busy_key())
        self.window.view.lake_water.set_mesh(FLOOD_KEY, None)
        self.window.view.update()
        if self.flood_dialog is not None:
            self.flood_dialog.reset()
            self.flood_dialog.status.setText("")

    def export_flood(self, path=None):
        """Растр глубин GeoTIFF и многоугольник затопления GeoPackage
        в проект QGIS, растр отмечен на глобусе, вода затопления
        следует за ним (kept). path - файл GeoTIFF, без него - новый
        файл результата (ui/results.py)."""
        state = self.state
        if state is None or state["flood"] is None \
                or not state["flood"].mask.any():
            return None
        if path is None:
            path = result_path("flood")
        result = state["flood"]
        depth = np.where(result.mask, state["level"] - state["z"], np.nan)
        polygons = os.path.splitext(path)[0] + ".gpkg"
        if not write_flood(path, polygons, state["grid"], depth,
                           result.mask, state["level"]):
            self.flood_dialog.status.setText(
                tr("Затопление не записано в «{path}».", path=path))
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        top = float(np.nanmax(depth))
        group = self._group_of(self.flood_dialog)
        layer = QgsVectorLayer(polygons + "|layername=flood",
                               tr("{name} - контур", name=name), "ogr")
        if layer.isValid():
            layer.setOpacity(0.5)
            _to_group(layer, group)
        raster = add_raster(path, tr("{name} - глубина", name=name),
                            [(0.0, DEPTH_COLORS[0]), (max(top, 0.1),
                                                      DEPTH_COLORS[1])],
                            group=group, abstract=stats_text(
                                tr("Глубина"), depth, tr(" м")))
        if raster is not None:
            self.kept[raster.id()] = (state["grid"], result.mask.copy(),
                                      state["level"])
            show_layer(self.window, raster)
        return path

    # --- сток --------------------------------------------------------------

    def _flow_line(self, dialog, grid, z, partial):
        if getattr(dialog, "item", None) is not None:
            return self._shape_lines(dialog, grid, z, partial)
        seed = hydro.index_of(grid, dialog.point[0], dialog.point[1],
                              ellipsoid.A)
        if not math.isfinite(float(z[seed])):
            dialog.status.setText(tr("Точка вне участка или в ней нет "
                                     "высот."))
            return None
        area, flat = dialog.stops()
        line = hydro.flow_line(z, seed, grid.cell, area=area, flat=flat)
        if len(line.rows) < 2:
            dialog.status.setText(tr("Вода из точки никуда не стекает."))
            return None
        lats, lons = hydro.latlon(grid, line.rows, line.cols, ellipsoid.A)
        points = list(zip(lats.tolist(), lons.tolist()))
        name = tr("Линия стока {point}", point="{:.4f}, {:.4f}".format(
            *dialog.point))
        text = tr("Длина {km} км, падение {drop} м.",
                  km=number(line.length / 1000.0),
                  drop=number(line.drop))
        text += " " + end_text(line.end)
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        layer = self._vector("flow", "line", [(points, _line_fields(line))],
                             LINE_FIELDS, name, LINE_COLOR, width=0.8)
        dialog.status.setText(self._added(layer, name, text))
        return layer

    def _shape_lines(self, dialog, grid, z, partial):
        """Линии стока от узлов пути или многоугольника - слоем
        в проект."""
        item = dialog.item
        seeds, _ = hydro.shape_seeds(grid, item.shape.kind,
                                     item.shape.points, ellipsoid.A)
        seeds = [s for s in seeds if math.isfinite(float(z.flat[s]))]
        if not seeds:
            dialog.status.setText(tr("Метка за краем данных высот."))
            return None
        area, flat = dialog.stops()
        lines = [line for line in hydro.flow_lines(
            z, seeds, grid.cell, area=area, flat=flat,
            merge=dialog.merge.isChecked()) if len(line.rows)
            >= hydro.MIN_LINE]
        if not lines:
            dialog.status.setText(tr("Вода от метки никуда не стекает."))
            return None
        dropped = max(0, len(lines) - LINES_MOST)
        lines = sorted(lines, key=lambda line: -line.length)[:LINES_MOST]
        items = []
        for line in lines:
            lats, lons = hydro.latlon(grid, line.rows, line.cols,
                                      ellipsoid.A)
            items.append((list(zip(lats.tolist(), lons.tolist())),
                          _line_fields(line)))
        name = tr("Линии стока «{name}»",
                  name=item.name or tr("Без названия"))
        layer = self._vector("flow_lines", "line", items, LINE_FIELDS,
                             name, LINE_COLOR, width=0.5)
        total = sum(line.length for line in lines)
        text = tr("Линий {count}, общая длина {km} км.",
                  count=len(lines), km=number(total / 1000.0))
        if dropped:
            text += " " + tr("Самых коротких линий не вошло {count}.",
                             count=dropped)
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        dialog.status.setText(self._added(layer, name, text))
        return layer

    def _outlet_basins(self, dialog, grid, z, partial, path=None):
        """Бассейны участка от устьев слоем GeoPackage в проект QGIS.
        path - файл, без него - окно выбора."""
        regions = hydro.outlet_basins(z, grid.cell, dialog.net_area())
        polygons = []
        for region in regions:
            rings = hydro.outline(region.mask)
            if not rings:
                continue
            lats, lons = hydro.latlon(grid, rings[0][:, 0], rings[0][:, 1],
                                      ellipsoid.A)
            polygons.append((list(zip(lons.tolist(), lats.tolist())),
                             region.area / 1e6))
        if not polygons:
            dialog.status.setText(tr("Водотоков с таким водосбором "
                                     "у края участка нет."))
            return None
        if path is None:
            path = result_path("basins", ".gpkg")
        if not write_basins(path, polygons):
            dialog.status.setText(tr("Бассейны не записаны в «{path}».",
                                     path=path))
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        layer = QgsVectorLayer(path + "|layername=basins", name, "ogr")
        if layer.isValid():
            style_basins(layer)
            show_layer(self.window,
                       _to_group(layer, self._group_of(dialog)))
        covered = sum(area for _, area in polygons)
        text = tr("В проект добавлено бассейнов {count}, они покрывают "
                  "{area} км² участка.", count=len(polygons),
                  area=number(covered))
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        dialog.status.setText(text + " " + built_text())
        return path

    def _basin(self, dialog, grid, z, partial):
        seed = hydro.index_of(grid, dialog.point[0], dialog.point[1],
                              ellipsoid.A)
        if not math.isfinite(float(z[seed])):
            dialog.status.setText(tr("Точка вне участка или в ней нет "
                                     "высот."))
            return None
        basin = hydro.watershed(z, seed, grid.cell, snap=int(round(
            dialog.snap.value() / float(grid.cell))))
        rings = hydro.outline(basin.mask)
        if not rings or int(basin.mask.sum()) < 3:
            dialog.status.setText(tr("К точке вода не стекает: водосбора "
                                     "нет."))
            return None
        name = tr("Водосбор {point}", point="{:.4f}, {:.4f}".format(
            *dialog.point))
        text = basin_text(basin.report)
        moved = math.hypot(basin.seed[0] - seed[0],
                           basin.seed[1] - seed[1]) * grid.cell
        if moved > 0.0:
            text += " " + tr("Створ перенесён на русло в {m} м от точки.",
                             m=number(moved))
        if basin.edge:
            text += " " + tr("Водосбор доходит до края участка, его часть "
                             "за краем не учтена. Нужен больший участок.")
        if partial:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        ring = rings[0]
        lats, lons = hydro.latlon(grid, ring[:, 0], ring[:, 1], ellipsoid.A)
        layer = self._vector(
            "catchment", "polygon",
            [(list(zip(lats.tolist(), lons.tolist())),
              _basin_fields(basin.report))],
            BASIN_FIELDS, name, BASIN_COLOR, fill=BASIN_FILL)
        rows, cols = basin.stream
        if layer is not None and len(rows) > 1:
            lats, lons = hydro.latlon(grid, rows[::-1], cols[::-1],
                                      ellipsoid.A)
            report = basin.report
            self._vector(
                "main_stream", "line",
                [(list(zip(lats.tolist(), lons.tolist())), {
                    "length_km": _round(report.get("stream_km"), 3),
                    "fall_m": _round(report.get("stream_fall_m")),
                    "slope_ppm": _round(report.get("stream_ppm"))})],
                [("length_km", "real"), ("fall_m", "real"),
                 ("slope_ppm", "real")],
                tr("Главный водоток {point}", point="{:.4f}, {:.4f}".format(
                    *dialog.point)), LINE_COLOR, width=0.8)
        dialog.status.setText(self._added(layer, name, text))
        return layer


def flood_mesh(grid, mask, level, scale, key):
    """Сетка поверхности воды затопления или None: mask - затопленные
    узлы сетки grid, вода на уровне level, высота на экране -
    level × scale."""
    if not mask.any():
        return None
    stride, wet = hydro.water_nodes(mask)
    rows = np.arange(wet.shape[0]) * stride + (stride - 1) / 2.0
    cols = np.arange(wet.shape[1]) * stride + (stride - 1) / 2.0
    cc, rr = np.meshgrid(cols, rows)
    lats, lons = hydro.latlon(grid, rr, cc, ellipsoid.A)
    bed = np.where(wet, level - 1.0, np.nan)
    part = bathymetry.water_part(lats, lons, bed, level, level * scale)
    if part is None:
        return None
    return subsurface.merge([part], key=key)


LINE_FIELDS = [("length_km", "real"), ("drop_m", "real"), ("end", "str")]
BASIN_FIELDS = [("area_km2", "real"), ("z_min", "real"), ("z_max", "real"),
                ("z_mean", "real")]


def _round(value, digits=1):
    """Число поля слоя или None."""
    if value is None:
        return None
    value = float(value)
    return round(value, digits) if math.isfinite(value) else None


def _line_fields(line):
    """Поля линии стока слоя проекта."""
    return {"length_km": _round(line.length / 1000.0, 3),
            "drop_m": _round(line.drop), "end": str(line.end)}


def _basin_fields(rep):
    """Поля водосбора слоя проекта."""
    return {"area_km2": _round(rep.get("area_km2"), 3),
            "z_min": _round(rep.get("z_min")),
            "z_max": _round(rep.get("z_max")),
            "z_mean": _round(rep.get("z_mean"))}


def basin_text(rep):
    """Итог водосбора строкой для окна."""
    lines = [tr("Площадь {area} км², высоты {low}-{high} м, средняя "
                "{mean} м.", area=number(rep.get("area_km2")),
                low=number(rep.get("z_min"), 4),
                high=number(rep.get("z_max"), 4),
                mean=number(rep.get("z_mean"), 4))]
    lines.append(stream_text(rep))
    if rep.get("sp_slope_ppm") is not None:
        lines.append(tr("Средний уклон склонов {slope} промилле по "
                        "СП 33-101-2003.",
                        slope=number(rep.get("sp_slope_ppm"))))
    if rep.get("net_dens") is not None:
        lines.append(tr("Густота речной сети {dens} км на км², водотоки "
                        "с водосбором от {area} км².",
                        dens=number(rep.get("net_dens")),
                        area=number(hydro.NET_AREA / 1e6)))
    return " ".join(lines)


def end_text(end):
    """Чем кончилась линия стока, строкой."""
    return {"edge": tr("Линия дошла до края участка, дальше вода идёт за "
                       "его пределы."),
            "stream": tr("Линия кончается на водотоке."),
            "flat": tr("Линия кончается, где рельеф выполаживается."),
            "merge": tr("Линия вливается в другую линию стока."),
            }.get(end, tr("Линия кончается у края данных высот."))


def stream_text(rep):
    """Главный водоток строкой."""
    return tr("Главный водоток {km} км, падение {fall} м, уклон {slope} "
              "промилле.", km=number(rep.get("stream_km")),
              fall=number(rep.get("stream_fall_m")),
              slope=number(rep.get("stream_ppm")))


def write_flood(path, polygons, grid, depth, mask, level):
    """Глубины в GeoTIFF path и контур затопления в слой flood файла
    GeoPackage polygons, система EPSG:3857. Главный поток. True, если
    записано."""
    from osgeo import gdal, ogr, osr
    from .inset import warm
    warm()
    rows, cols = depth.shape
    transform = (grid.x0 - grid.step / 2.0, grid.step, 0.0,
                 grid.y0 + grid.step / 2.0, 0.0, -grid.step)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    data = gdal.GetDriverByName("GTiff").Create(
        path, cols, rows, 1, gdal.GDT_Float32, ["COMPRESS=DEFLATE"])
    if data is None:
        return False
    data.SetGeoTransform(transform)
    data.SetProjection(srs.ExportToWkt())
    band = data.GetRasterBand(1)
    band.SetNoDataValue(float("nan"))
    band.WriteArray(depth.astype(np.float32))
    data = None
    source = gdal.GetDriverByName("MEM").Create("", cols, rows, 1,
                                                gdal.GDT_Byte)
    source.SetGeoTransform(transform)
    source.SetProjection(srs.ExportToWkt())
    wet = source.GetRasterBand(1)
    wet.WriteArray(mask.astype(np.uint8))
    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(polygons):
        driver.DeleteDataSource(polygons)
    out = driver.CreateDataSource(polygons)
    if out is None:
        return False
    layer = out.CreateLayer("flood", srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("wet", ogr.OFTInteger))
    code = gdal.Polygonize(wet, wet, layer, 0, ["8CONNECTED=8"])
    layer.CreateField(ogr.FieldDefn("level", ogr.OFTReal))
    layer.ResetReading()
    for feature in layer:
        feature.SetField("level", float(level))
        layer.SetFeature(feature)
    out = None
    source = None
    return code == 0


def write_rivers(path, lines):
    """Звенья речной сети в слой rivers файла GeoPackage path, EPSG:4326,
    поля order (порядок по Стралеру) и area_km2 (водосбор в замыкании
    звена). lines - (точки (долгота, широта), порядок, площадь)."""
    from osgeo import ogr, osr
    from .inset import warm
    warm()
    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(path):
        driver.DeleteDataSource(path)
    out = driver.CreateDataSource(path)
    if out is None:
        return False
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layer = out.CreateLayer("rivers", srs, ogr.wkbLineString)
    layer.CreateField(ogr.FieldDefn("order", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("area_km2", ogr.OFTReal))
    for points, order, area in lines:
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("order", int(order))
        feature.SetField("area_km2", float(area))
        line = ogr.Geometry(ogr.wkbLineString)
        for lon, lat in points:
            line.AddPoint_2D(lon, lat)
        feature.SetGeometry(line)
        layer.CreateFeature(feature)
    out = None
    return True


def write_basins(path, polygons):
    """Бассейны в слой basins файла GeoPackage path, EPSG:4326, поля
    basin (номер, крупные первыми) и area_km2. polygons - (кольцо
    (долгота, широта), площадь)."""
    from osgeo import ogr, osr
    from .inset import warm
    warm()
    driver = ogr.GetDriverByName("GPKG")
    if os.path.exists(path):
        driver.DeleteDataSource(path)
    out = driver.CreateDataSource(path)
    if out is None:
        return False
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    layer = out.CreateLayer("basins", srs, ogr.wkbPolygon)
    layer.CreateField(ogr.FieldDefn("basin", ogr.OFTInteger))
    layer.CreateField(ogr.FieldDefn("area_km2", ogr.OFTReal))
    for number_, (points, area) in enumerate(polygons, 1):
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("basin", number_)
        feature.SetField("area_km2", float(area))
        ring = ogr.Geometry(ogr.wkbLinearRing)
        for lon, lat in points + points[:1]:
            ring.AddPoint_2D(lon, lat)
        polygon = ogr.Geometry(ogr.wkbPolygon)
        polygon.AddGeometry(ring)
        feature.SetGeometry(polygon)
        layer.CreateFeature(feature)
    out = None
    return True


def style_basins(layer):
    """Бассейны разными цветами по номеру, полупрозрачно."""
    from qgis.core import QgsFillSymbol
    symbol = QgsFillSymbol.createSimple({"color": "60,140,255,60",
                                         "outline_color": RIVER_COLOR,
                                         "outline_width": "0.4"})
    symbol.symbolLayer(0).setDataDefinedProperty(
        _property("FillColor"), QgsProperty.fromExpression(
            "color_hsla(\"basin\" * 47 % 360, 70, 55, 45)"))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))


def style_rivers(layer):
    """Синие линии водотоков, толщина растёт с порядком."""
    symbol = QgsLineSymbol.createSimple({"line_color": RIVER_COLOR,
                                         "line_width": "0.2"})
    symbol.symbolLayer(0).setDataDefinedProperty(
        STROKE_WIDTH, QgsProperty.fromExpression(
            '0.15 + 0.2 * "order"'))
    layer.setRenderer(QgsSingleSymbolRenderer(symbol))
