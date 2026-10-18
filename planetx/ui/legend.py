# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шкалы в углу вида: температура суши и моря в градусах Цельсия,
уклон и экспозиция поверхности (core/slope.py), часы прямого солнца
(core/insolation.py), глубина очагов землетрясений (core/quakes.py),
оболочки разреза Земли (core/cutaway.py), пласты подземной модели,
темы NASA. Все шкалы стоят одной панелью LegendPanel.

Цвета и подписи берутся из core/temperature.py. Виджет рисует себя
сам, фон полупрозрачный, как у подписи источников.
"""
import math

from qgis.PyQt.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from qgis.PyQt.QtGui import (QColor, QFontMetrics, QLinearGradient, QPainter,
                             QPen)
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget

from ..core import (contours, cutaway, deposits, faults, fields, fires, flow,
                    infra, insolation, plants, quakes, slope, temperature,
                    tomography, volcanoes)
from ..i18n import tr
from ..qt_compat import enum
from .style import ACCENT, HOVER, MUTED, PLATE, TEXT as STYLE_TEXT

BAR_WIDTH = 180  # длина полосы шкалы, логических пикселей
BAR_HEIGHT = 9
PAD = 6
# Плашка и текст - общий вид элементов поверх глобуса, ui/style.py.
BACKGROUND = PLATE
TEXT = STYLE_TEXT
CLOSE = 14  # сторона крестика шкалы карты, логических пикселей


class Closable:
    """Крестик в правом верхнем углу шкалы карты витрины: щелчок по нему
    убирает карту с глобуса. Решение автора от 7 октября 2026 года -
    кнопка «Выключить» витрины далеко от карты. closer ставит окно,
    без него крестика нет. Прочие щелчки уходят виду под шкалой."""

    closer = None

    def _close_rect(self):
        return QRectF(self.width() - CLOSE - 3, 3, CLOSE, CLOSE)

    def _paint_close(self, painter):
        if self.closer is None:
            return
        rect = self._close_rect()
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(HOVER)
        painter.drawEllipse(rect)
        painter.setPen(TEXT)
        painter.drawText(rect, int(enum(Qt, "AlignmentFlag", "AlignCenter")),
                         "✕")

    def mousePressEvent(self, event):
        point = event.position() if hasattr(event, "position") \
            else event.pos()
        if self.closer is not None and self._close_rect().contains(
                QPointF(point.x(), point.y())):
            event.accept()
            self.closer()
            return
        event.ignore()


class TemperatureLegend(Closable, QWidget):
    """Две шкалы: суша и море."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = ((tr("Суша, °C"), temperature.LAND_STOPS,
                      temperature.LAND_TICKS),
                     (tr("Море, °C"), temperature.SEA_STOPS,
                      temperature.SEA_TICKS))
        line = QFontMetrics(self.font()).height()
        self.row_height = line * 2 + BAR_HEIGHT + 2
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          len(self.rows) * self.row_height + PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        for n, (title, stops, ticks) in enumerate(self.rows):
            top = PAD // 2 + n * self.row_height
            painter.setPen(TEXT)
            painter.drawText(PAD, top + metrics.ascent(), title)
            bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
            gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
            for value, rgb in stops:
                gradient.setColorAt(temperature.share(stops, value),
                                    QColor(*rgb))
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(gradient)
            painter.drawRect(bar)
            painter.setPen(TEXT)
            for tick in ticks:
                x = bar.left() + temperature.share(stops, tick) * BAR_WIDTH
                painter.drawLine(int(x), int(bar.bottom()), int(x),
                                 int(bar.bottom()) + 2)
                text = "{:+d}".format(tick) if tick else "0"
                width = metrics.horizontalAdvance(text)
                painter.drawText(int(x - width / 2),
                                 int(bar.bottom()) + 2 + metrics.ascent(),
                                 text)
        self._paint_close(painter)
        painter.end()


def field_titles():
    """Заголовки шкал карт значений (core/fields.py) по ключам."""
    return {"emag": tr("Магнитная аномалия, нТл"),
            "seafloor_age": tr("Возраст океанического дна, млн лет"),
            "gravity": tr("Аномалия силы тяжести, мГал"),
            "bouguer": tr("Аномалия Буге, мГал"),
            "heatflow": tr("Тепловой поток, мВт/м²"),
            "water_occurrence": tr("Повторяемость воды 1984-2021, %"),
            "soil_clay": tr("Глина в почве 0-5 см, %"),
            "soil_sand": tr("Песок в почве 0-5 см, %"),
            "soil_soc": tr("Органический углерод почвы 0-5 см, г/кг"),
            "soil_ph": tr("Кислотность почвы 0-5 см, pH в воде")}


def class_titles():
    """Заголовки шкал карт классами (core/tilemaps.py)."""
    return {"glim": tr("Литология GLiM"),
            "water_transitions": tr("Изменения воды 1984-2021 JRC"),
            "worldcover": tr("Покрытие земель ESA WorldCover 2021")}

