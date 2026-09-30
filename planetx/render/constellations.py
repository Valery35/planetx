# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Линии фигур созвездий в видеокарте.

Концы отрезков - направления на бесконечности, как у звёзд
(render/stars.py): w = 0, глубина 1.0. Отрезок между двумя
направлениями в перспективе ложится на дугу большого круга, поэтому
сгущать его не нужно. Данные - core/skydata.py.
"""
import ctypes

from OpenGL import GL

from ..core import skydata
from . import gpu
from .stars import sky_mvp

LINE_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_dir;
uniform mat4 u_mvp;
void main() {
    vec4 p = u_mvp * vec4(a_dir, 0.0);
    gl_Position = p.xyww;
}
"""

LINE_FRAGMENT = """#version 330 core
uniform vec4 u_color;
out vec4 frag;
void main() {
    frag = u_color;
}
"""

# Цвет линий: приглушённый голубой, свет прибавляется к небу.
# Подобран помощником.
COLOR = (0.35, 0.55, 0.85, 0.55)


class Constellations:
    """Буфер отрезков созвездий и программа."""

    def __init__(self):
        self.program = None
        self.vao = None
        self.vbo = None
        self.count = 0
        self.locations = {}
        self.drawn = 0

    def init_gl(self):
        data = skydata.segments(skydata.load())
        self.count = len(data)
        self.program = gpu.build_program(LINE_VERTEX, LINE_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_color")}
        self.vao = GL.glGenVertexArrays(1)
        GL.glBindVertexArray(self.vao)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 12,
                                 ctypes.c_void_p(0))
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def release_gl(self):
        if self.vao is not None:
            GL.glDeleteVertexArrays(1, [self.vao])
            GL.glDeleteBuffers(1, [self.vbo])
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = self.vao = self.vbo = None

    def draw(self, camera, frame):
        """Нарисовать линии после картинки неба и до звёзд. frame -
        поворот неба, см. render/stars.sky_mvp."""
        self.drawn = 0
        if self.program is None:
            return
        mvp = sky_mvp(camera, 0.0, frame)
        gl = gpu.gl
        gl.glUseProgram(self.program)
        gpu._uniform_matrix(self.locations["u_mvp"], 1, GL.GL_TRUE,
                            ctypes.c_void_p(mvp.ctypes.data))
        GL.glUniform4f(self.locations["u_color"], *COLOR)
        gl.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE,
                               GL.GL_ZERO, GL.GL_ONE)
        gl.glDepthFunc(GL.GL_LEQUAL)
        gl.glDepthMask(GL.GL_FALSE)
        try:
            gl.glBindVertexArray(self.vao)
            gl.glDrawArrays(GL.GL_LINES, 0, self.count)
            self.drawn = self.count // 2
        finally:
            gl.glBindVertexArray(0)
            gl.glDepthMask(GL.GL_TRUE)
            gl.glDepthFunc(GL.GL_LESS)
            gl.glDisable(GL.GL_BLEND)
