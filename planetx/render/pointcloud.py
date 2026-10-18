# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек в видеокарте (core/pointcloud.py, ui/pointcloud.py).

Клетка облака - буфер вершин: смещение точки на эллипсоиде от центра
клетки (float32), отметка в метрах и цвет RGBA (uint8). Высоту на экране
шейдер ставит вдоль нормали клетки: отметка × масштаб рельефа, без
рельефа - отметка минус низ облака. Смена масштаба не требует нового
чтения точек. Какие клетки рисовать, решает chooser окна
в каждом кадре - выбор по экрану core.pointcloud.select. Клетки
загружаются в видеокарту не больше UPLOADS за кадр. Точки рисуются
после поверхности кружками с проверкой и записью глубины, как модели.
"""
import ctypes

import numpy as np
from OpenGL import GL

from . import gpu
from .quakes import GL_PROGRAM_POINT_SIZE

UPLOADS = 4  # клеток в видеокарту за кадр, не больше
# Сдвиг глубины точек к глазу в координатах отсечения. Рельеф Terrarium
# сглажен на десятки метров, точки земли съёмки с дрона уходили под него.
# 0.004 - около 0.5 % расстояния до точки при ближней плоскости на
# половине расстояния. Выбор помощника, утверждает автор.
DEPTH_BIAS = 0.004

VERTEX = """#version 330 core
layout(location = 0) in vec3 a_offset;
layout(location = 1) in vec4 a_color;
layout(location = 2) in float a_height;
uniform mat4 u_mvp;
uniform float u_size;
uniform float u_bias;
uniform float u_scale;
uniform float u_floor;
uniform vec3 u_up;
out vec4 v_color;
void main() {
    float h = u_scale > 0.0 ? a_height * u_scale : a_height - u_floor;
    gl_Position = u_mvp * vec4(a_offset + u_up * h, 1.0);
    gl_Position.z -= u_bias * gl_Position.w;
    gl_PointSize = u_size;
    v_color = a_color;
}
"""

FRAGMENT = """#version 330 core
in vec4 v_color;
out vec4 frag;
void main() {
    vec2 d = gl_PointCoord - vec2(0.5);
    if (dot(d, d) > 0.25) {
        discard;
    }
    frag = vec4(v_color.rgb, 1.0);
}
"""

POINT = np.dtype([("offset", np.float32, 3), ("color", np.uint8, 4),
                  ("height", np.float32)])


class _Block:
    """Клетка в видеокарте."""

    def __init__(self, offsets, heights, colors, place):
        vertices = np.empty(len(offsets), dtype=POINT)
        vertices["offset"] = offsets
        vertices["color"] = colors
        vertices["height"] = heights
        self.count = len(vertices)
        # place - (центр на эллипсоиде, нормаль, низ облака в метрах,
        # отметки клетки (низ, верх), горизонтальный радиус).
        center, up, floor, span, radius = place
        self.center = np.asarray(center, dtype=np.float64)
        self.up = np.asarray(up, dtype=np.float64)
        self.floor = float(floor)
        self.span = (float(span[0]), float(span[1]))
        self.radius = float(radius)
        gl = gpu.gl
        self.vao = gl.gen_names("glGenVertexArrays", 1)[0]
        self.vbo = gl.gen_names("glGenBuffers", 1)[0]
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.buffer_data(GL.GL_ARRAY_BUFFER, vertices)
        stride = POINT.itemsize
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                 ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 4, GL.GL_UNSIGNED_BYTE, GL.GL_TRUE,
                                 stride, ctypes.c_void_p(12))
        gl.glEnableVertexAttribArray(2)
        gl.glVertexAttribPointer(2, 1, GL.GL_FLOAT, GL.GL_FALSE, stride,
                                 ctypes.c_void_p(16))
        gl.glBindVertexArray(0)

    def lifted(self, scale):
        """Середина клетки на экране и радиус с высотами при масштабе
        рельефа scale."""
        low, high = (h * scale if scale else h - self.floor
                     for h in self.span)
        middle = self.center + self.up * ((low + high) / 2.0)
        return middle, self.radius + abs(high - low) / 2.0

    def delete(self):
        gpu.gl.delete_names("glDeleteVertexArrays", [self.vao])
        gpu.gl.delete_names("glDeleteBuffers", [self.vbo])


class PointClouds:
    """Облака точек окна глобуса.

    chooser(camera) - ключи клеток для кадра, ставит окно. Ключ клетки -
    любой хешируемый, например (номер слоя, версия вида, клетка)."""

    def __init__(self):
        self.program = None
        self.locations = {}
        self.blocks = {}  # ключ - _Block
        self.pending = []  # (ключ, смещения, отметки, цвета, место)
        self.chooser = None
        self.size = 2.0  # логических пикселей
        self.scale = 1.0  # масштаб рельефа, 0 - рельеф выключен
        self.sizes = {}  # размер точки по первой части ключа - слою
        self.drawn = 0
        self.points = 0
        self.shown = []  # ключи клеток последнего кадра

    @property
    def active(self):
        return self.chooser is not None

    def init_gl(self):
        self.program = gpu.build_program(VERTEX, FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_size", "u_bias",
                                       "u_scale", "u_floor", "u_up")}

    def release_gl(self):
        for block in self.blocks.values():
            block.delete()
        self.blocks = {}
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = None

    def add(self, key, offsets, heights, colors, place):
        """Клетка пришла: в видеокарту в ближайших кадрах. place - см.
        _Block."""
        self.pending.append((key, offsets, heights, colors, place))

    def has(self, key):
        return key in self.blocks or any(p[0] == key for p in self.pending)

    def drop(self, test):
        """Убрать клетки, у ключа которых test(ключ) истинно."""
        self.pending = [p for p in self.pending if not test(p[0])]
        for key in [k for k in self.blocks if test(k)]:
            block = self.blocks.pop(key)
            if self.program is not None:
                block.delete()

    def nearest(self, eye):
        """Расстояние от глаза до ближайшей нарисованной клетки за
        вычетом радиуса, не меньше 1 м, или None."""
        found = None
        for key in self.shown:
            block = self.blocks.get(key)
            if block is None:
                continue
            middle, radius = block.lifted(self.scale)
            gap = max(float(np.linalg.norm(middle - eye)) - radius, 1.0)
            found = gap if found is None else min(found, gap)
        return found

    def _upload(self, limit):
        done = 0
        while self.pending and done < limit:
            key, offsets, heights, colors, place = self.pending.pop(0)
            old = self.blocks.pop(key, None)
            if old is not None:
                old.delete()
            if len(offsets):
                self.blocks[key] = _Block(offsets, heights, colors, place)
            done += 1

    def choose(self, camera):
        """Ключи клеток кадра от окна, их запоминает nearest."""
        self.shown = list(self.chooser(camera)) if self.chooser else []
        return self.shown

    def draw(self, camera, ratio, uploads=UPLOADS):
        """Нарисовать клетки choose после поверхности."""
        self.drawn = 0
        self.points = 0
        if self.program is None or self.chooser is None:
            return
        self._upload(uploads)
        keys = [k for k in self.shown if k in self.blocks]
        blocks = [self.blocks[k] for k in keys]
        if not blocks:
            return
        mvps = np.ascontiguousarray(
            camera.tiles_mvp([b.center for b in blocks]), dtype=np.float32)
        loc = self.locations
        gl = gpu.gl
        gl.glUseProgram(self.program)
        GL.glUniform1f(loc["u_bias"], DEPTH_BIAS)
        GL.glUniform1f(loc["u_scale"], float(self.scale))
        GL.glEnable(GL_PROGRAM_POINT_SIZE)
        base = mvps.ctypes.data
        stride = mvps.strides[0]
        try:
            size = None
            for i, block in enumerate(blocks):
                want = self.sizes.get(keys[i][0], self.size) \
                    if isinstance(keys[i], tuple) else self.size
                if want != size:
                    size = want
                    GL.glUniform1f(loc["u_size"], float(size * ratio))
                gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                    ctypes.c_void_p(base + stride * i))
                GL.glUniform3f(loc["u_up"], *block.up.tolist())
                GL.glUniform1f(loc["u_floor"], block.floor)
                gpu._bind_vao(block.vao)
                GL.glDrawArrays(GL.GL_POINTS, 0, block.count)
                self.drawn += 1
                self.points += block.count
        finally:
            gpu._bind_vao(0)
            GL.glDisable(GL_PROGRAM_POINT_SIZE)