def class_names():
    """Названия классов карт core/tilemaps.py по кодам."""
    return {
        # Литология GLiM, первый уровень классификации.
        "su": tr("Рыхлые отложения"),
        "ss": tr("Обломочные осадочные породы"),
        "sm": tr("Смешанные осадочные породы"),
        "sc": tr("Карбонатные осадочные породы"),
        "ev": tr("Эвапориты"),
        "py": tr("Пирокластика"),
        "va": tr("Кислые вулканические породы"),
        "vi": tr("Средние вулканические породы"),
        "vb": tr("Основные вулканические породы"),
        "pa": tr("Кислые плутонические породы"),
        "pi": tr("Средние плутонические породы"),
        "pb": tr("Основные плутонические породы"),
        "mt": tr("Метаморфические породы"),
        "ig": tr("Лёд и ледники"),
        # Переходы воды JRC.
        "permanent": tr("Постоянная вода"),
        "new_permanent": tr("Новая постоянная вода"),
        "lost_permanent": tr("Исчезнувшая постоянная вода"),
        "seasonal": tr("Сезонная вода"),
        "new_seasonal": tr("Новая сезонная вода"),
        "lost_seasonal": tr("Исчезнувшая сезонная вода"),
        "seasonal_to_permanent": tr("Сезонная стала постоянной"),
        "permanent_to_seasonal": tr("Постоянная стала сезонной"),
        "ephemeral_permanent": tr("Временная постоянная вода"),
        "ephemeral_seasonal": tr("Временная сезонная вода"),
        # Покрытие земель ESA WorldCover.
        "tree": tr("Лес"),
        "shrub": tr("Кустарник"),
        "grass": tr("Луга"),
        "crop": tr("Пашня"),
        "built": tr("Застройка"),
        "bare": tr("Голые и редкие земли"),
        "snow": tr("Снег и лёд"),
        "water": tr("Постоянные водоёмы"),
        "wetland": tr("Травяные болота"),
        "mangrove": tr("Мангры"),
        "moss": tr("Мхи и лишайники")}


class FieldLegend(Closable, QWidget):
    """Шкала карты значений геофизики (core/fields.py) - магнитных
    аномалий, возраста дна, силы тяжести, теплового потока."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.field = fields.FIELDS["emag"]
        self.title = ""
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)

    def set_field(self, field):
        self.field = field
        self.title = field_titles().get(field.key, field.key)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), self.title)
        bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
        stops = self.field.stops
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for value, rgb in stops:
            gradient.setColorAt(temperature.share(stops, value),
                                QColor(*rgb))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(gradient)
        painter.drawRect(bar)
        painter.setPen(TEXT)
        signed = stops[0][0] < 0
        for tick in self.field.ticks:
            x = bar.left() + temperature.share(stops, tick) * BAR_WIDTH
            painter.drawLine(int(x), int(bar.bottom()), int(x),
                             int(bar.bottom()) + 2)
            text = "{:+g}".format(tick) if tick and signed \
                else "{:g}".format(tick)
            width = metrics.horizontalAdvance(text)
            painter.drawText(int(x - width / 2),
                             int(bar.bottom()) + 2 + metrics.ascent(), text)
        self._paint_close(painter)
        painter.end()


class ContourLegend(Closable, QWidget):
    """Шкала горизонталей: цвет линии, сечение в середине вида, шаг
    утолщённых и ссылка «В проект QGIS…» - выгрузка горизонталей вида.
    Крестик выключает горизонтали. Просьба автора от 9 октября 2026
    года - выгрузку из меню на глобусе было не найти."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.step = 0.0
        self.index = 0.0
        self.color = QColor(*contours.LAND)
        self.export = None  # окно ставит выгрузку
        metrics = QFontMetrics(self.font())
        self.line = metrics.height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8, 3 * self.line + PAD + 2)
        self.setCursor(enum(Qt, "CursorShape", "ArrowCursor"))

    def set_step(self, step, palette):
        land, _, _, shade = contours.PALETTES[palette]
        color = QColor(*(int(c * shade) for c in land))
        if step == self.step and color == self.color:
            return
        self.step = step
        self.index = contours.index_step(step)
        self.color = color
        metrics = QFontMetrics(self.font())
        text = tr("через {step} м, утолщённые через {index} м",
                  step=contours.label_text(step),
                  index=contours.label_text(self.index))
        self.setFixedWidth(max(BAR_WIDTH + 2 * PAD + 8,
                               PAD + 30 + metrics.horizontalAdvance(text)
                               + PAD + CLOSE))
        self.update()

    def _link_rect(self):
        top = PAD // 2 + 2 * self.line
        return QRectF(PAD, top, BAR_WIDTH, self.line)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), tr("Горизонтали"))
        y = top + self.line + self.line // 2
        pen = painter.pen()
        pen.setColor(self.color)
        pen.setWidthF(2.0)
        painter.setPen(pen)
        painter.drawLine(PAD, y, PAD + 24, y)
        painter.setPen(TEXT)
        painter.drawText(PAD + 30, top + self.line + metrics.ascent(), tr(
            "через {step} м, утолщённые через {index} м",
            step=contours.label_text(self.step),
            index=contours.label_text(self.index)))
        if self.export is not None:
            font = painter.font()
            font.setUnderline(True)
            painter.setFont(font)
            painter.setPen(ACCENT)
            rect = self._link_rect()
            painter.drawText(int(rect.left()),
                             int(rect.top()) + metrics.ascent(),
                             tr("В проект QGIS…"))
        self._paint_close(painter)
        painter.end()

    def mousePressEvent(self, event):
        point = event.position() if hasattr(event, "position") \
            else event.pos()
        width = QFontMetrics(self.font()).horizontalAdvance(
            tr("В проект QGIS…"))
        link = self._link_rect()
        link.setWidth(width)
        if self.export is not None and link.contains(
                QPointF(point.x(), point.y())):
            event.accept()
            self.export()
            return
        super().mousePressEvent(event)


