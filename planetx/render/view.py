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
from qgis.PyQt.QtCore import QObject, QRunnable, QThreadPool, Qt, pyqtSignal
from qgis.PyQt.QtGui import QSurfaceFormat

from ..core import lod
from ..core.overlay import (MAX_ANCESTOR_DEPTH, urgency,
                            window as overlay_window)
from ..core.camera import Camera
from ..core.ellipsoid import A, B
from ..core.navigation import Navigator, Pose, altitude, nearest_terrain
from ..core.places import PlaceStore, kinds_at
from ..core.terrain import FLAT_LEVEL, HeightStore
from ..core.tiling import (HOLE_MARGIN, UNDERLAY_DEPTH, polar_cap_mesh,
                           tile_mesh)
from ..qt_compat import QOpenGLWidget, enum
from . import gpu
from .labels import Labels
from .shaders import (HOLE_FRAGMENT, HOLE_VERTEX, SHELL, SKY_FRAGMENT,
                      TILE_FRAGMENT, TILE_VERTEX)

START_LEVELS = (0, 1, 2)
START_VIEW = (58.0105, 56.2294, 2.0e7)  # над Пермью, 20 000 км

SPACE = (0.0, 0.0, 0.0)
HOLE = (1.0, 0.0, 1.0)  # пурпурный фон проверочного режима
OCEAN = (0xAA, 0xD3, 0xDF, 0xFF)  # цвет воды на подложке OSM
UNDERLAY_COLOR = (0x00, 0xFF, 0x00, 0xFF)  # подстилка в проверочном режиме
UNDERLAY_LEVEL = 2
# Подстилка лежит на UNDERLAY_DEPTH ниже поверхности. Это больше шага
# буфера глубины у дальней плоскости. Худший случай - глаз на высоте
# 9 км в 50 м от склона: ближняя плоскость 25 м, дальняя 680 км,
# шаг 1.1 км.
UNDERLAY_SCALE = 1.0 - UNDERLAY_DEPTH / A
FRAMES_KEPT = 300
UPLOADS_PER_FRAME = 3
UPLOAD_TIME = 0.002  # секунд на загрузку текстур в кадре
POOL_START = 64  # текстур в запасе при создании контекста, около 0.2 с
POOL_TARGET = 128  # до стольких запас пополняется в кадрах без движения
POOL_REFILL = 2  # текстур за такой кадр
LOADER_PERIOD = 0.1  # секунд между вызовами загрузчика при смене набора
MAX_TEXTURES = 1500  # 256×256 RGBA с мипмапами - около 350 МБ
MAX_PENDING = 400
MAX_OVERLAYS = 600  # картинок наложения в видеокарте
MAX_EMPTY_OVERLAYS = 20000  # ключей пустых картинок наложения
EVICT_PERIOD = 30  # кадров между попытками вытеснить картинки наложения
OVERLAY_UPLOADS = 2  # картинок наложения за кадр
DEGREES_PER_PIXEL = 0.25  # поворот и наклон мышью
# Участки кадра для замера, по порядку в paintGL.
SECTIONS = ("upload", "terrain", "select", "heights", "loader", "draw",
            "evict")
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


AIR_UNIFORMS = ("u_rotation", "u_tan", "u_viewport", "u_eye", "u_axes",
                "u_qc_shell", "u_air")
def uniforms(program, names):
    return {name: GL.glGetUniformLocation(program, name) for name in names}


def ray_uniforms(u, camera, a=A, b=B):
    """Общие для полноэкранных проходов величины луча из глаза.

    Координаты в долях полуосей эллипсоида с полуосями a и b. Возвращает
    глаз в этих координатах, float64.
    """
    axes = np.array([1.0 / a, 1.0 / a, 1.0 / b])
    eye = camera.eye * axes
    t = math.tan(math.radians(camera.fov_y) / 2.0)
    gpu.gl.matrix3(u["u_rotation"], GL.GL_TRUE, camera.rotation)
    gpu.gl.glUniform2f(u["u_tan"], t * camera.aspect, t)
    gpu.gl.glUniform2f(u["u_viewport"], camera.width, camera.height)
    gpu.gl.glUniform3f(u["u_eye"], *eye)
    gpu.gl.glUniform3f(u["u_axes"], *axes)
    return eye


def air_uniforms(u, camera, on):
    eye = ray_uniforms(u, camera)
    gpu.gl.glUniform1f(u["u_qc_shell"], float(eye @ eye) - SHELL * SHELL)
    gpu.gl.glUniform1f(u["u_air"], 1.0 if on else 0.0)
    return eye


