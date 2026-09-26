# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Виджет OpenGL с глобусом.

Уровни 0-2 грузятся до первого кадра, пока они не готовы, рисуется
только фон. Дальше каждый кадр выбирает тайлы по экранной ошибке
(core/lod.py), просит у загрузчика недостающие и снимает ненужные.
Навигация появляется в шаге 0.8.
"""
import math
import time
from collections import Counter, deque

import numpy as np
from OpenGL import GL
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QSurfaceFormat

from ..core import lod
from ..core.camera import Camera
from ..core.navigation import Navigator, Pose, altitude
from ..core.tiling import polar_cap_mesh, tile_mesh
from ..qt_compat import QOpenGLWidget, enum
from . import gpu
from .shaders import HOLE_FRAGMENT, HOLE_VERTEX, TILE_FRAGMENT, TILE_VERTEX

START_LEVELS = (0, 1, 2)
START_VIEW = (58.0105, 56.2294, 2.0e7)  # над Пермью, 20 000 км

SPACE = (0.0, 0.0, 0.0)
HOLE = (1.0, 0.0, 1.0)  # пурпурный фон проверочного режима
OCEAN = (0xAA, 0xD3, 0xDF, 0xFF)  # цвет воды на подложке OSM
UNDERLAY_COLOR = (0x00, 0xFF, 0x00, 0xFF)  # подстилка в проверочном режиме
UNDERLAY_LEVEL = 2
# Подстилка лежит на 1 км ниже поверхности. Это больше шага буфера
# глубины у дальней плоскости: около 200 м при камере на высоте 50 м.
UNDERLAY_SCALE = 1.0 - 1000.0 / 6378137.0
# Счётчик дыр не смотрит на полосу у края диска. Хорды тайлов уровня 2
# проседают до 7.7 км, эллипсоид счётчика сжат на 10 км.
HOLE_MARGIN = 10000.0
FRAMES_KEPT = 300
UPLOADS_PER_FRAME = 3
UPLOAD_TIME = 0.002  # секунд на загрузку текстур в кадре
POOL_START = 64  # текстур в запасе при создании контекста, около 0.2 с
POOL_TARGET = 128  # до стольких запас пополняется в кадрах без движения
POOL_REFILL = 2  # текстур за такой кадр
LOADER_PERIOD = 0.1  # секунд между вызовами загрузчика при смене набора
MAX_TEXTURES = 1500  # 256×256 RGBA с мипмапами - около 350 МБ
MAX_PENDING = 400
DEGREES_PER_PIXEL = 0.25  # поворот и наклон мышью
# Участки кадра для замера, по порядку в paintGL.
SECTIONS = ("upload", "select", "loader", "draw", "evict")
WHEEL_STEP = 0.8  # один щелчок колеса приближает на 20 %

LEFT = enum(Qt, "MouseButton", "LeftButton")
MIDDLE = enum(Qt, "MouseButton", "MiddleButton")
SHIFT = enum(Qt, "KeyboardModifier", "ShiftModifier")


def surface_format():
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(enum(QSurfaceFormat, "OpenGLContextProfile",
                        "CoreProfile"))
    fmt.setDepthBufferSize(24)
    fmt.setSwapInterval(1)
    return fmt


def start_keys():
    return [(z, x, y) for z in START_LEVELS
            for x in range(1 << z) for y in range(1 << z)]


START_KEYS = frozenset(start_keys())


class GlobeView(QOpenGLWidget):
    """Глобус. Ресурсы OpenGL живут и умирают вместе с контекстом."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFormat(surface_format())
        lat, lon, distance = START_VIEW
        self.camera = Camera.look_at(lat, lon, distance)
        self.navigator = Navigator(self.camera, Pose(lat, lon, distance))
        self.turning = None
        self.setMouseTracking(False)
        self.setCursor(enum(Qt, "CursorShape", "OpenHandCursor"))
        self.loader = None
        self.pending = {}
        self.meshes = {}
        self.textures = {}
        self.last_used = {}
        self.caps = []
        self.program = None
        self.ocean = None
        self.anisotropy = 1.0
        self.gl_info = {}
        self.error = ""
        self.show_holes = False
        self.frame = 0
        self.drawn = 0
        self.drawn_levels = Counter()
        self.selection = None
        self.frame_times = deque(maxlen=FRAMES_KEPT)
        self.sections = deque(maxlen=FRAMES_KEPT)
        self.gl_errors = Counter()
        self.draw_calls = 0
        self._wanted = frozenset()
        self._wanted_at = 0.0
        self._last_pose = None
        # Счётчик пикселей Земли без тайлов, включают проверочные скрипты.
        self.hole_check = False
        self.hole_counts = []
        self._context = None

    # Данные

    def add_image(self, key, rgba, mesh=None):
        """Картинка тайла и, если есть, готовая сетка его вершин."""
        self.pending[key] = (rgba, mesh)
        self.update()

    def has(self, key):
        return key in self.textures or key in self.pending

    def ready(self):
        return all(self.has(key) for key in START_KEYS)

    def altitude(self):
        return altitude(self.camera.eye)

    # Мышь

    def _pixel(self, event):
        """Точка события в пикселях кадра, с учётом масштаба экрана."""
        pos = event.position() if hasattr(event, "position") else event.pos()
        ratio = self.devicePixelRatioF()
        return pos.x() * ratio, pos.y() * ratio

    def _fit_camera(self):
        ratio = self.devicePixelRatioF()
        self.camera.width = max(1, int(round(self.width() * ratio)))
        self.camera.height = max(1, int(round(self.height() * ratio)))

    def mousePressEvent(self, event):
        self._fit_camera()
        px, py = self._pixel(event)
        button = event.button()
        shift = bool(event.modifiers() & SHIFT)
        if button == MIDDLE or (button == LEFT and shift):
            # Поворот не обрывает начатое приближение колесом.
            self.navigator.stop_inertia()
            self.turning = (px, py)
        elif button == LEFT:
            if self.navigator.press(px, py, time.monotonic()):
                self.setCursor(enum(Qt, "CursorShape", "ClosedHandCursor"))
        self.update()

    def mouseMoveEvent(self, event):
        px, py = self._pixel(event)
        if self.turning is not None:
            x0, y0 = self.turning
            self.turning = (px, py)
            # Угол на пиксель меряется в логических пикселях, иначе
            # на экране с масштабом 200 % поворот идёт вдвое быстрее.
            step = DEGREES_PER_PIXEL / self.devicePixelRatioF()
            self.navigator.turn((px - x0) * step, (y0 - py) * step)
            self.update()
        elif self.navigator.drag(px, py, time.monotonic()):
            self.update()

    def mouseReleaseEvent(self, event):
        self.turning = None
        self.navigator.release(time.monotonic())
        self.setCursor(enum(Qt, "CursorShape", "OpenHandCursor"))
        self.update()

    def wheelEvent(self, event):
        self._fit_camera()
        notches = event.angleDelta().y() / 120.0
        if notches:
            px, py = self._pixel(event)
            self.navigator.wheel(px, py, WHEEL_STEP ** notches,
                                 time.monotonic())
            self.update()

    # OpenGL

    def initializeGL(self):
        ctx = self.context()
        fmt = ctx.format()
        self.gl_info = {
            "version": (fmt.majorVersion(), fmt.minorVersion()),
            "profile": fmt.profile(),
            "renderer": GL.glGetString(GL.GL_RENDERER).decode(),
            "gl": GL.glGetString(GL.GL_VERSION).decode(),
        }
        if self.gl_info["version"] < (3, 3):
            self.error = self.gl_info["gl"]
            return
        self.program = gpu.build_program(TILE_VERTEX, TILE_FRAGMENT)
        self.u_mvp = GL.glGetUniformLocation(self.program, "u_mvp")
        self.u_texture = GL.glGetUniformLocation(self.program, "u_texture")
        self.anisotropy = min(gpu.max_anisotropy(), 8.0)
        self.pool = gpu.TexturePool(self.anisotropy)
        self.pool.allocate(POOL_START)
        self.ocean = gpu.create_texture(
            np.array(OCEAN, dtype=np.uint8).reshape(1, 1, 4))
        self.underlay_marker = gpu.create_texture(
            np.array(UNDERLAY_COLOR, dtype=np.uint8).reshape(1, 1, 4))
        self.caps = [gpu.GpuMesh(polar_cap_mesh(north))
                     for north in (True, False)]
        self.hole_program = gpu.build_program(HOLE_VERTEX, HOLE_FRAGMENT)
        self.hole_uniforms = {
            name: GL.glGetUniformLocation(self.hole_program, name)
            for name in ("u_rotation", "u_tan", "u_viewport", "u_eye",
                         "u_axes", "u_qc")}
        # Профиль Core требует привязанный массив вершин и там, где
        # вершины берутся из gl_VertexID.
        self.empty_vao = GL.glGenVertexArrays(1)
        # glGenQueries(1) в PyOpenGL отдаёт массив, а не число.
        self.hole_query = int(np.ravel(GL.glGenQueries(1))[0])
        self._context = ctx
        ctx.aboutToBeDestroyed.connect(self.release_gl)

    def release_gl(self):
        """Освобождение ресурсов перед уничтожением контекста."""
        if self._context is None:
            return
        self.makeCurrent()
        for mesh in list(self.meshes.values()) + self.caps:
            mesh.delete()
        for texture in self.textures.values():
            gpu.delete_texture(texture)
        self.pool.delete_all()
        if self.ocean is not None:
            gpu.delete_texture(self.ocean)
            gpu.delete_texture(self.underlay_marker)
        if self.program is not None:
            GL.glDeleteProgram(self.program)
            GL.glDeleteProgram(self.hole_program)
            GL.glDeleteVertexArrays(1, [self.empty_vao])
            GL.glDeleteQueries(1, [self.hole_query])
        self.meshes, self.textures, self.caps = {}, {}, []
        self.program = self.ocean = None
        self._context = None
        self.doneCurrent()

    def _upload(self, budget):
        """Загрузить в видеокарту не больше budget ожидающих картинок.

        Первыми идут уровни 0-2, за ними тайлы, нужные прошлому кадру.
        """
        keep = self.selection.keep if self.selection else set()
        order = sorted(self.pending,
                       key=lambda k: (k not in START_KEYS, k not in keep,
                                      k[0]))
        started = time.perf_counter()
        for count, key in enumerate(order[:budget]):
            # Хотя бы одна текстура за кадр, дальше - пока не вышло время.
            # Стартовые уровни 0-2 грузятся все сразу.
            if count and key not in START_KEYS \
                    and time.perf_counter() - started > UPLOAD_TIME:
                break
            image, mesh = self.pending.pop(key)
            self.textures[key] = self.pool.acquire(image)
            self.meshes[key] = gpu.GpuMesh(mesh or tile_mesh(*key))
            self.last_used[key] = self.frame

    def _evict(self, keep):
        """Вытеснить давно не нужные тайлы, уровни 0-2 не трогаются."""
        if len(self.textures) > MAX_TEXTURES:
            spare = sorted((self.last_used.get(k, 0), k)
                           for k in self.textures
                           if k not in keep and k not in START_KEYS)
            extra = len(self.textures) - int(MAX_TEXTURES * 0.9)
            for _, key in spare[:extra]:
                self.pool.release(self.textures.pop(key))
                self.meshes.pop(key).delete()
                self.last_used.pop(key, None)
        if len(self.pending) > MAX_PENDING:
            for key in [k for k in self.pending if k not in keep]:
                self.pending.pop(key)

    def paintGL(self):
        started = time.perf_counter()
        self.frame += 1
        self._fit_camera()
        # Время шага навигатора видно снаружи, по нему проверочные
        # скрипты считают скорость перелёта.
        self.step_time = time.monotonic()
        moving = self.navigator.step(self.step_time)
        GL.glClearColor(*(HOLE if self.show_holes else SPACE), 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        self.drawn = 0
        if self.program is None or not self.ready():
            return
        # До первого полного кадра уровни 0-2 грузятся в видеокарту все
        # сразу, на них держится подстилка. Дальше - не больше
        # UPLOADS_PER_FRAME за кадр.
        missing = any(key not in self.textures for key in START_KEYS)
        budget = len(self.pending) if missing else UPLOADS_PER_FRAME
        marks = [time.perf_counter()]
        self._upload(max(budget, UPLOADS_PER_FRAME))
        marks.append(time.perf_counter())

        sel = lod.select(self.camera, self.textures.__contains__)
        self.selection = sel
        marks.append(time.perf_counter())
        for key in sel.keep:
            if key in self.textures:
                self.last_used[key] = self.frame
        wanted = frozenset(sel.want)
        now = time.monotonic()
        stale = wanted and now - self._wanted_at > 1.0
        changed = wanted != self._wanted \
            and now - self._wanted_at > LOADER_PERIOD
        if self.loader is not None and (changed or stale):
            # Загрузчик зовётся при смене набора, но не чаще LOADER_PERIOD.
            # Во время перелёта набор меняется каждый кадр, а вызов
            # с запросами и снятиями стоил до 6 мс. Раз в секунду набор
            # повторяется, чтобы тайл после паузы на ошибку снова попал
            # в очередь.
            self.loader.want_many(sel.want.items())
            self.loader.retain(sel.want)
            self._wanted = wanted
            self._wanted_at = now
        marks.append(time.perf_counter())

        GL.glEnable(GL.GL_DEPTH_TEST)
        # Юбку тайла камера часто видит с изнанки, когда смотрит через
        # стык с соседом другого уровня. Отсечение обратных граней
        # убрало бы её.
        GL.glDisable(GL.GL_CULL_FACE)
        GL.glUseProgram(self.program)
        GL.glActiveTexture(GL.GL_TEXTURE0)
        GL.glUniform1i(self.u_texture, 0)

        items = [(cap, self.ocean) for cap in self.caps]
        items += [(self.meshes[key], self.textures[key]) for key in sel.draw]
        surface = len(items)
        scales = [1.0] * surface
        under = self._underlay_items(sel.keep)
        items += under
        scales += [UNDERLAY_SCALE] * len(under)
        mvps = self.camera.tiles_mvp([mesh.center for mesh, _ in items],
                                     scales=scales)
        gpu.draw_batch(items[:surface], mvps[:surface], self.u_mvp)
        if self.hole_check:
            # До подстилки: щели между тайлами. После: видимые дыры.
            gaps = self._count_holes()
            GL.glUseProgram(self.program)
        gpu.draw_batch(items[surface:], mvps[surface:], self.u_mvp)
        if self.hole_check:
            holes = self._count_holes()
            GL.glUseProgram(self.program)
            self.hole_counts.append((self.frame, gaps, holes))
        self.drawn = len(sel.draw)
        self.drawn_levels = Counter(k[0] for k in sel.draw)
        self.draw_calls = len(items)

        GL.glBindVertexArray(0)
        GL.glBindTexture(GL.GL_TEXTURE_2D, 0)
        GL.glUseProgram(0)
        for code in gpu.frame_errors():
            self.gl_errors[code] += 1
        marks.append(time.perf_counter())
        self._evict(sel.keep)
        # Неподвижность проверяется по самой камере: её двигает не только
        # навигатор, но и проверочные скрипты.
        pose = (tuple(self.camera.eye), tuple(self.camera.rotation.ravel()))
        still = pose == self._last_pose
        self._last_pose = pose
        refill = still and not moving and len(self.pool.free) < POOL_TARGET
        if refill:
            # Кадр без движения пополняет запас текстур понемногу.
            self.pool.allocate(POOL_REFILL)
        if moving or refill or (self.pending
                                and any(k in sel.keep for k in self.pending)):
            self.update()
        marks.append(time.perf_counter())
        self.paint_span = (started, marks[-1])
        self.frame_times.append(marks[-1] - started)
        spans = [b - a for a, b in zip(marks, marks[1:])]
        self.sections.append(dict(zip(SECTIONS, spans),
                                  draws=self.draw_calls))
        self.changed.emit()

    def _count_holes(self):
        """Пиксели Земли, не закрытые ни одним тайлом, в этом кадре.

        Рисуется полноэкранный треугольник на глубине 1.0. Проверка
        глубины пропускает его только там, где тайлов нет. Шейдер
        отбрасывает пиксели, луч через которые проходит мимо эллипсоида,
        сжатого на HOLE_MARGIN. Проходящие фрагменты считает запрос
        GL_SAMPLES_PASSED. Результат читается сразу, это задерживает
        кадр, поэтому счётчик включается только в проверочных скриптах.
        В проверочном режиме show_holes такие пиксели пурпурные.
        """
        cam = self.camera
        a = 6378137.0 - HOLE_MARGIN
        b = 6356752.314245179 - HOLE_MARGIN
        axes = np.array([1.0 / a, 1.0 / a, 1.0 / b])
        eye = cam.eye * axes
        t = math.tan(math.radians(cam.fov_y) / 2.0)
        GL.glUseProgram(self.hole_program)
        u = self.hole_uniforms
        GL.glUniformMatrix3fv(u["u_rotation"], 1, GL.GL_TRUE,
                              cam.rotation.astype(np.float32))
        GL.glUniform2f(u["u_tan"], t * cam.aspect, t)
        GL.glUniform2f(u["u_viewport"], cam.width, cam.height)
        GL.glUniform3f(u["u_eye"], *eye)
        GL.glUniform3f(u["u_axes"], *axes)
        GL.glUniform1f(u["u_qc"], float(eye @ eye) - 1.0)
        GL.glDepthFunc(GL.GL_LEQUAL)
        GL.glDepthMask(GL.GL_FALSE)
        if not self.show_holes:
            GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE,
                           GL.GL_FALSE)
        GL.glBeginQuery(GL.GL_SAMPLES_PASSED, self.hole_query)
        GL.glBindVertexArray(self.empty_vao)
        GL.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        GL.glEndQuery(GL.GL_SAMPLES_PASSED)
        GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
        GL.glDepthMask(GL.GL_TRUE)
        GL.glDepthFunc(GL.GL_LESS)
        result = np.zeros(1, dtype=np.uint32)
        GL.glGetQueryObjectuiv(self.hole_query, GL.GL_QUERY_RESULT, result)
        return int(result[0])

    def _underlay_items(self, keep):
        """Подстилка: тайлы уровня 2 на 1 км ниже поверхности.

        Хорда края тайла вдоль параллели лежит в плоскости параллели
        и смещается не только вниз, но и к оси Земли. На стыке с соседом
        другого уровня остаётся полоса, которую отвесная юбка закрывает
        не от всех лучей. На экране полоса уже пикселя, в ней видна
        подстилка. Рисуется последней, поэтому почти целиком отбрасывается
        проверкой глубины. В проверочном режиме она зелёная.

        Берутся только тайлы уровня 2 из keep: выбор тайлов прошёл через
        них, значит они видны. Шапки рисуются всегда.
        """
        marker = self.underlay_marker if self.show_holes else None
        out = []
        for key in keep:
            if key[0] == UNDERLAY_LEVEL and key in self.textures:
                out.append((self.meshes[key], marker or self.textures[key]))
        out += [(cap, marker or self.ocean) for cap in self.caps]
        return out