class InsolationLegend(QWidget):
    """Шкала инсоляции - часы прямого света в сутки от 0 до top."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)
        self.top = 1.0

    def set_top(self, top):
        self.top = float(top)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(),
                         tr("Прямое солнце, ч в сутки"))
        bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for share, rgb in insolation.STOPS:
            gradient.setColorAt(share, QColor(*rgb))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(gradient)
        painter.drawRect(bar)
        painter.setPen(TEXT)
        for share in (0.0, 0.5, 1.0):
            x = bar.left() + share * BAR_WIDTH
            text = "{:g}".format(round(share * self.top, 1))
            width = metrics.horizontalAdvance(text)
            left = min(max(x - width / 2, 0.0), self.width() - width)
            painter.drawText(int(left),
                             int(bar.bottom()) + 2 + metrics.ascent(), text)
        painter.end()


class SlopeLegend(QWidget):
    """Шкала уклона - классы с границами в градусах, или экспозиции -
    цвета сторон света. mode - "slope" или "aspect"."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)
        self.mode = "slope"

    def set_mode(self, mode):
        self.mode = mode
        self.update()

    def _cells(self):
        """Клетки шкалы: (цвет, подпись под левым краем клетки)."""
        if self.mode == "aspect":
            names = (tr("С"), tr("СВ"), tr("В"), tr("ЮВ"), tr("Ю"),
                     tr("ЮЗ"), tr("З"), tr("СЗ"))
            return ([(slope.FLAT_COLOR, "")]
                    + [(rgb, name) for (_, rgb), name in
                       zip(slope.ASPECT_STOPS[:-1], names)])
        return [(rgb, "{:g}".format(low)) for low, rgb in slope.SLOPE_STOPS]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        title = tr("Экспозиция, ровное - серое") if self.mode == "aspect" \
            else tr("Уклон, °")
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), title)
        cells = self._cells()
        width = BAR_WIDTH / len(cells)
        y = top + line + 1
        for n, (rgb, label) in enumerate(cells):
            x = PAD + 4 + n * width
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(*rgb))
            painter.drawRect(QRectF(x, y, width, BAR_HEIGHT))
            if label:
                painter.setPen(TEXT)
                left = x if self.mode == "slope" \
                    else x + (width - metrics.horizontalAdvance(label)) / 2
                painter.drawText(int(left),
                                 int(y + BAR_HEIGHT) + 2 + metrics.ascent(),
                                 label)
        painter.end()


