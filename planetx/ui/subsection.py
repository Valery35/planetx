# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Разрез модели»: подземная модель вниз вдоль пути.

Просьба автора от 4 октября 2026 года. Окно «Разрез» (ui/section.py)
режет Землю на сотни километров, это окно - модель подземного режима
на сотни метров: рельеф, пласты между кровлями, стволы скважин
и тоннели из полосы вдоль линии. Расстояния и отметки - в метрах.
Курсор над графиком отмечает точку на глобусе.
"""
from collections import namedtuple

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (QDialog, QDoubleSpinBox, QFormLayout,
                                 QLabel, QVBoxLayout, QWidget)

from ..core import drillholes, ellipsoid, section
from ..core import subsurface as core
from ..i18n import tr
from ..qt_compat import enum
from .elevation import axis_text, distance_text, nice_step

GRID = QColor(128, 128, 128, 90)
MARGIN = (60, 12, 14, 30)  # слева, сверху, справа, снизу, пиксели
CENTER = enum(Qt, "AlignmentFlag", "AlignCenter")
RIGHT = enum(Qt, "AlignmentFlag", "AlignRight") \
    | enum(Qt, "AlignmentFlag", "AlignVCenter")
LEFT = enum(Qt, "AlignmentFlag", "AlignLeft") \
    | enum(Qt, "AlignmentFlag", "AlignVCenter")
SAMPLES = 400  # точек вдоль линии
BAND = 200.0  # м, полоса скважин и тоннелей вдоль линии, выбор помощника
HEAD = 0.08  # доля высоты графика над наивысшей точкой рельефа
TUNNEL_MARGIN = 20.0  # м ниже самого глубокого тоннеля, если нет пластов

ModelSection = namedtuple(
    "ModelSection",
    "distance lats lons ground beds bottom holes tunnels diameters")
ModelSection.__doc__ = """Разрез модели. distance - м от начала линии,
lats, lons - точки линии, ground - отметки рельефа, beds - [(код, цвет,
верх, низ)] отметки пластов по точкам, bottom - отметка низа модели,
holes - [(название, [(расстояния, отметки, цвет)])] куски стволов по
интервалам, tunnels - [(название, расстояния, отметки, цвет)],
diameters - диаметр тоннеля по названию, м."""


def _runs(mask):
    """Отрезки подряд идущих True: [(начало, конец не включая)]."""
    out = []
    start = None
    for i, on in enumerate(list(mask) + [False]):
        if on and start is None:
            start = i
        elif not on and start is not None:
            out.append((start, i))
            start = None
    return out


def build(model, ground, points, band=BAND, count=SAMPLES):
    """Разрез модели вдоль points [(широта, долгота)] или None.
    ground(lats, lons) - настоящие отметки рельефа."""
    found = section.along(points, count)
    if found is None:
        return None
    km, lats, lons = found
    distance = km * 1000.0
    g = ground(lats, lons)
    bottom = model.bottom()
    if not model.holes and not model.horizons and model.tunnels:
        # Модель из одних тоннелей: низ - под самым глубоким из них.
        lows = []
        for _, pts, (start, end), diameter, _ in model.tunnels:
            tl, to = pts[:, 0], pts[:, 1]
            z = core.tunnel_z(ground(tl, to), start, end,
                              core.along(tl, to))
            lows.append(float(z.min()) - diameter)
        bottom = min(lows) - TUNNEL_MARGIN
    surfaces = [g] + [h.at(lats, lons) for h in model.horizons] \
        + [np.full(len(lats), bottom)]
    stack = core.stack(surfaces)
    top_code = model.beds[0] if model.beds else ""
    codes = [top_code] + [h.code for h in model.horizons]
    beds = [(code, model.color(code), stack[k], stack[k + 1])
            for k, code in enumerate(codes)]
    holes = []
    for hole, lat0, lon0 in model.holes:
        nodes = hole.axis
        hl, ho = _to_latlon(lat0, lon0, nodes[:, 1], nodes[:, 2])
        along, gap = core.to_line(lats, lons, distance, hl, ho)
        if gap.min() > band / 2.0:
            continue
        pieces = []
        for interval in hole.intervals or [
                drillholes.Interval(0.0, hole.eoh, "", {})]:
            part = drillholes.piece(nodes, interval.start, interval.end)
            pl, po = _to_latlon(lat0, lon0, part[:, 0], part[:, 1])
            d, _ = core.to_line(lats, lons, distance, pl, po)
            pieces.append((d, part[:, 2], model.color(interval.code)))
        holes.append((hole.hole_id, pieces))
    tunnels = []
    diameters = {}
    for name, pts, (start, end), diameter, color in model.tunnels:
        diameters[name] = max(diameters.get(name, 0.0), diameter)
        tl, to = pts[:, 0], pts[:, 1]
        z = core.tunnel_z(ground(tl, to), start, end, core.along(tl, to))
        d, gap = core.to_line(lats, lons, distance, tl, to)
        for a, b in _runs(gap <= band / 2.0):
            if b - a >= 2:
                tunnels.append((name, d[a:b], z[a:b], color))
    return ModelSection(distance, lats, lons, g, beds, bottom, holes,
                        tunnels, diameters)


def _to_latlon(lat0, lon0, east, north):
    """Смещения в метрах от устья в широты и долготы."""
    lat = lat0 + np.degrees(np.asarray(north) / ellipsoid.A)
    lon = lon0 + np.degrees(np.asarray(east) / (
        ellipsoid.A * np.cos(np.radians(lat0))))
    return lat, lon


def metres_text(value):
    return tr("{value} м", value="{:.0f}".format(value))


class ModelChart(QWidget):
    """График разреза модели. Сигнал hovered - номер точки линии под
    курсором или -1."""

    hovered = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.section = None
        self.hover = None
        self.setMouseTracking(True)
        self.setMinimumSize(480, 260)

    def set_section(self, value):
        self.section = value
        self.hover = None
        self.update()

    def _plot(self):
        left, top, right, bottom = MARGIN
        return QRectF(left, top, max(1.0, self.width() - left - right),
                      max(1.0, self.height() - top - bottom))

    def _range(self):
        s = self.section
        high = float(np.nanmax(s.ground))
        low = float(s.bottom)
        return high + (high - low) * HEAD, low

    def _mapper(self):
        rect = self._plot()
        s = self.section
        x1 = max(float(s.distance[-1]), 1.0)
        high, low = self._range()

        def to_screen(d, z):
            z = min(max(z, low), high)
            return QPointF(rect.left() + d / x1 * rect.width(),
                           rect.top() + (high - z) / (high - low)
                           * rect.height())
        return rect, x1, high, low, to_screen

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        s = self.section
        if s is None:
            painter.drawText(self._plot(), CENTER, tr("Нет данных"))
            return
        rect, x1, high, low, to_screen = self._mapper()
        for code, color, top, bottom in s.beds:
            good = np.isfinite(top) & np.isfinite(bottom) & (top > bottom)
            for a, b in _runs(good):
                path = QPainterPath(to_screen(float(s.distance[a]),
                                              float(top[a])))
                for k in range(a, b):
                    path.lineTo(to_screen(float(s.distance[k]),
                                          float(top[k])))
                for k in reversed(range(a, b)):
                    path.lineTo(to_screen(float(s.distance[k]),
                                          float(bottom[k])))
                path.closeSubpath()
                painter.fillPath(path, QColor(*color))
        # Рельеф линией поверх пластов.
        painter.setPen(QPen(QColor(60, 40, 20), 1.5))
        line = QPainterPath(to_screen(float(s.distance[0]),
                                      float(s.ground[0])))
        for d, z in zip(s.distance[1:], s.ground[1:]):
            line.lineTo(to_screen(float(d), float(z)))
        painter.drawPath(line)
        # Стволы - куски цвета интервала с тёмной обводкой.
        for _, pieces in s.holes:
            for d, z, color in pieces:
                if len(d) < 2:
                    continue
                path = QPainterPath(to_screen(float(d[0]), float(z[0])))
                for a, b in zip(d[1:], z[1:]):
                    path.lineTo(to_screen(float(a), float(b)))
                painter.setPen(QPen(QColor(30, 30, 30), 5.0))
                painter.drawPath(path)
                painter.setPen(QPen(QColor(*color), 3.0))
                painter.drawPath(path)
        # Тоннель - своим диаметром в масштабе графика, не тоньше 4 px.
        per_metre = rect.height() / max(high - low, 1e-9)
        for name, d, z, color in s.tunnels:
            path = QPainterPath(to_screen(float(d[0]), float(z[0])))
            for a, b in zip(d[1:], z[1:]):
                path.lineTo(to_screen(float(a), float(b)))
            painter.setPen(QPen(QColor(*color),
                                max(4.0, s.diameters.get(name, 0.0)
                                    * per_metre)))
            painter.drawPath(path)
        text = QPen(self.palette().text().color())
        painter.setPen(text)
        for name, pieces in s.holes:
            if pieces and len(pieces[0][0]):
                head = to_screen(float(pieces[0][0][0]),
                                 float(pieces[0][1][0]))
                painter.drawText(QRectF(head.x() - 40, head.y() - 18, 80,
                                        16), CENTER, name)
        grid = QPen(GRID, 1.0)
        step = nice_step(high - low, 6)
        z = np.ceil(low / step) * step
        while z <= high + 1e-9:
            point = to_screen(0.0, z)
            painter.setPen(grid)
            painter.drawLine(QPointF(rect.left(), point.y()),
                             QPointF(rect.right(), point.y()))
            painter.setPen(text)
            painter.drawText(QRectF(0, point.y() - 8, MARGIN[0] - 6, 16),
                             RIGHT, metres_text(z))
            z += step
        step = nice_step(x1, 6)
        d = 0.0
        while d <= x1 + 1e-9:
            point = to_screen(d, low)
            painter.setPen(grid)
            painter.drawLine(QPointF(point.x(), rect.top()),
                             QPointF(point.x(), rect.bottom()))
            painter.setPen(text)
            painter.drawText(QRectF(point.x() - 40, rect.bottom() + 4, 80,
                                    16), CENTER, axis_text(d, step))
            d += step
        if self.hover is not None:
            i = self.hover
            top = to_screen(float(s.distance[i]), high)
            painter.setPen(QPen(QColor(220, 60, 40), 1.2))
            painter.drawLine(QPointF(top.x(), rect.top()),
                             QPointF(top.x(), rect.bottom()))
            painter.setPen(text)
            painter.drawText(QRectF(rect.left() + 6, rect.top() + 2,
                                    rect.width() - 12, 16), LEFT,
                             self._hover_text(i))

    def _hover_text(self, i):
        s = self.section
        parts = [distance_text(float(s.distance[i])),
                 tr("рельеф {value}", value=metres_text(float(s.ground[i])))]
        for code, _, top, bottom in s.beds[1:]:
            if np.isfinite(top[i]) and top[i] > bottom[i] and code:
                parts.append("{} {}".format(code, metres_text(
                    float(top[i]))))
                break
        return ", ".join(parts)

    def mouseMoveEvent(self, event):
        s = self.section
        if s is None:
            return
        pos = event.position() if hasattr(event, "position") else event.pos()
        rect = self._plot()
        share = (pos.x() - rect.left()) / rect.width()
        if not 0.0 <= share <= 1.0:
            self.leaveEvent(event)
            return
        i = int(np.clip(np.searchsorted(s.distance,
                                        share * float(s.distance[-1])),
                        0, len(s.distance) - 1))
        if i != self.hover:
            self.hover = i
            self.update()
            self.hovered.emit(i)

    def leaveEvent(self, event):
        if self.hover is not None:
            self.hover = None
            self.update()
            self.hovered.emit(-1)


class ModelSectionDialog(QDialog):
    """Окно «Разрез модели». provider(band) даёт ModelSection или None.
    Сигнал point_hovered - (широта, долгота, м вдоль линии) или None."""

    point_hovered = pyqtSignal(object)

    def __init__(self, title, provider, parent=None):
        super().__init__(parent)
        self.setModal(False)
        self.provider = provider
        self.band = QDoubleSpinBox(self)
        self.band.setRange(10.0, 5000.0)
        self.band.setDecimals(0)
        self.band.setSingleStep(50.0)
        self.band.setSuffix(" " + tr("м"))
        self.band.setValue(BAND)
        self.band.setKeyboardTracking(False)
        self.band.setToolTip(tr(
            "Ширина полосы вдоль линии, из которой скважины и тоннели "
            "переносятся на разрез. Шире полоса - больше скважин, но "
            "дальние лежат не там, где линия."))
        self.band.valueChanged.connect(self.refresh)
        form = QFormLayout()
        form.addRow(tr("Полоса скважин и тоннелей"), self.band)
        self.chart = ModelChart(self)
        self.chart.hovered.connect(self._hovered)
        self.stats = QLabel(self)
        self.stats.setWordWrap(True)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.chart, 1)
        layout.addWidget(self.stats)
        self.set_source(title, provider)
        self.resize(900, 460)

    def set_source(self, title, provider):
        self.setWindowTitle(tr("Разрез модели: {name}", name=title)
                            if title else tr("Разрез модели"))
        self.provider = provider
        self.refresh()

    def refresh(self, *args):
        found = self.provider(float(self.band.value()))
        self.chart.set_section(found)
        if found is None:
            self.stats.setText(tr("Нужны подземная модель и путь хотя бы "
                                  "из двух точек."))
            return
        self.stats.setText(tr(
            "Длина {length}. Скважин в полосе {holes}, тоннелей "
            "{tunnels}.", length=distance_text(float(found.distance[-1])),
            holes=len(found.holes), tunnels=len(found.tunnels)))

    def _hovered(self, index):
        s = self.chart.section
        if index < 0 or s is None:
            self.point_hovered.emit(None)
            return
        self.point_hovered.emit((float(s.lats[index]), float(s.lons[index]),
                                 float(s.distance[index])))
