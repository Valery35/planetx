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
from qgis.PyQt.QtCore import (QObject, QRunnable, QThreadPool, Qt, QTimer,
                              pyqtSignal)
from qgis.PyQt.QtGui import QImage, QSurfaceFormat
from qgis.PyQt.QtWidgets import QApplication

from .. import journal
from ..core import cutaway, lod, skydata
from ..core.overlay import (MAX_ANCESTOR_DEPTH, urgency,
                            window as overlay_window)
from ..core.camera import Camera
from ..core import ellipsoid
from ..core.ellipsoid import ecef_to_geodetic
from ..core.flight import Flight
from ..core.navigation import (Navigator, Pose, altitude, ground_under,
                               nearest_terrain)
from ..core.places import Place, PlaceStore, kinds_at
from ..core.skyview import (FOV_MAX, FOV_MIN, distance_for, follow_pose,
                            pose_of, ra_dec_of)
from ..core.snapshot import letterbox
from ..core.terrain import FLAT_LEVEL, HeightStore
from ..core.tiling import (HOLE_MARGIN, UNDERLAY_DEPTH, polar_cap_mesh,
                           tile_mesh)
from ..qt_compat import QOpenGLWidget, enum
from . import gpu
from .buildings import SHOT_UPLOADS as BUILDING_SHOT_UPLOADS, Buildings
from .buildings import pick as pick_buildings
from .features import Features
from .labels import Labels, icon_style
from .gibs import LAYERS as GIBS_LAYERS, GibsLayer
from .subsurface import ImageWalls, Subsurface
from .quakes import DepositPoints, FirePoints, Quakes
from .satellites import SatellitePoints
from .constellations import Constellations
from .sky import Sky
from .stars import Stars
from .shaders import (HOLE_FRAGMENT, HOLE_VERTEX, SKY_FRAGMENT,
                      TILE_FRAGMENT, TILE_VERTEX, shell)

START_LEVELS = (0, 1, 2)
START_VIEW = (58.0105, 56.2294, 2.0e7)  # над Пермью, 20 000 км

SPACE = (0.0, 0.0, 0.0)
HOLE = (1.0, 0.0, 1.0)  # пурпурный фон проверочного режима
OCEAN = (0xAA, 0xD3, 0xDF, 0xFF)  # цвет воды на подложке OSM
UNDERLAY_COLOR = (0x00, 0xFF, 0x00, 0xFF)  # подстилка в проверочном режиме
UNDERLAY_LEVEL = 2
# Вода над дном океана: цвет и непрозрачность, мельче SHALLOW метров
# (с масштабом рельефа) вода прозрачнее. Выбор помощника, утверждает
# автор.
WATER_COLOR = (0.09, 0.30, 0.55, 0.5)
SHALLOW = 200.0
# Подстилка лежит на UNDERLAY_DEPTH ниже поверхности. Это больше шага
# буфера глубины у дальней плоскости. Худший случай - глаз на высоте
# 9 км в 50 м от склона: ближняя плоскость 25 м, дальняя 680 км,
# шаг 1.1 км.
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
CLICK_PIXELS = 4.0  # логических пикселей, дальше - уже перетаскивание
# Снимок вида. Кадры снимка идут по таймеру, в них грузится больше
# текстур: плавность движения не нужна, камера стоит.
SHOT_PERIOD = 30  # мс между кадрами снимка
SHOT_UPLOADS = 24
SHOT_UPLOAD_TIME = 0.02
SHOT_OVERLAY_UPLOADS = 8
# Снимок готов, когда столько кадров подряд ничего не ждут. Ответы
# запросов видимости надписей приходят через кадр.
SHOT_SETTLE = 3
PREVIEW_COLOR = (0.18, 0.18, 0.18)  # поля вокруг снимка в окне
PUMP_PERIOD = 250  # мс, страховочный запуск загрузчиков без кадров
# Загрузка считается вставшей, если вид ждёт тайлы, а столько секунд
# ничего не приходило. Три такие остановки 28 сентября 2026 года
# пользователь видел только как размытую картинку.
STALL_SHOW = 5.0
# Вершин своих объектов в видеокарте, больше - строка состояния
# предупреждает. 29 провинций Афганистана - 22 тысячи.
OBJECT_BUDGET = 200000

LEFT = enum(Qt, "MouseButton", "LeftButton")
MIDDLE = enum(Qt, "MouseButton", "MiddleButton")
RIGHT = enum(Qt, "MouseButton", "RightButton")
SHIFT = enum(Qt, "KeyboardModifier", "ShiftModifier")
CTRL = enum(Qt, "KeyboardModifier", "ControlModifier")

# Навигация как в Google Earth, решение автора от 29 сентября 2026 года.
# Величины - умолчания помощника, их назначает автор.
DOUBLE_ZOOM = 0.4  # двойной щелчок приближает в 2.5 раза, правой - отдаляет
RIGHT_ZOOM = 0.005  # правая кнопка: e^(0.005·200) = 2.7 раза на 200 пикселей
LOOK_PER_PIXEL = 0.1  # градусов на логический пиксель, Ctrl с левой
KEY_PAN = 0.05  # доля ширины видимой полосы на нажатие стрелки
KEY_TURN = 3.0  # градусов на нажатие Shift и Ctrl со стрелками
ARROWS = {"Key_Left": (-1, 0), "Key_Right": (1, 0), "Key_Up": (0, 1),
          "Key_Down": (0, -1)}


def surface_format():
    fmt = QSurfaceFormat()
    fmt.setVersion(3, 3)
    fmt.setProfile(enum(QSurfaceFormat, "OpenGLContextProfile",
                        "CoreProfile"))
    fmt.setDepthBufferSize(24)
    fmt.setSwapInterval(1)
    return fmt


AIR_UNIFORMS = ("u_rotation", "u_tan", "u_viewport", "u_eye", "u_axes",
                "u_qc_shell", "u_air", "u_sun", "u_sun_on", "u_radius_km",
                "u_air_tint")


def uniforms(program, names):
    return {name: GL.glGetUniformLocation(program, name) for name in names}


def ray_uniforms(u, camera, a=None, b=None):
    """Общие для полноэкранных проходов величины луча из глаза.

    Координаты в долях полуосей эллипсоида с полуосями a и b. Возвращает
    глаз в этих координатах, float64.
    """
    a = ellipsoid.A if a is None else a
    b = ellipsoid.B if b is None else b
    axes = np.array([1.0 / a, 1.0 / a, 1.0 / b])
    eye = camera.eye * axes
    t = math.tan(math.radians(camera.fov_y) / 2.0)
    gpu.gl.matrix3(u["u_rotation"], GL.GL_TRUE, camera.rotation)
    gpu.gl.glUniform2f(u["u_tan"], t * camera.aspect, t)
    gpu.gl.glUniform2f(u["u_viewport"], camera.width, camera.height)
    gpu.gl.glUniform3f(u["u_eye"], *eye)
    gpu.gl.glUniform3f(u["u_axes"], *axes)
    return eye


def air_uniforms(u, camera, on, sun=None, tint=(1.0, 1.0, 1.0)):
    """Величины воздуха и солнца. sun - направление на солнце в ECEF
    или None, тогда свет - отмывка без солнца. tint - рассеяние
    воздуха тела к земному по R, G, B или None - воздуха нет."""
    eye = ray_uniforms(u, camera)
    top = shell(ellipsoid.A)
    gpu.gl.glUniform1f(u["u_qc_shell"], float(eye @ eye) - top * top)
    gpu.gl.glUniform1f(u["u_air"], 1.0 if on and tint is not None else 0.0)
    gpu.gl.glUniform1f(u["u_radius_km"], ellipsoid.A / 1000.0)
    gpu.gl.glUniform3f(u["u_air_tint"], *(tint or (1.0, 1.0, 1.0)))
    gpu.gl.glUniform3f(u["u_sun"], *(sun or (0.0, 0.0, 1.0)))
    gpu.gl.glUniform1f(u["u_sun_on"], 0.0 if sun is None else 1.0)
    return eye


def start_keys():
    return [(z, x, y) for z in START_LEVELS
            for x in range(1 << z) for y in range(1 << z)]


START_KEYS = frozenset(start_keys())
REBUILD_TIME = 0.002  # секунд на подмену пересобранных сеток в кадре
# Приоритет замены тайла старой подложки, который виден в кадре. Выше
# экранной ошибки любого нового тайла, мелкие уровни раньше.
STALE_PRIORITY = 1.0e6
# Приоритет высот для линейки и профиля. Ниже тайлов кадра, у них
# приоритет - экранная ошибка в пикселях.
TOOL_HEIGHT_PRIORITY = 0.5


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


class _Shot:
    """Снимок в работе: размер, масштаб надписей, буфер кадра."""

    def __init__(self, width, height, ratio):
        self.width = width
        self.height = height
        self.ratio = ratio
        self.fbo = None
        self.buffers = []
        # Кадров подряд без ожидания и просьба снять сейчас.
        self.calm = 0
        self.force = False


