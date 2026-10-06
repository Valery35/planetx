# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно глобуса по образцу 3D-сцены Isoliner3D.

Слева панель: координаты, список источников и слоёв, строка состояния
(ui/panel.py). Справа вид OpenGL, в его левом верхнем углу плавающая
панель значков (ui/toolbar.py), в правом нижнем подпись источников.
Окно связывает части и решает, панели только показывают.
"""
import hashlib
import html
import math
import os
import sys
import time

import numpy as np
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsCsException, QgsProject, QgsRasterLayer,
                       QgsSettings)
from qgis.PyQt.QtCore import QEvent, QMimeData, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QIcon, QImage
from qgis.PyQt.QtWidgets import (QApplication, QFileDialog, QInputDialog,
                                 QLabel, QMessageBox, QSplitter,
                                 QVBoxLayout, QWidget)
from qgis.utils import iface

from ..core import (basemap, clouds, ellipsoid, lookat, stars, sun,
                    temperature, when)
from ..core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ..core.measure import (LENGTH_UNITS, convert, nearest_vertex,
                            number, segment_midpoints, surface_level)
from ..core import graticule, paleo, placetree
from ..core.features import Shape, grown, has_alts
from ..core.coords import FORMATS as COORD_FORMATS, parse_point
from ..core.flight import Flight, Spin, fit_view
from ..core.geocode import (SEARCH_INTERVAL, normalize, parse_places,
                            place_text, search_url)
from ..core.mipmap import mip_chain
from ..core.navigation import Pose, focal, ground_under
from ..core.planets import EARTH_PLANET, PLANETS, planet_by_key
from ..core import assistant as assistant_core
from ..core import searchbar, skydata
from ..core.skydata import direction as sky_direction
from ..core.skyview import SkyView, ra_dec_of, ra_dec_text
from ..core.sync import BOTH, DIRECTIONS
from ..core.slope import aspect_rgba, slope_aspect, slope_rgba
from ..core.terrain import MAX_LEVEL as TERRAIN_MAX, decode
from ..core.kml import KOverlay, KmlError, image_ext as kml_image_ext, \
    read_file as read_kml_file, read_kml, write_kml, write_kmz
from ..core.placetree import is_folder, numbered_name
from ..core.scene import EXTENSION, SceneError, read_scene, write_scene
from ..core.tour import PathStop, RecordedStop, Stop, clock, thin
from ..core.tiling import tile_mesh
from ..core import fires as fires_core
from ..core import (crust, cutaway, insolation, pick, plates, quakes,
                    overlays, section, slabs, themes, viewshed)
from ..core.buildings import EMPTY as NO_BUILDINGS, footprints
from ..core.places import (AS_QGIS, LABEL_LANGUAGES, LOCAL, DecodeError,
                           decode_places, name_languages)
from ..core.places import Place as MarkPlace  # метка найденного места
from ..i18n import tr, ui_language
from ..net.loader import TileLoader, set_moving
from ..core import sources as datasources
from ..net.overlay import (BORDERS, LINE_GROUPS, OPENFREEMAP_ATTRIBUTION,
                           PLACES,
                           RAIL_FROM, RAILWAYS, VECTOR_GROUPS, label_kinds,
                           railway_layer,
                           LayerOverlay, fetch_bytes,
                           fetch_json,
                           openfreemap_layer, plate_layer,
                           set_line_groups)
from ..qt_compat import enum
from ..render.view import OBJECT_BUDGET, GlobeView, start_keys
from .about import show_about
from .identify import Group, IdentifyDialog, identify, point_text
from .layer_labels import LayerLabels, range_key
from .legend import (BedsLegend, CutawayLegend, FireLegend,
                     InsolationLegend, LegendPanel, QuakeLegend,
                     SlopeLegend,
                     TemperatureLegend, ThemeLegend)
from .themes import theme_names
from .overlays import (OUTLINE, BoxVertices, CornerVertices,
                       GroundLayers, OverlayDialog, ScreenOverlays,
                       ground_geotiff, image_rgba)
from .spinner import LoadSpinner
from .draw import PlaceDialog
from . import globemenu
from .handles import DrawVertices, Handles, PropVertices, ShapeEdit
from .measure import GRAB_PIXELS, Ruler, RulerDialog, unit_short
from .measure import _xy as ruler_xy
from .elevation import HeightSource, ProfileDialog
from .section import SectionDialog
from .assistant import (AssistantDialog, current_provider, ready,
                        search_enabled)
from .myplaces import MyPlaces, OverlayItem
from .paleo import PaleoBar
from .panel import LayerPanel
from .project import (AUTO_REFRESH, FOLLOW, ProjectWatch, map_layers,
                      read_flag, read_insets, read_shown,
                      set_visible_on_map, visible_on_map, write_flag,
                      write_insets, write_shown)
from .inset import DeepSource, terrain_prepare
from .sources import SourcesDialog
from .inset import apply as apply_insets
from .inset import prepare as prepare_inset
from .navpad import NavPad
from .skylabels import SkyLabels
from .properties import SCALE_RANGE, PropertiesDialog
from .folderprops import FolderDialog
from .tilesource import TileSourceDialog
from .viewshed import ResultTiles, ViewshedDialog, display_level
from .insolation import InsolationDialog
from .subsurface import SubsurfaceManager, add_to_project, subsurface_ids
from .subsection import ModelSectionDialog, build as model_section
from .record import TourRecorder
from .placeprops import PlaceProperties
from .scene import apply as apply_scene, capture as capture_scene
from .snapshot import SnapshotDialog
from .tour import TourPlayer
from .routing import RouteManager
from .satellites import SatelliteManager
from ..core import satellites as satellites_core
from .track import (TrackDialog, TrackManager, date_range, layer_span,
                    timed_layer)
from .sync import MapSync
from .timebar import TimeBar
from .toolbar import ViewToolbar

VIEWSHED_POLL = 250  # мс между проверками высот видимости
VIEWSHED_WAIT = 30.0  # с, дальше расчёт идёт по тем высотам, что есть
HEIGHT_CHUNK = 20000  # узлов сетки инсоляции за проход цикла событий
CALC_BUDGET = 0.004  # с расчёта инсоляции за проход цикла событий

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
# Прежние запросы строки «Поиск», список строк от новых к старым.
HISTORY_KEY = "PlanetX/search_history"
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
                  "temperature": False, "buildings": False, "sun": False,
                  "slope": False, "aspect": False,
                  "quakes": False, "cutaway": False, "paleo": False,
                  "plates": False, "fires": False, "satellites": False}
# Уклон и экспозиция - один слой вида, включена одна из двух строк.
SURFACE_EXTRAS = ("slope", "aspect")
# Строки раздела «Слои», которые есть только у Земли.
EARTH_EXTRAS = ("clouds", "temperature", "buildings", "sun", "quakes",
                "cutaway", "paleo", "plates", "fires", "satellites")
# Глубины морей и океанов - часть данных рельефа, флажок в свойствах
# вида. Решение автора от 2 октября 2026 года, по умолчанию включены.
SEA_KEY = "PlanetX/sea_depths"
# Файлы модуля: указатель зон плит Slab2 (tools/build_slabs.py).
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
# Автообновление глобуса по умолчанию включено, решение автора от
# 2 октября 2026 года. Флажок хранится в проекте.
AUTO_DEFAULT = True
# Полоса очагов окна «Разрез» в демо «Японский жёлоб», км.
DEMO_QUAKE_BAND = 300.0
SUN_PERIOD = 60000  # мс между пересчётами солнца по часам компьютера
EXTRA_KEY = "PlanetX/show_"  # + ключ строки
THEME_KEY = "PlanetX/theme"  # тема NASA GIBS, "" - выключена
THEME_DELAY = 300  # мс после движения шкалы времени до смены дня темы
# Пауза после движения шкалы времени до новых картинок слоёв проекта
# со временем, мс.
LAYER_TIME_DELAY = 300
# Пауза после движения угла картинки на поверхности до пересборки её
# растра, мс.
GROUND_DELAY = 400
# Шаг проверки картинок по ссылке с обновлением, мс.
LINK_TICK = 1000
# Новая картинка на экране - под панелью значков, пикселей от верха.
SCREEN_TOP = 60.0
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


def slope_prepare(mode, floor, radius, insets=(), encoding="terrarium"):
    """Работа рабочего потока для тайла уклона или экспозиции: высоты
    Terrarium с врезками своего рельефа insets, расчёт core/slope.py,
    раскраска и уровни мипмапов."""
    def prepare(key, rgba):
        heights = decode(rgba, floor, encoding)
        if insets:
            heights = apply_insets(insets, key, heights)
        grade, aspect = slope_aspect(heights, key[0], key[2], radius)
        return mip_chain(aspect_rgba(aspect) if mode == "aspect"
                         else slope_rgba(grade))
    return prepare


def prepare_temperature(key, rgba):
    """Работа рабочего потока для тайла температуры: раскраска GIBS
    с непрозрачностью и уровни мипмапов."""
    return mip_chain(temperature.overlay_rgba(rgba))


def prepare_theme(key, rgba):
    """Работа рабочего потока для тайла темы NASA GIBS: прозрачность
    и уровни мипмапов."""
    return mip_chain(themes.overlay_rgba(rgba))


def prepare_lights(key, rgba):
    """Работа рабочего потока для тайла огней городов: премноженная
    альфа и уровни мипмапов."""
    return mip_chain(themes.overlay_rgba(rgba, 1.0))


def gibs_source(name):
    """Источник и подготовка тайла слоя GIBS по имени слоя вида."""
    if name == "lights":
        return (basemap.Source("NASA Black Marble", sun.LIGHTS_URL,
                               sun.LIGHTS_LEVEL, sun.LIGHTS_ATTRIBUTION,
                               builtin=True), prepare_lights)
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


class _WedgeCorners:
    """Угловые точки разреза Земли, которые тянутся мышью (render/view.py,
    vertex_tool), просьба автора от 2 октября 2026 года. Угол меняет
    свою долготу и свою широту сектора (core.cutaway.move_corner)."""

    def __init__(self, window):
        self.window = window
        self.index = None

    def points(self):
        """Углы сектора без повторов: у полюса два угла совпадают."""
        wedge = self.window.view.wedge
        if wedge is None:
            return []
        out = []
        for n, (lat, lon) in enumerate(cutaway.corners(wedge)):
            if abs(lat) >= 90.0 and n in (1, 3):
                continue
            out.append((n, lat, lon))
        return out

    def grab(self, px, py):
        view = self.window.view
        points = self.points()
        if not points:
            return False
        xyz = geodetic_to_ecef(np.array([p[1] for p in points]),
                               np.array([p[2] for p in points]),
                               np.zeros(len(points)))
        pixels, front = view.camera.project(xyz)
        found = nearest_vertex(pixels, front, px, py,
                               GRAB_PIXELS * view.devicePixelRatioF())
        self.index = None if found is None else points[found][0]
        return self.index is not None

    def move(self, px, py):
        window = self.window
        found = window._ground(px, py)
        wedge = window.view.wedge
        if found is None or self.index is None or wedge is None:
            return
        window.view.set_wedge(cutaway.move_corner(wedge, self.index,
                                                  *found), window.crust)
        window._update_tool_marks()

    def drop(self):
        self.index = None
        # Зоны плит - по новому сектору, когда угол отпущен.
        self.window._want_slabs()


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
        # Кружки вершин рисуемого объекта - тоже под панелью значков.
        self.handles = Handles(self.view)
        self.view.changed.connect(self.handles.sync)
        self.view.show_constellations = QgsSettings().value(
            CONSTELLATIONS_KEY, True, type=bool)
        self._sky_state = None  # взгляд на небо до выхода из него
        # Шкала времени меток, своя, как в Google Earth. Она нужна
        # до первого чтения «Моих меток».
        self.timebar = TimeBar(self.view)
        self._time_range = None
        self.timebar.range_changed.connect(self._time_changed)
        self.timebar.closed.connect(self._time_bar_closed)
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
        self.slope_legend = SlopeLegend(self.view)
        self.slope_legend.hide()
        # Пласты подземной модели.
        self.beds_legend = BedsLegend(self.view)
        self.insolation_legend = InsolationLegend(self.view)
        self.insolation_legend.hide()
        self.quake_legend = QuakeLegend(self.view)
        self.quake_legend.hide()
        self.fire_legend = FireLegend(self.view)
        self.fire_legend.hide()
        self.cutaway_legend = CutawayLegend(self.view)
        self.cutaway_legend.hide()
        # Тема NASA GIBS: выбранная тема и показанный день, ряды дат
        # и шкалы слоёв по ключу темы, ждущие ответы.
        self.theme_key = ""
        self.theme_day = None
        self._theme_shown = None
        self._theme_domains = {}
        self._theme_scales = {}
        self._theme_replies = {}
        self.theme_legend = ThemeLegend(self.view)
        # Шкалы - одной панелью, сверху вниз: тема, пласты, оболочки
        # разреза, очаги, пожары, инсоляция, уклон, температура.
        self.legend_panel = LegendPanel(self.view)
        for legend in (self.theme_legend, self.beds_legend,
                       self.cutaway_legend, self.quake_legend,
                       self.fire_legend, self.insolation_legend,
                       self.slope_legend, self.legend):
            self.legend_panel.add(legend)
        self.legend_panel.changed = self._place_attribution
        # День темы - правый бегунок шкалы времени, смена дня - после
        # паузы в движении бегунка.
        self._theme_open_time = False
        self._theme_timer = QTimer(self)
        self._theme_timer.setSingleShot(True)
        self._theme_timer.setInterval(THEME_DELAY)
        self._theme_timer.timeout.connect(self._apply_theme)
        # Слои проекта со временем рисуются в промежутке шкалы. Картинки
        # слоёв пересобираются после паузы в движении бегунков.
        self._layer_time_timer = QTimer(self)
        self._layer_time_timer.setSingleShot(True)
        self._layer_time_timer.setInterval(LAYER_TIME_DELAY)
        self._layer_time_timer.timeout.connect(self._apply_layer_time)
        # Промежуток, с которым собрано наложение, и охват времени
        # треков и слоёв на шкале.
        self._applied_time = None
        self._data_marks = []
        # Наложения картинок: растры картинок на поверхности в наложении,
        # ключи показанных фото и картинок на экране, текстуры фото,
        # окна свойств и их правки.
        self.ground_layers = GroundLayers()
        self._ground_rasters = []
        self._ground_ids = []
        self._photo_key = None
        self._screen_key = None
        self._photo_images = {}
        self.screen_overlays = ScreenOverlays(self.view)
        self.overlay_dialogs = {}
        self._href_replies = {}
        self._link_images = {}
        # Картинки по ссылке с обновлением: номер пришедшей картинки
        # адреса - часть метки картинки, время последнего запроса.
        self._link_gen = {}
        self._link_asked = {}
        self._link_timer = QTimer(self)
        self._link_timer.setInterval(LINK_TICK)
        self._link_timer.timeout.connect(self._refresh_links)
        self._link_timer.start()
        # Выгрузка в проект, ждущая картинок по ссылкам: (ключи, место).
        self._ground_export = None
        self._overlay_edits = {}
        self._ground_pending = {}
        self._ground_timer = QTimer(self)
        self._ground_timer.setSingleShot(True)
        self._ground_timer.setInterval(GROUND_DELAY)
        self._ground_timer.timeout.connect(self._ground_settled)
        # Палеогеография: ползунок возраста, карта возраста - подложка
        # из тайлов planetx-terrain. Шаги подменяют адрес на локальную
        # копию хранилища.
        self.paleo_bar = PaleoBar(self.view)
        self.paleo_bar.age_changed.connect(self._paleo_age)
        self.paleo_age = 0
        self.paleo_url = paleo.TILE_URL
        self._paleo_sources = {}
        self.paleo_bar.ready = self._paleo_ready
        # Землетрясения: события сводки и ответ на её запрос.
        self.quake_events = []
        self._quake_reply = None
        # Пожары NASA FIRMS: очаги сводки и ждущий ответ.
        self.fire_data = None
        self._fire_reply = None
        # Плиты Slab2 на разрезах: указатель зон с рамками, пришедшие
        # зоны, ждущие ответы. Зона просится, когда разрез её касается.
        # slab_base - шаблон адреса зоны вместо slabs.URL, для проверки
        # на локальной копии хранилища planetx-terrain.
        self.slab_index = None
        self.slab_zones = {}
        # Границы плит PB2002 (core/plates.py) и их слой наложения,
        # читаются при первом включении строки.
        self.plates_data = None
        self.plate_layer = None
        self._slab_replies = {}
        self.slab_errors = {}
        self.slab_base = None
        self._slab_codes = []
        # Разрез Земли: модель коры CRUST1.0, её запрос и ошибка.
        self.crust = None
        self._crust_reply = None
        self.crust_error = ""
        self.quake_error = ""
        self.view.installEventFilter(self)
        self.view.wedge_gain_changed.connect(self._wedge_gain_changed)
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
        self.auto_refresh = read_flag(AUTO_REFRESH, AUTO_DEFAULT)
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
        self.panel.assistant_requested.connect(self.open_assistant)
        self.panel.make_requested.connect(self.make_places)
        self.panel.undo_requested.connect(self.undo_made_places)
        self.panel.stop_requested.connect(self.stop_making)
        self.panel.accept_requested.connect(self.accept_proposed)
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
        # Подсказки строки «Поиск»: метки, прежние запросы, на небе
        # звёзды и созвездия (core/searchbar.py). Панель спрашивает их
        # при вводе. Объекты неба читаются из файла один раз.
        self._sky_objects = None
        # Чего ждёт строка «Поиск»: «assistant» - ответа модели, «search» -
        # ответа службы поиска мест. Пока множество не пусто, у строки
        # вращается значок ожидания.
        self._busy = set()
        self.panel.suggest_source = self.search_suggestions
        self.panel.suggestion_chosen.connect(self.choose_suggestion)
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
        self.panel.places_toggled.connect(self._places_toggled)
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
        # Разрез вниз вдоль пути: окно, точки пути и точка под курсором.
        self.section_dialog = None
        # ИИ-помощник: окно разговора, ui/assistant.py.
        self.assistant_dialog = None
        # Запросы поиска, которые запустил помощник (fly, assistant=False).
        self._tool_queries = set()
        self._section_points = []
        # Углы разреза Земли, которые тянутся мышью.
        self.wedge_corners = _WedgeCorners(self)
        self._section_mark = None
        # Видимость из точки: окно, задание расчёта и тайлы слоя.
        self.viewshed_dialog = None
        self.viewshed_job = None
        self.viewshed_tiles = None
        self.viewshed_result = None
        self.viewshed_timer = QTimer(self)
        self.viewshed_timer.setInterval(VIEWSHED_POLL)
        self.viewshed_timer.timeout.connect(self._viewshed_poll)
        # Инсоляция: то же, расчёт в своём рабочем потоке.
        self.insolation_dialog = None
        self.insolation_job = None
        self.insolation_tiles = None
        self.insolation_result = None
        self.insolation_pool = None
        self.insolation_timer = QTimer(self)
        self.insolation_timer.setInterval(VIEWSHED_POLL)
        self.insolation_timer.timeout.connect(self._insolation_poll)
        self.ruler_vertices = _RulerVertices(self)
        self.view.undo_point.connect(self._undo_point)
        self.ruler_dialog = None
        self.toolbar.ruler_clicked.connect(self._open_ruler)
        # Новая метка: тот же механизм точек, своё окно.
        self.drawer = Ruler(self)
        self.drawer.changed.connect(self._refresh_shapes)
        self.draw_vertices = DrawVertices(self)
        self.handles.tool = self.draw_vertices
        self.drawer.changed.connect(self.handles.sync)
        # Подсказка у курсора - тому, чьи вершины сейчас на глобусе: окно
        # «Новая метка» или окно свойств метки.
        self.view.hovered.connect(
            lambda px, py: self.handles.tool.hover(px, py))
        self.view.menu_requested.connect(self._globe_menu)
        self.place_dialog = None
        self.toolbar.place_clicked.connect(self._open_place)
        # Снимок вида в файл и в макет, по окну на каждое.
        self.shot_dialogs = {}
        self.toolbar.snapshot_clicked.connect(
            lambda: self._open_snapshot(False))
        self.toolbar.layout_clicked.connect(
            lambda: self._open_snapshot(True))
        # Подземный режим: скважины, кровли, разрезы, вырез блока.
        self.subsurface = SubsurfaceManager(self)
        self.model_section_dialog = None
        self.toolbar.subsurface_clicked.connect(self.subsurface.open_dialog)
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
        # Растущие треки точечных слоёв по шкале времени глобуса.
        self.tracks = TrackManager(self.view, self)
        self.tracks.changed.connect(self._refresh_shapes)
        self.tracks.reloaded.connect(self._update_data_marks)
        self._update_data_marks()
        self.panel.track_requested.connect(self._open_track)
        self.panel.inset_toggled.connect(self.set_inset)
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
        self.terrain_loader = None
        self.terrain_errors = {}
        self.sea_depths = QgsSettings().value(SEA_KEY, True, type=bool)
        self.view.sea_floor = self.sea_depths
        # Врезки своего рельефа - растры проекта, кортеж ui.inset.Entry.
        self.insets = ()
        self._load_insets()
        self._start_terrain(
            DeepSource("Terrarium", self._terrain_choice()[0], TERRAIN_MAX),
            self._earth_floor())
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
        self._fill_basemaps()
        self.panel.basemap_chosen.connect(self._panel_basemap)
        self.panel.add_source_requested.connect(self.add_tile_source)
        settings = QgsSettings()
        self.extras = {key: settings.value(EXTRA_KEY + key, default,
                                           type=bool)
                       for key, default in EXTRA_DEFAULTS.items()}
        # При открытии окна - нынешняя Земля. Палеогеография - отдельный
        # режим, она включается строкой и не переживает закрытие окна,
        # решение автора от 3 октября 2026 года.
        if "paleo" in self.extras:
            self.extras["paleo"] = False
            settings.setValue(EXTRA_KEY + "paleo", False)
        self.panel.set_extras(self.extras)
        self.panel.extra_toggled.connect(self.set_extra)
        # Спутники CelesTrak - строка с группами (ui/satellites.py).
        self.satellite_manager = SatelliteManager(self)
        self.satellite_manager.changed.connect(self._show_attribution)
        self.panel.set_satellite_groups(self.satellite_manager.groups)
        self.panel.satellite_groups_changed.connect(
            self.satellite_manager.set_groups)
        self.route_manager = RouteManager(self)
        self.route_manager.finished.connect(self._route_done)
        self.panel.route_link.connect(self.route_manager.link)
        self.grid_shapes = []
        self._grid_key = None
        self.layer_labels = LayerLabels(self)
        self.layer_labels.changed.connect(self._show_layer_labels)
        self.view.changed.connect(self._update_layer_labels)
        self.view.changed.connect(self._update_grid)
        for key, on in self.extras.items():
            self._apply_extra(key, on)
        self.panel.theme_chosen.connect(self.set_theme)
        # Включённые пожары - тоже выбор темы, иначе пустая тема
        # выключила бы их.
        self.set_theme("fires" if self.extras.get("fires")
                       else settings.value(THEME_KEY, "") or "")
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
                "auto": self.auto_refresh, "coords": self.coords,
                "sea": self.sea_depths}

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
        self._fill_basemaps()
        self._changed()

    def _fill_basemaps(self):
        """Группа «Основа» панели: источники Земли или снимки тела."""
        if self.planet.earth:
            names = [tr("{name} - пример", name=s.name) if s.example
                     else s.name for s in self.sources]
            self.panel.set_basemaps(names, self._basemap)
        else:
            self.panel.set_basemaps([], 0, own=self.planet.imagery[0])

    def _panel_basemap(self, index):
        """Подложка выбрана в панели - сразу на глобус, как флажки
        раздела «Слои»."""
        self.choose_basemap(index)
        self._sync_properties()
        self.refresh()

    def add_tile_source(self):
        """Окно «Новый источник тайлов». Источник ложится подключением
        XYZ QGIS и сразу становится подложкой."""
        pose = self.view.navigator.pose
        dialog = TileSourceDialog(self, (pose.lat, pose.lon))
        if not dialog.exec():
            return
        self.sources = basemap.builtins() + xyz_sources()
        names = [s.name for s in self.sources]
        index = names.index(dialog.saved_name) \
            if dialog.saved_name in names else self._basemap
        if self.properties is not None:
            # Список подложек окна свойств строится при открытии.
            self.properties.close()
            self.properties = None
        if iface is not None and hasattr(iface, "reloadConnections"):
            iface.reloadConnections()
        self._panel_basemap(index)

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
        if key in SURFACE_EXTRAS and on:
            # Уклон и экспозиция занимают один слой: вторая строка гаснет.
            other = SURFACE_EXTRAS[1 - SURFACE_EXTRAS.index(key)]
            self.extras[other] = False
            QgsSettings().setValue(EXTRA_KEY + other, False)
            self.panel.set_extras({other: False})
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
            self._update_timebar()
        elif key in SURFACE_EXTRAS:
            self._set_surface()
        elif key == "quakes":
            self._set_quakes(on)
        elif key == "fires":
            self._set_fires(on)
        elif key == "cutaway":
            self._set_cutaway(on)
        elif key == "paleo":
            self._set_paleo(on)
        elif key == "plates":
            self._set_plates(on)
        elif key == "satellites":
            self.satellite_manager.set_on(on)
            self._update_timebar()

    def _clock_on(self):
        """Нужны ли часы глобуса: Солнце или спутники на Земле, вид
        неба. Тогда шкала времени открывается и без данных."""
        view = getattr(self, "view", None)
        if view is not None and view.sky_view is not None:
            return True
        extras = getattr(self, "extras", {})
        planet = getattr(self, "planet", None)
        earth = planet is None or planet.earth
        return earth and bool(extras.get("sun")
                              or extras.get("satellites"))

    def satellite_span(self):
        """Момент спутников, секунды UTC: правый бегунок открытой шкалы
        времени или None - часы компьютера."""
        span = getattr(self, "_time_range", None)
        if span is not None and math.isfinite(span[1]):
            return span[1]
        return None

    # Темы NASA GIBS.

    def set_theme(self, key):
        """Тема NASA GIBS из групп раздела «Слои», "" - выключить.
        Включена одна тема, выбор помнят настройки QGIS. Выбранная тема
        открывает шкалу времени на последний день ряда, когда он придёт.
        Новая тема при открытой шкале берёт её момент."""
        # Пожары - в том же выборе: пожары или одна тема. Просьба
        # автора от 5 октября 2026 года.
        fires = key == "fires"
        if bool(self.extras.get("fires")) != fires:
            self.set_extra("fires", fires)
        key = key if key in themes.BY_KEY else ""
        self._theme_open_time = bool(key) and key != self.theme_key \
            and not self.timebar.shown()
        self.theme_key = key
        QgsSettings().setValue(THEME_KEY, key)
        self.panel.set_theme("fires" if fires else key)
        self._show_theme()

    def _theme_on(self):
        return bool(self.theme_key) and self.planet.earth \
            and self.view.sky_view is None

    def _show_theme(self):
        """Тема на глобус или с глобуса. Ряд дат и шкала слоя
        просятся при первом показе темы, ответы помнятся."""
        self._time_mode()
        if not self._theme_on():
            self._theme_shown = None
            self.theme_day = None
            self._set_gibs("theme", False)
            self.theme_legend.hide()
            self._place_attribution()
            return
        theme = themes.BY_KEY[self.theme_key]
        if theme.key not in self._theme_domains:
            self._theme_fetch(theme.key, "domains", theme.domains_url())
        if theme.colormap and theme.key not in self._theme_scales:
            self._theme_fetch(theme.key, "scale", theme.colormap_url())
        self._update_timebar()
        self._apply_theme()

    def _theme_fetch(self, key, kind, url):
        if (key, kind) in self._theme_replies:
            return
        self._theme_replies[(key, kind)] = fetch_bytes(
            url, lambda data, error, key=key, kind=kind:
            self._theme_done(key, kind, data, error))

    def _theme_done(self, key, kind, data, error):
        self._theme_replies.pop((key, kind), None)
        if kind == "domains":
            if data is None:
                self.message = (tr("Ряд дат темы не загрузился: {error}",
                                   error=error), time.monotonic())
                self._show_state()
                return
            self._theme_domains[key] = themes.parse_domains(data)
            self._update_timebar()
        else:
            self._theme_scales[key] = themes.parse_colormap(data) \
                if data else None
        if key == self.theme_key:
            self._apply_theme()

    def _time_mode(self):
        """Одно время вида: покрытию нужен момент, событиям - промежуток.
        Без событий шкала - один бегунок, при теме у шкалы шаги по ряду
        темы. Решение автора от 5 октября 2026 года."""
        theme = getattr(self, "theme_key", "") and self._theme_on()
        events = any(p.visible and p.time for p in self.myplaces.places) \
            or bool(self.extras.get("quakes")
                    and self.view.quakes.events) \
            or bool(self.extras.get("fires")
                    and self.view.fires.fires is not None) \
            or bool(self._data_marks)
        # Часам, как и покрытию, нужен момент.
        point = (bool(theme) or self._clock_on()) and not events
        if self.timebar.track.point != point:
            self.timebar.set_point(point)
        self.timebar.set_stepper(self._theme_step if theme else None)
        self.timebar.ready = self._theme_ready if theme else None

    def _theme_step(self, moment, delta):
        """Момент соседнего дня ряда темы для шага шкалы или None."""
        intervals = self._theme_domains.get(self.theme_key)
        if not intervals:
            return None
        days = themes.days(intervals)
        day = themes.pick_day(intervals, moment)
        if day not in days:
            return None
        index = days.index(day) + delta
        if not 0 <= index < len(days):
            return None
        return themes.moment(days[index])

    def _theme_ready(self):
        """Показан ли день темы: все картинки кадра пришли. Показ дней
        подряд ждёт этого."""
        layer = self.view.gibs["theme"]
        return not layer.missing and not layer.pending

    def theme_moment(self):
        """Момент дня темы: правый бегунок открытой шкалы времени, без
        неё - None, последний день ряда."""
        if self.timebar.shown():
            hi = self.timebar.range()[1]
            if math.isfinite(hi):
                return hi
        return None

    def _apply_theme(self):
        """День темы по шкале времени, слой вида и шкала в углу. Смена
        дня той же темы держит прежние картинки до замены."""
        if not self._theme_on():
            return
        theme = themes.BY_KEY[self.theme_key]
        intervals = self._theme_domains.get(theme.key)
        if intervals is None:
            return
        found = themes.span(intervals)
        if getattr(self, "_theme_open_time", False) and found:
            # Выбранная тема: шкала открывается на последнем дне ряда.
            self._theme_open_time = False
            if self.timebar.known:
                if not self.timebar.shown():
                    self.timebar.open_bar()
                    self.toolbar.set_time_shown(True)
                lo, hi = self.timebar.range()
                self.timebar.set_range(lo if lo < found[1] else found[1],
                                       found[1])
                self._time_range = self.timebar.range()
                self._refresh_shapes()
        day = themes.pick_day(intervals, self.theme_moment())
        if day is None:
            self.message = (tr("У темы нет дат в ряду."), time.monotonic())
            self._show_state()
            return
        self.theme_day = day
        name = theme_names()[theme.key][0]
        scale = self._theme_scales.get(theme.key)
        units = scale["units"] if scale else ""
        title = tr("{name}, {units} · {day}", name=name, units=units,
                   day=day) if units else tr("{name} · {day}", name=name,
                                             day=day)
        self.theme_legend.set_theme(title, scale)
        self.theme_legend.show()
        self._place_attribution()
        if (theme.key, day) == self._theme_shown:
            return
        keep = self._theme_shown is not None \
            and self._theme_shown[0] == theme.key
        self._theme_shown = (theme.key, day)
        source = basemap.Source("NASA GIBS", theme.url(day), theme.level,
                                themes.ATTRIBUTION, builtin=True,
                                missing=(404,))
        self.view.gibs["theme"].max_level = theme.level
        self._set_gibs("theme", True, (source, prepare_theme), keep=keep)
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
        # Огни городов - вместе с солнцем, загрузчик - при смене.
        if on != getattr(self, "_lights_on", False):
            self._lights_on = on
            self._set_gibs("lights", on, cache=True)
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
            self._tilejson = fetch_json(self._vector_choice(),
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
        self.layer_labels.time_range = self._layer_range()
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

    def _surface_source(self):
        """Тайлы высот тела для уклона: (источник, пол высот) или None,
        если высот у тела нет."""
        if self.planet.earth:
            return basemap.Source("Terrarium", self._terrain_choice()[0],
                                  TERRAIN_MAX, builtin=True), \
                self._earth_floor(), self.insets
        if self.planet.terrain is None:
            return None
        name, url, level, _ = self.planet.terrain
        return basemap.Source(name, url, level, builtin=True), None, ()

    def _set_surface(self):
        """Слой уклона или экспозиции по строкам раздела «Слои» и телу.
        Тайлы высот берутся через кэш QGIS, слой считается из них
        в рабочем потоке (core/slope.py)."""
        mode = next((k for k in SURFACE_EXTRAS if self.extras.get(k)),
                    None)
        found = self._surface_source()
        if mode is None or found is None or self.view.sky_view is not None:
            self._set_gibs("slope", False)
            self.slope_legend.hide()
            return
        source, floor, insets = found
        self.view.gibs["slope"].max_level = source.max_level
        encoding = self._terrain_choice()[1] if self.planet.earth \
            else "terrarium"
        self._set_gibs("slope", True, (source, slope_prepare(
            mode, floor, ellipsoid.A, insets, encoding)), cache=True)
        self.slope_legend.set_mode(mode)
        self.slope_legend.show()
        self._place_attribution()

    def _set_gibs(self, name, on, made=None, cache=False, keep=False):
        """Слой NASA GIBS вида - облака, море или суша: новый загрузчик
        или никакого. Ответы GIBS запрещают кэш, поэтому мимо него.
        made - (источник, подготовка) своего слоя, как у уклона."""
        old = self.gibs_loaders.pop(name, None)
        if old is not None:
            old.abort()
            old.deleteLater()
        loader = None
        if on:
            source, prepare = made or gibs_source(name)
            loader = TileLoader(source, parent=self, prepare=prepare,
                                size=TILE_SIZE, cache=cache)
            loader.loaded.connect(
                lambda key, rgba, levels, name=name:
                self.view.add_gibs(name, key, levels))
            self.gibs_loaders[name] = loader
        self.view.set_gibs(name, on, loader, keep=keep)
        self._show_attribution()

    def set_relief(self, on):
        """Включить или выключить рельеф, сразу, флажком панели «Слои»."""
        self._relief = bool(on)
        QgsSettings().setValue(RELIEF_KEY, self._relief)
        self.panel.set_geo(self._groups, self._relief)
        self.view.set_relief(self._relief_target())
        self.subsurface.relief_changed()
        self._place_quakes()
        self._place_fires()
        if self._relief and self.terrain_loader is not None:
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
        """Масштаб рельефа. У тела без высот рельефа нет. В палеогеографии
        рельеф выключен: нынешние горы на берегах прошлого лишние, решение
        автора от 4 октября 2026 года. Настройка рельефа не меняется."""
        if not self.planet.earth and self.planet.terrain is None:
            return 0.0
        if getattr(self, "extras", {}).get("paleo") and self._paleo_on():
            return 0.0
        return self._scale if self._relief else 0.0

    def _start_terrain(self, source, floor):
        """Загрузчик высот источника source или никакого (None).
        floor - нижний предел высот, core.terrain.decode."""
        old = self.terrain_loader
        if old is not None:
            old.abort()
            old.deleteLater()
        self.terrain_errors.clear()
        self.terrain_loader = None
        if source is not None:
            # Высоты Земли - с врезками своего рельефа и тайлами глубже
            # уровня 15 внутри их рамок (ui/inset.py).
            earth = isinstance(source, DeepSource)
            insets = self.insets if earth else ()
            encoding = self._terrain_choice()[1] if earth else "terrarium"
            self.view.store.deep = [entry.box() for entry in insets]
            self.terrain_loader = TileLoader(
                source, parent=self,
                prepare=terrain_prepare(insets, floor, encoding))
            self.terrain_loader.loaded.connect(self._heights)
            self.terrain_loader.failed.connect(
                self.terrain_errors.__setitem__)
            if self._relief:
                self.terrain_loader.want((0, 0, 0), 1.0)
        self.view.terrain_loader = self.terrain_loader

    # Источники данных.

    def _terrain_choice(self):
        """Адрес и запись высот рельефа Земли: свой из окна «Источники
        данных» или Terrarium."""
        settings = QgsSettings()
        return datasources.terrain(
            settings.value(datasources.TERRAIN_KEY, "") or "",
            settings.value(datasources.ENCODING_KEY, "") or "")

    def _terrain_credit(self):
        url = self._terrain_choice()[0]
        if url == datasources.TERRAIN_URL:
            return TERRAIN_ATTRIBUTION
        text = QgsSettings().value(datasources.TERRAIN_CREDIT_KEY, "") or ""
        return html.escape(text or tr("Рельеф: свой источник"))

    def _vector_choice(self):
        """Адрес TileJSON векторной основы: свой или OpenFreeMap."""
        return datasources.vector(
            QgsSettings().value(datasources.VECTOR_KEY, "") or "")

    def _vector_credit(self):
        if self._vector_choice() == datasources.VECTOR_TILEJSON:
            return link_html(*OPENFREEMAP_ATTRIBUTION)
        text = QgsSettings().value(datasources.VECTOR_CREDIT_KEY, "") or ""
        return html.escape(text or tr("Основа: свой источник"))

    def sources_changed(self, what):
        """Окно «Источники данных» сменило адрес: "terrain" - рельеф
        заново, "vector" - векторная основа, надписи и здания заново,
        "basemaps" - список подложек."""
        if what == "terrain":
            self._refresh_relief()
        elif what == "vector":
            if self.buildings_loader is not None:
                self.buildings_loader.abort()
                self.buildings_loader.deleteLater()
                self.buildings_loader = None
            self.ofm_layer = None
            self.rail_layer = None
            self._ofm_source = None
            self._tilejson = fetch_json(self._vector_choice(),
                                        self._tilejson_done)
        elif what == "basemaps":
            name = self.sources[self._basemap].name
            self.sources = basemap.builtins() + xyz_sources()
            names = [s.name for s in self.sources]
            if self.properties is not None:
                self.properties.close()
                self.properties = None
            if iface is not None and hasattr(iface, "reloadConnections"):
                iface.reloadConnections()
            self._panel_basemap(names.index(name) if name in names else 0)
        self._show_attribution()
        self.view.update()

    def _earth_floor(self):
        """Пол высот Земли: 0 - отрицательные высоты обнуляются, как
        прежде, None - с дном океана они остаются."""
        return None if self.sea_depths else 0.0

    def set_sea_depths(self, on):
        """Глубины морей и океанов флажком окна свойств вида."""
        self.sea_depths = bool(on)
        QgsSettings().setValue(SEA_KEY, self.sea_depths)
        self._set_sea_floor(self.sea_depths and self.planet.earth)
        self._sync_properties()

    def _set_sea_floor(self, on):
        """Глубины морей и океанов: высоты Земли заново, с впадинами
        ниже нуля или без них, и вода над ними."""
        self.view.sea_floor = on
        if not self.planet.earth:
            return
        self._body_terrain(self.planet)
        self.view.reset_heights()
        # Уклон и экспозиция тоже считают дно.
        self._set_surface()

    def _set_cutaway(self, on):
        """Разрез Земли строкой раздела «Слои»: сектор под точкой
        взгляда в момент включения."""
        self.cutaway_legend.setVisible(on)
        self._place_attribution()
        if not on:
            self.view.set_wedge(None)
            if self.view.vertex_tool is self.wedge_corners:
                self.view.vertex_tool = None
            self._update_tool_marks()
            self._wedge_gain_changed()
            self._show_slabs()
            return
        if self.view.wedge is None:
            pose = self.view.navigator.pose
            self.view.set_wedge(cutaway.wedge_at(pose.lat, pose.lon),
                                self.crust)
            self._wedge_gain_changed()
            self._want_slabs()
        if self.view.vertex_tool is None:
            self.view.vertex_tool = self.wedge_corners
        self._update_tool_marks()
        self._want_crust()
        self._show_attribution()

    def set_wedge_box(self, west, east, south, north):
        """Сектор разреза Земли по границам в градусах, при включённой
        строке «Разрез Земли». Так его ставят помощник и сцена."""
        if not self.planet.earth or not self.extras.get("cutaway"):
            return False
        self.view.set_wedge(cutaway.make_wedge(west, east, south, north),
                            self.crust)
        self._wedge_gain_changed()
        self._want_slabs()
        self._update_tool_marks()
        return True

    def _wedge_gain_changed(self):
        """Растяжение коры сменилось: очаги и шкала оболочек следом."""
        self.cutaway_legend.set_gain(self.view.wedge_gain)
        self._place_attribution()
        if self.view.quakes.events:
            self._place_quakes()

    def _crust_done(self, data, error):
        self._crust_reply = None
        self.crust_error = error
        if data is not None:
            try:
                self.crust = crust.from_archive(data)
            except crust.CrustError as problem:
                self.crust_error = str(problem)
        self._refresh_identified()
        self.cutaway_legend.set_crust(self.crust is not None)
        self._place_attribution()
        if self.crust is not None and self.view.wedge is not None:
            self.view.set_wedge(self.view.wedge, self.crust)
        self._show_attribution()
        self._refresh_section()

    def _want_crust(self):
        """Модель коры CRUST1.0: не распространяется с модулем, она
        скачивается с сайта UCSD и дальше берётся из кэша QGIS."""
        if self.crust is None and self._crust_reply is None \
                and not self.crust_error:
            self._crust_reply = fetch_bytes(crust.URL, self._crust_done)

    def _read_slab_index(self):
        if self.slab_index is None:
            with open(os.path.join(DATA_DIR, "slab2_index.json"),
                      encoding="utf-8") as fh:
                self.slab_index = slabs.read_index(fh.read())
        return self.slab_index

    def _want_slabs(self):
        """Зоны плит Slab2, которых касается разрез: пришедшие - на
        грани, недостающие - в запрос. Указатель зон лежит в модуле."""
        wedge = self.view.wedge
        if wedge is None:
            return
        codes = slabs.touched(self._read_slab_index(),
                              *cutaway.arc_points(wedge))
        self._slab_codes = codes
        self._request_slabs(codes)
        self._show_slabs()

    def _request_slabs(self, codes):
        """Файлы зон плит, которых ещё нет, - в запрос. Ждущие запросы
        входят в счётчик загрузки вида, его показывает значок."""
        for code in codes:
            if code in self.slab_zones or code in self._slab_replies \
                    or code in self.slab_errors:
                continue
            self._slab_replies[code] = fetch_bytes(
                slabs.url_of(code, self.slab_base),
                lambda data, error, code=code: self._slab_done(
                    code, data, error))
        self._count_pending()
        self.view.update()

    def _slab_done(self, code, data, error):
        self._slab_replies.pop(code, None)
        self._count_pending()
        if data is None:
            self.slab_errors[code] = error
        else:
            try:
                self.slab_zones[code] = slabs.load(data, code)
            except slabs.SlabError as problem:
                self.slab_errors[code] = str(problem)
        self._show_slabs()
        self._refresh_section()
        self._refresh_identified()

    def _refresh_identified(self):
        """Окно «Объекты» открыто - место в нём уточняется."""
        if self.identified is not None and self.identified.isVisible():
            self._show_identified()

    def _show_slabs(self):
        """Пришедшие зоны разреза - на грани, подпись источника и строка
        шкалы оболочек следом."""
        codes = self._slab_codes
        zones = [self.slab_zones[c] for c in codes if c in self.slab_zones] \
            if self.view.wedge is not None else []
        self.view.set_wedge_slabs(zones)
        self.cutaway_legend.set_slabs(bool(zones))
        self._place_attribution()
        self._show_attribution()

    def _depth_map(self):
        """Глубины на экране очагов: при разрезе Земли - с растяжением
        коры, иначе None."""
        gain = self.view.wedge_gain
        if self.view.wedge is None or gain == 1.0:
            return None
        return lambda depth: cutaway.stretch(depth, gain)

    def _paleo_on(self):
        return bool(self.extras.get("paleo")) and self.planet.earth \
            and self.view.sky_view is None

    def _set_paleo(self, on):
        """Палеогеография строкой раздела «Слои»: ползунок возраста,
        гладкая основа и берега материков на этот возраст."""
        shown = self._paleo_on()
        self.paleo_bar.setVisible(shown)
        self.view.plain_base = shown
        if self._relief_target() != self.view.store.scale:
            self.view.set_relief(self._relief_target())
            self._place_quakes()
            self._place_fires()
        self._place_attribution()
        if not shown:
            self.paleo_bar.stop()
            if self.planet.earth:
                self._switch_basemap(self._earth_source())
            self._show_attribution()
            return
        self._paleo_age(self.paleo_bar.age())

    def _paleo_age(self, age):
        """Карта возраста age млн лет - подложка. Уровни 0-2 прежнего
        возраста стоят на экране, пока не придут новые, глубокие тайлы
        снимаются сразу (change_source, coarse): кадр не смешивает два
        возраста, новый встаёт грубым и уточняется."""
        self.paleo_age = age
        if self._paleo_on():
            self._switch_basemap(self._earth_source(), coarse=True)

    def _paleo_source(self, age):
        """Источник тайлов карты возраста age, один на возраст: смена
        источника сравнивается по тождеству."""
        url = self.paleo_url.format(age=age, z="{z}", x="{x}", y="{y}")
        found = self._paleo_sources.get(url)
        if found is None:
            found = basemap.Source(tr("{age} млн лет назад", age=age), url,
                                   paleo.MAX_LEVEL, paleo.ATTRIBUTION,
                                   builtin=True, missing=(404,))
            self._paleo_sources[url] = found
        return found

    def _earth_source(self):
        """Подложка Земли: карта возраста в палеогеографии, иначе
        выбранная в группе «Основа»."""
        if self._paleo_on():
            return self._paleo_source(self.paleo_age)
        return self.sources[self._basemap]

    def _paleo_ready(self):
        """Показан ли нынешний возраст: уровни 0-2 его карты на экране
        и ни одного тайла прежней карты в кадре. Показ ждёт этого, иначе
        шаги обгоняют загрузку."""
        view = self.view
        keep = view.selection.keep if view.selection else ()
        return all(key in view.textures and key not in view.stale
                   for key in start_keys()) \
            and not any(key in view.stale for key in keep)

    def _count_pending(self):
        """Ждущие ответы зон плит - в счётчик загрузки вида, его
        показывает значок загрузки."""
        self.view.data_pending = len(self._slab_replies)

    def _quake_legend_state(self):
        """Шкала глубины очагов - при очагах на Земле."""
        on = self.extras.get("quakes", False) and self.planet.earth \
            and self.view.sky_view is None
        self.quake_legend.setVisible(on)
        self._place_attribution()

    def _set_fires(self, on):
        """Пожары - строка группы «Планета огня» в общем выборе тем.
        Сводка NASA FIRMS за 24 часа загружается при каждом включении.
        Включённые пожары снимают тему."""
        if on and self.theme_key:
            self.set_theme("fires")
        self.panel.set_theme("fires" if on else self.theme_key)
        self.fire_legend.setVisible(on and self.planet.earth
                                    and self.view.sky_view is None)
        self._place_attribution()
        if not on:
            if self._fire_reply is not None:
                self._fire_reply.abort()
            self._fire_reply = None
            self._place_fires()
            return
        if self._fire_reply is None:
            self._fire_reply = fetch_bytes(fires_core.FEED, self._fires_done,
                                           prefer_cache=False)
            self.view.data_pending += 1

    def _fires_done(self, data, error):
        if self._fire_reply is not None:
            self.view.data_pending = max(0, self.view.data_pending - 1)
        self._fire_reply = None
        if data is not None:
            self.fire_data = fires_core.parse(data.decode("utf-8",
                                                          "replace"))
        else:
            self.message = (tr("Сводка пожаров не загрузилась: {error}",
                               error=error), time.monotonic())
            self._show_state()
        self._place_fires()

    def _place_fires(self):
        """Очаги на глобус по нынешнему масштабу рельефа."""
        on = self.extras.get("fires", False) and self.planet.earth
        self.view.fires.set_fires(self.fire_data if on else None,
                                  self.view.store.scale,
                                  self._surface_ground)
        self._update_timebar()
        self._time_quakes()
        self._show_attribution()
        self.view.update()

    def _set_quakes(self, on):
        """Землетрясения строкой раздела «Слои». Сводка USGS
        загружается при каждом включении, кэш QGIS отдаёт её только
        по заголовкам сервера."""
        if not on:
            if self._quake_reply is not None:
                self._quake_reply.abort()
            self._quake_reply = None
            self.view.quakes.set_events([], 0.0, None)
            self._update_timebar()
            self._quake_legend_state()
            self._show_attribution()
            self.view.update()
            return
        self._quake_legend_state()
        self._want_quakes()

    def _want_quakes(self):
        """Сводка землетрясений USGS, если её запроса ещё нет."""
        if self._quake_reply is None:
            self._quake_reply = fetch_json(quakes.FEED, self._quakes_done,
                                           prefer_cache=False)

    def _quakes_done(self, data, error):
        self._quake_reply = None
        self.quake_error = error
        if data is not None:
            self.quake_events = quakes.parse(data)
        self._place_quakes()
        self._refresh_section()

    def _place_quakes(self):
        """События на глобус по нынешнему масштабу рельефа. Эпицентр
        стоит на рельефе из хранилища высот, грубом вдали от вида."""
        on = self.extras.get("quakes", False) and self.planet.earth
        events = self.quake_events if on else []
        # При разрезе Земли очаги растягиваются по глубине, как кора.
        self.view.quakes.set_events(events, self.view.store.scale,
                                    self._surface_ground, self._depth_map())
        self._update_timebar()
        self._time_quakes()
        self._show_attribution()
        self.view.update()

    def _surface_ground(self, lats, lons):
        """Высоты нарисованной поверхности: с дном океана - дно."""
        return self._true_heights(lats, lons)

    def _surface_heights(self, lats, lons):
        """Высоты поверхности для видимости и инсоляции: с дном океана
        над водой - уровень моря, а не дно."""
        heights = self._true_heights(lats, lons)
        if self.view.sea_floor:
            heights = np.maximum(heights, 0.0)
        return heights

    def _body_terrain(self, planet):
        """Высоты тела: Terrarium у Земли, архив у Марса и Луны.
        Архив тела скачивается, когда рельеф включён."""
        if planet.earth:
            self.view.store.max_level = TERRAIN_MAX
            self._start_terrain(DeepSource(
                "Terrarium", self._terrain_choice()[0], TERRAIN_MAX),
                self._earth_floor())
            return
        self.view.store.deep = []
        self._start_terrain(None, None)
        if planet.terrain is None:
            return
        name, url, level, _ = planet.terrain
        self.view.store.max_level = level
        # Впадины тел ниже нуля остаются, пол не ставится.
        self._start_terrain(basemap.Source(name, url, level,
                                           builtin=True), None)

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
        # Видимость, инсоляция и подземное считались по высотам
        # прежнего тела.
        self._clear_viewshed()
        self._clear_insolation()
        self.subsurface.clear()
        # Разрез вниз - земной: кора, плиты и очаги есть только у Земли.
        if self.section_dialog is not None:
            self.section_dialog.close()
        ellipsoid.set_body(planet.body)
        if planet.earth:
            source = self._earth_source()
        else:
            name, url, top, text, link = planet.imagery
            # Снимки тел лежат в S3: отсутствующий тайл - ответ 403.
            source = basemap.Source(name, url, top, (text, link),
                                    builtin=True, missing=(403, 404))
        old = self.loader
        old.abort()
        old.deleteLater()
        self.errors.clear()
        self.source = source
        self._start_loader()
        self.view.change_body(source.max_level, planet.air)
        self.loader.want_many((key, -key[0]) for key in start_keys())
        # Вода над впадинами - только у Земли.
        self.view.sea_floor = self.sea_depths and planet.earth
        self._body_terrain(planet)
        self.view.set_relief(self._relief_target())
        self.view.reset_places(self.source.max_level)
        self.view.label_kinds = label_kinds(self._groups) \
            if planet.earth else set()
        self._update_overlay()
        self._update_layer_labels(force=True)
        for extra in EARTH_EXTRAS:
            self._apply_extra(extra, self.extras.get(extra, False))
        self._show_theme()
        self._set_surface()
        if not planet.earth:
            # Отжатые кнопки сами выключают синхронизацию и опрос.
            self.toolbar.sync.setChecked(False)
            self.toolbar.identify.setChecked(False)
        self.toolbar.sync.setEnabled(planet.earth)
        self.toolbar.identify.setEnabled(planet.earth)
        self.panel.set_earth(planet.earth,
                             relief=planet.terrain is not None)
        self._fill_basemaps()
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
        return (bar.ruler_button, bar.sync, bar.identify)

    def body_key(self):
        """Ключ того, что на экране: тело глобуса или "sky"."""
        return "sky" if self.view.sky_view is not None else self.planet.key

    def sky_moment(self):
        """Момент светил неба: конец открытой шкалы времени, иначе
        None - часы компьютера."""
        return self.sun_time() if self.timebar.shown() else None

    def show_sky(self, ra=None, dec=None, fov=None):
        """Вид звёздного неба из центра небесной сферы. ra, dec, fov -
        взгляд в градусах, None - прежний взгляд или начальный."""
        view = self.view
        if view.sky_view is None:
            # Поза глобуса вернётся при выходе: в небе навигатор
            # ведёт взгляд на небо, core.skyview.pose_of.
            self._globe_pose = view.navigator.pose
            view.sky_view = self._sky_state or SkyView()
            for dialog in (self.ruler_dialog, self.place_dialog):
                if dialog is not None and dialog.isVisible():
                    dialog.close()
            view.navigator.stop()
        if ra is not None:
            view.sky_view.set(ra, dec, fov)
        view.sync_sky_pose()
        view.sky_time = self.sky_moment()
        self.toolbar.set_body("sky")
        self.navpad.hide()
        self.legend.hide()
        self.slope_legend.hide()
        self.insolation_legend.hide()
        self.quake_legend.hide()
        self.fire_legend.hide()
        self.cutaway_legend.hide()
        self.theme_legend.hide()
        self.paleo_bar.hide()
        self.view.plain_base = False
        for button in self._globe_buttons():
            button.setEnabled(False)
        self._show_attribution()
        self.sky_labels.sync()
        self._update_timebar()
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
        view.navigator.stop()
        if getattr(self, "_globe_pose", None) is not None:
            view.navigator.set_pose(self._globe_pose)
        self.navpad.show()
        for button in self._globe_buttons():
            button.setEnabled(True)
        self.toolbar.sync.setEnabled(self.planet.earth)
        self.toolbar.identify.setEnabled(self.planet.earth)
        self.legend.setVisible(bool(self.extras.get("temperature"))
                               and self.planet.earth)
        self.insolation_legend.setVisible(
            self.insolation_result is not None)
        self._quake_legend_state()
        self.fire_legend.setVisible(self.extras.get("fires", False)
                                    and self.planet.earth)
        self.cutaway_legend.setVisible(bool(self.extras.get("cutaway"))
                                       and self.planet.earth)
        self.paleo_bar.setVisible(self._paleo_on())
        self.view.plain_base = self._paleo_on()
        self._update_timebar()
        self._show_theme()
        self._set_surface()
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
        return (self.source is not self._earth_source()
                or self._relief_target() != self.view.store.scale
                or self._overlay_layers() != self._applied_layers
                or self._layers_stale)

    def refresh(self):
        """Показать на глобусе выбранные подложку, рельеф и слои. У Марса
        и Луны подложка своя, она остаётся."""
        self.refresh_timer.stop()
        if self.planet.earth:
            self._switch_basemap(self._earth_source())
        self.view.set_relief(self._relief_target())
        self.subsurface.relief_changed()
        self._place_quakes()
        self._place_fires()
        self._apply_vector(force=True)
        self._mark_dirty(False)
        self._show_attribution()

    def _apply_vector(self, force=False):
        """Показать выбранную векторную основу и отмеченные слои.

        force=False - как при флажке в панели «Слои»: слои проекта
        остаются прежними до кнопки «Обновить».
        """
        if force and self.planet.earth and hasattr(self, "subsurface"):
            # Геологические слои - в 3D, как обычные слои глобуса.
            self.subsurface.sync_project(self._shown_in_order(),
                                         restyle=self._layers_stale)
        layers = self._overlay_layers() if force else self._applied_layers
        if layers is None:
            layers = self._overlay_layers()
        lines = self._groups & set(LINE_GROUPS)
        old_lines = (self._applied_groups or set()) & set(LINE_GROUPS)
        self._applied_groups = set(self._groups)
        if self._groups and self.ofm_layer is None \
                and self._tilejson is None:
            self._tilejson = fetch_json(self._vector_choice(),
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
            # Охват времени слоёв на шкале мог смениться.
            self._update_data_marks()
        self._show_attribution()

    def _switch_basemap(self, source, coarse=False):
        if source is self.source:
            return
        old = self.loader
        old.abort()
        old.deleteLater()
        self.errors.clear()
        self.source = source
        self._start_loader()
        self.view.change_source(source.max_level, coarse=coarse)
        # Уровни 0-2 просятся сразу. Вид не рисует кадр, пока их нет,
        # и сам их не попросит. Без этого смена подложки до прихода
        # уровней 0-2 оставляла окно пустым, нашлось 26 сентября 2026.
        self.loader.want_many((key, -key[0]) for key in start_keys())

    # Наложение.

    def _overlay_layers(self):
        """Номера отмеченных слоёв проекта в порядке карты, кроме
        геологических - те идут в подземное (_apply_vector)."""
        shown = self._shown_in_order()
        under = subsurface_ids(shown)
        return [i for i in shown if i not in under]

    def _shown_in_order(self):
        return [layer.id() for layer in map_layers()
                if layer.id() in self._shown]

    # Время слоёв проекта и треков.

    def _temporal_layers(self):
        """Слои проекта на глобусе с действующими временными свойствами
        QGIS."""
        project = QgsProject.instance()
        layers = (project.mapLayer(layer_id) for layer_id
                  in getattr(self, "_applied_layers", None) or ())
        return [layer for layer in layers if timed_layer(layer)]

    def _layer_range(self):
        """Промежуток шкалы времени для слоёв со временем,
        QgsDateTimeRange. None - шкала закрыта или таких слоёв нет,
        тогда слои рисуются целиком, как и метки."""
        span = getattr(self, "_time_range", None)
        if span is None or not self.planet.earth \
                or not self._temporal_layers():
            return None
        return date_range(*span)

    def _apply_layer_time(self):
        """Картинки и подписи слоёв со временем заново, если промежуток
        шкалы для них сменился."""
        if range_key(self._layer_range()) == self._applied_time:
            return
        self._update_overlay(keep=True)
        self._update_layer_labels(force=True)

    def _update_data_marks(self):
        """Охват времени треков и слоёв проекта со временем на шкале.
        Охват слоя просматривает его поля, поэтому он считается при
        смене треков и слоёв, а не при движении шкалы."""
        spans = [self.tracks.data_span()] if hasattr(self, "tracks") \
            else []
        spans += [layer_span(layer) for layer in self._temporal_layers()]
        self._data_marks = [when.stamp(when.text(t))
                            for span in spans if span is not None
                            for t in span]
        self._update_timebar()

    def _follow_time(self):
        """Треки и слои проекта за шкалой времени: треки - к правому
        бегунку сразу, слои - после паузы в движении бегунков."""
        span = self._time_range
        hi = span[1] if span is not None and math.isfinite(span[1]) \
            else None
        if hasattr(self, "tracks"):
            self.tracks.set_time(hi)
        if range_key(self._layer_range()) != self._applied_time:
            self._layer_time_timer.start()
        if hasattr(self, "satellite_manager"):
            self.satellite_manager.time_changed()

    def time_span(self):
        """Промежуток времени треков для записи тура: открытая шкала,
        иначе охват треков. None - треков нет."""
        span = self._time_range
        if span is not None and all(math.isfinite(v) for v in span):
            return span
        return self.tracks.data_span()

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
        if self.planet.earth and (
                self._applied_groups and self.ofm_layer is not None
                or self.buildings_loader is not None):
            parts.append(self._vector_credit())
        if self.view.store.scale or "slope" in self.gibs_loaders:
            parts.append(self._terrain_credit() if self.planet.earth
                         else html.escape(self.planet.terrain[3])
                         if self.planet.terrain
                         and self.terrain_loader is not None else "")
        if "clouds" in self.gibs_loaders:
            parts.append(link_html(*clouds.ATTRIBUTION))
        if "theme" in self.gibs_loaders:
            parts.append(link_html(*themes.ATTRIBUTION))
        if "lights" in self.gibs_loaders:
            parts.append(link_html(*sun.LIGHTS_ATTRIBUTION))
        if "sea" in self.gibs_loaders:
            parts.append(link_html(*temperature.ATTRIBUTION))
        if self.view.quakes.events:
            parts.append(link_html(*quakes.ATTRIBUTION))
        if self.view.fires.fires is not None:
            parts.append(link_html(*fires_core.ATTRIBUTION))
        manager = getattr(self, "satellite_manager", None)
        if manager is not None and manager.on and manager.count():
            parts.append(link_html(*satellites_core.ATTRIBUTION))
        if self.planet.earth and getattr(self, "extras", {}).get("plates") \
                and self.plates_data is not None:
            parts.append(link_html(*plates.ATTRIBUTION))
        if self.view.wedge_slabs:
            parts.append(link_html(*slabs.ATTRIBUTION))
        if self.view.wedge is not None and self.crust is not None:
            parts.append(link_html(*crust.CITATION))
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
        # Шкалы слоёв - одной панелью в левом нижнем углу. Узкий вид:
        # над подписью. Ползунок палеогеографии - над панелью.
        panel = getattr(self, "legend_panel", None)
        if panel is None:
            return
        bottom = self.view.height() - MARGIN
        if self.attribution.x() < MARGIN + max(panel.width(),
                                               self.paleo_bar.width()):
            bottom = self.attribution.y() - MARGIN // 2
        panel.move(MARGIN, bottom - panel.height())
        if panel.isVisible():
            bottom = panel.y() - MARGIN // 2
        self.paleo_bar.move(MARGIN, bottom - self.paleo_bar.height())

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == enum(
                QEvent, "Type", "Resize"):
            self._place_attribution()
            if hasattr(self, "screen_overlays"):
                self.screen_overlays.place()
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
        # Наложение собирается и при создании окна, до строк «Слоёв».
        if self.planet.earth and getattr(self, "extras", {}).get("plates") \
                and self.plate_layer is not None:
            # Границы плит - над векторной основой.
            layers.append(self.plate_layer)
        if groups & set(LINE_GROUPS) and self.ofm_layer is not None:
            layers.append(self.ofm_layer)
        min_levels = {}
        if RAILWAYS in groups and self.rail_layer is not None:
            layers.append(self.rail_layer)
            min_levels[self.rail_layer.id()] = RAIL_FROM
        # Картинки на поверхности - под всеми, сразу над снимком.
        layers += getattr(self, "_ground_rasters", [])
        if self.overlay is not None:
            self.overlay.abort()
            self.overlay.deleteLater()
            self.overlay = None
        time_range = self._layer_range()
        self._applied_time = range_key(time_range)
        if layers:
            self.overlay = LayerOverlay(layers, parent=self,
                                        min_levels=min_levels,
                                        time_range=time_range)
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
        # Перерисовка слоя меняет глобус, только если слой на нём:
        # в наложении или в подземной модели из слоёв проекта.
        if self._applied_layers or self.subsurface.from_project():
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
        self.auto_refresh = read_flag(AUTO_REFRESH, AUTO_DEFAULT)
        self._read_shown()
        self.tracks.load()
        self.subsurface.project_reloaded()
        self._load_insets()
        self._refresh_relief()

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
            self.properties.sea_changed.connect(self.set_sea_depths)
            self.properties.assistant_requested.connect(self.open_assistant)
            self.properties.assistant_settings_requested.connect(
                lambda: self._assistant().open_settings())
            self.properties.history_clear_requested.connect(
                self.clear_search_history)
            self.properties.sources_requested.connect(self.open_sources)
        self.properties.show()
        self.properties.raise_()
        self.properties.activateWindow()

    def open_sources(self):
        """Окно «Источники данных», одно на окно глобуса."""
        dialog = getattr(self, "sources_dialog", None)
        if dialog is None:
            dialog = self.sources_dialog = SourcesDialog(self, self)
            dialog.changed.connect(self.sources_changed)
        else:
            dialog.rebuild()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

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

    def fly(self, text=None, assistant=True):
        """Поиск из поля ввода: координаты - перелёт, точное название
        своей метки, на небе звезды или созвездия - перелёт к ним без
        запроса в сеть, просьба словами - помощнику, иначе Nominatim.
        assistant=False - поиск запустил сам помощник, к нему запрос
        не возвращается и в историю запросов не идёт."""
        text = self.place.text() if text is None else text
        if assistant:
            self._remember_search(text)
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
        if not assistant:
            self._tool_queries.add(query)
        else:
            self._tool_queries.discard(query)
            self.panel.set_answer("")
        # Свои метки ищутся только по Enter пользователя. Поиск помощника
        # к ним не ведёт: точка взгляда уходит в модель, а места меток
        # в неё не идут, решение автора от 3 октября 2026 года.
        own = self._exact_match(text) if assistant else None
        if own is not None:
            self._fly_suggestion(own)
            return
        # Просьба словами уходит помощнику, название места - Nominatim.
        # Вне Земли Nominatim не работает, туда идёт любой запрос.
        if query and assistant and (assistant_core.is_request(query)
                                    or not self.planet.earth) \
                and self.ask_assistant(query):
            return
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
        self._set_busy("search", True)
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

    def _set_busy(self, reason, on):
        """Значок ожидания у строки «Поиск». reason - чего ждём,
        значок гаснет, когда не ждём ничего."""
        if on:
            self._busy.add(reason)
        else:
            self._busy.discard(reason)
        tip = tr("Помощник ждёт ответ модели.") \
            if "assistant" in self._busy else tr("Идёт поиск места.")
        self.panel.set_busy(bool(self._busy), tip if self._busy else "")

    def _search_done(self, key, data, error):
        self._search_reply = None
        # Следующий запрос может ждать своей очереди по таймеру.
        self._set_busy("search", self._search_timer.isActive())
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
            # Место не нашлось. Тема вроде «Путешествия Колумба» -
            # метки одним запросом, как кнопка помощника, вопрос -
            # разговор. В разговоре метки появляются, только если модель
            # вызовет add_kml. 4 октября 2026 года бесплатная модель
            # на «Путешествия Колумба» описала документ текстом, и меток
            # не было.
            if key[0] not in self._tool_queries:
                if not assistant_core.is_request(key[0]) \
                        and search_enabled() \
                        and ready(current_provider()) \
                        and self.make_places(key[0]):
                    return
                if self.ask_assistant(key[0]):
                    return
            self.message = (tr("Ничего не найдено: {text}", text=key[0]),
                            time.monotonic())
            if assistant_core.is_request(key[0]) and search_enabled() \
                    and not ready(current_provider()):
                self.message = (tr("Ключа API нет, просьба не отправлена. "
                                   "Ключ вводится в окне «Настройки "
                                   "помощника»."),
                                time.monotonic())
            self._show_state()
            return
        self.message = ("", 0.0)
        self._show_state()
        self._fly_place(places[0])
        # Тема вроде «Первая мировая война» находит места с этими словами
        # в названии. Рядом - ссылка на метки помощника по теме, просьба
        # автора от 4 октября 2026 года.
        if key[0] not in self._tool_queries and search_enabled() \
                and ready(current_provider()):
            self.panel.set_answer(tr("Найдены места с этим названием."),
                                  make=key[0])

    def fly_place(self, index):
        """Перелёт к месту из списка найденных."""
        if 0 <= index < len(self._found):
            self._fly_place(self._found[index])

    def clear_search(self):
        """Поле поиска очищено: списка и метки больше нет."""
        self._found = []
        self._search_key = None
        # Ждущий запрос Nominatim снимается: с пустым ключом
        # _send_search упал бы на search_url(*None).
        self._search_timer.stop()
        self._set_busy("search", False)
        self.view.set_search_mark(None)

    # Строка «Поиск»: подсказки при вводе, история запросов, точное
    # название своей метки или объекта неба (core/searchbar.py). Nominatim
    # при вводе не спрашивается, его правила запрещают автодополнение.

    def search_history(self):
        """Прежние запросы строки «Поиск» из профиля QGIS, от новых
        к старым."""
        saved = QgsSettings().value(HISTORY_KEY, []) or []
        # Список из одной строки настройки возвращают строкой.
        if isinstance(saved, str):
            saved = [saved]
        elif not isinstance(saved, (list, tuple)):
            saved = []
        return [str(text) for text in saved
                if str(text).strip()][:searchbar.HISTORY]

    def _remember_search(self, text):
        """Запрос по Enter встаёт в начало истории."""
        history = self.search_history()
        updated = searchbar.remember(history, text)
        if updated != history:
            QgsSettings().setValue(HISTORY_KEY, updated)

    def clear_search_history(self):
        """Пункт «Очистить историю поиска» меню кнопки помощника:
        прежние запросы стираются из профиля."""
        QgsSettings().remove(HISTORY_KEY)
        self.panel.hide_hints()
        self.message = (tr("История поиска очищена."), time.monotonic())
        self._show_state()

    def _search_places(self):
        """Метки для строки «Поиск»: ключ, название, широта и долгота
        меток тела на экране, на небе - меток неба. Метки без названия
        или геометрии и записанные туры не идут."""
        body = self.body_key()
        out = []
        for place in self.myplaces.places:
            points = place.shape.points
            if place.body == body and not place.tour and points \
                    and (place.name or "").strip():
                out.append((place.key, place.name, points[0][0],
                            points[0][1]))
        return out

    def _search_sky(self):
        """Звёзды и созвездия для строки «Поиск», вне неба их нет.
        Файл неба читается один раз."""
        if self.view.sky_view is None:
            return []
        if self._sky_objects is None:
            language = "ru" if ui_language() == "ru" else "en"
            self._sky_objects = searchbar.sky_objects(skydata.load(),
                                                      language)
        return self._sky_objects

    def search_suggestions(self, text):
        """Подсказки строки «Поиск» к тексту, их спрашивает панель при
        вводе. Пустой текст - прежние запросы."""
        found = searchbar.suggestions(
            text, self._search_places(), self.search_history(),
            self._search_sky(), searchbar.LIMIT + searchbar.HISTORY)
        return searchbar.drop_repeats(found)[:searchbar.LIMIT]

    def _exact_match(self, text):
        """Своя метка, а на небе звезда или созвездие, чьё название
        совпадает с text целиком. Из нескольких берётся первая, метки
        идут раньше объектов неба. Без совпадения - None."""
        places = self._search_places()
        sky = self._search_sky()
        found = searchbar.exact(text, searchbar.suggestions(
            text, places, sky=sky, limit=len(places) + len(sky) + 1))
        return found[0] if found else None

    def choose_suggestion(self, item):
        """Выбрана подсказка строки «Поиск». Прежний запрос идёт в строку
        и ищется заново, к метке и объекту неба начинается перелёт."""
        self.place.setText(item.text)
        if item.kind == "history":
            self.fly(item.text)
        else:
            self._fly_suggestion(item)

    def _fly_suggestion(self, item):
        """Перелёт к своей метке или объекту неба. Прежний поиск по
        названию снимается: списка найденных мест, метки поиска
        и ждущего запроса больше нет."""
        self._search_timer.stop()
        self.panel.set_found([])
        self.clear_search()
        if item.kind == "place":
            place = self.myplaces.find(item.key)
            if place is not None:
                self.fly_to_place(place)
                self.panel.select_place(item.key)
            return
        # Долгота подсказки неба - прямое восхождение от -180° до 180°.
        ra = item.lon % 360.0
        if self.view.sky_view is None:
            self.show_sky(ra, item.lat, item.fov)
        else:
            # Плавный перелёт взгляда, как двойной щелчок по небу.
            self.view.fly_sky(ra, item.lat, item.fov)
        self.view.setFocus()

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
        # Метки, по которым режется подземная модель, могли измениться.
        if hasattr(self, "subsurface"):
            self.subsurface.places_changed()
        self._update_timebar()
        self._refresh_shapes()

    def _update_timebar(self):
        """Охват шкалы времени по видимым меткам со временем."""
        times = [p.time for p in self.myplaces.places if p.visible]
        # Землетрясения на шкале - моменты первого и последнего события.
        quake_span = quakes.span(self.view.quakes.events) \
            if hasattr(self, "view") else None
        if quake_span is not None:
            times += [when.stamp(when.text(t)) for t in quake_span]
        # Пожары - так же, первый и последний снимок сводки.
        fire = self.view.fires.fires if hasattr(self, "view") else None
        fire_span = fires_core.span(fire) if fire is not None else None
        if fire_span is not None:
            times += [when.stamp(when.text(t)) for t in fire_span]
        # Тема NASA на шкале - первый и последний день её ряда.
        theme_span = themes.span(self._theme_domains.get(self.theme_key)) \
            if getattr(self, "theme_key", "") and self._theme_on() else None
        if theme_span is not None:
            times += [when.stamp(when.text(t)) for t in theme_span]
        # Треки и слои проекта со временем - их охват.
        times += getattr(self, "_data_marks", [])
        extent = when.extent(times)
        self.timebar.set_clock(self._clock_on())
        if extent is None and getattr(self, "theme_key", "") \
                and self._theme_on() \
                and self.theme_key not in self._theme_domains:
            # Ряд новой темы ещё грузится: шкала остаётся как есть,
            # иначе она закрывалась бы на время загрузки.
            return
        self.timebar.set_extent(extent)
        # Панель значков заводится позже первого чтения меток.
        toolbar = getattr(self, "toolbar", None)
        if toolbar is not None:
            toolbar.set_time_available(self.timebar.known)
        self._time_range = self.timebar.range() \
            if self.timebar.shown() else None
        if hasattr(self, "extras") and hasattr(self, "_theme_timer"):
            self._time_mode()
        if hasattr(self, "_layer_time_timer"):
            self._follow_time()

    def _time_bar_closed(self):
        """Шкалу закрыли кнопкой ⏹ на ней самой."""
        self.toolbar.set_time_shown(False)
        self._time_toggled(False)

    def _time_toggled(self, on):
        """Кнопка шкалы. Закрытая шкала метки не скрывает."""
        if on:
            self.timebar.open_bar()
        else:
            self.timebar.close_bar()
        self._time_range = self.timebar.range() \
            if self.timebar.shown() else None
        self._follow_time()
        self._refresh_shapes()
        self._update_sun()
        self._time_quakes()
        self._theme_timer.start()

    def _time_quakes(self):
        """Землетрясения и пожары в промежутке шкалы времени."""
        self.view.quakes.window = self._time_range
        self.view.fires.window = self._time_range
        self.view.update()

    def _time_changed(self, lo, hi):
        self._time_range = (lo, hi)
        self._follow_time()
        self._time_quakes()
        self._refresh_shapes()
        self._update_sun()
        self._theme_timer.start()
        if self.view.sky_view is not None:
            self.view.sky_time = self.sky_moment()
            self.view.update()

    def _time_ok(self, place):
        """Попадает ли время метки в промежуток шкалы."""
        span = self._time_range
        return span is None or when.visible(place.time, *span)

    def _timed_shape(self, place):
        """Объект метки в момент шкалы времени. Путь с промежутком
        времени растёт от начала к концу, пока по нему идёт правый
        бегунок шкалы."""
        shape = self.previews.get(place.key, place.shape)
        span = self._time_range
        if span is None or shape.kind != "line":
            return shape
        return grown(shape, when.share(place.time, span[1]))

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
        shapes = [self._timed_shape(p)
                  for p in self.myplaces.places
                  if p.visible and self._time_ok(p) and not p.tour
                  and p.body == self.planet.key]
        # Метки неба подписывает слой подписей неба.
        # Точка метки неба - (склонение, прямое восхождение), как
        # (широта, долгота) у меток глобуса.
        sky = [(p.shape.points[0], p.shape.name)
               for p in self.myplaces.places
               if p.visible and self._time_ok(p) and p.body == "sky"
               and p.shape.points and not p.tour]
        if self.view.sky_view is not None and self._place_open():
            shape = self.place_dialog.shape()
            if shape is not None and shape.points:
                sky.append((shape.points[0], shape.name))
        self.view.sky_places = [
            (sky_direction(point[1] % 360.0, point[0]), name)
            for point, name in sky]
        if getattr(self, "tracks", None) is not None and self.planet.earth:
            shapes += self.tracks.shapes()
        if getattr(self, "satellite_manager", None) is not None \
                and self.planet.earth:
            shapes += self.satellite_manager.shapes()
        shapes += getattr(self, "grid_shapes", [])
        if self._ruler_open():
            shape = self.ruler.shape()
            if shape is not None:
                shapes.append(shape)
        elif self._place_open():
            shape = self.place_dialog.shape()
            if shape is not None:
                shapes.append(shape)
        shapes += [self.previews[key] for key in
                   getattr(self, "overlay_dialogs", {})
                   if key in self.previews]
        self.view.set_shapes([self._drawn_shape(s) for s in shapes])
        self._refresh_overlays()

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

    def open_demo(self, name="perm"):
        """Демо из папки модуля, tools/make_demo.py: perm, bocachica,
        japan, subsurface, vegas, aral, mars, jezero, moon, sky. У
        subsurface после
        сцены строится подземное из planetx/demo/subsurface. У japan
        открывается окно «Разрез» по первому пути папки демо без тура."""
        demo = os.path.join(os.path.dirname(os.path.dirname(__file__)),
                            "demo")
        key = self.open_scene(os.path.join(demo, name + EXTENSION))
        if name == "japan" and key is not None:
            lines = [p for p in self.myplaces.places_in(key)
                     if p.shape.kind == "line" and not p.tour]
            if lines:
                self._open_section(lines[0].name, lines[0].shape.points)
                # За 30 суток очаги у этой линии лежат в 100-155 км от неё,
                # полоса демо шире умолчания. Выбор помощника.
                self.section_dialog.band.setValue(DEMO_QUAKE_BAND)
        # Подземные демо кладут данные в проект QGIS группой обычных
        # слоёв, глобус показывает их в 3D по флажкам «Слоёв проекта».
        # Решение автора от 4 октября 2026 года.
        if name == "subsurface":
            folder = os.path.join(demo, "subsurface")
            self.subsurface_layers(
                tr("Пермские отложения"),
                os.path.join(folder, "perm_subsurface.gpkg"),
                ("collar", "interval", "survey", "beds", "sections", "cut",
                 "images"),
                sorted(os.path.join(folder, f) for f in os.listdir(folder)
                       if f.startswith("roof_") and f.endswith(".tif")),
                opacity=0.6, cut=True)
        if name == "vegas":
            # Тоннели на 12 м под улицами видны сквозь полупрозрачную
            # поверхность. Непрозрачность 0.5 - выбор помощника.
            self.subsurface_layers(
                tr("Тоннели Vegas Loop"),
                os.path.join(demo, "vegas", "vegas_loop.gpkg"),
                ("tunnels",), (), opacity=0.5, cut=False)
        if name == "quarry":
            # Съёмка карьера - растр проекта, рельеф глобуса через меню
            # слоя. Растр на глобусе картинкой не показывается.
            layer_id = self._demo_raster(
                tr("Карьер, свой рельеф"), tr("Карьер, съёмка 1 м"),
                os.path.join(demo, "quarry", "quarry_dem.tif"))
            if layer_id is not None:
                self.set_insets(read_insets() + [layer_id])
        return key

    def _demo_raster(self, title, name, path):
        """Растр демо path в группе title вверху проекта. Прежняя группа
        с тем же названием заменяется. Возвращает номер слоя или None."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        old = root.findGroup(title)
        if old is not None:
            for node in old.findLayers():
                project.removeMapLayer(node.layerId())
            root.removeChildNode(old)
        layer = QgsRasterLayer(path, name, "gdal")
        if not layer.isValid():
            return None
        project.addMapLayer(layer, False)
        root.insertGroup(0, title).addLayer(layer)
        return layer.id()

    def subsurface_layers(self, title, path, tables, rasters, opacity, cut):
        """Данные подземного - демо или шаблон - группа title в проекте
        QGIS, слои отмечены на глобусе. Прежняя группа с тем же
        названием заменяется."""
        ids = add_to_project(title, path, tables, rasters)
        for layer_id in ids:
            self._shown.add(layer_id)
            if self.follow:
                set_visible_on_map(layer_id, True)
        write_shown(self._shown)
        self.subsurface.settings = dict(self.subsurface.settings,
                                        opacity=opacity, cut=cut)
        self._show_layers()
        self.refresh()

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
        self.view.vertex_tool = self.draw_vertices
        self.handles.tool = self.draw_vertices
        self._refresh_shapes()
        self._tool_cursor()

    def _place_closed(self, *args):
        self.view.vertex_tool = self.wedge_corners \
            if self.view.wedge is not None else None
        self.drawer.clear()
        self._refresh_shapes()
        self._tool_cursor()
        self.handles.sync()

    def _save_place(self):
        shape = self.place_dialog.shape(rubber=False)
        if shape is None:
            return
        self.myplaces.add(shape, folder=self.panel.current_folder(),
                          body=self.body_key())
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

    def add_place_here(self, lat, lon):
        """«Добавить метку здесь» меню глобуса: окно «Новая метка»
        с точкой под курсором."""
        self._open_place()
        self.place_dialog.tabs.setCurrentIndex(0)
        self.drawer.clear()
        self.drawer.add(lat, lon)

    def route_point(self, lat, lon, name, end):
        """Начало (end=False) или конец маршрута из меню на глобусе."""
        if end:
            self.route_manager.set_target(lat, lon, name)
        else:
            self.route_manager.set_origin(lat, lon, name)

    def _route_done(self, key):
        """Маршрут лёг в «Мои метки»: перелёт к нему."""
        for place in self.myplaces.places:
            if place.key == key:
                self.fly_to_place(place)
                return

    def spin_here(self, lat, lon):
        """«Вращаться вокруг» меню на глобусе."""
        navigator = self.view.navigator
        navigator.start_flight(Spin(navigator.pose, lat, lon,
                                    fov_y=self.view.camera.fov_y),
                               time.monotonic())
        self.view.setFocus()
        self.view.update()

    def _globe_menu(self, px, py):
        """Щелчок правой кнопкой по глобусу без сдвига."""
        globemenu.show(self, px, py)

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
        # Тайлов глубже предельного уровня источника нет, у тела без
        # высот их нет совсем: линейка и профиль их не ждут. Иначе вид
        # просил бы на Марсе земные тайлы Terrarium.
        if key in self.view.store.tiles:
            return True
        if self.terrain_loader is None:
            return True
        return key[0] > self.view.store.cap(key)

    # Свой рельеф.

    def _load_insets(self):
        """Врезки своего рельефа из записи проекта. Нижний в проекте
        растр врезается первым, верхний - последним."""
        ids = read_insets()
        order = {layer.id(): n for n, layer in enumerate(map_layers())}
        entries = []
        for layer_id in sorted(ids, key=lambda i: -order.get(i, -1)):
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer is None:
                continue
            QApplication.setOverrideCursor(enum(Qt, "CursorShape",
                                                "WaitCursor"))
            try:
                entry = prepare_inset(layer)
            finally:
                QApplication.restoreOverrideCursor()
            if isinstance(entry, str):
                self.message = (tr("Растр «{name}» не стал рельефом "
                                   "глобуса: {why}.", name=layer.name(),
                                   why=entry), time.monotonic())
                continue
            entries.append(entry)
        self.insets = tuple(entries)
        self.panel.inset_ids = set(ids)

    def set_inset(self, layer_id, on):
        """Растр проекта layer_id - рельеф глобуса или нет."""
        ids = [i for i in read_insets() if i != layer_id]
        if on:
            ids.append(layer_id)
        self.set_insets(ids)

    def set_insets(self, ids):
        """Растры проекта ids - рельеф глобуса, прочие - нет."""
        write_insets(ids)
        self._load_insets()
        self._refresh_relief()
        self._show_state()

    def _refresh_relief(self):
        """Высоты заново: врезки сменились."""
        self._body_terrain(self.planet)
        self.view.reset_heights()
        self._set_surface()

    # Видимость из точки.

    def _open_viewshed(self, item):
        """Окно «Видимость из точки» для точечной метки item."""
        dialog = self.viewshed_dialog
        if dialog is None:
            dialog = ViewshedDialog(self)
            dialog.build.connect(self._build_viewshed)
            dialog.clear.connect(self._clear_viewshed)
            self.viewshed_dialog = dialog
        lat, lon = item.shape.points[0]
        dialog.point = (lat, lon)
        dialog.place.setText("{}  {:.5f}, {:.5f}".format(
            item.name or tr("Без названия"), lat, lon))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()

    def _build_viewshed(self, observer, target, radius_m):
        """Расчёт видимости: сначала тайлы высот под кругом, потом
        расчёт в _viewshed_poll."""
        dialog = self.viewshed_dialog
        if self._surface_source() is None or self.view.sky_view is not None:
            dialog.status.setText(tr("Для этого тела высот нет."))
            return
        lat, lon = dialog.point
        cell = radius_m / viewshed.STEPS
        _, keys = viewshed.height_tiles(lat, lon, radius_m, cell,
                                        ellipsoid.A,
                                        self.view.store.max_level)
        self.viewshed_job = {"lat": lat, "lon": lon, "radius": radius_m,
                             "cell": cell, "observer": observer,
                             "target": target, "keys": keys,
                             "started": time.monotonic()}
        self.viewshed_timer.start()
        self._viewshed_poll()

    def _viewshed_poll(self):
        job = self.viewshed_job
        if job is None:
            self.viewshed_timer.stop()
            return
        missing = [k for k in job["keys"] if not self._has_height_tile(k)]
        waited = time.monotonic() - job["started"]
        if missing and waited < VIEWSHED_WAIT:
            self.view.want_tool_heights(missing)
            self.viewshed_dialog.status.setText(tr(
                "Загрузка высот: {done} из {total}",
                done=len(job["keys"]) - len(missing),
                total=len(job["keys"])))
            return
        self.viewshed_timer.stop()
        self.viewshed_job = None
        result = viewshed.compute(job["lat"], job["lon"], job["radius"],
                                  job["cell"], self._surface_heights,
                                  observer=job["observer"],
                                  target=job["target"])
        self._show_viewshed(result)
        text = tr("Видно {share} площади круга. Шаг расчёта {step} м.",
                  share="{:.0f}%".format(100.0 * result.share),
                  step="{:.0f}".format(result.step))
        if missing:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        self.viewshed_dialog.status.setText(text)

    def _show_viewshed(self, result):
        """Слой видимости по результату result, None убирает слой."""
        old = self.viewshed_tiles
        if old is not None:
            old.abort()
            old.deleteLater()
        self.viewshed_tiles = None
        self.viewshed_result = result
        if result is None:
            self.view.set_gibs("viewshed", False)
            return
        tiles = ResultTiles(result, ellipsoid.A, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("viewshed", key, levels))
        self.viewshed_tiles = tiles
        self.view.gibs["viewshed"].max_level = display_level(
            result.step, result.lat, ellipsoid.A)
        self.view.set_gibs("viewshed", True, tiles)

    def _clear_viewshed(self):
        self.viewshed_job = None
        self.viewshed_timer.stop()
        self._show_viewshed(None)
        if self.viewshed_dialog is not None:
            self.viewshed_dialog.status.setText("")

    # Инсоляция.

    def _open_insolation(self, item):
        """Окно «Инсоляция» для точечной метки item."""
        dialog = self.insolation_dialog
        if dialog is None:
            dialog = InsolationDialog(self)
            dialog.build.connect(self._build_insolation)
            dialog.clear.connect(self._clear_insolation)
            self.insolation_dialog = dialog
        lat, lon = item.shape.points[0]
        dialog.point = (lat, lon)
        dialog.place.setText("{}  {:.5f}, {:.5f}".format(
            item.name or tr("Без названия"), lat, lon))
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()

    def _build_insolation(self, start, end, radius_m):
        """Расчёт инсоляции: тайлы высот под сеткой, потом высоты узлов
        и расчёт частями по проходам цикла событий (_insolation_poll)."""
        dialog = self.insolation_dialog
        if not self.planet.earth or self.view.sky_view is not None:
            dialog.status.setText(tr("Инсоляция считается только для "
                                     "Земли."))
            return
        lat, lon = dialog.point
        cell, margin, _ = insolation.layout(radius_m)
        _, keys = viewshed.height_tiles(lat, lon, margin * cell + radius_m,
                                        cell, ellipsoid.A,
                                        self.view.store.max_level)
        self.insolation_job = {"lat": lat, "lon": lon, "radius": radius_m,
                               "start": start, "end": end, "keys": keys,
                               "started": time.monotonic(),
                               "work": None, "missing": False}
        self.insolation_timer.setInterval(VIEWSHED_POLL)
        self.insolation_timer.start()
        self._insolation_poll()

    def _insolation_poll(self):
        job = self.insolation_job
        dialog = self.insolation_dialog
        if job is None:
            self.insolation_timer.stop()
            return
        work = job["work"]
        if work is None:
            missing = [k for k in job["keys"]
                       if not self._has_height_tile(k)]
            waited = time.monotonic() - job["started"]
            if missing and waited < VIEWSHED_WAIT:
                self.view.want_tool_heights(missing)
                dialog.status.setText(tr(
                    "Загрузка высот: {done} из {total}",
                    done=len(job["keys"]) - len(missing),
                    total=len(job["keys"])))
                return
            # Высоты снимаются в главном потоке, хранилище высот вида
            # меняется только в нём. Узлов 640 тысяч, они снимаются
            # частями по HEIGHT_CHUNK за проход цикла событий, чтобы
            # вид отвечал мыши.
            if "points" not in job:
                job["missing"] = bool(missing)
                lats, lons = insolation.grid_points(job["lat"], job["lon"],
                                                    job["radius"])
                job["points"] = (lats.ravel(), lons.ravel())
                job["heights"] = []
                self.insolation_timer.setInterval(0)
            lats, lons = job["points"]
            done = sum(len(part) for part in job["heights"])
            if done < len(lats):
                end = done + HEIGHT_CHUNK
                job["heights"].append(self._surface_heights(
                    lats[done:end], lons[done:end]))
                dialog.status.setText(tr(
                    "Высоты узлов сетки: {share}",
                    share="{:.0f}%".format(100.0 * done / len(lats))))
                return
            heights = np.concatenate(job["heights"])
            job["work"] = insolation.parts(
                job["lat"], job["lon"], job["radius"], heights,
                job["start"], job["end"], ellipsoid.A)
            return
        # Расчёт идёт частями в главном потоке, не дольше CALC_BUDGET
        # за проход цикла событий. В рабочем потоке он отнимал у вида
        # GIL: при движении камеры 34 кадра из 125 шли дольше 50 мс.
        started = time.perf_counter()
        result = None
        try:
            while time.perf_counter() - started < CALC_BUDGET:
                share = next(work)
        except StopIteration as stop:
            result = stop.value
        if result is None:
            dialog.status.setText(tr("Расчёт инсоляции: {share}",
                                     share="{:.0f}%".format(100.0 * share)))
            return
        self.insolation_timer.stop()
        self.insolation_timer.setInterval(VIEWSHED_POLL)
        self.insolation_job = None
        self._show_insolation(result)
        text = tr("За {days} сут. прямое солнце светит от {low} "
                  "до {high} ч в сутки. Шаг сетки - {step} м.",
                  days=result.days,
                  low="{:.1f}".format(float(result.hours.min())),
                  high="{:.1f}".format(float(result.hours.max())),
                  step="{:.0f}".format(result.cell))
        if job["missing"]:
            text += " " + tr("Загружены не все высоты, расчёт шёл "
                             "по менее подробным.")
        dialog.status.setText(text)

    def _show_insolation(self, result):
        """Слой инсоляции по результату result, None убирает слой."""
        old = self.insolation_tiles
        if old is not None:
            old.abort()
            old.deleteLater()
        self.insolation_tiles = None
        self.insolation_result = result
        if result is None:
            self.view.set_gibs("insolation", False)
            self.insolation_legend.hide()
            return
        tiles = ResultTiles(result, ellipsoid.A, insolation.tile_rgba,
                            parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             self.view.add_gibs("insolation", key, levels))
        self.insolation_tiles = tiles
        self.view.gibs["insolation"].max_level = display_level(
            result.cell, result.lat, ellipsoid.A)
        self.view.set_gibs("insolation", True, tiles)
        self.insolation_legend.set_top(result.top)
        self.insolation_legend.show()
        self._place_attribution()

    def _clear_insolation(self):
        self.insolation_job = None
        self.insolation_timer.stop()
        self._show_insolation(None)
        if self.insolation_dialog is not None:
            self.insolation_dialog.status.setText("")

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
        elif self._place_open():
            self.drawer.remove_last()

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
        if self._section_mark is not None:
            marks.append(self._section_mark)
        for n, lat, lon in self.wedge_corners.points():
            # Подпись угла - его широта и долгота, видна, пока его тянут.
            marks.append(MarkPlace(-420000 - n, "{:.0f}°, {:.0f}°".format(
                lat, lon), "mark", 1, lat, lon))
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

    def _open_section(self, title, points):
        """Окно «Разрез» вниз вдоль пути points [(широта, долгота)].
        Кора, зоны плит и сводка землетрясений просятся, если их нет."""
        self._section_points = list(points)
        if self.section_dialog is None:
            self.section_dialog = SectionDialog(title, self._section, self)
            self.section_dialog.point_hovered.connect(self._section_hover)
            self.section_dialog.finished.connect(self._section_closed)
        else:
            self.section_dialog.set_source(title, self._section)
        self.section_dialog.show()
        self.section_dialog.raise_()

    def _section(self, depth, width):
        """Разрез по точкам пути и данным, что уже есть, и пояснение,
        что ещё загружается."""
        found = section.along(self._section_points)
        if found is None:
            return None, ""
        _, lats, lons = found
        self._want_crust()
        if not self.quake_events:
            self._want_quakes()
        codes = slabs.touched(self._read_slab_index(), lats, lons)
        self._request_slabs(codes)
        zones = [self.slab_zones[c] for c in codes if c in self.slab_zones]
        waiting = []
        if self.crust is None and self._crust_reply is not None:
            waiting.append(tr("кора CRUST1.0"))
        if any(c in self._slab_replies for c in codes):
            waiting.append(tr("плиты Slab2"))
        if self._quake_reply is not None:
            waiting.append(tr("землетрясения"))
        notes = tr("Загружаются: {what}.", what=", ".join(waiting)) \
            if waiting else ""
        built = section.build(self._section_points, self.crust, zones,
                              self.quake_events, depth, width)
        # Стенка на глобусе - из того же разреза.
        self.view.section_wall.set_mesh(
            "wall", section.wall_mesh(built) if built is not None else None)
        self.view.update()
        return built, notes

    def _open_model_section(self, title, points):
        """Окно «Разрез модели» вдоль пути points: пласты, скважины
        и тоннели подземной модели в метрах."""
        points = list(points)
        manager = self.subsurface

        def provider(band):
            if manager.model is None:
                return None
            return model_section(manager.model, manager._ground, points,
                                 band)
        if self.model_section_dialog is None:
            self.model_section_dialog = ModelSectionDialog(title, provider,
                                                           self)
            self.model_section_dialog.point_hovered.connect(
                self._model_section_hover)
            self.model_section_dialog.finished.connect(
                lambda *args: self._model_section_hover(None))
        else:
            self.model_section_dialog.set_source(title, provider)
        self.model_section_dialog.show()
        self.model_section_dialog.raise_()

    def _model_section_hover(self, point):
        """Точка разреза модели под курсором графика - метка на глобусе."""
        if point is None:
            self._section_mark = None
        else:
            lat, lon, distance = point
            self._section_mark = MarkPlace(
                -410000, tr("{value} м", value="{:.0f}".format(distance)),
                "mark", 1, lat, lon)
        self._update_tool_marks()

    def _section_closed(self, *args):
        """Окно «Разрез» закрыто: метка и стенка уходят с глобуса."""
        self._section_hover(None)
        self.view.section_wall.clear()
        self.view.update()

    def _refresh_section(self):
        if self.section_dialog is not None \
                and self.section_dialog.isVisible():
            self.section_dialog.refresh()

    def _section_hover(self, point):
        """Точка разреза под курсором графика - метка на глобусе."""
        if point is None:
            self._section_mark = None
        else:
            lat, lon, distance = point
            self._section_mark = MarkPlace(
                -410000, tr("{value} км", value="{:.0f}".format(distance)),
                "mark", 1, lat, lon)
        self._update_tool_marks()

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
        self.view.vertex_tool = self.wedge_corners \
            if self.view.wedge is not None else None
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

    def _places_toggled(self, states):
        """Флажки «Моих меток» из панели. Флажок папки без раскрытия
        переходит на всё её содержимое, в папке-переключателе остаётся
        одна видимая строка (core/placetree.radio_states)."""
        states = dict(states)
        nodes = self.myplaces.nodes()
        for folder in self.myplaces.folders:
            if not folder.expandable and folder.key in states:
                for key in placetree.descendants(nodes, folder.key):
                    states[key] = states[folder.key]
        radio = {f.key for f in self.myplaces.folders if f.radio}
        self.myplaces.set_visible_many(
            placetree.radio_states(nodes, radio, states))

    def _place_action(self, action, key):
        """Действие меню «Моих меток»: тур, папка, перелёт, имя,
        удаление, слои в проект. key "" - корень «Мои метки»."""
        if action == "project":
            self.myplaces.add_to_project()
            return
        if action == "clear":
            self.clear_places()
            return
        if action in ("draw_point", "draw_line", "draw_polygon"):
            # «Добавить» в меню папки: окно «Новая метка» на нужной
            # вкладке, новая метка ложится в эту папку.
            if key:
                self.panel.select_place(key)
            self._open_place()
            self.place_dialog.tabs.setCurrentIndex(
                ("draw_point", "draw_line", "draw_polygon").index(action))
            return
        if action == "record_tour":
            if key:
                self.panel.select_place(key)
            self.toolbar.record.setChecked(True)
            return
        if action in ("add_ground", "add_photo", "add_screen"):
            self.add_overlay(action[4:], key or None)
            return
        if action == "ground_project":
            self.ground_to_project(key or None)
            return
        if action == "sort":
            self.myplaces.sort_folder(key or None)
            return
        if action == "cut":
            # «Вырезать» Google Earth: копия в буфер обмена, строка
            # уходит из списка, «Вставить» кладёт её на новое место.
            self.copy_places([key])
            self.myplaces.remove(key)
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
        if is_folder(key):
            self._folder_action(action, item)
            return
        if isinstance(item, OverlayItem):
            if action == "properties":
                self._open_overlay_properties(item)
                return
            if action == "fly" and item.kind == "screen":
                return
        if action == "fly":
            self.fly_to_place(item)
        elif action == "tour":
            stop = self.place_stop(item, along=True)
            stop.time = item.view_time or item.time
            stop.description = item.description or ""
            self.tour.start([stop])
        elif action == "properties":
            self._open_place_properties(item)
        elif action == "profile":
            points = list(item.shape.points)
            self._open_profile(item.name, lambda: points, HeightSource(
                self._true_heights, self._has_height_tile,
                self.view.want_tool_heights))
        elif action == "section":
            self._open_section(item.name, list(item.shape.points))
        elif action == "model_section":
            self._open_model_section(item.name, list(item.shape.points))
        elif action in ("model_wall", "model_cut"):
            # Метка режет подземную модель или ставит стенку разреза,
            # повторный выбор убирает. Решение автора от 4 октября 2026
            # года - вырез и разрез рисуются на глобусе.
            on = self.subsurface.toggle_place(
                key, "cut" if action == "model_cut" else "section")
            names = {("model_cut", True): tr("Вырез модели по «{name}»."),
                     ("model_cut", False): tr("Вырез модели по «{name}» "
                                              "убран."),
                     ("model_wall", True): tr("Стенка разреза по «{name}»."),
                     ("model_wall", False): tr("Стенка разреза по «{name}» "
                                               "убрана.")}
            self.message = (names[(action, on)].format(
                name=item.name or tr("Без названия")), time.monotonic())
            self._show_state()
        elif action == "viewshed":
            self._open_viewshed(item)
        elif action == "insolation":
            self._open_insolation(item)
        elif action == "snapshot":
            # «Снимок вида» Google Earth: вид глобуса сейчас становится
            # видом метки, по нему идут перелёт к метке и тур.
            self.myplaces.update(key, {"view": lookat.text(
                self.current_view())})
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

    def clear_places(self, confirm=True):
        """«Очистить «Мои метки»» - удалить все метки и папки после
        подтверждения. Просьба автора от 4 октября 2026 года."""
        top = [n.key for n in self.myplaces.folders if n.parent is None] \
            + [p.key for p in self.myplaces.places + self.myplaces.overlays
               if p.folder is None]
        if not top:
            return False
        if confirm:
            answer = QMessageBox.question(
                self, tr("Очистить «Мои метки»"), tr(
                    "Удалить все метки и папки «Моих меток», всего меток "
                    "{count}? Отменить удаление нельзя.",
                    count=len(self.myplaces.places)))
            if answer != enum(QMessageBox, "StandardButton", "Yes"):
                return False
        self.myplaces.remove_many(top)
        self.made_folder = None
        return True

    def _folder_action(self, action, folder):
        """Перелёт к виду папки, снимок вида, свойства, имя, удаление."""
        key = folder.key
        if action == "fly":
            self.fly_to_folder(folder)
        elif action == "snapshot":
            self.myplaces.update(key, {"view": lookat.text(
                self.current_view())})
        elif action == "properties":
            dialog = FolderDialog(folder, self.current_view, self)
            if dialog.exec():
                self.myplaces.update(key, dialog.values())
        elif action == "remove":
            answer = QMessageBox.question(
                self, tr("Удалить папку"), tr(
                    "Удалить папку «{name}» со всем содержимым?",
                    name=folder.name or tr("Без названия")))
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

    # Наложения картинок (core/overlays.py, ui/overlays.py).

    def _overlay_edit(self, item):
        """Наложение item с правками открытого окна свойств: (метка
        картинки, Overlay, байты()). Углы картинки на поверхности
        приходят из окна после паузы в движении, см. _overlay_preview.
        Картинка - из файла меток, новая из окна или по ссылке."""
        overlay, data, link = self._overlay_edits.get(
            item.key, (item.overlay, None, None))
        if data is not None:
            token = "new:" + hashlib.sha256(data).hexdigest()
            return token, overlay, lambda data=data: data
        if link is None and item.image is not None:
            return item.image, overlay, \
                lambda item=item: self.myplaces.image(item.image)
        link = link if link is not None else item.href
        return self._link_token(link), overlay, \
            lambda link=link: self._link_data(link)

    def _link_token(self, link):
        """Метка картинки по ссылке: путь и время правки файла или адрес
        и пришёл ли ответ. Правка файла пересобирает растр."""
        if not link:
            return "link:"
        if link.startswith(("http://", "https://")):
            # Номер картинки растёт с каждой новой картинкой адреса.
            return "link:{}:{}".format(link, self._link_gen.get(link))
        try:
            stamp = os.path.getmtime(link)
        except OSError:
            stamp = None
        return "link:{}:{}".format(link, stamp)

    def _link_data(self, link):
        """Байты картинки по ссылке или None. Файл читается сразу, адрес
        в сети просится через кэш QGIS, ответ хранится в памяти, в файл
        меток не пишется - так ведёт себя поле Link Google Earth."""
        if not link:
            return None
        if link.startswith(("http://", "https://")):
            if link in self._link_images:
                return self._link_images[link]
            self._ask_link(link)
            return None
        try:
            with open(link, "rb") as stream:
                return stream.read()
        except OSError:
            return None

    def _ask_link(self, link, fresh=False):
        """Запросить картинку по адресу, если запроса ещё нет. fresh -
        мимо кэша QGIS, для обновления по промежутку."""
        self._link_asked[link] = time.monotonic()
        if link not in self._href_replies:
            self._href_replies[link] = fetch_bytes(
                link, lambda data, error, link=link:
                self._link_done(link, data, error), fresh=fresh)

    def _refresh_links(self):
        """Картинки по ссылке с обновлением: адрес просится заново мимо
        кэша, файл перечитывается по времени правки. Обновляются только
        видимые наложения, как у refreshMode onInterval в KML."""
        files = False
        now = time.monotonic()
        if self.view.sky_view is not None:
            return
        for item in self.myplaces.overlays:
            if not item.visible or item.body != self.planet.key \
                    or not self._time_ok(item):
                continue
            _, overlay, _ = self._overlay_edit(item)
            interval = overlays.refresh_interval(overlay.refresh)
            edits = self._overlay_edits.get(item.key)
            link = edits[2] if edits is not None and edits[2] is not None \
                else (item.href if item.image is None else None)
            if not interval or not link:
                continue
            asked = self._link_asked.get(link)
            if asked is not None and now - asked < interval:
                continue
            if link.startswith(("http://", "https://")):
                self._ask_link(link, fresh=True)
            else:
                self._link_asked[link] = now
                files = True
        if files:
            # Метка картинки файла - время его правки.
            self._refresh_overlays()

    def _link_done(self, link, data, error):
        self._href_replies.pop(link, None)
        if data and not QImage.fromData(data).isNull():
            data = bytes(data)
            if data != self._link_images.get(link):
                # Новая картинка - новая метка, растр и текстура заново.
                self._link_images[link] = data
                self._link_gen[link] = self._link_gen.get(link, 0) + 1
                self._refresh_overlays()
        else:
            self.message = (tr("Картинка по ссылке не загрузилась: {link}",
                               link=link), time.monotonic())
            self._show_state()
        self._ground_export_ready()

    def _overlay_bytes(self, item):
        """Байты картинки наложения: из файла меток или по ссылке."""
        if item.image is not None:
            return self.myplaces.image(item.image)
        return self._link_data(item.href)

    def _refresh_overlays(self):
        """Картинки на поверхности - растры в наложении, фото - плоскости
        в 3D, картинки на экране - поверх вида. Видны отмеченные
        наложения тела на глобусе в промежутке шкалы времени."""
        if not hasattr(self, "ground_layers"):
            return
        items = [o for o in self.myplaces.overlays
                 if o.visible and self._time_ok(o)
                 and o.body == self.planet.key
                 and self.view.sky_view is None]
        entries = []
        photos = []
        screens = []
        for item in items:
            token, overlay, data = self._overlay_edit(item)
            if item.kind == "ground":
                entries.append((token, item.fid, item.name, overlay, data))
            elif item.kind == "photo":
                photos.append((token, overlay, data))
            else:
                screens.append((token, overlay, data))
        layers = self.ground_layers.layers(entries)
        ids = [layer.id() for layer in layers]
        if ids != self._ground_ids:
            self._ground_rasters = layers
            self._ground_ids = ids
            self._update_overlay(keep=True)
        key = [(token, overlay.params()) for token, overlay, _ in photos]
        if key != self._photo_key:
            self._photo_key = key
            walls = []
            for token, overlay, data in photos:
                rgba = self._photo_images.get(token)
                if rgba is None:
                    rgba = image_rgba(data())
                    if rgba is None:
                        continue
                    self._photo_images[token] = rgba
                if overlay.color[3] < 255:
                    rgba = rgba.copy()
                    rgba[..., 3] = (rgba[..., 3].astype(np.uint16)
                                    * overlay.color[3] // 255)
                walls.append(overlays.photo_mesh(overlay.camera, overlay.fov,
                                                 overlay.near) + (rgba,))
            self.view.photos.set_walls(walls)
            self.view.update()
            # Текстуры прежних картинок, например до обновления по
            # ссылке, не копятся.
            tokens = {token for token, _, _ in photos}
            self._photo_images = {token: rgba for token, rgba
                                  in self._photo_images.items()
                                  if token in tokens}
        key = [(token, overlay.params()) for token, overlay, _ in screens]
        if key != self._screen_key:
            self._screen_key = key
            self.screen_overlays.set_items(
                [(overlay, data()) for _, overlay, data in screens])

    def add_overlay(self, kind, folder=None, path=None):
        """«Добавить → Картинку на поверхности, Фото, Картинку на
        экране»: картинка из файла встаёт по нынешнему виду, потом
        открывается окно свойств. Возвращает ключ или None."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Картинка наложения"), "",
                tr("Картинки (*.png *.jpg *.jpeg *.gif)"))
        if not path:
            return None
        with open(path, "rb") as stream:
            data = stream.read()
        image = QImage()
        if not image.loadFromData(data):
            self.message = (tr("Картинка не читается: {name}",
                               name=os.path.basename(path)),
                            time.monotonic())
            self._show_state()
            return None
        aspect = image.width() / float(max(image.height(), 1))
        pose = self.view.navigator.pose
        camera = self.view.camera
        if kind == "ground":
            visible = 2.0 * pose.distance * math.tan(
                math.radians(camera.fov_y) / 2.0) * camera.aspect
            overlay = overlays.Overlay("ground", box=overlays.fit_box(
                pose.lat, pose.lon, overlays.NEW_SHARE * visible, aspect))
        elif kind == "photo":
            lat, lon, alt = (float(v) for v in ecef_to_geodetic(camera.eye))
            shot, fov, near = overlays.view_camera(
                lat, lon, alt, pose.heading, pose.tilt, camera.fov_y,
                aspect, pose.distance)
            overlay = overlays.Overlay("photo", camera=shot, fov=fov,
                                       near=near)
        else:
            overlay = overlays.Overlay(
                "screen", overlay_xy=(0.0, 1.0, "fraction", "fraction"),
                screen_xy=(10.0, SCREEN_TOP, "pixels", "insetPixels"))
        name = os.path.splitext(os.path.basename(path))[0]
        key = self.myplaces.add_overlay(KOverlay(
            name, overlay, image=data,
            view=self.current_view() if kind != "screen" else None),
            folder)
        if key is not None:
            self.panel.select_place(key)
            self._open_overlay_properties(self.myplaces.find(key))
        return key

    def ground_to_project(self, key=None, target=None):
        """Картинки на поверхности - слоями проекта QGIS: файлы GeoTIFF
        в WGS84 по углам картинки и растровые слои в группе «PlanetX -
        картинки». key - картинка или папка, у папки - все её картинки
        на поверхности. target - файл для одной картинки или папка для
        нескольких, без него - окно выбора. Возвращает новые слои."""
        keys = self.myplaces.with_contents([key]) if key \
            else [o.key for o in self.myplaces.overlays]
        items = [o for o in self.myplaces.overlays
                 if o.key in keys and o.kind == "ground"]
        if not items:
            self.message = (tr("В папке нет картинок на поверхности."),
                            time.monotonic())
            self._show_state()
            return []
        start = QgsProject.instance().homePath() or os.path.expanduser("~")
        if target is None and len(items) == 1:
            target, _ = QFileDialog.getSaveFileName(
                self, tr("Картинка в проект QGIS"),
                os.path.join(start, (items[0].name or "overlay") + ".tif"),
                tr("GeoTIFF (*.tif)"))
        elif target is None:
            target = QFileDialog.getExistingDirectory(
                self, tr("Папка для картинок"), start)
        if not target:
            return []
        # Скрытая картинка по ссылке ещё не загружена. Выгрузка ждёт
        # ответов и идёт из _link_done, когда пришёл последний.
        for item in items:
            self._overlay_bytes(item)
        if any(item.image is None and item.href in self._href_replies
               for item in items):
            self._ground_export = ([item.key for item in items], target)
            self.message = (tr("Картинки по ссылкам загружаются, слои "
                               "добавятся после загрузки."),
                            time.monotonic())
            self._show_state()
            return []
        return self._write_ground(items, target)

    def _ground_export_ready(self):
        """Ждущая выгрузка в проект, если пришли все её ссылки."""
        if self._ground_export is None:
            return
        keys, target = self._ground_export
        items = [o for o in self.myplaces.overlays if o.key in keys]
        if any(item.image is None and item.href in self._href_replies
               for item in items):
            return
        self._ground_export = None
        self._write_ground(items, target)

    def _write_ground(self, items, target):
        """Файлы GeoTIFF картинок items и слои в группе «PlanetX -
        картинки». target - файл одной картинки или папка."""
        project = QgsProject.instance()
        group = project.layerTreeRoot().findGroup(tr("PlanetX - картинки"))
        if group is None:
            group = project.layerTreeRoot().insertGroup(
                0, tr("PlanetX - картинки"))
        added = []
        for n, item in enumerate(items):
            if len(items) == 1 and not os.path.isdir(target):
                path = target
            else:
                name = "".join(c if c.isalnum() or c in "-_ " else "_"
                               for c in (item.name or "overlay")).strip()
                path = os.path.join(target, "{}_{}.tif".format(
                    name or "overlay", n + 1))
            ok = ground_geotiff(item.fid, item.overlay,
                                self._overlay_bytes(item), path)
            layer = QgsRasterLayer(path, item.name or os.path.basename(path),
                                   "gdal") if ok else None
            if layer is None or not layer.isValid():
                self.message = (tr("Картинка «{name}» не записана.",
                                   name=item.name), time.monotonic())
                self._show_state()
                continue
            layer.renderer().setOpacity(item.overlay.color[3] / 255.0)
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            added.append(layer)
        if added:
            self.message = (tr("В проект добавлено картинок {count}.",
                               count=len(added)), time.monotonic())
            self._show_state()
        return added

    def _open_overlay_properties(self, item):
        """Немодальное окно свойств наложения. Правки видны сразу,
        «OK» пишет их в файл, «Отмена» возвращает прежнее."""
        key = item.key
        dialog = self.overlay_dialogs.get(key)
        if dialog is None:
            dialog = OverlayDialog(item, self._overlay_bytes(item), self)
            dialog.setAttribute(enum(Qt, "WidgetAttribute",
                                     "WA_DeleteOnClose"))
            self.overlay_dialogs[key] = dialog
            dialog.changed.connect(
                lambda key=key: self._overlay_preview(key))
            dialog.mode_changed.connect(
                lambda dialog=dialog: self._overlay_tool(dialog))

            def done(result, key=key, dialog=dialog):
                self.overlay_dialogs.pop(key, None)
                self._overlay_edits.pop(key, None)
                self.previews.pop(key, None)
                self._end_prop_vertices(dialog)
                if result:
                    self.myplaces.set_overlay(
                        key, dialog.overlay,
                        image=dialog.image if dialog.link is None else None,
                        link=dialog.link, **dialog.values())
                else:
                    self._refresh_shapes()
            dialog.finished.connect(done)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._overlay_tool(dialog)
        self._overlay_preview(key)

    def _overlay_tool(self, dialog):
        """Ручки картинки на поверхности по способу привязки: рамка -
        сдвиг, поворот и растяжение, четыре угла - каждый угол сам."""
        if dialog.item.kind != "ground" or self._place_open() \
                or self._ruler_open():
            return
        self._end_prop_vertices(dialog)
        if dialog.overlay.box is not None:
            tool = BoxVertices(self, dialog)
        else:
            tool = CornerVertices(self, dialog, ShapeEdit(
                "polygon", dialog.points, dialog.set_points))
        self.view.vertex_tool = tool
        self.handles.tool = tool
        self.handles.sync()

    def _overlay_preview(self, key):
        """Правка окна свойств наложения на глобусе. Контур углов
        картинки на поверхности - сразу, сама картинка - после паузы
        в движении: растр пересобирается целиком."""
        dialog = self.overlay_dialogs.get(key)
        if dialog is None:
            return
        overlay = dialog.overlay
        if overlay.kind == "ground":
            self.previews[key] = Shape("polygon", list(overlay.corners),
                                       color=OUTLINE, width=2.0)
            self._ground_pending[key] = dialog
            self._ground_timer.start()
        else:
            self._overlay_edits[key] = (
                overlays.from_params(overlay.kind, overlay.params()),
                dialog.image if dialog.link is None else None, dialog.link)
        self._refresh_shapes()
        self.handles.sync()

    def _ground_settled(self):
        """Пауза в движении углов: картинки на поверхности по окнам."""
        pending, self._ground_pending = self._ground_pending, {}
        for key, dialog in pending.items():
            if key in self.overlay_dialogs:
                overlay = dialog.overlay
                self._overlay_edits[key] = (
                    overlays.from_params("ground", overlay.params(),
                                         list(overlay.corners)),
                    dialog.image if dialog.link is None else None,
                    dialog.link)
        self._refresh_overlays()

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
                self.handles.sync()

            def done(result, key=key, dialog=dialog):
                self.prop_dialogs.pop(key, None)
                self.previews.pop(key, None)
                self._end_prop_vertices(dialog)
                if result:
                    if dialog.shape_changed():
                        self.myplaces.set_shape(key, dialog.preview())
                    self.myplaces.update(key, dialog.values())
                else:
                    self._refresh_shapes()
            dialog.changed.connect(preview)
            dialog.finished.connect(done)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        self._begin_prop_vertices(place, dialog)

    def _begin_prop_vertices(self, place, dialog):
        """Вершины метки тянутся мышью, пока открыто её окно свойств.
        Окно «Новая метка» и линейка главнее - при них вершины свойств
        не берутся."""
        if not globemenu.editable(place) or self._place_open() \
                or self._ruler_open():
            return
        tool = PropVertices(self, dialog, ShapeEdit(
            place.kind, dialog.points, dialog.set_points))
        self.view.vertex_tool = tool
        self.handles.tool = tool
        self.handles.sync()

    def _end_prop_vertices(self, dialog):
        tool = self.handles.tool
        if isinstance(tool, PropVertices) and tool.dialog is dialog:
            self.handles.tool = self.draw_vertices
            if self.view.vertex_tool is tool:
                self.view.vertex_tool = self.wedge_corners \
                    if self.view.wedge is not None else None
            self.handles.sync()

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
        found = tree.overlays()
        # Картинка наложения простого KML - ссылка на файл рядом с ним,
        # как у Google Earth. Из KMZ картинка ложится в файл меток.
        for item in found:
            if item.image is None and item.href and "://" not in item.href \
                    and not os.path.isabs(item.href):
                item.href = os.path.normpath(os.path.join(
                    os.path.dirname(path), item.href.replace("/", os.sep)))
        if not places and not found:
            QMessageBox.information(self, tr("Открыть KML или KMZ"), tr(
                "В файле нет точек, линий, многоугольников и наложений."))
        key = self.myplaces.import_tree(tree, parent)
        if key is not None:
            self.panel.select_place(key)
        points = [p for place in places for p in place.points] + [
            p for item in found for p in item.overlay.corners]
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
        kmz = path.lower().endswith(".kmz")
        hrefs = {}
        try:
            for n, item in enumerate(tree.overlays()):
                if item.image is None and item.href \
                        and os.path.isfile(item.href) and kmz:
                    # Картинка по ссылке на файл ложится в архив.
                    with open(item.href, "rb") as fh:
                        item.image = fh.read()
                if item.image and not kmz:
                    # Рядом с KML - папка картинок, ссылки на неё.
                    stem = os.path.splitext(os.path.basename(path))[0]
                    folder = os.path.join(os.path.dirname(path),
                                          stem + "_files")
                    os.makedirs(folder, exist_ok=True)
                    name = "overlay{}.{}".format(n + 1,
                                                 kml_image_ext(item.image))
                    with open(os.path.join(folder, name), "wb") as fh:
                        fh.write(item.image)
                    hrefs[id(item)] = stem + "_files/" + name
            data = write_kmz(tree) if kmz \
                else write_kml(tree, hrefs).encode("utf-8")
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
        if place.kind == "photo" and getattr(place, "overlay", None):
            # Фото: глаз в точке его камеры, как перелёт Google Earth.
            return Stop(name, *overlays.photo_pose(place.overlay.camera,
                                                   place.overlay.near))
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

    def fly_to_folder(self, folder):
        """Перелёт к папке, как двойной щелчок в Google Earth: к виду
        папки, без него - к охвату её меток. Берутся метки тела, которое
        на глобусе, без них - тела первой метки папки."""
        if folder.view is not None:
            self._fly_to(*folder.view)
            return
        places = self.myplaces.places_in(folder.key)
        if not places:
            return
        here = [p for p in places if p.body == self.body_key()]
        if not here:
            self.set_body(places[0].body)
            here = [p for p in places if p.body == self.body_key()]
        points = [pt for p in here for pt in p.shape.points]
        if len(points) == 1 or len(here) == 1:
            stop = self.place_stop(here[0])
            self._fly_to(stop.lat, stop.lon, stop.distance, stop.heading,
                         stop.tilt)
            return
        camera = self.view.camera
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        lat, lon, distance = fit_view(min(lons), min(lats), max(lons),
                                      max(lats), camera.fov_y, camera.aspect)
        self._fly_to(lat, lon, max(distance, SEARCH_MIN_DISTANCE), 0.0, 0.0)

    def fly_to_place(self, place):
        """Перелёт к метке, как остановка тура. Метка другого тела
        сначала переключает тело."""
        if place.body != self.body_key():
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
            # Тур идёт по меткам тела, которое сейчас на глобусе,
            # в небе - по меткам неба.
            if place.visible and place.body == self.body_key():
                stop = self.place_stop(place, along=True)
                stop.time = place.view_time or place.time
                stop.description = place.description or ""
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
            folder=self.panel.current_folder(), body=self.body_key())

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
        # В небе поза навигатора - взгляд на небо: точка метки -
        # склонение и прямое восхождение, расстояние - поле зрения.
        pose = self.view.navigator.pose
        shape = Shape("point", [(pose.lat, pose.lon)],
                      name=name.strip() or default)
        self.myplaces.add(shape, view=self.current_view(),
                          folder=self.panel.current_folder(),
                          body=self.body_key())

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
        sky = self.view.sky_view
        if sky is not None:
            # На небе щелчок ставит точку новой метки: склонение
            # и прямое восхождение под курсором.
            if tool is self.drawer:
                cam = self.view.camera
                ra, dec = ra_dec_of(sky.direction_at(px, py, cam.width,
                                                     cam.height))
                tool.add(dec, ra - 360.0 if ra > 180.0 else ra)
            return
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
        self.identify_here(px, py)

    def identify_here(self, px, py):
        """Опрос объектов под пикселем кадра: окно «Объекты». Его зовут
        щелчок в режиме «Определить объекты» и пункт «Получить сведения»
        меню на глобусе."""
        view = self.view
        camera = view.camera
        point = ground_under(camera, px, py, view.navigator.pose.terrain)
        if point is None:
            # Спутник на фоне неба опрашивается и без поверхности.
            found = self._identify_satellites(px, py)
            if found:
                self._identify_at = None
                if self.identified is None:
                    self.identified = IdentifyDialog(self)
                self.identified.show_result(found[0][1][0][0], found)
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
        self._identify_at = (lat, lon, height, tolerance, px, py, found)
        self._show_identified()

    def _show_identified(self):
        """Окно «Объекты» по последнему щелчку: слои проекта, «Мои
        метки», очаги землетрясений, место. Зовётся и по приходу коры
        и плит, тогда место уточняется."""
        args = getattr(self, "_identify_at", None)
        if args is None:
            return
        lat, lon, height, tolerance, px, py, found = args
        groups = list(found)
        groups += self._identify_places(lat, lon, tolerance)
        groups += self._identify_quakes(px, py)
        groups += self._identify_fires(px, py)
        groups = self._identify_satellites(px, py) + groups
        under = self.subsurface.identify(
            px, py, IDENTIFY_PIXELS * self.view.devicePixelRatioF())
        if under:
            groups.append((Group(tr("Подземное")), under))
        groups += self._identify_plates(lat, lon, tolerance)
        groups += self._identify_site(lat, lon, height)
        if self.identified is None:
            self.identified = IdentifyDialog(self)
        self.identified.show_result(
            point_text(lat, lon, height, fmt=self.coords), groups)

    # ИИ-помощник: контекст вида и инструменты (core/assistant.py).

    def _assistant(self):
        """Окно «Помощник», одно на окно глобуса, создаётся скрытым."""
        if self.assistant_dialog is None:
            dialog = AssistantDialog(self.assistant_tool,
                                     self.assistant_context, self)
            dialog.said.connect(self._assistant_said)
            dialog.busy_changed.connect(self._assistant_busy)
            dialog.generated.connect(self._places_made)
            dialog.progress.connect(self._assistant_progress)
            self.assistant_dialog = dialog
        return self.assistant_dialog

    def open_assistant(self):
        """Окно «Помощник», немодальное."""
        dialog = self._assistant()
        dialog.show()
        dialog.raise_()

    def ask_assistant(self, text):
        """Просьба из строки поиска. Ложь, если пользователь это
        выключил, ключа API нет или прежний ответ ещё ждётся - тогда
        запрос идёт поиском места."""
        if not search_enabled() or not ready(current_provider()):
            return False
        return self._assistant().ask(text)

    def make_places(self, text):
        """Метки по описанию одним запросом к модели, кнопка у строки
        поиска. Документ KML сразу ложится папкой в «Мои метки»
        (_places_made), нажатие кнопки - согласие на запись."""
        if not text.strip():
            self.message = (tr("Опишите в строке «Поиск», какие метки "
                               "создать."), time.monotonic())
            self._show_state()
            return False
        self.panel.set_answer("")
        return self._assistant().generate(text)

    def _places_made(self, kml):
        """Документ модели - в «Мои метки» новой папкой, камера к ней."""
        dialog = self.assistant_dialog
        try:
            tree = read_kml(str(kml).encode("utf-8"), tr("Помощник"))
        except KmlError as error:
            dialog.say_note(tr("KML модели не разобран: {error}",
                           error=str(error)))
            return
        count = len(tree.places())
        if not count:
            dialog.say_note(tr("В документе KML нет меток."))
            return
        key = self.myplaces.import_tree(tree, body=self.body_key())
        self.assistant_folder = key
        self.made_folder = key
        self.panel.select_place(key)
        folder = self.myplaces.find(key)
        if folder is not None:
            self.fly_to_folder(folder)
        self._show_made_time(key)
        dialog.say_note(tr("В «Мои метки» записано меток: {count}.",
                       count=count))
        timed = sum(1 for p in tree.places() if p.time)
        answer = tr("Создана папка «{name}», меток {count}, со временем "
                    "{timed}.", name=tree.name or tr("Помощник"),
                    count=count, timed=timed)
        if dialog.partial:
            # Документ неполон: остановка, обрыв или предел длины.
            answer += " " + dialog.partial
        self.panel.set_answer(answer, undo=True)

    def _show_made_time(self, key):
        """Шкала времени на даты созданных меток: открывается, если
        у меток папки есть время, промежуток - от первой до последней
        даты. Просьба автора от 4 октября 2026 года."""
        extent = when.extent([p.time for p in self.myplaces.places_in(key)])
        if extent is None or not self.timebar.known:
            return
        if not self.timebar.shown():
            self.timebar.open_bar()
            self.toolbar.set_time_shown(True)
        self.timebar.set_range(*extent)

    def undo_made_places(self):
        """Ссылка «Отменить» под строкой поиска: созданная папка
        удаляется из «Моих меток»."""
        key = getattr(self, "made_folder", None)
        self.made_folder = None
        if key is None or self.myplaces.find(key) is None:
            self.panel.set_answer("")
            return
        self.myplaces.remove(key)
        self.panel.set_answer(tr("Созданные метки удалены."))

    def _assistant_said(self, who, text):
        """Реплики разговора под строкой поиска. Вопрос пользователя
        там не повторяется, он уже в строке."""
        # Документ, который предложила модель, ждёт подтверждения. Он
        # виден под строкой со ссылкой «Записать». 4 октября 2026 года
        # предложение стояло в скрытом окне «Помощник», под строкой был
        # только рассказ модели о документе, меток на глобусе не было.
        dialog = self.assistant_dialog
        waiting = dialog is not None and dialog.pending is not None
        if waiting:
            text = dialog.proposal_text.text() + "\n" + text
        if who == "assistant" or who == "note":
            self.panel.set_answer(text, accept=waiting)
        elif who == "tool":
            self.panel.set_answer(tr("Помощник думает…") + "\n" + text,
                                  accept=waiting)

    def accept_proposed(self):
        """Ссылка «Записать в «Мои метки»» под строкой поиска."""
        if self.assistant_dialog is not None \
                and self.assistant_dialog.pending is not None:
            self.assistant_dialog._accept_place()

    def _assistant_busy(self, busy):
        self._set_busy("assistant", busy)
        if busy and not self.panel.answer.isVisible():
            self.panel.set_answer(tr("Помощник думает…"),
                                  stop=self._assistant().stream is not None)

    def _assistant_progress(self, count):
        """Метки идут потоком: счёт пришедших и ссылка «Остановить»."""
        self.panel.set_answer(
            tr("Помощник создаёт метки, получено {count}.", count=count),
            stop=True)

    def stop_making(self):
        """Ссылка «Остановить»: поток ответа обрывается, пришедшие
        целиком метки записываются."""
        if self.assistant_dialog is not None:
            self.assistant_dialog.stop_generation()

    def _layer_keys(self):
        """Ключи строк раздела «Слои», которые может включать помощник."""
        return ["relief"] + list(EXTRA_DEFAULTS) + list(VECTOR_GROUPS)

    def assistant_context(self):
        """Что уходит в модель с запросом: точка взгляда, тело,
        включённые строки, сектор разреза. Названия слоёв проекта
        и меток не уходят, решение автора от 3 октября 2026 года."""
        pose = self.view.navigator.pose
        on = (["relief"] if self._relief else []) \
            + [k for k, v in self.extras.items() if v] \
            + sorted(self._groups)
        wedge = self.view.wedge
        return {
            "view": {"lat": round(pose.lat, 4), "lon": round(pose.lon, 4),
                     "distance_km": round(pose.distance / 1000.0, 1),
                     "heading": round(pose.heading, 1),
                     "tilt": round(pose.tilt, 1)},
            "body": "sky" if self.view.sky_view is not None
            else self.planet.key,
            "body_keys": ["sky"] + [p.key for p in PLANETS],
            "layers_on": on, "layer_keys": self._layer_keys(),
            "cutaway": [round(v, 2) for v in wedge] if wedge else None,
            "selected_places": len(self.panel.list.selected_keys()),
            "utc": when.text(time.time())}

    def assistant_tool(self, call):
        """Исполнить вызов инструмента модели, ответ - текст для модели.
        Ошибка в аргументах - тоже ответ, модель может исправиться."""
        handler = getattr(self, "_tool_" + call.name, None)
        if handler is None:
            return tr("Нет такого инструмента: {name}.", name=call.name)
        try:
            return handler(**call.args)
        except (TypeError, ValueError, KeyError, IndexError) as error:
            return tr("Ошибка в аргументах {name}: {error}",
                      name=call.name, error=str(error))

    def _tool_fly_to(self, lat, lon, distance_km=500.0):
        self._fly_to(float(lat), float(lon), float(distance_km) * 1000.0)
        return tr("Перелёт к {lat:.3f}, {lon:.3f}.", lat=float(lat),
                  lon=float(lon))

    def _tool_search_place(self, query):
        self.place.setText(str(query))
        # Поиск помощника не возвращается к помощнику, иначе запрос
        # без найденного места пошёл бы по кругу.
        self.fly(str(query), assistant=False)
        return tr("Поиск запущен: {query}.", query=query)

    def _tool_set_body(self, body):
        if body != "sky" and body not in [p.key for p in PLANETS]:
            return tr("Неизвестное тело: {body}.", body=body)
        self.set_body(body)
        return tr("Тело: {body}.", body=body)

    def _tool_set_layer(self, key, on):
        on = bool(on)
        if key == "relief":
            self.set_relief(on)
        elif key in EXTRA_DEFAULTS:
            self.set_extra(key, on)
        elif key in VECTOR_GROUPS:
            self.set_line_group(key, on)
        else:
            return tr("Неизвестная строка: {key}.", key=key)
        return tr("Строка {key}: {state}.", key=key,
                  state=tr("включена") if on else tr("выключена"))

    def _tool_set_time(self, start="", end=""):
        if not start and not end:
            self.toolbar.set_time_shown(False)
            self._time_toggled(False)
            return tr("Шкала времени закрыта.")
        if not self.timebar.known:
            return tr("Шкалы времени нет: у видимых меток и событий нет "
                      "времени.")
        lo = when.parse(start) if start else float("-inf")
        hi = when.parse(end) if end else float("inf")
        if lo is None or hi is None:
            return tr("Даты не разобраны: {start} - {end}.", start=start,
                      end=end)
        self.toolbar.set_time_shown(True)
        self._time_toggled(True)
        self.timebar.set_range(lo, hi)
        return tr("Шкала времени: {start} - {end}.", start=start, end=end)

    def _tool_earth_cutaway(self, west=None, east=None, south=0.0,
                            north=90.0, off=False):
        if off:
            self.set_extra("cutaway", False)
            return tr("Разрез Земли убран.")
        if not self.planet.earth:
            return tr("Разрез Земли есть только у Земли.")
        if not self.extras.get("cutaway"):
            self.set_extra("cutaway", True)
        if west is not None and east is not None:
            self.set_wedge_box(west, east, south, north)
        wedge = self.view.wedge
        return tr("Сектор: {wedge}.", wedge=", ".join(
            "{:.1f}".format(v) for v in wedge))

    def _tool_section_down(self, points, depth_km=700.0):
        pts = [(float(p[0]), float(p[1])) for p in points]
        if len(pts) < 2:
            return tr("Для разреза нужны хотя бы две точки.")
        self._open_section(tr("Разрез помощника"), pts)
        dialog = self.section_dialog
        best = min(range(dialog.depth.count()), key=lambda i: abs(
            dialog.depth.itemData(i) - float(depth_km)))
        dialog.depth.setCurrentIndex(best)
        found = dialog.chart.section
        if found is None:
            return tr("Разрез не построен.")
        return tr("Разрез открыт: длина {length:.0f} км, глубина "
                  "{depth:.0f} км, очагов в полосе {count}.",
                  length=float(found.distance[-1]), depth=found.depth,
                  count=len(found.quakes))

    def _tool_point_info(self, lat, lon):
        lat, lon = float(lat), float(lon)
        height = float(self._true_heights(np.array([lat]),
                                          np.array([lon]))[0])
        groups = self._identify_site(lat, lon, height)
        if not groups:
            return tr("Сведений о точке нет.")
        values = groups[0][1][0][1]
        return "; ".join("{}: {}".format(k, v) for k, v in values)

    def _tool_quakes_summary(self, south, north, west, east):
        if not self.quake_events:
            self._want_quakes()
            return tr("Сводка землетрясений загружается, повтори запрос "
                      "через несколько секунд.")
        return assistant_core.quakes_text(
            self.quake_events, (float(south), float(north), float(west),
                                float(east)))

    def _tool_add_kml(self, kml):
        # Модель оборачивает документ текстом, оградой Markdown, прологом
        # с чужой кодировкой - снимается так же, как у ответа текстом.
        kml = assistant_core.extract_kml(str(kml)) or str(kml)
        try:
            tree = read_kml(kml.encode("utf-8"), tr("Помощник"))
        except KmlError as error:
            return tr("KML не разобран: {error}. Исправь документ.",
                      error=str(error))
        count = len(tree.places())
        if not count:
            return tr("В документе KML нет меток.")

        def write():
            # Ключ новой папки - для перелёта и для проверки.
            self.assistant_folder = self.myplaces.import_tree(tree)
            self._show_made_time(self.assistant_folder)
            return tr("В «Мои метки» записано меток: {count}.",
                      count=count)
        self.assistant_dialog.propose(
            tr("Помощник предлагает папку «{name}», меток {count}.",
               name=tree.name or tr("Помощник"), count=count), write)
        return tr("Документ показан пользователю, меток {count}. Запись - "
                  "после его подтверждения.", count=count)

    def _tool_get_kml(self):
        pose = self.view.navigator.pose
        out = [assistant_core.look_at_kml(pose.lat, pose.lon, pose.distance,
                                          pose.heading, pose.tilt)]
        keys = self.panel.list.selected_keys()
        if keys:
            out.append(write_kml(self.myplaces.export_keys(keys)))
        else:
            out.append(tr("Выделенных меток нет."))
        return "\n".join(out)

    def _identify_places(self, lat, lon, tolerance):
        """Видимые «Мои метки» под щелчком."""
        places = [p for p in self.myplaces.places
                  if p.visible and self._time_ok(p) and not p.tour
                  and p.body == self.planet.key and p.shape.points]
        hits = pick.picked([(p.shape.kind, p.shape.points) for p in places],
                           lat, lon, tolerance)
        kinds = {"point": tr("Метка"), "line": tr("Путь"),
                 "polygon": tr("Многоугольник")}
        features = []
        for n in hits:
            p = places[n]
            shape = p.shape
            values = [(tr("Тип"), kinds.get(shape.kind, shape.kind))]
            if shape.kind == "point":
                a, b = shape.points[0]
                values.append((tr("Координаты"), "{:.5f}, {:.5f}".format(
                    a, b)))
            elif shape.kind == "line":
                values.append((tr("Длина"), distance_text(
                    pick.path_length(shape.points))))
            else:
                values.append((tr("Периметр"), distance_text(
                    pick.path_length(shape.points, closed=True))))
            if p.measure:
                values.append((tr("Измерение"), p.measure))
            if p.description:
                values.append((tr("Описание"), p.description))
            features.append((shape.name or tr("Без названия"), values, None))
        return [(Group(tr("Мои метки")), features)] if features else []

    def _identify_quakes(self, px, py):
        """Очаги землетрясений на глобусе у точки щелчка на экране."""
        layer = self.view.quakes
        if not layer.events:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        shown = quakes.facing(eye, layer.epicenter, layer.lats, layer.lons) \
            & quakes.in_window(layer.times, layer.window)
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        near = np.zeros(len(layer.events), dtype=bool)
        for points in (layer.focus, layer.epicenter):
            pixels, front = self.view.camera.project(points)
            gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
            near |= front & (gap <= radius)
        features = []
        for n in np.nonzero(near & shown)[0]:
            q = layer.events[int(n)]
            values = [(tr("Магнитуда"), "{:.1f}".format(q.mag)),
                      (tr("Глубина очага"), tr("{value} км", value=(
                          "{:.0f}".format(q.depth))))]
            if q.time is not None:
                values.append((tr("Время, UTC"), when.text(q.time)))
            if q.url:
                values.append((tr("Страница USGS"), q.url))
            features.append((q.place or "M {:.1f}".format(q.mag), values,
                             None))
        return [(Group(tr("Землетрясения")), features)] if features else []

    def _identify_satellites(self, px, py):
        """Спутник у точки щелчка на экране, группа окна «Объекты»."""
        found = self.satellite_manager.identify(px, py)
        features = [(name, values, None) for name, values in found]
        return [(Group(tr("Спутники")), features)] if features else []

    def _identify_fires(self, px, py):
        """Очаги пожаров у точки щелчка на экране, не больше 20."""
        layer = self.view.fires
        data = layer.fires
        if data is None:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        shown = quakes.facing(eye, layer.focus, layer.lats, layer.lons) \
            & quakes.in_window(layer.times, layer.window)
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        pixels, front = self.view.camera.project(layer.focus)
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        near = np.nonzero(front & shown & (gap <= radius))[0]
        near = near[np.argsort(gap[near])][:20]
        features = []
        for n in near:
            n = int(n)
            values = [(tr("Мощность излучения"), tr(
                "{value} МВт", value="{:.1f}".format(data.frp[n])))]
            if not np.isnan(data.time[n]):
                values.append((tr("Время снимка, UTC"),
                               when.text(float(data.time[n]))))
            if data.confidence[n]:
                values.append((tr("Достоверность"), data.confidence[n]))
            values.append((tr("Снимок"), tr("ночной") if data.night[n]
                           else tr("дневной")))
            features.append(("{:.4f}, {:.4f}".format(data.lat[n],
                                                     data.lon[n]),
                             values, None))
        return [(Group(tr("Пожары")), features)] if features else []

    def _plate_names(self):
        """Подписи групп и классов границ плит на языке интерфейса."""
        return ({"divergent": tr("Раздвиг плит"),
                 "transform": tr("Сдвиг плит"),
                 "convergent": tr("Схождение плит")},
                {"OSR": tr("Океанический спрединговый хребет"),
                 "CRB": tr("Континентальный рифт"),
                 "OTF": tr("Океанический трансформный разлом"),
                 "CTF": tr("Континентальный трансформный разлом"),
                 "SUB": tr("Зона субдукции"),
                 "OCB": tr("Океаническая граница схождения"),
                 "CCB": tr("Континентальная коллизия")})

    def _set_plates(self, on):
        """Строка «Границы плит»: линии границ в наложении, названия
        плит надписями глобуса. Файл data/plates.json читается при
        первом включении."""
        if on and self.plates_data is None:
            try:
                with open(os.path.join(DATA_DIR, "plates.json"),
                          encoding="utf-8") as fh:
                    self.plates_data = plates.Plates.from_text(fh.read())
            except (OSError, ValueError) as error:
                self.message = (tr("Границы плит не прочитаны: {error}",
                                   error=str(error)), time.monotonic())
                self._show_state()
                return
        if on and self.plate_layer is None:
            self.plate_layer = plate_layer(self.plates_data,
                                           self._plate_names()[0])
        self.view.plate_marks = [
            MarkPlace(-300000 - n, p.name, "plate", 1, p.lat, p.lon)
            for n, p in enumerate(self.plates_data.plates)] \
            if on and self.plates_data is not None else []
        self._update_overlay(keep=True)
        self._show_attribution()
        self.view.update()

    def _identify_plates(self, lat, lon, tolerance):
        """Граница плит у точки щелчка, когда строка включена."""
        if not (self.planet.earth and self.extras.get("plates")
                and self.plates_data is not None):
            return []
        found = plates.nearest(self.plates_data, lat, lon, tolerance)
        if found is None:
            return []
        groups, classes = self._plate_names()
        values = [(tr("Тип"), classes.get(found.code, found.code)),
                  (tr("Плиты"), found.pair),
                  (tr("Скорость"), tr("{value} мм/год",
                                      value="{:.0f}".format(found.speed)))]
        return [(Group(tr("Граница плит")), [
            (groups[plates.group(found.code)], values, None)])]

    def _identify_site(self, lat, lon, height):
        """Место под щелчком: высота или глубина, кора CRUST1.0, плита
        Slab2. Кора и зона плиты просятся, если их нет, окно обновится
        по их приходу."""
        if not self.planet.earth:
            return []
        values = []
        if height is not None:
            kind, value = surface_level(height)
            values.append((tr("Глубина") if kind == "depth"
                           else tr("Высота"), tr("{value} м",
                                                 value=str(value))))
        self._want_crust()
        if self.crust is not None:
            bounds = self.crust.at([lat], [lon])[0].astype(float)
            sediments = float(bounds[2] - bounds[5])
            values.append((tr("Мохо"), tr("{value} км", value="{:.1f}".format(
                -bounds[-1]))))
            values.append((tr("Толщина коры"), tr("{value} км", value=(
                "{:.1f}".format(bounds[1] - bounds[-1])))))
            if sediments > 0.0:
                values.append((tr("Осадки"), tr("{value} км", value=(
                    "{:.1f}".format(sediments)))))
        elif self._crust_reply is not None:
            values.append((tr("Кора"), tr("загружается")))
        codes = slabs.touched(self._read_slab_index(), [lat], [lon])
        self._request_slabs(codes)
        zones = [self.slab_zones[c] for c in codes if c in self.slab_zones]
        top, bottom = slabs.band(zones, [lat], [lon])
        if np.isfinite(top[0]):
            values.append((tr("Плита Slab2"), tr(
                "{top}-{bottom} км", top="{:.0f}".format(top[0]),
                bottom="{:.0f}".format(bottom[0]))))
        elif any(c in self._slab_replies for c in codes):
            values.append((tr("Плита Slab2"), tr("загружается")))
        return [(Group(tr("Место")), [(tr("Под точкой"), values, None)])] \
            if values else []

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
        # Сообщение о закрытии уходит и после ошибки по дороге, иначе
        # плагин держит ссылку на окно, которое Qt уже уничтожил.
        try:
            # Закрытое окно Qt удаляет позже. До того правки проекта, в том
            # числе его очистка при выходе QGIS, будили бы окно, и оно
            # собирало бы новое наложение со слоями вне проекта. Их
            # удаление после выхода роняло QGIS 3.36.
            self.watch.blockSignals(True)
            self.sync.close()
            self._layer_time_timer.stop()
            self._link_timer.stop()
            self.satellite_manager.close()
            self.route_manager.close()
            self.layer_labels.close()
            if self.identified is not None:
                self.identified.close()
            if self.ruler_dialog is not None:
                self.ruler_dialog.close()
            if self.place_dialog is not None:
                self.place_dialog.close()
            if self.viewshed_dialog is not None:
                self.viewshed_dialog.close()
            if self.section_dialog is not None:
                self.section_dialog.close()
            if self.assistant_dialog is not None:
                self.assistant_dialog.close()
            self.viewshed_timer.stop()
            if self.viewshed_tiles is not None:
                self.viewshed_tiles.abort()
            if self.insolation_dialog is not None:
                self.insolation_dialog.close()
            self.insolation_timer.stop()
            self.insolation_job = None
            if self.insolation_tiles is not None:
                self.insolation_tiles.abort()
            self.subsurface.close()
            self.loader.abort()
            if self.place_loader is not None:
                self.place_loader.abort()
            # У тела без высот загрузчика высот нет.
            for loader in list(self.gibs_loaders.values()) + [
                    self.terrain_loader, self.sky_loader,
                    self.buildings_loader]:
                if loader is not None:
                    loader.abort()
            if self.overlay is not None:
                self.overlay.abort()
            # Растры картинок на поверхности не входят в проект, их держит
            # окно. Они отпускаются здесь, пока QGIS жив, а не при разборе
            # Python после выхода.
            self._ground_rasters = []
            self._ground_ids = []
            self.ground_layers.clear()
            self.refresh_timer.stop()
            set_moving(False)
            if self.properties is not None:
                self.properties.close()
            sys.setswitchinterval(self._switch_interval)
        finally:
            super().closeEvent(event)
            # Окно с WA_DeleteOnClose Qt уничтожает позже. Плагин
            # узнаёт о закрытии сразу, чтобы меню открыло новое окно.
            self.closed.emit()