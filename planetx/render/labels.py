# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Надписи населённых пунктов, как в Google Earth.

Надпись стоит на экране ровно и не поворачивается вместе с Землёй.
Текст с тёмной обводкой растрируется один раз в картинку и кладётся
в атлас - общую текстуру всех надписей. Каждый кадр надписи ставятся
прямоугольниками одним вызовом отрисовки.

Какие надписи видны:

- точка пункта перед камерой, в окне и на обращённой к глазу стороне
  Земли;
- надпись не задевает более важную, выбор в core/places.py;
- точка пункта не закрыта рельефом. Надпись видна или скрыта целиком,
  как в Google Earth. После тайлов для каждого проверяемого пункта
  рисуется невидимая точка с проверкой глубины внутри запроса
  видимости OpenGL. Ответ забирается, когда он готов, обычно через
  кадр-два, и процессор видеокарту не ждёт.

  До запросов пробовались три способа, замеры 26 сентября 2026 года.
  Проверка глубины по каждому пикселю текста обрезала надписи у края
  диска: ближняя к глазу часть шара закрывала надпись дальнего пункта.
  Чтение глубины glReadPixels в конце своего кадра ждало видеокарту,
  кадров над Пермью было 28 в секунду против 52 без надписей. Чтение
  из буфера окна в начале следующего кадра давало мусор: Qt 6
  объявляет глубину окна недействительной после кадра. Чтение из своей
  копии глубины двухкадровой давности всё равно ждало видеокарту 7 мс.

