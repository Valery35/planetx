# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Единый вид элементов поверх глобуса: плашки и значки.

Просьба автора от 17 октября 2026 года - «кнопки на карте сделать бы
в едином стиле, сейчас разнобой жуткий». На панели значков стояли
цветные значки QGIS и свои SVG на светлой плашке, у шкалы времени и
тура - синие квадраты и символы эмодзи, у органов навигации - светлые
линии на тёмном стекле. Теперь у всех элементов поверх вида одна
тёмная полупрозрачная плашка, как у органов навигации, и значки одного
набора - светлые линии, нажатое и включённое - синим. Значки рисуются
кодом (icon), так набор не зависит от темы значков QGIS и шрифта
эмодзи Windows.

Цвета и толщина линий - выбор помощника, утверждает автор.
"""
import math

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt
from qgis.PyQt.QtGui import (QColor, QIcon, QImage, QPainter, QPainterPath,
                             QPen, QPixmap, QPolygonF)

from ..qt_compat import enum

# Плашка, линия, текст, подсветка, акцент.
PLATE = QColor(30, 33, 38, 215)
BORDER = QColor(255, 255, 255, 45)
TEXT = QColor(236, 239, 243)
MUTED = QColor(170, 176, 184)
HOVER = QColor(255, 255, 255, 30)
ACCENT = QColor(74, 163, 255)
RECORD = QColor(240, 86, 72)
ICON_SIDE = 20  # сторона значка, логических пикселей
STROKE = 1.7  # толщина линии значка в долях клетки 24


def _rgba(color):
    return "rgba({}, {}, {}, {})".format(color.red(), color.green(),
                                       color.blue(), color.alpha())


def plate_style(name, kind="QFrame"):
    """Стиль плашки kind#name и её кнопок, подписей, списков и полей."""
    return (
        "{kind}#{name} {{ background: {plate}; border: 1px solid {border}; "
        "border-radius: 6px; }}"
        "{kind}#{name} QLabel {{ color: {text}; background: transparent; "
        "border: none; }}"
        "{kind}#{name} QToolButton {{ color: {text}; background: "
        "transparent; border: none; border-radius: 4px; padding: 2px; }}"
        "{kind}#{name} QToolButton:hover {{ background: {hover}; }}"
        "{kind}#{name} QToolButton:checked {{ background: {checked}; }}"
        "{kind}#{name} QToolButton:disabled {{ color: {muted}; }}"
        "{kind}#{name} QToolButton::menu-indicator {{ image: none; "
        "width: 0px; }}"
        "{kind}#{name} QComboBox, {kind}#{name} QDoubleSpinBox, "
        "{kind}#{name} QSpinBox {{ color: {text}; background: {hover}; "
        "border: 1px solid {border}; border-radius: 3px; padding: 1px 4px; "
        "}}"
        "{kind}#{name} QComboBox QAbstractItemView {{ color: {text}; "
        "background: rgb(40, 44, 50); selection-background-color: "
        "{checked}; }}"
        "{kind}#{name} QSlider::groove:horizontal {{ height: 4px; "
        "background: {border}; border-radius: 2px; }}"
        "{kind}#{name} QSlider::sub-page:horizontal {{ background: "
        "{accent}; border-radius: 2px; }}"
        "{kind}#{name} QSlider::handle:horizontal {{ width: 12px; "
        "margin: -5px 0; border-radius: 6px; background: {text}; }}"
    ).format(kind=kind, name=name, plate=_rgba(PLATE), border=_rgba(BORDER),
             text=_rgba(TEXT), muted=_rgba(MUTED), hover=_rgba(HOVER),
             checked="rgba(74, 163, 255, 110)", accent=_rgba(ACCENT))


def _pen(color, width):
    pen = QPen(color, width)
    pen.setCapStyle(enum(Qt, "PenCapStyle", "RoundCap"))
    pen.setJoinStyle(enum(Qt, "PenJoinStyle", "RoundJoin"))
    return pen


def _arrow(p, x, y, angle, size):
    """Наконечник стрелки в точке (x, y), направление angle в градусах
    по часовой от оси x."""
    a = math.radians(angle)
    for side in (-1, 1):
        b = a + side * math.radians(150.0)
        p.drawLine(QPointF(x, y), QPointF(x + size * math.cos(b),
                                          y + size * math.sin(b)))


def _triangle(p, points):
    p.drawPolygon(QPolygonF([QPointF(x, y) for x, y in points]))


