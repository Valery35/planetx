# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Разрез модели»: подземная модель вниз вдоль пути.

Просьба автора от 4 октября 2026 года. Окно «Разрез» (ui/section.py)
режет Землю на сотни километров, это окно - модель подземного режима
на сотни метров: рельеф, пласты между кровлями, стволы скважин
и тоннели из полосы вдоль линии. Расстояния и отметки - в метрах.
Курсор над графиком отмечает точку на глобусе.

Геологический разрез по слоям проекта - выбор автора от 17 октября
2026 года. Слои разреза выбираются флажками в самом окне - любые
одноканальные растры проекта как кровли, скважины, слои с Z (стенки
«3D-забора» Isoliner3D и линии с отметками в полосе вдоль линии) -
без пункта «Поверхность по отметкам» и без подземной модели на глобусе
(ui.subsurface.section_layers, section_model). Разрез пишется картинкой
PNG и таблицей CSV отметок по точкам линии.
"""
import csv
import os
from collections import namedtuple

import numpy as np
from qgis.PyQt.QtCore import QPointF, QRectF, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor, QPainter, QPainterPath, QPen
from qgis.PyQt.QtWidgets import (QColorDialog, QDialog, QDoubleSpinBox,
                                 QFileDialog, QFormLayout, QHBoxLayout,
                                 QLabel, QListWidget, QListWidgetItem,
                                 QMenu, QPushButton, QSplitter, QVBoxLayout,
                                 QWidget)

from ..core import drillholes, ellipsoid, section
from ..core import subsurface as core
from ..i18n import tr
from ..qt_compat import enum
from .elevation import axis_text, distance_text, nice_step
from .project import read_section_colors, write_section_colors
from .subsurface import HOST_COLOR

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
LAYER_ROLE = enum(Qt, "ItemDataRole", "UserRole")
CHECKED = enum(Qt, "CheckState", "Checked")
UNCHECKED = enum(Qt, "CheckState", "Unchecked")
HOLES = "holes"  # данные строки «Скважины» списка слоёв
HOVER_BEDS = 4  # кровель в подписи под курсором
LEGEND_ROWS = 12  # строк подписи цветов, не больше
LINE_WIDTH = 1.6  # пикселей, линии кровель и подошв
LINE_PICK = 6.0  # пикселей, линия под курсором для меню цвета

ModelSection = namedtuple(
    "ModelSection",
    "distance lats lons ground beds bottom holes tunnels diameters fences "
    "owners lines", defaults=((), (), ()))
ModelSection.__doc__ = """Разрез модели. distance - м от начала линии,
lats, lons - точки линии, ground - отметки рельефа, beds - [(код, цвет,
верх, низ)] отметки промежутков по точкам, owners - ключ своего цвета
каждого промежутка (код пласта или core.HOST - порода между пластами),
lines - [(код, цвет, отметки)] кровель и подошв, bottom - отметка низа модели,
holes - [(название, [(расстояния, отметки, цвет)])] куски стволов по
интервалам, tunnels - [(название, расстояния, отметки, цвет)],
diameters - диаметр тоннеля по названию, м, fences - [(слой,
расстояния, отметки, RGBA, вид)] частей объектов с Z в полосе."""


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
    fills = core.section_fills(codes, model.color, HOST_COLOR)
    beds = [(code, color, stack[k], stack[k + 1])
            for k, (code, (_, color)) in enumerate(zip(codes, fills))]
    owners = [key for key, _ in fills]
    # Линии кровель и подошв - по поверхностям под рельефом.
    lines = [(code, core.line_color(model.color(code)), stack[k])
             for k, code in enumerate(codes) if k > 0]
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
    fences = []
    for shape in model.zshapes:
        for part in shape.parts:
            found = core.fence_part(part, lats, lons, distance, band)
            if found is not None:
                fences.append((shape.layer, found[0], found[1], shape.color,
                               shape.kind))
    return ModelSection(distance, lats, lons, g, beds, bottom, holes,
                        tunnels, diameters, fences, owners, lines)


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
    # Свои цвета изменились: {ключ: {"fill" или "line": (r, g, b)}}.
    colors_changed = pyqtSignal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.section = None
        self.hover = None
        # Свои цвета пользователя: ключ - код пласта или core.HOST.
        self.own = {}
        self.setMouseTracking(True)
        self.setMinimumSize(480, 260)

    def set_section(self, value):
        self.section = value
        self.hover = None
        self.update()

    def owner(self, k):
        """Ключ своего цвета промежутка k."""
        owners = self.section.owners
        return owners[k] if k < len(owners) else self.section.beds[k][0]

    def fill_of(self, k):
        """Заливка промежутка k - своя или по умолчанию."""
        own = self.own.get(self.owner(k), {}).get("fill")
        return own or self.section.beds[k][1]

    def line_of(self, code):
        """Цвет линии кровли или подошвы code - свой или по умолчанию."""
        own = self.own.get(code, {}).get("line")
        if own:
            return own
        for name, color, _ in self.section.lines:
            if name == code:
                return color
        return (40, 40, 40)

    def _at(self, pos):
        """Промежуток и ближайшая поверхность под точкой графика:
        (номер промежутка или None, код линии или None)."""
        s = self.section
        rect, x1, high, low, _ = self._mapper()
        share = (pos.x() - rect.left()) / rect.width()
        if not 0.0 <= share <= 1.0 or not len(s.beds):
            return None, None
        i = int(np.clip(np.searchsorted(s.distance, share * x1), 0,
                        len(s.distance) - 1))
        z = high - (pos.y() - rect.top()) / rect.height() * (high - low)
        found = None
        for k, (_, _, top, bottom) in enumerate(s.beds):
            if np.isfinite(top[i]) and bottom[i] <= z <= top[i] \
                    and top[i] > bottom[i]:
                found = k
        near = None
        best = LINE_PICK / rect.height() * (high - low)
        for code, _, zs in s.lines:
            if np.isfinite(zs[i]) and abs(zs[i] - z) <= best:
                near, best = code, abs(zs[i] - z)
        return found, near

    def contextMenuEvent(self, event):
        """Правая кнопка: цвет пласта, породы между пластами или линии
        под курсором, сброс своих цветов. Просьба автора от 17 октября
        2026 года - цвета пластов и промежутков между ними задаются."""
        if self.section is None:
            return
        k, line = self._at(event.pos())
        menu = QMenu(self)
        if k is not None:
            key = self.owner(k)
            if key == core.HOST:
                text = tr("Цвет породы между пластами…")
            else:
                text = tr("Цвет пласта «{name}»…",
                          name=core.bed_key(key)[0] or key)
            menu.addAction(text).triggered.connect(
                lambda _=False, key=key, k=k: self._pick(
                    key, "fill", self.fill_of(k)))
        if line is not None:
            menu.addAction(tr("Цвет линии «{name}»…", name=line)) \
                .triggered.connect(lambda _=False, line=line: self._pick(
                    line, "line", self.line_of(line)))
        if self.own:
            menu.addSeparator()
            menu.addAction(tr("Цвета разреза по умолчанию")) \
                .triggered.connect(self.reset_colors)
        if not menu.isEmpty():
            menu.exec(event.globalPos())

    def _pick(self, key, part, current):
        color = QColorDialog.getColor(QColor(*current[:3]), self,
                                      tr("Цвет на разрезе"))
        if color.isValid():
            self.set_color(key, part, (color.red(), color.green(),
                                       color.blue()))

    def set_color(self, key, part, rgb):
        """Свой цвет part ("fill" или "line") для ключа key."""
        self.own.setdefault(key, {})[part] = tuple(int(c) for c in rgb)
        self.update()
        self.colors_changed.emit(self.own)

    def reset_colors(self):
        self.own = {}
        self.update()
        self.colors_changed.emit(self.own)

    def _plot(self):
        left, top, right, bottom = MARGIN
        return QRectF(left, top, max(1.0, self.width() - left - right),
                      max(1.0, self.height() - top - bottom))

    def _range(self):
        s = self.section
        high = float(np.nanmax(s.ground))
        low = float(s.bottom)
        for _, _, z, _, _ in s.fences:
            # Стенки забора тоже входят в график.
            high = max(high, float(np.nanmax(z)))
            low = min(low, float(np.nanmin(z)))
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
        for k, (code, color, top, bottom) in enumerate(s.beds):
            color = self.fill_of(k)
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
        # Стенки забора и линии с отметками - цветом объекта.
        for _, d, z, color, kind in s.fences:
            path = QPainterPath(to_screen(float(d[0]), float(z[0])))
            for a, b in zip(d[1:], z[1:]):
                path.lineTo(to_screen(float(a), float(b)))
            # Цвет объекта - RGBA 0-255, альфа - непрозрачность слоя.
            rgba = QColor(*[int(c) for c in color[:4]])
            if kind == "polygon":
                path.closeSubpath()
                painter.fillPath(path, rgba)
                painter.setPen(QPen(rgba.darker(150), 0.8))
            else:
                painter.setPen(QPen(rgba, 2.0))
            painter.drawPath(path)
        # Кровли и подошвы - линиями своего цвета, пласт отделён от
        # породы между пластами.
        for code, _, z in s.lines:
            painter.setPen(QPen(QColor(*self.line_of(code)), LINE_WIDTH))
            for a, b in _runs(np.isfinite(z)):
                if b - a < 2:
                    continue
                path = QPainterPath(to_screen(float(s.distance[a]),
                                              float(z[a])))
                for k in range(a + 1, b):
                    path.lineTo(to_screen(float(s.distance[k]),
                                          float(z[k])))
                painter.drawPath(path)
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
        self._legend(painter, rect, text)
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

    def _legend(self, painter, rect, text):
        """Подписи цветов в правом верхнем углу графика: пласты по
        коду, у растров без таблицы пластов - по названию кровли,
        слои с Z по названию слоя."""
        s = self.section
        rows = []
        seen = set()
        for k, (code, _, top, bottom) in enumerate(s.beds):
            key = self.owner(k)
            if key == core.HOST:
                name = tr("Между пластами")
            elif code:
                name = core.bed_key(code)[0] or code
            else:
                continue
            if name not in seen and np.any(top > bottom):
                seen.add(name)
                rows.append((name, self.fill_of(k)))
        for name, _, _, color, _ in s.fences:
            if name not in seen:
                seen.add(name)
                rows.append((name, color[:3]))
        if not rows:
            return
        rows = rows[:LEGEND_ROWS]
        metrics = painter.fontMetrics()
        line = metrics.height() + 2
        width = max(metrics.horizontalAdvance(name)
                    if hasattr(metrics, "horizontalAdvance")
                    else metrics.width(name) for name, _ in rows) + 30
        box = QRectF(rect.right() - width - 6, rect.top() + 22, width,
                     line * len(rows) + 6)
        painter.fillRect(box, QColor(255, 255, 255, 200))
        for k, (name, color) in enumerate(rows):
            y = box.top() + 3 + k * line
            painter.fillRect(QRectF(box.left() + 5, y + 2, 16, line - 5),
                             QColor(*[int(c) for c in color[:3]]))
            painter.setPen(QPen(QColor(30, 30, 30)))
            painter.drawText(QRectF(box.left() + 26, y, width - 28, line),
                             LEFT, name)
        painter.setPen(text)

    def _hover_text(self, i):
        s = self.section
        parts = [distance_text(float(s.distance[i])),
                 tr("рельеф {value}", value=metres_text(float(s.ground[i])))]
        shown = 0
        for code, _, top, bottom in s.beds[1:]:
            if np.isfinite(top[i]) and top[i] > bottom[i] and code \
                    and shown < HOVER_BEDS:
                parts.append("{} {}".format(code, metres_text(
                    float(top[i]))))
                shown += 1
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
    """Окно «Разрез модели». provider(band, choice) даёт ModelSection
    или None, choice - отметки списка слоёв (растры, скважины, слои
    с Z). layers - (растры, есть ли скважины, слои с Z, отметки по
    умолчанию) из ui.subsurface.section_layers и section_defaults.
    Сигнал point_hovered - (широта, долгота, м вдоль линии) или None."""

    point_hovered = pyqtSignal(object)

    def __init__(self, title, provider, parent=None, layers=None):
        super().__init__(parent)
        self.setModal(False)
        self.provider = provider
        self.title = title
        self.band = QDoubleSpinBox(self)
        self.band.setRange(10.0, 5000.0)
        self.band.setDecimals(0)
        self.band.setSingleStep(50.0)
        self.band.setSuffix(" " + tr("м"))
        self.band.setValue(BAND)
        self.band.setKeyboardTracking(False)
        self.band.setToolTip(tr(
            "Ширина полосы вдоль линии, из которой скважины, тоннели "
            "и объекты с Z переносятся на разрез. Шире полоса - больше "
            "скважин, но дальние лежат не там, где линия."))
        self.band.valueChanged.connect(self.refresh)
        form = QFormLayout()
        form.addRow(tr("Полоса скважин и объектов"), self.band)
        self.layers = QListWidget(self)
        self.layers.setToolTip(tr(
            "Слои проекта на разрезе. Растры - кровли пластов, сверху "
            "вниз по порядку таблицы пластов или по средней отметке. "
            "Скважины - устья с интервалами и инклинометрией. Слои с Z - "
            "стенки «3D-забора» и линии с отметками в полосе вдоль "
            "линии."))
        self.layers.itemChanged.connect(lambda *_: self.refresh())
        self.chart = ModelChart(self)
        self.chart.hovered.connect(self._hovered)
        # Свои цвета пластов, породы между ними и линий живут в проекте.
        self.chart.own = read_section_colors()
        self.chart.colors_changed.connect(write_section_colors)
        self.chart.setToolTip(tr(
            "Правая кнопка по пласту, породе между пластами или линии "
            "кровли задаёт их цвет. Цвета запоминаются в проекте QGIS."))
        self.stats = QLabel(self)
        self.stats.setWordWrap(True)
        picture = QPushButton(tr("Картинка…"), self)
        picture.setToolTip(tr("Разрез картинкой PNG в размере окна."))
        picture.clicked.connect(lambda _=False: self.save_picture())
        table = QPushButton(tr("Таблица CSV…"), self)
        table.setToolTip(tr(
            "Отметки по точкам линии - расстояние, широта, долгота, рельеф "
            "и кровли пластов, нет кровли - пустое поле."))
        table.clicked.connect(lambda _=False: self.save_table())
        buttons = QHBoxLayout()
        buttons.addWidget(self.stats, 1)
        buttons.addWidget(picture)
        buttons.addWidget(table)
        right = QWidget(self)
        column = QVBoxLayout(right)
        column.setContentsMargins(0, 0, 0, 0)
        column.addLayout(form)
        column.addWidget(self.chart, 1)
        split = QSplitter(self)
        split.addWidget(self.layers)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        split.setSizes([220, 760])
        layout = QVBoxLayout(self)
        layout.addWidget(split, 1)
        layout.addLayout(buttons)
        self.set_source(title, provider, layers)
        self.resize(1000, 480)

    def set_source(self, title, provider, layers=None):
        self.title = title
        self.setWindowTitle(tr("Разрез модели: {name}", name=title)
                            if title else tr("Разрез модели"))
        self.provider = provider
        self.chart.own = read_section_colors()
        if layers is not None:
            self._fill_layers(*layers)
        self.refresh()

    def _fill_layers(self, rasters, holes, zlayers, defaults):
        """Строки списка слоёв с флажками по defaults - (растры,
        скважины ли, слои с Z)."""
        on_rasters, on_holes, on_z = defaults
        self.layers.blockSignals(True)
        self.layers.clear()

        def heading(text):
            item = QListWidgetItem(text)
            font = item.font()
            font.setBold(True)
            item.setFont(font)
            item.setFlags(enum(Qt, "ItemFlag", "NoItemFlags"))
            self.layers.addItem(item)

        def row(text, data, on):
            item = QListWidgetItem(text)
            item.setData(LAYER_ROLE, data)
            item.setFlags(item.flags()
                          | enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
            item.setCheckState(CHECKED if on else UNCHECKED)
            self.layers.addItem(item)
        if rasters:
            heading(tr("Кровли - растры"))
            for layer_id, name in rasters:
                row(name, ("raster", layer_id), layer_id in on_rasters)
        if holes:
            heading(tr("Скважины"))
            row(tr("Скважины проекта"), (HOLES, ""), on_holes)
        if zlayers:
            heading(tr("Слои с Z"))
            for layer_id, name in zlayers:
                row(name, ("z", layer_id), layer_id in on_z)
        if not (rasters or holes or zlayers):
            heading(tr("В проекте нет растров, скважин и слоёв с Z"))
        self.layers.blockSignals(False)

    def choice(self):
        """Отмеченные слои: (номера растров по порядку списка, скважины
        ли, номера слоёв с Z)."""
        rasters, zlayers, holes = [], [], False
        for n in range(self.layers.count()):
            item = self.layers.item(n)
            data = item.data(LAYER_ROLE)
            if not data or item.checkState() != CHECKED:
                continue
            kind, layer_id = data
            if kind == "raster":
                rasters.append(layer_id)
            elif kind == "z":
                zlayers.append(layer_id)
            elif kind == HOLES:
                holes = True
        return tuple(rasters), holes, tuple(zlayers)

    def refresh(self, *args):
        found = self.provider(float(self.band.value()), self.choice())
        self.chart.set_section(found)
        if found is None:
            self.stats.setText(tr(
                "Нужны путь хотя бы из двух точек и слой разреза - растр "
                "кровли, скважины или слой с Z."))
            return
        self.stats.setText(tr(
            "Длина {length}. Кровель {beds}, скважин в полосе {holes}, "
            "тоннелей {tunnels}, частей объектов с Z {fences}.",
            length=distance_text(float(found.distance[-1])),
            beds=max(len(found.beds) - 1, 0), holes=len(found.holes),
            tunnels=len(found.tunnels), fences=len(found.fences)))

    def _file_name(self, ext):
        name = "".join(c if c.isalnum() or c in "-_" else "_"
                       for c in (self.title or "section"))
        return "{}{}".format(name or "section", ext)

    def save_picture(self, path=None):
        """Разрез картинкой PNG: путь или None, если не записан."""
        if self.chart.section is None:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Разрез картинкой"), self._file_name(".png"),
                "PNG (*.png)")
        if not path:
            return None
        if not self.chart.grab().save(path, "PNG"):
            self.stats.setText(tr("Файл не записан: {error}", error=path))
            return None
        return path

    def save_table(self, path=None):
        """Отметки разреза таблицей CSV: путь или None."""
        s = self.chart.section
        if s is None:
            return None
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Разрез таблицей"), self._file_name(".csv"),
                "CSV (*.csv)")
        if not path:
            return None
        names = [code or "top" for code, _, _, _ in s.beds[1:]]
        try:
            with open(path, "w", encoding="utf-8", newline="") as fh:
                out = csv.writer(fh)
                out.writerow(["distance_m", "lat", "lon", "ground_m"]
                             + names)
                for i in range(len(s.distance)):
                    tops = []
                    for _, _, top, bottom in s.beds[1:]:
                        ok = np.isfinite(top[i]) and top[i] > bottom[i]
                        tops.append("{:.2f}".format(float(top[i]))
                                    if ok else "")
                    out.writerow(["{:.1f}".format(float(s.distance[i])),
                                  "{:.7f}".format(float(s.lats[i])),
                                  "{:.7f}".format(float(s.lons[i])),
                                  "{:.2f}".format(float(s.ground[i]))]
                                 + tops)
        except OSError as error:
            self.stats.setText(tr("Файл не записан: {error}",
                                  error=str(error)))
            return None
        return os.path.abspath(path)

    def _hovered(self, index):
        s = self.chart.section
        if index < 0 or s is None:
            self.point_hovered.emit(None)
            return
        self.point_hovered.emit((float(s.lats[index]), float(s.lons[index]),
                                 float(s.distance[index])))