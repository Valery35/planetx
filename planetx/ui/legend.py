# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шкалы в углу вида: температура суши и моря в градусах Цельсия,
уклон и экспозиция поверхности (core/slope.py), часы прямого солнца
(core/insolation.py), глубина очагов землетрясений (core/quakes.py),
оболочки разреза Земли (core/cutaway.py).

Цвета и подписи берутся из core/temperature.py. Виджет рисует себя
сам, фон полупрозрачный, как у подписи источников.
"""
from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFontMetrics, QLinearGradient, QPainter
from qgis.PyQt.QtWidgets import QWidget

from ..core import cutaway, insolation, quakes, slope, temperature
from ..i18n import tr
from ..qt_compat import enum

BAR_WIDTH = 180  # длина полосы шкалы, логических пикселей
BAR_HEIGHT = 9
PAD = 6
BACKGROUND = QColor(255, 255, 255, 190)
TEXT = QColor(30, 30, 30)


class TemperatureLegend(QWidget):
    """Две шкалы: суша и море."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
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
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
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
        painter.end()


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
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
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
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
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
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
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
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        painter.setBrush(BACKGROUND)
        painter.drawRoundedRect(QRectF(self.rect()), 3, 3)
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
