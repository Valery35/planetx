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

Оформление - просьба автора от 19 октября 2026 года, «переключатель
в свойствах вида, для всего модуля», «в окне карты в светлом стиле
пусть более серыми будут», «по умолчанию тёмная тема». Три
оформления (THEMES): «Тёмное» (по умолчанию) - тёмные плашки и тёмные
окна; «Светлое» - серые плашки с тёмными значками и светлые окна;
«Как в QGIS» - тёмные плашки на виде, окна модуля в оформлении QGIS.
Цвета плашек - общие объекты QColor, apply меняет их на месте,
restyle перекрашивает плашки (plate), значки
набора (icon помнит имя значка по cacheKey) и окна модуля
(window_style - левая панель, панель свойств, каталог, окна QDialog).
"""
import ctypes
import math
import os
import sys

from qgis.PyQt.QtCore import QPointF, QRectF, QSize, Qt
from qgis.PyQt.QtGui import (QColor, QIcon, QImage, QPainter, QPainterPath,
                             QPen, QPixmap, QPolygonF)
from qgis.PyQt.QtWidgets import QAbstractButton, QWidget

from ..qt_compat import QAction, enum

# Плашка, линия, текст, подсветка, акцент.
PLATE = QColor(30, 33, 38, 215)
BORDER = QColor(255, 255, 255, 45)
TEXT = QColor(236, 239, 243)
MUTED = QColor(170, 176, 184)
HOVER = QColor(255, 255, 255, 30)
ACCENT = QColor(74, 163, 255)
RECORD = QColor(240, 86, 72)
CHECKED = QColor(74, 163, 255, 110)
LIST = QColor(40, 44, 50)
# Органы навигации: заливка, линии, кружок и буква N.
NAV_FILL = QColor(24, 24, 24)
NAV_LINE = QColor(255, 255, 255)
NAV_ACCENT = QColor(120, 190, 255)
NORTH_FILL = QColor(240, 240, 240)
NORTH_TEXT = QColor(30, 30, 30)
ICON_SIDE = 20  # сторона значка, логических пикселей
STROKE = 1.7  # толщина линии значка в долях клетки 24


def _rgba(color):
    return "rgba({}, {}, {}, {})".format(color.red(), color.green(),
                                       color.blue(), color.alpha())


# Фон выпадающих меню непрозрачный: всплывающее окно без прозрачного
# фона Windows заливает долю прозрачности чёрным.
MENU = QColor(36, 40, 46)

THEME_KEY = "PlanetX/ui_theme"
QGIS, LIGHT, DARK = "qgis", "light", "dark"
THEMES = (QGIS, LIGHT, DARK)
_DARK_PLATES = {
    "PLATE": (30, 33, 38, 215), "BORDER": (255, 255, 255, 45),
    "TEXT": (236, 239, 243, 255), "MUTED": (170, 176, 184, 255),
    "HOVER": (255, 255, 255, 30), "ACCENT": (74, 163, 255, 255),
    "MENU": (36, 40, 46, 255), "CHECKED": (74, 163, 255, 110),
    "LIST": (40, 44, 50, 255), "NAV_FILL": (24, 24, 24, 255),
    "NAV_LINE": (255, 255, 255, 255), "NAV_ACCENT": (120, 190, 255, 255),
    "NORTH_FILL": (240, 240, 240, 255), "NORTH_TEXT": (30, 30, 30, 255)}
# Светлое: плашки серые, а не белые - просьба автора, значки тёмные.
_LIGHT_PLATES = {
    "PLATE": (214, 218, 223, 225), "BORDER": (0, 0, 0, 45),
    "TEXT": (34, 38, 44, 255), "MUTED": (98, 105, 114, 255),
    "HOVER": (0, 0, 0, 24), "ACCENT": (26, 104, 204, 255),
    "MENU": (228, 231, 235, 255), "CHECKED": (26, 104, 204, 70),
    "LIST": (238, 240, 243, 255), "NAV_FILL": (205, 209, 215, 255),
    "NAV_LINE": (40, 44, 50, 255), "NAV_ACCENT": (26, 104, 204, 255),
    "NORTH_FILL": (52, 56, 62, 255), "NORTH_TEXT": (240, 242, 245, 255)}
PLATES = {QGIS: _DARK_PLATES, LIGHT: _LIGHT_PLATES, DARK: _DARK_PLATES}
# Окна модуля: фон, текст, поле, рамка, кнопка, кнопка под курсором,
# выделение, приглушённый текст.
WINDOWS = {
    LIGHT: {"back": "#eef0f3", "text": "#1f2329", "field": "#ffffff",
            "border": "#bfc5cd", "button": "#e1e5ea", "hover": "#d4d9e0",
            "select": "#2f6fbf", "muted": "#7b828c", "alt": "#f5f6f8"},
    DARK: {"back": "#262a30", "text": "#e3e7ec", "field": "#1d2025",
           "border": "#454b54", "button": "#353a42", "hover": "#3f454e",
           "select": "#2f6fbf", "muted": "#7f8690", "alt": "#22262c"}}
# Части окна глобуса, которые перекрашивает window_style: окна свойств
# и прочие QDialog, левая панель, панель свойств справа, каталог.
WINDOW_PARTS = ("QDialog", "#planetxPanel", "#planetxSide",
                "#planetxCatalog")
# Части, у которых фон из правил рисуется только с WA_StyledBackground.
STYLED_BACK = ("planetxWindow", "planetxPanel", "planetxSide")
CHECK = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data",
                     "check.svg").replace("\\", "/")
_current = [DARK]  # по умолчанию тёмное, просьба автора


def current():
    return _current[0]


def apply(name):
    """Оформление name: цвета плашек меняются на месте."""
    if name not in THEMES:
        name = QGIS
    _current[0] = name
    colors = globals()
    for key, rgba in PLATES[name].items():
        colors[key].setRgb(*rgba)


def window_style(name=None):
    """Правила окон модуля для оформления name, «Как в QGIS» - пусто."""
    w = WINDOWS.get(current() if name is None else name)
    if w is None:
        return ""
    rules = (
        "{p} {{ background-color: {back}; color: {text}; }}"
        "{p} QWidget {{ background-color: {back}; color: {text}; }}"
        "{p} QLabel, {p} QCheckBox, {p} QRadioButton {{ background: "
        "transparent; }}"
        "{p} QLineEdit, {p} QTextEdit, {p} QPlainTextEdit, "
        "{p} QAbstractSpinBox, {p} QComboBox {{ background-color: {field}; "
        "border: 1px solid {border}; border-radius: 3px; padding: 2px 4px; "
        "selection-background-color: {select}; selection-color: white; }}"
        "{p} QComboBox QAbstractItemView {{ background-color: {field}; "
        "selection-background-color: {select}; }}"
        "{p} QAbstractItemView {{ background-color: {field}; "
        "alternate-background-color: {alt}; border: 1px solid {border}; "
        "selection-background-color: {select}; selection-color: white; }}"
        "{p} QHeaderView::section {{ background-color: {button}; "
        "border: none; border-right: 1px solid {border}; padding: 3px; }}"
        "{p} QPushButton {{ background-color: {button}; border: 1px solid "
        "{border}; border-radius: 3px; padding: 3px 10px; }}"
        "{p} QPushButton:hover, {p} QToolButton:hover {{ background-color: "
        "{hover}; }}"
        "{p} QPushButton:pressed, {p} QPushButton:checked, "
        "{p} QToolButton:checked {{ background-color: {select}; "
        "color: white; }}"
        "{p} QPushButton:disabled, {p} QLabel:disabled, "
        "{p} QCheckBox:disabled {{ color: {muted}; }}"
        "{p} QToolButton {{ background: transparent; border: none; "
        "border-radius: 3px; padding: 2px; }}"
        "{p} QGroupBox {{ border: 1px solid {border}; border-radius: 4px; "
        "margin-top: 10px; padding-top: 4px; }}"
        "{p} QGroupBox::title {{ subcontrol-origin: margin; left: 8px; "
        "padding: 0 3px; }}"
        "{p} QTabBar::tab {{ background-color: {button}; border: 1px solid "
        "{border}; padding: 4px 10px; }}"
        "{p} QTabBar::tab:selected {{ background-color: {field}; }}"
        "{p} QScrollBar:vertical {{ background: {alt}; width: 11px; "
        "margin: 0; }}"
        "{p} QScrollBar:horizontal {{ background: {alt}; height: 11px; "
        "margin: 0; }}"
        "{p} QScrollBar::handle {{ background: {border}; border-radius: "
        "4px; min-height: 20px; min-width: 20px; }}"
        "{p} QScrollBar::add-line, {p} QScrollBar::sub-line {{ width: 0; "
        "height: 0; }}"
        "{p} QScrollBar::add-page, {p} QScrollBar::sub-page {{ "
        "background: none; }}"
        "{p} QMenu {{ background-color: {field}; border: 1px solid "
        "{border}; }}"
        "{p} QMenu::item:selected {{ background-color: {select}; "
        "color: white; }}"
        "{p} QSplitter::handle {{ background-color: {border}; }}"
        # Флажки рисуются правилами: на тёмном фоне пустой флажок стиля
        # QGIS не виден.
        "{p} QAbstractItemView::indicator, {p} QCheckBox::indicator, "
        "{p} QGroupBox::indicator {{ width: 12px; height: 12px; "
        "border: 1px solid {muted}; border-radius: 2px; "
        "background-color: {field}; }}"
        "{p} QAbstractItemView::indicator:checked, "
        "{p} QCheckBox::indicator:checked, "
        "{p} QGroupBox::indicator:checked {{ background-color: {select}; "
        "border-color: {select}; image: url({check}); }}"
        "{p} QAbstractItemView::indicator:indeterminate, "
        "{p} QCheckBox::indicator:indeterminate {{ background-color: "
        "{muted}; border-color: {muted}; }}")
    out = "".join(rules.format(p=part, check=CHECK, **w)
                  for part in WINDOW_PARTS)
    # Всплывающие меню окна глобуса - меню правой кнопки на глобусе
    # и прочие QMenu с родителем-окном. У меню плашек свои правила.
    menus = (
        "QMenu {{ background-color: {field}; color: {text}; border: 1px "
        "solid {border}; padding: 3px 0; }}"
        "QMenu::item {{ padding: 4px 22px 4px 22px; background: "
        "transparent; }}"
        "QMenu::item:selected {{ background-color: {select}; color: "
        "white; }}"
        "QMenu::item:disabled {{ color: {muted}; }}"
        "QMenu::separator {{ height: 1px; background: {border}; "
        "margin: 3px 8px; }}").format(**w)
    return out + menus + \
        "QWidget#planetxWindow {{ background-color: {}; }}".format(w["back"])


# Тёмный заголовок окна Windows - атрибут DWM, Qt его не рисует.
# Замечание автора от 19 октября 2026 года со снимком - светлая полоса
# заголовка над тёмным окном глобуса. 20 - Windows 10 20H1 и новее,
# 19 - ранние сборки Windows 10.
DARK_TITLE_ATTRIBUTES = (20, 19)


def title_bar(widget, dark=None):
    """Заголовок окна widget тёмный или светлый (по оформлению). Только
    Windows, на прочих системах ничего не делает."""
    if sys.platform != "win32" or widget is None:
        return
    if dark is None:
        dark = current() == DARK
    try:
        hwnd = ctypes.c_void_p(int(widget.window().winId()))
        flag = ctypes.c_int(1 if dark else 0)
        dwm = ctypes.windll.dwmapi
    except (AttributeError, OSError, RuntimeError, TypeError, ValueError):
        return
    for attribute in DARK_TITLE_ATTRIBUTES:
        if dwm.DwmSetWindowAttribute(hwnd, attribute, ctypes.pointer(flag),
                                     ctypes.sizeof(flag)) == 0:
            break


class TitleBars:
    """Заголовки окон модуля по оформлению: окно глобуса, его дочерние
    окна при показе (сигнал focusWindowChanged приложения - окно
    получает фокус, когда открывается)."""

    def __init__(self, root):
        from qgis.PyQt.QtWidgets import QApplication
        self.root = root
        self.app = QApplication.instance()
        self.app.focusWindowChanged.connect(self._focused)

    def close(self):
        if self.app is None:
            return
        try:
            self.app.focusWindowChanged.disconnect(self._focused)
        except (TypeError, RuntimeError):
            # Связь уже снята: окно закрывается второй раз.
            self.app = None

    def apply_all(self):
        """Окно глобуса и все открытые окна модуля."""
        title_bar(self.root)
        for widget in self.root.findChildren(QWidget):
            if widget.isWindow() and widget.isVisible():
                title_bar(widget)

    def _focused(self, window):
        from qgis.PyQt.QtWidgets import QApplication
        widget = QApplication.activeWindow()
        probe = widget
        while probe is not None:
            if probe is self.root:
                title_bar(widget)
                return
            probe = probe.parentWidget()


def dress(dialog):
    """Окно модуля без родителя-окна глобуса, например «О модуле» из
    меню QGIS: правила сохранённого оформления."""
    from qgis.core import QgsSettings
    name = QgsSettings().value(THEME_KEY, DARK)
    name = name if name in THEMES else DARK
    dialog.setStyleSheet(window_style(name))
    title_bar(dialog, name == DARK)


def plate(widget, name, kind="QFrame", label=False):
    """Плашка kind#name на виджете: имя, стиль и метка для restyle.
    label - у подписи-плашки свой цвет текста и поля."""
    widget.setObjectName(name)
    widget.setProperty("planetxPlate", "{}|{}".format(kind, int(label)))
    widget.setStyleSheet(_plate_sheet(name, kind, label))


def _plate_sheet(name, kind, label):
    sheet = plate_style(name, kind)
    if label:
        sheet += " {}#{} {{ color: {}; padding: 3px 6px; }}".format(
            kind, name, _rgba(TEXT))
    return sheet


# Значки набора по cacheKey: имя, свой ли цвет, стрелка меню, сторона.
_ICONS = {}


def restyle(root):
    """Перекрасить плашки, значки набора и окна модуля под root."""
    widgets = [root] + list(root.findChildren(QWidget))
    for widget in widgets:
        found = widget.property("planetxPlate")
        if found:
            kind, label = str(found).split("|")
            widget.setStyleSheet(_plate_sheet(widget.objectName(), kind,
                                              label == "1"))
        if isinstance(widget, QAbstractButton):
            _reicon(widget)
        for action in widget.actions():
            _reicon(action)
        widget.update()
    for action in root.findChildren(QAction):
        _reicon(action)


def _reicon(item):
    found = _ICONS.get(item.icon().cacheKey())
    if found is not None:
        name, menu, side = found
        item.setIcon(icon(name, side=side, menu=menu))


def menu_rules(selector):
    """Правила стиля выпадающего меню selector в цветах плашки, просьба
    автора от 17 октября 2026 года. Фигурные скобки удвоены - строка
    идёт в format плашки."""
    return (
        "{sel} {{{{ color: {{text}}; background: {menu}; border: 1px solid "
        "{{border}}; border-radius: 6px; padding: 4px 0; }}}}"
        "{sel}::item {{{{ padding: 4px 22px 4px 22px; background: "
        "transparent; }}}}"
        "{sel}::item:selected {{{{ background: {{checked}}; }}}}"
        "{sel}::item:disabled {{{{ color: {{muted}}; }}}}"
        "{sel}::separator {{{{ height: 1px; background: {{border}}; "
        "margin: 4px 8px; }}}}"
        "{sel}::indicator {{{{ width: 12px; height: 12px; left: 6px; }}}}"
    ).format(sel=selector, menu=_rgba(MENU))


def menu_style():
    """Стиль меню, которое живёт вне плашки (setStyleSheet самого меню)."""
    return menu_rules("QMenu").format(
        text=_rgba(TEXT), muted=_rgba(MUTED), border=_rgba(BORDER),
        checked=_rgba(CHECKED))


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
        "background: {list}; selection-background-color: "
        "{checked}; }}"
        "{kind}#{name} QSlider::groove:horizontal {{ height: 4px; "
        "background: {border}; border-radius: 2px; }}"
        "{kind}#{name} QSlider::sub-page:horizontal {{ background: "
        "{accent}; border-radius: 2px; }}"
        "{kind}#{name} QSlider::handle:horizontal {{ width: 12px; "
        "margin: -5px 0; border-radius: 6px; background: {text}; }}"
        + menu_rules("{kind}#{name} QMenu")
    ).format(kind=kind, name=name, plate=_rgba(PLATE), border=_rgba(BORDER),
             text=_rgba(TEXT), muted=_rgba(MUTED), hover=_rgba(HOVER),
             checked=_rgba(CHECKED), accent=_rgba(ACCENT),
             list=_rgba(LIST))


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
    elif name == "copy":
        # Копия вида в буфер обмена: два листа один на другом.
        p.drawRoundedRect(QRectF(4, 3, 12, 14), 1.5, 1.5)
        p.drawRoundedRect(QRectF(8, 7, 12, 14), 1.5, 1.5)
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
    own = color is None
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
    out = QIcon(pixmap)
    if own:
        _ICONS[out.cacheKey()] = (name, menu, side)
    return out


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
