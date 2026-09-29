# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Картинка неба с Млечным путём позади Земли.

Проход на весь экран на глубине 1.0, как у неба с гало: Земля его
закрывает. Для пикселя считается направление взгляда, оно
поворачивается в экваториальную систему на звёздное время и даёт
прямое восхождение и склонение, то есть точку на картинке. Свет
картинки прибавляется к небу, альфа кадра не меняется. Картинка
8192×4096 грузится в видеокарту один раз, без мипмапов: пиксель
экрана при угле обзора 45° примерно равен текселю картинки.
Точечные звёзды каталога рисуются поверх, render/stars.py.
"""
import time

import numpy as np
from OpenGL import GL

from ..core import stars
from . import gpu
from .shaders import HOLE_VERTEX

SKY_FRAGMENT = """#version 330 core
uniform mat3 u_sky;       // оси камеры в экваториальной системе
uniform vec2 u_tan;       // tan(fov/2)·aspect и tan(fov/2)
uniform vec2 u_viewport;  // размер кадра в пикселях
uniform float u_gain;     // яркость с угасанием по высоте
uniform float u_floor;    // порог чёрного, ниже него зерно слабых звёзд
uniform sampler2D u_map;
out vec4 frag;
const float PI = 3.14159265358979;
void main() {
    vec2 ndc = gl_FragCoord.xy / u_viewport * 2.0 - 1.0;
    vec3 d = normalize(u_sky * vec3(ndc.x * u_tan.x, ndc.y * u_tan.y,
                                    -1.0));
    // Уровень 0 явно: на шве 0h производные координат рвутся,
    // и выбор уровня по ним дал бы полосу.
    vec2 uv = vec2(fract(atan(d.y, d.x) / (2.0 * PI)),
                   acos(clamp(d.z, -1.0, 1.0)) / PI);
    vec3 c = max(textureLod(u_map, uv, 0.0).rgb - u_floor, 0.0)
        / (1.0 - u_floor);
    frag = vec4(c * u_gain, 1.0);
}
"""


def fit(rgba, max_size):
    """Картинка не шире max_size: делится пополам, пока не влезет."""
    while rgba.shape[1] > max_size:
        rgba = rgba[::2, ::2]
    return np.ascontiguousarray(rgba)


def sky_matrix(camera, unix_time):
    """Оси камеры в экваториальной системе, по строкам, float32."""
    return np.ascontiguousarray(
        stars.sky_rotation(unix_time).T @ camera.rotation, dtype=np.float32)


class Sky:
    """Картинка неба в видеокарте."""

    def __init__(self):
        self.program = None
        self.texture = None
        self.pending = None  # массив RGBA до загрузки в видеокарту
        self.locations = {}
        self.empty_vao = None
        self.drawn = False  # картинка была в последнем кадре

    def set_image(self, rgba):
        """Пришла картинка неба. В видеокарту она уйдёт в кадре."""
        self.pending = rgba

    def init_gl(self, empty_vao):
        self.program = gpu.build_program(HOLE_VERTEX, SKY_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_sky", "u_tan", "u_viewport",
                                       "u_gain", "u_floor", "u_map")}
        self.empty_vao = empty_vao

    def release_gl(self):
        if self.texture is not None:
            GL.glDeleteTextures(1, [self.texture])
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = self.texture = None

    def _upload(self):
        rgba = fit(self.pending, int(GL.glGetIntegerv(
            GL.GL_MAX_TEXTURE_SIZE)))
        self.pending = None
        if self.texture is None:
            self.texture = gpu.gl.gen_texture()
        GL.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
        GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGB8, rgba.shape[1],
                        rgba.shape[0], 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                        rgba)
        for name, value in ((GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR),
                            (GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT),
                            (GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE),
                            (GL.GL_TEXTURE_MAX_LEVEL, 0)):
            GL.glTexParameteri(GL.GL_TEXTURE_2D, name, value)

    def draw(self, camera, unix_time=None):
        """Нарисовать небо после неба с гало и до точечных звёзд."""
        share = stars.fade(camera.altitude())
        self.drawn = False
        if self.program is None or share <= 0.0:
            return
        if self.pending is not None:
            self._upload()
        if self.texture is None:
            return
        loc = self.locations
        gl = gpu.gl
        gl.glUseProgram(self.program)
        gl.matrix3(loc["u_sky"], GL.GL_TRUE, sky_matrix(
            camera, time.time() if unix_time is None else unix_time))
        t = np.tan(np.radians(camera.fov_y) / 2.0)
        gl.glUniform2f(loc["u_tan"], float(t * camera.aspect), float(t))
        gl.glUniform2f(loc["u_viewport"], float(camera.width),
                       float(camera.height))
        gl.glUniform1f(loc["u_gain"], float(stars.SKY_GAIN * share))
        gl.glUniform1f(loc["u_floor"], float(stars.SKY_FLOOR))
        gl.glUniform1i(loc["u_map"], 0)
        gl.glActiveTexture(GL.GL_TEXTURE0)
        gl.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
        gl.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_ONE, GL.GL_ONE, GL.GL_ZERO, GL.GL_ONE)
        gl.glDepthFunc(GL.GL_LEQUAL)
        gl.glDepthMask(GL.GL_FALSE)
        try:
            gl.glBindVertexArray(self.empty_vao)
            gl.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
            self.drawn = True
        finally:
            gl.glBindVertexArray(0)
            gl.glDepthMask(GL.GL_TRUE)
            gl.glDepthFunc(GL.GL_LESS)
            gl.glDisable(GL.GL_BLEND)
