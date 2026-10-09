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
from qgis.PyQt.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter
from qgis.PyQt.QtWidgets import QVBoxLayout, QWidget

from ..core import (contours, cutaway, fires, insolation, quakes, slope,
                    temperature)
from ..i18n import tr
from ..qt_compat import enum

BAR_WIDTH = 180  # длина полосы шкалы, логических пикселей
BAR_HEIGHT = 9
PAD = 6
BACKGROUND = QColor(255, 255, 255, 190)
TEXT = QColor(30, 30, 30)
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
        painter.setBrush(QColor(0, 0, 0, 40))
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
            painter.setPen(QColor(20, 90, 200))
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


class CutawayLegend(QWidget):
    """Оболочки разреза Земли: цвет, название, глубины границ в км."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.line = QFontMetrics(self.font()).height()
        self.crust = False
        self.gain = 1.0
        self.slabs = False
        self.set_crust(False)

    def set_slabs(self, on):
        """Строка плиты Slab2, когда на гранях есть плиты."""
        self.slabs = bool(on)
        self.set_crust(self.crust)

    def set_gain(self, gain):
        """Растяжение коры разреза, строка под заголовком при gain > 1."""
        self.gain = float(gain)
        self.set_crust(self.crust)

    def set_crust(self, on):
        """Строки шкалы: оболочки PREM или, с моделью коры, слои
        CRUST1.0 сверху и мантия от Мохо."""
        self.crust = bool(on)
        names = shell_names()
        top = cutaway.PREM_RADIUS
        rows = []
        if self.crust:
            layers = crust_names()
            rows = [(layers[key], cutaway.CRUST_COLORS[key])
                    for key in cutaway.crust_layers()]
        if self.slabs:
            rows.append((tr("Плита Slab2"), cutaway.SLAB_COLOR))
        for key, low, high, color in reversed(cutaway.SHELLS):
            if key == "crust" and self.crust:
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
            painter.setPen(QColor(60, 60, 60))
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
                painter.setPen(QColor(60, 60, 60))
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
