# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои объекты глобуса в видеокарте: линии и заливка многоугольников.

Расчёт вершин - в core/features.py. Здесь буферы OpenGL и отрисовка.
На объект свой массив вершин и свой вызов отрисовки. Путь кадра - как
у тайлов (gpu.draw_batch): матрицы всех объектов одной операцией NumPy,
вызовы через указатели без проверки ошибок после каждого. Через
PyOpenGL 29 провинций Афганистана рисовались 10 мс за кадр.

Вершины садятся на рельеф по высотам, которые есть на момент сборки,
и поднимаются на высоту объекта. Выдавленный объект получает стену
до земли, выдавленная точка - стойку. Стена рисуется цветом заливки,
у линии - её цветом с прозрачностью WALL_ALPHA.
Контур объекта (core.features.geometry) считается один раз. Пришли
новые высоты - объекты заново садятся на рельеф частями, не дольше
REBUILD_TIME за кадр, прочие пока рисуются по прежним высотам. Новый
или изменённый объект собирается сразу. Точки рисует система надписей,
см. view.py.
"""
import ctypes
import time

import numpy as np
from OpenGL import GL

from ..core.features import centered, geometry, vertices
from . import gpu
from .shaders import (FEATURE_FRAGMENT, FEATURE_LINE_GEOMETRY,
                      FEATURE_VERTEX)

# Подтяжка к глазу в доле расстояния. На 2 км это 6 м, на 100 км 300 м.
PULL = 0.003
REBUILD_TIME = 0.003  # секунд на посадку объектов по новым высотам
WALL_ALPHA = 100  # непрозрачность стены линии, 0-255
UNIFORMS = ("u_mv", "u_projection", "u_pull", "u_color", "u_viewport",
            "u_width")
KINDS = ("walls", "fill", "lines")
GEOMETRY_CACHE = 4000  # контуров в памяти, по форме объекта


def _rgba(color):
    return [c / 255.0 for c in color]


class _Buffers:
    """Массив вершин объекта: смещения, отрезки контура, треугольники."""

    def __init__(self, center, offsets, lines, triangles,
                 wall=np.zeros(0, dtype=np.uint32)):
        self.center = center
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, offsets.nbytes, offsets,
                        GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12, None)
        GL.glBindVertexArray(0)
        # Индексы заливаются через GL_ARRAY_BUFFER. Привязка
        # GL_ELEMENT_ARRAY_BUFFER без массива вершин в профиле Core
        # на части драйверов - ошибка. Как индексы буфер привязывается
        # при отрисовке, вместе с массивом вершин.
        self.index = {}
        for name, indices in (("lines", lines), ("fill", triangles),
                              ("walls", wall)):
            if len(indices):
                ebo = GL.glGenBuffers(1)
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, ebo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, indices.nbytes,
                                indices, GL.GL_STATIC_DRAW)
                self.index[name] = (ebo, len(indices))
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def release(self):
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteBuffers(1, [self.vbo])
        for ebo, _ in self.index.values():
            GL.glDeleteBuffers(1, [ebo])


_geometries = {}


def cached_geometry(shape):
    """Контур объекта из памяти по его форме.

    «Мои метки» при каждом изменении перечитываются, и объекты
    создаются заново. Контур с треугольниками считался с нуля, у 29
    провинций Афганистана 0.6 с на каждый флажок. Форма - вид, вершины,
    есть ли заливка и стена, от цвета и названия контур не зависит.
    """
    key = (shape.kind, tuple(map(tuple, shape.points)),
           shape.fill is not None,
           bool(shape.extrude) and float(shape.height or 0.0) > 0.0)
    if key not in _geometries:
        if len(_geometries) >= GEOMETRY_CACHE:
            _geometries.clear()
        _geometries[key] = geometry(shape)
    return _geometries[key]


def build(shape, heights_at=None, geo=None):
    """Вершины объекта: центр, смещения, отрезки, треугольники заливки
    и стены. geo - готовый контур, иначе считается здесь.

    None для точки без стойки и для объекта без вершин.
    """
    geo = geo if geo is not None else geometry(shape)
    if geo is None:
        return None
    xyz = vertices(geo, float(shape.height or 0.0), heights_at)
    center, offsets = centered(xyz)
    return center, offsets, geo.lines, geo.triangles, geo.wall


def program_for(kind, line_program, fill_program):
    """Программа для вида отрисовки: у линий - с геометрическим
    шейдером толщины, у стен и заливки - без него."""
    return line_program if kind == "lines" else fill_program


class Features:
    """Набор объектов и их буферы в видеокарте."""

    def __init__(self):
        self.shapes = []
        self.buffers = []  # по объектам, None у точки
        # По id объекта: (объект, контур, буферы, версия высот). Пока
        # тянется резинка, меняется только она, прочие объекты
        # не пересобираются.
        self._built = {}
        self.version = None  # последняя версия высот
        self.line_program = None
        self.fill_program = None
        self.locations = {}  # программа -> места переменных
        self.dirty = False

    def vertex_count(self):
        """Вершин собранных объектов, по контурам."""
        total = 0
        for _, geo, _, _ in self._built.values():
            if geo is not None:
                n = len(geo.ring)
                total += 2 * n if len(geo.wall) or geo.stem else n
        return total

    def set_shapes(self, shapes):
        """Новый набор объектов. Буферы пересоберутся в кадре."""
        self.shapes = list(shapes)
        self.dirty = True

    def marks(self):
        """Точечные объекты: (номер, имя, широта, долгота, подъём,
        значок, цвет)."""
        return [(i, shape.name, shape.points[0][0], shape.points[0][1],
                 float(shape.height or 0.0), shape.icon,
                 tuple(shape.color))
                for i, shape in enumerate(self.shapes)
                if shape.kind == "point" and shape.points]

    # Ресурсы OpenGL.

    def init_gl(self):
        self.line_program = gpu.build_program(
            FEATURE_VERTEX, FEATURE_FRAGMENT, FEATURE_LINE_GEOMETRY)
        self.fill_program = gpu.build_program(FEATURE_VERTEX,
                                              FEATURE_FRAGMENT)
        self.locations = {
            program: {name: GL.glGetUniformLocation(program, name)
                      for name in UNIFORMS}
            for program in (self.line_program, self.fill_program)}
        self.dirty = True

    def release_gl(self):
        self._drop()
        for program in (self.line_program, self.fill_program):
            if program is not None:
                GL.glDeleteProgram(program)
        self.line_program = self.fill_program = None

    def _drop(self):
        for _, _, item, _ in self._built.values():
            if item is not None:
                item.release()
        self._built = {}
        self.buffers = []

    def _make(self, shape, geo, heights_at, version):
        built = build(shape, heights_at, geo)
        return (shape, geo, _Buffers(*built) if built else None, version)

    def _update(self, heights_at, version, still=True):
        """Буферы по объектам. Новые и изменённые собираются сразу,
        отставшие по высотам - в пределах REBUILD_TIME, ненужные
        освобождаются.

        Объект, созданный заново с той же формой и высотой, берёт буферы
        прежнего. «Мои метки» при флажке создают все объекты заново,
        и без этого все садились на рельеф заново.
        """
        old = self._built
        self._built = {}
        self.buffers = []
        started = time.perf_counter()
        spent = False
        spare = {}
        for key, entry in old.items():
            if entry[1] is not None:
                spare.setdefault((id(entry[1]), float(
                    entry[0].height or 0.0)), []).append(key)
        for shape in self.shapes:
            entry = old.get(id(shape))
            if entry is not None and entry[0] is shape:
                del old[id(shape)]
                # В движении объекты по новым высотам не пересаживаются,
                # движение важнее, решение автора от 28 сентября 2026 года.
                if still and entry[3] != version and entry[1] is not None \
                        and (not spent or time.perf_counter() - started
                             < REBUILD_TIME):
                    spent = True
                    if entry[2] is not None:
                        entry[2].release()
                    entry = self._make(shape, entry[1], heights_at, version)
            else:
                geo = cached_geometry(shape)
                entry = None
                for key in spare.get((id(geo), float(shape.height or 0.0)),
                                     []):
                    if key in old and old[key][1] is geo:
                        reuse = old.pop(key)
                        entry = (shape, geo, reuse[2], reuse[3])
                        break
                if entry is None:
                    entry = self._make(shape, geo, heights_at, version)
            self._built[id(shape)] = entry
            self.buffers.append(entry[2])
        for _, _, item, _ in old.values():
            if item is not None:
                item.release()
        self.version = version
        self.dirty = any(entry[3] != version and entry[1] is not None
                         for entry in self._built.values())

    # Кадр.

    def draw(self, camera, heights_at, version, ratio, still=True):
        """Нарисовать объекты. Вызывается после тайлов, до надписей.

        heights_at - высоты массива точек или None без рельефа. still -
        камера стоит, объекты можно пересаживать по новым высотам.
        Возвращает True, если объекты ещё садятся по новым высотам
        и нужен следующий кадр.
        """
        if self.line_program is None or not self.shapes:
            return False
        if self.dirty or version != self.version:
            self._update(heights_at, version, still)
        projection = camera.projection().astype(np.float32)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_BLEND)
        # Альфа кадра остаётся 1. С общим смешиванием полупрозрачная
        # линия уменьшала её, окно Qt просвечивало чёрным, и белая
        # сетка выходила тёмной, 29 сентября 2026 года.
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        try:
            self._draw_kinds(camera, projection, ratio)
        finally:
            # Ошибка посреди отрисовки оставляла запись глубины
            # выключенной, и следующие кадры рисовали тайлы без неё:
            # юбки полосами, шахматка вдали, 28 сентября 2026 года.
            GL.glBindVertexArray(0)
            GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
            GL.glDisable(GL.GL_BLEND)
            GL.glDepthMask(GL.GL_TRUE)
        return self.dirty

    def _draw_kinds(self, camera, projection, ratio):
        """Стены, заливки и линии всех объектов."""
        items = [(shape, item) for shape, item
                 in zip(self.shapes, self.buffers) if item is not None]
        if not items:
            return
        # Матрицы «глаз - центр объекта» всех объектов одной операцией.
        mvs = np.ascontiguousarray(camera.tiles_mvp(
            [item.center for _, item in items],
            projection=np.eye(4)), dtype=np.float32)
        base = mvs.ctypes.data
        stride = mvs.strides[0]
        proj = np.ascontiguousarray(projection, dtype=np.float32)
        null = ctypes.c_void_p(0)
        gl = gpu.gl
        for kind in KINDS:
            # Геометрический шейдер линий ждёт отрезки. Стена и заливка -
            # треугольники, им программа без него.
            program = program_for(kind, self.line_program,
                                  self.fill_program)
            loc = self.locations[program]
            gl.glUseProgram(program)
            gpu._uniform_matrix(loc["u_projection"], 1, GL.GL_TRUE,
                                ctypes.c_void_p(proj.ctypes.data))
            gl.glUniform1f(loc["u_pull"], PULL)
            if kind == "lines":
                gl.glUniform2f(loc["u_viewport"], float(camera.width),
                               float(camera.height))
            mode = GL.GL_LINES if kind == "lines" else GL.GL_TRIANGLES
            for i, (shape, item) in enumerate(items):
                found = item.index.get(kind)
                if found is None:
                    continue
                if kind == "fill":
                    color = shape.fill
                elif kind == "walls":
                    color = shape.fill or tuple(shape.color[:3]) \
                        + (WALL_ALPHA,)
                else:
                    color = shape.color
                gpu._uniform_matrix(loc["u_mv"], 1, GL.GL_TRUE,
                                    ctypes.c_void_p(base + stride * i))
                gpu._uniform4f(loc["u_color"], *_rgba(color))
                if kind == "lines":
                    gl.glUniform1f(loc["u_width"], shape.width * ratio)
                ebo, count = found
                gpu._bind_vao(item.vao)
                gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ebo)
                gpu._draw_elements(mode, count, GL.GL_UNSIGNED_INT, null)
