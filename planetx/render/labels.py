# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Надписи населённых пунктов, как в Google Earth.

Надпись стоит на экране прямо и не поворачивается вместе с Землёй.
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
import time
from collections import deque

import numpy as np
from OpenGL import GL
from OpenGL.raw.GL.VERSION.GL_1_1 import glDrawArrays as raw_draw_arrays
from OpenGL.raw.GL.VERSION.GL_1_5 import (glBeginQuery, glEndQuery,
                                          glGetQueryObjectuiv)
from qgis.PyQt.QtCore import QPointF, QRectF, Qt
from qgis.PyQt.QtGui import (QBrush, QColor, QFont, QFontMetricsF, QImage,
                             QPainter, QPainterPath, QPen, QPolygonF)

from ..core.ellipsoid import geodetic_to_ecef, surface_normal
from ..core.places import KIND, identity, select_labels
from ..i18n import tr
from ..qt_compat import enum
from . import gpu
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
}
# Табличка номера дороги: европейский маршрут зелёный, как на знаках,
# остальные тёмные.
SHIELD_E = QColor(30, 125, 70, 235)
SHIELD = QColor(55, 58, 66, 235)
PIN = QColor(219, 50, 54, 255)  # метка найденного места
MARK = QColor(255, 214, 0, 255)  # метка своего объекта, как в Google Earth
# Крупный город - город или столица с рангом OpenMapTiles не больше
# BIG_RANK. Его надпись на BIG_STEP пикселей крупнее и полужирная,
# иначе Пермь терялась среди окрестных деревень. Жирный шрифт
# и шаг 3 пикселя автор счёл слишком громкими.
BIG_RANK = 4
BIG_STEP = 2
MEDIUM = enum(QFont, "Weight", "Medium")
PREMULTIPLIED = enum(QImage, "Format", "Format_RGBA8888_Premultiplied")
ROUND_JOIN = enum(Qt, "PenJoinStyle", "RoundJoin")


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
            halo = QPen(HALO, 2.0 * self.halo)
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
        self.program = None
        self.vao = None
        self.vbo = None
        self.texture = None
        self.ratio = 1.0
        self.styles = {}
        self.entries = {}  # (класс, текст) -> (u0, v0, u1, v1, w, h, ax, ay)
        self.atlas = _Atlas()
        self.shown = set()  # пункты, видные в прошлом кадре
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
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        stride = 5 * 4
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                 ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                 ctypes.c_void_p(12))
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self.texture = GL.glGenTextures(1)
        self._clear_atlas()
        self.point_program = gpu.build_program(POINT_VERTEX, POINT_FRAGMENT)
        self.point_vao = GL.glGenVertexArrays(1)
        self.point_vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self.point_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.point_vbo)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12,
                                 ctypes.c_void_p(0))
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def _clear_atlas(self):
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA8, ATLAS, ATLAS, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                        np.zeros((ATLAS, ATLAS, 4), dtype=np.uint8))
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_MAX_LEVEL, 0)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
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
        for name in ("_ver", "_tier"):
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
                self._ver[row] = NO_HEIGHT
            rows.append(row)
        rows = np.asarray(rows, dtype=np.int64)
        # Неполный список не запоминается, следующий кадр доразметит его.
        self._list = None if self._more else places
        self._rows = rows
        return rows

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
            for row in np.concatenate([new, old]):
                place = self._places[row]
                h = height_at(place.lat, place.lon) if height_at else 0.0
                h += place.lift or 0.0
                self._p[row] = geodetic_to_ecef(place.lat, place.lon, h)
                self._ver[row] = version
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
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        GL.glTexSubImage2D(GL.GL_TEXTURE_2D, 0, x, y, w, h, GL.GL_RGBA,
                           GL.GL_UNSIGNED_BYTE, rgba)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        _, _, ax, ay = self._layout(place)
        entry = (x / ATLAS, y / ATLAS, (x + w) / ATLAS, (y + h) / ATLAS,
                 w, h, ax, ay)
        self.entries[key] = entry
        return entry

    def draw(self, camera, projection, places, height_at, version, ratio):
        """Выбрать и нарисовать надписи кадра.

        Вызывается после тайлов, буфер глубины кадра заполнен.
        projection - матрица проекции кадра 4×4. ratio - пикселей кадра
        на логический пиксель. Возвращает количество надписей.
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
        entries = [self.hidden.get(key) for key in keys]
        unknown = any(e is None or e[1] != stamp for e in entries)
        keep = [n for n, e in enumerate(entries)
                if e is not None and not e[0]]
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
        new = 0
        raster_start = time.perf_counter()
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
            quads.append((left, top, left + w, top + h, u0, v0, u1, v1,
                          alpha[n]))
            shown.add(keys[n])
        self.shown = shown
        self.pending = self.pending or unknown or self._more
        if quads:
            self._draw_quads(quads, camera.width, camera.height)
        self.count = len(quads)
        return self.count

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
        GL.glUseProgram(self.point_program)
        GL.glBindVertexArray(self.point_vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.point_vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STREAM_DRAW)
        GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_DEPTH_TEST)
        for n, query in enumerate(queries):
            glBeginQuery(GL.GL_ANY_SAMPLES_PASSED, query)
            raw_draw_arrays(GL.GL_POINTS, n, 1)
            glEndQuery(GL.GL_ANY_SAMPLES_PASSED)
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)
        self.batches.append((queries, [keys[n] for n in order], stamp))

    def _collect(self):
        """Забрать готовые ответы запросов видимости, по порядку.

        Готовность проверяется по последнему запросу пачки, ответы
        приходят по порядку. Неготовая пачка ждёт следующего кадра.
        """
        value = ctypes.c_uint(0)
        while self.batches:
            queries, keys, stamp = self.batches[0]
            glGetQueryObjectuiv(queries[-1], GL.GL_QUERY_RESULT_AVAILABLE,
                                ctypes.byref(value))
            if not value.value:
                break
            self.batches.popleft()
            if len(self.hidden) > 20000:
                self.hidden.clear()
            for query, key in zip(queries, keys):
                glGetQueryObjectuiv(query, GL.GL_QUERY_RESULT,
                                    ctypes.byref(value))
                self.hidden[key] = (value.value == 0, stamp)
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
        GL.glUseProgram(self.program)
        GL.glUniform1i(self.u_atlas, 0)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STREAM_DRAW)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_ONE, GL.GL_ONE_MINUS_SRC_ALPHA)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 6 * len(q))
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDisable(GL.GL_BLEND)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        GL.glBindVertexArray(0)