def start_keys():
    return [(z, x, y) for z in START_LEVELS
            for x in range(1 << z) for y in range(1 << z)]


START_KEYS = frozenset(start_keys())
REBUILD_TIME = 0.002  # секунд на подмену пересобранных сеток в кадре
# Приоритет замены тайла старой подложки, который виден в кадре. Выше
# экранной ошибки любого нового тайла, мелкие уровни раньше.
STALE_PRIORITY = 1.0e6


class _Built(QObject):
    """Живёт в главном потоке. Сигнал из рабочего потока идёт очередью."""

    done = pyqtSignal(object, object, int, int)


class _BuildTask(QRunnable):
    """Сборка сетки тайла с уточнёнными высотами в рабочем потоке.

    Задача считает только NumPy, не трогает Qt и OpenGL и ничего
    не ждёт от главного потока. Предупреждения NumPy гасятся. relief -
    номер настройки рельефа, сетка старой настройки не подменяется.
    """

    def __init__(self, key, height_tile, level, scale, relief, sink):
        super().__init__()
        self.key = key
        self.height_tile = height_tile
        self.level = level
        self.scale = scale
        self.relief = relief
        self.sink = sink

    def run(self):
        with np.errstate(all="ignore"):
            mesh = tile_mesh(*self.key, self.height_tile,
                             exaggeration=self.scale)
        self.sink.done.emit(self.key, mesh, self.level, self.relief)


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
        # Рельеф: хранилище высот, загрузчик Terrarium, уровень высот,
        # с которым собрана сетка каждого тайла, и пересборка сеток.
        self.store = HeightStore()
        self.terrain_loader = None
        self.mesh_levels = {}
        self.build_pool = QThreadPool(self)
        self.build_pool.setMaxThreadCount(1)
        self.build_sink = _Built(self)
        self.build_sink.done.connect(self._built)
        self.building = {}
        self.built = {}
        # Номер настройки рельефа. Растёт с каждой сменой масштаба.
        self.relief = 0
        self._terrain_wanted = frozenset()
        self._terrain_at = 0.0
        self._nearest_probe = None
        # Ошибки и видимость узлов между кадрами неподвижной камеры.
        self.memo = lod.Memo()
        self.navigator.set_terrain(self.store.height_at)
        self.pending = {}
        # Подложка: наибольший уровень источника и тайлы прежней подложки,
        # которые ещё не заменены.
        self.max_level = lod.MAX_LEVEL
        self.stale = set()
        # Наложение: отрисовщик слоёв QGIS, картинки в видеокарте,
        # ожидающие загрузки картинки и кадр последнего использования.
        self.overlay = None
        self.overlays = {}
        self.overlay_pending = {}
        self.overlay_used = {}
        # Тайлы с пустой картинкой наложения: готовы, рисуются прозрачной
        # текстурой, в видеокарту не грузятся.
        self.overlay_empty = set()
        # Картинки прежнего отрисовщика после обновления слоёв. Они
        # рисуются, пока их не заменят новые, как тайлы прежней подложки.
        self.overlay_stale = set()
        self._overlay_wanted = frozenset()
        self._overlay_at = 0.0
        self._drop_overlays = False
        self._prune_overlays = False
        self._overlay_evicted = 0
        self.clear_texture = None
        self.meshes = {}
        self.textures = {}
        self.last_used = {}
        self.caps = []
        self.program = None
        self.ocean = None
        # Шапки выше 85.05° красятся цветом края тайла 0/0/0 подложки,
        # до его прихода - цветом воды OSM. Северная первая.
        self.cap_textures = []
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
        # Небо, гало и дымка. Выключается для сравнения в замерах.
        self.atmosphere = True
        self.hole_counts = []
        # Надписи пунктов: тайлы пунктов, их загрузчик и отрисовка.
        # Загрузчик ставит окно, когда известен адрес тайлов.
        self.places = PlaceStore()
        self.place_loader = None
        # Классы надписей для включённых групп векторной основы.
        self.label_kinds = set()
        self._places_wanted = frozenset()
        self._places_at = 0.0
        self.labels = Labels()
        # Временная метка найденного места, Place класса «search» или None.
        # Список пунктов с меткой помнится вместе со списком без неё:
        # таблица надписей узнаёт прежний список по тождеству.
        self.search_mark = None
        self._marked = (None, None, [])
        self._context = None

    # Данные

    def add_image(self, key, rgba, mesh=None, level=-1):
        """Картинка тайла и, если есть, готовая сетка его вершин.

        level - уровень тайла высот, с которым собрана сетка, -1 без
        высот.
        """
        self.pending[key] = (rgba, mesh, level)
        self.update()

    def set_search_mark(self, mark):
        """Поставить временную метку найденного места или снять, None."""
        self.search_mark = mark
        self.update()

    def reset_places(self, max_level):
        """Пункты заново, например на другом языке подписей."""
        self.places = PlaceStore(max_level)
        self._places_wanted = frozenset()
        self._places_at = 0.0
        self.update()

    def add_places(self, key, places):
        """Пришли пункты тайла векторной основы."""
        self.places.add(key, places)
        self.update()

    def add_heights(self, tile):
        """Пришёл тайл высот. Тайлы, которым он точнее, пересобираются."""
        self.store.add(tile)
        for key, level in list(self.mesh_levels.items()):
            self._maybe_rebuild(key, level)
        self.update()

    def change_source(self, max_level):
        """Новая подложка.

        Тайлы прежней подложки, нужные кадру, и уровни 0-2 остаются
        на экране, пока их не заменят новые. Остальные освобождаются
        в кадре, где контекст OpenGL текущий, см. _drop_stale.
        """
        self.max_level = max_level
        self.pending.clear()
        self.stale = set(self.textures)
        self._wanted = frozenset()
        self._wanted_at = 0.0
        self.update()

    def _forget(self, key):
        """Освободить текстуру и сетку тайла. Только при текущем контексте."""
        self.pool.release(self.textures.pop(key))
        self.meshes.pop(key).delete()
        self.last_used.pop(key, None)
        self.mesh_levels.pop(key, None)
        self.built.pop(key, None)
        self.stale.discard(key)

    def _drop_stale(self, keep):
        """Освободить тайлы прежней подложки, которые кадру не нужны.

        Каждый кадр, пока они есть. Тайл, ушедший из кадра до замены,
        иначе висел бы в памяти, и его никто не просил бы заменить.
        """
        for key in [k for k in self.stale
                    if k not in keep and k not in START_KEYS]:
            self._forget(key)

    def set_overlay(self, overlay, keep=False):
        """Новый отрисовщик наложения или None.

        keep=False - прежние картинки освобождаются в следующем кадре,
        где контекст OpenGL текущий. keep=True - прежние картинки
        рисуются, пока их не заменят новые. Так обновление слоёв после
        правки не даёт мигания. Отрисовщик снимает окно, вид его только
        зовёт.
        """
        self.overlay = overlay
        self.overlay_pending.clear()
        self._overlay_wanted = frozenset()
        self._overlay_at = 0.0
        if keep and overlay is not None:
            # Прежние картинки остаются только у тайлов, которые сейчас
            # на экране. Остальные освобождаются в следующем кадре. Иначе
            # при отдалении новые тайлы брали прежние картинки, и снятый
            # слой мелькал до замены, нашлось 26 сентября 2026 года.
            drawn = set(self.selection.draw) if self.selection else set()
            self.overlay_empty &= drawn
            self.overlay_stale = (set(self.overlays) & drawn) \
                | self.overlay_empty
            self._prune_overlays = True
        else:
            self._drop_overlays = True
        self.update()

    def add_overlay(self, key, levels, extra=None):
        """Пришла картинка наложения тайла, уровни мипмапов.

        None - картинка пустая, линий на тайле нет.
        """
        self.overlay_stale.discard(key)
        if levels is None:
            self.overlay_empty.add(key)
            self.overlay_pending.pop(key, None)
            if len(self.overlay_empty) > MAX_EMPTY_OVERLAYS:
                self.overlay_empty.clear()
        else:
            self.overlay_empty.discard(key)
            self.overlay_pending[key] = levels
        self.update()

    def _overlay_ready(self, key):
        return key in self.overlays or key in self.overlay_empty

    def _forget_overlay(self, key):
        self.pool.release(self.overlays.pop(key))
        self.overlay_used.pop(key, None)
        self.overlay_stale.discard(key)

    def set_relief(self, scale):
        """Вертикальный масштаб рельефа, 0 - рельеф выключен.

        Сетки всех тайлов пересобираются в рабочем потоке, до подмены
        рисуются прежние. Сетки прежней настройки, которые ещё
        собираются, отбрасываются.
        """
        if scale == self.store.scale:
            return
        self.store.set_scale(scale)
        self.relief += 1
        self.build_pool.clear()
        self.building.clear()
        self.built.clear()
        self.pending = {key: (image, mesh, -1) for key, (image, mesh, _)
                        in self.pending.items()}
        for key in self.mesh_levels:
            self.mesh_levels[key] = -1
            self._maybe_rebuild(key, -1)
        self.update()

    def _maybe_rebuild(self, key, level):
        tile, target = self.store.for_mesh(key)
        if target <= level:
            return
        if self.building.get(key, -1) >= target:
            return
        self.building[key] = target
        self.build_pool.start(_BuildTask(key, tile, target, self.store.scale,
                                         self.relief, self.build_sink))

    def _built(self, key, mesh, level, relief):
        if relief != self.relief:
            return
        if self.building.get(key) == level:
            del self.building[key]
        if key in self.meshes and level > self.mesh_levels.get(key, -1):
            self.built[key] = (mesh, level)
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
        # Горячие вызовы кадра не отпускают GIL, см. gpu.hold_gil.
        self.hold_gil = gpu.hold_gil(ctx)
        self.program = gpu.build_program(TILE_VERTEX, TILE_FRAGMENT)
        self.u_mvp = GL.glGetUniformLocation(self.program, "u_mvp")
        self.u_texture = GL.glGetUniformLocation(self.program, "u_texture")
        self.tile_air = uniforms(self.program, AIR_UNIFORMS)
        self.sky_program = gpu.build_program(HOLE_VERTEX, SKY_FRAGMENT)
        self.sky_air = uniforms(self.sky_program, AIR_UNIFORMS + ("u_qc",))
        self.anisotropy = min(gpu.max_anisotropy(), 8.0)
        self.pool = gpu.TexturePool(self.anisotropy)
        self.pool.allocate(POOL_START)
        self.ocean = gpu.create_texture(
            np.array(OCEAN, dtype=np.uint8).reshape(1, 1, 4))
        self.underlay_marker = gpu.create_texture(
            np.array(UNDERLAY_COLOR, dtype=np.uint8).reshape(1, 1, 4))
        self.caps = [gpu.GpuMesh(polar_cap_mesh(north))
                     for north in (True, False)]
        # Подстилка - свои плоские тайлы уровня 2. Тайлы с рельефом
        # из грубых высот могли бы подняться над дном долины.
        self.underlay_meshes = {
            key: gpu.GpuMesh(tile_mesh(*key)) for key in START_KEYS
            if key[0] == UNDERLAY_LEVEL}
        self.u_overlay = GL.glGetUniformLocation(self.program, "u_overlay")
        self.u_overlay_uv = GL.glGetUniformLocation(self.program,
                                                    "u_overlay_uv")
        self.clear_texture = gpu.create_texture(
            np.zeros((1, 1, 4), dtype=np.uint8))
        self.hole_program = gpu.build_program(HOLE_VERTEX, HOLE_FRAGMENT)
        self.hole_uniforms = uniforms(self.hole_program, (
            "u_rotation", "u_tan", "u_viewport", "u_eye", "u_axes", "u_qc"))
        # Профиль Core требует привязанный массив вершин и там, где
        # вершины берутся из gl_VertexID.
        self.empty_vao = GL.glGenVertexArrays(1)
        # glGenQueries(1) в PyOpenGL отдаёт массив, а не число.
        self.hole_query = int(np.ravel(GL.glGenQueries(1))[0])
        self.labels.init_gl()
        self._context = ctx
        ctx.aboutToBeDestroyed.connect(self.release_gl)

    def release_gl(self):
        """Освобождение ресурсов перед уничтожением контекста."""
        if self._context is None:
            return
        self.makeCurrent()
        self.labels.release_gl()
        self.build_pool.clear()
        self.build_pool.waitForDone(2000)
        for mesh in (list(self.meshes.values()) + self.caps
                     + list(self.underlay_meshes.values())):
            mesh.delete()
        for texture in (list(self.textures.values())
                        + list(self.overlays.values())):
            gpu.delete_texture(texture)
        self.pool.delete_all()
        if self.clear_texture is not None:
            gpu.delete_texture(self.clear_texture)
            self.clear_texture = None
        self.overlays = {}
        if self.ocean is not None:
            gpu.delete_texture(self.ocean)
            for texture in self.cap_textures:
                gpu.delete_texture(texture)
            gpu.delete_texture(self.underlay_marker)
        if self.program is not None:
            GL.glDeleteProgram(self.program)
            GL.glDeleteProgram(self.hole_program)
            GL.glDeleteProgram(self.sky_program)
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
            image, mesh, level = self.pending.pop(key)
            if key in self.textures:
                # Тайл прежней подложки заменяется новым.
                self._forget(key)
            if mesh is None:
                mesh = tile_mesh(*key)
                level = FLAT_LEVEL if not self.store.scale else -1
            self.textures[key] = self.pool.acquire(image)
            if key == (0, 0, 0):
                self._paint_caps(image)
            self.meshes[key] = gpu.GpuMesh(mesh)
            self.mesh_levels[key] = level
            self.last_used[key] = self.frame
            # Пока сетка ждала очереди, могли прийти высоты точнее.
            self._maybe_rebuild(key, level)

    def _upload_overlays(self):
        """Картинки наложения в видеокарту, не больше OVERLAY_UPLOADS
        за кадр. Первыми идут тайлы, нужные прошлому кадру.
        """
        if self._drop_overlays:
            for key in list(self.overlays):
                self._forget_overlay(key)
            self.overlay_empty.clear()
            self.overlay_stale.clear()
            self._drop_overlays = False
            self._prune_overlays = False
        if self._prune_overlays:
            # Картинки в видеокарте в этот момент все прежние, новые
            # грузятся ниже.
            for key in [k for k in self.overlays
                        if k not in self.overlay_stale]:
                self._forget_overlay(key)
            self._prune_overlays = False
        if self.overlay is None:
            self.overlay_pending.clear()
            return
        keep = self.selection.keep if self.selection else set()
        order = sorted(self.overlay_pending,
                       key=lambda k: (k not in keep, k[0]))
        started = time.perf_counter()
        for count, key in enumerate(order[:OVERLAY_UPLOADS]):
            if count and time.perf_counter() - started > UPLOAD_TIME:
                break
            levels = self.overlay_pending.pop(key)
            if key in self.overlays:
                self._forget_overlay(key)
            self.overlays[key] = self.pool.acquire(levels)
            self.overlay_used[key] = self.frame

    def _overlay_items(self, sel, now):
        """Пары (текстура наложения, окно) для нарисованных тайлов.

        Заодно просит у отрисовщика картинки тайлов, у которых своей
        нет, и отмечает использованные картинки. Отрисовщик зовётся
        при смене набора, не чаще LOADER_PERIOD, как загрузчик тайлов.
        """
        wanted = {}
        items = []
        keep = sel.keep
        stale_set = self.overlay_stale
        for key in sel.draw:
            if stale_set:
                # Картинка прежнего наложения годится только своему
                # тайлу. Часть её у предка показала бы снятый слой
                # на тайле, которого при обновлении не было на экране.
                found = overlay_window(
                    key, lambda k, key=key: self._overlay_ready(k)
                    and (k == key or k not in stale_set))
            else:
                found = overlay_window(key, self._overlay_ready)
            if found is None or found[0] in self.overlay_empty:
                items.append((self.clear_texture, gpu.NO_OVERLAY))
            else:
                items.append((self.overlays[found[0]], found[1]))
                self.overlay_used[found[0]] = self.frame
            stale = found is not None and found[0] in self.overlay_stale
            if found is not None and found[0] == key and not stale:
                continue
            # Тайл, чьи дети нужны кадру, стоит временно и скоро сменится
            # детьми. Своя картинка ему нужна, только если нет даже части
            # картинки предка. В новом месте такие картинки были двумя
            # третями всех отрисовок наложения.
            z, x, y = key
            if found is not None and (z + 1, 2 * x, 2 * y) in keep:
                continue
            # Картинка прежнего отрисовщика заменяется раньше всех.
            wanted[key] = (MAX_ANCESTOR_DEPTH + 2.0 if stale
                           else urgency(key, found))
        if stale_set:
            # Прежняя картинка тайла, ушедшего с экрана, освобождается.
            # При возврате к нему она показала бы снятый слой. Контекст
            # OpenGL здесь текущий, это вызов из paintGL.
            gone = stale_set.difference(sel.draw)
            for key in gone:
                if key in self.overlays:
                    self._forget_overlay(key)
            self.overlay_empty -= gone
            stale_set -= gone
        keys = frozenset(wanted)
        stale = keys and now - self._overlay_at > 1.0
        changed = keys != self._overlay_wanted \
            and now - self._overlay_at > LOADER_PERIOD
        if changed or stale:
            self.overlay.want_many(wanted.items())
            self.overlay.retain(wanted)
            self._overlay_wanted = keys
            self._overlay_at = now
        return items

    def _evict_overlays(self, keep):
        # Сортировка всех картинок стоила до 2 мс. Когда вытеснить нечего,
        # потому что кадру нужны почти все, она повторялась каждый кадр.
        # Теперь - не чаще раза в EVICT_PERIOD кадров.
        if len(self.overlays) > MAX_OVERLAYS \
                and self.frame - self._overlay_evicted >= EVICT_PERIOD:
            self._overlay_evicted = self.frame
            spare = sorted((self.overlay_used.get(k, 0), k)
                           for k in self.overlays
                           if self.overlay_used.get(k, 0) < self.frame)
            extra = len(self.overlays) - int(MAX_OVERLAYS * 0.9)
            for _, key in spare[:extra]:
                self._forget_overlay(key)
        if len(self.overlay_pending) > MAX_PENDING:
            for key in [k for k in self.overlay_pending if k not in keep]:
                self.overlay_pending.pop(key)

    def _paint_caps(self, image):
        """Цвет полярных шапок по краю тайла 0/0/0.

        Берётся медиана двух крайних строк, верхних для севера и нижних
        для юга. Медиана не замечает редких островов и подписей.
        """
        rgba = image[0] if isinstance(image, list) else image
        for texture in self.cap_textures:
            gpu.delete_texture(texture)
        self.cap_textures = []
        for rows in (rgba[:2], rgba[-2:]):
            color = np.median(rows.reshape(-1, 4), axis=0)
            color[3] = 255
            self.cap_textures.append(gpu.create_texture(
                color.astype(np.uint8).reshape(1, 1, 4)))

    def _swap_built(self):
        """Подменить сетки, пересобранные с уточнёнными высотами."""
        started = time.perf_counter()
        for key in list(self.built):
            if time.perf_counter() - started > REBUILD_TIME:
                break
            mesh, level = self.built.pop(key)
            old = self.meshes.get(key)
            if old is None:
                continue
            self.meshes[key] = gpu.GpuMesh(mesh)
            self.mesh_levels[key] = level
            old.delete()

    def _with_stale(self, sel):
        """Нужные тайлы кадра и тайлы прежней подложки на замену.

        Тайл прежней подложки считается готовым, выбор его не просит.
        Видные в кадре и уровни 0-2 просятся с приоритетом выше новых.
        """
        if not self.stale:
            return sel.want
        want = dict(sel.want)
        for key in self.stale:
            if key in sel.keep or key in START_KEYS:
                want[key] = STALE_PRIORITY - key[0]
        return want

    def _want_heights(self, sel, now):
        """Попросить высоты для тайлов кадра, как подложку.

        Приоритет высот - экранная ошибка тайла, который их ждёт.
        Загрузчик зовётся при смене набора, не чаще LOADER_PERIOD.
        """
        if self.terrain_loader is None or not self.store.scale:
            return
        # Чаще LOADER_PERIOD загрузчик не зовётся, набор между вызовами
        # не нужен. Сбор набора стоил около 0.5 мс на кадр.
        if now - self._terrain_at <= LOADER_PERIOD:
            return
        wanted = {}
        # Высоты нужны и тайлам, которые подложка ждёт. Иначе у самой
        # земли рисуется грубый предок, ему хватает грубых высот,
        # и точные не просит никто.
        for key in list(sel.draw) + list(sel.want):
            height_key = self.store.wanted(key)
            if height_key not in self.store.tiles:
                wanted[height_key] = max(wanted.get(height_key, 0.0),
                                         sel.want.get(key, 1.0))
        keys = frozenset(wanted)
        stale = keys and now - self._terrain_at > 1.0
        changed = keys != self._terrain_wanted \
            and now - self._terrain_at > LOADER_PERIOD
        if changed or stale:
            # Уровень 0 нужен всегда, на нём держится оценка высот.
            if (0, 0, 0) not in self.store.tiles:
                wanted[(0, 0, 0)] = float("inf")
            self.terrain_loader.want_many(wanted.items())
            self.terrain_loader.retain(wanted)
            self._terrain_wanted = keys
            self._terrain_at = now

    def _evict(self, keep):
        """Вытеснить давно не нужные тайлы, уровни 0-2 не трогаются."""
        if len(self.textures) > MAX_TEXTURES:
            spare = sorted((self.last_used.get(k, 0), k)
                           for k in self.textures
                           if k not in keep and k not in START_KEYS)
            extra = len(self.textures) - int(MAX_TEXTURES * 0.9)
            for _, key in spare[:extra]:
                self._forget(key)
                self.built.pop(key, None)
        if len(self.pending) > MAX_PENDING:
            for key in [k for k in self.pending if k not in keep]:
                self.pending.pop(key)

    def paintGL(self):
        started = time.perf_counter()
        # Процессорное время потока. Разница с общим временем кадра -
        # ожидание GIL или драйвера, по ней видно, считает поток или ждёт.
        cpu_started = time.thread_time()
        self.frame += 1
        self._fit_camera()
        # Время шага навигатора видно снаружи, по нему проверочные
        # скрипты считают скорость перелёта.
        self.step_time = time.monotonic()
        moving = self.navigator.step(self.step_time)
        gpu.gl.glClearColor(*(HOLE if self.show_holes else SPACE), 1.0)
        gpu.gl.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
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
        self._upload_overlays()
        self._swap_built()
        marks.append(time.perf_counter())

        # Рельеф под глазом: от него ближняя плоскость и зазор камеры.
        if self.navigator.keep_clear():
            moving = True
        # Опрос высот вокруг глаза стоит до 1 мс. Он повторяется, только
        # если глаз сдвинулся или пришли новые высоты.
        probe = (tuple(self.camera.eye), self.store.version)
        if probe != self._nearest_probe:
            self._nearest_probe = probe
            self.camera.nearest = nearest_terrain(self.camera.eye,
                                                  self.store.height_at)
        marks.append(time.perf_counter())
        sel = lod.select(self.camera, self.textures.__contains__,
                         max_level=self.max_level,
                         heights=self.store.range_for,
                         memo=self.memo.bind(self.camera, lod.THRESHOLD,
                                             self.store.version,
                                             self.store.take_added()))
        self.selection = sel
        marks.append(time.perf_counter())
        if self.stale:
            self._drop_stale(sel.keep)
        self._want_heights(sel, time.monotonic())
        marks.append(time.perf_counter())
        for key in sel.keep:
            if key in self.textures:
                self.last_used[key] = self.frame
        want = self._with_stale(sel)
        wanted = frozenset(want)
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
            self.loader.want_many(want.items())
            self.loader.retain(want)
            self._wanted = wanted
            self._wanted_at = now
        marks.append(time.perf_counter())

        gpu.gl.glEnable(GL.GL_DEPTH_TEST)
        # Юбку тайла камера часто видит с изнанки, когда смотрит через
        # стык с соседом другого уровня. Отсечение обратных граней
        # убрало бы её.
        gpu.gl.glDisable(GL.GL_CULL_FACE)
        gpu.gl.glUseProgram(self.program)
        gpu.gl.glUniform1i(self.u_texture, 0)
        gpu.gl.glUniform1i(self.u_overlay, 1)
        self._clear_overlay()
        air = self.atmosphere and not self.show_holes
        air_uniforms(self.tile_air, self.camera, air)

        items = list(zip(self.caps, self.cap_textures or [self.ocean] * 2))
        items += [(self.meshes[key], self.textures[key]) for key in sel.draw]
        surface = len(items)
        scales = [1.0] * surface
        under = self._underlay_items(sel.keep)
        items += under
        scales += [UNDERLAY_SCALE] * len(under)
        mvps = self.camera.tiles_mvp([mesh.center for mesh, _ in items],
                                     scales=scales)
        overlays = None
        if self.overlay is not None and not self.show_holes:
            overlays = [(self.clear_texture, gpu.NO_OVERLAY)] * len(self.caps)
            overlays += self._overlay_items(sel, time.monotonic())
        gpu.draw_batch(items[:surface], mvps[:surface], self.u_mvp,
                       overlays, self.u_overlay_uv)
        if overlays is not None:
            # Подстилка идёт без наложения.
            self._clear_overlay()
        if self.hole_check:
            # До подстилки: щели между тайлами. После: видимые дыры.
            gaps = self._count_holes()
            GL.glUseProgram(self.program)
        gpu.draw_batch(items[surface:], mvps[surface:], self.u_mvp)
        if self.hole_check:
            holes = self._count_holes()
            GL.glUseProgram(self.program)
            self.hole_counts.append((self.frame, gaps, holes))
        if air:
            self._draw_sky()
        if (self.label_kinds or self.search_mark is not None) \
                and not self.show_holes:
            self._draw_labels(sel)
        else:
            self.labels.count = 0
        self.drawn = len(sel.draw)
        self.drawn_levels = Counter(k[0] for k in sel.draw)
        self.draw_calls = len(items)

        gpu.gl.glBindVertexArray(0)
        gpu.gl.glBindTexture(GL.GL_TEXTURE_2D, 0)
        gpu.gl.glUseProgram(0)
        for code in gpu.frame_errors():
            self.gl_errors[code] += 1
        marks.append(time.perf_counter())
        self._evict(sel.keep)
        self._evict_overlays(sel.keep)
        # Неподвижность проверяется по самой камере: её двигает не только
        # навигатор, но и проверочные скрипты.
        pose = (tuple(self.camera.eye), tuple(self.camera.rotation.ravel()))
        still = pose == self._last_pose
        self._last_pose = pose
        refill = still and not moving and len(self.pool.free) < POOL_TARGET
        if refill:
            # Кадр без движения пополняет запас текстур понемногу.
            self.pool.allocate(POOL_REFILL)
        if moving or refill or self.built or self._drop_overlays \
                or self.labels.pending or (
                self.pending and any(k in sel.keep for k in self.pending)) \
                or (self.overlay_pending and any(
                    k in sel.keep for k in self.overlay_pending)):
            self.update()
        marks.append(time.perf_counter())
        self.paint_span = (started, marks[-1])
        self.frame_times.append(marks[-1] - started)
        spans = [b - a for a, b in zip(marks, marks[1:])]
        self.sections.append(dict(zip(SECTIONS, spans),
                                  draws=self.draw_calls,
                                  cpu=time.thread_time() - cpu_started))
        self.changed.emit()

    def _clear_overlay(self):
        """Прозрачное наложение на блоке 1, окно без сдвига."""
        gpu.gl.glActiveTexture(GL.GL_TEXTURE1)
        gpu.gl.glBindTexture(GL.GL_TEXTURE_2D, self.clear_texture)
        gpu.gl.glActiveTexture(GL.GL_TEXTURE0)
        gpu.gl.glUniform4f(self.u_overlay_uv, *gpu.NO_OVERLAY, 0.0)

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
        GL.glUseProgram(self.hole_program)
        u = self.hole_uniforms
        eye = ray_uniforms(u, self.camera, A - HOLE_MARGIN, B - HOLE_MARGIN)
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

    def _draw_sky(self):
        """Небо и гало там, где нет тайлов.

        Полноэкранный треугольник на глубине 1.0, как у счётчика дыр,
        проверка глубины оставляет только пиксели без тайлов. Дымка
        над самими тайлами считается в шейдере тайла.
        """
        gl = gpu.gl
        gl.glUseProgram(self.sky_program)
        u = self.sky_air
        eye = air_uniforms(u, self.camera, True)
        gl.glUniform1f(u["u_qc"], float(eye @ eye) - 1.0)
        gl.glDepthFunc(GL.GL_LEQUAL)
        gl.glDepthMask(GL.GL_FALSE)
        gl.glBindVertexArray(self.empty_vao)
        gl.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        gl.glDepthMask(GL.GL_TRUE)
        gl.glDepthFunc(GL.GL_LESS)

    def _draw_labels(self, sel):
        """Надписи пунктов поверх кадра, с проверкой глубины."""
        now = time.monotonic()
        loader = self.place_loader
        if loader is not None and now - self._places_at > LOADER_PERIOD:
            wanted = {key: -key[0] for key in self.places.wanted(sel.draw)
                      if key not in self.places.tiles}
            keys = frozenset(wanted)
            if keys != self._places_wanted or now - self._places_at > 1.0:
                loader.want_many(wanted.items())
                loader.retain(wanted)
                self._places_wanted = keys
                self._places_at = now
        kinds = kinds_at(self.label_kinds, self.camera.altitude())
        places = self.places.collect(sel.draw, kinds)
        mark = self.search_mark
        if mark is not None:
            if self._marked[0] is not places or self._marked[1] is not mark:
                self._marked = (places, mark, [mark] + places)
            places = self._marked[2]
        height_at = self.store.height_at if self.store.scale else None
        self.labels.draw(self.camera, self.camera.projection(), places,
                         height_at, self.store.version,
                         self.devicePixelRatioF())

    def _underlay_items(self, keep):
        """Подстилка: тайлы уровня 2 на 3 км ниже поверхности.

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
                out.append((self.underlay_meshes[key],
                            marker or self.textures[key]))
        out += [(cap, marker or texture) for cap, texture
                in zip(self.caps, self.cap_textures or [self.ocean] * 2)]
        return out
