# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Землетрясения в видеокарте: очаги точками, линии к эпицентрам.

Расчёт - core/quakes.py. Очаги лежат под рельефом, поэтому рисуются
без проверки глубины, поверх поверхности, а очаги за горизонтом
отбрасываются на процессоре (core.quakes.facing). Каждый кадр вершины
считаются от глаза в double и уходят в видеокарту в float32, так
мировые координаты в видеокарту не попадают (AGENTS, «Координаты»).
Событий сводки - сотни, пересчёт стоит доли миллисекунды.
"""
import ctypes

import numpy as np
from OpenGL import GL

from ..core import quakes as core
from ..core.ellipsoid import geodetic_to_ecef
from ..core.fires import colors as fire_colors
from ..core.fires import sizes as fire_sizes
from ..core.subsurface import display, ecef
from . import gpu

GL_PROGRAM_POINT_SIZE = 0x8642
STEM_ALPHA = 0.55  # непрозрачность линии от эпицентра к очагу

VERTEX = """#version 330 core
layout(location = 0) in vec3 a_offset;
layout(location = 1) in float a_size;
layout(location = 2) in vec4 a_color;
uniform mat4 u_mvp;
uniform float u_ratio;
out vec4 v_color;
void main() {
    gl_Position = u_mvp * vec4(a_offset, 1.0);
    gl_PointSize = a_size * u_ratio;
    v_color = a_color;
}
"""

FRAGMENT = """#version 330 core
in vec4 v_color;
uniform float u_points;
out vec4 frag;
void main() {
    float alpha = v_color.a;
    if (u_points > 0.5) {
        // Кружок с тёмным ободком: точка видна и на светлом снимке.
        float d = 2.0 * length(gl_PointCoord - vec2(0.5));
        if (d > 1.0) {
            discard;
        }
        vec3 rgb = d > 0.75 ? v_color.rgb * 0.35 : v_color.rgb;
        frag = vec4(rgb, alpha);
    } else {
        frag = vec4(v_color.rgb, alpha);
    }
}
"""


class Quakes:
    """Очаги землетрясений окна глобуса."""

    def __init__(self):
        self.program = None
        self.vao = None
        self.vbo = None
        self.locations = {}
        self.events = []
        self.focus = np.zeros((0, 3))
        self.epicenter = np.zeros((0, 3))
        self.colors = np.zeros((0, 4), dtype=np.float32)
        self.sizes = np.zeros(0, dtype=np.float32)
        self.lats = np.zeros(0)
        self.lons = np.zeros(0)
        self.times = np.zeros(0)
        # Промежуток шкалы времени (от, до) или None - видно всё.
        self.window = None
        self.drawn = 0
        # Линии от эпицентра к очагу. У пожаров (FirePoints) их нет.
        self.stems = True

    def init_gl(self):
        self.program = gpu.build_program(VERTEX, FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_ratio", "u_points")}
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
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteBuffers(1, [self.vbo])
        self.program = None

    def set_events(self, events, scale, ground, depth_map=None):
        """События core.quakes.Quake. scale - масштаб рельефа, ground -
        настоящие отметки рельефа для эпицентров, depth_map - глубины
        на экране при выделении коры разреза или None."""
        self.events = list(events)
        if not self.events:
            self.focus = np.zeros((0, 3))
            self.epicenter = np.zeros((0, 3))
            return
        self.focus, self.epicenter = core.points(self.events, scale, ground,
                                                 depth_map)
        rgb = core.depth_colors([q.depth for q in self.events])
        self.colors = np.hstack([rgb / 255.0, np.ones((len(rgb), 1))]) \
            .astype(np.float32)
        self.sizes = core.sizes([q.mag for q in self.events]) \
            .astype(np.float32)
        self.lats = np.array([q.lat for q in self.events])
        self.lons = np.array([q.lon for q in self.events])
        self.times = core.times(self.events)

    def draw(self, camera, ratio):
        """Нарисовать видимые очаги и линии к ним. Вызывается в кадре
        после поверхности и своих объектов, до надписей."""
        self.drawn = 0
        if self.program is None or not len(self.focus):
            return
        eye = np.asarray(camera.eye, dtype=np.float64)
        seen = core.facing(eye, self.epicenter, self.lats, self.lons) \
            & core.in_window(self.times, self.window)
        if not np.any(seen):
            return
        focus = self.focus[seen] - eye
        colors = self.colors[seen]
        n = len(focus)
        dots = np.zeros((n, 8), dtype=np.float32)
        dots[:, 0:3] = focus
        dots[:, 3] = self.sizes[seen]
        dots[:, 4:8] = colors
        lines = 0
        if self.stems:
            epi = self.epicenter[seen] - eye
            stems = np.zeros((2 * n, 8), dtype=np.float32)
            stems[0::2, 0:3] = epi
            stems[1::2, 0:3] = focus
            stems[:, 4:8] = np.repeat(colors, 2, axis=0)
            stems[:, 7] = STEM_ALPHA
            lines = 2 * n
            dots = np.vstack([stems, dots])
        data = np.ascontiguousarray(dots)
        mvp = np.ascontiguousarray(camera.tiles_mvp([eye])[0],
                                   dtype=np.float32)
        loc = self.locations
        GL.glUseProgram(self.program)
        GL.glUniformMatrix4fv(loc["u_mvp"], 1, GL.GL_TRUE, mvp)
        GL.glUniform1f(loc["u_ratio"], float(ratio))
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STREAM_DRAW)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL_PROGRAM_POINT_SIZE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        try:
            if lines:
                GL.glUniform1f(loc["u_points"], 0.0)
                GL.glDrawArrays(GL.GL_LINES, 0, lines)
            GL.glUniform1f(loc["u_points"], 1.0)
            GL.glDrawArrays(GL.GL_POINTS, lines, n)
            self.drawn = n
        finally:
            GL.glBindVertexArray(0)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glDisable(GL.GL_BLEND)
            GL.glDisable(GL_PROGRAM_POINT_SIZE)
            GL.glEnable(GL.GL_DEPTH_TEST)


class FirePoints(Quakes):
    """Очаги пожаров окна глобуса: точки на рельефе без линий, цвет
    и размер по мощности излучения (core/fires.py). Очагов десятки
    тысяч, отбор и сдвиг от глаза - одним проходом NumPy."""

    def __init__(self):
        super().__init__()
        self.stems = False
        self.fires = None

    def set_fires(self, fires, scale, ground):
        """Очаги core.fires.Fires или None. scale - масштаб рельефа,
        ground(lats, lons) - настоящие отметки рельефа."""
        self.fires = fires if fires is not None and len(fires) else None
        if self.fires is None:
            self.focus = np.zeros((0, 3))
            self.epicenter = self.focus
            return
        lat, lon = fires.lat, fires.lon
        g = np.asarray(ground(lat, lon), dtype=np.float64)
        self.focus = geodetic_to_ecef(lat, lon, display(g, scale, g))
        self.epicenter = self.focus
        rgb = fire_colors(fires.frp)
        self.colors = np.hstack([rgb / 255.0, np.full((len(rgb), 1), 0.9)]) \
            .astype(np.float32)
        self.sizes = fire_sizes(fires.frp).astype(np.float32)
        self.lats = lat
        self.lons = lon
        self.times = fires.time


class DepositPoints(Quakes):
    """Месторождения USGS (core/deposits.py): точки на рельефе, цвет -
    группа полезного ископаемого, размер - крупное месторождение или
    стадия освоения. Точек около 300 тысяч, поэтому нормали считаются
    один раз, а в кадре - не больше LIMIT видимых точек в порядке
    важности: крупные месторождения мира, действующие и прежние
    рудники, остальные - в постоянном перемешанном порядке."""

    LIMIT = 80000
    NEAR = 6.0  # высот глаза до самой дальней точки низко над Землёй
    FAR = 3.0e6  # м, выше глаз берёт всю видимую полусферу

    def __init__(self):
        super().__init__()
        self.stems = False
        self.data = None
        self.up = np.zeros((0, 3))

    def set_deposits(self, data, scale, ground):
        """Месторождения core.deposits.Deposits или None. scale -
        масштаб рельефа, ground(lats, lons) - отметки рельефа."""
        from ..core import deposits as dp
        self.data = data if data is not None and len(data) else None
        if self.data is None:
            self.focus = np.zeros((0, 3))
            self.epicenter = self.focus
            return
        lat, lon = data.lat, data.lon
        # Порядок важности: крупные, рудники, остальные перемешаны -
        # при пределе точек вид заполняется ровно, а не по порядку
        # файла.
        rank = np.where(data.major, 0,
                        np.where(data.status <= 2, 1, 2)).astype(np.int64)
        shuffle = np.random.default_rng(0).permutation(len(data))
        order = np.lexsort((shuffle, rank))
        self.order = order
        lat, lon = lat[order], lon[order]
        g = np.asarray(ground(lat, lon), dtype=np.float64)
        self.focus = ecef(lat, lon, display(g, scale, g))
        self.epicenter = self.focus
        self.up = core.surface_normal(lat, lon)
        rgb = dp.colors(data.group[order])
        self.colors = np.hstack([rgb / 255.0, np.full((len(rgb), 1), 0.9)]) \
            .astype(np.float32)
        self.sizes = dp.sizes(data.major[order],
                              data.status[order]).astype(np.float32)
        self.lats = lat
        self.lons = lon
        self.times = np.full(len(lat), np.nan)

    def visible(self, eye):
        """Номера видимых точек (в порядке важности), не больше LIMIT.
        Низко над Землёй точки дальше NEAR высот глаза не берутся: предел
        тратится на то, что в кадре, а не на всю видимую полусферу."""
        eye = np.asarray(eye, dtype=np.float64)
        to_eye = eye - self.focus
        seen = np.einsum("ij,ij->i", self.up, to_eye) > 0.0
        height = float(np.linalg.norm(eye)) - 6371000.0
        if height < self.FAR:
            reach = self.NEAR * max(height, 1000.0)
            seen &= np.einsum("ij,ij->i", to_eye, to_eye) < reach * reach
        return np.nonzero(seen)[0][:self.LIMIT]

    def draw(self, camera, ratio):
        self.drawn = 0
        if self.program is None or self.data is None:
            return
        eye = np.asarray(camera.eye, dtype=np.float64)
        seen = self.visible(eye)
        n = len(seen)
        if not n:
            return
        dots = np.empty((n, 8), dtype=np.float32)
        dots[:, 0:3] = self.focus[seen] - eye
        dots[:, 3] = self.sizes[seen]
        dots[:, 4:8] = self.colors[seen]
        mvp = np.ascontiguousarray(camera.tiles_mvp([eye])[0],
                                   dtype=np.float32)
        loc = self.locations
        GL.glUseProgram(self.program)
        GL.glUniformMatrix4fv(loc["u_mvp"], 1, GL.GL_TRUE, mvp)
        GL.glUniform1f(loc["u_ratio"], float(ratio))
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, dots.nbytes, dots,
                        GL.GL_STREAM_DRAW)
        GL.glDisable(GL.GL_DEPTH_TEST)
        GL.glEnable(GL_PROGRAM_POINT_SIZE)
        GL.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        try:
            GL.glUniform1f(loc["u_points"], 1.0)
            GL.glDrawArrays(GL.GL_POINTS, 0, n)
            self.drawn = n
        finally:
            GL.glBindVertexArray(0)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glDisable(GL.GL_BLEND)
            GL.glDisable(GL_PROGRAM_POINT_SIZE)
            GL.glEnable(GL.GL_DEPTH_TEST)