def _draw(p, name, color):
    """Значок name на клетке 24 × 24."""
    line = _pen(color, STROKE)
    p.setPen(line)
    p.setBrush(enum(Qt, "BrushStyle", "NoBrush"))
    fill = color
    if name == "sidebar":
        p.drawRoundedRect(QRectF(3, 5, 18, 14), 2, 2)
        p.drawLine(QPointF(9, 5), QPointF(9, 19))
    elif name in ("refresh", "sync", "loop"):
        p.drawArc(QRectF(5, 5, 14, 14), 40 * 16, 260 * 16)
        _arrow(p, 17.4, 7.6, -40.0 + 90.0, 3.5)
        if name != "refresh":
            p.drawArc(QRectF(5, 5, 14, 14), 220 * 16, 40 * 16)
            _arrow(p, 6.6, 16.4, 140.0 + 90.0, 3.5)
    elif name == "identify":
        # Прицел: опрос точки под щелчком.
        p.drawEllipse(QPointF(12, 12), 6.5, 6.5)
        for x0, y0, x1, y1 in ((12, 2.5, 12, 7.5), (12, 16.5, 12, 21.5),
                               (2.5, 12, 7.5, 12), (16.5, 12, 21.5, 12)):
            p.drawLine(QPointF(x0, y0), QPointF(x1, y1))
        p.setBrush(fill)
        p.drawEllipse(QPointF(12, 12), 1.3, 1.3)
    elif name == "ruler":
        p.translate(12, 12)
        p.rotate(-30)
        p.drawRoundedRect(QRectF(-9.5, -3.5, 19, 7), 1.5, 1.5)
        for x, tall in ((-6, 3), (-3, 2), (0, 3), (3, 2), (6, 3)):
            p.drawLine(QPointF(x, -3.5), QPointF(x, -3.5 + tall))
    elif name == "place":
        path = QPainterPath()
        path.moveTo(12, 21)
        path.cubicTo(7, 15, 5, 12, 5, 9.5)
        path.arcTo(QRectF(5, 2.5, 14, 14), 180, -180)
        path.cubicTo(19, 12, 17, 15, 12, 21)
        p.drawPath(path)
        p.drawEllipse(QPointF(12, 9.5), 2.6, 2.6)
    elif name == "bookmark":
        _triangle(p, ((6, 3.5), (18, 3.5), (18, 20.5), (12, 15.5),
                      (6, 20.5)))
    elif name == "record":
        p.drawEllipse(QPointF(12, 12), 8, 8)
        p.setPen(enum(Qt, "PenStyle", "NoPen"))
        p.setBrush(RECORD)
        p.drawEllipse(QPointF(12, 12), 4, 4)
    elif name == "time":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawLine(QPointF(12, 12), QPointF(12, 7))
        p.drawLine(QPointF(12, 12), QPointF(15.5, 14))
    elif name == "camera":
        p.drawRoundedRect(QRectF(3, 7, 18, 12), 2, 2)
        p.drawLine(QPointF(8.5, 7), QPointF(10, 4.5))
        p.drawLine(QPointF(10, 4.5), QPointF(14, 4.5))
        p.drawLine(QPointF(14, 4.5), QPointF(15.5, 7))
        p.drawEllipse(QPointF(12, 13), 3.6, 3.6)
    elif name == "layout":
        p.drawRoundedRect(QRectF(5, 3, 14, 18), 1.5, 1.5)
        p.drawRect(QRectF(8, 6, 8, 6))
        p.drawLine(QPointF(8, 15), QPointF(16, 15))
        p.drawLine(QPointF(8, 18), QPointF(13, 18))
    elif name == "scene":
        p.drawRoundedRect(QRectF(3, 7, 18, 13), 2, 2)
        p.drawLine(QPointF(3, 10.5), QPointF(21, 10.5))
        p.drawLine(QPointF(3, 7), QPointF(5, 4))
        p.drawLine(QPointF(5, 4), QPointF(19, 4))
        p.drawLine(QPointF(19, 4), QPointF(21, 7))
        _triangle(p, ((10, 13), (10, 18), (14.5, 15.5)))
    elif name == "demo":
        _triangle(p, ((2.5, 9.5), (12, 5), (21.5, 9.5), (12, 14)))
        p.drawLine(QPointF(6.5, 11.5), QPointF(6.5, 16))
        p.drawArc(QRectF(6.5, 12, 11, 7), 180 * 16, 180 * 16)
        p.drawLine(QPointF(17.5, 11.5), QPointF(17.5, 15.5))
        p.drawLine(QPointF(21.5, 9.5), QPointF(21.5, 15))
    elif name == "body":
        p.drawEllipse(QPointF(12, 12), 6.5, 6.5)
        p.translate(12, 12)
        p.rotate(-20)
        p.drawArc(QRectF(-11, -3.5, 22, 7), 200 * 16, 140 * 16)
        p.drawArc(QRectF(-11, -3.5, 22, 7), -20 * 16, 40 * 16)
    elif name == "settings":
        p.drawEllipse(QPointF(12, 12), 3, 3)
        p.drawEllipse(QPointF(12, 12), 6.5, 6.5)
        for k in range(8):
            a = math.radians(45.0 * k)
            p.drawLine(QPointF(12 + 6.5 * math.cos(a),
                               12 + 6.5 * math.sin(a)),
                       QPointF(12 + 9 * math.cos(a), 12 + 9 * math.sin(a)))
    elif name == "fullscreen":
        for x, y, dx, dy in ((4, 4, 1, 1), (20, 4, -1, 1), (4, 20, 1, -1),
                             (20, 20, -1, -1)):
            p.drawLine(QPointF(x, y), QPointF(x + 5 * dx, y))
            p.drawLine(QPointF(x, y), QPointF(x, y + 5 * dy))
    elif name == "info":
        p.drawEllipse(QPointF(12, 12), 8.5, 8.5)
        p.drawLine(QPointF(12, 10.5), QPointF(12, 16.5))
        p.setBrush(fill)
        p.drawEllipse(QPointF(12, 7.6), 0.9, 0.9)
    elif name in ("prev", "next"):
        p.setBrush(fill)
        if name == "prev":
            p.drawLine(QPointF(6.5, 6), QPointF(6.5, 18))
            _triangle(p, ((18, 6), (18, 18), (9, 12)))
        else:
            p.drawLine(QPointF(17.5, 6), QPointF(17.5, 18))
            _triangle(p, ((6, 6), (6, 18), (15, 12)))
    elif name == "play":
        p.setBrush(fill)
        _triangle(p, ((7.5, 5), (7.5, 19), (19, 12)))
    elif name == "pause":
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(6.5, 5.5, 3.5, 13), 1, 1)
        p.drawRoundedRect(QRectF(14, 5.5, 3.5, 13), 1, 1)
    elif name == "stop":
        p.setBrush(fill)
        p.drawRoundedRect(QRectF(6.5, 6.5, 11, 11), 1.5, 1.5)
    elif name == "rec":
        p.setPen(enum(Qt, "PenStyle", "NoPen"))
        p.setBrush(RECORD)
        p.drawEllipse(QPointF(12, 12), 6, 6)
    elif name == "captions":
        p.drawRoundedRect(QRectF(3, 6, 18, 12), 2, 2)
        p.drawLine(QPointF(6.5, 11), QPointF(17.5, 11))
        p.drawLine(QPointF(6.5, 14.5), QPointF(13.5, 14.5))
    elif name == "swipe":
        p.drawLine(QPointF(4, 9), QPointF(20, 9))
        _arrow(p, 20, 9, 0.0, 4.0)
        p.drawLine(QPointF(4, 15), QPointF(20, 15))
        _arrow(p, 4, 15, 180.0, 4.0)
    elif name in ("left", "right", "back"):
        if name == "left":
            p.drawLine(QPointF(14.5, 6), QPointF(8.5, 12))
            p.drawLine(QPointF(8.5, 12), QPointF(14.5, 18))
        elif name == "right":
            p.drawLine(QPointF(9.5, 6), QPointF(15.5, 12))
            p.drawLine(QPointF(15.5, 12), QPointF(9.5, 18))
        else:
            p.drawLine(QPointF(5, 12), QPointF(19, 12))
            _arrow(p, 5, 12, 180.0, 6.0)
    elif name == "close":
        p.drawLine(QPointF(7, 7), QPointF(17, 17))
        p.drawLine(QPointF(17, 7), QPointF(7, 17))


