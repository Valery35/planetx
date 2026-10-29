# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карта теней кадра в видеокарте: буфер кадра с текстурой глубины,
проход тайлов, зданий и моделей со стороны солнца. Матрицы света -
core/shadowmap.py.

Карта лежит на текстурном блоке UNIT. Шейдеру тайла это семнадцатый
блок, OpenGL 3.3 обещает шестнадцать. Если видеокарта даёт меньше
семнадцати, тени не включаются, шейдеры собираются без них (supported).
"""
import ctypes

import numpy as np
from OpenGL import GL

from ..core import shadowmap
from . import gpu
from .shaders import SHADOW_TILE_FRAGMENT, SHADOW_TILE_VERTEX

UNIT = 16  # текстурный блок карты теней
# Наклон смещения глубины в проходе карты - против полос самозатенения
# склонов под косым солнцем. Выбор помощника по кадрам.
SLOPE_BIAS = 2.0
UNITS_BIAS = 4.0


def units_available():
    """Сколько текстурных блоков даёт видеокарта фрагментному шейдеру."""
    return int(np.ravel(GL.glGetIntegerv(GL.GL_MAX_TEXTURE_IMAGE_UNITS))[0])


class ShadowMap:
    """Буфер кадра карты теней. frame - LightFrame последнего прохода
    или None - тени не рисуются."""

    def __init__(self, size=shadowmap.MAP_SIZE):
        self.size = size
        self.supported = False
        self.program = None
        self.fbo = None
        self.texture = None
        self.u_mvp = -1
        self.u_fade = -1
        self.frame = None
        self.drawn = 0

    def init_gl(self):
        self.supported = units_available() > UNIT
        if not self.supported:
            return
        self.program = gpu.build_program(SHADOW_TILE_VERTEX,
                                         SHADOW_TILE_FRAGMENT)
        self.u_mvp = GL.glGetUniformLocation(self.program, "u_mvp")
        self.u_fade = GL.glGetUniformLocation(self.program, "u_fade")
        self.texture = int(np.ravel(GL.glGenTextures(1))[0])
        GL.glActiveTexture(GL.GL_TEXTURE0 + UNIT)
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_DEPTH_COMPONENT24,
                        self.size, self.size, 0, GL.GL_DEPTH_COMPONENT,
                        GL.GL_UNSIGNED_INT, None)
        for name, value in (
                (GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                (GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE),
                (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
                (GL.GL_TEXTURE_COMPARE_MODE, GL.GL_COMPARE_REF_TO_TEXTURE),
                (GL.GL_TEXTURE_COMPARE_FUNC, GL.GL_LEQUAL)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        self.fbo = int(np.ravel(GL.glGenFramebuffers(1))[0])
        previous = int(np.ravel(GL.glGetIntegerv(
            GL.GL_DRAW_FRAMEBUFFER_BINDING))[0])
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        GL.glFramebufferTexture2D(GL.GL_FRAMEBUFFER, GL.GL_DEPTH_ATTACHMENT,
                                  GL.GL_TEXTURE_2D, self.texture, 0)
        GL.glDrawBuffer(GL.GL_NONE)
        GL.glReadBuffer(GL.GL_NONE)
        status = GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, previous)
        if status != GL.GL_FRAMEBUFFER_COMPLETE:
            self.release()
            self.supported = False

    def release(self):
        """Освободить ресурсы, контекст текущий."""
        if self.fbo is not None:
            GL.glDeleteFramebuffers(1, [self.fbo])
        if self.texture is not None:
            GL.glDeleteTextures([self.texture])
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.fbo = self.texture = self.program = None
        self.frame = None

    def bind(self, locations):
        """Карту на её блок и значения шейдера: locations - (u_shadow_on,
        u_shadow_params, u_shadow_offset) программы, она уже текущая."""
        on_loc, params_loc, offset_loc = locations
        frame = self.frame
        if frame is None or not self.supported:
            gpu.gl.glUniform1f(on_loc, 0.0)
            return False
        gpu._active_texture(GL.GL_TEXTURE0 + UNIT)
        gpu._bind_texture(GL.GL_TEXTURE_2D, self.texture)
        gpu._active_texture(GL.GL_TEXTURE0)
        gpu.gl.glUniform1f(on_loc, 1.0)
        gpu.gl.glUniform3f(params_loc, 1.0 / self.size, frame.bias,
                           shadowmap.FADE)
        gpu.gl.glUniform1f(offset_loc, frame.offset)
        return True

    def render(self, frame, items, fades, draw_more):
        """Проход карты глубины: тайлы items (пары сетка, текстура)
        с долями заплаток fades, потом draw_more(LightCamera) - здания
        и модели. frame - LightFrame или None, тогда теней нет."""
        self.frame = None
        self.drawn = 0
        if not self.supported or frame is None or not frame.active:
            return
        previous = int(np.ravel(GL.glGetIntegerv(
            GL.GL_DRAW_FRAMEBUFFER_BINDING))[0])
        viewport = [int(v) for v in np.ravel(GL.glGetIntegerv(
            GL.GL_VIEWPORT))]
        gpu.gl.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.fbo)
        gpu.gl.glViewport(0, 0, self.size, self.size)
        gpu.gl.glDepthMask(GL.GL_TRUE)
        gpu.gl.glEnable(GL.GL_DEPTH_TEST)
        gpu.gl.glClear(GL.GL_DEPTH_BUFFER_BIT)
        gpu.gl.glEnable(GL.GL_POLYGON_OFFSET_FILL)
        gpu.gl.glPolygonOffset(SLOPE_BIAS, UNITS_BIAS)
        try:
            gpu.gl.glUseProgram(self.program)
            if items:
                mats = np.ascontiguousarray(frame.matrices(
                    [mesh.center for mesh, _ in items]), dtype=np.float32)
                gpu.draw_batch(items, mats, self.u_mvp, fades=fades,
                               u_fade=self.u_fade)
                gpu.gl.glUniform4f(self.u_fade, 0.0, 0.0, 0.0, 0.0)
            draw_more(shadowmap.LightCamera(frame))
            self.frame = frame
            self.drawn = len(items)
        finally:
            gpu.gl.glDisable(GL.GL_POLYGON_OFFSET_FILL)
            gpu._bind_vao(0)
            gpu.gl.glBindFramebuffer(GL.GL_FRAMEBUFFER, previous)
            gpu.gl.glViewport(*viewport)


def uniform_locations(program):
    """Места значений тени в программе: (u_shadow_on, u_shadow_params,
    u_shadow_offset, u_shadow, u_shadow_map)."""
    return tuple(GL.glGetUniformLocation(program, name) for name in (
        "u_shadow_on", "u_shadow_params", "u_shadow_offset", "u_shadow",
        "u_shadow_map"))


def set_matrix(location, matrix):
    """Матрица света (4×4 float32 по строкам) в шейдер."""
    gpu._uniform_matrix(location, 1, GL.GL_TRUE,
                        ctypes.c_void_p(matrix.ctypes.data))