Всё, что трогает OpenGL, вызывается из paintGL при текущем контексте.
"""
import ctypes
import math
import os
import time
from collections import deque

import numpy as np
from OpenGL import GL
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage,
                             QPainter, QPainterPath, QPen, QPolygonF)

from ..core import icons
from ..core.ellipsoid import geodetic_to_ecef, surface_normal
from ..core.layer_labels import dark
from ..core.places import KIND, identity, select_labels
from ..i18n import tr
from ..qt_compat import enum
from . import gpu
from .gpu import gl
from .shaders import (LABEL_FRAGMENT, LABEL_VERTEX, POINT_FRAGMENT,
                      POINT_VERTEX)

ATLAS = 2048  # сторона атласа надписей, пикселей
# Проверочная точка придвигается к глазу на такую долю расстояния.
# Пункт закрыт, если рельеф в его пикселе ещё ближе. Меньший запас
# путает пункт с самим склоном под ним.
OCCLUSION_MARGIN = 0.03
# Подъём проверочной точки над пунктом, доля расстояния до глаза.
# Сетка тайла собрана по высотам грубее, чем высота пункта, и точка
# на самом пункте может оказаться под нарисованной землёй. При 1 %
# пункт в 100 км поднимался на километр и выглядывал из-за хребта.
LIFT = 0.002
MAX_TESTS = 32  # пунктов проверяется за кадр, не больше
NO_HEIGHT = -2  # версия высот новой строки таблицы пунктов
NEW_PER_FRAME = 24  # новых надписей растрируется за кадр, не больше
# Новых пунктов размечается за кадр, не больше. Тайл с сотнями пунктов
# размечался одним кадром до 69 мс, проезд тура над Екатеринбургом
# 28 сентября 2026 года. Остальные пункты ждут следующих кадров.
NEW_ROWS_PER_FRAME = 60
# Растровка новых надписей за кадр, секунд, не больше. Одна надпись
# с обводкой стоит 2-3 мс, 24 надписи давали кадр до 80 мс.
RASTER_TIME = 0.004
HEIGHTS_PER_FRAME = 80  # высот пунктов уточняется за кадр, не больше
MAX_CANDIDATES = 600  # пунктов в окне, которые спорят за место
# Значков своих меток без подписи в кадре, не больше.
MAX_ICONS = 20000
# Зазор между надписями, логических пикселей. При 3 пикселях надписи
# из космоса шли сплошным ковром, 26 сентября 2026 года.
PADDING = 10.0
# Обводка: цвет и толщина в логических пикселях. Тонкая полупрозрачная
# обводка читается на снимках и не делает текст громким.
HALO = QColor(0, 0, 0, 140)
HALO_WIDTH = 1.4
# Надпись гаснет, когда пункт уходит к горизонту. Мера - синус угла
# между лучом зрения и касательной плоскостью в пункте. Ниже FADE_LOW
# надписи нет, выше FADE_HIGH она целиком.
FADE_LOW = 0.12
FADE_HIGH = 0.35
# Новая надпись проявляется за столько секунд, просьба автора от
# 16 октября 2026 года. Своя метка - точка профиля, длина отрезка -
# видна сразу: её текст меняется с каждым шагом курсора.
LABEL_FADE = 0.3
# Точечная метка «Моих меток» под курсором поднимается: значок
# с подписью за HOP_TIME секунд встаёт на HOP_HEIGHT логических пикселей
# выше, держится, пока курсор на нём, и опускается, когда курсор уходит,
# как в Google Earth. Просьба автора от 20 октября 2026 года, величины -
# выбор помощника.
HOP_TIME = 0.15
HOP_HEIGHT = 7.0

# Вид надписи по классу: кегль в логических пикселях, жирный, курсив,
# цвет с прозрачностью, размер значка и значок. Значок - точка «dot»,
# треугольник вершины «peak», квадрат аэропорта «square», табличка
# номера дороги «shield», метка найденного места «pin» или жёлтая
# метка своего объекта «yellow». Без значка
# надпись стоит серединой на пункте.
STYLES = {
    "search": (13, False, False, QColor(255, 255, 255, 250), 5.0,
               "pin"),
    "mark": (12, False, False, QColor(255, 255, 255, 245), 4.5,
             "yellow"),
    "country": (14, False, False, QColor(255, 244, 214, 235), 0.0, None),
    "capital": (13, False, False, QColor(255, 255, 255, 240), 3.0, "dot"),
    "city": (13, False, False, QColor(255, 255, 255, 235), 2.5, "dot"),
    "state": (11, False, True, QColor(230, 230, 230, 200), 0.0, None),
    "water": (12, False, True, QColor(165, 210, 255, 230), 0.0, None),
    "town": (12, False, False, QColor(255, 255, 255, 225), 2.2, "dot"),
    "park": (11, False, True, QColor(160, 225, 150, 220), 0.0, None),
    "peak": (11, False, False, QColor(255, 236, 205, 225), 3.2, "peak"),
    "airport": (11, False, False, QColor(255, 255, 255, 225), 2.6,
                "square"),
    "road_ref": (10, True, False, QColor(255, 255, 255, 245), 0.0,
                 "shield"),
    "village": (11, False, False, QColor(240, 240, 240, 210), 1.8, "dot"),
    # Подпись линии координатной сетки, без значка.
    "grid": (11, False, False, QColor(255, 255, 255, 235), 0.0, None),
    # Подпись слоя проекта по умолчанию. Цвет и кегль подписи слоя
    # приходят из QGIS, для них стиль заводит layer_style.
    "layer": (12, False, False, QColor(255, 255, 255, 245), 0.0, None),
    # Длина отрезка линейки, жёлтая, как её линия.
    "ruler": (12, True, False, QColor(255, 214, 0, 250), 0.0, None),
    # Экватор, тропики и полярные круги, жёлтые, как в Google Earth.
    "circle": (11, False, False, QColor(255, 230, 0, 240), 0.0, None),
    # Название литосферной плиты, строка «Границы плит».
    "plate": (13, True, False, QColor(255, 200, 140, 240), 0.0, None),
    # Число поля прогноза погоды над его раскраской.
    "value": (13, True, False, QColor(255, 255, 255, 250), 0.0, None),
    # Статья Википедии рядом: голубой кружок с белым кольцом.
    "wiki": (11, False, False, QColor(205, 228, 255, 235), 3.4, "wiki"),
}
# Табличка номера дороги: европейский маршрут зелёный, как на знаках,
# остальные тёмные.
SHIELD_E = QColor(30, 125, 70, 235)
SHIELD = QColor(55, 58, 66, 235)
PIN = QColor(219, 50, 54, 255)  # метка найденного места
MARK = QColor(255, 214, 0, 255)  # метка своего объекта, как в Google Earth
WIKI = QColor(45, 110, 205, 255)  # кружок статьи Википедии
# Крупный город - город или столица с рангом OpenMapTiles не больше
# BIG_RANK. Его надпись на BIG_STEP пикселей крупнее и полужирная,
# иначе Пермь терялась среди окрестных деревень. Жирный шрифт
# и шаг 3 пикселя автор счёл слишком громкими.
BIG_RANK = 4
BIG_STEP = 2
MEDIUM = enum(QFont, "Weight", "Medium")
PREMULTIPLIED = enum(QImage, "Format", "Format_RGBA8888_Premultiplied")
ROUND_JOIN = enum(Qt, "PenJoinStyle", "RoundJoin")


HALO_LIGHT = QColor(255, 255, 255, 200)  # обводка тёмной подписи слоя
GAP_DOT = 3.0  # отступ подписи точки слоя от самой точки, пикселей
ICON_DOT = 8.0  # полуразмер значка метки, логических пикселей
ROUND_DOT = 4.5  # полуразмер кружка метки


# Пределы размеров значка и подписи из KML, доли обычного.
SCALE_RANGE = (0.25, 4.0)


def _clamp_scale(value):
    return min(max(float(value), SCALE_RANGE[0]), SCALE_RANGE[1])


def icon_style(icon, rgba, icon_scale=1.0, label=None, label_scale=1.0,
               turn=0.0):
    """Класс надписи для значка icon (core/icons.py) цвета rgba. Стиль
    заводится один раз на сочетание, место в очереди - как у «mark».

    icon_scale - размер значка, label - цвет подписи RGBA или None
    (белый), label_scale - размер подписи, доли обычного, как scale
    IconStyle и LabelStyle KML. turn - поворот значка на экране по
    часовой стрелке, градусы."""
    marker = "icon:%s:%s" % (icon, ",".join(str(int(c)) for c in rgba))
    if turn:
        marker += ":%g" % round(turn, 1)
    plain = abs(icon_scale - 1.0) < 1e-6 and label is None \
        and abs(label_scale - 1.0) < 1e-6 and not turn
    kind = marker if plain else "%s:%g:%s:%g" % (
        marker, icon_scale, ",".join(str(int(c)) for c in label or ()),
        label_scale)
    if kind not in STYLES:
        dot = ROUND_DOT if icon == icons.DEFAULT else ICON_DOT
        # Размер значка 0 - значка нет, как в Google Earth.
        dot = dot * _clamp_scale(icon_scale) if icon_scale > 0.0 else 0.0
        size = 12.0 * _clamp_scale(label_scale) if label_scale > 0.0 \
            else 12.0
        color = QColor(*label) if label else QColor(255, 255, 255, 245)
        STYLES[kind] = (int(round(size)), False, False, color, dot, marker)
        KIND[kind] = KIND["mark"]
    return kind


def svg_file(relative):
    """Полный путь SVG из библиотеки QGIS или None."""
    for folder in QgsApplication.svgPaths():
        path = os.path.join(folder, relative)
        if os.path.exists(path):
            return path
    return None


def lift_step(share, up, dt):
    """Доля подъёма метки через dt секунд: к 1 под курсором, к 0 без
    него, весь путь за HOP_TIME."""
    step = max(dt, 0.0) / HOP_TIME
    return min(1.0, share + step) if up else max(0.0, share - step)


def lift_pixels(share):
    """Подъём метки в логических пикселях при доле share: плавный
    разгон и остановка."""
    share = min(max(share, 0.0), 1.0)
    return HOP_HEIGHT * share * share * (3.0 - 2.0 * share)


def _draw_icon(painter, marker, cx, cy, r, halo):
    """Значок метки: SVG из библиотеки QGIS, окрашенный цветом метки,
    кружок - без SVG. Нет файла - кружок."""
    parts = marker.split(":")
    icon, rgba = parts[1], parts[2]
    turn = float(parts[3]) if len(parts) > 3 else 0.0
    color = QColor(*(int(v) for v in rgba.split(",")))
    path = svg_file(icons.svg(icon)) if icon != icons.DEFAULT else None
    if path is not None:
        size = 2.0 * r
        image, _ = QgsApplication.svgCache().svgAsImage(
            path, size, color, QColor(40, 30, 0, 230), 1.0, 1.0)
        if not image.isNull():
            painter.save()
            painter.translate(cx, cy)
            painter.rotate(turn)
            painter.drawImage(QPointF(-image.width() / 2.0,
                                      -image.height() / 2.0), image)
            painter.restore()
            return
    painter.setPen(QPen(QColor(60, 40, 0, 230), halo))
    painter.setBrush(QBrush(color))
    painter.drawEllipse(QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r))


def layer_style(size, rgba, point):
    """Вид надписи подписи слоя проекта: кегль в логических пикселях,
    цвет (r, g, b, a). У точки текст стоит справа от неё, значок
    QGIS не закрывается. Возвращает класс надписи, он заводится один
    раз на сочетание вида. Место в очереди - как у класса «layer»."""
    kind = "layer:%d:%s:%d" % (round(size), ",".join(map(str, rgba)),
                               int(bool(point)))
    if kind not in STYLES:
        STYLES[kind] = (int(round(size)), False, False, QColor(*rgba),
                        GAP_DOT if point else 0.0, "gap" if point else None)
        KIND[kind] = KIND["layer"]
    return kind


class _Style:
    """Шрифт, значок и размеры надписи одного класса при данном
    масштабе."""

    def __init__(self, kind, ratio, big=False):
        size, bold, italic, color, dot, marker = STYLES[kind]
        if big:
            size += BIG_STEP
            dot += 0.5
        self.font = QFont()
        self.font.setPixelSize(max(1, int(round(size * ratio))))
        self.font.setBold(bold)
        if big:
            self.font.setWeight(MEDIUM)
        self.font.setItalic(italic)
        self.metrics = QFontMetricsF(self.font)
        self.color = color
        # Тёмная подпись слоя проекта - со светлой обводкой.
        self.halo_color = HALO_LIGHT if dark(
            (color.red(), color.green(), color.blue())) else HALO
        self.marker = marker
        self.dot = dot * ratio if marker not in (None, "shield") else 0.0
        self.halo = HALO_WIDTH * ratio
        self.gap = 3.0 * ratio
        self.pad = 3.0 * ratio  # поле таблички вокруг текста

    def layout(self, text):
        """Размер картинки надписи и точка привязки в ней."""
        width = self.metrics.horizontalAdvance(text)
        height = self.metrics.ascent() + self.metrics.descent()
        halo = self.halo
        if self.marker == "shield":
            w = width + 2.0 * self.pad + 2.0
            h = height + self.pad + 2.0
            anchor = (w / 2.0, h / 2.0)
        elif self.dot:
            w = halo + 2.0 * self.dot + self.gap + width + halo
            h = max(height, 2.0 * self.dot) + 2.0 * halo
            anchor = (halo + self.dot, h / 2.0)
        else:
            w = width + 2.0 * halo
            h = height + 2.0 * halo
            anchor = (w / 2.0, h / 2.0)
        return int(math.ceil(w)), int(math.ceil(h)), anchor

    def raster(self, text):
        """Картинка надписи, массив (h, w, 4) с премноженной альфой."""
        w, h, anchor = self.layout(text)
        image = QImage(w, h, PREMULTIPLIED)
        image.fill(0)
        painter = QPainter(image)
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        top = (h - self.metrics.ascent() - self.metrics.descent()) / 2.0
        if self.marker == "shield":
            fill = SHIELD_E if text.startswith("E") else SHIELD
            painter.setPen(QPen(QColor(255, 255, 255, 200), 1.0))
            painter.setBrush(QBrush(fill))
            painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1.0, h - 1.0),
                                    self.pad, self.pad)
            path = QPainterPath()
            path.addText(QPointF(self.pad + 1.0, top + self.metrics.ascent()),
                         self.font, text)
            painter.fillPath(path, QBrush(self.color))
        else:
            halo = QPen(self.halo_color, 2.0 * self.halo)
            halo.setJoinStyle(ROUND_JOIN)
            x = self.halo + (2.0 * self.dot + self.gap if self.dot else 0.0)
            path = QPainterPath()
            path.addText(QPointF(x, top + self.metrics.ascent()), self.font,
                         text)
            painter.strokePath(path, halo)
            painter.fillPath(path, QBrush(self.color))
            if self.dot:
                self._marker(painter, anchor)
        painter.end()
        ptr = image.constBits()
        ptr.setsize(image.sizeInBytes())
        rows = np.frombuffer(ptr, dtype=np.uint8).reshape(
            h, image.bytesPerLine())
        return rows[:, :w * 4].reshape(h, w, 4).copy()

    def _marker(self, painter, anchor):
        if self.marker == "gap":
            return  # точку слоя рисует QGIS в картинке наложения
        if self.marker.startswith("icon:"):
            _draw_icon(painter, self.marker, anchor[0], anchor[1],
                       self.dot, self.halo * 0.8)
            return
        painter.setPen(QPen(HALO, self.halo * 0.8))
        painter.setBrush(QBrush(self.color))
        r = self.dot
        cx, cy = anchor
        if self.marker == "peak":
            painter.drawPolygon(QPolygonF([
                QPointF(cx, cy - r), QPointF(cx + r, cy + r * 0.8),
                QPointF(cx - r, cy + r * 0.8)]))
        elif self.marker == "pin":
            # Метка найденного места: красный круг с белым кольцом.
            painter.setPen(QPen(QColor(255, 255, 255, 240), r * 0.45))
            painter.setBrush(QBrush(PIN))
            painter.drawEllipse(QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r))
        elif self.marker == "yellow":
            painter.setPen(QPen(QColor(60, 40, 0, 230), r * 0.35))
            painter.setBrush(QBrush(MARK))
            painter.drawEllipse(QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r))
        elif self.marker == "wiki":
            painter.setPen(QPen(QColor(255, 255, 255, 235), r * 0.4))
            painter.setBrush(QBrush(WIKI))
            painter.drawEllipse(QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r))
        elif self.marker == "square":
            painter.drawRect(QRectF(cx - r * 0.8, cy - r * 0.8,
                                    1.6 * r, 1.6 * r))
        else:
            painter.drawEllipse(QRectF(cx - r, cy - r, 2.0 * r, 2.0 * r))


def label_text(place):
    """Текст надписи пункта. У вершины после названия высота."""
    if place.kind == "peak" and place.info is not None:
        return tr("{name}, {ele} м", name=place.name, ele=place.info)
    return place.name


class _Atlas:
    """Раскладка картинок надписей по полкам атласа."""

    def __init__(self, size=ATLAS):
        self.size = size
        self.shelves = []  # [y, высота, занятая ширина]
        self.bottom = 0

    def place(self, w, h):
        """Левый верхний угол места под картинку или None, атлас полон."""
        if w > self.size:
            return None
        for shelf in self.shelves:
            y, height, used = shelf
            if h <= height <= h * 1.4 and used + w <= self.size:
                shelf[2] += w
                return used, y
        if self.bottom + h > self.size:
            return None
        self.shelves.append([self.bottom, h, w])
        self.bottom += h
        return 0, self.bottom - h


class Labels:
    """Надписи пунктов: атлас в видеокарте и отбор на кадр."""

    def __init__(self):
        # Высоты рельефа с дном моря для своих меток от дна, ставит
        # вид (GlobeView). None - как у поверхности.
        self.floor_at = None
        self.program = None
        self.vao = None
        self.vbo = None
        self.texture = None
        self.ratio = 1.0
        self.styles = {}
        self.entries = {}  # (класс, текст) -> (u0, v0, u1, v1, w, h, ax, ay)
        self.atlas = _Atlas()
        self.shown = set()  # пункты, видные в прошлом кадре
        # Свои точечные метки прошлого кадра: (номер метки, левый,
        # верхний, правый, нижний край в пикселях кадра), по ним - метка
        # под курсором. hovered - номер метки под курсором или None,
        # lifts - номер - (доля подъёма 0-1, время).
        self.mark_boxes = []
        self.hovered = None
        self.lifts = {}
        # Пункт -> начало проявления, пока надпись проявляется.
        self.born = {}
        # Не все выбранные надписи растрированы или проверены, нужен
        # ещё кадр.
        self.pending = False
        self.count = 0
        # Запросы видимости в работе: номера запросов, пункты, отметка.
        self.batches = deque()
        self.free_queries = []
        # Пункт -> (закрыт рельефом, отметка). Отметка - положение глаза
        # и версия высот, при которых проверен пункт. Проверка с другой
        # отметкой устарела, пункт проверяется снова.
        self.hidden = {}
        self._cursor = 0  # с какого пункта перепроверка по кругу
        # Таблица пунктов: строка на пункт, номер строки по ключу пункта.
        # Точка ECEF, нормаль, версия высот точки, размер надписи
        # (w, h, ax, ay) и класс лежат в массивах по номерам строк.
        # Список пунктов кадра - массив номеров строк, отбор идёт
        # массивами NumPy. При повороте набор тайлов пунктов меняется
        # почти каждый кадр, и пересчёт по самому списку стоил 4 мс.
        self._row = {}
        self._keys = []
        self._places = []
        self._p = np.empty((0, 3))
        self._n = np.empty((0, 3))
        self._ver = np.empty(0, dtype=np.int64)
        self._size = np.empty((0, 4))
        self._tier = np.empty(0, dtype=np.int64)
        # Строка своей метки со значком - номер её класса в _icon_kinds,
        # иначе -1. Значок такой метки виден и без подписи.
        self._icon = np.empty(0, dtype=np.int64)
        self._icon_kinds = {}  # класс - номер
        self._icon_places = []  # номер - пункт этого класса без текста
        self.icons = 0  # значков без подписи в прошлом кадре
        self._table_ratio = None
        self._list = None
        self._more = False  # список пунктов размечен не весь
        self._rows = None

    # Ресурсы OpenGL.

    def init_gl(self):
        self.program = gpu.build_program(LABEL_VERTEX, LABEL_FRAGMENT)
        self.u_atlas = GL.glGetUniformLocation(self.program, "u_atlas")
        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        stride = 5 * 4
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                 ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                 ctypes.c_void_p(12))
        gl.glBindVertexArray(0)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        # Число, а не массив: атлас привязывает gpu.gl.glBindTexture.
        self.texture = int(np.ravel(GL.glGenTextures(1))[0])
        self._clear_atlas()
        self.point_program = gpu.build_program(POINT_VERTEX, POINT_FRAGMENT)
        self.point_vao = GL.glGenVertexArrays(1)
        self.point_vbo = GL.glGenBuffers(1)
        gl.glBindVertexArray(self.point_vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.point_vbo)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12,
                                 ctypes.c_void_p(0))
        gl.glBindVertexArray(0)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def _clear_atlas(self):
        gl.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, ATLAS, ATLAS, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                        np.zeros((ATLAS, ATLAS, 4), dtype=np.uint8))
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_MAX_LEVEL, 0)):
            gl.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        gl.glBindTexture(GL.GL_TEXTURE_2D, 0)
        self.atlas = _Atlas()
        self.entries = {}

    def release_gl(self):
        if self.program is None:
            return
        GL.glDeleteProgram(self.program)
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteBuffers(1, [self.vbo])
        GL.glDeleteProgram(self.point_program)
        GL.glDeleteVertexArrays(1, [self.point_vao])
        GL.glDeleteBuffers(1, [self.point_vbo])
        queries = self.free_queries + [q for batch in self.batches
                                       for q in batch[0]]
        if queries:
            GL.glDeleteQueries(len(queries), queries)
        self.free_queries = []
        self.batches.clear()
        gpu.delete_texture(self.texture)
        self.program = None

    # Таблица пунктов.

    def _style(self, place):
        key = (place.kind, place.kind in ("city", "capital")
               and place.rank <= BIG_RANK)
        style = self.styles.get(key)
        if style is None:
            style = self.styles[key] = _Style(key[0], self.ratio, key[1])
        return style

    def _layout(self, place):
        w, h, (ax, ay) = self._style(place).layout(label_text(place))
        return (w, h, ax, ay)

    def _grow(self, need):
        size = len(self._ver)
        if need <= size:
            return
        cap = max(need, 2 * size, 256)
        for name, width in (("_p", 3), ("_n", 3), ("_size", 4)):
            grown = np.zeros((cap, width))
            grown[:size] = getattr(self, name)
            setattr(self, name, grown)
        for name in ("_ver", "_tier", "_icon"):
            grown = np.full(cap, -1, dtype=np.int64)
            grown[:size] = getattr(self, name)
            setattr(self, name, grown)

    def _rows_of(self, places):
        """Номера строк таблицы для списка пунктов, новые заводятся.

        Список пунктов меняется, только когда меняется набор тайлов
        пунктов. Для того же списка номера берутся из памяти.
        """
        if self._table_ratio != self.ratio:
            # Другой масштаб экрана - другие размеры надписей.
            for row, place in enumerate(self._places):
                self._size[row] = self._layout(place)
            self._table_ratio = self.ratio
        self._more = False
        if places is self._list:
            return self._rows
        rows = []
        budget = NEW_ROWS_PER_FRAME
        for place in places:
            key = identity(place)
            row = self._row.get(key)
            if row is not None and (place.id or 0) < 0 \
                    and self._places[row] is not place \
                    and (self._places[row].lat, self._places[row].lon) \
                    != (place.lat, place.lon):
                # Своя метка - точка профиля, длина отрезка линейки,
                # подпись сетки - сменила место при том же номере и
                # тексте. Строка переносится на новое место, иначе
                # надпись стояла бы там, где этот текст был раньше:
                # точка профиля прыгала на прежнее место той же высоты.
                self._places[row] = place
                self._n[row] = surface_normal(place.lat, place.lon)
                self._ver[row] = NO_HEIGHT
                # Прежний ответ о видимости остаётся, но устаревшим: до
                # новой проверки надпись показывается по нему. Сброс
                # ответа гасил надпись до проверки, и точка профиля
                # мигала на каждом шаге курсора.
                old = self.hidden.get(key)
                if old is not None:
                    self.hidden[key] = (old[0], None)
            elif row is not None and (place.id or 0) < 0 \
                    and self._places[row].kind != place.kind:
                # Своя метка сменила вид на месте: значок под курсором
                # (highlight StyleMap), правка в окне свойств. Иначе
                # строка держала бы прежний вид.
                self._places[row] = place
                self._size[row] = self._layout(place)
                self._tier[row] = KIND[place.kind]
                self._icon[row] = self._icon_of(place)
            if row is None:
                if budget <= 0:
                    # Пункт размечается в следующих кадрах, пока его
                    # надписи нет.
                    self._more = True
                    continue
                budget -= 1
                row = len(self._keys)
                self._grow(row + 1)
                self._row[key] = row
                self._keys.append(key)
                self._places.append(place)
                self._n[row] = surface_normal(place.lat, place.lon)
                self._size[row] = self._layout(place)
                self._tier[row] = KIND[place.kind]
                self._icon[row] = self._icon_of(place)
                self._ver[row] = NO_HEIGHT
            rows.append(row)
        rows = np.asarray(rows, dtype=np.int64)
        # Неполный список не запоминается, следующий кадр доразметит его.
        self._list = None if self._more else places
        self._rows = rows
        return rows

    def _icon_of(self, place):
        """Номер класса значка своей метки или -1: значок рисуется и там,
        где подписи метки нет места."""
        if (place.id or 0) > -2 or not label_text(place):
            return -1
        style = STYLES.get(place.kind)
        if style is None or not style[4] or not str(
                style[5] or "").startswith("icon:"):
            return -1
        number = self._icon_kinds.get(place.kind)
        if number is None:
            number = self._icon_kinds[place.kind] = len(self._icon_places)
            self._icon_places.append(place._replace(name=""))
        return number

    def _icon_quads(self, rows, inside, px, py, alpha, drawn):
        """Значки своих меток в окне, которым не досталось места для
        подписи: массив прямоугольников для _draw_quads. Как в Google
        Earth - тысячи точек видны значками, подписи у тех, кому есть
        место. Проверки видимости за рельефом у них нет, как у своих
        меток до ответа запроса."""
        icon = self._icon[rows]
        pick = np.nonzero(inside & (icon >= 0))[0]
        if not len(pick):
            return None
        if drawn:
            pick = pick[~np.isin(rows[pick], np.fromiter(
                drawn, dtype=np.int64, count=len(drawn)))]
        pick = pick[:MAX_ICONS]
        if not len(pick):
            return None
        out = np.zeros((len(pick), 9))
        kinds = icon[pick]
        for number in np.unique(kinds):
            entry = self._entry(self._icon_places[number])
            if entry is None:
                continue
            u0, v0, u1, v1, w, h, ax, ay = entry
            mask = kinds == number
            left = np.round(px[pick[mask]] - ax)
            top = np.round(py[pick[mask]] - ay)
            out[mask] = np.stack([
                left, top, left + w, top + h,
                np.full(len(left), u0), np.full(len(left), v0),
                np.full(len(left), u1), np.full(len(left), v1),
                alpha[pick[mask]]], axis=1)
        out = out[out[:, 2] > out[:, 0]]
        return out if len(out) else None

    def _positions(self, rows, height_at, version):
        """Точки пунктов в ECEF и нормали по строкам rows.

        Высота пункта берётся по рельефу. Новый пункт получает высоту
        сразу. После прихода новых высот она уточняется не больше чем
        у HEIGHTS_PER_FRAME пунктов за кадр, остальные пока стоят
        на прежней.
        """
        ver = self._ver[rows]
        stale = rows[ver != version]
        if len(stale):
            new = stale[self._ver[stale] == NO_HEIGHT]
            old = stale[self._ver[stale] != NO_HEIGHT][:HEIGHTS_PER_FRAME]
            todo = np.concatenate([new, old])
            # Высоты всех пунктов разом: height_at берёт массивы широт
            # и долгот (GlobeView.label_heights). По одному пункту опрос
            # высот был заметной долей кадра при облёте новых мест,
            # профиль 15 октября 2026 года.
            places = [self._places[row] for row in todo]
            lats = np.array([p.lat for p in places], dtype=np.float64)
            lons = np.array([p.lon for p in places], dtype=np.float64)
            h = np.asarray(height_at(lats, lons), dtype=np.float64) \
                if height_at else np.zeros(len(todo))
            # Своя метка с режимом высоты от дна или от уровня моря
            # (Place.base, core.features.MODES).
            bases = [getattr(p, "base", None) for p in places]
            if "floor" in bases and height_at and self.floor_at:
                floor = np.array([b == "floor" for b in bases])
                h[floor] = np.asarray(self.floor_at(lats[floor],
                                                    lons[floor]),
                                      dtype=np.float64)
            if "abs" in bases:
                h[np.array([b == "abs" for b in bases])] = 0.0
            h = h + np.array([p.lift or 0.0 for p in places])
            self._p[todo] = geodetic_to_ecef(lats, lons, h)
            self._ver[todo] = version
        return self._p[rows], self._n[rows]

    # Отбор и отрисовка.

    def _entry(self, place):
        """Место надписи в атласе, растрирует новую."""
        key = (place.kind, label_text(place))
        entry = self.entries.get(key)
        if entry is not None:
            return entry
        rgba = self._style(place).raster(label_text(place))
        h, w = rgba.shape[:2]
        spot = self.atlas.place(w, h)
        if spot is None:
            # Атлас полон. Он очищается, видимые надписи растрируются
            # заново в следующих кадрах.
            self._clear_atlas()
            spot = self.atlas.place(w, h)
            if spot is None:
                return None
        x, y = spot
        gl.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        gl.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        gl.tex_region(x, y, w, h, rgba)
        gl.glBindTexture(GL.GL_TEXTURE_2D, 0)
        _, _, ax, ay = self._layout(place)
        entry = (x / ATLAS, y / ATLAS, (x + w) / ATLAS, (y + h) / ATLAS,
                 w, h, ax, ay)
        self.entries[key] = entry
        return entry

    def draw(self, camera, projection, places, height_at, version, ratio,
             fade=True):
        """Выбрать и нарисовать надписи кадра.

        Вызывается после тайлов, буфер глубины кадра заполнен.
        projection - матрица проекции кадра 4×4. ratio - пикселей кадра
        на логический пиксель. fade - проявлять новые надписи, у снимка
        вида нет. Возвращает количество надписей.
        """
        self.count = 0
        self.pending = False
        if self.program is None or not places:
            self.shown = set()
            return 0
        if ratio != self.ratio:
            self.ratio = ratio
            self.styles = {}
            self._clear_atlas()
        self._collect()
        rows = self._rows_of(places)
        if not len(rows):
            self.shown = set()
            self.pending = self._more
            return 0
        points, normals = self._positions(rows, height_at, version)
        eye = camera.eye
        v = points - eye
        cam = v @ camera.rotation
        # Пункт на обращённой к глазу стороне: глаз над касательной
        # плоскостью в пункте. rise - синус угла луча зрения над этой
        # плоскостью, по нему надпись гаснет у горизонта.
        rise = -(v * normals).sum(axis=1) / np.maximum(
            np.linalg.norm(v, axis=1), 1e-9)
        facing = rise > FADE_LOW
        front = cam[:, 2] < 0.0
        clip_w = np.where(front, -cam[:, 2], 1.0)
        t = math.tan(math.radians(camera.fov_y) / 2.0)
        px = (cam[:, 0] / clip_w / (t * camera.aspect) + 1.0) * 0.5 \
            * camera.width
        py = (1.0 - cam[:, 1] / clip_w / t) * 0.5 * camera.height
        inside = front & facing & (px > -50) & (px < camera.width + 50) \
            & (py > -50) & (py < camera.height + 50)
        index = np.nonzero(inside)[0][:MAX_CANDIDATES]
        if not len(index):
            self.shown = set()
            self.pending = self._more
            return 0
        keys = [self._keys[row] for row in rows[index]]
        # Проверочные точки: над пунктом на LIFT и ближе к глазу
        # на OCCLUSION_MARGIN расстояния.
        dist = np.linalg.norm(v[index], axis=1)[:, None]
        test = points[index] + normals[index] * (LIFT * dist)
        test = eye + (test - eye) * (1.0 - OCCLUSION_MARGIN)
        stamp = (tuple(np.round(eye, 1)), version)
        self._test(keys, test, camera, projection, stamp)
        # Пункт без ответа не подписывается, пока его не проверят.
        # Иначе пункт за горой мелькал бы надписью до ответа. Пункт
        # с устаревшей проверкой показывается по ней до новой. Кадры
        # идут, пока все пункты окна не проверены при этой отметке.
        # Своя метка (отрицательный номер) - точка профиля, длина отрезка
        # линейки - показывается и до ответа. Её текст меняется с каждым
        # шагом курсора, у нового текста своя строка, и без этого точка
        # профиля мигала на каждом шаге. За горой её скроет ответ.
        entries = [self.hidden.get(key) for key in keys]
        own = [(self._places[row].id or 0) < 0 for row in rows[index]]
        unknown = any(e is None or e[1] != stamp for e in entries)
        keep = [n for n, e in enumerate(entries)
                if (e is not None and not e[0]) or (e is None and own[n])]
        if not keep:
            self.shown = set()
            self.pending = unknown or self._more
            return 0
        chosen_rows = rows[index[keep]]
        keys = [keys[n] for n in keep]
        x = px[index[keep]]
        y = py[index[keep]]
        alpha = np.clip((rise[index[keep]] - FADE_LOW)
                        / (FADE_HIGH - FADE_LOW), 0.0, 1.0)
        pad = PADDING * ratio
        size = self._size[chosen_rows]
        x0 = x - size[:, 2]
        y0 = y - size[:, 3]
        boxes = np.stack([x0 - pad, y0 - pad, x0 + size[:, 0] + pad,
                          y0 + size[:, 1] + pad], axis=1).tolist()
        tiers = self._tier[chosen_rows].tolist()
        previous = [n for n, key in enumerate(keys) if key in self.shown]
        chosen = select_labels(boxes, tiers, previous)
        quads = []
        shown = set()
        boxes = []
        new = 0
        raster_start = time.perf_counter()
        now = time.monotonic()
        born = {}
        lifts = {}
        # Строки с нарисованной подписью и строки, которые проверка
        # видимости нашла за рельефом, - у них нет отдельного значка.
        drawn = {int(rows[index[n]]) for n, e in enumerate(entries)
                 if e is not None and e[0]}
        for n in chosen:
            place = self._places[chosen_rows[n]]
            if (place.kind, label_text(place)) not in self.entries:
                if new >= NEW_PER_FRAME or new and time.perf_counter() \
                        - raster_start > RASTER_TIME:
                    self.pending = True
                    continue
                new += 1
            entry = self._entry(place)
            if entry is None:
                continue
            u0, v0, u1, v1, w, h, ax, ay = entry
            # Углы по целым пикселям, иначе текст размывается.
            left = round(x[n] - ax)
            top = round(y[n] - ay)
            share = 1.0
            if fade and (place.id or 0) >= 0:
                # Надпись прошлого кадра без отметки уже проявилась.
                start = self.born.get(keys[n]) if keys[n] in self.shown \
                    else now
                if start is not None:
                    share = min(1.0, (now - start) / LABEL_FADE)
                    if share < 1.0:
                        born[keys[n]] = start
            if (place.id or 0) <= -2:
                # Своя точечная метка (render.view._own_marks).
                boxes.append((place.id, left, top, left + w, top + h))
                rise_share, at = self.lifts.get(place.id, (0.0, now))
                rise_share = lift_step(rise_share,
                                       place.id == self.hovered, now - at)
                if rise_share > 0.0 or place.id == self.hovered:
                    lifts[place.id] = (rise_share, now)
                top -= round(lift_pixels(rise_share) * ratio)
            quads.append((left, top, left + w, top + h, u0, v0, u1, v1,
                          alpha[n] * share))
            shown.add(keys[n])
            drawn.add(int(chosen_rows[n]))
        self.shown = shown
        self.mark_boxes = boxes
        self.lifts = lifts
        self.born = born
        if any(0.0 < part < 1.0 or (part == 0.0) == (key == self.hovered)
               for key, (part, _) in lifts.items()):
            self.pending = True
        if born:
            self.pending = True
        self.pending = self.pending or unknown or self._more
        icons = self._icon_quads(
            rows, inside, px, py, np.clip((rise - FADE_LOW)
                                          / (FADE_HIGH - FADE_LOW), 0.0,
                                          1.0), drawn)
        if icons is not None:
            self._draw_quads(icons, camera.width, camera.height)
        if quads:
            self._draw_quads(quads, camera.width, camera.height)
        self.count = len(quads)
        self.icons = 0 if icons is None else len(icons)
        return self.count

    def hover_at(self, x, y):
        """Курсор в точке кадра (x, y), None - ушёл с вида. Возвращает
        номер своей точечной метки под ним или None и True, если метка
        под курсором сменилась: тогда нужен кадр, метка поднимается или
        опускается."""
        key = None
        if x is not None:
            for item, left, top, right, bottom in reversed(self.mark_boxes):
                if left <= x <= right and top <= y <= bottom:
                    key = item
                    break
        if key == self.hovered:
            return False
        self.hovered = key
        return True

    def _test(self, keys, test, camera, projection, stamp):
        """Запросы видимости проверочных точек пунктов.

        keys - ключи пунктов окна, test - их проверочные точки ECEF.
        Первыми проверяются пункты без проверки, затем устаревшие
        и проверенные по кругу, не больше MAX_TESTS за кадр. Когда
        камера движется, устаревают все отметки, и без круга первые
        MAX_TESTS пунктов занимали бы все проверки.
        """
        groups = ([], [], [])  # без проверки, устаревшие, проверенные
        for n, key in enumerate(keys):
            entry = self.hidden.get(key)
            groups[0 if entry is None else 1 if entry[1] != stamp
                   else 2].append(n)
        order = list(groups[0])
        for group in groups[1:]:
            if group:
                start = self._cursor % len(group)
                order += group[start:] + group[:start]
        self._cursor += MAX_TESTS
        order = order[:MAX_TESTS]
        if not order:
            return
        cam = (test[order] - camera.eye) @ camera.rotation
        clip = np.concatenate([cam, np.ones((len(order), 1))], axis=1) \
            @ projection.T
        ndc = clip[:, :3] / clip[:, 3:4]
        # Пункт у края окна проверяется по пикселю на краю.
        ndc[:, :2] = np.clip(ndc[:, :2], -0.999, 0.999)
        data = np.ascontiguousarray(ndc, dtype=np.float32)
        while len(self.free_queries) < len(order):
            self.free_queries.extend(
                int(q) for q in np.ravel(GL.glGenQueries(16)))
        queries = [self.free_queries.pop() for _ in order]
        gpu.gl.glUseProgram(self.point_program)
        gpu.gl.glBindVertexArray(self.point_vao)
        gpu.gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.point_vbo)
        gl.stream_data(GL.GL_ARRAY_BUFFER, data)
        gl.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE)
        gpu.gl.glDepthMask(GL.GL_FALSE)
        gpu.gl.glEnable(GL.GL_DEPTH_TEST)
        for n, query in enumerate(queries):
            gl.glBeginQuery(GL.GL_ANY_SAMPLES_PASSED, query)
            gl.glDrawArrays(GL.GL_POINTS, n, 1)
            gl.glEndQuery(GL.GL_ANY_SAMPLES_PASSED)
        gl.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
        gpu.gl.glDepthMask(GL.GL_TRUE)
        gpu.gl.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        gpu.gl.glBindVertexArray(0)
        self.batches.append((queries, [keys[n] for n in order], stamp))

    def _collect(self):
        """Забрать готовые ответы запросов видимости, по порядку.

        Готовность проверяется по последнему запросу пачки, ответы
        приходят по порядку. Неготовая пачка ждёт следующего кадра.
        Ответ пишется в массив ctypes, а не через byref. PyOpenGL
        до 3.1.10 на Python 3.12 не принимает byref.
        """
        value = (ctypes.c_uint * 1)()
        while self.batches:
            queries, keys, stamp = self.batches[0]
            gl.query_uint(queries[-1], GL.GL_QUERY_RESULT_AVAILABLE, value)
            if not value[0]:
                break
            self.batches.popleft()
            if len(self.hidden) > 20000:
                self.hidden.clear()
            for query, key in zip(queries, keys):
                gl.query_uint(query, GL.GL_QUERY_RESULT, value)
                self.hidden[key] = (value[0] == 0, stamp)
            self.free_queries.extend(queries)

    def _draw_quads(self, quads, width, height):
        """Прямоугольники надписей одним вызовом, без проверки глубины."""
        q = np.array(quads, dtype=np.float64)
        x0 = q[:, 0] / width * 2.0 - 1.0
        x1 = q[:, 2] / width * 2.0 - 1.0
        y0 = 1.0 - q[:, 1] / height * 2.0
        y1 = 1.0 - q[:, 3] / height * 2.0
        u0, v0, u1, v1 = q[:, 4], q[:, 5], q[:, 6], q[:, 7]
        alpha = q[:, 8]
        corners = [(x0, y0, u0, v0), (x0, y1, u0, v1), (x1, y0, u1, v0),
                   (x1, y0, u1, v0), (x0, y1, u0, v1), (x1, y1, u1, v1)]
        data = np.zeros((len(q), 6, 5), dtype=np.float32)
        for k, (x, y, u, vv) in enumerate(corners):
            data[:, k, 0] = x
            data[:, k, 1] = y
            data[:, k, 2] = alpha
            data[:, k, 3] = u
            data[:, k, 4] = vv
        gpu.gl.glUseProgram(self.program)
        gpu.gl.glUniform1i(self.u_atlas, 0)
        gpu.gl.glActiveTexture(GL.GL_TEXTURE0)
        gpu.gl.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        gpu.gl.glBindVertexArray(self.vao)
        gpu.gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.stream_data(GL.GL_ARRAY_BUFFER, data)
        gpu.gl.glEnable(GL.GL_BLEND)
        gl.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        gpu.gl.glDisable(GL.GL_DEPTH_TEST)
        gpu.gl.glDrawArrays(GL.GL_TRIANGLES, 0, 6 * len(q))
        gpu.gl.glEnable(GL.GL_DEPTH_TEST)
        gpu.gl.glDisable(GL.GL_BLEND)
        gpu.gl.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        gpu.gl.glBindVertexArray(0)
