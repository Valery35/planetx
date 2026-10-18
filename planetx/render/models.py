# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-модели в видеокарте (core/models.py).

Модель - части одного материала: буферы вершин core.models.
MODEL_VERTEX от точки модели и картинка или цвет. Окно глобуса
отдаёт модели списком, точку каждой модели вид считает по рельефу
каждый кадр, где пришли новые высоты (anchor). Модели рисуются после
поверхности с проверкой и записью глубины, как здания, свет с двух
сторон.

Анимированная модель (core/animation.py) получает у части с дорожкой
свою матрицу на момент: время идёт по кругу длительности от показа
модели, пока модель видна, вид просит кадр раз в ANIMATION_TICK.

Движущаяся модель (модель трека, поезд) несёт mover - по моменту он
даёт точку и поворот 3×3 вершин, посчитанных на исходном месте. Модели
с одним mesh делят буферы видеокарты: сотня поездов - одна загрузка.
"""
import ctypes
import time

import numpy as np
from OpenGL import GL

from ..core.animation import frame_delta
from ..core.models import MODEL_VERTEX
from ..core.tiling import AMBIENT
from . import gpu
from .gpu import gl
from .buildings import _latlon, light_at
from .shaders import MODEL_FRAGMENT, MODEL_VERTEX as VERTEX_SHADER

UNIFORMS = ("u_mvp", "u_turn", "u_light", "u_ambient", "u_image",
            "u_textured", "u_color")
# Кадр анимированной модели - не чаще, мс. Выбор помощника.
ANIMATION_TICK = 33
STILL = np.eye(3, dtype=np.float32)


class _Part:
    """Часть модели в видеокарте: буфер вершин и картинка."""

    def __init__(self, vertices, rgba, color, track=None):
        vertices = np.ascontiguousarray(vertices, dtype=MODEL_VERTEX)
        self.count = len(vertices)
        self.color = color
        self.track = track
        self.vao = gl.gen_names("glGenVertexArrays", 1)[0]
        self.vbo = gl.gen_names("glGenBuffers", 1)[0]
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.buffer_data(GL.GL_ARRAY_BUFFER, vertices)
        stride = MODEL_VERTEX.itemsize
        for index, size, field in ((0, 3, "position"), (1, 3, "normal"),
                                   (2, 2, "uv")):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(
                index, size, GL.GL_FLOAT, GL.GL_FALSE, stride,
                ctypes.c_void_p(MODEL_VERTEX.fields[field][1]))
        gl.glBindVertexArray(0)
        self.texture = None
        if rgba is not None:
            self.texture = gpu.create_texture(rgba)
            # Картинки моделей повторяются по грани, как в SketchUp.
            gl.glBindTexture(GL.GL_TEXTURE_2D, self.texture)
            gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S,
                               GL.GL_REPEAT)
            gl.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T,
                               GL.GL_REPEAT)
            gl.glBindTexture(GL.GL_TEXTURE_2D, 0)

    def delete(self):
        gpu.gl.delete_names("glDeleteVertexArrays", [self.vao])
        gpu.gl.delete_names("glDeleteBuffers", [self.vbo])
        if self.texture is not None:
            gpu.delete_texture(self.texture)


class Model:
    """Модель для вида: части и место.

    parts - [(вершины MODEL_VERTEX, картинка RGBA или None, цвет RGBA
    0-1, дорожка анимации или None)], place - (широта, долгота,
    altitudeMode, высота), radius - радиус шара вокруг точки, метры,
    alpha - непрозрачность 0-1. animation - core.animation.Animation
    или None, frame - матрица core.models.frame места модели.

    mover(now) - (широта, долгота, поворот 3×3 вершин) на момент
    time.monotonic, четвёртым числом - высота по altitudeMode места,
    или None, если модели сейчас нет. live - mover
    меняется со временем сам, вид просит кадры. mesh - ключ буферов,
    общий у одинаковых моделей, без него - key."""

    def __init__(self, key, parts, place, radius, alpha=1.0,
                 animation=None, frame=None, mover=None, live=False,
                 mesh=None):
        self.key = key
        self.parts = parts
        self.place = place
        self.radius = radius
        self.alpha = alpha
        self.animation = animation
        self.frame = frame
        self.mover = mover
        self.live = live
        self.mesh = key if mesh is None else mesh
        self.linear = None  # поворот вершин от mover в этом кадре


def _moved(linear, pose):
    """Поза части движущейся модели: поворот вершин linear после
    анимации части pose или без неё."""
    matrix = np.eye(4)
    matrix[:3, :3] = linear
    if pose is not None:
        matrix = matrix @ pose[0]
    try:
        turn = np.linalg.inv(matrix[:3, :3]).T
    except np.linalg.LinAlgError:
        turn = matrix[:3, :3]
    return matrix, np.ascontiguousarray(turn, dtype=np.float32)


class Models:
    """3D-модели окна глобуса."""

    def __init__(self):
        self.program = None
        self.locations = {}
        self.source = []  # Model окна
        self.groups = {}  # имя группы - [Model]
        self.loaded = {}  # mesh - [_Part]
        self.hidden = set()  # номера source, которых сейчас нет
        self.pending = True
        self.centers = []  # точки моделей в ECEF, по source
        # anchor(Model) - точка модели в ECEF по рельефу, ставит вид.
        self.anchor = None
        self.drawn = 0
        # Есть ли на виде анимированная модель - вид просит кадры.
        self.animated = False
        self.started = {}  # ключ - начало анимации, time.monotonic

    @property
    def active(self):
        return bool(self.source)

    def init_gl(self):
        self.program = gpu.build_program(VERTEX_SHADER, MODEL_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in UNIFORMS}

    def release_gl(self):
        for parts in self.loaded.values():
            for part in parts:
                part.delete()
        self.loaded = {}
        self.pending = True
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = None

    def set_models(self, items, group="overlays"):
        """Новый список Model группы: наложения «Моих меток», треки,
        поезда. Части загружаются в видеокарту в кадре, модели
        с прежним mesh не загружаются заново."""
        self.groups[group] = list(items)
        self.source = [item for items in self.groups.values()
                       for item in items]
        self.pending = True
        self.place()

    def place(self):
        """Точки моделей заново, например после прихода высот."""
        if self.anchor is None:
            self.centers = []
            return
        self.move(time.monotonic())
        self.centers = [self.anchor(item) for item in self.source]

    def move(self, now):
        """Места движущихся моделей на момент now. Возвращает, есть ли
        модель, которая движется сама."""
        self.hidden = set()
        live = False
        for i, item in enumerate(self.source):
            if item.mover is None:
                continue
            live = live or item.live
            found = item.mover(now)
            if found is None:
                self.hidden.add(i)
                continue
            lat, lon, linear = found[:3]
            if len(found) > 3:
                item.place = (lat, lon, item.place[2], found[3])
            else:
                item.place = (lat, lon) + tuple(item.place[2:])
            item.linear = linear
        return live

    def poses(self, item, now):
        """{дорожка: (матрица 4×4 смещений ECEF, поворот нормалей 3×3)}
        анимированной модели на момент now или пустой словарь."""
        if item.animation is None or item.frame is None:
            return {}
        start = self.started.setdefault(item.key, now)
        out = {}
        for track, delta in item.animation.deltas(now - start).items():
            linear, shift = frame_delta(item.frame, delta)
            matrix = np.eye(4)
            matrix[:3, :3] = linear
            matrix[:3, 3] = shift
            try:
                turn = np.linalg.inv(linear).T
            except np.linalg.LinAlgError:
                turn = linear
            out[track] = (matrix, np.ascontiguousarray(turn,
                                                       dtype=np.float32))
        return out

    def nearest(self, eye):
        """Расстояние от глаза до ближайшей модели за вычетом её радиуса,
        не меньше 1 м, или None без моделей."""
        found = None
        for i, (item, center) in enumerate(zip(self.source, self.centers)):
            if i in self.hidden:
                continue
            gap = float(np.linalg.norm(center - eye)) - item.radius
            gap = max(gap, 1.0)
            found = gap if found is None else min(found, gap)
        return found

    def _upload(self):
        meshes = {item.mesh for item in self.source}
        for mesh in list(self.loaded):
            if mesh not in meshes:
                for part in self.loaded.pop(mesh):
                    part.delete()
        for item in self.source:
            if item.mesh not in self.loaded:
                self.loaded[item.mesh] = [_Part(*part)
                                          for part in item.parts]
        keys = {item.key for item in self.source}
        self.started = {key: value for key, value in self.started.items()
                        if key in keys}
        self.pending = False

    def draw(self, camera):
        """Нарисовать модели после поверхности, глубина включена."""
        self.drawn = 0
        self.animated = False
        if self.program is None or not self.source:
            return
        if self.pending:
            self._upload()
        now = time.monotonic()
        if any(item.mover is not None for item in self.source):
            # Движущиеся модели встают на своё место каждый кадр.
            self.animated = self.move(now)
            if self.anchor is not None:
                self.centers = [self.anchor(item) for item in self.source]
        if len(self.centers) != len(self.source):
            self.place()
        if len(self.centers) != len(self.source):
            return
        whole = np.asarray(camera.tiles_mvp(self.centers), dtype=np.float64)
        mvps = np.ascontiguousarray(whole, dtype=np.float32)
        loc = self.locations
        gl.glUseProgram(self.program)
        lat, lon = _latlon(np.asarray(camera.eye, dtype=np.float64))
        gl.glUniform3f(loc["u_light"], *light_at(lat, lon).tolist())
        gl.glUniform1f(loc["u_ambient"], AMBIENT)
        gl.glUniform1i(loc["u_image"], 0)
        gl.glActiveTexture(GL.GL_TEXTURE0)
        gl.glEnable(GL.GL_BLEND)
        gl.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        base = mvps.ctypes.data
        stride = mvps.strides[0]
        try:
            for i, item in enumerate(self.source):
                if i in self.hidden:
                    continue
                poses = self.poses(item, now)
                if poses:
                    self.animated = True
                move = item.linear if item.mover is not None else None
                for part in self.loaded.get(item.mesh, ()):
                    pose = poses.get(part.track)
                    if move is not None:
                        pose = _moved(move, pose)
                    if pose is None:
                        gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                            ctypes.c_void_p(
                                                base + stride * i))
                        GL.glUniformMatrix3fv(loc["u_turn"], 1, GL.GL_TRUE,
                                              STILL)
                    else:
                        moved = np.ascontiguousarray(
                            whole[i] @ pose[0], dtype=np.float32)
                        gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                            ctypes.c_void_p(
                                                moved.ctypes.data))
                        GL.glUniformMatrix3fv(loc["u_turn"], 1, GL.GL_TRUE,
                                              pose[1])
                    red, green, blue, alpha = part.color
                    gl.glUniform4f(loc["u_color"], red, green, blue,
                                   alpha * item.alpha)
                    if part.texture is not None:
                        gl.glBindTexture(GL.GL_TEXTURE_2D, part.texture)
                        gl.glUniform1f(loc["u_textured"], 1.0)
                    else:
                        gl.glUniform1f(loc["u_textured"], 0.0)
                    gpu._bind_vao(part.vao)
                    gl.glDrawArrays(GL.GL_TRIANGLES, 0, part.count)
                self.drawn += 1
        finally:
            gpu._bind_vao(0)
            gl.glBindTexture(GL.GL_TEXTURE_2D, 0)
            gl.glDisable(GL.GL_BLEND)
