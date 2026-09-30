# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-здания в видеокарте: сетки тайлов, их сборка и отрисовка.

Расчёт - в core/buildings.py. Загрузчик разбирает тайл в рабочем
потоке (core.buildings.footprints). Сетка по высотам рельефа
собирается в своём потоке по снимку хранилища высот, в видеокарту
за кадр уходит не больше UPLOADS сеток. Пришли точнее высоты -
сетка тайла собирается заново, до подмены рисуется прежняя.

Сетка тайла - один массив вершин и один вызов отрисовки. Матрицы
тайлов считаются одной операцией NumPy, как у тайлов подложки,
вызовы идут через указатели gpu без отпускания GIL.
"""
import ctypes
import math
from collections import OrderedDict

import numpy as np
from OpenGL import GL
from qgis.PyQt.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from ..core import buildings as core
from ..core import sun as core_sun
from ..core.ellipsoid import ecef_to_geodetic, surface_normal
from ..core.tiling import AMBIENT, LIGHT_ELEVATION, SHADE_LIMITS
from . import gpu
from .shaders import BUILDING_FRAGMENT, BUILDING_VERTEX

UPLOADS = 1  # сеток за кадр
SHOT_UPLOADS = 8  # сеток за кадр снимка
FOOTPRINTS_KEPT = 96  # разобранных тайлов в памяти, по давности
LOADER_PERIOD = 0.1  # секунд между просьбами к загрузчику
UNIFORMS = ("u_mvp", "u_light", "u_ambient", "u_flat", "u_limits",
            "u_day", "u_night")


class _Built(QObject):
    """Живёт в главном потоке, сигнал из рабочего идёт очередью."""

    done = pyqtSignal(object, object, int, int)


class _MeshTask(QRunnable):
    """Сетка тайла по снимку высот в рабочем потоке."""

    def __init__(self, footprint, store, level, relief, sink):
        super().__init__()
        self.footprint = footprint
        self.store = store
        self.level = level
        self.relief = relief
        self.sink = sink

    def run(self):
        with np.errstate(all="ignore"):
            heights = self.store.heights_at if self.store.scale else None
            mesh = core.mesh(self.footprint, heights)
        self.sink.done.emit(self.footprint.key, mesh, self.level,
                            self.relief)


class _Buffers:
    """Сетка тайла в видеокарте."""

    def __init__(self, mesh, level):
        vertices = np.ascontiguousarray(mesh.vertices)
        indices = np.ascontiguousarray(mesh.indices, dtype=np.uint32)
        self.center = mesh.center
        self.level = level
        self.vertices = len(vertices)
        self.count = len(indices)
        gl = gpu.gl
        self.vao = gl.gen_names("glGenVertexArrays", 1)[0]
        self.vbo, self.ebo = gl.gen_names("glGenBuffers", 2)
        gl.glBindVertexArray(self.vao)
        gl.glBindBuffer(GL.GL_ARRAY_BUFFER, self.vbo)
        gl.buffer_data(GL.GL_ARRAY_BUFFER, vertices)
        gl.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, self.ebo)
        gl.buffer_data(GL.GL_ELEMENT_ARRAY_BUFFER, indices)
        stride = core.VERTEX.itemsize
        for index, size, kind, normalized, field in (
                (0, 3, GL.GL_FLOAT, GL.GL_FALSE, "position"),
                (1, 4, GL.GL_BYTE, GL.GL_TRUE, "normal"),
                (2, 4, GL.GL_UNSIGNED_BYTE, GL.GL_TRUE, "color")):
            gl.glEnableVertexAttribArray(index)
            gl.glVertexAttribPointer(
                index, size, kind, normalized, stride,
                ctypes.c_void_p(core.VERTEX.fields[field][1]))
        gl.glBindVertexArray(0)

    def delete(self):
        gpu.gl.delete_names("glDeleteVertexArrays", [self.vao])
        gpu.gl.delete_names("glDeleteBuffers", [self.vbo, self.ebo])


def light_at(lat, lon):
    """Направление света в ECEF у точки, как у отмывки рельефа:
    с северо-запада под LIGHT_ELEVATION."""
    la, lo = math.radians(lat), math.radians(lon)
    up = surface_normal(lat, lon)
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo),
                      -math.sin(la) * math.sin(lo), math.cos(la)])
    flat = math.sin(LIGHT_ELEVATION)
    across = math.cos(LIGHT_ELEVATION) / math.sqrt(2.0)
    return up * flat + (north - east) * across


class Buildings:
    """Здания вокруг глаза: разобранные тайлы, сборка, видеокарта."""

    def __init__(self):
        self.shown = False
        self.loader = None  # загрузчик тайлов OpenFreeMap, ставит окно
        self.footprints = OrderedDict()  # ключ -> Footprint или EMPTY
        self.building = {}  # ключ -> уровень высот собираемой сетки
        self.results = {}  # ключ -> (Mesh, уровень), ждут видеокарты
        self.buffers = {}  # ключ -> _Buffers
        self.wanted = []  # ключи тайлов кадра, ближние первыми
        self.relief = 0
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.sink = _Built()
        self.sink.done.connect(self._built)
        self.program = None
        self.locations = {}
        self._near_key = None
        self._asked = frozenset()
        self._asked_at = 0.0
        self.drawn = 0
        self.vertices = 0
        self.rejected = 0  # сеток, не прошедших core.mesh_ok

    # Данные.

    def set_shown(self, on, loader=None):
        """Показать здания с загрузчиком loader или скрыть их."""
        self.shown = bool(on)
        self.loader = loader
        if not on:
            self.drawn = 0
            self.wanted = []
            self._near_key = None
            self._asked = frozenset()

    def add(self, key, footprint):
        """Пришёл разобранный тайл: Footprint или EMPTY."""
        self.footprints[key] = footprint
        self.footprints.move_to_end(key)
        while len(self.footprints) > FOOTPRINTS_KEPT:
            old, _ = self.footprints.popitem(last=False)
            self.results.pop(old, None)

    def set_relief(self, relief):
        """Сменился масштаб рельефа: все сетки собираются заново."""
        self.relief = relief
        self.pool.clear()
        self.building.clear()
        self.results.clear()
        for item in self.buffers.values():
            item.level = -2

    def _built(self, key, mesh, level, relief):
        if relief != self.relief:
            return
        if self.building.get(key) == level:
            del self.building[key]
        self.results[key] = (mesh, level)

    def missing(self):
        """Сколько тайлов кадр ещё ждёт: данных, сборки, видеокарты."""
        if not self.shown:
            return 0
        count = 0
        for key in self.wanted:
            if key not in self.footprints:
                count += 1
            elif key in self.building or key in self.results:
                count += 1
            elif self.footprints[key] != core.EMPTY \
                    and key not in self.buffers:
                count += 1
        return count

    # Кадр.

    def update(self, camera, store, now):
        """Выбор тайлов вокруг глаза, просьбы к загрузчику и сборка.

        Возвращает True, если что-то ещё собирается или ждёт видеокарты.
        """
        if not self.shown:
            return False
        eye = np.asarray(camera.eye, dtype=np.float64)
        forward = camera.forward
        near_key = (tuple(np.round(eye, 0)), tuple(np.round(forward, 2)),
                    store.version)
        if near_key != self._near_key:
            self._near_key = near_key
            ground = float(store.height_at(*_latlon(eye)))
            self.wanted = self._budget(
                core.near_tiles(eye, forward, ground))
        self._ask(now)
        for key in self.wanted:
            footprint = self.footprints.get(key)
            if footprint is None or footprint == core.EMPTY:
                continue
            self.footprints.move_to_end(key)
            if key in self.building:
                # Одна сборка на тайл. Высоты приходят уровень за
                # уровнем, и тайл вставал в очередь на каждый уровень.
                continue
            _, target = store.for_mesh(key)
            have = self.buffers.get(key)
            done = self.results.get(key)
            level = max(have.level if have else -3,
                        done[1] if done else -3)
            if target > level:
                self.building[key] = target
                self.pool.start(_MeshTask(footprint, store.snapshot(),
                                          target, self.relief, self.sink))
        return bool(self.building or self.results)

    def _budget(self, near):
        """Ближние тайлы в пределах бюджета вершин."""
        out = []
        total = 0
        for key, _ in near:
            footprint = self.footprints.get(key)
            if footprint is not None and footprint != core.EMPTY:
                total += core.vertex_count(footprint)
                if total > core.MAX_VERTICES and out:
                    break
            out.append(key)
        return out

    def _ask(self, now):
        if self.loader is None or now - self._asked_at < LOADER_PERIOD:
            return
        wanted = {key: -float(i) for i, key in enumerate(self.wanted)
                  if key not in self.footprints}
        keys = frozenset(wanted)
        if keys != self._asked or now - self._asked_at > 1.0:
            self.loader.want_many(wanted.items())
            self.loader.retain(wanted)
            self._asked = keys
            self._asked_at = now

    def upload(self, count=UPLOADS):
        """Готовые сетки в видеокарту, ближние первыми. Только при
        текущем контексте."""
        order = [k for k in self.wanted if k in self.results]
        for key in order[:count]:
            mesh, level = self.results.pop(key)
            old = self.buffers.pop(key, None)
            if old is not None:
                old.delete()
            if not core.mesh_ok(mesh):
                self.rejected += 1
            elif len(mesh.indices):
                self.buffers[key] = _Buffers(mesh, level)
        # Сетки тайлов вне кадра освобождаются.
        keep = set(self.wanted)
        for key in [k for k in self.buffers if k not in keep]:
            self.buffers.pop(key).delete()
        for key in [k for k in self.results if k not in keep]:
            del self.results[key]
        self.vertices = sum(b.vertices for b in self.buffers.values())

    # Ресурсы OpenGL.

    def init_gl(self):
        self.program = gpu.build_program(BUILDING_VERTEX, BUILDING_FRAGMENT)
        self.locations = {name: GL.glGetUniformLocation(self.program, name)
                          for name in UNIFORMS}

    def release_gl(self):
        self.pool.clear()
        self.pool.waitForDone(2000)
        for item in self.buffers.values():
            item.delete()
        self.buffers = {}
        self.results = {}
        self.building = {}
        if self.program is not None:
            GL.glDeleteProgram(self.program)
        self.program = None

    def draw(self, camera, sun=None):
        """Нарисовать здания. Вызывается после тайлов, до неба.

        sun - направление на солнце в ECEF или None - постоянный свет.
        Доля дня берётся у глаза, здания видны не дальше RANGE от него.
        """
        self.drawn = 0
        if not self.shown or self.program is None:
            return
        items = [self.buffers[k] for k in self.wanted if k in self.buffers]
        if not items:
            return
        mvps = np.ascontiguousarray(
            camera.tiles_mvp([item.center for item in items]),
            dtype=np.float32)
        loc = self.locations
        gl = gpu.gl
        gl.glUseProgram(self.program)
        lat, lon = _latlon(np.asarray(camera.eye, dtype=np.float64))
        if sun is None:
            gl.glUniform3f(loc["u_light"], *light_at(lat, lon).tolist())
            day = 1.0
        else:
            gl.glUniform3f(loc["u_light"], *(float(v) for v in sun))
            day = float(core_sun.daylight(surface_normal(lat, lon) @ sun))
        gl.glUniform1f(loc["u_day"], day)
        gl.glUniform1f(loc["u_night"], core_sun.NIGHT)
        gl.glUniform1f(loc["u_ambient"], AMBIENT)
        gl.glUniform1f(loc["u_flat"], AMBIENT + (1.0 - AMBIENT)
                       * math.sin(LIGHT_ELEVATION))
        gl.glUniform2f(loc["u_limits"], *SHADE_LIMITS)
        base = mvps.ctypes.data
        stride = mvps.strides[0]
        null = ctypes.c_void_p(0)
        for i, item in enumerate(items):
            gpu._uniform_matrix(loc["u_mvp"], 1, GL.GL_TRUE,
                                ctypes.c_void_p(base + stride * i))
            gpu._bind_vao(item.vao)
            gpu._draw_elements(GL.GL_TRIANGLES, item.count,
                               GL.GL_UNSIGNED_INT, null)
        gpu._bind_vao(0)
        self.drawn = len(items)


def _latlon(eye):
    lat, lon, _ = ecef_to_geodetic(eye)
    return float(lat), float(lon)
