# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-модели в видеокарте (core/models.py).

Модель - части одного материала: буферы вершин core.models.
MODEL_VERTEX от точки модели и картинка или цвет. Окно глобуса
отдаёт модели списком, точку каждой модели вид считает по рельефу
каждый кадр, где пришли новые высоты (anchor). Модели рисуются после
поверхности с проверкой и записью глубины, как здания, свет с двух
сторон.
"""
import ctypes

import numpy as np
from OpenGL import GL

from ..core.models import MODEL_VERTEX
from ..core.tiling import AMBIENT
from . import gpu
from .buildings import _latlon, light_at
from .shaders import MODEL_FRAGMENT, MODEL_VERTEX as VERTEX_SHADER

UNIFORMS = ("u_mvp", "u_light", "u_ambient", "u_image", "u_textured",
            "u_color")


class _Part:
    """Часть модели в видеокарте: буфер вершин и картинка."""

    def __init__(self, vertices, rgba, color):
        vertices = np.ascontiguousarray(vertices, dtype=MODEL_VERTEX)
        self.count = len(vertices)
        self.color = color
        gl = gpu.gl
        self.vao = gl.gen_names("glGenVertexArrays", 1)[0]
        self.vbo = gl.gen_names("glGenBuffers", 1)[0]
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.buffer_data(GL.GL_ARRAY_BUFFER, vertices)
        stride = MODEL_VERTEX.itemsize
        for index, size, field in ((0, 3, "position"), (1, 3, "normal"),
                                   (2, 2, "uv")):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(
                index, size, GL.GL_FLOAT, GL.GL_FALSE, stride,
                ctypes.c_void_p(MODEL_VERTEX.fields[field][1]))
        gl.glBindVertexArray(0)
        self.texture = None
        if rgba is not None:
            self.texture = gpu.create_texture(rgba)
            # Картинки моделей повторяются по грани, как в SketchUp.
            GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S,
                               GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T,
                               GL.GL_REPEAT)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def delete(self):
        gpu.gl.delete_names("glDeleteVertexArrays", [self.vao])
        gpu.gl.delete_names("glDeleteBuffers", [self.vbo])
        if self.texture is not None:
            gpu.delete_texture(self.texture)


class Model:
    """Модель для вида: части и место.

    parts - [(вершины MODEL_VERTEX, картинка RGBA или None, цвет RGBA
    0-1)], place - (широта, долгота, altitudeMode, высота), radius -
    радиус шара вокруг точки, метры, alpha - непрозрачность 0-1."""

    def __init__(self, key, parts, place, radius, alpha=1.0):
        self.key = key
        self.parts = parts
        self.place = place
        self.radius = radius
        self.alpha = alpha


class Models:
    """3D-модели окна глобуса."""

    def __init__(self):
        self.program = None
        self.locations = {}
        self.source = []  # Model окна
        self.loaded = {}  # ключ - [_Part]
        self.pending = True
        self.centers = []  # точки моделей в ECEF, по source
        # anchor(Model) - точка модели в ECEF по рельефу, ставит вид.
        self.anchor = None
        self.drawn = 0

    @property
    def active(self):
        return bool(self.source)

    def init_gl(self):
        self.program = gpu.build_program(VERTEX_SHADER, MODEL_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in UNIFORMS}

    def release_gl(self):
        for parts in self.loaded.values():
            for part in parts:
                part.delete()
        self.loaded = {}
        self.pending = True
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = None

    def set_models(self, items):
        """Новый список Model. Части загружаются в видеокарту в кадре,
        модели с прежним ключом не загружаются заново."""
        self.source = list(items)
        self.pending = True
        self.place()

    def place(self):
        """Точки моделей заново, например после прихода высот."""
        if self.anchor is None:
            self.centers = []
            return
        self.centers = [self.anchor(item) for item in self.source]

    def nearest(self, eye):
        """Расстояние от глаза до ближайшей модели за вычетом её радиуса,
        не меньше 1 м, или None без моделей."""
        found = None
        for item, center in zip(self.source, self.centers):
            gap = float(np.linalg.norm(center - eye)) - item.radius
            gap = max(gap, 1.0)
            found = gap if found is None else min(found, gap)
        return found

    def _upload(self):
        keys = {item.key for item in self.source}
        for key in list(self.loaded):
            if key not in keys:
                for part in self.loaded.pop(key):
                    part.delete()
        for item in self.source:
            if item.key not in self.loaded:
                self.loaded[item.key] = [_Part(*part) for part in item.parts]
        self.pending = False

    def draw(self, camera):
        """Нарисовать модели после поверхности, глубина включена."""
        self.drawn = 0
        if self.program is None or not self.source:
            return
        if self.pending:
            self._upload()
        if len(self.centers) != len(self.source):
            self.place()
        if len(self.centers) != len(self.source):
            return
        mvps = np.ascontiguousarray(camera.tiles_mvp(self.centers),
                                    dtype=np.float32)
        loc = self.locations
        gl = gpu.gl
        gl.glUseProgram(self.program)
        lat, lon = _latlon(np.asarray(camera.eye, dtype=np.float64))
        gl.glUniform3f(loc["u_light"], *light_at(lat, lon).tolist())
        gl.glUniform1f(loc["u_ambient"], AMBIENT)
        gl.glUniform1i(loc["u_image"], 0)
        gl.glActiveTexture(GL.GL_TEXTURE0)
        gl.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        base = mvps.ctypes.data
        stride = mvps.strides[0]
        try:
            for i, item in enumerate(self.source):
                gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                    ctypes.c_void_p(base + stride * i))
                for part in self.loaded.get(item.key, ()):
                    red, green, blue, alpha = part.color
                    GL.glUniform4f(loc["u_color"], red, green, blue,
                                   alpha * item.alpha)
                    if part.texture is not None:
                        GL.glBindTexture(GL.GL_TEXTURE_2D, part.texture)
                        GL.glUniform1f(loc["u_textured"], 1.0)
                    else:
                        GL.glUniform1f(loc["u_textured"], 0.0)
                    gpu._bind_vao(part.vao)
                    GL.glDrawArrays(GL.GL_TRIANGLES, 0, part.count)
                self.drawn += 1
        finally:
            gpu._bind_vao(0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
            gl.glDisable(GL.GL_BLEND)
