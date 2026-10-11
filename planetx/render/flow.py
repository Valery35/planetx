# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Струйки ветра и течений в видеокарте (core/flow.py).

Следы частиц - отрезки линий от положения к положению, голова ярче
хвоста. Точки следа хранятся в ECEF рядом с широтами и долготами
частиц: на каждом шаге считается только голова, по рельефу, остальное
сдвигается. Рисуются после поверхности без проверки глубины, сторона
шара за горизонтом отбрасывается, программа шейдеров - как у очагов
землетрясений (render/quakes.py).
"""
import ctypes

import numpy as np
from OpenGL import GL

from ..core import flow as core
from ..core.ellipsoid import geodetic_to_ecef
from ..core.subsurface import display
from . import gpu
from .quakes import FRAGMENT, GL_PROGRAM_POINT_SIZE, VERTEX

WIND_COLOR = (0.96, 0.97, 1.0)  # струйки ветра поверх его раскраски
WIND_SLOW = 2.0  # м/с, медленнее струйка ветра бледнеет
ALPHA = 1.0
LIFT = 30.0  # м над рельефом, струйка не тонет в тайле
HEAD_SIZE = 2.5  # логических пикселей - точка головы струйки
LINE_WIDTH = 1.8  # логических пикселей - толщина следа

# Следы - отрезки толщиной u_width пикселей: геометрический шейдер
# разворачивает отрезок в полосу на экране, как у линий меток
# (render/shaders.py, FEATURE_LINE_GEOMETRY), цвет идёт с вершин.
LINE_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_offset;
layout(location = 2) in vec4 a_color;
uniform mat4 u_mvp;
out vec4 g_color;
void main() {
    gl_Position = u_mvp * vec4(a_offset, 1.0);
    g_color = a_color;
}
"""

LINE_GEOMETRY = """#version 330 core
layout(lines) in;
layout(triangle_strip, max_vertices = 4) out;
uniform vec2 u_viewport;
uniform float u_width;
in vec4 g_color[];
out vec4 f_color;
void main() {
    vec4 a = gl_in[0].gl_Position;
    vec4 b = gl_in[1].gl_Position;
    if (a.w <= 0.0 || b.w <= 0.0) return;
    vec2 half_size = 0.5 * u_viewport;
    vec2 d = b.xy / b.w * half_size - a.xy / a.w * half_size;
    float len = length(d);
    d = len > 1e-6 ? d / len : vec2(1.0, 0.0);
    vec2 n = vec2(-d.y, d.x) * (0.5 * u_width);
    for (int i = 0; i < 4; i++) {
        vec4 p = i < 2 ? a : b;
        vec2 s = (i == 0 || i == 2) ? n : -n;
        gl_Position = vec4(p.xy + s / half_size * p.w, p.zw);
        f_color = i < 2 ? g_color[0] : g_color[1];
        EmitVertex();
    }
    EndPrimitive();
}
"""

LINE_FRAGMENT = """#version 330 core
in vec4 f_color;
out vec4 frag;
void main() {
    frag = f_color;
}
"""


