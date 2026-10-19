# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно глобуса по образцу 3D-сцены Isoliner3D.

Слева панель: координаты, список источников и слоёв, строка состояния
(ui/panel.py). Справа вид OpenGL, в его левом верхнем углу плавающая
панель значков (ui/toolbar.py), в правом нижнем подпись источников.
Окно связывает части и решает, панели только показывают.

Методы окна разнесены по примесям пакета ui/globe по разделам: state,
themes, earthdata, body, layers, search, places, actions, tools,
pictures, identify, resources. Здесь - создание окна и его закрытие.
"""
import os
import sys
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QSize, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QFont, QIcon, QKeySequence, QPixmap
from qgis.PyQt.QtWidgets import (QGraphicsDropShadowEffect, QLabel,
                                 QSplitter, QToolButton, QVBoxLayout,
                                 QWidget)
from qgis.utils import iface

from .. import journal
from ..core import (ellipsoid, fields, geoid, paleo, infra, mining, themes,
                    tilemaps)
from ..core.coords import FORMATS as COORD_FORMATS
from ..core.geocode import SEARCH_INTERVAL
from ..core.planets import EARTH_PLANET
from ..core.sync import BOTH, DIRECTIONS
from ..core.terrain import MAX_LEVEL as TERRAIN_MAX
from .overpass import OverpassTiles
from .flow import FlowManager
from .rumsey import RumseyLoader
from ..core.places import AS_QGIS, LABEL_LANGUAGES, LOCAL
from ..i18n import tr
from ..net.loader import set_moving
from ..net.overlay import VECTOR_GROUPS
from ..qt_compat import QAction, enum
from ..render.view import GlobeView, start_keys
from .about import show_about
from .snapshot import BRAND_HEIGHT, brand_image
from . import guide as guide_ui
from . import style
from .sidepanel import SidePanel
from .layer_labels import LayerLabels
from .legend import (BedsLegend, ContourLegend, CutawayLegend, DepositLegend,
                     FireLegend, InsolationLegend, LegendPanel, QuakeLegend,
                     SlopeLegend, TemperatureLegend, ThemeLegend,
                     ClassLegend, CurrentLegend, FaultLegend, FieldLegend,
                     InfraLegend, PointCloudLegend,
                     PlantLegend, TrainLegend, VolcanoLegend,
                     VesselLegend, AircraftLegend)
from .overlays import GroundLayers, ScreenOverlays
from .spinner import LoadSpinner
from .handles import DrawVertices, Handles
from .measure import Ruler
from .myplaces import MyPlaces
from .paleo import PaleoBar
from .panel import LayerPanel
from .project import (AUTO_REFRESH, ProjectWatch, read_flag, read_grids,
                      read_map_years, read_zlayers)
from .inset import DeepSource
from .contours import ContourExport
from .netlink import NetLinks
from .extrude import ExtrudeManager
from .navpad import NavPad
from .skylabels import SkyLabels
from .properties import SCALE_RANGE
from .pointcloud import PointCloudManager
from .subsurface import SubsurfaceManager
from .record import TourRecorder
from .tour import TourPlayer
from .routing import RouteManager
from .weather import WeatherManager
from .satellites import SatelliteManager
from .track import TrackManager
from .trains import TrainManager
from .live import AircraftManager, VesselManager
from .flightsim import FlightSim
from .swipe import SwipeBar
from .sync import MapSync
from .timebar import TimeBar
from .toolbar import ViewToolbar
from .globe.base import (ACCEPTED_KEY, ATTRIBUTION_STYLE, AUTO_DEFAULT,
                         BRAND_STYLE,
                         BASEMAP_KEY, CONSTELLATIONS_KEY, COORDS_KEY,
                         DEFAULT_GROUPS, EXTRA_DEFAULTS, EXTRA_KEY,
                         FLOW_LAYERS, GIBS_FADES, GROUND_DELAY, GUIDE_DELAY,
                         LANGUAGE_KEY, LAYER_TIME_DELAY, LINES_KEY, LINK_TICK,
                         MARGIN, NEW_SHOWN_KEY, OPACITY_PAUSE, OSM_PAUSE,
                         PANEL_WIDTH, POINT_LAYERS, READY_KEY, RECORD_PERIOD,
                         RELIEF_KEY, SCALE_KEY, SEA_KEY, SIDEBAR_KEY,
                         SWITCH_INTERVAL, SYNC_KEY, TERRAIN_MIRRORS,
                         THEME_DELAY, THEME_KEY, VIEWSHED_POLL, _RulerVertices,
                         _WedgeCorners, all_sources)
from .globe.state import StateMixin
from .globe.themes import ThemesMixin
from .globe.earthdata import EarthDataMixin
from .globe.body import BodyMixin
from .globe.layers import LayersMixin
from .globe.search import SearchMixin
from .globe.places import PlacesMixin
from .globe.actions import ActionsMixin
from .globe.tools import ToolsMixin
from .globe.pictures import PicturesMixin
from .globe.identify import IdentifyMixin
from .globe.resources import ResourcesMixin

# Имена, которые берут из модуля окна снаружи.
__all__ = ("GlobeWindow", "ACCEPTED_KEY", "READY_KEY", "TERRAIN_MIRRORS",
           "all_sources")


def _shadow(widget):
    """Тёмная тень светлого текста подписи: на светлом снимке её
    держит тень, на тёмном - сам цвет."""
    effect = QGraphicsDropShadowEffect(widget)
    effect.setBlurRadius(4.0)
    effect.setOffset(1.0, 1.0)
    effect.setColor(QColor(0, 0, 0, 220))
    return effect


class GlobeWindow(StateMixin, ThemesMixin, EarthDataMixin, BodyMixin,
                  LayersMixin, SearchMixin, PlacesMixin, ActionsMixin,
                  ToolsMixin, PicturesMixin, IdentifyMixin, ResourcesMixin,
                  QWidget):
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
        # Оформление - до плашек и значков, они берут его цвета.
        style.apply(QgsSettings().value(style.THEME_KEY, style.DARK))

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
        self.timebar.compare_toggled.connect(self.set_compare)
        # Шторка сравнения двух дней темы: момент левой части или None.
        self.swipe_bar = SwipeBar(self.view)
        self.swipe_bar.moved.connect(self._swipe_moved)
        self.swipe_bar.stepped.connect(self._compare_step)
        self.swipe_bar.closed.connect(lambda: self.set_compare(False))
        self._compare_at = None
        self._compare_shown = None
        # Шторка исторических карт: момент левой части, ключ её сборки, растры
        # картинок на поверхности левой части и загрузчик её наложения.
        self._map_compare_at = None
        self._map_compare_key = None
        self.compare_grounds = GroundLayers()
        self.map_compare_overlay = None
        self.view.on_motion = set_moving
        self.view.load_changed.connect(self._show_state)
        self.panel = LayerPanel(self)
        self.panel.setObjectName("planetxPanel")
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
        self.attribution.setStyleSheet(ATTRIBUTION_STYLE)
        font = QFont(self.attribution.font())
        font.setPointSizeF(font.pointSizeF() * 0.85)
        self.attribution.setFont(font)
        self.attribution.setGraphicsEffect(_shadow(self.attribution))
        self.attribution.setToolTip(tr(
            "Источники того, что на глобусе. Щелчок открывает окно "
            "«Источники данных» с полными подписями и условиями."))
        self.attribution.linkActivated.connect(
            lambda _link: QTimer.singleShot(0, self.open_sources))
        # Знак PlanetX в правом нижнем углу, щелчок - «О модуле».
        self.brand = QToolButton(self.view)
        self.brand.setStyleSheet(BRAND_STYLE)
        ratio = self.devicePixelRatioF()
        mark = QPixmap.fromImage(brand_image(BRAND_HEIGHT * ratio))
        mark.setDevicePixelRatio(ratio)
        self.brand.setIcon(QIcon(mark))
        self.brand.setIconSize(QSize(int(mark.width() / ratio),
                                     int(mark.height() / ratio)))
        self.brand.setCursor(enum(Qt, "CursorShape", "PointingHandCursor"))
        self.brand.setToolTip(tr("О модуле"))
        self.brand.clicked.connect(
            lambda _=False: QTimer.singleShot(0, lambda: show_about(self)))
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
        self.deposit_legend = DepositLegend(self.view)
        self.deposit_legend.hide()
        self.deposit_legend.closer = self._close_deposit_legend
        self.plant_legend = PlantLegend(self.view)
        self.plant_legend.hide()
        self.plant_legend.closer = lambda: self.set_extra("plants", False)
        self.volcano_legend = VolcanoLegend(self.view)
        self.volcano_legend.hide()
        self.volcano_legend.closer = \
            lambda: self.set_extra("volcanoes", False)
        self.infra_legend = InfraLegend(self.view)
        self.infra_legend.hide()
        self.infra_legend.closer = lambda: self.set_extra("infra_osm", False)
        self.fault_legend = FaultLegend(self.view)
        self.fault_legend.hide()
        self.fault_legend.closer = lambda: self.set_extra("faults", False)
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
        # Горизонтали: сечение, крестик и выгрузка в проект.
        self.contour_legend = ContourLegend(self.view)
        self.contour_legend.hide()
        self.contour_legend.closer = \
            lambda: self.set_extra("contours", False)
        self._contour_palette = "map"
        # Крестик на шкале карты витрины убирает карту.
        for legend in (self.theme_legend, self.fire_legend, self.legend):
            legend.closer = lambda: self.set_theme("")
        # Шкалы - одной панелью, сверху вниз: тема, пласты, оболочки
        # разреза, очаги, пожары, инсоляция, уклон, температура.
        self.legend_panel = LegendPanel(self.view)
        for legend in (self.theme_legend, self.beds_legend,
                       self.cutaway_legend, self.quake_legend,
                       self.fire_legend, self.deposit_legend,
                       self.plant_legend, self.volcano_legend,
                       self.infra_legend, self.fault_legend,
                       self.insolation_legend,
                       self.slope_legend, self.contour_legend,
                       self.legend):
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
        # Годы исторических карт проекта и растры-карты, скрытые при сборке
        # наложения правилом «последняя карта не позже момента».
        self._map_years = read_map_years()
        self._applied_maps = frozenset()
        # Наложения картинок: растры картинок на поверхности в наложении,
        # ключи показанных фото и картинок на экране, текстуры фото,
        # окна свойств и их правки.
        self.ground_layers = GroundLayers()
        self._ground_rasters = []
        self._ground_ids = []
        self._photo_key = None
        # 3D-модели: разобранные пакеты по метке и место на глобусе.
        self._model_cache = {}
        self._model_key = None
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
        # Исторические землетрясения (ISC-GEM): каталог, ждущий ответ
        # и собранные части каталога, пока идут запросы по промежуткам.
        self.history_events = None
        self._history_reply = None
        self._history_parts = []
        # Пожары NASA FIRMS: очаги сводки и ждущий ответ.
        self.fire_data = None
        self._fire_reply = None
        # Месторождения USGS: данные, ждущие ответы двух архивов, задача
        # разбора в рабочем потоке.
        self.deposit_data = None
        # Контуры горных разработок (core/mining.py): слой QGIS из файла
        # профиля и его загрузка.
        self.mining_layer = None
        self._mining_reply = None
        # Шахты и карьеры OSM: объекты по тайлам, очередь тайлов, запрос
        # Overpass в работе и время последнего запроса.
        self.osm_mines_tiles = OverpassTiles(
            self.view, "mines", mining.query, mining.parse,
            self._place_osm_mines, self._overpass_failed)
        # ЛЭП, подстанции и трубопроводы OSM (core/infra.py): тот же
        # загрузчик, слои QGIS в памяти в картинке тайлов.
        self.infra_tiles = OverpassTiles(
            self.view, "infra", infra.query, infra.parse,
            self._place_infra, self._overpass_failed)
        self.infra_lines = None
        self.infra_points = None
        # Электростанции WRI (core/plants.py): файл профиля, загрузка
        # архива и разбор в рабочем потоке.
        self.plant_data = None
        # Вулканы GVP (core/volcanoes.py): файл профиля, загрузка.
        self.volcano_data = None
        self._volcano_reply = None
        self._plant_reply = None
        self._plant_job = None
        self._osm_timer = QTimer(self)
        self._osm_timer.setSingleShot(True)
        self._osm_timer.setInterval(OSM_PAUSE)
        self._osm_timer.timeout.connect(self._want_overpass)
        self._deposit_replies = {}
        self._deposit_bytes = {}
        self._deposit_job = None
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
        # Подводные кабели OSM (core/cables.py), файл data/cables.json.
        self.cables_data = None
        self.geomag = None  # (модель IGRF, таблицы полюсов), core/geomag
        # Линии склонения: (год, линии) и подписи.
        self._decl_cache = None
        self._decl_marks = []
        # Скорости плит (core/platemotion.py): модель, стрелки, подписи.
        self.plate_motion = None
        self.motion_shapes = []
        self._motion_marks = []
        self._motion_key = None
        # Адреса тайлов карт значений (core/fields.py), шаги проверки
        # ставят локальную копию planetx-terrain.
        self.field_urls = {key: fields.url(f)
                           for key, f in fields.FIELDS.items()}
        self.geoid_url = geoid.TILE_URL
        self._field_shown = None  # ключ карты на глобусе
        # (ключ, точка, значение или None, ошибка) - значение под щелчком.
        self._field_value = None
        self._field_reply = None
        # Карты картинками (core/tilemaps.py): адреса тайлов (шаги
        # проверки ставят локальную копию planetx-terrain), карта на
        # глобусе, значение под щелчком и его запрос.
        self.tilemap_urls = {key: m.url for key, m in tilemaps.MAPS.items()}
        self.tilemap_coarse = {key: m.coarse
                               for key, m in tilemaps.MAPS.items()}
        self._tilemap_shown = None
        self._tilemap_value = None
        self._tilemap_reply = None
        self.cable_layer = None
        # Наложения тайлов (core/tileoverlays.py): ключ - слой XYZ QGIS.
        self.tile_layers = {}
        # Активные разломы GEM (core/faults.py): файл профиля, загрузка,
        # разбор в рабочем потоке, слой наложения.
        self.faults_data = None
        self.fault_layer = None
        self._fault_reply = None
        self._fault_job = None
        # Геологическая карта Macrostrat (core/geology.py): запрос
        # и ответ о породе под щелчком.
        self._geology_reply = None
        self._geology_value = None
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
        # Панель свойств справа от вида (ui/sidepanel.py): окна свойств
        # метки, папки, картинки, батиметрии и выдавливания.
        self.side = SidePanel(self)
        self.side.setObjectName("planetxSide")
        self.setObjectName("planetxWindow")
        for part in (self, self.panel, self.side):
            part.setAttribute(enum(Qt, "WidgetAttribute",
                                   "WA_StyledBackground"))
        self.setStyleSheet(style.window_style())
        # Заголовки окна глобуса и окон модуля по оформлению.
        self.title_bars = style.TitleBars(self)
        style.title_bar(self)
        splitter.addWidget(self.side)
        # Разделитель показывает добавленную панель, пустая - скрыта.
        self.side.hide()
        splitter.setCollapsible(2, False)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([PANEL_WIDTH, 1300, 0])
        self.side.changed.connect(self._side_changed)
        splitter.splitterMoved.connect(self._side_moved)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(splitter)

        # Первая встроенная подложка, Esri World Imagery, - по умолчанию.
        self.sources = all_sources()
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
        self._update_water()
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
        # Адреса пункта «Что здесь?»: ответы по ключу (широта, долгота,
        # язык), очередь - общая с поиском по SEARCH_INTERVAL.
        self._addresses = {}
        self._address_key = None
        self._address_reply = None
        self._address_timer = QTimer(self)
        self._address_timer.setSingleShot(True)
        self._address_timer.timeout.connect(self._send_address)
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
        # Действия модуля в строке «Поиск» (ui/commands.py): функции
        # последнего списка подсказок по ключу. Ctrl+K в окне глобуса
        # ставит курсор в строку и показывает включённое и прежние
        # запросы.
        self._actions = {}
        # Знакомство с модулем (ui/guide.py): при первом открытии окна
        # в профиле, потом - по действию строки «Поиск».
        self.guide = None
        if guide_ui.first_time():
            QTimer.singleShot(GUIDE_DELAY, self.start_guide)
        find = QAction(self)
        find.setShortcut(QKeySequence("Ctrl+K"))
        find.setShortcutContext(
            enum(Qt, "ShortcutContext", "WindowShortcut"))
        find.triggered.connect(self.focus_search)
        self.addAction(find)
        self.panel.layer_toggled.connect(self.set_layer_shown)
        self.panel.geo_changed.connect(self.set_line_groups)
        self.panel.relief_toggled.connect(self.set_relief)
        self.panel.relief_model_chosen.connect(self.set_relief_model)
        self.panel.sea_toggled.connect(self.set_sea_depths)
        self.panel.sea_model_chosen.connect(self.set_sea_model)
        self.panel.sources_requested.connect(self.open_sources)
        self.panel.fly_to_layer.connect(self.fly_to_layer)
        self.panel.opacity_changed.connect(self.set_layer_opacity)
        self.panel.layer_properties.connect(iface.showLayerProperties)
        self.toolbar.refresh_clicked.connect(self.refresh)
        # Боковая панель прячется значком, как в Google Earth. Состояние
        # помнится между запусками.
        self.toolbar.sidebar_clicked.connect(
            lambda: self.set_sidebar(self.panel.isHidden()))
        self.set_sidebar(QgsSettings().value(SIDEBAR_KEY, True, type=bool))
        # Во весь экран для показа, просьба автора от 15 октября 2026
        # года. F11 включает и выключает, Esc - только выключает, пока
        # режим включён, иначе Esc остаётся у вида и инструментов.
        self._windowed = None
        self.toolbar.fullscreen_clicked.connect(self.toggle_fullscreen)
        self._full_key = self._window_key("F11", self.toggle_fullscreen)
        self._full_escape = self._window_key("Esc", self.toggle_fullscreen)
        self._full_escape.setEnabled(False)
        self.toolbar.about_clicked.connect(lambda: show_about(self))
        self.toolbar.properties_clicked.connect(self._show_properties)
        self.toolbar.save_view_requested.connect(self.save_view)
        # «Мои метки»: общий файл профиля QGIS, объекты на глобусе.
        self.myplaces = MyPlaces(parent=self)
        self.netlinks = NetLinks(self)
        self.panel.is_link = lambda key: bool(
            getattr(self.myplaces.find(key), "link", ""))
        # Открытые окна свойств меток и их правки для глобуса по ключу.
        self.previews = {}
        self.prop_dialogs = {}
        # Region KML: метки, скрытые по расстоянию, и цепочки Region
        # метки и папок над ней, см. _update_regions.
        self._region_hidden = frozenset()
        self._region_eye = None
        self._region_items = None
        self.myplaces.changed.connect(self._regions_changed)
        self.view.changed.connect(self._update_regions)
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
        # Ползунок непрозрачности выделенного: цвета выделения снимаются
        # при выделении, запись идёт после паузы OPACITY_DELAY в
        # движении ползунка.
        self._opacity_items = []
        self._opacity_base = 1.0
        self._opacity_value = 1.0
        self._opacity_timer = QTimer(self)
        self._opacity_timer.setSingleShot(True)
        self._opacity_timer.timeout.connect(self._apply_opacity)
        self.panel.places_selected.connect(self._opacity_selection)
        self.panel.opacity_moved.connect(self._opacity_moved)
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
        self.contour_export = ContourExport(self)
        self.extruder = ExtrudeManager(self)
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
        self.toolbar.copy_clicked.connect(self.copy_view)
        # Подземный режим: скважины, кровли, разрезы, вырез блока.
        self.subsurface = SubsurfaceManager(self)
        # Облака точек слоёв проекта (ui/pointcloud.py).
        self.pointclouds = PointCloudManager(self)
        self.model_section_dialog = None
        self.panel.subsurface_requested.connect(self.subsurface.open_dialog)
        self.toolbar.set_auto(self.auto_refresh)
        self.myplaces.load()
        # Тур по отмеченным «Моим меткам».
        self.tour = TourPlayer(self.view, self._tour_stops, self)
        self.tour.bar.attach(self.timebar)
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
        self.tour.stop_reached.connect(self._stop_reached)
        # Растущие треки точечных слоёв по шкале времени глобуса.
        self.tracks = TrackManager(self.view, self)
        self.tracks.changed.connect(self._refresh_shapes)
        self.tracks.reloaded.connect(self._update_data_marks)
        self._update_data_marks()
        self.panel.track_requested.connect(self._open_track)
        self.panel.inset_toggled.connect(self.set_inset)
        self.panel.bathymetry_requested.connect(self.edit_bathymetry)
        self.panel.map_year_requested.connect(self.edit_map_year)
        self.panel.sounding_requested.connect(self.sounding_bathymetry)
        self.panel.volume_requested.connect(self.volume_compare)
        self.panel.grid_toggled.connect(self.set_grid)
        self.panel.contours_requested.connect(
            lambda layer: self.contour_export.grid_contours(layer))
        self.panel.extrude_requested.connect(
            lambda layer: self.extruder.configure(layer))
        self.panel.ground_alpha.connect(
            lambda value: self.subsurface.set_opacity(value))
        self.panel.grid_ids = set(read_grids())
        self.panel.zlayer_toggled.connect(self.set_zlayer)
        self.panel.pointcloud_style.connect(self.set_pointcloud_style)
        self.panel.zlayer_ids = set(read_zlayers())
        self.toolbar.scene_save_requested.connect(self.save_scene)
        self.toolbar.scene_open_requested.connect(self.open_scene)
        self.toolbar.share_requested.connect(self.share_view)
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
        # Модель рельефа 30 м поверх Terrarium (core/dem.py) или None.
        self.dem = self._make_dem()
        # Глубины GEBCO поверх дна тайлов высот или None.
        self.sea_dem = self._make_sea()
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
        self._update_relief_menu()
        self.panel.basemap_chosen.connect(self._panel_basemap)
        self.panel.add_source_requested.connect(self.add_tile_source)
        self.panel.ready_requested.connect(self.add_ready_source)
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
        # Раздел «На глобусе».
        self.panel.active_off.connect(self._active_off)
        self.panel.active_toggled.connect(self._active_toggle)
        # Строки «На глобусе», выключенные флажком: остаются в разделе
        # до «Убрать с глобуса». У карты витрины - её ключ.
        self._parked = {}
        self.panel.active_opacity.connect(self._active_opacity)
        self.panel.active_export.connect(self.active_export)
        self.panel.geoid_scale = self.geoid_scale()
        self.panel.geoid_scale_changed.connect(self.set_geoid_scale)
        self.panel.cutaway_stretch = self.cutaway_stretch()
        self.view.wedge_stretch = self.panel.cutaway_stretch
        self.panel.cutaway_stretch_changed.connect(self.set_cutaway_stretch)
        self.tomo = None
        self._tomo_reply = None
        self._tomo_job = None
        self.panel.cutaway_tomo = self.cutaway_tomo()
        self.panel.cutaway_tomo_changed.connect(self.set_cutaway_tomo)
        self._crust_export = None
        self.panel.crust_export.connect(self.crust_to_project)
        self._opacity_overlay = QTimer(self)
        self._opacity_overlay.setSingleShot(True)
        self._opacity_overlay.setInterval(OPACITY_PAUSE)
        self._opacity_overlay.timeout.connect(
            lambda: self._update_overlay(keep=True))
        for key in tuple(POINT_LAYERS) + tuple(GIBS_FADES) \
                + tuple(FLOW_LAYERS):
            self._apply_layer_opacity(key)
        # Спутники CelesTrak - строка с группами (ui/satellites.py).
        self.satellite_manager = SatelliteManager(self)
        self.satellite_manager.changed.connect(self._show_attribution)
        # Поезда Финляндии вживую (ui/trains.py).
        self.train_manager = TrainManager(self)
        self.train_manager.changed.connect(self._show_attribution)
        self.train_legend = TrainLegend(self.view)
        self.train_legend.hide()
        self.legend_panel.add(self.train_legend)
        self.train_legend.closer = lambda: self.set_extra("trains", False)
        # Суда Балтики и самолёты вживую (ui/live.py).
        self.vessel_manager = VesselManager(self)
        self.aircraft_manager = AircraftManager(self)
        self.vessel_legend = VesselLegend(self.view)
        self.aircraft_legend = AircraftLegend(self.view)
        for key, manager, legend in (
                ("vessels", self.vessel_manager, self.vessel_legend),
                ("aircraft", self.aircraft_manager, self.aircraft_legend)):
            manager.changed.connect(self._show_attribution)
            legend.hide()
            self.legend_panel.add(legend)
            legend.closer = lambda key=key: self.set_extra(key, False)
        # Живые объекты: запись облёта ведёт их по своим часам.
        self.live_managers = (self.train_manager, self.vessel_manager,
                              self.aircraft_manager)
        # Режим полёта своего самолёта (ui/flightsim.py).
        self.flight = FlightSim(self)
        self.route_manager = RouteManager(self)
        # Погода: поля прогноза GFS темой группы «Погода», окна прогноза
        # в точке.
        self.weather = WeatherManager(self)
        self.weather.changed.connect(self._weather_changed)
        # Струйки ветра и течений (ui/flow.py).
        self.flow = FlowManager(self)
        # Карты Рамсея: каталог и сборка карт (ui/rumsey.py).
        self.rumsey_loader = RumseyLoader(self)
        self.flow.changed.connect(self._flow_changed)
        self.current_legend = CurrentLegend(self.view)
        self.current_legend.hide()
        self.legend_panel.add(self.current_legend)
        self.current_legend.closer = lambda: self.set_extra("currents",
                                                            False)
        self.field_legend = FieldLegend(self.view)
        self.field_legend.hide()
        self.legend_panel.add(self.field_legend)
        self.cloud_legend = PointCloudLegend(self.view)
        self.cloud_legend.hide()
        self.legend_panel.add(self.cloud_legend)
        self.class_legend = ClassLegend(self.view)
        self.class_legend.hide()
        self.legend_panel.add(self.class_legend)
        self.class_legend.closer = lambda: self._tilemap_shown and \
            self.set_extra(self._tilemap_shown, False)
        self.field_legend.closer = lambda: (
            self._field_shown or self._tilemap_shown) and self.set_extra(
                self._field_shown or self._tilemap_shown, False)
        self.route_manager.finished.connect(self._route_done)
        self.panel.route_link.connect(self.route_manager.link)
        self.grid_shapes = []
        self._grid_key = None
        self.layer_labels = LayerLabels(self)
        self.layer_labels.changed.connect(self._show_layer_labels)
        self.view.changed.connect(self._update_layer_labels)
        self.view.changed.connect(self._update_grid)
        # Числа поля прогноза: поле на глобусе (Field, Grid) и ключ
        # узлов, см. _update_values.
        self._value_field = None
        self._value_key = None
        self.view.changed.connect(self._update_values)
        self.view.changed.connect(self._update_plate_arrows)
        self.view.changed.connect(self._update_contour_legend)
        self.view.changed.connect(self._overpass_view_changed)
        self.view.changed.connect(self._wayback_view)
        for key, on in self.extras.items():
            self._apply_extra(key, on)
        self.panel.gallery_requested.connect(self.open_gallery)
        # Включённые пожары и температура - тоже выбор карты витрины,
        # иначе пустая тема выключила бы их.
        self.set_theme(self.gallery_key() if any(
            self.extras.get(extra) for extra in themes.EXCLUSIVE)
            else settings.value(THEME_KEY, "") or "")
        self.refresh()

    def closeEvent(self, event):
        # Сообщение о закрытии уходит и после ошибки по дороге, иначе
        # плагин держит ссылку на окно, которое Qt уже уничтожил.
        journal.note(tr("Окно глобуса закрыто."))
        try:
            # Закрытое окно Qt удаляет позже. До того правки проекта, в том
            # числе его очистка при выходе QGIS, будили бы окно, и оно
            # собирало бы новое наложение со слоями вне проекта. Их
            # удаление после выхода роняло QGIS 3.36.
            self.watch.blockSignals(True)
            self.sync.close()
            self.netlinks.stop()
            self._layer_time_timer.stop()
            self._link_timer.stop()
            self.satellite_manager.close()
            self.train_manager.close()
            self.vessel_manager.close()
            self.aircraft_manager.close()
            self.flight.close()
            self.title_bars.close()
            self.route_manager.close()
            self.weather.close()
            self.flow.close()
            if getattr(self, "gallery", None) is not None:
                self.gallery.close()
            self._address_timer.stop()
            reply, self._address_reply = self._address_reply, None
            if reply is not None:
                reply.abort()
            for reply in (getattr(self, "_demo_replies", None)
                          or {}).values():
                reply.abort()
            self._demo_replies = None
            reply, self._parcel_reply = \
                getattr(self, "_parcel_reply", None), None
            self._parcels = None
            if reply is not None:
                reply.abort()
            self._drop_field()
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
            self.pointclouds.close()
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
            if self.map_compare_overlay is not None:
                self.map_compare_overlay.abort()
            self.compare_grounds.clear()
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
