# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Ресурсы видеокарты: программа шейдеров, сетки тайлов, текстуры.

Все функции вызываются только в главном потоке и только при текущем
контексте OpenGL. Устройство описано в AGENTS.md, раздел «Кадр».
"""
import ctypes

import numpy as np
from OpenGL import GL
from OpenGL.error import GLError
from OpenGL.raw.GL.VERSION.GL_1_1 import glBindTexture as _bind_texture
from OpenGL.raw.GL.VERSION.GL_1_1 import glDrawElements as _draw_elements
from OpenGL.raw.GL.VERSION.GL_1_1 import glGetError as _get_error
from OpenGL.raw.GL.VERSION.GL_2_0 import \
    glUniformMatrix4fv as _uniform_matrix
from OpenGL.raw.GL.VERSION.GL_3_0 import glBindVertexArray as _bind_vao

# Расширение анизотропной фильтрации. Константы не входят в ядро 3.3.
TEXTURE_MAX_ANISOTROPY = 0x84FE
MAX_TEXTURE_MAX_ANISOTROPY = 0x84FF
STRIDE = 6 * 4  # x, y, z, u, v и множитель отмывки во float32


class ShaderError(RuntimeError):
    """Шейдер не собрался. Текст ошибки - журнал драйвера."""


def _compile(kind, source):
    shader = GL.glCreateShader(kind)
    GL.glShaderSource(shader, source)
    GL.glCompileShader(shader)
    if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
        log = GL.glGetShaderInfoLog(shader)
        GL.glDeleteShader(shader)
        raise ShaderError(log.decode(errors="replace")
                          if isinstance(log, bytes) else str(log))
    return shader


def build_program(vertex, fragment):
    """Программа из двух шейдеров.

    glValidateProgram не вызывается. В профиле Core он требует
    привязанного массива вершин и на части драйверов даёт ложный отказ.
    """
    shaders = [_compile(GL.GL_VERTEX_SHADER, vertex),
               _compile(GL.GL_FRAGMENT_SHADER, fragment)]
    program = GL.glCreateProgram()
    for shader in shaders:
        GL.glAttachShader(program, shader)
    GL.glLinkProgram(program)
    for shader in shaders:
        GL.glDetachShader(program, shader)
        GL.glDeleteShader(shader)
    if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
        log = GL.glGetProgramInfoLog(program)
        GL.glDeleteProgram(program)
        raise ShaderError(log.decode(errors="replace")
                          if isinstance(log, bytes) else str(log))
    return program


class GpuMesh:
    """Сетка тайла в видеокарте: массив вершин с буферами."""

    def __init__(self, mesh):
        data = np.ascontiguousarray(
            np.concatenate([mesh.positions, mesh.uv, mesh.shade[:, None]],
                           axis=1),
            dtype=np.float32)
        indices = np.ascontiguousarray(mesh.indices)
        self.count = len(indices)
        self.center = mesh.center
        self.vao = GL.glGenVertexArrays(1)
        self.vbo, self.ebo = GL.glGenBuffers(2)
        GL.glBindVertexArray(self.vao)
        GL.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data,
                        GL.GL_STATIC_DRAW)
        GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices,
                        GL.GL_STATIC_DRAW)
        GL.glEnableVertexAttribArray(0)
        GL.glVertexAttribPointer(0, 3, GL.GL_FLOAT, GL.GL_FALSE, STRIDE,
                                 ctypes.c_void_p(0))
        GL.glEnableVertexAttribArray(1)
        GL.glVertexAttribPointer(1, 2, GL.GL_FLOAT, GL.GL_FALSE, STRIDE,
                                 ctypes.c_void_p(3 * 4))
        GL.glEnableVertexAttribArray(2)
        GL.glVertexAttribPointer(2, 1, GL.GL_FLOAT, GL.GL_FALSE, STRIDE,
                                 ctypes.c_void_p(5 * 4))
        GL.glBindVertexArray(0)

    def draw(self):
        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, self.count, GL.GL_UNSIGNED_SHORT,
                          ctypes.c_void_p(0))

    def delete(self):
        GL.glDeleteVertexArrays(1, [self.vao])
        GL.glDeleteBuffers(2, [self.vbo, self.ebo])


def draw_batch(items, mvps, u_mvp):
    """Нарисовать набор сеток, у каждой своя текстура и матрица.

    items - пары (GpuMesh, текстура), mvps - массив (N, 4, 4) float32
    по строкам, как его даёт Camera.tiles_mvp. Горячий путь кадра
    идёт через функции OpenGL.raw без проверки ошибок после каждого
    вызова. Замер 26 сентября 2026 года: glUniformMatrix4fv с проверкой
    36 мкс, без неё 6 мкс. Ошибки ловит frame_errors раз в кадр.
    """
    base = mvps.ctypes.data
    stride = mvps.strides[0]
    last_texture = None
    null = ctypes.c_void_p(0)
    for i, (mesh, texture) in enumerate(items):
        if texture != last_texture:
            _bind_texture(GL.GL_TEXTURE_2D, texture)
            last_texture = texture
        _uniform_matrix(u_mvp, 1, GL.GL_TRUE,
                        ctypes.c_void_p(base + stride * i))
        _bind_vao(mesh.vao)
        _draw_elements(GL.GL_TRIANGLES, mesh.count, GL.GL_UNSIGNED_SHORT,
                       null)


def frame_errors():
    """Коды ошибок OpenGL, накопленные с прошлого вызова."""
    codes = []
    for _ in range(16):
        code = _get_error()
        if not code:
            break
        codes.append(int(code))
    return codes


def max_anisotropy():
    """Наибольшая анизотропия, которую даёт драйвер. 1 - без неё."""
    try:
        return float(GL.glGetFloatv(MAX_TEXTURE_MAX_ANISOTROPY))
    except GLError:
        return 1.0


def create_texture(image, anisotropy=1.0):
    """Текстура с мипмапами.

    image - массив (h, w, 4) uint8 или готовый список уровней от mip_chain.
    Для одного массива мипмапы строит glGenerateMipmap. На новой текстуре
    он стоит 1.6 мс, поэтому тайлы приходят с готовыми уровнями.
    Первая строка массива - верх картинки, у тайла это северный край.
    Она ложится на v = 0.
    """
    levels = image if isinstance(image, list) else [image]
    texture = GL.glGenTextures(1)
    GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
    GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
    for level, rgba in enumerate(levels):
        rgba = np.ascontiguousarray(rgba, dtype=np.uint8)
        h, w = rgba.shape[:2]
        GL.glTexImage2D(GL.GL_TEXTURE_2D, level, GL.GL_RGBA8, w, h, 0,
                        GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, rgba)
    if len(levels) > 1:
        count = len(levels)
    else:
        GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
        count = max(levels[0].shape[:2]).bit_length()
    _texture_parameters(count, anisotropy)
    GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
    return texture


def delete_texture(texture):
    GL.glDeleteTextures(1, [texture])


TILE_SIZE = 256


class TexturePool:
    """Запас текстур тайла 256×256 с выделенной памятью под все уровни.

    Новая текстура с уровнями стоит 3.5 мс главного потока, перезапись
    уровней в готовой через glTexSubImage2D - 0.36 мс. Замер 26 сентября
    2026 года. Вытесненная текстура возвращается в запас.
    """

    def __init__(self, anisotropy, limit=256):
        self.anisotropy = anisotropy
        self.limit = limit
        self.free = []
        self.levels = TILE_SIZE.bit_length()  # 256 -> 9 уровней

    def allocate(self, count):
        """Выделить count пустых текстур в запас."""
        for _ in range(count):
            texture = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
            for level in range(self.levels):
                size = TILE_SIZE >> level
                GL.glTexImage2D(GL.GL_TEXTURE_2D, level, GL.GL_RGBA8, size,
                                size, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                                None)
            _texture_parameters(self.levels, self.anisotropy)
            self.free.append(texture)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def acquire(self, levels):
        """Текстура с картинкой тайла, из запаса, если он не пуст."""
        fits = (isinstance(levels, list) and len(levels) == self.levels
                and levels[0].shape[:2] == (TILE_SIZE, TILE_SIZE))
        if not fits or not self.free:
            return create_texture(levels, self.anisotropy)
        texture = self.free.pop()
        GL.glBindTexture(GL.GL_TEXTURE_2D, texture)
        GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        for level, rgba in enumerate(levels):
            size = rgba.shape[0]
            GL.glTexSubImage2D(GL.GL_TEXTURE_2D, level, 0, 0, size, size,
                               GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, rgba)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return texture

    def release(self, texture):
        if len(self.free) < self.limit:
            self.free.append(texture)
        else:
            delete_texture(texture)

    def delete_all(self):
        for texture in self.free:
            delete_texture(texture)
        self.free = []


def _texture_parameters(levels, anisotropy):
    """Фильтрация и края для привязанной текстуры тайла."""
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAX_LEVEL,
                       levels - 1)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER,
                       GL.GL_LINEAR_MIPMAP_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER,
                       GL.GL_LINEAR)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S,
                       GL.GL_CLAMP_TO_EDGE)
    GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T,
                       GL.GL_CLAMP_TO_EDGE)
    if anisotropy > 1.0:
        GL.glTexParameterf(GL.GL_TEXTURE_2D, TEXTURE_MAX_ANISOTROPY,
                           anisotropy)
