# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Ресурсы видеокарты: программа шейдеров, сетки тайлов, текстуры.

Все функции вызываются только в главном потоке и только при текущем
контексте OpenGL. Устройство описано в AGENTS.md, раздел «Кадр».
"""
import ctypes
from collections import deque

import numpy as np
from OpenGL import GL
from OpenGL.error import GLError
from OpenGL.raw.GL.VERSION.GL_1_1 import glBindTexture as _bind_texture
from OpenGL.raw.GL.VERSION.GL_1_1 import glDrawElements as _draw_elements
from OpenGL.raw.GL.VERSION.GL_1_1 import glGetError as _get_error
from OpenGL.raw.GL.VERSION.GL_1_3 import glActiveTexture as _active_texture
from OpenGL.raw.GL.VERSION.GL_2_0 import glUniform4f as _uniform4f
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


def build_program(vertex, fragment, geometry=None):
    """Программа из вершинного, фрагментного и, если дан, геометрического
    шейдера.

    glValidateProgram не вызывается. В профиле Core он требует
    привязанного массива вершин и на части драйверов даёт ложный отказ.
    """
    shaders = [_compile(GL.GL_VERTEX_SHADER, vertex),
               _compile(GL.GL_FRAGMENT_SHADER, fragment)]
    if geometry is not None:
        shaders.append(_compile(GL.GL_GEOMETRY_SHADER, geometry))
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
        # Сетка создаётся в кадре для каждого нового тайла, вызовы идут
        # через gl без отпускания GIL, см. hold_gil.
        self.vao = gl.gen_names("glGenVertexArrays", 1)[0]
        self.vbo, self.ebo = gl.gen_names("glGenBuffers", 2)
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.buffer_data(GL.GL_ARRAY_BUFFER, data)
        gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        gl.buffer_data(GL.GL_ELEMENT_ARRAY_BUFFER, indices)
        for index, size, offset in ((0, 3, 0), (1, 2, 3), (2, 1, 5)):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(index, size, GL.GL_FLOAT, GL.GL_FALSE,
                                     STRIDE, ctypes.c_void_p(offset * 4))
        gl.glBindVertexArray(0)

    def draw(self):
        GL.glBindVertexArray(self.vao)
        GL.glDrawElements(GL.GL_TRIANGLES, self.count, GL.GL_UNSIGNED_SHORT,
                          ctypes.c_void_p(0))

    def delete(self):
        gl.delete_names("glDeleteVertexArrays", [self.vao])
        gl.delete_names("glDeleteBuffers", [self.vbo, self.ebo])


NO_OVERLAY = (0.0, 0.0, 1.0)

# Горячие вызовы, которые не отпускают GIL. Имя, возвращаемый тип,
# типы аргументов. Имена - как у функций OpenGL.raw выше.
_HOLD_GIL = (
    ("_bind_texture", "glBindTexture", (ctypes.c_uint, ctypes.c_uint)),
    ("_draw_elements", "glDrawElements",
     (ctypes.c_uint, ctypes.c_int, ctypes.c_uint, ctypes.c_void_p)),
    ("_uniform_matrix", "glUniformMatrix4fv",
     (ctypes.c_int, ctypes.c_int, ctypes.c_ubyte, ctypes.c_void_p)),
    ("_bind_vao", "glBindVertexArray", (ctypes.c_uint,)),
    ("_active_texture", "glActiveTexture", (ctypes.c_uint,)),
    ("_uniform4f", "glUniform4f",
     (ctypes.c_int, ctypes.c_float, ctypes.c_float, ctypes.c_float,
      ctypes.c_float)),
)


_F = ctypes.c_float
_U = ctypes.c_uint
_I = ctypes.c_int
_P = ctypes.c_void_p
# Вызовы кадра вне draw_batch: имя и типы аргументов. Указатели
# передаются адресом массива NumPy, обёртки ниже берут сам массив.
_FRAME_CALLS = (
    ("glClearColor", (_F, _F, _F, _F)),
    ("glClear", (_U,)),
    ("glEnable", (_U,)),
    ("glDisable", (_U,)),
    ("glUseProgram", (_U,)),
    ("glUniform1i", (_I, _I)),
    ("glUniform1f", (_I, _F)),
    ("glUniform2f", (_I, _F, _F)),
    ("glUniform3f", (_I, _F, _F, _F)),
    ("glUniform4f", (_I, _F, _F, _F, _F)),
    ("glDepthFunc", (_U,)),
    ("glDepthMask", (ctypes.c_ubyte,)),
    ("glBindVertexArray", (_U,)),
    ("glBindTexture", (_U, _U)),
    ("glActiveTexture", (_U,)),
    ("glDrawArrays", (_U, _I, _I)),
    ("glPixelStorei", (_U, _I)),
    ("glUniformMatrix3fv", (_I, _I, ctypes.c_ubyte, _P)),
    ("glTexSubImage2D", (_U, _I, _I, _I, _I, _I, _U, _U, _P)),
    # Выделение текстур в запас: оно идёт в кадрах без движения, то есть
    # во время загрузки почти в каждом кадре.
    ("glTexImage2D", (_U, _I, _I, _I, _I, _I, _U, _U, _P)),
    ("glTexParameteri", (_U, _U, _I)),
    ("glTexParameterf", (_U, _U, _F)),
    ("glGenTextures", (_I, _P)),
    # Сетки новых тайлов.
    ("glGenVertexArrays", (_I, _P)),
    ("glGenBuffers", (_I, _P)),
    ("glDeleteVertexArrays", (_I, _P)),
    ("glDeleteBuffers", (_I, _P)),
    ("glBindBuffer", (_U, _U)),
    ("glBufferData", (_U, ctypes.c_ssize_t, _P, _U)),
    ("glEnableVertexAttribArray", (_U,)),
    ("glVertexAttribPointer", (_U, _I, _U, ctypes.c_ubyte, _I, _P)),
)


class _FrameGL:
    """Вызовы OpenGL кадра. До hold_gil - функции PyOpenGL."""

    def __init__(self):
        for name, _ in _FRAME_CALLS:
            setattr(self, name, getattr(GL, name))
        self.fast = False

    def matrix3(self, location, transpose, matrix):
        """glUniformMatrix3fv для массива 3×3 float32."""
        if self.fast:
            data = np.ascontiguousarray(matrix, dtype=np.float32)
            self.glUniformMatrix3fv(location, 1, transpose, data.ctypes.data)
        else:
            GL.glUniformMatrix3fv(location, 1, transpose, matrix)

    def gen_names(self, function, count):
        """Имена новых объектов через glGen*, список чисел."""
        if self.fast:
            names = (ctypes.c_uint * count)()
            getattr(self, function)(count, ctypes.addressof(names))
            return [int(n) for n in names]
        return [int(n) for n in np.ravel(getattr(GL, function)(count))]

    def delete_names(self, function, names):
        """Удалить объекты через glDelete*."""
        if self.fast:
            array = (ctypes.c_uint * len(names))(*names)
            getattr(self, function)(len(names), ctypes.addressof(array))
        else:
            getattr(GL, function)(len(names), list(names))

    def buffer_data(self, target, array):
        """glBufferData из массива NumPy, GL_STATIC_DRAW."""
        if self.fast:
            self.glBufferData(target, array.nbytes, array.ctypes.data,
                              GL.GL_STATIC_DRAW)
        else:
            GL.glBufferData(target, array.nbytes, array, GL.GL_STATIC_DRAW)

    def gen_texture(self):
        """Имя новой текстуры."""
        if self.fast:
            name = (ctypes.c_uint * 1)()
            self.glGenTextures(1, ctypes.addressof(name))
            return int(name[0])
        return int(np.ravel(GL.glGenTextures(1))[0])

    def tex_sub(self, level, size, rgba):
        """glTexSubImage2D уровня квадратной текстуры RGBA из массива."""
        if self.fast:
            data = np.ascontiguousarray(rgba, dtype=np.uint8)
            self.glTexSubImage2D(GL.GL_TEXTURE_2D, level, 0, 0, size, size,
                                 GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                                 data.ctypes.data)
        else:
            GL.glTexSubImage2D(GL.GL_TEXTURE_2D, level, 0, 0, size, size,
                               GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, rgba)


gl = _FrameGL()


_RAW = {"_bind_texture": _bind_texture, "_draw_elements": _draw_elements,
        "_uniform_matrix": _uniform_matrix, "_bind_vao": _bind_vao,
        "_active_texture": _active_texture, "_uniform4f": _uniform4f}


def release_gil():
    """Вернуть вызовы OpenGL.raw и PyOpenGL, для сравнения в замерах."""
    globals().update(_RAW)
    for name, _ in _FRAME_CALLS:
        setattr(gl, name, getattr(GL, name))
    gl.fast = False


def hold_gil(context):
    """Перевести горячие вызовы кадра на указатели без отпускания GIL.

    Функции ctypes, как у OpenGL.raw, отпускают GIL на время вызова.
    Если в это время рабочий поток выполняет Python, главный поток ждёт
    GIL обратно до интервала переключения, 5 мс. За кадр таких вызовов
    сотни. Проверка 26 сентября 2026 года, tools/qgis_gil.py: при потоке
    чистого Python участок отрисовки занял 1022 мс в медиане против
    1.3 мс без него.

    Указатели строятся через ctypes.PYFUNCTYPE, он не отпускает GIL.
    Адреса даёт QOpenGLContext.getProcAddress текущего контекста.
    Соглашение о вызове cdecl, на Windows x64 оно единственное. Если
    адрес не получен, остаётся функция OpenGL.raw. Возвращает имена
    переведённых функций.
    """
    done = []
    for name, gl_name, argtypes in _HOLD_GIL:
        address = context.getProcAddress(gl_name.encode())
        address = int(address) if address is not None else 0
        if not address:
            continue
        globals()[name] = ctypes.PYFUNCTYPE(None, *argtypes)(address)
        done.append(gl_name)
    fast = {}
    for gl_name, argtypes in _FRAME_CALLS:
        address = context.getProcAddress(gl_name.encode())
        address = int(address) if address is not None else 0
        if not address:
            break
        fast[gl_name] = ctypes.PYFUNCTYPE(None, *argtypes)(address)
    else:
        # Все или ни одного: у обёрток с указателями разные аргументы.
        for gl_name, function in fast.items():
            setattr(gl, gl_name, function)
        gl.fast = True
        done += list(fast)
    return done


def draw_batch(items, mvps, u_mvp, layers=()):
    """Нарисовать набор сеток, у каждой своя текстура и матрица.

    items - пары (GpuMesh, текстура), mvps - массив (N, 4, 4) float32
    по строкам, как его даёт Camera.tiles_mvp. Подложка идёт на блок 0.
    layers - слои поверх неё: (текстурный блок, место окна в шейдере,
    пары (текстура, окно (сдвиг u, сдвиг v, масштаб)) по одной на сетку).
    Это наложение слоёв проекта, облака и температура. Блоки слоёв,
    которых в списке нет, не трогаются.

    Горячий путь кадра идёт через функции OpenGL.raw без проверки ошибок
    после каждого вызова. Замер 26 сентября 2026 года: glUniformMatrix4fv
    с проверкой 36 мкс, без неё 6 мкс. Ошибки ловит frame_errors раз
    в кадр. Привязка и окно слоя меняются, только когда отличаются
    от прошлой сетки.
    """
    base = mvps.ctypes.data
    stride = mvps.strides[0]
    last_texture = None
    last = [[None, None] for _ in layers]
    null = ctypes.c_void_p(0)
    for i, (mesh, texture) in enumerate(items):
        for n, (unit, u_uv, pairs) in enumerate(layers):
            image, window = pairs[i]
            seen = last[n]
            if image != seen[0]:
                _active_texture(unit)
                _bind_texture(GL.GL_TEXTURE_2D, image)
                _active_texture(GL.GL_TEXTURE0)
                seen[0] = image
            if window != seen[1]:
                _uniform4f(u_uv, window[0], window[1], window[2], 0.0)
                seen[1] = window
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
        # Очередь, а не стек. Освобождённая только что текстура могла
        # рисоваться в прошлом кадре, и запись в неё заставила бы драйвер
        # ждать видеокарту. Берётся освобождённая раньше всех.
        self.free = deque()
        self.levels = TILE_SIZE.bit_length()  # 256 -> 9 уровней

    def allocate(self, count):
        """Выделить count пустых текстур в запас."""
        for _ in range(count):
            texture = gl.gen_texture()
            gl.glBindTexture(GL.GL_TEXTURE_2D, texture)
            for level in range(self.levels):
                size = TILE_SIZE >> level
                gl.glTexImage2D(GL.GL_TEXTURE_2D, level, GL.GL_RGBA8, size,
                                size, 0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE,
                                None)
            _texture_parameters(self.levels, self.anisotropy)
            self.free.append(texture)
        gl.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def acquire(self, levels):
        """Текстура с картинкой тайла, из запаса, если он не пуст."""
        fits = (isinstance(levels, list) and len(levels) == self.levels
                and levels[0].shape[:2] == (TILE_SIZE, TILE_SIZE))
        if not fits or not self.free:
            return create_texture(levels, self.anisotropy)
        texture = self.free.popleft()
        gl.glBindTexture(GL.GL_TEXTURE_2D, texture)
        gl.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 4)
        for level, rgba in enumerate(levels):
            gl.tex_sub(level, rgba.shape[0], rgba)
        gl.glBindTexture(GL.GL_TEXTURE_2D, 0)
        return texture

    def release(self, texture):
        if len(self.free) < self.limit:
            self.free.append(texture)
        else:
            delete_texture(texture)

    def delete_all(self):
        for texture in self.free:
            delete_texture(texture)
        self.free = deque()


def _texture_parameters(levels, anisotropy):
    """Фильтрация и края для привязанной текстуры тайла."""
    gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAX_LEVEL,
                       levels - 1)
    gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER,
                       GL.GL_LINEAR_MIPMAP_LINEAR)
    gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER,
                       GL.GL_LINEAR)
    gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S,
                       GL.GL_CLAMP_TO_EDGE)
    gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T,
                       GL.GL_CLAMP_TO_EDGE)
    if anisotropy > 1.0:
        gl.glTexParameterf(GL.GL_TEXTURE_2D, TEXTURE_MAX_ANISOTROPY,
                           anisotropy)