class QuakeLegend(QWidget):
    """Шкала глубины очагов землетрясений, км, цвета core.quakes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(),
                         tr("Глубина очага, км"))
        bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
        deepest = quakes.DEPTH_STOPS[-1][0]
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for depth, rgb in quakes.DEPTH_STOPS:
            gradient.setColorAt(depth / deepest, QColor(*rgb))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(gradient)
        painter.drawRect(bar)
        painter.setPen(TEXT)
        for depth in quakes.DEPTH_TICKS:
            x = bar.left() + depth / deepest * BAR_WIDTH
            text = "{:g}".format(depth)
            width = metrics.horizontalAdvance(text)
            left = min(max(x - width / 2, 0.0), self.width() - width)
            painter.drawText(int(left),
                             int(bar.bottom()) + 2 + metrics.ascent(), text)
        painter.end()


class FireLegend(Closable, QWidget):
    """Шкала мощности излучения очагов пожаров, МВт, логарифмическая,
    цвета core.fires."""

    def __init__(self, parent=None):
        super().__init__(parent)
        line = QFontMetrics(self.font()).height()
        self.setFixedSize(BAR_WIDTH + 2 * PAD + 8,
                          line * 2 + BAR_HEIGHT + 2 + PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(),
                         tr("Мощность пожара, МВт"))
        bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
        low = math.log10(fires.FRP_STOPS[0][0])
        high = math.log10(fires.FRP_STOPS[-1][0])
        gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
        for frp, rgb in fires.FRP_STOPS:
            gradient.setColorAt((math.log10(frp) - low) / (high - low),
                                QColor(*rgb))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(gradient)
        painter.drawRect(bar)
        painter.setPen(TEXT)
        for frp in fires.FRP_TICKS:
            x = bar.left() + (math.log10(frp) - low) / (high - low) \
                * BAR_WIDTH
            text = "{:g}".format(frp)
            width = metrics.horizontalAdvance(text)
            left = min(max(x - width / 2, 0.0), self.width() - width)
            painter.drawText(int(left),
                             int(bar.bottom()) + 2 + metrics.ascent(), text)
        self._paint_close(painter)
        painter.end()


def deposit_group_names():
    """Названия групп полезных ископаемых по core.deposits.GROUPS и
    прочих."""
    return {"precious": tr("Благородные металлы"),
            "base": tr("Цветные металлы"),
            "iron": tr("Чёрные и легирующие металлы"),
            "rare": tr("Редкие металлы, литий, алюминий"),
            "energy": tr("Уголь, уран, геотермальные"),
            "gems": tr("Алмазы и самоцветы"),
            "industrial": tr("Нерудные и строительные"),
            "other": tr("Прочие")}


def fuel_names():
    """Названия видов топлива электростанций по core.plants.FUELS."""
    return {"coal": tr("Уголь"), "gas": tr("Газ"), "oil": tr("Мазут"),
            "nuclear": tr("Атомные"), "hydro": tr("ГЭС"),
            "wind": tr("Ветер"), "solar": tr("Солнце"),
            "bio": tr("Биотопливо, отходы, геотермальные"),
            "other": tr("Прочие")}


def infra_names():
    """Названия классов ЛЭП и трубопроводов по core.infra."""
    return {"v500": tr("ЛЭП 500 кВ и выше"), "v220": tr("ЛЭП 220-330 кВ"),
            "v110": tr("ЛЭП 110-150 кВ"),
            "v35": tr("ЛЭП ниже 110 кВ и без напряжения"),
            "cable": tr("Силовой кабель"), "telecom": tr("Линия связи"),
            "gas": tr("Газопровод"), "oil": tr("Нефте- и продуктопровод"),
            "water": tr("Вода, тепло, стоки"),
            "other": tr("Трубопровод, вещество не указано")}


class _RowsLegend(Closable, QWidget):
    """Шкала строками: заголовок, кружки или отрезки цветов, подвал."""

    title = ""
    footer = ""

    def rows(self):
        """Строки (цвет, подпись, вид «dot» или «line», толщина)."""
        return []

    def __init__(self, parent=None):
        super().__init__(parent)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        texts = [self.title, self.footer] + [r[1] for r in self.rows()]
        width = max(_text_width(metrics, text) for text in texts if text)
        self.setFixedSize(max(BAR_WIDTH + 2 * PAD + 8,
                              width + PAD + 26 + PAD + 16),
                          line * (len(self.rows()) + 1
                                  + (1 if self.footer else 0)) + PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        y = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, y + metrics.ascent(), self.title)
        y += line
        for rgb, text, kind, width in self.rows():
            middle = y + line / 2
            if kind == "line":
                pen = QPen(QColor(*rgb), width)
                painter.setPen(pen)
                painter.drawLine(QPointF(PAD + 2, middle),
                                 QPointF(PAD + 20, middle))
            else:
                painter.setPen(QColor(*rgb).darker(250))
                painter.setBrush(QColor(*rgb))
                painter.drawEllipse(QPointF(PAD + 10, middle), 4.0, 4.0)
            painter.setPen(TEXT)
            painter.drawText(PAD + 26, y + metrics.ascent(), text)
            y += line
        if self.footer:
            painter.drawText(PAD, y + metrics.ascent(), self.footer)
        self._paint_close(painter)
        painter.end()


class PointCloudLegend(_RowsLegend):
    """Шкала облаков точек: классы ASPRS встреченных точек или высоты
    по цветам облака."""

    def __init__(self, parent=None):
        self._rows = []
        self.title = tr("Облако точек")
        super().__init__(parent)

    def rows(self):
        return self._rows

    def set_rows(self, title, rows, footer=""):
        """rows - [(цвет RGB, подпись)]."""
        self.title = title
        self.footer = footer
        self._rows = [(color, text, "dot", 0.0) for color, text in rows]
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        texts = [self.title, self.footer] + [r[1] for r in self._rows]
        width = max(_text_width(metrics, text) for text in texts if text)
        self.setFixedSize(max(BAR_WIDTH + 2 * PAD + 8,
                              width + PAD + 26 + PAD + 16),
                          line * (len(self._rows) + 1
                                  + (1 if footer else 0)) + PAD)
        self.update()


class PlantLegend(_RowsLegend):
    """Шкала электростанций: цвет - вид топлива, размер - мощность."""

    def __init__(self, parent=None):
        self.title = tr("Электростанции WRI")
        self.footer = tr("Размер точки - мощность")
        super().__init__(parent)

    def rows(self):
        names = fuel_names()
        return [(f[2], names[f[0]], "dot", 0.0) for f in plants.FUELS]


def period_names():
    """Время последнего извержения вулкана по core.volcanoes.PERIODS."""
    return {"recent": tr("Извергался с 1900 года"),
            "historic": tr("Извергался в 1500-1899 годах"),
            "holocene": tr("Извергался до 1500 года"),
            "unknown": tr("Дата извержения неизвестна")}


class VolcanoLegend(_RowsLegend):
    """Шкала вулканов: цвет - время последнего извержения."""

    def __init__(self, parent=None):
        self.title = tr("Вулканы голоцена GVP")
        self.footer = tr("Размер точки - высота вулкана")
        super().__init__(parent)

    def rows(self):
        names = period_names()
        return [(p[2], names[p[0]], "dot", 0.0) for p in volcanoes.PERIODS]


class CurrentLegend(_RowsLegend):
    """Шкала струек течений: цвет - скорость, м/с."""

    def __init__(self, parent=None):
        self.title = tr("Течения, м/с")
        self.footer = tr("Геострофические, по спутниковой альтиметрии")
        super().__init__(parent)

    def rows(self):
        return [(c, "{:g}".format(s), "line", 2.0)
                for s, c in flow.CURRENT_STOPS]


class InfraLegend(_RowsLegend):
    """Шкала ЛЭП и трубопроводов OSM: классы напряжения и вещества."""

    def __init__(self, parent=None):
        self.title = tr("ЛЭП, кабели и трубопроводы OSM")
        self.footer = tr("Квадрат - подстанция")
        super().__init__(parent)

    def rows(self):
        names = infra_names()
        return [(v[2], names[v[0]], "line", v[3]) for v in infra.VOLTAGES] \
            + [(c[1], names[c[0]], "line", c[2]) for c in infra.CABLES] \
            + [(s[2], names[s[0]], "line", infra.PIPE_WIDTH)
               for s in infra.SUBSTANCES]


def fault_names():
    """Виды смещения разломов по ключам core.faults.KINDS."""
    return {"normal": tr("Сбросы"),
            "reverse": tr("Взбросы, надвиги, субдукция"),
            "strike": tr("Сдвиги"),
            "ridge": tr("Срединные хребты"),
            "fold": tr("Складки"),
            "other": tr("Вид смещения не указан")}


class FaultLegend(_RowsLegend):
    """Шкала активных разломов: цвет - вид смещения."""

    def __init__(self, parent=None):
        self.title = tr("Активные разломы GEM")
        self.footer = tr("Щелчок по линии - сведения")
        super().__init__(parent)

    def rows(self):
        names = fault_names()
        return [(faults.COLORS[key][:3], names[key], "line", 2.0)
                for key in faults.KINDS]


class ClassLegend(_RowsLegend):
    """Шкала карты классами (core/tilemaps.py) - литологии GLiM или
    изменений воды. Строки меняются вместе с картой."""

    def __init__(self, parent=None):
        self._rows = []
        self.title = tr("Литология GLiM")
        super().__init__(parent)

    def rows(self):
        return self._rows

    def set_map(self, tmap):
        names = class_names()
        self.title = class_titles().get(tmap.key, tmap.key)
        self.footer = tr("Щелчок - класс в точке")
        self._rows = [(color, names.get(code, code), "dot", 0.0)
                      for code, color in tmap.classes or ()]
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        texts = [self.title, self.footer] + [r[1] for r in self._rows]
        width = max(_text_width(metrics, text) for text in texts if text)
        self.setFixedSize(max(BAR_WIDTH + 2 * PAD + 8,
                              width + PAD + 26 + PAD + 16),
                          line * (len(self._rows) + 2) + PAD)
        self.update()


def mine_kind_names():
    """Виды шахт и карьеров OSM по ключам core.mining.KINDS."""
    return {"mine": tr("Шахта или рудник"),
            "shaft": tr("Ствол шахты"),
            "quarry": tr("Карьер")}


def _text_width(metrics, text):
    """Ширина строки в пикселях. У QFontMetrics Qt 6 нет width."""
    if hasattr(metrics, "horizontalAdvance"):
        return metrics.horizontalAdvance(text)
    return metrics.width(text)


class DepositLegend(Closable, QWidget):
    """Шкала месторождений: цвет - группа полезного ископаемого
    (core.deposits.GROUPS), крупное месторождение мира - большая
    точка, рудник или завод мира - точка поменьше. Ширина - по самой
    длинной подписи, иначе длинные названия групп обрезались."""

    def __init__(self, parent=None):
        super().__init__(parent)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        names = deposit_group_names()
        texts = [tr("Месторождения USGS")] + list(names.values()) \
            + [tr("Размер точки, цвет - группа:"),
               tr("Крупное месторождение мира"),
               tr("Рудник или завод мира")]
        width = max(_text_width(metrics, text) for text in texts)
        self.setFixedSize(max(BAR_WIDTH + 2 * PAD + 8,
                              width + PAD + 18 + PAD + 16),
                          line * (len(deposits.GROUPS) + 5) + PAD)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(),
                         tr("Месторождения USGS"))
        names = deposit_group_names()
        rows = [(g[2], names[g[0]]) for g in deposits.GROUPS] \
            + [(deposits.OTHER_COLOR, names["other"])]
        y = top + line
        for rgb, name in rows:
            painter.setPen(QColor(*rgb).darker(250))
            painter.setBrush(QColor(*rgb))
            painter.drawEllipse(QPointF(PAD + 8, y + line / 2), 4.0, 4.0)
            painter.setPen(TEXT)
            painter.drawText(PAD + 18, y + metrics.ascent(), name)
            y += line
        # Размер - отдельно от цвета: кружки без цвета группы, иначе
        # жёлтый кружок читался как благородные металлы, замечание автора
        # от 11 октября 2026 года.
        painter.drawText(PAD, y + metrics.ascent(),
                         tr("Размер точки, цвет - группа:"))
        y += line
        for radius, text in ((deposits.MAJOR_SIZE / 2.0 + 1.0,
                              tr("Крупное месторождение мира")),
                             (deposits.FACILITY_SIZE / 2.0 + 1.0,
                              tr("Рудник или завод мира"))):
            painter.setPen(MUTED)
            painter.setBrush(QColor(255, 255, 255, 0))
            painter.drawEllipse(QPointF(PAD + 8, y + line / 2), radius,
                                radius)
            painter.setPen(TEXT)
            painter.drawText(PAD + 18, y + metrics.ascent(), text)
            y += line
        self._paint_close(painter)
        painter.end()


def shell_names():
    """Названия оболочек разреза по ключам core.cutaway.SHELLS."""
    return {"inner_core": tr("Внутреннее ядро"),
            "outer_core": tr("Внешнее ядро"),
            "lower_mantle": tr("Нижняя мантия"),
            "transition_zone": tr("Переходная зона"),
            "upper_mantle": tr("Верхняя мантия"),
            "crust": tr("Кора")}


def crust_names():
    """Названия слоёв CRUST1.0 по ключам core.crust.LAYERS."""
    return {"water": tr("Вода"),
            "ice": tr("Лёд"),
            "sediments_upper": tr("Верхние осадки"),
            "sediments_middle": tr("Средние осадки"),
            "sediments_lower": tr("Нижние осадки"),
            "crust_upper": tr("Верхняя кора"),
            "crust_middle": tr("Средняя кора"),
            "crust_lower": tr("Нижняя кора")}


def part_names():
    """Части коры по ключам core.cutaway.OCEAN_COLORS для строк
    «Континентальная кора, верхняя» и подобных."""
    return {"crust_upper": tr("верхняя"),
            "crust_middle": tr("средняя"),
            "crust_lower": tr("нижняя")}


class CutawayLegend(QWidget):
    """Оболочки разреза Земли: цвет, название, глубины границ в км."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.line = QFontMetrics(self.font()).height()
        self.crust = False
        self.oceanic = False
        self.tomo = False
        self.missing = ""
        self.gain = 1.0
        self.slabs = False
        self.set_crust(False)

    def set_slabs(self, on):
        """Строка плиты Slab2, когда на гранях есть плиты."""
        self.slabs = bool(on)
        self._rows()

    def set_gain(self, gain):
        """Растяжение коры разреза, строка под заголовком при gain > 1."""
        self.gain = float(gain)
        self._rows()

    def set_tomo(self, on):
        """Мантия по томографии: строки dVs вместо оболочек мантии."""
        self.tomo = bool(on)
        self._rows()

    def set_missing(self, reason):
        """Модель коры не пришла: строка с причиной, кора - слой PREM.
        Пустая строка снимает её."""
        self.missing = str(reason or "")
        self._rows()

    def set_crust(self, on, oceanic=False):
        """Строки шкалы: оболочки PREM или, с моделью коры, слои
        CRUST1.0 сверху и мантия от Мохо. oceanic - кора делится на
        континентальную и океаническую."""
        self.crust = bool(on)
        self.oceanic = bool(on and oceanic)
        self._rows()

    def _rows(self):
        names = shell_names()
        top = cutaway.PREM_RADIUS
        rows = []
        if self.crust:
            layers = crust_names()
            for key in cutaway.crust_layers():
                if self.oceanic and key in cutaway.OCEAN_COLORS:
                    continue
                rows.append((layers[key], cutaway.CRUST_COLORS[key]))
            if self.oceanic:
                parts = part_names()
                for title, colors in ((tr("Континентальная кора, {}"),
                                       cutaway.CRUST_COLORS),
                                      (tr("Океаническая кора, {}"),
                                       cutaway.OCEAN_COLORS)):
                    for key in cutaway.OCEAN_COLORS:
                        rows.append((title.format(parts[key]), colors[key]))
        if self.slabs:
            rows.append((tr("Плита Slab2"), cutaway.SLAB_COLOR))
        if self.tomo:
            rows += [(tr("Мантия медленнее PREM на 2 % и больше"),
                      tomography.STOPS[0][1]),
                     (tr("Мантия как PREM"), tomography.STOPS[2][1]),
                     (tr("Мантия быстрее PREM на 2 % и больше"),
                      tomography.STOPS[-1][1])]
        for key, low, high, color in reversed(cutaway.SHELLS):
            if key == "crust" and self.crust:
                continue
            if self.tomo and key in cutaway.MANTLE:
                continue
            if key == "upper_mantle" and self.crust:
                text = tr("{}, Мохо-{:g}").format(names[key], top - low)
            else:
                text = "{}, {:g}-{:g}".format(names[key], top - high,
                                              top - low)
            rows.append((text, color))
        if self.gain > 1.0:
            rows.insert(0, (tr("Глубины до {:g} км растянуты, у поверхности "
                               "×{:g}").format(cutaway.STRETCH_DEPTH,
                                               self.gain), None))
        if self.missing and not self.crust:
            rows.insert(0, (tr("Модель коры CRUST1.0 не загружена ({}), "
                               "кора - слой PREM").format(self.missing),
                            None))
        self.rows = rows
        metrics = QFontMetrics(self.font())
        width = max(metrics.horizontalAdvance(text) for text, _ in rows)
        width = max(width, metrics.horizontalAdvance(self._title()))
        self.setFixedSize(width + 2 * PAD + self.line + 4,
                          (len(rows) + 1) * self.line + PAD)
        self.update()

    def _title(self):
        if self.crust:
            return tr("Кора CRUST1.0, оболочки PREM, глубина, км")
        return tr("Оболочки PREM, глубина, км")

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), self._title())
        box = self.line - 4
        for n, (text, rgb) in enumerate(self.rows):
            y = top + (n + 1) * self.line
            painter.setPen(TEXT)
            if rgb is None:
                # Строка пояснения без цвета.
                painter.drawText(PAD, y + metrics.ascent(), text)
                continue
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(*rgb))
            painter.drawRect(QRectF(PAD, y + 2, box, box))
            painter.setPen(TEXT)
            painter.drawText(PAD + box + 6, y + metrics.ascent(), text)
        painter.end()


