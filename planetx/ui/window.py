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
import os
import sys
import time

from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform,
                       QgsProject, QgsSettings)
from qgis.PyQt.QtCore import QEvent, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QLabel, QSplitter, QVBoxLayout, QWidget
from qgis.utils import iface

from ..core import basemap
from ..core.ellipsoid import ecef_to_geodetic
from ..core.flight import Flight, fit_view, parse_latlon
from ..core.geocode import (SEARCH_INTERVAL, normalize, parse_places,
                            place_text, search_url)
from ..core.mipmap import mip_chain
from ..core.navigation import focal, ground_under
from ..core.sync import BOTH, DIRECTIONS
from ..core.terrain import MAX_LEVEL as TERRAIN_MAX, make_tile
from ..core.tiling import tile_mesh
from ..core.places import (AS_QGIS, LABEL_LANGUAGES, LOCAL, DecodeError,
                           decode_places, name_languages)
from ..core.places import Place as MarkPlace  # метка найденного места
from ..i18n import tr, ui_language
from ..net.loader import TERRARIUM_URL, TileLoader
from ..net.overlay import (BORDERS, LINE_GROUPS, OPENFREEMAP_ATTRIBUTION,
                           PLACES,
                           RAIL_FROM, RAILWAYS, VECTOR_GROUPS, label_kinds,
                           railway_layer,
                           OPENFREEMAP_TILEJSON, LayerOverlay, fetch_json,
                           openfreemap_layer, set_line_groups)
from ..qt_compat import enum
from ..render.view import GlobeView, start_keys
from .about import show_about
from .identify import IdentifyDialog, identify, point_text
from .panel import LayerPanel
from .project import (AUTO_REFRESH, ProjectWatch, map_layers, read_flag,
                      read_shown, write_flag, write_shown)
from .properties import SCALE_RANGE, PropertiesDialog
from .sync import MapSync
from .toolbar import ViewToolbar

TERRAIN_ATTRIBUTION = (
    '<a href="https://github.com/tilezen/joerd/blob/master/docs/'
    'attribution.md">Terrain: Mapzen, SRTM, GMTED, ETOPO1 and others</a>')
XYZ_PREFIX = "connections/xyz/items/"
BASEMAP_KEY = "PlanetX/basemap"  # имя выбранной подложки в настройках
# Включена ли группа линий векторной основы, по группам.
LINES_KEY = "PlanetX/lines/{}"
# Группы панели «Слои», включённые при первом открытии. Решение автора
# от 27 сентября 2026 года, рельеф включён отдельно.
DEFAULT_GROUPS = (BORDERS, PLACES)
RELIEF_KEY = "PlanetX/relief"  # показывать ли рельеф
SCALE_KEY = "PlanetX/relief_scale"  # вертикальный масштаб рельефа
LANGUAGE_KEY = "PlanetX/label_language"  # язык подписей
SYNC_KEY = "PlanetX/sync"  # направление синхронизации с картой
# Допуск щелчка при определении объектов, логических пикселей.
IDENTIFY_PIXELS = 5.0
CURSOR_PERIOD = 60  # мс между пересчётами точки под курсором
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


def heights_preparer(key, rgba):
    """Работа рабочего потока для тайла высот Terrarium."""
    return make_tile(*key, rgba)


