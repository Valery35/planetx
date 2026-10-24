# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слой снимков неба HiPS в виде неба (core/hips.py, Layer).

Тайл - сетка вершин-направлений на бесконечности, как у линий
созвездий (w = 0, глубина 1.0), с картинкой тайла. Рисуются от
грубых к подробным: подробный тайл закрывает предка. Пока подробного
нет, виден загруженный предок не мельче layer.low, у слоя с Allsky -
тайл порядка 3 из Allsky.jpg. Слой проявляется по полю зрения
(hips.share) смешиванием с тем, что нарисовано под ним. Выбор тайлов
вида - want, загрузку ведёт ui/skysurvey.py.

Пришедшая картинка проявляется из прозрачности за appear.DURATION той же
кривой, что тайлы Земли. Пока она проявляется, под ней рисуется ближайший
готовый предок или Allsky.
"""
import ctypes
import math
import time
from collections import OrderedDict

import numpy as np
from OpenGL import GL

from ..core import appear, hips
from . import gpu
from .gpu import gl
from .stars import sky_mvp

TILE_VERTEX = """#version 330 core
layout(location = 0) in vec3 a_dir;
layout(location = 1) in vec2 a_uv;
uniform mat4 u_mvp;
uniform vec4 u_rect;
out vec2 v_uv;
void main() {
    vec4 p = u_mvp * vec4(a_dir, 0.0);
    gl_Position = p.xyww;
    v_uv = u_rect.xy + a_uv * u_rect.zw;
}
"""

TILE_FRAGMENT = """#version 330 core
uniform sampler2D u_map;
uniform float u_alpha;
in vec2 v_uv;
out vec4 frag;
void main() {
    frag = vec4(texture(u_map, v_uv).rgb, u_alpha);
}
"""

KEEP = 160  # тайлов в видеокарте, около 160 МБ с мипмапами
UPLOADS = 3  # новых текстур за кадр
MESHES = 600  # сеток тайлов в памяти
WANT_LIMIT = 120  # тайлов вида не больше
ALLSKY = "allsky"  # ключ времени появления Allsky в born


class HipsSky:
    """Тайлы одного слоя в видеокарте и выбор тайлов вида."""

    def __init__(self, layer):
        self.layer = layer
        self.program = None
        self.locations = {}
        self.indices = hips.mesh_indices()
        self.ebo = None
        self.top = layer.top
        self.share = 0.0  # проявление слоя в последнем кадре
        self.allsky = None  # (текстура, ширина, высота)
        self.allsky_pending = None
        self.textures = OrderedDict()  # (порядок, номер): текстура
        self.pending = OrderedDict()  # (порядок, номер): RGBA
        self.meshes = OrderedDict()  # (порядок, номер): (vao, vbo)
        self.want = []  # недостающие тайлы вида, важные первыми
        self.drawn = 0
        self.born = {}  # ключ тайла или ALLSKY: время появления картинки
        self.fading = False  # в последнем кадре что-то проявлялось
        self.fade = True  # проявлять пришедшие картинки

    def set_allsky(self, rgba):
        self.allsky_pending = rgba

    def add_tile(self, key, rgba):
        self.pending[key] = rgba

    def has(self, key):
        return key in self.textures or key in self.pending

    def init_gl(self):
        self.program = gpu.build_program(TILE_VERTEX, TILE_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in ("u_mvp", "u_rect", "u_map", "u_alpha")}
        self.ebo = int(np.ravel(GL.glGenBuffers(1))[0])
        gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, self.indices.nbytes,
                        self.indices, GL.GL_STATIC_DRAW)
        gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, 0)

    def release_gl(self):
        """Освободить всё в видеокарте. Картинки придут заново."""
        self._drop_textures()
        for vao, vbo in self.meshes.values():
            GL.glDeleteVertexArrays(1, [vao])
            GL.glDeleteBuffers(1, [vbo])
        self.meshes.clear()
        if self.ebo is not None:
            GL.glDeleteBuffers(1, [self.ebo])
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = self.ebo = None

    def _drop_textures(self):
        if self.program is not None:
            for texture in self.textures.values():
                gpu.delete_texture(texture)
            if self.allsky is not None:
                gpu.delete_texture(self.allsky[0])
        self.textures.clear()
        self.born.clear()
        self.allsky = None

    def _mesh(self, key):
        mesh = self.meshes.get(key)
        if mesh is not None:
            self.meshes.move_to_end(key)
            return mesh
        dirs, uv = hips.tile_mesh(*key)
        data = np.ascontiguousarray(np.hstack([dirs, uv]), dtype=np.float32)
        vao = int(np.ravel(GL.glGenVertexArrays(1))[0])
        vbo = int(np.ravel(GL.glGenBuffers(1))[0])
        gl.glBindVertexArray(vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STATIC_DRAW)
        gl.glEnableVertexAttribArray(0)
        gl.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, 20,
                                 ctypes.c_void_p(0))
        gl.glEnableVertexAttribArray(1)
        gl.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, 20,
                                 ctypes.c_void_p(12))
        gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        gl.glBindVertexArray(0)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, 0)
        self.meshes[key] = (vao, vbo)
        while len(self.meshes) > MESHES:
            _, (old_vao, old_vbo) = self.meshes.popitem(last=False)
            GL.glDeleteVertexArrays(1, [old_vao])
            GL.glDeleteBuffers(1, [old_vbo])
        return vao, vbo

    def _upload(self):
        if self.allsky_pending is not None:
            rgba = self.allsky_pending
            self.allsky_pending = None
            self.allsky = (gpu.create_texture(rgba), rgba.shape[1],
                           rgba.shape[0])
            self.born[ALLSKY] = time.monotonic()
        for _ in range(UPLOADS):
            if not self.pending:
                break
            key, rgba = self.pending.popitem(last=False)
            self.textures[key] = gpu.create_texture(rgba)
            self.born[key] = time.monotonic()
        while len(self.textures) > KEEP:
            key, texture = self.textures.popitem(last=False)
            self.born.pop(key, None)
            gpu.delete_texture(texture)

    def opacity(self, key):
        """Доля проявления картинки тайла или Allsky, 0..1."""
        born = self.born.get(key)
        if born is None or not self.fade:
            return 1.0
        return 1.0 - appear.curve((time.monotonic() - born)
                                  / appear.DURATION)

    def select(self, axis, reach, radians_per_pixel):
        """Тайлы кадра: что рисовать (от грубых к подробным) и чего
        не хватает. Порядок тайлов вида - по пикселю экрана."""
        order = hips.order_for(radians_per_pixel, self.top)
        if order is None and not self.layer.allsky:
            order = self.layer.low
        if order is not None:
            order = max(order, self.layer.low)
        draw = set()  # (ключ, вид); вид "allsky" рисуется до "tile"
        want = []
        if order is not None:
            cells = hips.visible(order, axis, reach)
            if len(cells) > WANT_LIMIT:
                # Поле шире, чем держит запас: тайлы порядком грубее.
                while order > self.layer.low and len(cells) > WANT_LIMIT:
                    order -= 1
                    cells = hips.visible(order, axis, reach)
            near = hips.centers(order, cells) @ axis
            for ipix in cells[np.argsort(-near)]:
                ipix = int(ipix)
                if (order, ipix) not in self.textures:
                    want.append((order, ipix))
                # Готовый тайл и, пока он проявляется, предки под ним.
                for level in range(order, self.layer.low - 1, -1):
                    key = (level, ipix >> (2 * (order - level)))
                    if key in self.textures:
                        draw.add((key, "tile"))
                        self.textures.move_to_end(key)
                        if self.opacity(key) >= 1.0:
                            break
                else:
                    if self.layer.allsky:
                        draw.add(((hips.MIN_ORDER, ipix >> (
                            2 * (order - hips.MIN_ORDER))), "allsky"))
        else:
            for ipix in hips.visible(hips.MIN_ORDER, axis, reach):
                draw.add(((hips.MIN_ORDER, int(ipix)), "allsky"))
        self.want = [k for k in want if k not in self.pending]
        return sorted(draw)

    def draw(self, camera, view, share=1.0):
        """Нарисовать слой с долей проявления share поверх того, что
        под ним. view - core.skyview.SkyView. Без проявления тайлы вида
        не просятся."""
        self.drawn = 0
        self.share = share
        if self.program is None:
            return
        self._upload()
        if share <= 0.0:
            self.want = []
            return
        t = math.tan(math.radians(camera.fov_y) / 2.0)
        reach = math.atan(t * math.hypot(1.0, camera.aspect))
        items = self.select(view.forward(), reach,
                            view.radians_per_pixel(camera.height))
        mvp = sky_mvp(camera, 0.0, np.eye(3))
        loc = self.locations
        gl.glUseProgram(self.program)
        gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                            ctypes.c_void_p(mvp.ctypes.data))
        gl.glUniform1i(loc["u_map"], 0)
        gl.glActiveTexture(GL.GL_TEXTURE0)
        gl.glEnable(GL.GL_BLEND)
        gpu.gl.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
        gl.glDepthFunc(GL.GL_LEQUAL)
        gl.glDepthMask(GL.GL_FALSE)
        count = len(self.indices)
        null = ctypes.c_void_p(0)
        self.fading = False
        try:
            for key, kind in items:
                if kind == "tile":
                    texture = self.textures[key]
                    rect = (0.0, 0.0, 1.0, 1.0)
                    seen = self.opacity(key)
                elif self.allsky is not None:
                    texture, width, height = self.allsky
                    rect = hips.allsky_rect(key[1], width, height)
                    seen = self.opacity(ALLSKY)
                else:
                    continue
                if seen < 1.0:
                    self.fading = True
                vao, _ = self._mesh(key)
                gl.glBindTexture(GL.GL_TEXTURE_2D, texture)
                gl.glUniform1f(loc["u_alpha"], float(share * seen))
                gl.glUniform4f(loc["u_rect"], *(float(v) for v in rect))
                gl.glBindVertexArray(vao)
                gpu._draw_elements(GL.GL_TRIANGLES, count,
                                   GL.GL_UNSIGNED_INT, null)
                self.drawn += 1
        finally:
            gl.glBindVertexArray(0)
            gl.glBindTexture(GL.GL_TEXTURE_2D, 0)
            gl.glDisable(GL.GL_BLEND)
            gl.glDepthMask(GL.GL_TRUE)
            gl.glDepthFunc(GL.GL_LESS)
