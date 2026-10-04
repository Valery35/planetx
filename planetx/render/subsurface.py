# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подземный режим в видеокарте: сетки стволов, горизонтов, разрезов.

Подшаг 4.4 плана фазы 3 (doc/PLAN_PHASE3.md). Сетки собирает
ui/subsurface.py (core/subsurface.py), здесь они загружаются
и рисуются до тайлов. Так поверхность при прозрачности ложится
поверх них смешиванием, а непрозрачная закрывает их проверкой
глубины. Сетка - именованная: «wells», «horizons», «sections»,
новая сетка с тем же именем заменяет прежнюю в следующем кадре.
"""
import ctypes

import numpy as np
from OpenGL import GL

from ..core.subsurface import IMAGE_VERTEX
from ..core.tiling import AMBIENT
from . import gpu
from .buildings import _Buffers, _latlon, light_at
from .shaders import (IMAGE_WALL_FRAGMENT, IMAGE_WALL_VERTEX,
                      SUBSURFACE_FRAGMENT, SUBSURFACE_VERTEX)

UNIFORMS = ("u_mvp", "u_light", "u_ambient")


class Subsurface:
    """Подземные сетки окна глобуса.

    offset - сетки поверх других в той же плоскости: полосы плит Slab2
    на гранях разреза Земли (core.cutaway.slab_bands). Смещение
    глубины к глазу убирает мерцание совпадающих плоскостей.
    xray - сетки видны сквозь поверхность, без проверки и записи
    глубины, как стенка разреза вдоль линии (core.section.wall_mesh).
    Рисуются после поверхности, порядок полос - порядок в сетке.
    """

    def __init__(self, offset=False, xray=False):
        self.offset = offset
        self.xray = xray
        self.program = None
        self.locations = {}
        self.buffers = {}  # имя - _Buffers
        self.pending = {}  # имя - Mesh или None (убрать)
        self.drawn = 0

    @property
    def active(self):
        """Есть ли сетки в видеокарте. Очередь загружает prepare."""
        return bool(self.buffers)

    def prepare(self):
        """Новые и убранные сетки - в видеокарту. Зовётся каждый кадр
        с текущим контекстом, до active."""
        if self.pending and self.program is not None:
            self._upload()

    def init_gl(self):
        self.program = gpu.build_program(SUBSURFACE_VERTEX,
                                         SUBSURFACE_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in UNIFORMS}
        # Сетки, пришедшие до контекста, ждут в pending.

    def release_gl(self):
        for item in self.buffers.values():
            item.delete()
        self.buffers = {}
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = None

    def set_mesh(self, name, mesh):
        """Новая сетка name или None - убрать. В видеокарту - в кадре."""
        self.pending[name] = mesh

    def clear(self):
        for name in list(self.buffers) + list(self.pending):
            self.pending[name] = None

    def vertex_count(self):
        return sum(item.vertices for item in self.buffers.values())

    def _upload(self):
        for name, mesh in self.pending.items():
            old = self.buffers.pop(name, None)
            if old is not None:
                old.delete()
            if mesh is not None and len(mesh.indices):
                self.buffers[name] = _Buffers(mesh, 0)
        self.pending = {}

    def draw(self, camera):
        """Нарисовать сетки. Вызывается из кадра с текущим контекстом,
        до тайлов, проверка и запись глубины включены."""
        self.drawn = 0
        if self.program is None:
            return
        self.prepare()
        items = list(self.buffers.values())
        if not items:
            return
        mvps = np.ascontiguousarray(
            camera.tiles_mvp([item.center for item in items]),
            dtype=np.float32)
        loc = self.locations
        gl = gpu.gl
        gl.glUseProgram(self.program)
        lat, lon = _latlon(np.asarray(camera.eye, dtype=np.float64))
        gl.glUniform3f(loc["u_light"], *light_at(lat, lon).tolist())
        gl.glUniform1f(loc["u_ambient"], AMBIENT)
        # Полупрозрачные части (стенки, если так задан цвет) не пишут
        # глубину сами в себя заметно: сеток мало, порядок - по имени.
        gl.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        if self.offset:
            GL.glEnable(GL.GL_POLYGON_OFFSET_FILL)
            GL.glPolygonOffset(-1.0, -4.0)
        if self.xray:
            GL.glDisable(GL.GL_DEPTH_TEST)
            GL.glDepthMask(GL.GL_FALSE)
        base = mvps.ctypes.data
        stride = mvps.strides[0]
        null = ctypes.c_void_p(0)
        try:
            for i, item in enumerate(items):
                gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                    ctypes.c_void_p(base + stride * i))
                gpu._bind_vao(item.vao)
                gpu._draw_elements(GL.GL_TRIANGLES, item.count,
                                   GL.GL_UNSIGNED_INT, null)
        finally:
            gpu._bind_vao(0)
            gl.glDisable(GL.GL_BLEND)
            if self.offset:
                GL.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            if self.xray:
                GL.glDepthMask(GL.GL_TRUE)
                GL.glEnable(GL.GL_DEPTH_TEST)
        self.drawn = len(items)


class _Wall:
    """Стенка с картинкой в видеокарте: буферы и текстура."""

    def __init__(self, center, vertices, indices, rgba):
        vertices = np.ascontiguousarray(vertices)
        indices = np.ascontiguousarray(indices, dtype=np.uint32)
        self.center = center
        self.count = len(indices)
        gl = gpu.gl
        self.vao = gl.gen_names("glGenVertexArrays", 1)[0]
        self.vbo, self.ebo = gl.gen_names("glGenBuffers", 2)
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.buffer_data(GL.GL_ARRAY_BUFFER, vertices)
        gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        gl.buffer_data(GL.GL_ELEMENT_ARRAY_BUFFER, indices)
        stride = IMAGE_VERTEX.itemsize
        for index, size, field in ((0, 3, "position"), (1, 2, "uv")):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(
                index, size, GL.GL_FLOAT, GL.GL_FALSE, stride,
                ctypes.c_void_p(IMAGE_VERTEX.fields[field][1]))
        gl.glBindVertexArray(0)
        self.texture = gpu.create_texture(rgba)

    def delete(self):
        gpu.gl.delete_names("glDeleteVertexArrays", [self.vao])
        gpu.gl.delete_names("glDeleteBuffers", [self.vbo, self.ebo])
        gpu.delete_texture(self.texture)


class ImageWalls:
    """Разрезы с картинками: вертикальные стенки вдоль линий, на них
    натянута картинка разреза (core.subsurface.image_wall). Рисуются
    вместе с прочим подземным, до тайлов, с проверкой глубины, видны
    с обеих сторон."""

    def __init__(self):
        self.program = None
        self.locations = {}
        self.walls = []
        self.source = []  # стенки окна: (центр, вершины, индексы, rgba)
        self.pending = None  # стенки, ждущие загрузки в видеокарту
        self.drawn = 0

    @property
    def active(self):
        return bool(self.walls) or bool(self.pending)

    def init_gl(self):
        self.program = gpu.build_program(IMAGE_WALL_VERTEX,
                                         IMAGE_WALL_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_image")}

    def release_gl(self):
        for wall in self.walls:
            wall.delete()
        self.walls = []
        # Стенки возвращаются в очередь: после смены контекста они
        # загружаются снова.
        self.pending = list(self.source) if self.source else None
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = None

    def set_walls(self, walls):
        """Новые стенки, [] - убрать. В видеокарту - в кадре."""
        self.source = list(walls)
        self.pending = list(walls)

    def _upload(self):
        for wall in self.walls:
            wall.delete()
        self.walls = [_Wall(*item) for item in self.pending]
        self.pending = None

    def draw(self, camera):
        self.drawn = 0
        if self.program is None:
            return
        if self.pending is not None:
            self._upload()
        if not self.walls:
            return
        mvps = np.ascontiguousarray(
            camera.tiles_mvp([wall.center for wall in self.walls]),
            dtype=np.float32)
        loc = self.locations
        gl = gpu.gl
        gl.glUseProgram(self.program)
        gl.glUniform1i(loc["u_image"], 0)
        gl.glActiveTexture(GL.GL_TEXTURE0)
        gl.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        base = mvps.ctypes.data
        stride = mvps.strides[0]
        null = ctypes.c_void_p(0)
        try:
            for i, wall in enumerate(self.walls):
                GL.glBindTexture(GL.GL_TEXTURE_2D, wall.texture)
                gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                    ctypes.c_void_p(base + stride * i))
                gpu._bind_vao(wall.vao)
                gpu._draw_elements(GL.GL_TRIANGLES, wall.count,
                                   GL.GL_UNSIGNED_INT, null)
        finally:
            gpu._bind_vao(0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            gl.glDisable(GL.GL_BLEND)
        self.drawn = len(self.walls)
