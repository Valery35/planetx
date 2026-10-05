# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Спутники в видеокарте: точки на своей высоте над Землёй.

Положения - core/satellites.py. Геостационарные спутники стоят
в 36 000 км над поверхностью. Растянуть до них дальнюю плоскость
вида значит поднять ближнюю и срезать рельеф у низкой камеры
(AGENTS, «Координаты»). Поэтому точки рисуются своей проекцией
с дальностью FAR без проверки глубины, а закрытые Землёй отброшены
на процессоре (core.satellites.hidden). Вершины считаются от глаза
в double, в видеокарту уходят в float32. Шейдеры - у очагов
землетрясений (render/quakes.py).
"""
import numpy as np
from OpenGL import GL

from ..core import satellites as core
from ..core.camera import perspective
from .quakes import GL_PROGRAM_POINT_SIZE, Quakes

NEAR = 1000.0  # м
FAR = 1.0e9  # м, дальше Луны


class SatellitePoints(Quakes):
    """Точки спутников окна глобуса."""

    def __init__(self):
        super().__init__()
        self.stems = False
        self.points = np.zeros((0, 3))
        self.ok = np.zeros(0, dtype=bool)
        self.colors = np.zeros((0, 4), dtype=np.float32)
        self.sizes = np.zeros(0, dtype=np.float32)
        # Номера видимых спутников в последнем кадре, для опроса.
        self.seen = np.zeros(0, dtype=np.int64)
        self.highlight = None  # номер выбранного спутника или None
        # Положения на кадр: функция без аргументов, отдаёт (точки,
        # годные), или None - спутников нет.
        self.source = None

    def set_points(self, points, ok, colors, sizes):
        """Положения ECEF в метрах, признак годного положения, цвета
        RGBA 0-1 и размеры в логических пикселях."""
        self.points = points
        self.ok = ok
        self.colors = colors
        self.sizes = sizes

    def clear(self):
        self.set_points(np.zeros((0, 3)), np.zeros(0, dtype=bool),
                        np.zeros((0, 4), dtype=np.float32),
                        np.zeros(0, dtype=np.float32))

    def visible(self, eye):
        """Номера спутников, которые не закрыты Землёй."""
        if not len(self.points):
            return np.zeros(0, dtype=np.int64)
        idx = np.flatnonzero(self.ok)
        if not idx.size:
            return idx
        return idx[~core.hidden(eye, self.points[idx])]

    def projection(self, camera):
        return perspective(camera.fov_y, camera.aspect, NEAR, FAR)

    def draw(self, camera, ratio):
        self.drawn = 0
        if self.source is not None:
            self.points, self.ok = self.source()
        if self.program is None or not len(self.points):
            self.seen = np.zeros(0, dtype=np.int64)
            return
        eye = np.asarray(camera.eye, dtype=np.float64)
        idx = self.visible(eye)
        self.seen = idx
        if not idx.size:
            return
        n = idx.size
        dots = np.zeros((n, 8), dtype=np.float32)
        dots[:, 0:3] = self.points[idx] - eye
        dots[:, 3] = self.sizes[idx]
        dots[:, 4:8] = self.colors[idx]
        if self.highlight is not None:
            mark = idx == self.highlight
            dots[mark, 3] *= 2.0
        data = np.ascontiguousarray(dots)
        mvp = np.ascontiguousarray(
            camera.tiles_mvp([eye], projection=self.projection(camera))[0],
            dtype=np.float32)
        loc = self.locations
        GL.glUseProgram(self.program)
        GL.glUniformMatrix4fv(loc["u_mvp"], 1, GL.GL_TRUE, mvp)
        GL.glUniform1f(loc["u_ratio"], float(ratio))
        GL.glUniform1f(loc["u_points"], 1.0)
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
            GL.glDrawArrays(GL.GL_POINTS, 0, n)
            self.drawn = n
        finally:
            GL.glBindVertexArray(0)
            GL.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
            GL.glDisable(GL.GL_BLEND)
            GL.glDisable(GL_PROGRAM_POINT_SIZE)
            GL.glEnable(GL.GL_DEPTH_TEST)

    def pick(self, camera, x, y, radius):
        """Номер видимого спутника ближе radius пикселей к точке (x, y)
        окна или None."""
        idx = self.seen
        if not idx.size:
            return None
        pixels, front = camera.project(self.points[idx])
        d = np.hypot(pixels[:, 0] - x, pixels[:, 1] - y)
        d = np.where(front, d, np.inf)
        best = int(np.argmin(d))
        return int(idx[best]) if d[best] <= radius else None