class BedsLegend(QWidget):
    """Шкала подземного режима: пласты модели сверху вниз квадратами
    своих цветов с кодами, ниже тоннели. items - [(цвет (r, g, b),
    подпись)]."""

    SWATCH = 12
    COLUMN = 110  # логических пикселей на столбец

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.items = []
        self.hide()

    def _layout(self):
        """Строк в столбце и столбцов: не выше 12 строк."""
        rows = min(len(self.items), 12) or 1
        columns = (len(self.items) + rows - 1) // rows or 1
        return rows, columns

    def set_items(self, items):
        self.items = list(items)
        line = QFontMetrics(self.font()).height()
        rows, columns = self._layout()
        self.setFixedSize(columns * self.COLUMN + 2 * PAD,
                          line * (rows + 1) + PAD)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), tr("Пласты"))
        rows, _ = self._layout()
        for n, (rgb, label) in enumerate(self.items):
            x = PAD + (n // rows) * self.COLUMN
            y = top + line * (n % rows + 1)
            painter.setPen(MUTED)
            painter.setBrush(QColor(*rgb))
            painter.drawRect(QRectF(x, y + (line - self.SWATCH) / 2.0,
                                    self.SWATCH, self.SWATCH))
            painter.setPen(TEXT)
            painter.drawText(int(x + self.SWATCH + 6),
                             int(y + metrics.ascent()), label)
        painter.end()


class ThemeLegend(Closable, QWidget):
    """Шкала темы NASA GIBS: название с датой, ниже полоса цветов
    с подписями (непрерывная шкала) или квадраты классов. scale -
    словарь core.themes.parse_colormap или None, тогда только строка
    названия."""

    SWATCH = 10
    COLUMN = 170  # логических пикселей на столбец классов
    ROWS = 9  # строк классов в столбце

    def __init__(self, parent=None):
        super().__init__(parent)
        self.title = ""
        self.scale = None
        self.hide()

    def set_theme(self, title, scale):
        self.title = title
        self.scale = scale
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        width = max(BAR_WIDTH + 2 * PAD + 8,
                    metrics.horizontalAdvance(title) + 2 * PAD
                    + CLOSE + 6)
        height = line + PAD
        if scale and scale["kind"] != "classification":
            height += line + BAR_HEIGHT + 2
        elif scale:
            rows = min(len(scale["names"]), self.ROWS)
            columns = (len(scale["names"]) + self.ROWS - 1) // self.ROWS
            width = max(width, columns * self.COLUMN + 2 * PAD)
            height += rows * line
        self.setFixedSize(width, height)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        _background(self, painter)
        metrics = QFontMetrics(self.font())
        line = metrics.height()
        top = PAD // 2
        painter.setPen(TEXT)
        painter.drawText(PAD, top + metrics.ascent(), self.title)
        scale = self.scale
        if scale and scale["kind"] != "classification":
            bar = QRectF(PAD + 4, top + line + 1, BAR_WIDTH, BAR_HEIGHT)
            colors = scale["colors"]
            gradient = QLinearGradient(bar.left(), 0, bar.right(), 0)
            for n, rgb in enumerate(colors):
                gradient.setColorAt(n / max(len(colors) - 1, 1),
                                    QColor(*rgb[:3]))
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(gradient)
            painter.drawRect(bar)
            painter.setPen(TEXT)
            # Подпись, которая налезла бы на прежнюю, пропускается.
            right = -1.0
            for share, text in scale["labels"]:
                x = bar.left() + share * BAR_WIDTH
                width = metrics.horizontalAdvance(text)
                left = min(max(x - width / 2, 1), self.width() - width - 1)
                if left < right + 4:
                    continue
                right = left + width
                painter.drawLine(int(x), int(bar.bottom()), int(x),
                                 int(bar.bottom()) + 2)
                painter.drawText(int(left),
                                 int(bar.bottom()) + 2 + metrics.ascent(),
                                 text)
        elif scale:
            for n, (rgb, name) in enumerate(zip(scale["colors"],
                                                scale["names"])):
                x = PAD + (n // self.ROWS) * self.COLUMN
                y = top + line * (n % self.ROWS + 1)
                painter.setPen(MUTED)
                painter.setBrush(QColor(*rgb[:3]))
                painter.drawRect(QRectF(x, y + (line - self.SWATCH) / 2.0,
                                        self.SWATCH, self.SWATCH))
                painter.setPen(TEXT)
                painter.drawText(int(x + self.SWATCH + 5),
                                 int(y + metrics.ascent()),
                                 metrics.elidedText(
                                     name, enum(Qt, "TextElideMode",
                                                "ElideRight"),
                                     self.COLUMN - self.SWATCH - 10))
        self._paint_close(painter)
        painter.end()


def _background(widget, painter):
    """Фон шкалы. Шкала в панели LegendPanel фона не рисует, фон
    общий у панели."""
    if isinstance(widget.parentWidget(), LegendPanel):
        return
    painter.setPen(enum(Qt, "PenStyle", "NoPen"))
    painter.setBrush(BACKGROUND)
    painter.drawRoundedRect(QRectF(widget.rect()), 3, 3)


class LegendPanel(QWidget):
    """Шкалы слоёв одной панелью в углу вида: общий фон, шкалы -
    разделами сверху вниз в порядке добавления, скрытые не занимают
    места. Решение автора от 5 октября 2026 года. changed() зовётся,
    когда размер панели сменился, - окно ставит её на место."""

    def __init__(self, parent=None):
        super().__init__(parent)
        # Щелчок мимо крестика шкалы уходит виду под панелью.
        self.layout_ = QVBoxLayout(self)
        self.layout_.setContentsMargins(0, PAD // 2, 0, PAD // 2)
        self.layout_.setSpacing(2)
        self.legends = []
        self.changed = None
        self.hide()

    def add(self, legend):
        legend.setParent(self)
        self.layout_.addWidget(legend)
        self.legends.append(legend)
        legend.installEventFilter(self)
        self.refit()

    def eventFilter(self, watched, event):
        # ShowToParent и HideToParent приходят и при скрытой панели,
        # Show и Hide шкале скрытой панели Qt не шлёт.
        if event.type() in (enum(QEvent, "Type", "Show"),
                            enum(QEvent, "Type", "Hide"),
                            enum(QEvent, "Type", "ShowToParent"),
                            enum(QEvent, "Type", "HideToParent"),
                            enum(QEvent, "Type", "Resize")):
            QTimer.singleShot(0, self.refit)
        return False

    def refit(self):
        shown = [legend for legend in self.legends if not legend.isHidden()]
        self.setVisible(bool(shown))
        if shown:
            self.layout_.activate()
            self.adjustSize()
        if self.changed is not None:
            self.changed()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
        painter.end()
