# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Звёзды в видеокарте: точки на бесконечности позади Земли.

Направления звёзд лежат в буфере один раз, в экваториальной системе.
Поворот на звёздное время и вид камеры сходятся в одной матрице кадра,
сдвига глаза в ней нет. Точка стоит на глубине 1.0, как небо, поэтому
Земля звезду закрывает, а небо нет. Свет звезды прибавляется к небу.
Расчёт - в core/stars.py.
"""
import ctypes
import os
import time

import numpy as np
from OpenGL import GL

from ..core import stars
from . import gpu

DATA = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data",
                    "stars.npy")
GL_PROGRAM_POINT_SIZE = 0x8642

STAR_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_dir;
layout(location = 1) in float a_size;
layout(location = 2) in vec4 a_color;
uniform mat4 u_mvp;
uniform float u_scale;
uniform float u_fade;
out vec4 v_color;
void main() {
    vec4 p = u_mvp * vec4(a_dir, 0.0);
    gl_Position = p.xyww;
    gl_PointSize = a_size * u_scale;
    v_color = vec4(a_color.rgb, a_color.a * u_fade);
}
"""

STAR_FRAGMENT = """#version 330 core
in vec4 v_color;
out vec4 frag;
void main() {
    float d = 2.0 * length(gl_PointCoord - vec2(0.5));
    frag = vec4(v_color.rgb, v_color.a * clamp(1.0 - d * d, 0.0, 1.0));
}
"""


def load(path=DATA):
    """Вершины звёзд (N, 8) float32: направление, размер, цвет и яркость."""
    table = np.load(path, allow_pickle=False)
    out = np.empty((len(table), 8), dtype=np.float32)
    out[:, 0:3] = stars.sky_directions(table[:, 0], table[:, 1])
    out[:, 3] = stars.sizes(table[:, 2])
    out[:, 4:7] = stars.colors(table[:, 3])
    out[:, 7] = stars.brightness(table[:, 2])
    return out


def sky_mvp(camera, unix_time):
    """Матрица кадра для направлений звёзд: проекция, поворот камеры
    и поворот неба на звёздное время, по строкам, float32."""
    angle = stars.gmst(unix_time)
    c, s = np.cos(angle), np.sin(angle)
    earth = np.array([[c, s, 0.0], [-s, c, 0.0], [0.0, 0.0, 1.0]])
    view = np.eye(4)
    view[:3, :3] = camera.rotation.T @ earth
    return np.ascontiguousarray(camera.projection() @ view,
                                dtype=np.float32)


class Stars:
    """Буфер звёзд и программа."""

    def __init__(self):
        self.program = None
        self.vao = None
        self.vbo = None
        self.count = 0
        self.locations = {}
        self.drawn = 0  # звёзд в последнем кадре, 0 - погашены

    def init_gl(self):
        data = load()
        self.count = len(data)
        self.program = gpu.build_program(STAR_VERTEX, STAR_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_scale", "u_fade")}
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STATIC_DRAW)
        for index, (size, offset) in enumerate(((3, 0), (1, 12), (4, 16))):
            GL.glEnableVertexAttribArray(index)
            GL.glVertexAttribPointer(index, size, GL.GL_FLOAT, GL.GL_FALSE,
                                     32, ctypes.c_void_p(offset))
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def release_gl(self):
        if self.vao is not None:
            GL.glDeleteVertexArrays(1, [self.vao])
            GL.glDeleteBuffers(1, [self.vbo])
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = self.vao = self.vbo = None

    def draw(self, camera, ratio, unix_time=None):
        """Нарисовать звёзды после неба. ratio - пикселей кадра
        на логический пиксель."""
        share = stars.fade(camera.altitude())
        self.drawn = 0
        if self.program is None or share <= 0.0:
            return
        mvp = sky_mvp(camera, time.time() if unix_time is None
                      else unix_time)
        gl = gpu.gl
        gl.glUseProgram(self.program)
        gpu._uniform_matrix(self.locations["u_mvp"], 1, GL.GL_TRUE,
                            ctypes.c_void_p(mvp.ctypes.data))
        gl.glUniform1f(self.locations["u_scale"], float(ratio))
        gl.glUniform1f(self.locations["u_fade"], float(share))
        gl.glEnable(GL_PROGRAM_POINT_SIZE)
        gl.glEnable(GL.GL_BLEND)
        # Свет звезды прибавляется к небу, альфа кадра остаётся 1.
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE,
                               GL.GL_ZERO, GL.GL_ONE)
        gl.glDepthFunc(GL.GL_LEQUAL)
        gl.glDepthMask(GL.GL_FALSE)
        try:
            gl.glBindVertexArray(self.vao)
            gl.glDrawArrays(GL.GL_POINTS, 0, self.count)
            self.drawn = self.count
        finally:
            gl.glBindVertexArray(0)
            gl.glDepthMask(GL.GL_TRUE)
            gl.glDepthFunc(GL.GL_LESS)
            gl.glDisable(GL.GL_BLEND)
            gl.glDisable(GL_PROGRAM_POINT_SIZE)