def icon(name, color=None, side=ICON_SIDE, menu=False):
    """Значок name набора PlanetX: светлые линии, color - другой цвет,
    например тёмный для светлых окон. menu - белая стрелка вниз в правом
    нижнем углу у кнопки с меню, замечание автора от 17 октября 2026
    года - стрелку меню Qt стиль плашки прятал."""
    color = TEXT if color is None else color
    ratio = 2
    image = QImage(side * ratio, side * ratio,
                   enum(QImage, "Format", "Format_ARGB32_Premultiplied"))
    image.fill(QColor(0, 0, 0, 0))
    p = QPainter(image)
    p.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    scale = side * ratio / 24.0
    p.scale(scale, scale)
    _draw(p, name, color)
    if menu:
        p.resetTransform()
        p.scale(scale, scale)
        p.setPen(enum(Qt, "PenStyle", "NoPen"))
        p.setBrush(color)
        _triangle(p, ((17.5, 19), (23.5, 19), (20.5, 23)))
    p.end()
    pixmap = QPixmap.fromImage(image)
    pixmap.setDevicePixelRatio(ratio)
    return QIcon(pixmap)


# Символы прежних кнопок и значки набора.
GLYPHS = {"⏮": "prev", "▶️": "play", "▶️": "play", "▶": "play",
          "⏸": "pause", "⏭": "next", "🔁": "loop", "⏹": "stop", "⏺": "rec",
          "🔤": "captions", "⇆": "swipe", "‹": "left", "›": "right",
          "←": "back", "✕": "close"}


def set_glyph(button, symbol, color=None):
    """Значок кнопки по прежнему символу: текст снимается."""
    button.setText("")
    button.setIcon(icon(GLYPHS[symbol], color))
    button.setIconSize(QSize(ICON_SIDE, ICON_SIDE))
