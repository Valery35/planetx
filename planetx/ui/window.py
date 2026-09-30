# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно глобуса по образцу 3D-сцены Isoliner3D.

Слева панель: координаты, список источников и слоёв, строка состояния
(ui/panel.py). Справа вид OpenGL, в его левом верхнем углу плавающая
панель значков (ui/toolbar.py), в правом нижнем подпись источников.
Окно связывает части и решает, панели только показывают.
"""
import html
import math
import os
import sys
import time

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsProject, QgsSettings)
from qgis.PyQt.QtCore import QEvent, QMimeData, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import (QApplication, QFileDialog, QInputDialog,
                                 QLabel, QMessageBox, QSplitter,
                                 QVBoxLayout, QWidget)
from qgis.utils import iface

from ..core import (basemap, clouds, ellipsoid, lookat, stars, sun,
                    temperature, when)
from ..core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ..core.measure import (LENGTH_UNITS, convert, nearest_vertex,
                            number, segment_midpoints)
from ..core import graticule
from ..core.features import Shape, has_alts
from ..core.coords import FORMATS as COORD_FORMATS, parse_point
from ..core.flight import Flight, fit_view
from ..core.geocode import (SEARCH_INTERVAL, normalize, parse_places,
                            place_text, search_url)
from ..core.mipmap import mip_chain
from ..core.navigation import Pose, focal, ground_under
from ..core.planets import EARTH_PLANET, planet_by_key
from ..core.skyview import SkyView, ra_dec_text
from ..core.sync import BOTH, DIRECTIONS
from ..core.terrain import MAX_LEVEL as TERRAIN_MAX, make_tile
from ..core.kml import KmlError, read_file as read_kml_file, read_kml, \
    write_kml, write_kmz
from ..core.placetree import is_folder, numbered_name
from ..core.scene import EXTENSION, SceneError, read_scene, write_scene
from ..core.tour import PathStop, RecordedStop, Stop, clock, thin
from ..core.tiling import tile_mesh
from ..core.buildings import EMPTY as NO_BUILDINGS, footprints
from ..core.places import (AS_QGIS, LABEL_LANGUAGES, LOCAL, DecodeError,
                           decode_places, name_languages)
from ..core.places import Place as MarkPlace  # метка найденного места
from ..i18n import tr, ui_language
from ..net.loader import TERRARIUM_URL, TileLoader, set_moving
from ..net.overlay import (BORDERS, LINE_GROUPS, OPENFREEMAP_ATTRIBUTION,
                           PLACES,
                           RAIL_FROM, RAILWAYS, VECTOR_GROUPS, label_kinds,
                           railway_layer,
                           OPENFREEMAP_TILEJSON, LayerOverlay, fetch_json,
                           openfreemap_layer, set_line_groups)
from ..qt_compat import enum
from ..render.view import OBJECT_BUDGET, GlobeView, start_keys
from .about import show_about
from .identify import IdentifyDialog, identify, point_text
from .layer_labels import LayerLabels
from .legend import TemperatureLegend
from .spinner import LoadSpinner
from .draw import PlaceDialog
from .measure import GRAB_PIXELS, Ruler, RulerDialog, unit_short
from .measure import _xy as ruler_xy
from .elevation import HeightSource, ProfileDialog
from .myplaces import MyPlaces
from .panel import LayerPanel
from .project import (AUTO_REFRESH, FOLLOW, ProjectWatch, map_layers,
                      read_flag, read_shown, set_visible_on_map,
                      visible_on_map, write_flag, write_shown)
from .navpad import NavPad
from .skylabels import SkyLabels
from .properties import SCALE_RANGE, PropertiesDialog
from .record import TourRecorder
from .placeprops import PlaceProperties
from .scene import apply as apply_scene, capture as capture_scene
from .snapshot import SnapshotDialog
from .tour import TourPlayer
from .track import TrackDialog, TrackManager
from .sync import MapSync
from .timebar import TimeBar
from .toolbar import ViewToolbar

TERRAIN_ATTRIBUTION = (
    '<a href="https://github.com/tilezen/joerd/blob/master/docs/'
    'attribution.md">Terrain: Mapzen, SRTM, GMTED, ETOPO1 and others</a>')
# Подпись вида неба: Млечный путь, звёзды, созвездия и светила.
SKY_ATTRIBUTION = (
    ("Milky Way: NASA/Goddard SVS, Gaia DR2: ESA/Gaia/DPAC",
     "https://svs.gsfc.nasa.gov/4851"),
    ("Stars: Yale BSC5", ""),
    ("Constellations: d3-celestial © Olaf Frohn",
     "https://github.com/ofrohn/d3-celestial"),
    ("Planets: JPL approximate elements", ""))
XYZ_PREFIX = "connections/xyz/items/"
BASEMAP_KEY = "PlanetX/basemap"  # имя выбранной подложки в настройках
SIDEBAR_KEY = "PlanetX/sidebar"  # видна ли левая панель окна
CONSTELLATIONS_KEY = "PlanetX/constellations"  # линии созвездий на небе
# Включена ли группа линий векторной основы, по группам.
LINES_KEY = "PlanetX/lines/{}"
# Группы панели «Слои», включённые при первом открытии. Решение автора
# от 27 сентября 2026 года, рельеф включён отдельно.
DEFAULT_GROUPS = (BORDERS, PLACES)
RELIEF_KEY = "PlanetX/relief"  # показывать ли рельеф
# Сетка, звёзды, облака: ключ настройки и умолчание. Звёзды включены,
# как в Google Earth, сетка и облака выключены. Решение помощника от
# 29 сентября 2026 года, его утверждает автор. 3D-здания выключены,
# решение автора от 29 сентября 2026 года.
# Солнце выключено, умолчание плана работ после 0.16.0.
EXTRA_DEFAULTS = {"grid": False, "stars": True, "clouds": False,
                  "temperature": False, "buildings": False, "sun": False}
# Строки раздела «Слои», которые есть только у Земли.
EARTH_EXTRAS = ("clouds", "temperature", "buildings", "sun")
SUN_PERIOD = 60000  # мс между пересчётами солнца по часам компьютера
EXTRA_KEY = "PlanetX/show_"  # + ключ строки
GRID_COLOR = (220, 220, 220, 255)
GRID_WIDTH = 1.0
CIRCLE_COLOR = (255, 230, 0, 255)  # экватор, тропики, полярные круги
SCALE_KEY = "PlanetX/relief_scale"  # вертикальный масштаб рельефа
LANGUAGE_KEY = "PlanetX/label_language"  # язык подписей
COORDS_KEY = "PlanetX/coords"  # формат координат
RECORD_PERIOD = 100  # мс между позами записи тура
SYNC_KEY = "PlanetX/sync"  # направление синхронизации с картой
# Тип KML в буфере обмена, как у Google Earth. Рядом кладётся текст.
KML_MIME = "application/vnd.google-earth.kml+xml"
# Допуск щелчка при определении объектов, логических пикселей.
IDENTIFY_PIXELS = 5.0
CURSOR_PERIOD = 60  # мс между пересчётами точки под курсором
SELECTION_DELAY = 300  # мс после смены выделения до перерисовки слоя
NEW_SHOWN_KEY = "PlanetX/new_layers_shown"  # новые слои сразу на глобус
TILE_SIZE = 256
# Интервал переключения GIL, пока открыто окно. Каждый вызов OpenGL
# и PyQt из главного потока отпускает GIL и ждёт его обратно, пока
# рабочий поток выполняет Python, до интервала переключения. При 5 мс
# по умолчанию вращение с загрузкой наложения давало 53 кадра в худшую
# секунду, при 1 мс - 59. Замер 26 сентября 2026 года, qgis_overlay.py.
SWITCH_INTERVAL = 0.001
STATUS_PERIOD = 0.25  # секунд между обновлениями строки состояния
MESSAGE_TIME = 5.0  # секунд, сколько видно сообщение об ошибке ввода
# Расстояние в конце перелёта - текущее, но не больше этого, метров.
# Из космоса перелёт кончается на 2 км, от улицы к улице идёт на месте.
FLIGHT_DISTANCE = 2000.0
# Ближе этого к найденному месту камера не подлетает, метров. У вершины
# охват - точка, и камера вставала в 300 м от неё.
SEARCH_MIN_DISTANCE = 3000.0
# Охват страны вроде России дал бы камеру за Луной.
SEARCH_MAX_DISTANCE = 1.2e7
# Пауза после последней правки слоя до перерисовки наложения, мс.
REFRESH_DELAY = 300
PANEL_WIDTH = 300  # ширина левой панели при открытии, пикселей
MARGIN = 8  # отступ панели значков и подписи от края вида
ATTRIBUTION_STYLE = ("QLabel { background: rgba(255, 255, 255, 190); "
                     "padding: 1px 4px; border-radius: 3px; }")


def imagery_preparer(store):
    """Работа рабочего потока для тайла подложки.

    Сетка вершин с лучшими высотами из store, уровни мипмапов, уровень
    высот, с которым собрана сетка, и масштаб рельефа. Хранилище только
    читается, пишет в него главный поток.
    """
    def prepare(key, rgba):
        scale = store.scale
        heights, level = store.for_mesh(key)
        mesh = tile_mesh(*key, heights, exaggeration=scale)
        return mesh, mip_chain(rgba), level, scale
    return prepare


def prepare_clouds(key, rgba):
    """Работа рабочего потока для тайла облаков: прозрачность
    по белизне и уровни мипмапов."""
    return mip_chain(clouds.cloud_rgba(rgba, key))


def prepare_temperature(key, rgba):
    """Работа рабочего потока для тайла температуры: раскраска GIBS
    с непрозрачностью и уровни мипмапов."""
    return mip_chain(temperature.overlay_rgba(rgba))


def gibs_source(name):
    """Источник и подготовка тайла слоя GIBS по имени слоя вида."""
    if name == "clouds":
        return (basemap.Source("NASA GIBS", clouds.url_template(
            time.time()), clouds.MAX_LEVEL, clouds.ATTRIBUTION,
            builtin=True), prepare_clouds)
    layer = temperature.SEA if name == "sea" else temperature.LAND
    return (basemap.Source("NASA GIBS", temperature.url_template(layer),
                           temperature.MAX_LEVEL, temperature.ATTRIBUTION,
                           builtin=True), prepare_temperature)


def xyz_sources():
    """Подложки из подключений XYZ в настройках QGIS."""
    settings = QgsSettings()
    items = {}
    for key in settings.allKeys():
        if key.startswith(XYZ_PREFIX):
            name, _, field = key[len(XYZ_PREFIX):].rpartition("/")
            if name:
                items.setdefault(name, {})[field] = settings.value(key)
    return basemap.from_settings(items)


def attribution_html(source):
    return link_html(*source.attribution)


def link_html(text, link):
    text = html.escape(text)
    if link:
        return '<a href="{}">{}</a>'.format(html.escape(link), text)
    return text


def label_languages(choice=AS_QGIS):
    """Языки названий пунктов по выбору в свойствах вида."""
    return name_languages(choice, ui_language())


def places_decoder(languages):
    """Разбор векторного тайла в рабочем потоке, список пунктов.

    Ошибка разбора даёт None, исключение в рабочем потоке не уходит.
    """
    def decode(key, data):
        try:
            return decode_places(key, data, languages)
        except DecodeError:
            return None
    return decode


def buildings_decoder(key, data):
    """Разбор тайла зданий в рабочем потоке: Footprint или NO_BUILDINGS.

    Ошибка разбора даёт None, исключение в рабочем потоке не уходит.
    """
    try:
        found = footprints(key, data)
    except (DecodeError, ValueError, IndexError):
        return None
    return NO_BUILDINGS if found is None else found


def heights_preparer(key, rgba):
    """Работа рабочего потока для тайла высот Terrarium."""
    return make_tile(*key, rgba)


def distance_text(metres):
    """Расстояние для строки состояния, метры или километры."""
    if metres < 10000.0:
        return tr("{value} м", value="%.0f" % metres)
    return tr("{value} км", value="{:,.0f}".format(metres / 1000.0)
              .replace(",", " "))


class _RulerVertices:
    """Точки линейки, которые тянутся мышью (render/view.py,
    vertex_tool). Точка хватается, если курсор ближе GRAB_PIXELS."""

    def __init__(self, window):
        self.window = window
        self.index = None

    def grab(self, px, py):
        window = self.window
        ruler = window.ruler
        points = ruler.points
        if not points:
            return False
        view = window.view
        lats = np.array([p[0] for p in points])
        lons = np.array([p[1] for p in points])
        if ruler.spatial():
            xyz = window.drawn_points(ruler)
        else:
            xyz = geodetic_to_ecef(lats, lons,
                                   view.store.heights_at(lats, lons))
        pixels, front = view.camera.project(xyz)
        self.index = nearest_vertex(pixels, front, px, py,
                                    GRAB_PIXELS * view.devicePixelRatioF())
        return self.index is not None

    def move(self, px, py):
        window = self.window
        if window.ruler.spatial():
            found = window._surface(px, py)
        else:
            found = window._ground(px, py)
        if found is not None and self.index is not None:
            window.ruler.move(self.index, *found)

    def drop(self):
        self.index = None


class GlobeWindow(QWidget):
    """Отдельное окно поверх главного окна QGIS."""

    closed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent, enum(Qt, "WindowType", "Window"))
        # Закрытое окно уничтожается вместе с контекстом OpenGL
        # и загрузчиком. Пункт меню открывает новое.
        self.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        # Интервал общий для всего Python в QGIS. Прежний возвращается
        # при закрытии окна.
        self._switch_interval = sys.getswitchinterval()
        sys.setswitchinterval(min(self._switch_interval, SWITCH_INTERVAL))
        self.setWindowTitle("PlanetX")
        self.setWindowIcon(QIcon(os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "icon.svg")))
        # Окно открывается на Земле, даже если прежнее закрылось на Марсе:
        # размеры тела общие для модуля.
        self.planet = EARTH_PLANET
        ellipsoid.set_body(EARTH_PLANET.body)

        self.view = GlobeView(self)
        # Подписи неба - раньше панели значков, чтобы лечь под неё.
        self.sky_labels = SkyLabels(self.view)
        self.view.changed.connect(self.sky_labels.sync)
        self.view.show_constellations = QgsSettings().value(
            CONSTELLATIONS_KEY, True, type=bool)
        self._sky_state = None  # взгляд на небо до выхода из него
        # Шкала времени меток, своя, как в Google Earth. Она нужна
        # до первого чтения «Моих меток».
        self.timebar = TimeBar(self.view)
        self._time_range = None
        self.timebar.range_changed.connect(self._time_changed)
        self.view.on_motion = set_moving
        self.view.load_changed.connect(self._show_state)
        self.panel = LayerPanel(self)
        self.place = self.panel.place
        self.status = self.panel.status
        self.toolbar = ViewToolbar(self.view)
        # Экранные органы навигации, как в Google Earth.
        self.navpad = NavPad(self.view)
        self.toolbar.move(MARGIN, MARGIN)
        # Значок загрузки справа от панели значков.
        self.spinner = LoadSpinner(self.view)
        self.view.load_changed.connect(
            lambda: self.spinner.set_state(self.view.load_missing,
                                           self.view.load_stalled))
        self.attribution = QLabel(self.view)
        self.attribution.setOpenExternalLinks(True)
        self.attribution.setStyleSheet(ATTRIBUTION_STYLE)
        # Шкала температуры, видна вместе со строкой «Температура».
        self.legend = TemperatureLegend(self.view)
        self.legend.hide()
        self.view.installEventFilter(self)
        splitter = QSplitter(self)
        self.splitter = splitter
        splitter.addWidget(self.panel)
        splitter.addWidget(self.view)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([PANEL_WIDTH, 1300])
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Первая встроенная подложка, Esri World Imagery, - по умолчанию.
        self.sources = basemap.builtins() + xyz_sources()
        names = [source.name for source in self.sources]
        saved = QgsSettings().value(BASEMAP_KEY, "")
        self.source = self.sources[names.index(saved)
                                   if saved in names else 0]
        self.overlay = None
        self.overlay_error = ""
        self._tilejson = None
        self.ofm_layer = None
        self.rail_layer = None
        self.place_loader = None
        self.gibs_loaders = {}  # слой GIBS вида -> загрузчик, см. _set_gibs
        self.sky_loader = None  # картинка неба, см. _load_sky
        self.buildings_loader = None  # тайлы зданий, см. _set_buildings
        self._ofm_source = None  # тайлы OpenFreeMap после TileJSON
        # Настройки вида делятся на выбранные и действующие. Выбранные
        # показывают свойства вида и список слоёв. Действующие видны
        # на глобусе. Кнопка «Обновить» или автообновление переносят
        # выбранные в действующие.
        settings = QgsSettings()
        self._basemap = self.sources.index(self.source)
        self._groups = {group for group in VECTOR_GROUPS if settings.value(
            LINES_KEY.format(group), group in DEFAULT_GROUPS, type=bool)}
        self._relief = settings.value(RELIEF_KEY, True, type=bool)
        self._scale = min(max(settings.value(SCALE_KEY, 1.0, type=float),
                              SCALE_RANGE[0]), SCALE_RANGE[1])
        language = settings.value(LANGUAGE_KEY, AS_QGIS) or AS_QGIS
        self._language = language if language in LABEL_LANGUAGES \
            or language == LOCAL else AS_QGIS
        # Формат координат, по умолчанию десятичные градусы. Решение
        # помощника от 30 сентября 2026 года, утверждает автор.
        coords = QgsSettings().value(COORDS_KEY, COORD_FORMATS[0])
        self.coords = coords if coords in COORD_FORMATS \
            else COORD_FORMATS[0]
        self._places_source = None
        # Масштаб ставится до первой загрузки, сетки сразу собираются
        # с ним.
        self.view.set_relief(self._relief_target())
        self._applied_groups = None
        self._applied_layers = None
        # Слои проекта изменились с последнего обновления.
        self._layers_stale = False
        self.auto_refresh = read_flag(AUTO_REFRESH, False)
        self.new_shown = settings.value(NEW_SHOWN_KEY, False, type=bool)
        self.follow = False
        self._shown = set()
        self._known = set()
        self._read_shown()
        self.dirty = False
        self.properties = None
        self.message = ("", 0.0)
        self.refresh_timer = QTimer(self)
        self.refresh_timer.setSingleShot(True)
        self.refresh_timer.timeout.connect(self.refresh)

        self.panel.fly_text.connect(self.fly)
        self.panel.place_chosen.connect(self.fly_place)
        self.panel.search_cleared.connect(self.clear_search)
        # Поиск по названию: ответы по ключу (запрос, язык), запрос
        # в работе, время последнего запроса, найденные места.
        self._searched = {}
        self._search_key = None
        self._search_reply = None
        self._search_at = -SEARCH_INTERVAL
        self._found = []
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.timeout.connect(self._send_search)
        self.panel.layer_toggled.connect(self.set_layer_shown)
        self.panel.geo_changed.connect(self.set_line_groups)
        self.panel.relief_toggled.connect(self.set_relief)
        self.panel.fly_to_layer.connect(self.fly_to_layer)
        self.panel.opacity_changed.connect(self.set_layer_opacity)
        self.panel.layer_properties.connect(iface.showLayerProperties)
        self.toolbar.refresh_clicked.connect(self.refresh)
        # Боковая панель прячется значком, как в Google Earth. Состояние
        # помнится между запусками.
        self.toolbar.sidebar_clicked.connect(
            lambda: self.set_sidebar(self.panel.isHidden()))
        self.set_sidebar(QgsSettings().value(SIDEBAR_KEY, True, type=bool))
        self.toolbar.about_clicked.connect(lambda: show_about(self))
        self.toolbar.properties_clicked.connect(self._show_properties)
        self.toolbar.save_view_requested.connect(self.save_view)
        # «Мои метки»: общий файл профиля QGIS, объекты на глобусе.
        self.myplaces = MyPlaces(parent=self)
        # Открытые окна свойств меток и их правки для глобуса по ключу.
        self.previews = {}
        self.prop_dialogs = {}
        self.myplaces.changed.connect(self._places_changed)
        self.panel.places_toggled.connect(self.myplaces.set_visible_many)
        self.panel.folder_expanded.connect(self.myplaces.set_expanded)
        self.panel.place_action.connect(self._place_action)
        self.panel.place_moved.connect(
            lambda key, parent, index: self.myplaces.move(
                key, parent or None, index))
        self.panel.places_moved.connect(
            lambda keys, parent, index: self.myplaces.move_many(
                keys, parent or None, index))
        self.panel.places_action.connect(self._places_action)
        self.ruler = Ruler(self)
        self.ruler.changed.connect(self._refresh_shapes)
        self.ruler.changed.connect(self._ruler_changed)
        self.ruler.heights = self._true_heights
        self.ruler.has_heights = self._has_height_tile
        self.ruler.ask_heights = self.view.want_tool_heights
        self.profile_dialog = None
        self._profile_mark = None
        self.ruler_vertices = _RulerVertices(self)
        self.view.undo_point.connect(self._undo_point)
        self.ruler_dialog = None
        self.toolbar.ruler_clicked.connect(self._open_ruler)
        # Новая метка: тот же механизм точек, своё окно.
        self.drawer = Ruler(self)
        self.drawer.changed.connect(self._refresh_shapes)
        self.place_dialog = None
        self.toolbar.place_clicked.connect(self._open_place)
        # Снимок вида в файл и в макет, по окну на каждое.
        self.shot_dialogs = {}
        self.toolbar.snapshot_clicked.connect(
            lambda: self._open_snapshot(False))
        self.toolbar.layout_clicked.connect(
            lambda: self._open_snapshot(True))
        self.myplaces.load()
        # Тур по отмеченным «Моим меткам».
        self.tour = TourPlayer(self.view, self._tour_stops, self)
        # Запись тура с экрана, как в Google Earth.
        self._recording = None
        self._record_timer = QTimer(self)
        self._record_timer.setInterval(RECORD_PERIOD)
        self._record_timer.timeout.connect(self._record_sample)
        self.toolbar.record_toggled.connect(self._record_toggled)
        self.toolbar.time_toggled.connect(self._time_toggled)
        self.toolbar.constellations.setChecked(
            self.view.show_constellations)
        self.toolbar.constellations_toggled.connect(
            self.set_constellations)
        self.toolbar.body_chosen.connect(self.set_body)
        self._update_timebar()
        self.tour.stop_reached.connect(
            lambda stop: self._show_time(stop.time))
        # Растущие треки точечных слоёв по времени контроллера QGIS.
        self.tracks = TrackManager(self.view, self)
        self.tracks.changed.connect(self._refresh_shapes)
        self.panel.track_requested.connect(self._open_track)
        self.toolbar.scene_save_requested.connect(self.save_scene)
        self.toolbar.scene_open_requested.connect(self.open_scene)
        self.toolbar.demo_requested.connect(self.open_demo)
        self.tour.message.connect(
            lambda text: setattr(self, "message", (text, time.monotonic())))
        # Запись тура кадрами PNG по одной шкале с треками.
        self.recorder = TourRecorder(self, self)
        self.tour.bar.record.connect(self.record_tour)
        self.tour.bar.close_clicked.connect(self.recorder.cancel)
        self.recorder.progress.connect(self.tour.show_recording)
        self.recorder.done.connect(self._recorded)
        # Синхронизация с окном карты QGIS и определение объектов.
        way = QgsSettings().value(SYNC_KEY, BOTH) or BOTH
        self.sync = MapSync(self, iface.mapCanvas())
        self.sync.set_direction(way if way in DIRECTIONS else BOTH)
        self.toolbar.sync_toggled.connect(self.sync.set_enabled)
        self.view.changed.connect(self.sync.globe_frame)
        self.identifying = False
        self.identified = None
        self.toolbar.identify_toggled.connect(self._set_identify)
        self.view.clicked.connect(self._clicked)
        self._hover = None
        self._cursor_text = ""
        self._cursor_timer = QTimer(self)
        self._cursor_timer.setSingleShot(True)
        self._cursor_timer.timeout.connect(self._update_cursor)
        self.view.hovered.connect(self._hovered)

        self.errors = {}
        # Сетка вершин и мипмапы тайла считаются в рабочем потоке
        # загрузчика, главному потоку остаётся передать их в видеокарту.
        self.loader = None
        self._start_loader()
        self.view.max_level = self.source.max_level
        # Высоты Terrarium идут своим загрузчиком, запросы к ним просит
        # вид по тайлам кадра.
        self.terrain_loader = TileLoader(
            basemap.Source("Terrarium", TERRARIUM_URL, TERRAIN_MAX),
            parent=self, prepare=heights_preparer)
        self.terrain_loader.loaded.connect(self._heights)
        self.terrain_errors = {}
        self.terrain_loader.failed.connect(self.terrain_errors.__setitem__)
        self.view.terrain_loader = self.terrain_loader
        if self._relief:
            self.terrain_loader.want((0, 0, 0), 1.0)
        self._shown_at = 0.0
        self.view.changed.connect(self._frame_done)
        # Мелкие уровни важнее: они первыми закрывают весь шар.
        self.loader.want_many((key, -key[0]) for key in start_keys())
        self.watch = ProjectWatch(self)
        self.watch.changed.connect(self._project_changed)
        self.watch.reloaded.connect(self._project_reloaded)
        self.watch.renamed.connect(self._show_layers)
        # Выделение на карте: картинки слоя перерисовываются сразу,
        # без кнопки «Обновить», QGIS рисует выделенное своим цветом.
        self._selection_timer = QTimer(self)
        self._selection_timer.setSingleShot(True)
        self._selection_timer.timeout.connect(self._selection_redraw)
        self.watch.selected.connect(self._selection_changed)
        self.watch.legend.connect(self._legend_changed)
        self._show_layers()
        self.panel.set_geo(self._groups, self._relief)
        settings = QgsSettings()
        self.extras = {key: settings.value(EXTRA_KEY + key, default,
                                           type=bool)
                       for key, default in EXTRA_DEFAULTS.items()}
        self.panel.set_extras(self.extras)
        self.panel.extra_toggled.connect(self.set_extra)
        self.grid_shapes = []
        self._grid_key = None
        self.layer_labels = LayerLabels(self)
        self.layer_labels.changed.connect(self._show_layer_labels)
        self.view.changed.connect(self._update_layer_labels)
        self.view.changed.connect(self._update_grid)
        for key, on in self.extras.items():
            self._apply_extra(key, on)
        self.refresh()

    # Выбранное состояние. Его же меняют проверочные скрипты, на глобус
    # оно переходит по refresh.

    def basemap_index(self):
        return self._basemap

    def line_groups(self):
        """Включённые группы линий векторной основы."""
        return set(self._groups)

    def shown_layers(self):
        """Номера слоёв проекта, отмеченных в списке глобуса."""
        return set(self._shown)

    def relief_on(self):
        return self._relief

    def relief_scale(self):
        return self._scale

    def state(self):
        """Состояние для окна свойств."""
        return {"basemap": self._basemap, "groups": self._groups,
                "relief": self._relief, "scale": self._scale,
                "language": self._language, "sync": self.sync.direction,
                "follow": self.follow, "new_shown": self.new_shown,
                "auto": self.auto_refresh, "coords": self.coords}

    def set_sync_direction(self, way):
        """Кто за кем следует при синхронизации с картой."""
        self.sync.set_direction(way)
        QgsSettings().setValue(SYNC_KEY, way)

    def set_label_language(self, code):
        """Язык подписей, сразу, без кнопки «Обновить».

        Пункты разбираются из векторных тайлов заново, на новом языке.
        Тайлы берутся из кэша QGIS.
        """
        self._language = code
        QgsSettings().setValue(LANGUAGE_KEY, code)
        self._sync_properties()
        if self._places_source is not None:
            self._start_place_loader()

    def choose_basemap(self, index):
        self._basemap = index
        QgsSettings().setValue(BASEMAP_KEY, self.sources[index].name)
        self._changed()

    def set_line_groups(self, groups):
        """Включить группы векторной основы, остальные выключить.

        Как в Google Earth, флажки панели «Слои» срабатывают сразу,
        без кнопки «Обновить». Решение автора от 27 сентября 2026 года.
        """
        self._groups = set(groups) & set(VECTOR_GROUPS)
        settings = QgsSettings()
        for group in VECTOR_GROUPS:
            settings.setValue(LINES_KEY.format(group), group in self._groups)
        self.panel.set_geo(self._groups, self._relief)
        self._apply_vector()

    def set_line_group(self, group, on):
        groups = set(self._groups)
        if on:
            groups.add(group)
        else:
            groups.discard(group)
        self.set_line_groups(groups)

    def set_extra(self, key, on):
        """Сетка, звёзды или облака флажком раздела «Слои», сразу."""
        self.extras[key] = bool(on)
        QgsSettings().setValue(EXTRA_KEY + key, bool(on))
        self.panel.set_extras({key: bool(on)})
        self._apply_extra(key, bool(on))

    def _apply_extra(self, key, on):
        if key in EARTH_EXTRAS and not self.planet.earth:
            # Облака, температура, здания и солнце - земные. Флажок
            # помнится и действует после возврата на Землю.
            on = False
        if key == "grid":
            self._grid_key = None
            self._update_grid()
        elif key == "stars":
            self.view.set_stars(on)
            if on:
                self._load_sky()
        elif key == "clouds":
            self._set_gibs("clouds", on)
        elif key == "temperature":
            self._set_gibs("sea", on)
            self._set_gibs("land", on)
            self.legend.setVisible(on)
            self._place_attribution()
        elif key == "buildings":
            self._set_buildings(on)
        elif key == "sun":
            self._update_sun()

    def sun_time(self):
        """Момент для солнца, секунды UTC: конец промежутка открытой
        шкалы времени, иначе часы компьютера."""
        if self.timebar.shown():
            hi = self.timebar.range()[1]
            if math.isfinite(hi):
                return hi
        return sun.now()

    def _update_sun(self):
        """Направление на солнце в вид. Пока строка «Солнце» включена
        и шкала закрыта, солнце идёт по часам раз в SUN_PERIOD."""
        # Шкала времени бывает раньше строк раздела «Слои».
        on = getattr(self, "extras", {}).get("sun", False) \
            and self.planet.earth
        self.view.sun = sun.direction(self.sun_time()) if on else None
        timer = getattr(self, "sun_timer", None)
        if timer is None:
            timer = self.sun_timer = QTimer(self)
            timer.setInterval(SUN_PERIOD)
            timer.timeout.connect(self._update_sun)
        if on and not self.timebar.shown():
            timer.start()
        else:
            timer.stop()
        self.view.update()

    def _set_buildings(self, on):
        """3D-здания: загрузчик тайлов OpenFreeMap или никакого. Адрес
        тайлов даёт TileJSON, до его прихода здания ждут."""
        old = self.buildings_loader
        if old is not None:
            old.abort()
            old.deleteLater()
        self.buildings_loader = None
        if on and self._ofm_source is not None:
            self.buildings_loader = TileLoader(self._ofm_source, parent=self,
                                               decode=buildings_decoder)
            self.buildings_loader.loaded.connect(
                lambda key, found, extra: self.view.add_buildings(key, found))
        elif on and self._tilejson is None:
            self._tilejson = fetch_json(OPENFREEMAP_TILEJSON,
                                        self._tilejson_done)
        self.view.set_buildings(on, self.buildings_loader)
        self._show_attribution()

    def _update_layer_labels(self, force=False):
        """Подписи слоёв проекта, которые сейчас на глобусе. Слои
        читаются заново, только когда вид сдвинулся на долю окна."""
        pose = self.view.navigator.pose
        width = 2.0 * pose.distance * math.tan(
            math.radians(self.view.camera.fov_y) / 2.0)
        # Слои проекта - земные, на другом теле подписей нет.
        layers = (self._applied_layers or []) if self.planet.earth else []
        self.layer_labels.update(layers, pose.lat,
                                 pose.lon, width, force)

    def _show_layer_labels(self):
        self.view.layer_marks = self.layer_labels.marks
        self.view.update()

    def _update_grid(self):
        """Сетка на глобусе. Строится заново, только когда меняется
        шаг или точка взгляда уходит на шаг, а не каждый кадр."""
        if not self.extras.get("grid"):
            if self.grid_shapes or self.view.grid_marks:
                self.grid_shapes = []
                self.view.grid_marks = []
                self._grid_key = None
                self._refresh_shapes()
            return
        pose = self.view.navigator.pose
        width = 2.0 * pose.distance * math.tan(
            math.radians(self.view.camera.fov_y) / 2.0)
        key = graticule.key(pose.lat, pose.lon, width)
        if key == self._grid_key:
            return
        self._grid_key = key
        step, found = graticule.lines(pose.lat, pose.lon, width)
        self.grid_shapes = [Shape("line", points, color=GRID_COLOR,
                                  width=GRID_WIDTH)
                            for _, _, points in found]
        self.grid_shapes += [
            Shape("line", points, color=CIRCLE_COLOR, width=GRID_WIDTH)
            for _, _, points in graticule.circles(pose.lat, pose.lon,
                                                  width)]
        marks = []
        for n, (lat, lon, kind, value) in enumerate(
                graticule.labels(pose.lat, pose.lon, width)):
            marks.append(MarkPlace(-100000 - n, self._grid_text(
                kind, value, step), "grid", 1, lat,
                graticule.normal_lon(lon)))
        names = self._circle_names()
        for n, (lat, lon, name) in enumerate(
                graticule.circle_labels(pose.lat, pose.lon, width)):
            marks.append(MarkPlace(-200000 - n, names[name], "circle", 1,
                                   lat, graticule.normal_lon(lon)))
        self.view.grid_marks = marks
        self._refresh_shapes()

    @staticmethod
    def _circle_names():
        return {"equator": tr("Экватор"),
                "cancer": tr("Тропик Рака"),
                "capricorn": tr("Тропик Козерога"),
                "arctic": tr("Северный полярный круг"),
                "antarctic": tr("Южный полярный круг")}

    def _grid_text(self, kind, value, step):
        """Подпись линии сетки с полушарием."""
        angle = graticule.angle_text(value, step)
        if kind == "lat":
            if abs(value) < 1e-9:
                return angle
            return tr("{angle} с. ш.", angle=angle) if value > 0 \
                else tr("{angle} ю. ш.", angle=angle)
        value = graticule.normal_lon(value)
        if abs(value) < 1e-9 or abs(abs(value) - 180.0) < 1e-9:
            return graticule.angle_text(abs(value), step)
        return tr("{angle} в. д.", angle=angle) if value > 0 \
            else tr("{angle} з. д.", angle=angle)

    def _load_sky(self):
        """Картинка неба с Млечным путём, один раз за окно. Запрос идёт
        тем же загрузчиком, что и тайлы, картинка раскодируется в его
        потоке. Второй раз она берётся из кэша QGIS."""
        if self.sky_loader is not None:
            return
        source = basemap.Source("NASA SVS", stars.SKY_URL, 0,
                                builtin=True)
        self.sky_loader = TileLoader(source, parent=self)
        self.sky_loader.loaded.connect(
            lambda key, rgba, extra: self.view.set_sky_image(rgba))
        self.sky_loader.want((0, 0, 0), 1.0)

    def _set_gibs(self, name, on):
        """Слой NASA GIBS вида - облака, море или суша: новый загрузчик
        или никакого. Ответы GIBS запрещают кэш, поэтому мимо него."""
        old = self.gibs_loaders.pop(name, None)
        if old is not None:
            old.abort()
            old.deleteLater()
        loader = None
        if on:
            source, prepare = gibs_source(name)
            loader = TileLoader(source, parent=self, prepare=prepare,
                                size=TILE_SIZE, cache=False)
            loader.loaded.connect(
                lambda key, rgba, levels, name=name:
                self.view.add_gibs(name, key, levels))
            self.gibs_loaders[name] = loader
        self.view.set_gibs(name, on, loader)
        self._show_attribution()

    def set_relief(self, on):
        """Включить или выключить рельеф, сразу, флажком панели «Слои»."""
        self._relief = bool(on)
        QgsSettings().setValue(RELIEF_KEY, self._relief)
        self.panel.set_geo(self._groups, self._relief)
        self.view.set_relief(self._relief_target())
        if self._relief:
            self.terrain_loader.want((0, 0, 0), 1.0)
        self._sync_properties()
        self._show_attribution()
        self._mark_dirty(self._pending())

    def set_relief_scale(self, scale):
        """Вертикальный масштаб рельефа."""
        self._scale = min(max(float(scale), SCALE_RANGE[0]), SCALE_RANGE[1])
        QgsSettings().setValue(SCALE_KEY, self._scale)
        self._changed()

    def set_layer_shown(self, layer_id, on):
        """Отметка слоя проекта в списке глобуса.

        В режиме «как на карте QGIS» отметка включает и выключает слой
        в дереве слоёв QGIS, глобус следует за деревом.
        """
        if self.follow:
            set_visible_on_map(layer_id, on)
            return
        if on:
            self._shown.add(layer_id)
        else:
            self._shown.discard(layer_id)
        write_shown(self._shown)
        self._changed()

    def _relief_target(self):
        """Масштаб рельефа. У Марса и Луны высот тайлами нет."""
        if not self.planet.earth:
            return 0.0
        return self._scale if self._relief else 0.0

    # Тело глобуса.

    def set_body(self, key):
        """Земля, Марс или Луна. Размеры тела, подложка, воздух,
        земные слои и вид - всё сразу. Камера встаёт над домашней
        точкой тела."""
        if key == "sky":
            self.show_sky()
            return
        if self.view.sky_view is not None:
            self._leave_sky()
        planet = planet_by_key(key)
        self.toolbar.set_body(planet.key)
        if planet is self.planet:
            return
        self.planet = planet
        ellipsoid.set_body(planet.body)
        if planet.earth:
            source = self.sources[self._basemap]
        else:
            name, url, top, text, link = planet.imagery
            source = basemap.Source(name, url, top, (text, link),
                                    builtin=True)
        old = self.loader
        old.abort()
        old.deleteLater()
        self.errors.clear()
        self.source = source
        self._start_loader()
        self.view.change_body(source.max_level, planet.air)
        self.loader.want_many((key, -key[0]) for key in start_keys())
        self.view.set_relief(self._relief_target())
        self.view.reset_places(self.source.max_level)
        self.view.label_kinds = label_kinds(self._groups) \
            if planet.earth else set()
        self._update_overlay()
        self._update_layer_labels(force=True)
        for extra in EARTH_EXTRAS:
            self._apply_extra(extra, self.extras.get(extra, False))
        if not planet.earth:
            # Отжатые кнопки сами выключают синхронизацию и опрос.
            self.toolbar.sync.setChecked(False)
            self.toolbar.identify.setChecked(False)
        self.toolbar.sync.setEnabled(planet.earth)
        self.toolbar.identify.setEnabled(planet.earth)
        self.panel.set_earth(planet.earth)
        self._grid_key = None
        self._update_grid()
        self._refresh_shapes()
        lat, lon, distance = planet.home
        navigator = self.view.navigator
        navigator.stop()
        navigator.set_pose(Pose(lat, lon, distance, 0.0, 0.0))
        self._show_attribution()
        self.view.update()

    # Вид неба.

    def _globe_buttons(self):
        """Значки, которым нужна поверхность тела."""
        bar = self.toolbar
        return (bar.ruler_button, bar.place_button, bar.save_button,
                bar.record, bar.sync, bar.identify)

    def sky_moment(self):
        """Момент светил неба: конец открытой шкалы времени, иначе
        None - часы компьютера."""
        return self.sun_time() if self.timebar.shown() else None

    def show_sky(self, ra=None, dec=None, fov=None):
        """Вид звёздного неба из центра небесной сферы. ra, dec, fov -
        взгляд в градусах, None - прежний взгляд или начальный."""
        view = self.view
        if view.sky_view is None:
            view.sky_view = self._sky_state or SkyView()
            for dialog in (self.ruler_dialog, self.place_dialog):
                if dialog is not None and dialog.isVisible():
                    dialog.close()
            view.navigator.stop()
        if ra is not None:
            view.sky_view.set(ra, dec, fov)
        view.sky_time = self.sky_moment()
        self.toolbar.set_body("sky")
        self.navpad.hide()
        self.legend.hide()
        for button in self._globe_buttons():
            button.setEnabled(False)
        self._show_attribution()
        self.sky_labels.sync()
        view.update()

    def set_constellations(self, on):
        """Линии и названия созвездий на небе."""
        self.view.show_constellations = bool(on)
        QgsSettings().setValue(CONSTELLATIONS_KEY, bool(on))
        self.toolbar.constellations.setChecked(bool(on))
        self.view.update()

    def _leave_sky(self):
        view = self.view
        self._sky_state = view.sky_view
        view.sky_view = None
        self.navpad.show()
        for button in self._globe_buttons():
            button.setEnabled(True)
        self.toolbar.sync.setEnabled(self.planet.earth)
        self.toolbar.identify.setEnabled(self.planet.earth)
        self.legend.setVisible(bool(self.extras.get("temperature"))
                               and self.planet.earth)
        self.toolbar.set_body(self.planet.key)
        self._show_attribution()
        self.sky_labels.sync()
        view.update()

    def _read_shown(self):
        """Отметки слоёв из проекта.

        В проекте без записи не отмечен ни один слой, решение автора
        от 27 сентября 2026 года. Раньше отмечались слои, видимые на карте.
        """
        layers = map_layers()
        self.follow = read_flag(FOLLOW, False)
        if self.follow:
            self._shown = {layer.id() for layer in layers
                           if visible_on_map(layer)}
            self._known = {layer.id() for layer in layers}
            return
        shown = read_shown()
        self._shown = shown if shown is not None else set()
        self._known = {layer.id() for layer in layers}

    # Переход выбранного состояния на глобус.

    def _changed(self):
        """Выбранное состояние изменилось."""
        self._sync_properties()
        self._show_layers()
        if self.auto_refresh:
            self.refresh_timer.start(REFRESH_DELAY)
        else:
            self._mark_dirty(self._pending())

    def _pending(self):
        """Есть ли выбранное, что ещё не видно на глобусе. У Марса
        и Луны подложка своя, земные подложка и слои ждут Земли."""
        if not self.planet.earth:
            return False
        return (self.source not in self.sources
                or self._basemap != self.sources.index(self.source)
                or self._relief_target() != self.view.store.scale
                or self._overlay_layers() != self._applied_layers
                or self._layers_stale)

    def refresh(self):
        """Показать на глобусе выбранные подложку, рельеф и слои. У Марса
        и Луны подложка своя, она остаётся."""
        self.refresh_timer.stop()
        if self.planet.earth:
            self._switch_basemap(self.sources[self._basemap])
        self.view.set_relief(self._relief_target())
        self._apply_vector(force=True)
        self._mark_dirty(False)
        self._show_attribution()

    def _apply_vector(self, force=False):
        """Показать выбранную векторную основу и отмеченные слои.

        force=False - как при флажке в панели «Слои»: слои проекта
        остаются прежними до кнопки «Обновить».
        """
        layers = self._overlay_layers() if force else self._applied_layers
        if layers is None:
            layers = self._overlay_layers()
        lines = self._groups & set(LINE_GROUPS)
        old_lines = (self._applied_groups or set()) & set(LINE_GROUPS)
        self._applied_groups = set(self._groups)
        if self._groups and self.ofm_layer is None \
                and self._tilejson is None:
            self._tilejson = fetch_json(OPENFREEMAP_TILEJSON,
                                        self._tilejson_done)
        self.view.label_kinds = label_kinds(self._groups) \
            if self.planet.earth else set()
        self.view.update()
        # Наложение перерисовывается, только если сменились линии
        # или слои. Надписи пунктов рисует вид. Изменённые слои проекта
        # переходят на глобус только по кнопке «Обновить».
        stale = self._layers_stale and force
        if lines != old_lines or layers != self._applied_layers \
                or stale or self.overlay is None and layers:
            self._applied_layers = layers
            if force:
                self._layers_stale = False
            if self.ofm_layer is not None:
                set_line_groups(self.ofm_layer, lines)
            self._update_overlay(keep=True)
            # Подписи слоёв - заново: сменились слои или их данные.
            self._update_layer_labels(force=True)
        self._show_attribution()

    def _switch_basemap(self, source):
        if source is self.source:
            return
        old = self.loader
        old.abort()
        old.deleteLater()
        self.errors.clear()
        self.source = source
        self._start_loader()
        self.view.change_source(source.max_level)
        # Уровни 0-2 просятся сразу. Вид не рисует кадр, пока их нет,
        # и сам их не попросит. Без этого смена подложки до прихода
        # уровней 0-2 оставляла окно пустым, нашлось 26 сентября 2026.
        self.loader.want_many((key, -key[0]) for key in start_keys())

    # Наложение.

    def _overlay_layers(self):
        """Номера отмеченных слоёв проекта в порядке карты."""
        return [layer.id() for layer in map_layers()
                if layer.id() in self._shown]

    def _start_loader(self):
        """Загрузчик выбранной подложки и её подпись."""
        self.loader = TileLoader(self.source, parent=self,
                                 prepare=imagery_preparer(self.view.store),
                                 size=TILE_SIZE, fill=True)
        self.loader.loaded.connect(self._loaded)
        self.loader.failed.connect(self._failed)
        self.view.loader = self.loader
        self._show_attribution()

    def _show_attribution(self):
        if self.view.sky_view is not None:
            self.attribution.setText(" · ".join(
                link_html(*credit) for credit in SKY_ATTRIBUTION))
            self._place_attribution()
            return
        parts = [attribution_html(self.source)]
        if self._applied_groups and self.ofm_layer is not None \
                or self.buildings_loader is not None:
            parts.append(link_html(*OPENFREEMAP_ATTRIBUTION))
        if self.view.store.scale:
            parts.append(TERRAIN_ATTRIBUTION)
        if "clouds" in self.gibs_loaders:
            parts.append(link_html(*clouds.ATTRIBUTION))
        if "sea" in self.gibs_loaders:
            parts.append(link_html(*temperature.ATTRIBUTION))
        self.attribution.setText(" · ".join(parts))
        self._place_attribution()

    def _place_attribution(self):
        self.attribution.adjustSize()
        self.attribution.move(
            max(MARGIN, self.view.width() - self.attribution.width()
                - MARGIN),
            self.view.height() - self.attribution.height() - MARGIN)
        bar = self.toolbar.geometry()
        self.spinner.move(bar.right() + MARGIN,
                          bar.center().y() - self.spinner.height() // 2)
        # Шкала времени - под панелью значков, как в Google Earth.
        self.timebar.anchor = lambda: (bar.left(), bar.bottom() + MARGIN)
        self.timebar._place()
        # Шкала - в левом нижнем углу. Узкий вид: над подписью.
        bottom = self.view.height() - MARGIN
        if self.attribution.x() < MARGIN + self.legend.width():
            bottom = self.attribution.y() - MARGIN // 2
        self.legend.move(MARGIN, bottom - self.legend.height())

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == enum(
                QEvent, "Type", "Resize"):
            self._place_attribution()
        return super().eventFilter(watched, event)

    def _tilejson_done(self, data, error):
        self._tilejson = None
        tiles = (data or {}).get("tiles") or []
        if not tiles:
            self.overlay_error = error or "TileJSON"
            self._show_state()
            return
        self.overlay_error = ""
        max_zoom = int(data.get("maxzoom", 14))
        self.ofm_layer = openfreemap_layer(tiles[0], max_zoom,
                                           self._applied_groups or ())
        self.rail_layer = railway_layer(tiles[0], max_zoom)
        # Названия пунктов - из тех же векторных тайлов, свой загрузчик.
        self._places_source = basemap.Source("OpenFreeMap", tiles[0],
                                             max_zoom)
        self._ofm_source = basemap.Source("OpenFreeMap", tiles[0], max_zoom)
        self._start_place_loader()
        # TileJSON просят и здания без векторной основы. Тогда наложение
        # не пересобирается, картинки слоёв проекта остаются.
        if self._applied_groups:
            self._update_overlay()
        if self.extras.get("buildings") and self.buildings_loader is None:
            self._set_buildings(True)
        self._show_attribution()

    def _start_place_loader(self):
        """Загрузчик пунктов на выбранном языке, пункты с нуля."""
        old = self.place_loader
        if old is not None:
            old.abort()
            old.deleteLater()
        self.place_loader = TileLoader(
            self._places_source, parent=self,
            decode=places_decoder(label_languages(self._language)))
        self.place_loader.loaded.connect(
            lambda key, found, extra: self.view.add_places(key, found))
        self.view.reset_places(self._places_source.max_level)
        self.view.place_loader = self.place_loader

    def _update_overlay(self, keep=False):
        """Собрать наложение заново из действующих источников.

        Сверху отмеченные слои проекта в порядке карты QGIS, под ними
        векторная основа. keep=True - прежние картинки видны, пока их
        не заменят новые, так обновление после правки не мигает.
        """
        project = QgsProject.instance()
        layers = [project.mapLayer(layer_id)
                  for layer_id in self._applied_layers or ()]
        layers = [layer for layer in layers if layer is not None]
        groups = self._applied_groups or set()
        if not self.planet.earth:
            # Слои проекта и векторная основа - земные.
            layers, groups = [], set()
        if groups & set(LINE_GROUPS) and self.ofm_layer is not None:
            layers.append(self.ofm_layer)
        min_levels = {}
        if RAILWAYS in groups and self.rail_layer is not None:
            layers.append(self.rail_layer)
            min_levels[self.rail_layer.id()] = RAIL_FROM
        if self.overlay is not None:
            self.overlay.abort()
            self.overlay.deleteLater()
            self.overlay = None
        if layers:
            self.overlay = LayerOverlay(layers, parent=self,
                                        min_levels=min_levels)
            self.overlay.loaded.connect(self.view.add_overlay)
        self.view.set_overlay(self.overlay,
                              keep=keep and self.overlay is not None)

    def _show_layers(self):
        self.panel.set_layers(map_layers(), self._shown)

    def set_layer_opacity(self, layer_id, opacity):
        """Прозрачность слоя QGIS из меню глобуса.

        Меняется сам слой, карта перерисуется. Глобус обновляется сразу,
        без кнопки «Обновить»: прозрачность двигают здесь и смотрят
        здесь же. Таймер собирает движения ползунка в одно обновление.
        """
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return
        layer.setOpacity(opacity)
        layer.triggerRepaint()
        if layer_id in self.shown_layers():
            self._layers_stale = True
            self.refresh_timer.start(REFRESH_DELAY)

    def _project_changed(self):
        """Слои проекта изменились: обновить сразу или зажечь кнопку.

        Новый слой попадает на глобус, если так задано в свойствах вида.
        По умолчанию его отмечают в списке.
        """
        layers = map_layers()
        if self.tracks.settings:
            # Точки трека могли измениться.
            self.tracks.reload()
        added = [layer.id() for layer in layers
                 if layer.id() not in self._known]
        self._known = {layer.id() for layer in layers}
        if added and self.new_shown and not self.follow:
            self._shown |= set(added)
            write_shown(self._shown)
        # Перерисовка слоя меняет глобус, только если слой на нём.
        if self._applied_layers:
            self._layers_stale = True
        self._changed()

    def _legend_changed(self):
        """Видимость в дереве слоёв QGIS сменилась."""
        if not self.follow:
            return
        self._shown = {layer.id() for layer in map_layers()
                       if visible_on_map(layer)}
        self._changed()

    def set_follow(self, on):
        """Режим «как на карте QGIS»: видимость слоёв на глобусе - из
        дерева слоёв QGIS. Флажок хранится в проекте."""
        self.follow = bool(on)
        write_flag(FOLLOW, self.follow)
        if self.follow:
            self._legend_changed()
        else:
            write_shown(self._shown)
            self._changed()

    def set_new_shown(self, on):
        """Новые слои проекта сразу на глобус. Настройка QGIS."""
        self.new_shown = bool(on)
        QgsSettings().setValue(NEW_SHOWN_KEY, self.new_shown)
        self._sync_properties()

    def _selection_changed(self, layer_id):
        if layer_id in (self._applied_layers or ()):
            self._selection_timer.start(SELECTION_DELAY)

    def _selection_redraw(self):
        if self.overlay is not None:
            self._update_overlay(keep=True)

    def _project_reloaded(self):
        """Открыт другой проект: его настройки глобуса."""
        self.auto_refresh = read_flag(AUTO_REFRESH, False)
        self._read_shown()
        self.tracks.load()

    def _mark_dirty(self, dirty):
        self.dirty = dirty
        self.toolbar.set_dirty(dirty)
        self._show_state()

    def _set_auto(self, on):
        self.auto_refresh = bool(on)
        write_flag(AUTO_REFRESH, on)
        if on and self.dirty:
            self.refresh()

    def set_coords(self, fmt):
        """Формат координат строки состояния и окна «Объекты»."""
        if fmt not in COORD_FORMATS:
            return
        self.coords = fmt
        QgsSettings().setValue(COORDS_KEY, fmt)
        self._cursor_text = ""
        self._update_cursor()
        self._sync_properties()

    def _sync_properties(self):
        if self.properties is not None:
            self.properties.set_state(self.state())

    def _show_properties(self):
        if self.properties is None:
            self.properties = PropertiesDialog(
                self.sources, self.state(), self)
            self.properties.auto_changed.connect(self._set_auto)
            self.properties.basemap_chosen.connect(self.choose_basemap)
            self.properties.scale_changed.connect(self.set_relief_scale)
            self.properties.language_chosen.connect(self.set_label_language)
            self.properties.sync_chosen.connect(self.set_sync_direction)
            self.properties.follow_changed.connect(self.set_follow)
            self.properties.new_shown_changed.connect(self.set_new_shown)
            self.properties.coords_chosen.connect(self.set_coords)
        self.properties.show()
        self.properties.raise_()
        self.properties.activateWindow()

    # Загрузка.

    def _heights(self, key, rgba, tile):
        self.terrain_errors.pop(key, None)
        self.view.add_heights(tile)
        self._heights_arrived()

    def _loaded(self, key, rgba, prepared):
        self.errors.pop(key, None)
        mesh, levels, level, scale = prepared
        # Сетка, собранная до смены масштаба рельефа, пересобирается.
        if scale != self.view.store.scale:
            level = -1
        self.view.add_image(key, levels, mesh, level)
        # Пока уровни 0-2 не готовы, полных кадров нет и сигнала changed
        # тоже. Строка загрузки обновляется отсюда, с тем же ограничением.
        self._frame_done()

    def _failed(self, key, error):
        self.errors[key] = error
        self._show_state()

    def _frame_done(self):
        """После кадра строка обновляется не чаще STATUS_PERIOD.

        setText на каждом кадре перерисовывает строку и отнимает время
        у цикла событий. Замер 26 сентября 2026 года показал до 22 мс
        между кадром и следующим paintGL.
        """
        now = time.monotonic()
        # Под неподвижным курсором при движении камеры точка другая.
        if getattr(self, "_hover", None) is not None \
                and not self._cursor_timer.isActive():
            self._cursor_timer.start(CURSOR_PERIOD)
        if now - self._shown_at >= STATUS_PERIOD:
            self._shown_at = now
            self._show_state()

    # Перелёты.

    def fly(self, text=None):
        """Поиск из поля ввода: координаты - перелёт, иначе Nominatim."""
        text = self.place.text() if text is None else text
        target = parse_point(text)
        if target is not None:
            self.panel.set_found([])
            self._found = []
            self._mark(normalize(text), *target)
            distance = min(self.view.navigator.pose.distance,
                           FLIGHT_DISTANCE)
            self._fly_to(target[0], target[1], distance)
            return
        query = normalize(text)
        if query and not self.planet.earth:
            # Поиск по названию - Nominatim, он знает только Землю.
            self.message = (tr("Поиск по названию есть только у Земли. "
                               "Координаты вводятся числами."),
                            time.monotonic())
            self._show_state()
            return
        if query:
            self._search(query)

    # Поиск места по названию. Правила Nominatim: запрос только по Enter,
    # не чаще раза в SEARCH_INTERVAL, ответы запоминаются до закрытия
    # окна, заголовок PlanetX ставит обработчик запросов загрузчика.

    def _search_language(self):
        languages = label_languages(self._language)
        return languages[0] if languages else None

    def _search(self, query):
        key = (query, self._search_language())
        if key in self._searched:
            self._show_found(key, self._searched[key])
            return
        self._search_key = key
        self.message = (tr("Поиск: {text}", text=query), time.monotonic())
        self._show_state()
        wait = SEARCH_INTERVAL - (time.monotonic() - self._search_at)
        self._search_timer.start(max(0, int(wait * 1000)))

    def _send_search(self):
        if self._search_reply is not None:
            # Прежний запрос ещё идёт, новый ждёт его.
            self._search_timer.start(int(SEARCH_INTERVAL * 1000))
            return
        key = self._search_key
        self._search_at = time.monotonic()
        self._search_reply = fetch_json(
            search_url(*key),
            lambda data, error: self._search_done(key, data, error))

    def _search_done(self, key, data, error):
        self._search_reply = None
        if data is None:
            self.message = (tr("Поиск не удался: {error}", error=error),
                            time.monotonic())
            self._show_state()
            return
        places = parse_places(data)
        self._searched[key] = places
        if key == self._search_key:
            self._show_found(key, places)

    def _show_found(self, key, places):
        """Перелёт к первому найденному месту, остальные - списком."""
        self._found = places
        self.panel.set_found([place_text(p) for p in places]
                             if len(places) > 1 else [])
        if not places:
            self.message = (tr("Ничего не найдено: {text}", text=key[0]),
                            time.monotonic())
            self._show_state()
            return
        self.message = ("", 0.0)
        self._show_state()
        self._fly_place(places[0])

    def fly_place(self, index):
        """Перелёт к месту из списка найденных."""
        if 0 <= index < len(self._found):
            self._fly_place(self._found[index])

    def clear_search(self):
        """Поле поиска очищено: списка и метки больше нет."""
        self._found = []
        self._search_key = None
        self.view.set_search_mark(None)

    def _mark(self, name, lat, lon):
        """Временная метка на месте, как у Google Earth. Одна на окно."""
        self.view.set_search_mark(MarkPlace(-1, name, "search", 0, lat, lon))

    def _fly_place(self, place):
        """Метка и камера над местом, охват места целиком в кадре."""
        self._mark(place.name, place.lat, place.lon)
        distance = SEARCH_MIN_DISTANCE
        if place.box is not None:
            camera = self.view.camera
            distance = min(max(fit_view(*place.box, camera.fov_y,
                                        camera.aspect)[2],
                               SEARCH_MIN_DISTANCE), SEARCH_MAX_DISTANCE)
        self._fly_to(place.lat, place.lon, distance)

    def fly_to_layer(self, layer):
        """Перелёт к охвату слоя, камера смотрит отвесно."""
        self._fly_extent(layer.extent(), layer.crs())

    # «Мои метки».

    def _places_changed(self):
        self.panel.set_places(self.myplaces.tree())
        self._update_timebar()
        self._refresh_shapes()

    def _update_timebar(self):
        """Охват шкалы времени по видимым меткам со временем."""
        extent = when.extent(p.time for p in self.myplaces.places
                             if p.visible)
        self.timebar.set_extent(extent)
        # Панель значков заводится позже первого чтения меток.
        toolbar = getattr(self, "toolbar", None)
        if toolbar is not None:
            toolbar.set_time_available(extent is not None)
        self._time_range = self.timebar.range() \
            if self.timebar.shown() else None

    def _time_toggled(self, on):
        """Кнопка шкалы. Закрытая шкала метки не скрывает."""
        if on:
            self.timebar.open_bar()
        else:
            self.timebar.close_bar()
        self._time_range = self.timebar.range() \
            if self.timebar.shown() else None
        self._refresh_shapes()
        self._update_sun()

    def _time_changed(self, lo, hi):
        self._time_range = (lo, hi)
        self._refresh_shapes()
        self._update_sun()
        if self.view.sky_view is not None:
            self.view.sky_time = self.sky_moment()
            self.view.update()

    def _time_ok(self, place):
        """Попадает ли время метки в промежуток шкалы."""
        span = self._time_range
        return span is None or when.visible(place.time, *span)

    def _show_time(self, time):
        """Шкала на время вида или метки, как у Google Earth. Закрытая
        шкала при этом открывается - у вида есть дата."""
        span = when.interval(time)
        if span is None or not self.timebar.known:
            return
        if not self.timebar.shown():
            self.timebar.open_bar()
            self.toolbar.set_time_shown(True)
        self.timebar.set_range(*span)

    def _refresh_shapes(self):
        """На глобусе видимые «Мои метки», треки и фигура открытой
        линейки."""
        # Метка с открытым окном свойств показывается с правками окна.
        shapes = [self.previews.get(p.key, p.shape)
                  for p in self.myplaces.places
                  if p.visible and self._time_ok(p) and not p.tour
                  and p.body == self.planet.key]
        if getattr(self, "tracks", None) is not None and self.planet.earth:
            shapes += self.tracks.shapes()
        shapes += getattr(self, "grid_shapes", [])
        if self._ruler_open():
            shape = self.ruler.shape()
            if shape is not None:
                shapes.append(shape)
        elif self._place_open():
            shape = self.place_dialog.shape()
            if shape is not None:
                shapes.append(shape)
        self.view.set_shapes([self._drawn_shape(s) for s in shapes])

    def _drawn_shape(self, shape):
        """3D-объект так, как он стоит на поднятом рельефе: к настоящей
        высоте точки добавлен подъём рельефа под ней."""
        scale = self.view.store.scale
        if not has_alts(shape) or not scale or scale == 1.0:
            return shape
        lat = np.array([p[0] for p in shape.points])
        lon = np.array([p[1] for p in shape.points])
        drawn = np.asarray(self.view.store.heights_at(lat, lon))
        alts = np.asarray(shape.alts, dtype=np.float64) + drawn \
            - drawn / scale
        return shape._replace(alts=tuple(float(a) for a in alts))

    # Сцена.

    def record_tour(self, folder=None):
        """Записать показанный тур кадрами PNG в папку. Без folder -
        выбор папки. Возвращает True, если запись началась."""
        if self.recorder.active or not self.tour.stops:
            return False
        if folder is None:
            folder = QFileDialog.getExistingDirectory(
                self, tr("Папка для кадров тура"))
            if not folder:
                return False
        self.tour.pause_for_record()
        return self.recorder.start(self.tour.stops,
                                   self.tour.bar.pause.value(), folder)

    def _recorded(self, ok, text):
        self.message = (text, time.monotonic())
        self.tour._show()
        self._show_state()

    def save_scene(self, path=None):
        """Сцена в файл. Метки и тур - выбранная папка «Моих меток»."""
        folder = self.panel.current_folder()
        if path is None:
            name = self.myplaces.find(folder).name if folder else "PlanetX"
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Сохранить сцену"), (name or "PlanetX") + EXTENSION,
                tr("Сцена PlanetX (*{ext})", ext=EXTENSION))
        if not path:
            return False
        name = os.path.splitext(os.path.basename(path))[0]
        scene, kml = capture_scene(self, folder, name)
        try:
            with open(path, "wb") as fh:
                fh.write(write_scene(scene, kml))
        except OSError as error:
            QMessageBox.warning(self, tr("Сохранить сцену"), tr(
                "Файл не записан: {error}", error=str(error)))
            return False
        self.message = (tr("Сцена сохранена: {path}", path=path),
                        time.monotonic())
        self._show_state()
        return True

    def open_demo(self):
        """Демо «Пермь» из папки модуля, tools/make_demo.py."""
        return self.open_scene(os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "demo",
            "perm" + EXTENSION))

    def open_scene(self, path=None):
        """Сцена из файла на глобус. Возвращает ключ папки её меток."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Открыть сцену"), "",
                tr("Сцена PlanetX (*{ext})", ext=EXTENSION))
        if not path:
            return None
        try:
            with open(path, "rb") as fh:
                scene, kml = read_scene(fh.read())
        except (OSError, SceneError) as error:
            QMessageBox.warning(self, tr("Открыть сцену"), tr(
                "Файл не прочитан: {error}", error=str(error)))
            return None
        key, missing = apply_scene(self, scene, kml)
        if key is not None:
            self.panel.select_place(key)
        if missing:
            self.message = (tr("Сцена открыта, слои не найдены: {names}",
                               names=", ".join(missing)),
                            time.monotonic())
            self._show_state()
        return key

    def _open_track(self, layer):
        """Окно «Трек» точечного слоя."""
        dialog = TrackDialog(layer, self.tracks.settings.get(layer.id()),
                             self)
        if dialog.exec():
            self.tracks.set_track(layer, None if dialog.removed
                                  else dialog.settings())

    # Новая метка.

    def _place_open(self):
        return self.place_dialog is not None and self.place_dialog.isVisible()

    def _open_place(self):
        if self._ruler_open():
            self.ruler_dialog.close()
        if self.place_dialog is None:
            self.place_dialog = PlaceDialog(self.drawer, self._draw_name,
                                            self)
            self.place_dialog.save_requested.connect(self._save_place)
            self.place_dialog.style_changed.connect(self._refresh_shapes)
            self.place_dialog.finished.connect(self._place_closed)
        self.place_dialog.show()
        self.place_dialog.raise_()
        self._refresh_shapes()
        self._tool_cursor()

    def _place_closed(self, *args):
        self.drawer.clear()
        self._refresh_shapes()
        self._tool_cursor()

    def _save_place(self):
        shape = self.place_dialog.shape(rubber=False)
        if shape is None:
            return
        self.myplaces.add(shape, folder=self.panel.current_folder())
        self.place_dialog.name.clear()
        self.place_dialog.reset_name()
        self.drawer.clear()

    def new_name(self, base):
        """Название новой метки с номером, как «Моя метка 3»."""
        return numbered_name(base, [p.name for p in
                                    self.myplaces.places_in(None)])

    def _draw_name(self, mode):
        bases = {"point": tr("Моя метка"), "path": tr("Мой путь"),
                 "polygon": tr("Мой многоугольник")}
        return self.new_name(bases[mode])

    def set_sidebar(self, shown):
        """Показать или скрыть левую панель, вид занимает её место."""
        self.panel.setVisible(bool(shown))
        self.toolbar.set_sidebar(bool(shown))
        QgsSettings().setValue(SIDEBAR_KEY, bool(shown))

    # Снимок вида.

    def _open_snapshot(self, to_layout):
        # Окно строится заново: пропорции окна глобуса и список макетов
        # с прошлого раза могли измениться. Окно с начатым снимком
        # остаётся.
        dialog = self.shot_dialogs.get(to_layout)
        if dialog is not None and not dialog.mine:
            dialog.deleteLater()
            dialog = None
        if dialog is None and self.view.shot is None:
            dialog = SnapshotDialog(self, to_layout)
            self.shot_dialogs[to_layout] = dialog
        if dialog is None:
            return  # идёт снимок другого окна
        dialog.show()
        dialog.raise_()

    # Линейка.

    def _true_heights(self, lats, lons):
        """Настоящие высоты рельефа, без вертикального масштаба."""
        return self.view.store.heights_at(lats, lons, scaled=False)

    def _has_height_tile(self, key):
        # Высот Марса и Луны нет, линейка и профиль не ждут их: высоты
        # там нулевые. Иначе вид просил бы земные тайлы Terrarium.
        return key in self.view.store.tiles or not self.planet.earth

    def _ruler_changed(self):
        self._update_tool_marks()
        dialog = self.profile_dialog
        if dialog is not None and dialog.isVisible() \
                and dialog.source is self.ruler:
            dialog.refresh()

    def _undo_point(self):
        """Backspace над видом: последняя точка линейки."""
        if self._ruler_open():
            self.ruler.remove_last()

    def _heights_arrived(self):
        """Пришёл тайл высот: длина по рельефу и профиль уточняются."""
        if self._ruler_open() and len(self.ruler.points) >= 2:
            self.ruler_dialog.show_values()
        dialog = self.profile_dialog
        if dialog is not None and dialog.isVisible():
            dialog.refresh()

    def _update_tool_marks(self):
        """Длины отрезков линейки у их середин и точка профиля под
        курсором графика."""
        marks = []
        ruler = self.ruler
        if self._ruler_open() and ruler.mode in ("line", "path",
                                                 "polygon"):
            points = ruler._points(True)
            closed = ruler.mode == "polygon"
            pairs = list(zip(points, points[1:]))
            if closed and len(points) >= 3:
                pairs.append((points[-1], points[0]))
            unit = self.ruler_dialog.length_unit()
            short = unit_short()[unit]
            middles = segment_midpoints(points, closed)
            for n, ((a, b), (lat, lon)) in enumerate(zip(pairs, middles)):
                length = ruler.da.measureLine(ruler_xy([a, b]))
                text = "{} {}".format(
                    number(convert(length, unit, LENGTH_UNITS)), short)
                marks.append(MarkPlace(-300000 - n, text, "ruler", 1, lat,
                                       lon))
        if self._profile_mark is not None:
            marks.append(self._profile_mark)
        self.view.tool_marks = marks
        self.view.update()

    def _open_profile(self, title, points, source):
        """Окно «Профиль высот» для точек points() с высотами source."""
        if self.profile_dialog is None:
            self.profile_dialog = ProfileDialog(title, points, source, self)
            self.profile_dialog.point_hovered.connect(self._profile_hover)
            self.profile_dialog.finished.connect(
                lambda *args: self._profile_hover(None))
        else:
            self.profile_dialog.set_points(title, points, source)
        self.profile_dialog.show()
        self.profile_dialog.raise_()

    def _ruler_profile(self):
        self._open_profile(tr("Линейка"), lambda: self.ruler._points(False),
                           self.ruler)

    def _profile_hover(self, point):
        """Точка профиля под курсором графика - метка на глобусе."""
        if point is None:
            self._profile_mark = None
        else:
            lat, lon, height = point
            self._profile_mark = MarkPlace(
                -400000, tr("{value} м", value="{:.0f}".format(height)),
                "mark", 1, lat, lon)
        self._update_tool_marks()

    def _ruler_open(self):
        return self.ruler_dialog is not None and self.ruler_dialog.isVisible()

    def _open_ruler(self):
        if self._place_open():
            self.place_dialog.close()
        if self.ruler_dialog is None:
            self.ruler_dialog = RulerDialog(self.ruler, self)
            self.ruler_dialog.save_requested.connect(self._save_ruler)
            self.ruler_dialog.profile_requested.connect(
                self._ruler_profile)
            self.ruler_dialog.finished.connect(self._ruler_closed)
        self.ruler_dialog.show()
        self.ruler_dialog.raise_()
        self.view.vertex_tool = self.ruler_vertices
        self._refresh_shapes()
        self._tool_cursor()

    def _ruler_closed(self, *args):
        self.view.vertex_tool = None
        self.ruler.clear()
        self._refresh_shapes()
        self._tool_cursor()

    def _save_ruler(self):
        """«Сохранить»: фигура линейки в «Мои метки» с измерением."""
        titles = {"line": tr("Линия"), "path": tr("Путь"),
                  "polygon": tr("Многоугольник"), "circle": tr("Круг"),
                  "path3d": tr("3D-путь"),
                  "polygon3d": tr("3D-многоугольник")}
        name, ok = QInputDialog.getText(
            self, tr("Сохранить измерение"), tr("Название"),
            text=self.new_name(titles[self.ruler.mode]))
        if not ok:
            return
        shape = self.ruler.shape(rubber=False, name=name.strip())
        if shape is None:
            return
        self.myplaces.add(shape, measure=self.ruler_dialog.summary(),
                          folder=self.panel.current_folder())
        self.ruler.clear()

    def _place_action(self, action, key):
        """Действие меню «Моих меток»: тур, папка, перелёт, имя,
        удаление, слои в проект. key "" - корень «Мои метки»."""
        if action == "project":
            self.myplaces.add_to_project()
            return
        if action in ("new_folder", "new_folder_after"):
            # Папка сразу с названием, без окна, переименовывается потом.
            # На метке - сразу под ней, на папке - внутрь, как у GE.
            if action == "new_folder":
                parent, after = key or None, None
            else:
                place = self.myplaces.find(key)
                parent, after = (place.folder if place else None), key
            new = self.myplaces.add_folder(tr("Новая папка"), parent,
                                           after=after)
            if new is not None:
                self.panel.select_place(new)
            return
        if action == "import_kml":
            self.import_kml(key or None)
            return
        if action == "copy":
            self.copy_places([key] if key else [])
            return
        if action == "paste":
            place = self.myplaces.find(key) if key else None
            folder = key if is_folder(key) else (
                place.folder if place is not None else None)
            self.paste_places(folder)
            return
        if action == "export_kml":
            self.export_kml(key or None)
            return
        if action == "tour" and (not key or is_folder(key)):
            self.tour.start(self._tour_stops(key or None))
            return
        item = self.myplaces.find(key)
        if item is None:
            return
        if action == "fly":
            self.fly_to_place(item)
        elif action == "tour":
            stop = self.place_stop(item, along=True)
            stop.time = item.view_time or item.time
            self.tour.start([stop])
        elif action == "properties":
            self._open_place_properties(item)
        elif action == "profile":
            points = list(item.shape.points)
            self._open_profile(item.name, lambda: points, HeightSource(
                self._true_heights, self._has_height_tile,
                self.view.want_tool_heights))
        elif action == "snapshot":
            # «Снимок вида» Google Earth: вид глобуса сейчас становится
            # видом метки, по нему идут перелёт к метке и тур.
            self.myplaces.update(key, {"view": lookat.text(
                self.current_view())})
        elif action == "rename":
            name, ok = QInputDialog.getText(
                self, tr("Переименовать"), tr("Название"), text=item.name)
            if ok:
                self.myplaces.rename(key, name.strip())
        elif action == "remove":
            name = item.name or tr("Без названия")
            if is_folder(key):
                title = tr("Удалить папку")
                question = tr("Удалить папку «{name}» со всем "
                              "содержимым?", name=name)
            else:
                title = tr("Удалить метку")
                question = tr("Удалить «{name}» из «Моих меток»?",
                              name=name)
            answer = QMessageBox.question(self, title, question)
            if answer == enum(QMessageBox, "StandardButton", "Yes"):
                self.myplaces.remove(key)

    def _places_action(self, action, keys):
        """Действие над несколькими выбранными строками «Моих меток»:
        показать, скрыть, удалить."""
        keys = [k for k in keys if self.myplaces.find(k) is not None]
        if not keys:
            return
        if action == "copy":
            self.copy_places(keys)
            return
        if action in ("show", "hide"):
            self.myplaces.set_visible_many(
                {k: action == "show"
                 for k in self.myplaces.with_contents(keys)})
        elif action == "remove":
            if len(keys) == 1:
                self._place_action("remove", keys[0])
                return
            answer = QMessageBox.question(
                self, tr("Удалить выбранное"), tr(
                    "Удалить выбранное из «Моих меток»? Строк {count}, "
                    "папки удаляются со всем содержимым.",
                    count=len(keys)))
            if answer == enum(QMessageBox, "StandardButton", "Yes"):
                self.myplaces.remove_many(keys)

    def _open_place_properties(self, place):
        """Немодальное окно свойств метки. Правки видны на глобусе
        сразу, «OK» записывает их, «Отмена» возвращает прежний вид."""
        key = place.key
        dialog = self.prop_dialogs.get(key)
        if dialog is None:
            dialog = PlaceProperties(place, self,
                                     current_view=self.current_view)
            dialog.setAttribute(enum(Qt, "WidgetAttribute",
                                     "WA_DeleteOnClose"))
            self.prop_dialogs[key] = dialog

            def preview(shape, key=key):
                self.previews[key] = shape
                self._refresh_shapes()

            def done(result, key=key, dialog=dialog):
                self.prop_dialogs.pop(key, None)
                self.previews.pop(key, None)
                if result:
                    self.myplaces.update(key, dialog.values())
                else:
                    self._refresh_shapes()
            dialog.changed.connect(preview)
            dialog.finished.connect(done)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def copy_places(self, keys):
        """Метки и папки keys в буфер обмена текстом KML, как Google
        Earth. Пустой keys - все «Мои метки». Текст открывается
        в блокноте, правится и вставляется обратно."""
        tree = self.myplaces.export_keys(keys) if keys \
            else self.myplaces.export_tree(None)
        text = write_kml(tree)
        mime = QMimeData()
        mime.setText(text)
        mime.setData(KML_MIME, text.encode("utf-8"))
        QApplication.clipboard().setMimeData(mime)
        self.message = (tr("KML в буфере обмена, меток {count}.",
                           count=len(tree.places())), time.monotonic())
        self._show_state()
        return text

    def paste_places(self, folder=None):
        """KML из буфера обмена в папку folder (None - корень «Моих
        меток»). Содержимое ложится само, без новой папки. Возвращает
        количество вставленных меток."""
        mime = QApplication.clipboard().mimeData()
        data = b""
        if mime is not None and mime.hasFormat(KML_MIME):
            data = bytes(mime.data(KML_MIME))
        elif mime is not None and mime.hasText():
            data = mime.text().encode("utf-8")
        tree = None
        if data.strip():
            try:
                tree = read_kml(data, tr("Вставка"))
            except KmlError:
                tree = None
        if tree is None or not tree.children:
            self.message = (tr("В буфере обмена нет меток KML."),
                            time.monotonic())
            self._show_state()
            return 0
        self.myplaces.import_tree(tree, folder, wrap=False)
        count = len(tree.places())
        self.message = (tr("Вставлено меток {count}.", count=count),
                        time.monotonic())
        self._show_state()
        return count

    def import_kml(self, parent=None, path=None):
        """Открыть KML или KMZ в папку parent новой папкой и подлететь
        к содержимому, как Google Earth."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Открыть KML или KMZ"), "",
                tr("KML и KMZ (*.kml *.kmz)"))
        if not path:
            return None
        name = os.path.splitext(os.path.basename(path))[0]
        try:
            with open(path, "rb") as fh:
                tree = read_kml_file(fh.read(), name)
        except (OSError, KmlError) as error:
            QMessageBox.warning(self, tr("Открыть KML или KMZ"), tr(
                "Файл не прочитан: {error}", error=str(error)))
            return None
        places = tree.places()
        if not places:
            QMessageBox.information(self, tr("Открыть KML или KMZ"), tr(
                "В файле нет точек, линий и многоугольников."))
        key = self.myplaces.import_tree(tree, parent)
        if key is not None:
            self.panel.select_place(key)
        points = [p for place in places for p in place.points]
        if points:
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            camera = self.view.camera
            lat, lon, distance = fit_view(min(lons), min(lats), max(lons),
                                          max(lats), camera.fov_y,
                                          camera.aspect)
            self._fly_to(lat, lon, distance)
        return key

    def export_kml(self, folder=None, path=None):
        """Сохранить папку folder (None - все «Мои метки») в KML или KMZ."""
        tree = self.myplaces.export_tree(folder)
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Сохранить как KML"), (tree.name or "PlanetX")
                + ".kmz", tr("KMZ (*.kmz);;KML (*.kml)"))
        if not path:
            return False
        data = write_kmz(tree) if path.lower().endswith(".kmz") \
            else write_kml(tree).encode("utf-8")
        try:
            with open(path, "wb") as fh:
                fh.write(data)
        except OSError as error:
            QMessageBox.warning(self, tr("Сохранить как KML"), tr(
                "Файл не записан: {error}", error=str(error)))
            return False
        return True

    def place_stop(self, place, along=False):
        """Остановка над меткой: вид метки, иначе точка, охват линии
        и многоугольника.

        Вид метки (core/lookat.py) задаёт точку взгляда, расстояние,
        азимут и наклон, как вид метки Google Earth. along - путь
        проезжается вдоль, как в туре Google Earth.
        """
        points = place.shape.points
        name = place.shape.name
        if place.tour:
            # Записанный тур: проигрывание, перелёт - к его началу.
            recorded = RecordedStop(name, place.tour)
            return recorded if along else Stop(
                name, *place.tour[0][1:])
        if along and place.kind == "line" and len(points) > 1:
            return PathStop(name, points)
        if place.view is not None:
            return Stop(name, *place.view)
        if len(points) == 1:
            lat, lon = points[0]
            return Stop(name, lat, lon, SEARCH_MIN_DISTANCE)
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        camera = self.view.camera
        lat, lon, distance = fit_view(min(lons), min(lats), max(lons),
                                      max(lats), camera.fov_y, camera.aspect)
        return Stop(name, lat, lon, distance)

    def fly_to_place(self, place):
        """Перелёт к метке, как остановка тура. Метка другого тела
        сначала переключает тело."""
        if place.body != self.planet.key:
            self.set_body(place.body)
        stop = self.place_stop(place)
        self._fly_to(stop.lat, stop.lon, stop.distance, stop.heading,
                     stop.tilt)
        self._show_time(place.view_time or place.time)

    def _tour_stops(self, folder=None):
        """Остановки тура: отмеченные метки папки folder и вложенных
        папок в порядке списка, None - все «Мои метки»."""
        stops = []
        for place in self.myplaces.places_in(folder):
            # Тур идёт по меткам тела, которое сейчас на глобусе.
            if place.visible and place.body == self.planet.key:
                stop = self.place_stop(place, along=True)
                stop.time = place.view_time or place.time
                stops.append(stop)
        return stops

    def _record_toggled(self, on):
        """Кнопка записи тура: начать или закончить и сохранить."""
        if on:
            self._recording = []
            self._record_start = time.monotonic()
            self._record_sample()
            self._record_timer.start()
            return
        self._record_timer.stop()
        samples = thin(self._recording or [])
        self._recording = None
        if len(samples) < 2 or samples[-1][0] <= 0.0:
            self.message = (tr("Тур не записан, камера не двигалась."),
                            time.monotonic())
            self._show_state()
            return
        default = self.new_name(tr("Тур"))
        name, ok = QInputDialog.getText(self, tr("Сохранить тур"),
                                        tr("Название"), text=default)
        if not ok:
            return
        self.save_recorded(samples, name.strip() or default)

    def save_recorded(self, samples, name):
        """Записанный тур в «Мои метки». Линия метки - точки
        взгляда, на глобусе она не рисуется."""
        points = [(s[1], s[2]) for s in samples]
        return self.myplaces.add(
            Shape("line", points, name=name), tour=list(samples),
            folder=self.panel.current_folder())

    def _record_sample(self):
        """Поза камеры в запись, раз в RECORD_PERIOD."""
        if self._recording is None:
            return
        pose = self.view.navigator.pose
        t = time.monotonic() - self._record_start
        self._recording.append((t, pose.lat, pose.lon, pose.distance,
                                pose.heading, pose.tilt))
        self.message = (tr("Запись тура {clock}. Повторный щелчок "
                           "по кнопке записи её заканчивает.",
                           clock=clock(t)), time.monotonic())
        self._show_state()

    def save_view(self):
        """Вид глобуса меткой в «Моих метках», как в Google Earth.

        Метка стоит в точке взгляда, вид - в поле view.
        """
        default = self.new_name(tr("Вид"))
        name, ok = QInputDialog.getText(self, tr("Сохранить вид"),
                                        tr("Название"), text=default)
        if not ok:
            return
        pose = self.view.navigator.pose
        shape = Shape("point", [(pose.lat, pose.lon)],
                      name=name.strip() or default)
        self.myplaces.add(shape, view=self.current_view(),
                          folder=self.panel.current_folder())

    def current_view(self):
        """Вид глобуса сейчас для метки, core.lookat."""
        pose = self.view.navigator.pose
        return lookat.make(pose.lat, pose.lon, pose.distance,
                           pose.heading, pose.tilt)

    def _fly_extent(self, extent, crs):
        """Перелёт к охвату в системе координат crs, взгляд отвесный."""
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(crs, wgs, QgsProject.instance())
        try:
            box = transform.transformBoundingBox(extent)
        except QgsCsException:
            return
        camera = self.view.camera
        lat, lon, distance = fit_view(box.xMinimum(), box.yMinimum(),
                                      box.xMaximum(), box.yMaximum(),
                                      camera.fov_y, camera.aspect)
        self._fly_to(lat, lon, distance)

    # Определение объектов.

    def _set_identify(self, on):
        self.identifying = bool(on)
        self._tool_cursor()

    def _tool_cursor(self):
        """Перекрестие, пока щелчок по глобусу что-то ставит или ищет."""
        self.view.set_tool_cursor(self.identifying or self._ruler_open()
                                  or self._place_open())

    def _clicked(self, px, py):
        """Щелчок по глобусу: точка линейки или опрос объектов под ней."""
        tool = self.ruler if self._ruler_open() \
            else self.drawer if self._place_open() else None
        if tool is not None:
            if tool is self.ruler and tool.spatial():
                found = self._surface(px, py)
                if found is not None:
                    tool.add(*found)
                return
            found = self._ground(px, py)
            if found is not None:
                tool.add(found[0], found[1])
            return
        if not self.identifying:
            return
        view = self.view
        camera = view.camera
        point = ground_under(camera, px, py, view.navigator.pose.terrain)
        if point is None:
            return
        lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
        # Метров на пиксель кадра в точке щелчка.
        metres = float(((point - camera.eye) ** 2).sum()) ** 0.5 \
            / focal(camera)
        tolerance = IDENTIFY_PIXELS * view.devicePixelRatioF() * metres
        project = QgsProject.instance()
        layers = [project.mapLayer(i) for i in self._applied_layers or ()]
        found = identify([layer for layer in layers if layer is not None],
                         lat, lon, tolerance)
        scale = view.store.scale
        height = h / scale if scale else None
        self._mark("{:.5f}, {:.5f}".format(lat, lon), lat, lon)
        if self.identified is None:
            self.identified = IdentifyDialog(self)
        self.identified.show_result(
            point_text(lat, lon, height, fmt=self.coords), found)

    def _ground(self, px, py):
        """Широта и долгота точки рельефа под пикселем или None."""
        view = self.view
        point = ground_under(view.camera, px, py,
                             view.navigator.pose.terrain)
        if point is None:
            return None
        lat, lon, _ = (float(v) for v in ecef_to_geodetic(point))
        return lat, lon

    def _surface(self, px, py):
        """Точка 3D-линейки под пикселем: широта, долгота и настоящая
        высота над эллипсоидом, на крыше или стене здания, если луч
        встречает его раньше рельефа. None - мимо Земли.

        Рельеф на экране поднят в store.scale раз. Высота точки над
        рельефом при этом настоящая, здания не растягиваются, поэтому
        настоящая высота - нарисованная минус подъём рельефа."""
        view = self.view
        point = view.surface_hit(px, py)
        if point is None:
            return None
        lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
        scale = view.store.scale
        if scale and scale != 1.0:
            drawn = float(view.store.heights_at(np.array([lat]),
                                                np.array([lon]))[0])
            h -= drawn - drawn / scale
        return lat, lon, h

    def drawn_points(self, ruler, rubber=False):
        """Точки 3D-линейки в ECEF так, как они нарисованы: при подъёме
        рельефа высота рельефа под точкой поднята в store.scale раз."""
        xyz = ruler.space_points(rubber)
        scale = self.view.store.scale
        if not len(xyz) or not scale or scale == 1.0:
            return xyz
        lat, lon, h = ecef_to_geodetic(xyz)
        drawn = np.asarray(self.view.store.heights_at(lat, lon))
        return geodetic_to_ecef(lat, lon, h + drawn - drawn / scale)

    def fly_view(self, lat, lon, distance):
        """Перелёт с прежними азимутом и наклоном, для синхронизации."""
        pose = self.view.navigator.pose
        self._fly_to(lat, lon, distance, pose.heading, pose.tilt,
                     focus=False)

    def _fly_to(self, lat, lon, distance, heading=0.0, tilt=0.0,
                focus=True):
        """Перелёт, по умолчанию в конце взгляд отвесный, север вверху."""
        navigator = self.view.navigator
        flight = Flight(navigator.pose, lat, lon, distance, heading, tilt,
                        fov_y=self.view.camera.fov_y)
        navigator.start_flight(flight, time.monotonic())
        if focus:
            self.view.setFocus()
        self.view.update()

    def _show_state(self):
        keys = start_keys()
        done = sum(1 for key in keys if self.view.has(key))
        text, shown = self.message
        if text and time.monotonic() - shown < MESSAGE_TIME:
            self.status.setText(text)
            return
        sky = self.view.sky_view
        if sky is not None:
            # Небо тайлов не грузит, загрузка глобуса стоит без ошибки.
            text = tr("Звёздное небо, поле зрения {fov}°",
                      fov=int(round(sky.fov)))
            if self._cursor_text:
                text += "\n" + self._cursor_text
            self.status.setText(text)
            return
        if self.errors:
            text = tr("Подложка не загрузилась: {error}",
                      error=next(iter(self.errors.values())))
        elif self.overlay_error:
            text = tr("Векторная основа не загрузилась: {error}",
                      error=self.overlay_error)
        elif self.dirty:
            text = tr("Настройки или слои изменились. Глобус покажет их "
                      "после кнопки «Обновить».")
        elif done < len(keys):
            text = tr("Загрузка подложки: {done} из {total}",
                      done=done, total=len(keys))
        elif self.view.error:
            text = tr("Контекст OpenGL 3.3 недоступен: {version}",
                      version=self.view.error)
        else:
            text = tr("Обзор с высоты {height}",
                      height=distance_text(self.view.altitude()))
            text += self._load_text()
            if self._cursor_text:
                text += "\n" + self._cursor_text
            self.status.setText(text)
            return
        # Вставшая загрузка и тяжёлые метки видны и рядом с ошибкой или
        # подсказкой «Обновить».
        self.status.setText(text + self._load_text())

    def _load_text(self):
        """Хвост первой строки: загрузка, вставшая загрузка, объём меток.

        Деградация видна, а не прячется в размытой картинке, решение
        автора от 28 сентября 2026 года (шаг 14).
        """
        view = self.view
        parts = []
        if view.load_stalled:
            parts.append(tr("загрузка стоит {seconds} с",
                            seconds=int(view.load_stalled)))
        elif view.load_missing:
            parts.append(tr("загрузка {count}", count=view.load_missing))
        vertices = view.object_vertices()
        if vertices > OBJECT_BUDGET:
            parts.append(tr("метки тяжёлые, {count} тыс. вершин",
                            count=vertices // 1000))
        return "".join(" · " + part for part in parts)

    # Координаты под курсором.

    def _hovered(self, px, py):
        """Курсор сдвинулся. Точка считается не чаще раза в CURSOR_PERIOD."""
        self._hover = None if px < 0 else (px, py)
        if self._hover is None:
            self._cursor_text = ""
            self._show_state()
        elif not self._cursor_timer.isActive():
            self._cursor_timer.start(CURSOR_PERIOD)

    def _update_cursor(self):
        """Широта, долгота и высота рельефа под курсором."""
        text = ""
        view = self.view
        if self._hover is not None and view.sky_view is not None:
            cam = view.camera
            text = ra_dec_text(view.sky_view.direction_at(
                *self._hover, cam.width, cam.height))
        elif self._hover is not None:
            point = ground_under(view.camera, *self._hover,
                                 view.navigator.pose.terrain)
            if point is not None:
                lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
                if self._ruler_open() and self.ruler.spatial():
                    found = self._surface(*self._hover)
                    if found is not None:
                        self.ruler.set_cursor(found[:2], found[2])
                elif self._ruler_open():
                    self.ruler.set_cursor((lat, lon))
                elif self._place_open():
                    self.drawer.set_cursor((lat, lon))
                scale = view.store.scale
                text = point_text(lat, lon, h / scale if scale else None,
                                  digits=5, fmt=self.coords)
        if text != self._cursor_text:
            self._cursor_text = text
            self._show_state()

    def closeEvent(self, event):
        self.sync.close()
        self.tracks.close()
        self.layer_labels.close()
        if self.identified is not None:
            self.identified.close()
        if self.ruler_dialog is not None:
            self.ruler_dialog.close()
        if self.place_dialog is not None:
            self.place_dialog.close()
        self.loader.abort()
        self.terrain_loader.abort()
        if self.place_loader is not None:
            self.place_loader.abort()
        for loader in list(self.gibs_loaders.values()) + [
                self.sky_loader, self.buildings_loader]:
            if loader is not None:
                loader.abort()
        if self.overlay is not None:
            self.overlay.abort()
        self.refresh_timer.stop()
        set_moving(False)
        if self.properties is not None:
            self.properties.close()
        sys.setswitchinterval(self._switch_interval)
        super().closeEvent(event)
        # Окно с WA_DeleteOnClose Qt уничтожает позже. Плагин узнаёт
        # о закрытии сразу, чтобы меню открыло новое окно, а не это.
        self.closed.emit()