def distance_text(metres):
    """Расстояние для строки состояния, метры или километры."""
    if metres < 10000.0:
        return tr("{value} м", value="%.0f" % metres)
    return tr("{value} км", value="{:,.0f}".format(metres / 1000.0)
              .replace(",", " "))


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

        self.view = GlobeView(self)
        self.panel = LayerPanel(self)
        self.place = self.panel.place
        self.status = self.panel.status
        self.toolbar = ViewToolbar(self.view)
        self.toolbar.move(MARGIN, MARGIN)
        self.attribution = QLabel(self.view)
        self.attribution.setOpenExternalLinks(True)
        self.attribution.setStyleSheet(ATTRIBUTION_STYLE)
        self.view.installEventFilter(self)
        splitter = QSplitter(self)
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
        self._places_source = None
        # Масштаб ставится до первой загрузки, сетки сразу собираются
        # с ним.
        self.view.set_relief(self._relief_target())
        self._applied_groups = None
        self._applied_layers = None
        # Слои проекта изменились с последнего обновления.
        self._layers_stale = False
        self.auto_refresh = read_flag(AUTO_REFRESH, False)
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
        self.panel.properties_requested.connect(self._show_properties)
        self.panel.layer_toggled.connect(self.set_layer_shown)
        self.panel.geo_changed.connect(self.set_line_groups)
        self.panel.relief_toggled.connect(self.set_relief)
        self.panel.fly_to_layer.connect(self.fly_to_layer)
        self.toolbar.refresh_clicked.connect(self.refresh)
        self.toolbar.about_clicked.connect(lambda: show_about(self))
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
        self._show_layers()
        self.panel.set_geo(self._groups, self._relief)
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
                "auto": self.auto_refresh}

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
        """Отметка слоя проекта в списке глобуса."""
        if on:
            self._shown.add(layer_id)
        else:
            self._shown.discard(layer_id)
        write_shown(self._shown)
        self._changed()

    def _relief_target(self):
        return self._scale if self._relief else 0.0

    def _read_shown(self):
        """Отметки слоёв из проекта.

        В проекте без записи не отмечен ни один слой, решение автора
        от 27 сентября 2026 года. Раньше отмечались слои, видимые на карте.
        """
        layers = map_layers()
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
        """Есть ли выбранное, что ещё не видно на глобусе."""
        return (self._basemap != self.sources.index(self.source)
                or self._relief_target() != self.view.store.scale
                or self._overlay_layers() != self._applied_layers
                or self._layers_stale)

    def refresh(self):
        """Показать на глобусе выбранные подложку, рельеф и слои."""
        self.refresh_timer.stop()
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
        self.view.label_kinds = label_kinds(self._groups)
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
                                 size=TILE_SIZE)
        self.loader.loaded.connect(self._loaded)
        self.loader.failed.connect(self._failed)
        self.view.loader = self.loader
        self._show_attribution()

    def _show_attribution(self):
        parts = [attribution_html(self.source)]
        if self._applied_groups and self.ofm_layer is not None:
            parts.append(link_html(*OPENFREEMAP_ATTRIBUTION))
        if self.view.store.scale:
            parts.append(TERRAIN_ATTRIBUTION)
        self.attribution.setText(" · ".join(parts))
        self._place_attribution()

    def _place_attribution(self):
        self.attribution.adjustSize()
        self.attribution.move(
            max(MARGIN, self.view.width() - self.attribution.width()
                - MARGIN),
            self.view.height() - self.attribution.height() - MARGIN)

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
        self._start_place_loader()
        self._update_overlay()
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

    def _project_changed(self):
        """Слои проекта изменились: обновить сразу или зажечь кнопку.

        Новый слой на глобус сам не попадает, его отмечают в списке.
        """
        self._known = {layer.id() for layer in map_layers()}
        # Перерисовка слоя меняет глобус, только если слой на нём.
        if self._applied_layers:
            self._layers_stale = True
        self._changed()

    def _project_reloaded(self):
        """Открыт другой проект: его настройки глобуса."""
        self.auto_refresh = read_flag(AUTO_REFRESH, False)
        self._read_shown()

    def _mark_dirty(self, dirty):
        self.dirty = dirty
        self.toolbar.set_dirty(dirty)
        self._show_state()

    def _set_auto(self, on):
        self.auto_refresh = bool(on)
        write_flag(AUTO_REFRESH, on)
        if on and self.dirty:
            self.refresh()

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
        self.properties.show()
        self.properties.raise_()
        self.properties.activateWindow()

    # Загрузка.

    def _heights(self, key, rgba, tile):
        self.terrain_errors.pop(key, None)
        self.view.add_heights(tile)

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
        target = parse_latlon(text)
        if target is not None:
            self.panel.set_found([])
            self._found = []
            self._mark(normalize(text), *target)
            distance = min(self.view.navigator.pose.distance,
                           FLIGHT_DISTANCE)
            self._fly_to(target[0], target[1], distance)
            return
        query = normalize(text)
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
        wgs = QgsCoordinateReferenceSystem("EPSG:4326")
        transform = QgsCoordinateTransform(layer.crs(), wgs,
                                           QgsProject.instance())
        box = transform.transformBoundingBox(layer.extent())
        camera = self.view.camera
        lat, lon, distance = fit_view(box.xMinimum(), box.yMinimum(),
                                      box.xMaximum(), box.yMaximum(),
                                      camera.fov_y, camera.aspect)
        self._fly_to(lat, lon, distance)

    # Определение объектов.

    def _set_identify(self, on):
        self.identifying = bool(on)
        self.view.setCursor(enum(Qt, "CursorShape", "WhatsThisCursor"
                                 if on else "OpenHandCursor"))

    def _clicked(self, px, py):
        """Щелчок по глобусу: точка рельефа и объекты слоёв под ней."""
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
        self.identified.show_result(point_text(lat, lon, height), found)

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
            if self._cursor_text:
                text += "\n" + self._cursor_text
        self.status.setText(text)

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
        if self._hover is not None:
            view = self.view
            point = ground_under(view.camera, *self._hover,
                                 view.navigator.pose.terrain)
            if point is not None:
                lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
                scale = view.store.scale
                text = point_text(lat, lon, h / scale if scale else None,
                                  digits=5)
        if text != self._cursor_text:
            self._cursor_text = text
            self._show_state()

    def closeEvent(self, event):
        self.sync.close()
        if self.identified is not None:
            self.identified.close()
        self.loader.abort()
        self.terrain_loader.abort()
        if self.place_loader is not None:
            self.place_loader.abort()
        if self.overlay is not None:
            self.overlay.abort()
        self.refresh_timer.stop()
        if self.properties is not None:
            self.properties.close()
        sys.setswitchinterval(self._switch_interval)
        super().closeEvent(event)
        # Окно с WA_DeleteOnClose Qt уничтожает позже. Плагин узнаёт
        # о закрытии сразу, чтобы меню открыло новое окно, а не это.
        self.closed.emit()