# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Ряд по датам»: индекс участка по сценам окна «Космоснимки».

Сцены - видимые в списке окна снимков, то есть найденные и не облачнее
заданного над участком. Сводку каждой сцены считает рабочий поток
своего пула series (ui.sentinel.series_value), график дополняется по мере
расчёта. Точка - медиана участка, отрезок - от 10-го до 90-го
процентиля (core/series.py). Щелчок по точке выбирает сцену в списке
окна снимков, её превью и выдача - как обычно. Таблица ряда пишется
в CSV.
"""
import math
import os

from qgis.PyQt.QtCore import QPointF, QRectF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QFileDialog, QHBoxLayout, QLabel,
                                 QPushButton, QVBoxLayout, QWidget)

from ..core import series
from ..i18n import tr
from ..qt_compat import enum
from .elevation import NBSP, nice_step

POLL = 200  # мс между проверками заданий
# Сцен ряда, читаемых сразу. Свой пул: в общем пуле окна снимков
# 4 потока, ряд из 43 сцен Sentinel-2 шёл 140 с, сцене нужно 3-4 файла
# по сети, и время уходит на ожидание ответов, а не на расчёт.
SERIES_WORKERS = 8
POINT = QColor(30, 130, 80)  # точки и линия медианы
BAND = QColor(30, 130, 80, 90)  # отрезок 10-90 %
HOVER = QColor(220, 60, 40)
GRID = QColor(128, 128, 128, 90)
MARGIN = (58, 26, 14, 30)  # слева, сверху, справа, снизу, пиксели
PICK = 8.0  # пикселей до точки, щелчок по которой выбирает сцену
CENTER = enum(Qt, "AlignmentFlag", "AlignCenter")
VCENTER = enum(Qt, "AlignmentFlag", "AlignVCenter")
RIGHT = enum(Qt, "AlignmentFlag", "AlignRight") | VCENTER
LEFT = enum(Qt, "AlignmentFlag", "AlignLeft") | VCENTER
TEMPERATURES = ("lst", "lst_day", "lst_night")


def value_text(product, value):
    """Значение продукта для подписи: температура в °C, снег в %,
    индекс - три знака."""
    if product in TEMPERATURES:
        return "{:.1f}{}°C".format(value, NBSP)
    if product == "snow_cover":
        return "{:.0f}{}%".format(value, NBSP)
    return "{:.3f}".format(value)


class SeriesChart(QWidget):
    """График ряда: rows - [(сутки, время сцены, номер, Point)]. Сигнал
    picked - номер сцены точки под щелчком."""

    picked = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.product = ""
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumSize(520, 240)

    def set_rows(self, rows, product):
        self.rows = sorted(rows, key=lambda r: r[0])
        self.product = product
        if self.hover is not None and self.hover >= len(self.rows):
            self.hover = None
        self.update()

    def _plot(self):
        left, top, right, bottom = MARGIN
        return QRectF(left, top, max(1.0, self.width() - left - right),
                      max(1.0, self.height() - top - bottom))

    def _ranges(self):
        days = [r[0] for r in self.rows]
        first, last = min(days), max(days)
        pad = max((last - first) * 0.03, 3.0)
        low = min(r[3].low for r in self.rows)
        high = max(r[3].high for r in self.rows)
        span = max(high - low, 1e-3)
        return first - pad, last + pad, low - span * 0.08, high + span * 0.08

    def _screen(self, rect, ranges):
        x0, x1, y0, y1 = ranges

        def to_screen(day, value):
            return QPointF(rect.left() + (day - x0) / (x1 - x0)
                           * rect.width(),
                           rect.bottom() - (value - y0) / (y1 - y0)
                           * rect.height())
        return to_screen

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        rect = self._plot()
        text = QPen(self.palette().text().color())
        if not self.rows:
            painter.setPen(text)
            painter.drawText(rect, CENTER, tr("Нет точек ряда"))
            return
        ranges = self._ranges()
        x0, x1, y0, y1 = ranges
        to_screen = self._screen(rect, ranges)
        grid = QPen(GRID, 1.0)
        step = nice_step(y1 - y0, 4)
        value = math.ceil(y0 / step) * step
        while value <= y1:
            y = to_screen(x0, value).y()
            painter.setPen(grid)
            painter.drawLine(QPointF(rect.left(), y),
                             QPointF(rect.right(), y))
            painter.setPen(text)
            painter.drawText(QRectF(0, y - 8, MARGIN[0] - 6, 16), RIGHT,
                             value_text(self.product, value))
            value += step
        for day, label in series.date_ticks(x0, x1):
            x = to_screen(day, y0).x()
            painter.setPen(grid)
            painter.drawLine(QPointF(x, rect.top()),
                             QPointF(x, rect.bottom()))
            painter.setPen(text)
            painter.drawText(QRectF(x - 45, rect.bottom() + 4, 90, 16),
                             CENTER, label)
        painter.setPen(QPen(BAND, 3.0))
        for day, _, _, p in self.rows:
            painter.drawLine(to_screen(day, p.low), to_screen(day, p.high))
        if len(self.rows) > 1:
            path = QPainterPath(to_screen(self.rows[0][0],
                                          self.rows[0][3].median))
            for day, _, _, p in self.rows[1:]:
                path.lineTo(to_screen(day, p.median))
            painter.setPen(QPen(POINT, 1.2))
            painter.drawPath(path)
        painter.setPen(QPen(POINT, 1.0))
        painter.setBrush(POINT)
        for day, _, _, p in self.rows:
            painter.drawEllipse(to_screen(day, p.median), 3.0, 3.0)
        if self.hover is not None:
            day, when, _, p = self.rows[self.hover]
            point = to_screen(day, p.median)
            painter.setPen(QPen(HOVER, 1.2))
            painter.setBrush(HOVER)
            painter.drawEllipse(point, 4.5, 4.5)
            painter.setPen(text)
            painter.drawText(
                QRectF(rect.left() + 4, 2, rect.width() - 8, 20), LEFT,
                tr("{when}: медиана {median}, 10-90 % {low} - {high}, "
                   "без облаков {share} % участка",
                   when=when, median=value_text(self.product, p.median),
                   low=value_text(self.product, p.low),
                   high=value_text(self.product, p.high),
                   share="{:.0f}".format(p.share)))

    def _nearest(self, pos):
        if not self.rows:
            return None
        rect = self._plot()
        to_screen = self._screen(rect, self._ranges())
        best, index = None, None
        for i, (day, _, _, p) in enumerate(self.rows):
            point = to_screen(day, p.median)
            distance = math.hypot(point.x() - pos.x(), point.y() - pos.y())
            if best is None or distance < best:
                best, index = distance, i
        return index if best is not None and best <= PICK else None

    @staticmethod
    def _pos(event):
        return event.position() if hasattr(event, "position") \
            else QPointF(event.pos())

    def mouseMoveEvent(self, event):
        index = self._nearest(self._pos(event))
        if index != self.hover:
            self.hover = index
            self.update()

    def mousePressEvent(self, event):
        index = self._nearest(self._pos(event))
        if index is not None:
            self.picked.emit(str(self.rows[index][2]))

    def leaveEvent(self, event):
        if self.hover is not None:
            self.hover = None
            self.update()


class SeriesDialog(QDialog):
    """Окно ряда. owner - окно «Космоснимки»: пул, ключ SAS, участок
    и список сцен."""

    def __init__(self, owner, parent=None):
        super().__init__(parent or owner)
        self.owner = owner
        self.setWindowTitle(tr("Ряд по датам"))
        self.setModal(False)
        self.jobs = []
        self.values = {}  # номер сцены - Point или None
        self.scenes = []
        self.generation = 0
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)
        self.product = QComboBox(self)
        self.product.setToolTip(tr(
            "Величина ряда. Точка - медиана по участку без облаков и теней, "
            "отрезок - от 10-го до 90-го процентиля. Смена величины "
            "считает ряд заново."))
        self.product.currentIndexChanged.connect(lambda *_: self.start())
        self.where = QLabel(self)
        self.where.setWordWrap(True)
        self.chart = SeriesChart(self)
        self.chart.picked.connect(self.owner.select_scene)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.csv = QPushButton(tr("Таблица CSV…"), self)
        self.csv.setToolTip(tr(
            "Ряд в файл CSV - дата и номер сцены, медиана, 10-й и 90-й "
            "процентили, доля участка без облаков. Сцены без значения "
            "идут пустыми строками."))
        self.csv.clicked.connect(lambda _=False: self.save_csv())
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        buttons.addButton(self.csv,
                          enum(QDialogButtonBox, "ButtonRole", "ActionRole"))
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Величина"), self))
        row.addWidget(self.product, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.where)
        layout.addLayout(row)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        self.resize(720, 420)

    def show_series(self, mission, scenes, products, names, area):
        """Ряд по сценам scenes спутника mission. products - продукты
        ряда, names - их названия, area - название участка."""
        self.mission = mission
        self.scenes = sorted(scenes, key=lambda s: s.when)
        text = tr("Участок: {name}, сцен {count}", name=area,
                  count=len(self.scenes))
        if self.owner.cloud_jobs:
            text += ". " + tr("Облачность остальных сцен ещё считается, "
                              "кнопка «Ряд по датам…» потом добавит их.")
        self.where.setText(text)
        current = self.product.currentData()
        self.product.blockSignals(True)
        self.product.clear()
        for key in products:
            self.product.addItem(names.get(key, key), key)
        index = self.product.findData(current)
        self.product.setCurrentIndex(max(index, 0))
        self.product.blockSignals(False)
        self.start()

    def current_product(self):
        return self.product.currentData() or ""

    def start(self):
        """Расчёт ряда заново по выбранной величине."""
        self.generation += 1
        self._cancel()
        self.values = {}
        self.chart.set_rows([], self.current_product())
        if not self.scenes or not self.current_product():
            self.status.setText(tr("Нет сцен для ряда."))
            return
        generation = self.generation
        self.status.setText(tr("Считается ряд: 0 из {total}…",
                               total=len(self.scenes)))
        self.owner.with_token(lambda: self._submit(generation))

    def _submit(self, generation):
        if generation != self.generation:
            return
        from ..net.gdalnet import executor
        from .sentinel import series_value, warm
        warm()
        ring = self.owner.ring_used
        name = self.current_product()
        pool = executor("series", SERIES_WORKERS)
        self.jobs = [(s.id, pool.submit(series_value, s, ring, name,
                                        self.owner.sas))
                     for s in self.scenes]
        self.timer.start()

    def _poll(self):
        pending = []
        for number, job in self.jobs:
            if not job.done():
                pending.append((number, job))
                continue
            try:
                value = job.result()[1]
            except (RuntimeError, ValueError, OSError, KeyError):
                # Файлы сцены не прочитаны - сцена без точки.
                value = None
            self.values[number] = value
        changed = len(pending) != len(self.jobs)
        self.jobs = pending
        if changed:
            self._show()
        if not self.jobs:
            self.timer.stop()

    def rows(self):
        """Точки графика: (сутки, время, номер, Point) сцен со
        значением."""
        out = []
        for s in self.scenes:
            value = self.values.get(s.id)
            if value is not None:
                out.append((series.day_number(s.when), s.when, s.id, value))
        return out

    def _show(self):
        rows = self.rows()
        self.chart.set_rows(rows, self.current_product())
        done = len(self.values)
        total = len(self.scenes)
        if done < total and self.jobs:
            self.status.setText(tr(
                "Считается ряд: {done} из {total}, точек {count}…",
                done=done, total=total, count=len(rows)))
            return
        self.status.setText(tr(
            "Точек {count} из {total}. Сцены без точки - участок закрыт "
            "облаками больше чем на {share} % или файлы не прочитаны.",
            count=len(rows), total=total,
            share="{:.0f}".format(100.0 - series.MIN_CLEAR)))

    def save_csv(self):
        product = self.current_product()
        if not product or not self.values:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("Ряд в CSV"), os.path.join(
                self.owner.folder, "series_{}.csv".format(product)),
            "CSV (*.csv)")
        if not path:
            return
        rows = [(s.when, s.id, self.values.get(s.id))
                for s in self.scenes if s.id in self.values]
        text = series.csv_text(rows, self.product.currentText())
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
        except OSError as error:
            self.status.setText(tr("Файл не записан: {error}",
                                   error=str(error)))
            return
        self.status.setText(tr("Ряд записан: {path}", path=path))

    def _cancel(self):
        for _, job in self.jobs:
            job.cancel()
        self.jobs = []
        self.timer.stop()

    def closeEvent(self, event):
        self.generation += 1
        self._cancel()
        super().closeEvent(event)
