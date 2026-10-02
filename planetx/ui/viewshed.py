# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Видимость из точки: окно с величинами и тайлы слоя вида.

Расчёт - core/viewshed.py. Слой вида - «viewshed» в render/gibs.py,
его картинки тайлов даёт ResultTiles из готового результата, без
сети. Вид просит тайлы так же, как у загрузчика слоёв GIBS:
want_many, retain, abort. Картинка тайла стоит 13-19 мс, поэтому она
считается в рабочем потоке, иначе вид не отвечал мыши.
"""
import math
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
                                 QFormLayout, QLabel, QLayout, QPushButton,
                                 QVBoxLayout)

from ..core import viewshed
from ..core.mipmap import mip_chain
from ..core.slope import row_latitudes
from ..i18n import tr
from ..qt_compat import enum

SIZE = 256
POLL = 15  # мс между проверками рабочего потока
IN_FLIGHT = 2  # заданий в рабочем потоке сразу


def tile_axes(z, x, y):
    """Широты строк и долготы столбцов центров пикселей тайла."""
    n = 1 << z
    lons = (x + (np.arange(SIZE) + 0.5) / SIZE) / n * 360.0 - 180.0
    return row_latitudes(z, y, SIZE), lons


class ResultTiles(QObject):
    """Картинки тайлов слоя по результату расчёта в круге - видимости
    или инсоляции. paint(результат, широты, долготы, радиус тела) даёт
    картинку. Сигнал loaded - ключ тайла, картинка и уровни мипмапов,
    как у загрузчика. Тайл вне рамки круга получает пустую картинку
    без расчёта."""

    loaded = pyqtSignal(object, object, object)

    def __init__(self, result, radius, paint=viewshed.tile_rgba,
                 parent=None):
        super().__init__(parent)
        self.result = result
        self.radius = radius
        self.paint = paint
        # Рамка результата - своя (маска выреза) или рамка круга.
        self.box = getattr(result, "box", None) or viewshed.circle_box(
            result.lat, result.lon, result.radius_m, radius)
        self.queue = []
        self.running = {}  # ключ тайла - задание рабочего потока
        self.pool = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._work)

    def want_many(self, items):
        # Слой просит только тайлы без картинки, повтор просьбы -
        # картинка сброшена видом, она считается заново.
        for key, _ in items:
            if key not in self.queue and key not in self.running:
                self.queue.append(key)
        if self.queue and not self.timer.isActive():
            # Вид просит тайлы из кадра, задания уходят по таймеру.
            self.timer.start()

    def retain(self, wanted):
        self.queue = [k for k in self.queue if k in wanted]

    def abort(self):
        self.timer.stop()
        self.queue = []
        for future in self.running.values():
            future.cancel()
        self.running = {}
        if self.pool is not None:
            self.pool.shutdown(wait=False)
            self.pool = None

    def _paint(self, key):
        """Картинка и мипмапы тайла, в рабочем потоке."""
        south, north, west, east = self.box
        lats, lons = tile_axes(*key)
        if lats.min() > north or lats.max() < south \
                or lons.min() > east or lons.max() < west:
            rgba = np.zeros((SIZE, SIZE, 4), dtype=np.uint8)
        else:
            grid = np.meshgrid(lats, lons, indexing="ij")
            rgba = self.paint(self.result, grid[0], grid[1], self.radius)
        return rgba, mip_chain(rgba)

    def _work(self):
        # Готовые картинки уходят виду, новые задания - рабочему потоку,
        # не больше IN_FLIGHT сразу, чтобы снятые видом тайлы не копились.
        for key, future in list(self.running.items()):
            if future.done():
                del self.running[key]
                rgba, levels = future.result()
                self.loaded.emit(key, rgba, levels)
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=1)
        while self.queue and len(self.running) < IN_FLIGHT:
            key = self.queue.pop(0)
            self.running[key] = self.pool.submit(self._paint, key)
        if not self.queue and not self.running:
            self.timer.stop()


STATUS_LINES = 3  # строк под состояние расчёта
DIALOG_WIDTH = 360  # наименьшая ширина окна, логических пикселей


def fit_status(dialog, layout):
    """Строка состояния окна расчёта переносится на несколько строк
    после показа окна. Место под STATUS_LINES строк оставляется заранее,
    и окно не становится меньше содержимого. Иначе поля сжимались
    и текст в них обрезался снизу."""
    status = dialog.status
    status.setMinimumHeight(STATUS_LINES * status.fontMetrics().lineSpacing())
    status.setAlignment(enum(Qt, "AlignmentFlag", "AlignTop")
                        | enum(Qt, "AlignmentFlag", "AlignLeft"))
    dialog.setMinimumWidth(DIALOG_WIDTH)
    layout.setSizeConstraint(enum(QLayout, "SizeConstraint",
                                  "SetMinimumSize"))


def display_level(step, lat, radius):
    """Уровень тайлов слоя, пиксель которого не крупнее шага расчёта."""
    ground = 2.0 * math.pi * radius * max(math.cos(math.radians(lat)),
                                          0.01) / SIZE
    return int(min(19, max(0, math.ceil(math.log2(ground / step)))))


class ViewshedDialog(QDialog):
    """Окно «Видимость из точки». Сигналы build - высота наблюдателя,
    высота цели, радиус в метрах, clear - убрать слой."""

    build = pyqtSignal(float, float, float)
    clear = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Видимость из точки"))
        self.place = QLabel(self)
        self.observer = QDoubleSpinBox(self)
        self.observer.setRange(0.0, 10000.0)
        self.observer.setDecimals(1)
        self.observer.setSuffix(tr(" м"))
        self.observer.setValue(2.0)
        self.observer.setToolTip(tr(
            "Высота глаза или мачты над рельефом в точке. Выше - дальше "
            "видно и меньше мест скрыто за рельефом."))
        self.target = QDoubleSpinBox(self)
        self.target.setRange(0.0, 10000.0)
        self.target.setDecimals(1)
        self.target.setSuffix(tr(" м"))
        self.target.setToolTip(tr(
            "Высота того, что надо увидеть, над рельефом, например "
            "мачты или здания. При нуле проверяется сама земля."))
        self.radius = QDoubleSpinBox(self)
        self.radius.setRange(0.1, 100.0)
        self.radius.setDecimals(1)
        self.radius.setSuffix(tr(" км"))
        self.radius.setValue(10.0)
        self.radius.setToolTip(tr(
            "Радиус круга расчёта. Больше - шаг расчёта крупнее, он "
            "около пятисотой доли радиуса."))
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        form = QFormLayout()
        form.addRow(tr("Точка"), self.place)
        form.addRow(tr("Высота наблюдателя"), self.observer)
        form.addRow(tr("Высота цели"), self.target)
        form.addRow(tr("Радиус"), self.radius)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.clicked.connect(lambda: self.build.emit(
            self.observer.value(), self.target.value(),
            self.radius.value() * 1000.0))
        remove = QPushButton(tr("Убрать"), self)
        remove.setToolTip(tr("Убрать слой видимости с глобуса."))
        remove.clicked.connect(self.clear)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        buttons.addButton(remove, enum(QDialogButtonBox, "ButtonRole",
                                       "ActionRole"))
        buttons.addButton(enum(QDialogButtonBox, "StandardButton", "Close"))
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