class FlowLines:
    """Следы частиц одного поля: kind «wind» или «currents»."""

    def __init__(self, kind):
        self.kind = kind
        self.program = None
        self.line_program = None
        self.line_locations = {}
        self.vao = None
        self.vbo = None
        self.locations = {}
        self.xyz = None
        self.particles = None
        self.opacity = 1.0
        self.drawn = 0

    def init_gl(self):
        self.program = gpu.build_program(VERTEX, FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_ratio", "u_points")}
        self.line_program = gpu.build_program(LINE_VERTEX, LINE_FRAGMENT,
                                              LINE_GEOMETRY)
        self.line_locations = {
            name: GL.glGetUniformLocation(self.line_program, name)
            for name in ("u_mvp", "u_viewport", "u_width")}
        self.vao = GL.glGenVertexArrays(1)
        self.vbo = GL.glGenBuffers(1)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        stride = 8 * 4
        for index, size, offset in ((0, 3, 0), (1, 1, 3), (2, 4, 4)):
            GL.glEnableVertexAttribArray(index)
            GL.glVertexAttribPointer(index, size, GL.GL_FLOAT, GL.GL_FALSE,
                                     stride, ctypes.c_void_p(offset * 4))
        GL.glBindVertexArray(0)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)

    def release_gl(self):
        if self.program is None:
            return
        GL.glDeleteProgram(self.program)
        GL.glDeleteProgram(self.line_program)
        self.line_program = None
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteBuffers(1, [self.vbo])
        self.program = None

    def clear(self):
        self.particles = None
        self.xyz = None
        self.drawn = 0

    def advance(self, particles, ground, scale):
        """Точки следа после шага частиц: голова - по рельефу ground(lats,
        lons) с масштабом scale, у новорождённых весь след в голове."""
        self.particles = particles
        lat, lon = particles.lats[:, 0], particles.lons[:, 0]
        if self.kind == "currents":
            height = np.zeros(len(lat))
        else:
            g = np.maximum(np.asarray(ground(lat, lon), dtype=np.float64),
                           0.0)
            height = display(g, scale, g) + LIFT
        head = geodetic_to_ecef(lat, lon, height)
        if self.xyz is None or len(self.xyz) != len(lat):
            self.xyz = np.repeat(head[:, None, :], core.TRAIL, axis=1)
            return
        self.xyz[:, 1:] = self.xyz[:, :-1]
        self.xyz[:, 0] = head
        new = particles.age == 0
        self.xyz[new] = head[new][:, None, :]

    def draw(self, camera, ratio):
        self.drawn = 0
        p = self.particles
        if self.program is None or p is None or self.xyz is None:
            return
        eye = np.asarray(camera.eye, dtype=np.float64)
        head = self.xyz[:, 0]
        facing = np.einsum("ij,ij->i", head, eye - head) > 0.0
        depth = np.arange(core.TRAIL - 1)[None, :] < np.minimum(
            p.age, core.TRAIL - 1)[:, None]
        jump = np.abs(p.lons[:, :-1] - p.lons[:, 1:]) < 90.0
        keep = depth & jump & facing[:, None]
        if not np.any(keep):
            return
        a = self.xyz[:, :-1][keep] - eye
        b = self.xyz[:, 1:][keep] - eye
        share = np.broadcast_to(np.arange(core.TRAIL - 1)
                                / (core.TRAIL - 1.0), keep.shape)[keep]
        speed = np.broadcast_to(p.speed[:, None], keep.shape)[keep]
        alpha = ALPHA * (1.0 - share) * self.opacity
        if self.kind == "currents":
            rgb = core.current_colors(speed) / 255.0
        else:
            rgb = np.broadcast_to(np.array(WIND_COLOR), (len(speed), 3))
            alpha = alpha * np.clip(speed / WIND_SLOW, 0.2, 1.0)
        m = len(a)
        data = np.empty((2 * m, 8), dtype=np.float32)
        data[0::2, 0:3] = a
        data[1::2, 0:3] = b
        data[:, 3] = 1.0
        color = np.hstack([rgb, alpha[:, None]])
        data[0::2, 4:8] = color
        data[1::2, 4:8] = color
        data[1::2, 7] *= 0.7
        # Голова - точка, по тонкой линии струйка видна хуже.
        heads = keep[:, 0]
        n = int(np.count_nonzero(heads))
        dots = np.empty((n, 8), dtype=np.float32)
        dots[:, 0:3] = self.xyz[heads, 0] - eye
        dots[:, 3] = HEAD_SIZE
        if self.kind == "currents":
            dots[:, 4:7] = core.current_colors(p.speed[heads]) / 255.0
            dots[:, 7] = self.opacity
        else:
            dots[:, 4:7] = WIND_COLOR
            dots[:, 7] = self.opacity * np.clip(p.speed[heads] / WIND_SLOW,
                                                0.2, 1.0)
        data = np.vstack([data, dots])
        mvp = np.ascontiguousarray(camera.tiles_mvp([eye])[0],
                                   dtype=np.float32)
        line = self.line_locations
        GL.glUseProgram(self.line_program)
        GL.glUniformMatrix4fv(line["u_mvp"], 1, GL.GL_TRUE, mvp)
        GL.glUniform2f(line["u_viewport"], float(camera.width),
                       float(camera.height))
        GL.glUniform1f(line["u_width"], LINE_WIDTH * float(ratio))
        loc = self.locations
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STREAM_DRAW)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        GL.glEnable(GL_PROGRAM_POINT_SIZE)
        try:
            GL.glDrawArrays(GL.GL_LINES, 0, 2 * m)
            if n:
                GL.glUseProgram(self.program)
                GL.glUniformMatrix4fv(loc["u_mvp"], 1, GL.GL_TRUE, mvp)
                GL.glUniform1f(loc["u_ratio"], float(ratio))
                GL.glUniform1f(loc["u_points"], 1.0)
                GL.glDrawArrays(GL.GL_POINTS, 2 * m, n)
            self.drawn = m
        finally:
            GL.glBindVertexArray(0)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glDisable(GL.GL_BLEND)
            GL.glDisable(GL_PROGRAM_POINT_SIZE)
            GL.glEnable(GL.GL_DEPTH_TEST)
