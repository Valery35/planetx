# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои объекты глобуса в видеокарте: линии и заливка многоугольников.

Расчёт вершин - в core/features.py. Здесь буферы OpenGL и отрисовка.
Объектов немного, десятки или сотни, поэтому на объект свой массив
вершин и свой вызов отрисовки, путь кадра через PyOpenGL.

Вершины садятся на рельеф по высотам, которые есть на момент сборки.
Пришли новые высоты - объекты пересобираются, не чаще раза
в REBUILD_PERIOD. Точки рисует система надписей, см. view.py.
"""
import time

import numpy as np
from OpenGL import GL

from ..core.features import centered, densify, fill, lift, segments
from . import gpu
from .shaders import (FEATURE_FRAGMENT, FEATURE_LINE_GEOMETRY,
                      FEATURE_VERTEX)

# Подтяжка к глазу в доле расстояния. На 2 км это 6 м, на 100 км 300 м.
PULL = 0.003
REBUILD_PERIOD = 0.5  # секунд между пересборками по новым высотам


def _rgba(color):
    return [c / 255.0 for c in color]


class _Buffers:
    """Массив вершин объекта: смещения, отрезки контура, треугольники."""

    def __init__(self, center, offsets, lines, triangles):
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
        for name, indices in (("lines", lines), ("fill", triangles)):
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


def build(shape, height_at=None):
    """Вершины объекта: центр, смещения, отрезки, треугольники.

    None для точки и для объекта без вершин.
    """
    if shape.kind == "point" or len(shape.points) < 2:
        return None
    closed = shape.kind == "polygon" and len(shape.points) >= 3
    triangles = np.zeros(0, dtype=np.uint32)
    if closed and shape.fill is not None:
        ring, triangles = fill(shape.points)
    else:
        ring = densify(shape.points, closed=closed)
    center, offsets = centered(lift(ring, height_at))
    lines = segments(len(ring), closed=closed)
    return center, offsets, lines, triangles


class Features:
    """Набор объектов и их буферы в видеокарте."""

    def __init__(self):
        self.shapes = []
        self.buffers = []  # по объектам, None у точки
        # Собранные буферы по объекту: id объекта -> (объект, буферы).
        # Пока тянется резинка, меняется только она, прочие объекты
        # не пересобираются. Сборка стоит опроса высот на каждую точку.
        self._built = {}
        self.version = None  # версия высот, по которой собраны буферы
        self.built_at = 0.0
        self.line_program = None
        self.fill_program = None
        self.dirty = False

    def set_shapes(self, shapes):
        """Новый набор объектов. Буферы пересоберутся в кадре."""
        self.shapes = list(shapes)
        self.dirty = True

    def marks(self):
        """Точечные объекты: (номер, имя, широта, долгота)."""
        return [(i, shape.name, shape.points[0][0], shape.points[0][1])
                for i, shape in enumerate(self.shapes)
                if shape.kind == "point" and shape.points]

    # Ресурсы OpenGL.

    def init_gl(self):
        self.line_program = gpu.build_program(
            FEATURE_VERTEX, FEATURE_FRAGMENT, FEATURE_LINE_GEOMETRY)
        self.fill_program = gpu.build_program(FEATURE_VERTEX,
                                              FEATURE_FRAGMENT)
        self.dirty = True

    def release_gl(self):
        self._drop()
        for program in (self.line_program, self.fill_program):
            if program is not None:
                GL.glDeleteProgram(program)
        self.line_program = self.fill_program = None

    def _drop(self):
        for _, item in self._built.values():
            if item is not None:
                item.release()
        self._built = {}
        self.buffers = []

    def _rebuild(self, height_at, version):
        """Буферы по объектам. Новые высоты пересобирают все, иначе
        собираются только новые объекты, ушедшие освобождаются."""
        if version != self.version:
            self._drop()
        old = self._built
        self._built = {}
        self.buffers = []
        for shape in self.shapes:
            entry = old.pop(id(shape), None)
            if entry is None or entry[0] is not shape:
                if entry is not None and entry[1] is not None:
                    entry[1].release()
                built = build(shape, height_at)
                entry = (shape, _Buffers(*built) if built else None)
            self._built[id(shape)] = entry
            self.buffers.append(entry[1])
        for _, item in old.values():
            if item is not None:
                item.release()
        self.version = version
        self.built_at = time.monotonic()
        self.dirty = False

    # Кадр.

    def draw(self, camera, height_at, version, ratio):
        """Нарисовать объекты. Вызывается после тайлов, до надписей."""
        if self.line_program is None or not self.shapes:
            return
        stale = version != self.version \
            and time.monotonic() - self.built_at > REBUILD_PERIOD
        if self.dirty or stale:
            self._rebuild(height_at, version)
        projection = camera.projection().astype(np.float32)
        GL.glEnable(GL.GL_DEPTH_TEST)
        GL.glDepthMask(GL.GL_FALSE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        viewport = (float(camera.width), float(camera.height))
        for kind in ("fill", "lines"):
            program = self.fill_program if kind == "fill" \
                else self.line_program
            GL.glUseProgram(program)
            loc = {name: GL.glGetUniformLocation(program, name)
                   for name in ("u_mv", "u_projection", "u_pull",
                                "u_color", "u_viewport", "u_width")}
            GL.glUniformMatrix4fv(loc["u_projection"], 1, GL.GL_TRUE,
                                  projection)
            GL.glUniform1f(loc["u_pull"], PULL)
            if kind == "lines":
                GL.glUniform2f(loc["u_viewport"], *viewport)
            for shape, item in zip(self.shapes, self.buffers):
                if item is None or kind not in item.index:
                    continue
                color = shape.fill if kind == "fill" else shape.color
                mv = camera.tile_model_view(item.center).astype(np.float32)
                GL.glUniformMatrix4fv(loc["u_mv"], 1, GL.GL_TRUE, mv)
                GL.glUniform4f(loc["u_color"], *_rgba(color))
                if kind == "lines":
                    GL.glUniform1f(loc["u_width"], shape.width * ratio)
                ebo, count = item.index[kind]
                GL.glBindVertexArray(item.vao)
                GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ebo)
                GL.glDrawElements(
                    GL.GL_LINES if kind == "lines" else GL.GL_TRIANGLES,
                    count, GL.GL_UNSIGNED_INT, None)
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)
        GL.glDisable(GL.GL_BLEND)
        GL.glDepthMask(GL.GL_TRUE)