class GlobeView(QOpenGLWidget):
    """Глобус. Ресурсы OpenGL живут и умирают вместе с контекстом."""

    changed = pyqtSignal()
    # Щелчок левой кнопкой без перетаскивания, пиксели кадра.
    clicked = pyqtSignal(float, float)
    # Курсор над видом без нажатых кнопок, пиксели кадра. Уход курсора
    # из вида - (-1, -1).
    hovered = pyqtSignal(float, float)
    # Снимок: сколько тайлов, картинок и надписей он ещё ждёт.
    shot_progress = pyqtSignal(int)
    # Снимок готов: QImage или None при ошибке, всё ли загрузилось.
    shot_done = pyqtSignal(object, bool)
    # Сменилось состояние загрузки: сколько ждёт, стоит ли загрузка.
    load_changed = pyqtSignal()
    # Сменилось растяжение коры разреза Земли, cutaway.gain_for.
    wedge_gain_changed = pyqtSignal()
    # Backspace или Delete над видом: убрать последнюю точку инструмента.
    undo_point = pyqtSignal()
    # Щелчок правой кнопкой без сдвига, пиксели кадра: меню глобуса.
    menu_requested = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFormat(surface_format())
        lat, lon, distance = START_VIEW
        self.camera = Camera.look_at(lat, lon, distance)
        self.navigator = Navigator(self.camera, Pose(lat, lon, distance))
        self.turning = None
        self._press = None  # пиксель нажатия левой кнопки
        # Взгляд по сторонам с Ctrl и приближение правой кнопкой:
        # последний пиксель и точка, к которой идёт приближение.
        self.looking = None
        self.zoom_drag = None
        # Стрелки и буквы навигации приходят виду, когда он в фокусе.
        self.setFocusPolicy(enum(Qt, "FocusPolicy", "StrongFocus"))
        # Слежение за мышью без нажатия: координаты под курсором.
        self.setMouseTracking(True)
        # Курсор в покое: стрелка, у инструментов - перекрестие. Ладонь
        # была всюду и мешала целиться, решение автора 27 сентября 2026
        # года. Сжатая ладонь - только пока Земля тянется.
        self.tool_cursor = enum(Qt, "CursorShape", "ArrowCursor")
        # Включён инструмент: опрос, линейка или рисование. Тогда второй
        # щелчок двойного - обычный щелчок, точка инструмента.
        self.tool_active = False
        # Точки инструмента, которые можно тянуть мышью: объект с методами
        # grab(px, py) -> bool, move(px, py) и drop(). Ставит окно.
        self.vertex_tool = None
        self._vertex_drag = False
        # Правая кнопка: щелчок без сдвига открывает меню. Меню ждёт
        # срок двойного щелчка, двойной щелчок правой отдаляет.
        self._right_press = None
        self._right_double = False
        self._menu_point = None
        self._menu_timer = QTimer(self)
        self._menu_timer.setSingleShot(True)
        self._menu_timer.timeout.connect(self._emit_menu)
        self.setCursor(self.tool_cursor)
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
        # Тайлы высот для линейки и профиля. Загрузчик высот оставляет
        # только набор вида, поэтому они входят в него.
        self.tool_heights = {}
        self._nearest_probe = None
        # Ошибки и видимость узлов между кадрами неподвижной камеры.
        self.memo = lod.Memo()
        # Подземный режим: сетки (render/subsurface.py), непрозрачность
        # поверхности и пол навигации - функция высоты на экране или
        # None. С полом камера опускается под рельеф до низа модели.
        self.subsurface = Subsurface()
        # Разрезы с картинками подземного режима.
        self.image_walls = ImageWalls()
        # Фото с камерой (core/overlays.py): плоскости с картинкой в 3D.
        self.photos = ImageWalls()
        self._terrain_nearest = None
        # Разрез Земли: вынутый сектор (core.cutaway.Wedge или None)
        # и грани с оболочками - отдельный набор подземных сеток.
        self.wedge = None
        # Палеогеография: снимок подложки - карта прошлого со своей
        # отмывкой. Без отмывки вида, воды, наложений, солнца и подписей
        # нынешних мест.
        self.plain_base = False
        self.cutaway = Subsurface()
        self.wedge_crust = None
        self.wedge_gain = 1.0
        # Плиты Slab2 на гранях: зоны, которых касается разрез, и их
        # полосы - поверх граней со смещением глубины.
        self.wedge_slabs = []
        self.cutaway_slabs = Subsurface(offset=True)
        # Запросов данных вне загрузчиков тайлов: файлы зон плит.
        # Входят в счётчик загрузки, его показывает значок загрузки.
        self.data_pending = 0
        # Стенка разреза вдоль линии (окно «Разрез»): видна сквозь
        # поверхность.
        self.section_wall = Subsurface(xray=True)
        # Вода водоёмов своей батиметрии (core/bathymetry.py): после
        # поверхности, дно видно сквозь неё. Сетка на врезку.
        self.lake_water = Subsurface(glass=True)
        # Выдавленные слои проекта (ui/extrude.py): призмы, столбики
        # и стенки над рельефом, сетка на слой.
        self.extruded = Subsurface()
        # Надписи без пунктов вынутого сектора: список, сектор, итог.
        self._wedged = (None, None, [])
        # Землетрясения: очаги точками поверх поверхности.
        self.quakes = Quakes()
        # Пожары NASA FIRMS: очаги точками на рельефе.
        self.fires = FirePoints()
        # Месторождения USGS (core/deposits.py): точки на рельефе.
        self.deposits = DepositPoints()
        # Спутники - своей проекцией, геостационарные дальше дальней
        # плоскости вида (render/satellites.py).
        self.satellites = SatellitePoints()
        self.surface_alpha = 1.0
        self.floor = None
        # Дно океана: высоты Земли ниже нуля не обнуляются, над ними
        # рисуется вода (_draw_water). Включает строка «Дно океана».
        self.sea_floor = False
        self.navigator.set_terrain(self.terrain_at)
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
        # Ошибки OpenGL, накопленные вне кадра: от Qt, между кадрами.
        self.outside_errors = Counter()
        self.draw_calls = 0
        self._wanted = frozenset()
        self._wanted_at = 0.0
        self._last_pose = None
        # Счётчик пикселей Земли без тайлов, включают проверочные скрипты.
        self.hole_check = False
        # Небо, гало и дымка. Выключается для сравнения в замерах.
        self.atmosphere = True
        # Направление на солнце в ECEF или None - свет отмывки без
        # солнца. Ставит окно по строке «Солнце» раздела «Слои».
        self.sun = None
        # Воздух тела: рассеяние к земному по R, G, B, None - воздуха
        # нет. Ставит окно по телу (core/planets.py).
        self.air_tint = (1.0, 1.0, 1.0)
        self.hole_counts = []
        # Надписи пунктов: тайлы пунктов, их загрузчик и отрисовка.
        # Загрузчик ставит окно, когда известен адрес тайлов.
        self.places = PlaceStore()
        self.place_loader = None
        # Классы надписей для включённых групп векторной основы.
        self.label_kinds = set()
        # Подписи координатной сетки, core.places.Place класса «grid».
        self.grid_marks = []
        # Подписи слоёв проекта, ui/layer_labels.py.
        self.layer_marks = []
        # Названия литосферных плит, строка «Границы плит».
        self.plate_marks = []
        # Числа поля прогноза погоды, ставит окно (_update_values).
        self.value_marks = []
        # Подписи устьев скважин подземного режима.
        self.subsurface_marks = []
        # Длины отрезков линейки и точка профиля высот.
        self.tool_marks = []
        self._places_wanted = frozenset()
        self._places_at = 0.0
        self.labels = Labels()
        # Временная метка найденного места, Place класса «search» или None.
        # Список пунктов с меткой помнится вместе со списком без неё:
        # таблица надписей узнаёт прежний список по тождеству.
        self.search_mark = None
        # Свои объекты: линии и многоугольники рисует Features, точки -
        # надписи класса «mark».
        self.features = Features()
        # 3D-здания из тайлов OpenFreeMap, строка «3D-здания».
        self.buildings = Buildings()
        self.stars = Stars()
        self.sky = Sky()  # Млечный путь, строка «Звёзды»
        self.show_stars = True
        # Вид неба: core.skyview.SkyView или None - глобус. Камера неба
        # стоит в экваториальной системе, светила - на момент sky_time,
        # None - часы компьютера.
        self.sky_view = None
        # Шёл ли перелёт взгляда в прошлом кадре неба, см. _render_sky.
        self._sky_moved = False
        self.sky_time = None
        self.sky_camera = Camera((0.0, 0.0, 0.0), np.eye(3))
        self.constellations = Constellations()
        self.show_constellations = True
        self.bodies = Stars(source=lambda: skydata.body_points(time.time()))
        # Метки неба: (направление J2000, название), ставит окно.
        self.sky_places = []
        self._bodies_time = None
        self._sky_press = None
        # Слои NASA GIBS: облака, температура моря и суши.
        self.gibs = {name: GibsLayer(level)
                     for name, level, _, _, _ in GIBS_LAYERS}
        # Шторка сравнения: доля ширины кадра от левого края или None.
        # Левее неё - слой «compare», ставит окно (ui/swipe.py).
        self.swipe = None
        self._feature_marks = ([], None)
        self._marked = (None, None, [])
        self._context = None
        self._overlay_missing = 0
        # Состояние загрузки для строки состояния: сколько тайлов,
        # картинок и надписей ждёт кадр, секунд без поступлений, когда
        # что-то ждёт, и время последнего поступления.
        self.load_missing = 0
        self.load_stalled = 0.0
        self.last_arrival = time.monotonic()
        # Сообщить загрузчикам, движется ли камера: функция с флагом
        # или None. Ставит окно.
        self.on_motion = None
        # Снимок вида в работе, _Shot или None.
        self.shot = None
        self._shot_timer = QTimer(self)
        self._shot_timer.timeout.connect(self._shot_frame)
        # Загрузчики запускают запросы после каждого показанного кадра:
        # таймер запуска при частой перерисовке не срабатывает.
        self.frameSwapped.connect(self._pump_loaders)
        # Страховка без кадров. Просьбу тайлов вид шлёт загрузчику только
        # в кадре, а кадры идут, пока приходят тайлы. Загрузчик опустел
        # раньше новой просьбы - кадров нет, картинка стоит грубой.
        # Нашлось 28 сентября 2026 года. Таймер заказывает кадр, если
        # вид ждёт тайлы, а загрузчик пуст, и подгоняет загрузчики.
        self._pump_timer = QTimer(self)
        self._pump_timer.setInterval(PUMP_PERIOD)
        self._pump_timer.timeout.connect(self._heartbeat)
        self._pump_timer.start()

    def _pump_loaders(self):
        for loader in (self.loader, self.terrain_loader, self.place_loader,
                       self.overlay, self.buildings.loader):
            if loader is not None:
                loader.pump_if_due()

    def _heartbeat(self):
        """Таймер вида: подгонка загрузчиков, кадр, если вид ждёт тайлы
        при пустом загрузчике, и состояние загрузки. Подсчёт ждущего
        стоит миллисекунды, после каждого кадра он отнимал у поворота
        до трети кадров."""
        self._pump_loaders()
        sel = self.selection
        if sel is not None and sel.want and self.loader is not None \
                and not self.loader.busy() and self.shot is None:
            self.update()
        elif self.buildings.results and self.shot is None:
            # Готовые сетки зданий уходят в видеокарту только в кадре.
            self.update()
        self._check_load(sel)

    def _check_load(self, sel):
        """Сколько ждёт кадр и стоит ли загрузка, для строки состояния."""
        if self.sky_view is not None:
            # Небо ничего не ждёт. Загрузка глобуса под ним стоит, но
            # это не остановка.
            if self.load_missing or self.load_stalled:
                self.load_missing, self.load_stalled = 0, 0.0
                self.load_changed.emit()
            return
        if sel is None or self.shot is not None:
            return
        missing = self._missing(sel) + self.data_pending
        # Надписи ждут ответов проверок видимости, а не данных, вставшей
        # считается только загрузка данных.
        data = missing - (1 if self.labels.pending else 0)
        idle = time.monotonic() - self.last_arrival
        stalled = idle if data > 0 and idle > STALL_SHOW else 0.0
        state = (missing, int(stalled))
        if state != (self.load_missing, int(self.load_stalled)):
            self.load_missing, self.load_stalled = missing, stalled
            self.load_changed.emit()

    def object_vertices(self):
        """Вершин своих объектов в видеокарте."""
        return self.features.vertex_count()

    # Данные

    def add_image(self, key, rgba, mesh=None, level=-1):
        """Картинка тайла и, если есть, готовая сетка его вершин.

        level - уровень тайла высот, с которым собрана сетка, -1 без
        высот.
        """
        self.pending[key] = (rgba, mesh, level)
        self.last_arrival = time.monotonic()
        self.update()

    def set_tool_cursor(self, cross):
        """Перекрестие у инструментов, иначе стрелка."""
        self.tool_cursor = enum(Qt, "CursorShape",
                                "CrossCursor" if cross else "ArrowCursor")
        self.tool_active = bool(cross)
        self.setCursor(self.tool_cursor)

    def set_shapes(self, shapes):
        """Свои объекты глобуса, core.features.Shape."""
        self.features.set_shapes(shapes)
        self.update()

    def _own_marks(self):
        """Точечные объекты как надписи класса «mark»."""
        shapes = self.features.shapes
        if self._feature_marks[1] is not shapes:
            self._feature_marks = ([
                Place(-2 - i, name or "", icon_style(icon, color), 1, lat,
                      lon, None, lift)
                for i, name, lat, lon, lift, icon, color
                in self.features.marks()],
                shapes)
        return self._feature_marks[0]

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
        self.last_arrival = time.monotonic()
        self.update()

    def _draw_water(self, items, mvps):
        """Вода над дном океана: те же сетки тайлов, опущенные на уровень
        моря (TileMesh.sea), только там, где рельеф ниже нуля. Глубину
        не пишет, поэтому дно видно сквозь неё, а суша выше нуля
        закрывает её проверкой глубины. Программа - тайла, с дымкой."""
        if not items:
            return
        gl = gpu.gl
        gl.glUniform1f(self.u_water, 1.0)
        gl.glUniform4f(self.u_water_color, *WATER_COLOR)
        gl.glUniform1f(self.u_shallow, SHALLOW * self.store.scale)
        gl.glEnable(GL.GL_BLEND)
        GL.glBlendFuncSeparate(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA,
                               GL.GL_ZERO, GL.GL_ONE)
        GL.glDepthMask(GL.GL_FALSE)
        try:
            gpu.draw_batch(items, mvps, self.u_mvp)
        finally:
            GL.glDepthMask(GL.GL_TRUE)
            gl.glDisable(GL.GL_BLEND)
            gl.glUniform1f(self.u_water, 0.0)

    def label_height(self, lat, lon):
        """Высота надписи: с дном океана - не ниже уровня моря, иначе
        названия морей лежали бы на дне."""
        h = self.store.height_at(lat, lon)
        return max(h, 0.0) if self.sea_floor else h

    def terrain_at(self, lat, lon):
        """Высота на экране, по которой ходит камера: рельеф или, если
        задан пол подземного режима, наименьшее из рельефа и пола."""
        h = self.store.height_at(lat, lon)
        if self.floor is not None:
            low = self.floor(lat, lon)
            if low is not None and low < h:
                return low
        return h

    def set_wedge(self, wedge, crust=None):
        """Разрез Земли: вынуть сектор wedge (core.cutaway.Wedge) или
        вернуть поверхность (None). crust - модель коры core.crust.Crust
        для граней или None."""
        self.wedge = wedge
        self.wedge_crust = crust
        self.camera.deep = wedge is not None
        self.wedge_gain = self._wedge_gain()
        self.cutaway.set_mesh("faces", None if wedge is None
                              else cutaway.faces(wedge, crust=crust,
                                                 gain=self.wedge_gain))
        if wedge is None:
            self.wedge_slabs = []
        self._build_wedge_slabs()
        self.update()

    def _wedge_gain(self):
        """Растяжение коры для нынешнего расстояния до точки взгляда,
        без сектора - 1."""
        if self.wedge is None:
            return 1.0
        return cutaway.gain_for(self.navigator.pose.distance)

    def _follow_wedge_gain(self):
        """Грани заново, если сменилась ступень растяжения коры. Зовётся
        из кадра, сборка граней - около 6 мс."""
        gain = self._wedge_gain()
        if gain == self.wedge_gain:
            return
        self.wedge_gain = gain
        self.cutaway.set_mesh("faces", cutaway.faces(
            self.wedge, crust=self.wedge_crust, gain=gain))
        self._build_wedge_slabs()
        self.wedge_gain_changed.emit()

    def set_wedge_slabs(self, zones):
        """Зоны плит Slab2 на гранях разреза, core.slabs.Slab."""
        self.wedge_slabs = list(zones)
        self._build_wedge_slabs()
        self.update()

    def _build_wedge_slabs(self):
        mesh = None
        if self.wedge is not None and self.wedge_slabs:
            mesh = cutaway.slab_bands(self.wedge, self.wedge_slabs,
                                      self.wedge_gain)
        self.cutaway_slabs.set_mesh("bands", mesh)

    def eye_underground(self):
        """Глаз ниже рельефа под ним - только с полом подземного режима."""
        if self.floor is None:
            return False
        lat, lon, h = (float(v) for v in ecef_to_geodetic(
            np.asarray(self.camera.eye, dtype=np.float64)))
        return h < self.store.height_at(lat, lon)

    def want_tool_heights(self, keys):
        """Тайлы высот для линейки и профиля. Прежний набор заменяется,
        пришедшие тайлы из него уходят сами."""
        self.tool_heights = {key: TOOL_HEIGHT_PRIORITY for key in keys
                             if key not in self.store.tiles}
        self._terrain_at = 0.0
        self.update()

    def add_heights(self, tile):
        """Пришёл тайл высот. Тайлы, которым он точнее, пересобираются."""
        self.store.add(tile)
        self.last_arrival = time.monotonic()
        for key, level in list(self.mesh_levels.items()):
            self._maybe_rebuild(key, level)
        self.update()

    def change_source(self, max_level, coarse=False):
        """Новая подложка.

        Тайлы прежней подложки, нужные кадру, и уровни 0-2 остаются
        на экране, пока их не заменят новые. Остальные освобождаются
        в кадре, где контекст OpenGL текущий, см. _drop_stale.

        coarse=True - на экране остаются только уровни 0-2, прочие тайлы
        освобождаются сразу. Так у карт возрастов палеогеографии кадр
        не смешивает две карты: новая встаёт грубой и уточняется.
        """
        self.max_level = max_level
        self.pending.clear()
        if coarse and self._context is not None:
            self.makeCurrent()
            for key in [k for k in self.textures if k not in START_KEYS]:
                self._forget(key)
            self.doneCurrent()
        self.stale = set(self.textures)
        self._wanted = frozenset()
        self._wanted_at = 0.0
        self.update()

    def change_body(self, max_level, air_tint):
        """Новое тело. core.ellipsoid.set_body окно уже сделало.

        Сброс полный: тайлы, сетки, высоты, наложение и кэш выбора
        тайлов прежнего тела на другом радиусе не годятся даже на время.
        Полярные шапки и подстилка строятся заново. Кадр не рисуется,
        пока не придут уровни 0-2 нового тела.
        """
        self.max_level = max_level
        self.air_tint = air_tint
        lod.clear_cache()
        self.memo = lod.Memo()
        self.store.clear()
        self.relief += 1
        self.build_pool.clear()
        self.building.clear()
        self.built.clear()
        self.pending.clear()
        self.overlay_pending.clear()
        self.stale = set()
        self._wanted = frozenset()
        self._wanted_at = 0.0
        if self._context is not None:
            self.makeCurrent()
            for key in list(self.textures):
                self._forget(key)
            for key in list(self.overlays):
                self._forget_overlay(key)
            for mesh in self.caps + list(self.underlay_meshes.values()):
                mesh.delete()
            for texture in self.cap_textures:
                gpu.delete_texture(texture)
            self.cap_textures = []
            self.caps = [gpu.GpuMesh(polar_cap_mesh(north))
                         for north in (True, False)]
            self.underlay_meshes = {
                key: gpu.GpuMesh(tile_mesh(*key)) for key in START_KEYS
                if key[0] == UNDERLAY_LEVEL}
            self.doneCurrent()
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
        self.last_arrival = time.monotonic()
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
        self.buildings.set_relief(self.relief)
        self.build_pool.clear()
        self.building.clear()
        self.built.clear()
        self.pending = {key: (image, mesh, -1) for key, (image, mesh, _)
                        in self.pending.items()}
        for key in self.mesh_levels:
            self.mesh_levels[key] = -1
            self._maybe_rebuild(key, -1)
        self.update()

    def reset_heights(self):
        """Забыть высоты и пересобрать сетки по новым, например когда
        включили дно океана: прежние высоты моря обнулены. До прихода
        новых высот рисуются прежние сетки."""
        self.store.clear()
        self.relief += 1
        self.buildings.set_relief(self.relief)
        self.build_pool.clear()
        self.building.clear()
        self.built.clear()
        self.pending = {key: (image, mesh, -1) for key, (image, mesh, _)
                        in self.pending.items()}
        for key in self.mesh_levels:
            self.mesh_levels[key] = -1
        self._terrain_wanted = frozenset()
        self._terrain_at = 0.0
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
        if self.shot is not None:
            return
        self._fit_camera()
        px, py = self._pixel(event)
        button = event.button()
        if self.sky_view is not None:
            # Небо тянется левой кнопкой. Щелчок без сдвига - точка
            # новой метки, сигнал clicked.
            self._sky_press = (px, py) if button == LEFT else None
            self._press = self._sky_press
            return
        shift = bool(event.modifiers() & SHIFT)
        ctrl = bool(event.modifiers() & CTRL)
        if button == MIDDLE or (button == LEFT and shift):
            # Поворот не обрывает начатое приближение колесом.
            self.navigator.stop_inertia()
            self.turning = (px, py)
        elif button == LEFT and ctrl:
            self.navigator.stop()
            self.looking = (px, py)
        elif button == RIGHT:
            self.navigator.stop()
            self.zoom_drag = (px, py, py)
            self._right_press = (px, py)
        elif button == LEFT and self.vertex_tool is not None \
                and self.vertex_tool.grab(px, py):
            # Точка линейки под курсором тянется, Земля стоит.
            self.navigator.stop()
            self._vertex_drag = True
        elif button == LEFT:
            self._press = (px, py)
            self.navigator.press(px, py, time.monotonic())
        self.update()

    def mouseMoveEvent(self, event):
        if self.shot is not None:
            return
        px, py = self._pixel(event)
        self.hovered.emit(px, py)
        if self.sky_view is not None:
            if self._sky_press is not None:
                x0, y0 = self._sky_press
                self._sky_press = (px, py)
                self.sky_view.drag(px - x0, py - y0, self.camera.height)
                self.sync_sky_pose()
                self.update()
            return
        if self._vertex_drag:
            self.vertex_tool.move(px, py)
            self.update()
            return
        if self._press is not None and math.hypot(
                px - self._press[0], py - self._press[1]) \
                > CLICK_PIXELS * self.devicePixelRatioF():
            self._press = None
            if self.navigator.grab is not None:
                self.setCursor(enum(Qt, "CursorShape", "ClosedHandCursor"))
        if self.looking is not None:
            x0, y0 = self.looking
            self.looking = (px, py)
            step = LOOK_PER_PIXEL / self.devicePixelRatioF()
            self.navigator.look_around((px - x0) * step, (y0 - py) * step)
            self.update()
        elif self.zoom_drag is not None:
            # Вверх - ближе, вниз - дальше, к точке нажатия.
            x0, y0, last = self.zoom_drag
            if self._right_press is not None and math.hypot(
                    px - x0, py - y0) \
                    > CLICK_PIXELS * self.devicePixelRatioF():
                self._right_press = None
            self.zoom_drag = (x0, y0, py)
            factor = math.exp((py - last) * RIGHT_ZOOM
                              / self.devicePixelRatioF())
            self.navigator.zoom_now(x0, y0, factor)
            self.update()
        elif self.turning is not None:
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
        if self.shot is not None:
            return
        if self.sky_view is not None:
            press, self._press = self._press, None
            self._sky_press = None
            if press is not None and event.button() == LEFT:
                px, py = self._pixel(event)
                if math.hypot(px - press[0], py - press[1]) \
                        <= CLICK_PIXELS * self.devicePixelRatioF():
                    self.clicked.emit(*press)
            return
        press, self._press = self._press, None
        if self._vertex_drag:
            self._vertex_drag = False
            if self.vertex_tool is not None:
                self.vertex_tool.drop()
        elif press is not None and event.button() == LEFT:
            self.clicked.emit(*press)
        if event.button() == RIGHT:
            right, self._right_press = self._right_press, None
            double, self._right_double = self._right_double, False
            if right is not None and not double:
                self._menu_point = right
                self._menu_timer.start(QApplication.doubleClickInterval())
        self.turning = None
        self.looking = None
        self.zoom_drag = None
        self.navigator.release(time.monotonic())
        self.setCursor(self.tool_cursor)
        self.update()

    def _emit_menu(self):
        point, self._menu_point = self._menu_point, None
        if point is not None and self.shot is None:
            self.menu_requested.emit(*point)

    def surface_hit(self, px, py):
        """Точка ECEF под пикселем кадра на крыше или стене здания, если
        луч встречает его раньше рельефа, иначе на рельефе. None - луч
        уходит мимо Земли. Для 3D-линейки."""
        self._fit_camera()
        ground = ground_under(self.camera, px, py,
                              self.navigator.pose.terrain)
        buildings = self.buildings
        if not buildings.shown:
            return ground
        origin, d = self.camera.ray(px, py)
        items = [buildings.buffers[k] for k in buildings.wanted
                 if k in buildings.buffers]
        t = pick_buildings(items, origin, d)
        if t is None:
            return ground
        hit = np.asarray(origin, dtype=np.float64) + np.asarray(d) * t
        if ground is not None and float(np.linalg.norm(ground - origin)) \
                < float(np.linalg.norm(hit - origin)):
            return ground
        return hit

    def mouseDoubleClickEvent(self, event):
        """Двойной щелчок левой - перелёт к точке с приближением, правой -
        отдаление, как в Google Earth."""
        if self.shot is not None:
            return
        if self.sky_view is not None:
            # Левая - точка в середину и ближе вдвое, правая - дальше.
            self._fit_camera()
            sky = self.sky_view
            if event.button() == LEFT:
                px, py = self._pixel(event)
                v = sky.direction_at(px, py, self.camera.width,
                                     self.camera.height)
                ra, dec = ra_dec_of(v)
                self.fly_sky(ra, dec, sky.fov / 2.0)
            elif event.button() == RIGHT:
                ra, dec = ra_dec_of(sky.forward())
                self.fly_sky(ra, dec, sky.fov * 2.0)
            self.update()
            return
        if event.button() == RIGHT:
            self._menu_timer.stop()
            self._right_double = True
        if self.tool_active:
            self.mousePressEvent(event)
            return
        self._fit_camera()
        nav = self.navigator
        pose = nav.pose
        if event.button() == LEFT and not event.modifiers() & (SHIFT | CTRL):
            px, py = self._pixel(event)
            point = ground_under(self.camera, px, py, pose.terrain)
            if point is None:
                return
            lat, lon, _ = ecef_to_geodetic(point)
            self.fly_pose(float(lat), float(lon), pose.distance * DOUBLE_ZOOM,
                      pose.heading, pose.tilt)
        elif event.button() == RIGHT:
            self.fly_pose(pose.lat, pose.lon, pose.distance / DOUBLE_ZOOM,
                      pose.heading, pose.tilt)

    def fly_pose(self, lat, lon, distance, heading, tilt):
        flight = Flight(self.navigator.pose, lat, lon, distance, heading,
                        tilt, fov_y=self.camera.fov_y)
        self.navigator.start_flight(flight, time.monotonic())
        self.update()

    def keyPressEvent(self, event):
        """Клавиши Google Earth. Стрелки сдвигают вид, с Shift
        поворачивают и наклоняют, с Ctrl - взгляд по сторонам. PageUp,
        PageDown, плюс и минус приближают и отдаляют. N - север вверху,
        U - взгляд отвесно, R - то и другое, пробел останавливает."""
        if self.shot is not None:
            return
        self._fit_camera()
        key = event.key()
        mods = event.modifiers()
        nav = self.navigator
        pose = nav.pose

        def named(*names):
            return any(key == enum(Qt, "Key", n) for n in names)

        if self.sky_view is not None:
            if self._sky_key(key, named):
                self.sync_sky_pose()
                self.update()
            else:
                super().keyPressEvent(event)
            return

        for name, (dx, dy) in ARROWS.items():
            if key == enum(Qt, "Key", name):
                if mods & CTRL:
                    nav.look_around(dx * KEY_TURN, dy * KEY_TURN)
                elif mods & SHIFT:
                    nav.turn(dx * KEY_TURN, dy * KEY_TURN)
                else:
                    width = 2.0 * pose.distance * math.tan(
                        math.radians(self.camera.fov_y) / 2.0)
                    nav.pan_by(dy * KEY_PAN * width, dx * KEY_PAN * width)
                self.update()
                return
        centre = (self.camera.width / 2.0, self.camera.height / 2.0)
        if named("Key_PageUp", "Key_Plus", "Key_Equal"):
            nav.wheel(*centre, WHEEL_STEP, time.monotonic())
        elif named("Key_PageDown", "Key_Minus"):
            nav.wheel(*centre, 1.0 / WHEEL_STEP, time.monotonic())
        elif named("Key_N"):
            self.fly_pose(pose.lat, pose.lon, pose.distance, 0.0, pose.tilt)
        elif named("Key_U"):
            self.fly_pose(pose.lat, pose.lon, pose.distance, pose.heading, 0.0)
        elif named("Key_R"):
            self.fly_pose(pose.lat, pose.lon, pose.distance, 0.0, 0.0)
        elif named("Key_Space"):
            nav.stop()
        elif named("Key_Backspace", "Key_Delete"):
            self.undo_point.emit()
        else:
            super().keyPressEvent(event)
            return
        self.update()

    def _sky_key(self, key, named):
        """Клавиши вида неба: стрелки сдвигают взгляд на долю высоты
        кадра, PageUp, PageDown, плюс и минус меняют угол обзора."""
        height = self.camera.height
        for name, (dx, dy) in ARROWS.items():
            if key == enum(Qt, "Key", name):
                self.sky_view.drag(-dx * KEY_PAN * 2.0 * height,
                                   dy * KEY_PAN * 2.0 * height, height)
                return True
        if named("Key_PageUp", "Key_Plus", "Key_Equal"):
            self.sky_view.zoom(WHEEL_STEP)
        elif named("Key_PageDown", "Key_Minus"):
            self.sky_view.zoom(1.0 / WHEEL_STEP)
        else:
            return False
        return True

    def leaveEvent(self, event):
        self.hovered.emit(-1.0, -1.0)
        super().leaveEvent(event)

    def wheelEvent(self, event):
        if self.shot is not None:
            return
        self._fit_camera()
        notches = event.angleDelta().y() / 120.0
        if notches and self.sky_view is not None:
            self.sky_view.zoom(WHEEL_STEP ** notches)
            self.sync_sky_pose()
            self.update()
            return
        if notches:
            px, py = self._pixel(event)
            self.navigator.wheel(px, py, WHEEL_STEP ** notches,
                                 time.monotonic())
            self.update()

    # OpenGL

    def initializeGL(self):
        self._take_outside_errors()
        ctx = self.context()
        fmt = ctx.format()
        self.gl_info = {
            "version": (fmt.majorVersion(), fmt.minorVersion()),
            "profile": fmt.profile(),
            "renderer": GL.glGetString(GL.GL_RENDERER).decode(),
            "gl": GL.glGetString(GL.GL_VERSION).decode(),
        }
        journal.note("OpenGL {}, {}".format(self.gl_info["gl"],
                                            self.gl_info["renderer"]))
        if self.gl_info["version"] < (3, 3):
            self.error = self.gl_info["gl"]
            return
        # Горячие вызовы кадра не отпускают GIL, см. gpu.hold_gil.
        self.hold_gil = gpu.hold_gil(ctx)
        self.program = gpu.build_program(TILE_VERTEX, TILE_FRAGMENT)
        self.u_mvp = GL.glGetUniformLocation(self.program, "u_mvp")
        self.u_texture = GL.glGetUniformLocation(self.program, "u_texture")
        # Непрозрачность поверхности. Значение по умолчанию в GLSL - 0,
        # а альфа кадра видна окну Qt, поэтому 1 ставится сразу.
        self.u_alpha = GL.glGetUniformLocation(self.program, "u_alpha")
        self.u_water = GL.glGetUniformLocation(self.program, "u_water")
        self.u_water_color = GL.glGetUniformLocation(self.program,
                                                     "u_water_color")
        self.u_shallow = GL.glGetUniformLocation(self.program, "u_shallow")
        self.u_wedge_on = GL.glGetUniformLocation(self.program,
                                                  "u_wedge_on")
        self.u_wedge = GL.glGetUniformLocation(self.program, "u_wedge")
        self.u_plain = GL.glGetUniformLocation(self.program, "u_plain")
        self.u_swipe = GL.glGetUniformLocation(self.program, "u_swipe")
        self.u_wedge_lat = GL.glGetUniformLocation(self.program,
                                                   "u_wedge_lat")
        GL.glUseProgram(self.program)
        GL.glUniform1f(self.u_alpha, 1.0)
        GL.glUniform1f(self.u_water, 0.0)
        GL.glUseProgram(0)
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
        # Слой GIBS: (блок, место текстуры, место окна) в шейдере.
        self.gibs_slots = {
            name: (GL.GL_TEXTURE0 + unit,
                   GL.glGetUniformLocation(self.program, sampler),
                   GL.glGetUniformLocation(self.program, uv))
            for name, _, unit, sampler, uv in GIBS_LAYERS}
        self.hole_program = gpu.build_program(HOLE_VERTEX, HOLE_FRAGMENT)
        self.hole_uniforms = uniforms(self.hole_program, (
            "u_rotation", "u_tan", "u_viewport", "u_eye", "u_axes", "u_qc"))
        # Профиль Core требует привязанный массив вершин и там, где
        # вершины берутся из gl_VertexID.
        self.empty_vao = GL.glGenVertexArrays(1)
        # glGenQueries(1) в PyOpenGL отдаёт массив, а не число.
        self.hole_query = int(np.ravel(GL.glGenQueries(1))[0])
        self.labels.init_gl()
        self.features.init_gl()
        self.buildings.init_gl()
        self.subsurface.init_gl()
        self.image_walls.init_gl()
        self.photos.init_gl()
        self.cutaway.init_gl()
        self.cutaway_slabs.init_gl()
        self.section_wall.init_gl()
        self.lake_water.init_gl()
        self.extruded.init_gl()
        self.quakes.init_gl()
        self.fires.init_gl()
        self.deposits.init_gl()
        self.satellites.init_gl()
        self.stars.init_gl()
        self.sky.init_gl(self.empty_vao)
        self.constellations.init_gl()
        self.bodies.init_gl()
        self._context = ctx
        ctx.aboutToBeDestroyed.connect(self.release_gl)

    def release_gl(self):
        """Освобождение ресурсов перед уничтожением контекста."""
        if self._context is None:
            return
        self.makeCurrent()
        self._end_shot()
        self.labels.release_gl()
        self.features.release_gl()
        self.buildings.release_gl()
        self.subsurface.release_gl()
        self.image_walls.release_gl()
        self.photos.release_gl()
        self.cutaway.release_gl()
        self.cutaway_slabs.release_gl()
        self.section_wall.release_gl()
        self.lake_water.release_gl()
        self.extruded.release_gl()
        self.quakes.release_gl()
        self.fires.release_gl()
        self.deposits.release_gl()
        self.satellites.release_gl()
        self.stars.release_gl()
        self.sky.release_gl()
        self.constellations.release_gl()
        self.bodies.release_gl()
        self.build_pool.clear()
        self.build_pool.waitForDone(2000)
        for mesh in (list(self.meshes.values()) + self.caps
                     + list(self.underlay_meshes.values())):
            mesh.delete()
        for texture in (list(self.textures.values())
                        + [t for layer in self.gibs.values()
                           for t in layer.textures.values()]):
            gpu.delete_texture(texture)
        for layer in self.gibs.values():
            layer.textures.clear()
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

    def _upload(self, budget, time_limit=UPLOAD_TIME):
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
                    and time.perf_counter() - started > time_limit:
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

    def _upload_overlays(self, count=OVERLAY_UPLOADS,
                         time_limit=UPLOAD_TIME):
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
        for n, key in enumerate(order[:count]):
            if n and time.perf_counter() - started > time_limit:
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
        self._overlay_missing = len(wanted)
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
        if self.terrain_loader is None:
            return
        if not self.store.scale and not self.tool_heights:
            return
        # Чаще LOADER_PERIOD загрузчик не зовётся, набор между вызовами
        # не нужен. Сбор набора стоил около 0.5 мс на кадр.
        if now - self._terrain_at <= LOADER_PERIOD:
            return
        wanted = self._height_needs(sel) if self.store.scale else {}
        self.tool_heights = {key: priority for key, priority
                             in self.tool_heights.items()
                             if key not in self.store.tiles}
        for key, priority in self.tool_heights.items():
            wanted.setdefault(key, priority)
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

    def _height_needs(self, sel):
        """Недостающие тайлы высот кадра и их приоритет.

        Высоты нужны и тайлам, которые подложка ждёт. Иначе у самой
        земли рисуется грубый предок, ему хватает грубых высот,
        и точные не просит никто.
        """
        wanted = {}
        for key in list(sel.draw) + list(sel.want):
            height_key = self.store.wanted(key)
            if height_key not in self.store.tiles:
                wanted[height_key] = max(wanted.get(height_key, 0.0),
                                         sel.want.get(key, 1.0))
        return wanted

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
        if self.shot is not None:
            self._paint_preview()
            return
        self._fit_camera()
        self._render(self.devicePixelRatioF())

    def _take_outside_errors(self):
        """Забрать ошибки OpenGL, оставленные до кадра чужим кодом.

        Функции PyOpenGL проверяют ошибку после вызова и поднимают любую
        накопленную, даже чужую. Без указателей gpu.hold_gil первым таким
        вызовом кадра был glClearColor, и кадр обрывался на ошибке 1280
        до рисования. Так было в QGIS 4.0.2 у пользователя, 28 сентября
        2026 года.
        """
        for code in gpu.frame_errors():
            self.outside_errors[code] += 1

    def _render(self, ratio, shot=False):
        """Кадр в текущий буфер кадра размером камеры.

        ratio - пикселей кадра на логический пиксель, от него размер
        надписей и толщина линий. shot - кадр снимка: загрузка больше,
        сам вид кадры не заказывает. Возвращает количество тайлов,
        картинок и надписей, которых кадр ещё ждёт, или None, если
        рисовать нечего.
        """
        started = time.perf_counter()
        # Процессорное время потока. Разница с общим временем кадра -
        # ожидание GIL или драйвера, по ней видно, считает поток или ждёт.
        cpu_started = time.thread_time()
        self.frame += 1
        # Время шага навигатора видно снаружи, по нему проверочные
        # скрипты считают скорость перелёта.
        self.step_time = time.monotonic()
        moving = self.navigator.step(self.step_time)
        self._take_outside_errors()
        gpu.reset_state()
        gpu.gl.glClearColor(*(HOLE if self.show_holes else SPACE), 1.0)
        gpu.gl.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        self.drawn = 0
        if self.sky_view is not None and self.program is not None:
            return self._render_sky(ratio, started, moving)
        if self.program is None or not self.ready():
            return None
        # До первого полного кадра уровни 0-2 грузятся в видеокарту все
        # сразу, на них держится подстилка. Дальше - не больше
        # UPLOADS_PER_FRAME за кадр.
        missing = any(key not in self.textures for key in START_KEYS)
        budget = len(self.pending) if missing else UPLOADS_PER_FRAME
        marks = [time.perf_counter()]
        # Камера движется: перелёт, тур, инерция, колесо, перетаскивание
        # или поворот. Тогда кадр грузит одну текстуру и одну картинку
        # слоя, загрузчики запускают запросы реже. Движение важнее
        # загрузки.
        motion = moving or self.navigator.grab is not None \
            or self.turning is not None
        if self.on_motion is not None:
            self.on_motion(motion and not shot)
        if shot:
            self._upload(max(budget, SHOT_UPLOADS), SHOT_UPLOAD_TIME)
            self._upload_overlays(SHOT_OVERLAY_UPLOADS, SHOT_UPLOAD_TIME)
        elif motion and not missing:
            self._upload(1, 0.0)
            self._upload_overlays(1, 0.0)
        else:
            self._upload(max(budget, UPLOADS_PER_FRAME))
            self._upload_overlays()
        self._swap_built()
        marks.append(time.perf_counter())

        # Рельеф под глазом: от него ближняя плоскость и зазор камеры.
        if self.navigator.keep_clear():
            moving = True
        # Опрос высот вокруг глаза стоит до 1 мс. Он повторяется, только
        # если глаз сдвинулся или пришли новые высоты.
        probe = (tuple(self.camera.eye), self.store.version, id(self.floor))
        if probe != self._nearest_probe:
            self._nearest_probe = probe
            self._terrain_nearest = nearest_terrain(self.camera.eye,
                                                    self.terrain_at)
        self.camera.nearest = self._terrain_nearest
        # Плоскость фото ближе рельефа: ближняя плоскость отсечения
        # не срезает её, когда глаз стоит в камере фото.
        photo = self.photos.nearest(self.camera.eye)
        if photo is not None:
            self.camera.nearest = photo if self.camera.nearest is None \
                else min(self.camera.nearest, photo)
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
        # Подземное - до поверхности: прозрачная поверхность ложится
        # поверх смешиванием, непрозрачная закрывает проверкой глубины.
        self.subsurface.prepare()
        underground = (self.subsurface.active
                       or self.image_walls.active) and not self.show_holes
        if underground:
            self.subsurface.draw(self.camera)
            self.image_walls.draw(self.camera)
        if self.photos.active and not self.show_holes:
            self.photos.draw(self.camera)
        self.extruded.prepare()
        if self.extruded.active and not self.show_holes:
            self.extruded.draw(self.camera)
        else:
            self.extruded.drawn = 0
        wedge = self.wedge if not self.show_holes else None
        if wedge is not None:
            self._follow_wedge_gain()
            self.cutaway.draw(self.camera)
            self.cutaway_slabs.draw(self.camera)
        else:
            # Убранная сетка граней уходит из видеокарты.
            self.cutaway.prepare()
            self.cutaway_slabs.prepare()
            self.cutaway.drawn = 0
            self.cutaway_slabs.drawn = 0
        gpu.gl.glUseProgram(self.program)
        gpu.gl.glUniform1f(self.u_wedge_on, 0.0 if wedge is None else 1.0)
        gpu.gl.glUniform1f(self.u_plain, 1.0 if self.plain_base else 0.0)
        swipe = self.swipe if self.gibs["compare"].shown else None
        gpu.gl.glUniform1f(self.u_swipe, -1.0 if swipe is None else swipe)
        if wedge is not None:
            cx, cy, cos_half, sin_s, sin_n = cutaway.uniform(wedge)
            gpu.gl.glUniform4f(self.u_wedge, cx, cy, cos_half, 0.0)
            GL.glUniform2f(self.u_wedge_lat, sin_s, sin_n)
        gpu.gl.glUniform1i(self.u_texture, 0)
        gpu.gl.glUniform1i(self.u_overlay, 1)
        for unit, sampler, _ in self.gibs_slots.values():
            gpu.gl.glUniform1i(sampler, unit - GL.GL_TEXTURE0)
        self._clear_overlay()
        self._clear_gibs()
        # Под землёй воздуха нет: глаз ниже рельефа - атмосфера
        # и небо не рисуются.
        air = self.atmosphere and not self.show_holes \
            and not self.eye_underground()
        air_uniforms(self.tile_air, self.camera, air, self.sun,
                     self.air_tint)
        alpha = self.surface_alpha if underground else 1.0
        gpu.gl.glUniform1f(self.u_alpha, alpha)

        items = list(zip(self.caps, self.cap_textures or [self.ocean] * 2))
        items += [(self.meshes[key], self.textures[key]) for key in sel.draw]
        surface = len(items)
        scales = [1.0] * surface
        # Подстилка закрыла бы подземное сквозь прозрачную поверхность
        # и вырез блока.
        cut = self.gibs["cut"].shown
        under = [] if (underground and (alpha < 1.0 or cut)) \
            else self._underlay_items(sel.keep)
        items += under
        # Подстилка ниже самой низкой высоты тела: впадины Марса и Луны
        # уходят ниже эллипсоида, и подстилка на 3 км закрывала их
        # размытым снимком уровня 2.
        depth = UNDERLAY_DEPTH + self.store.depth()
        scales += [1.0 - depth / ellipsoid.A] * len(under)
        mvps = self.camera.tiles_mvp([mesh.center for mesh, _ in items],
                                     scales=scales)
        overlays = None
        if self.overlay is not None and not self.show_holes:
            overlays = [(self.clear_texture, gpu.NO_OVERLAY)] * len(self.caps)
            overlays += self._overlay_items(sel, time.monotonic())
        else:
            self._overlay_missing = 0
        layers = []
        if overlays is not None:
            layers.append((GL.GL_TEXTURE1, self.u_overlay_uv, overlays))
        clear = [(self.clear_texture, gpu.NO_OVERLAY)] * len(self.caps)
        for name, layer in self.gibs.items():
            if layer.dropping:
                # Контекст OpenGL здесь текущий, это вызов из paintGL.
                layer.drop(self.pool)
            if layer.shown and not self.show_holes:
                layer.upload(self.pool, self.frame)
                unit, _, u_uv = self.gibs_slots[name]
                layers.append((unit, u_uv, clear + layer.items(
                    sel.draw, self.clear_texture, self.frame)))
            else:
                layer.missing = 0
        if alpha < 1.0:
            # Прозрачная поверхность в два прохода. Первый пишет только
            # глубину, второй смешивает цвет там, где глубина та же. Так
            # на пиксель приходится один слой поверхности, а юбки тайлов
            # под ней не просвечивают полосами.
            GL.glColorMask(GL.GL_FALSE, GL.GL_FALSE, GL.GL_FALSE,
                           GL.GL_FALSE)
            gpu.draw_batch(items[:surface], mvps[:surface], self.u_mvp,
                           layers)
            GL.glColorMask(GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE, GL.GL_TRUE)
            GL.glDepthFunc(GL.GL_LEQUAL)
            GL.glDepthMask(GL.GL_FALSE)
            gpu.gl.glEnable(GL.GL_BLEND)
            GL.glBlendFuncSeparate(
                GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA, GL.GL_ZERO,
                GL.GL_ONE)
        gpu.draw_batch(items[:surface], mvps[:surface], self.u_mvp, layers)
        if alpha < 1.0:
            gpu.gl.glDisable(GL.GL_BLEND)
            GL.glDepthMask(GL.GL_TRUE)
            GL.glDepthFunc(GL.GL_LESS)
        if layers:
            # Подстилка идёт без наложения и слоёв GIBS.
            self._clear_overlay()
            self._clear_gibs()
        if self.hole_check:
            # До подстилки: щели между тайлами. После: видимые дыры.
            gaps = self._count_holes()
            GL.glUseProgram(self.program)
        gpu.draw_batch(items[surface:], mvps[surface:], self.u_mvp)
        if alpha < 1.0:
            gpu.gl.glUniform1f(self.u_alpha, 1.0)
        if self.sea_floor and self.store.scale and not self.show_holes:
            self._draw_water(items[len(self.caps):surface],
                             mvps[len(self.caps):surface])
        if self.hole_check:
            holes = self._count_holes()
            GL.glUseProgram(self.program)
            self.hole_counts.append((self.frame, gaps, holes))
        buildings_busy = False
        if self.buildings.shown and not self.show_holes:
            # До неба: небо рисуется там, где глубина осталась 1.0.
            buildings_busy = self.buildings.update(
                self.camera, self.store, time.monotonic())
            self.buildings.upload(BUILDING_SHOT_UPLOADS if shot
                                  else 1 if motion else 2)
            self.buildings.draw(self.camera, self.sun)
        if air:
            self._draw_sky()
        if self.show_stars and not self.show_holes:
            self.sky.draw(self.camera)
            self.stars.draw(self.camera, ratio)
        else:
            self.stars.drawn = 0
            self.sky.drawn = False
        features_busy = False
        if self.features.shapes and not self.show_holes:
            features_busy = self.features.draw(
                self.camera, self.store.heights_at if self.store.scale
                else None, self.store.version, ratio,
                still=shot or not motion)
        self.lake_water.prepare()
        if self.lake_water.active and not self.show_holes:
            self.lake_water.draw(self.camera)
        else:
            self.lake_water.drawn = 0
        self.section_wall.prepare()
        if self.section_wall.active and not self.show_holes:
            self.section_wall.draw(self.camera)
        else:
            self.section_wall.drawn = 0
        if self.deposits.data is not None and not self.show_holes:
            self.deposits.draw(self.camera, ratio)
        else:
            self.deposits.drawn = 0
        if self.fires.fires is not None and not self.show_holes:
            self.fires.draw(self.camera, ratio)
        else:
            self.fires.drawn = 0
        if self.quakes.events and not self.show_holes:
            self.quakes.draw(self.camera, ratio)
        else:
            self.quakes.drawn = 0
        if self.satellites.source is not None and not self.show_holes:
            self.satellites.draw(self.camera, ratio)
        else:
            self.satellites.drawn = 0
        if (self.label_kinds or self.search_mark is not None
                or self.tool_marks or self.subsurface_marks
                or self.features.shapes) \
                and not self.show_holes:
            self._draw_labels(sel, ratio)
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
        for layer in self.gibs.values():
            layer.evict(self.pool, self.frame)
        # Неподвижность проверяется по самой камере: её двигает не только
        # навигатор, но и проверочные скрипты.
        pose = (tuple(self.camera.eye), tuple(self.camera.rotation.ravel()))
        still = pose == self._last_pose
        self._last_pose = pose
        refill = still and not moving and len(self.pool.free) < POOL_TARGET
        if refill:
            # Кадр без движения пополняет запас текстур понемногу.
            self.pool.allocate(POOL_REFILL)
        if shot:
            pass  # кадры снимка идут по таймеру
        elif moving or refill or self.built or self._drop_overlays \
                or features_busy or buildings_busy \
                or self.labels.pending or (
                self.pending and any(k in sel.keep for k in self.pending)) \
                or (self.overlay_pending and any(
                    k in sel.keep for k in self.overlay_pending)) \
                or any(layer.shown and (layer.pending or layer.unasked)
                       for layer in self.gibs.values()):
            self.update()
        marks.append(time.perf_counter())
        self.paint_span = (started, marks[-1])
        self.frame_times.append(marks[-1] - started)
        spans = [b - a for a, b in zip(marks, marks[1:])]
        self.sections.append(dict(zip(SECTIONS, spans),
                                  draws=self.draw_calls,
                                  cpu=time.thread_time() - cpu_started))
        self.changed.emit()
        # Снимок ждёт и свои объекты: запись тура меняет треки к кадру.
        return self._missing(sel) + int(bool(features_busy)) if shot else 0

    def sky_frame_camera(self):
        """Камера неба под размер кадра и взгляд SkyView."""
        cam = self.sky_camera
        cam.width, cam.height = self.camera.width, self.camera.height
        cam.fov_y = self.sky_view.fov
        cam.rotation = self.sky_view.rotation()
        return cam

    def sync_sky_pose(self):
        """Поза навигатора по взгляду на небо. Её зовут после мыши
        и клавиш: перелёт и тур начинаются с того, что на экране."""
        lat, lon, distance = pose_of(self.sky_view)
        self.navigator.stop()
        self.navigator.set_pose(Pose(lat, lon, distance, 0.0, 0.0))

    def fly_sky(self, ra, dec, fov):
        """Перелёт взгляда на небе к точке ra, dec с полем fov."""
        fov = max(FOV_MIN, min(FOV_MAX, fov))
        lon = ra - 360.0 if ra > 180.0 else ra
        self.sync_sky_pose()
        self.fly_pose(dec, lon, distance_for(fov), 0.0, 0.0)

    def _render_sky(self, ratio, started, moving=False):
        """Кадр вида неба: Млечный путь, линии созвездий, звёзды
        и светила. Тайлов, воздуха и своих объектов в нём нет, камера
        стоит в центре небесной сферы. Пока идёт перелёт или тур,
        взгляд берётся из позы навигатора, core.skyview.pose_of."""
        # На последнем шаге перелёта навигатор ставит конечную позу
        # и сообщает, что движения больше нет. Взгляд переносится
        # и в этом кадре, иначе он вставал чуть не доходя до цели:
        # 4 октября 2026 года у Сириуса на 0.09° и с полем 12.8° вместо
        # 12°.
        if moving or self._sky_moved:
            pose = self.navigator.pose
            follow_pose(self.sky_view, pose.lat, pose.lon, pose.distance)
        self._sky_moved = moving
        cam = self.sky_frame_camera()
        frame = np.eye(3)
        gpu.gl.glEnable(GL.GL_DEPTH_TEST)
        self.sky.draw(cam, frame=frame, share=1.0)
        if self.show_constellations:
            self.constellations.draw(cam, frame)
        else:
            self.constellations.drawn = 0
        self.stars.draw(cam, ratio, frame=frame, share=1.0)
        moment = self.sky_time if self.sky_time is not None \
            else time.time()
        if self._bodies_time is None or abs(moment - self._bodies_time) > 30:
            self.bodies.set_points(skydata.body_points(moment))
            self._bodies_time = moment
        self.bodies.draw(cam, ratio, frame=frame, share=1.0)
        gpu.gl.glBindVertexArray(0)
        gpu.gl.glUseProgram(0)
        for code in gpu.frame_errors():
            self.gl_errors[code] += 1
        self.labels.count = 0
        self.frame_times.append(time.perf_counter() - started)
        self.changed.emit()
        if moving:
            self.update()
        return 0

    def _missing(self, sel):
        """Сколько тайлов, картинок и надписей кадр ещё ждёт."""
        keep = sel.keep
        count = len(sel.want) + len(self.built) + len(self.building)
        count += sum(1 for k in self.pending if k in keep)
        count += len(self.stale & keep)
        if self.overlay is not None:
            count += self._overlay_missing
            count += sum(1 for k in self.overlay_pending if k in keep)
        if self.terrain_loader is not None and self.store.scale:
            count += len(self._height_needs(sel))
        if self.place_loader is not None and self.label_kinds:
            count += sum(1 for k in self.places.wanted(sel.draw)
                         if k not in self.places.tiles)
        if self.labels.pending:
            count += 1
        for layer in self.gibs.values():
            if layer.shown:
                count += layer.missing + len(layer.pending)
        return count + self.buildings.missing()

    # Снимок вида

    def start_shot(self, width, height, ratio):
        """Начать снимок вида размером width × height пикселей.

        Камера останавливается, мышь её не двигает. Кадры снимка идут
        по таймеру в невидимый буфер, пока всё нужное не загрузится.
        Готовый снимок приходит сигналом shot_done. Окно тем временем
        показывает снимок, вписанный в себя.
        """
        if self._context is None or self.program is None:
            return False
        self._end_shot()
        self.navigator.stop()
        self.shot = _Shot(int(width), int(height), float(ratio))
        self._shot_timer.start(SHOT_PERIOD)
        return True

    def finish_shot(self):
        """Снять сейчас, не дожидаясь загрузки."""
        if self.shot is not None:
            self.shot.force = True

    def cancel_shot(self):
        """Бросить снимок без результата."""
        if self.shot is not None:
            self.makeCurrent()
            self._end_shot()
            self.doneCurrent()
            self.update()

    def _end_shot(self):
        """Освободить буфер снимка. Только при текущем контексте."""
        self._shot_timer.stop()
        shot, self.shot = self.shot, None
        if shot is not None and shot.fbo is not None:
            GL.glDeleteFramebuffers(1, [shot.fbo])
            GL.glDeleteRenderbuffers(2, shot.buffers)

    def _shot_buffer(self, shot):
        """Буфер кадра снимка: цвет RGBA8 и глубина 24 бита."""
        shot.fbo = int(np.ravel(GL.glGenFramebuffers(1))[0])
        shot.buffers = [int(b) for b in np.ravel(GL.glGenRenderbuffers(2))]
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, shot.fbo)
        for buffer, fmt, attach in (
                (shot.buffers[0], GL.GL_RGBA8, GL.GL_COLOR_ATTACHMENT0),
                (shot.buffers[1], GL.GL_DEPTH_COMPONENT24,
                 GL.GL_DEPTH_ATTACHMENT)):
            GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, buffer)
            GL.glRenderbufferStorage(GL.GL_RENDERBUFFER, fmt, shot.width,
                                     shot.height)
            GL.glFramebufferRenderbuffer(GL.GL_FRAMEBUFFER, attach,
                                         GL.GL_RENDERBUFFER, buffer)
        GL.glBindRenderbuffer(GL.GL_RENDERBUFFER, 0)
        return GL.glCheckFramebufferStatus(GL.GL_FRAMEBUFFER) \
            == GL.GL_FRAMEBUFFER_COMPLETE

    def _shot_frame(self):
        """Кадр снимка по таймеру. Готовый снимок уходит сигналом."""
        shot = self.shot
        if shot is None or self._context is None:
            self._shot_timer.stop()
            return
        self.makeCurrent()
        try:
            if shot.fbo is None and not self._shot_buffer(shot):
                self._end_shot()
                self.shot_done.emit(None, False)
                return
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, shot.fbo)
            GL.glViewport(0, 0, shot.width, shot.height)
            self.camera.width = shot.width
            self.camera.height = shot.height
            missing = self._render(shot.ratio, shot=True)
            if missing is None:
                missing = 1
            shot.calm = shot.calm + 1 if missing == 0 else 0
            if shot.calm >= SHOT_SETTLE or shot.force:
                image = self._read_shot(shot)
                complete = missing == 0
                self._end_shot()
                self.shot_done.emit(image, complete)
            else:
                self.shot_progress.emit(missing)
        finally:
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,
                                 self.defaultFramebufferObject())
            self.doneCurrent()
        self.update()

    def _read_shot(self, shot):
        """Пиксели буфера снимка в QImage, строки сверху вниз."""
        GL.glPixelStorei(GL.GL_PACK_ALIGNMENT, 1)
        data = GL.glReadPixels(0, 0, shot.width, shot.height, GL.GL_RGBA,
                               GL.GL_UNSIGNED_BYTE)
        rgba = np.frombuffer(data, dtype=np.uint8).reshape(
            shot.height, shot.width, 4)[::-1].copy()
        rgba[..., 3] = 255
        image = QImage(rgba.data, shot.width, shot.height, 4 * shot.width,
                       enum(QImage, "Format", "Format_RGBA8888"))
        return image.copy()

    def _paint_preview(self):
        """Окно во время снимка: снимок, вписанный в окно."""
        shot = self.shot
        ratio = self.devicePixelRatioF()
        width = max(1, int(round(self.width() * ratio)))
        height = max(1, int(round(self.height() * ratio)))
        self._take_outside_errors()
        gpu.reset_state()
        GL.glClearColor(*PREVIEW_COLOR, 1.0)
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if shot.fbo is None:
            return
        x0, y0, x1, y1 = letterbox(shot.width, shot.height, width, height)
        GL.glBindFramebuffer(GL.GL_READ_FRAMEBUFFER, shot.fbo)
        GL.glBindFramebuffer(GL.GL_DRAW_FRAMEBUFFER,
                             self.defaultFramebufferObject())
        GL.glBlitFramebuffer(0, 0, shot.width, shot.height, x0, y0, x1, y1,
                             GL.GL_COLOR_BUFFER_BIT, GL.GL_LINEAR)
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER,
                             self.defaultFramebufferObject())

    def _clear_gibs(self):
        """Прозрачные слои GIBS на своих блоках, окна без сдвига."""
        for unit, _, u_uv in self.gibs_slots.values():
            gpu.gl.glActiveTexture(unit)
            gpu.gl.glBindTexture(GL.GL_TEXTURE_2D, self.clear_texture)
            gpu.gl.glUniform4f(u_uv, *gpu.NO_OVERLAY, 0.0)
        gpu.gl.glActiveTexture(GL.GL_TEXTURE0)

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
        eye = ray_uniforms(u, self.camera, ellipsoid.A - HOLE_MARGIN,
                           ellipsoid.B - HOLE_MARGIN)
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

    def set_gibs(self, name, on, loader=None, keep=False):
        """Показать слой GIBS с загрузчиком loader или скрыть его.
        Прежние картинки освобождаются в следующем кадре. keep - они
        рисуются, пока новый загрузчик не пришлёт замену: маска выреза
        после пересборки модели не мигает непрозрачной поверхностью."""
        layer = self.gibs[name]
        layer.shown = bool(on)
        layer.loader = loader
        if keep and on:
            layer.stale = set(layer.textures)
            layer.wanted = frozenset()
        else:
            layer.dropping = True
        self.update()

    def add_gibs(self, name, key, levels):
        """Пришла картинка тайла слоя GIBS."""
        self.gibs[name].add(key, levels)
        self.last_arrival = time.monotonic()
        self.update()

    def set_buildings(self, on, loader=None):
        """Показать 3D-здания с загрузчиком loader или скрыть их."""
        self.buildings.set_shown(on, loader)
        self.update()

    def add_buildings(self, key, footprint):
        """Пришёл разобранный тайл зданий."""
        self.buildings.add(key, footprint)
        self.last_arrival = time.monotonic()
        self.update()

    def set_stars(self, on):
        """Показать или скрыть звёзды."""
        self.show_stars = bool(on)
        self.update()

    def set_sky_image(self, rgba):
        """Пришла картинка неба с Млечным путём."""
        self.sky.set_image(rgba)
        self.update()

    def _draw_sky(self):
        """Небо и гало там, где нет тайлов.

        Полноэкранный треугольник на глубине 1.0, как у счётчика дыр,
        проверка глубины оставляет только пиксели без тайлов. Дымка
        над самими тайлами считается в шейдере тайла.
        """
        gl = gpu.gl
        gl.glUseProgram(self.sky_program)
        u = self.sky_air
        eye = air_uniforms(u, self.camera, True, self.sun, self.air_tint)
        gl.glUniform1f(u["u_qc"], float(eye @ eye) - 1.0)
        gl.glDepthFunc(GL.GL_LEQUAL)
        gl.glDepthMask(GL.GL_FALSE)
        gl.glBindVertexArray(self.empty_vao)
        gl.glDrawArrays(GL.GL_TRIANGLES, 0, 3)
        gl.glDepthMask(GL.GL_TRUE)
        gl.glDepthFunc(GL.GL_LESS)

    def _draw_labels(self, sel, ratio):
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
        # На гладкой основе нынешних городов и стран нет.
        kinds = set() if self.plain_base \
            else kinds_at(self.label_kinds, self.camera.altitude())
        places = self.places.collect(sel.draw, kinds)
        mark = self.search_mark
        own = self._own_marks() + self.layer_marks + self.grid_marks \
            + self.plate_marks + self.value_marks \
            + self.subsurface_marks \
            + self.tool_marks
        if mark is not None or own:
            head = ([mark] if mark is not None else []) + own
            if self._marked[0] is not places or self._marked[1] != head:
                self._marked = (places, head, head + places)
            places = self._marked[2]
        if self.wedge is not None and places:
            # Пункты вынутого сектора висели бы над его гранями.
            if self._wedged[0] is not places \
                    or self._wedged[1] != self.wedge:
                out = cutaway.inside(self.wedge,
                                     [p.lat for p in places],
                                     [p.lon for p in places])
                self._wedged = (places, self.wedge,
                                [p for p, gone in zip(places, out)
                                 if not gone])
            places = self._wedged[2]
        height_at = self.label_height if self.store.scale else None
        self.labels.draw(self.camera, self.camera.projection(), places,
                         height_at, self.store.version, ratio)

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
