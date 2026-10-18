# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Постоянные и функции окна глобуса (ui/window.py) и его частей
ui/globe."""
import html
import os
import time

import numpy as np
from qgis.core import QgsSettings

from ...core import (basemap, cadastre, clouds, fields, geology, sun,
                     temperature, cutaway, slabs, themes, tilemaps,
                     tileoverlays)
from ...core.ellipsoid import geodetic_to_ecef
from ...core.measure import nearest_vertex
from ...core.mipmap import mip_chain
from ...core.contours import contour_rgba, upsample as contour_upsample
from ...core.slope import aspect_rgba, slope_aspect, slope_rgba
from ...core.terrain import ancestor, decode
from ...core.tiling import tile_mesh
from ...core.mirrors import Mirrors
from ...core.buildings import EMPTY as NO_BUILDINGS, footprints
from ...core.places import AS_QGIS, DecodeError, decode_places, name_languages
from ...i18n import is_russian, tr, ui_language
from ...net.overlay import BORDERS, PLACES
from ..measure import GRAB_PIXELS
from ..inset import apply as apply_insets
from ..nasamaps import LAYERS as GALLERY_LAYERS


# Папка модуля planetx: части окна лежат в ui/globe.
PLUGIN_DIR = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))

VIEWSHED_POLL = 250  # мс между проверками высот видимости
VIEWSHED_WAIT = 30.0  # с, дальше расчёт идёт по тем высотам, что есть
HEIGHT_CHUNK = 20000  # узлов сетки инсоляции за проход цикла событий
CALC_BUDGET = 0.004  # с расчёта инсоляции за проход цикла событий
# Region KML пересчитывается, когда глаз ушёл на эту долю расстояния
# до точки взгляда.
REGION_MOVE = 0.02
# Зеркала хранилища planetx-terrain, одно состояние на QGIS.
TERRAIN_MIRRORS = Mirrors(slabs.TERRAIN_REPOS)
# Раздел «На глобусе»: непрозрачность и выгрузка слоёв. Точки - атрибут
# вида, тайловые слои - слои вида GIBS, слои QGIS - в наложении.
POINT_LAYERS = {"deposits": "deposits", "osm_mines": "osm_mines",
                "plants": "plants", "quakes": "quakes", "fires": "fires",
                "volcanoes": "volcanoes", "iscgem": "history"}
# Струйки: ключ строки - поле вида.
FLOW_LAYERS = {"currents": "currents"}
GIBS_FADES = {"clouds": ("clouds",), "slope": ("slope",),
              "aspect": ("slope",), "contours": ("contours",),
              "temperature": ("sea", "land"), "map": ("theme", "compare"),
              "currents": ("currents",), "cadastre": ("cadastre",),
              "emag": ("emag",), "seafloor_age": ("emag",),
              "heatflow": ("emag",), "gravity": ("emag",),
              "bouguer": ("emag",), "geology": ("emag",),
              "glim": ("emag",), "worldcover": ("emag",),
              "water_occurrence": ("emag",),
              "water_transitions": ("emag",), "soil_clay": ("emag",),
              "soil_sand": ("emag",), "soil_soc": ("emag",),
              "soil_ph": ("emag",)}
QGIS_LAYERS = ("plates", "faults", "mining", "infra_osm",
               "cables") + tileoverlays.KEYS
# Раскраски: в проект - сеткой значений или картинкой WMS GIBS.
PICTURE_LAYERS = ("map", "currents", "clouds", "temperature")
OPACITY_KEY = "PlanetX/opacity/"
# Строки слоёв остановки тура и вида метки проявляются и гаснут за
# столько секунд, шаг таймера - мс. Выбор помощника, утверждает автор.
LAYER_FADE = 0.5
LAYER_FADE_TICK = 30
OPACITY_PAUSE = 300  # мс, наложение пересобирается после ползунка
# Окно «Разрез» пересобирается после паузы движения шкалы времени, мс.
# Выбор помощника, утверждает автор.
SECTION_TIME_PAUSE = 400
# Архив Wayback: изменения в середине вида ищутся после паузы вида, мс.
# Выбор помощника, утверждает автор.
WAYBACK_PAUSE = 700
# Порядок строк «На глобусе»: слои витрины, слои «Карты», карты витрины.
ACTIVE_ORDER = tuple(key for key, _ in GALLERY_LAYERS) + (
    "grid", "buildings", "contours", "cadastre", "infra_osm", "cables",
    "fires", "temperature")
# Каталог «Добавить данные» в левой панели: панель не уже, пиксели.
# Горизонтали тел - на столько уровней глубже уровня высот тела, по
# пересчитанному предку. У Марса пиксель уровня 5 около 2.6 км, уровня
# 9 - около 160 м. Выбор помощника.
BODY_CONTOUR_DEEPER = 4
# Знакомство с модулем при первом открытии - после первых кадров, мс.
GUIDE_DELAY = 1500
DEPOSIT_POLL = 300  # мс между проверками разбора месторождений
# Шахты OSM: пауза после остановки вида перед запросом тайлов, мс,
# и пауза после отказа Overpass, с. Выбор помощника.
OSM_PAUSE = 800
# Уровень воды Бриенцского озера в демо, м: средний уровень 563.7 м
# по swisstopo, округлён.
BRIENZ_LEVEL = 564.0
# Исторические карты Москвы в демо: год, название, тайлы карты Wikimedia
# Commons (общественное достояние), привязанной в Wikimaps Warper.
# Состав - выбор помощника.
WARPER_TILES = ("https://warper.wmflabs.org/maps/tile/{}/"
                "{{z}}/{{x}}/{{y}}.png")


def moscow_maps():
    return ((1813, tr("План Москвы"), WARPER_TILES.format(2423)),
            (1860, tr("Москва, карта Шуберта"), WARPER_TILES.format(2129)),
            (1900, tr("Окрестности Москвы"), WARPER_TILES.format(2127)),
            (1917, tr("План Москвы"), WARPER_TILES.format(2407)),
            (1935, tr("Генеральный план Москвы"),
             WARPER_TILES.format(2692)))


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
# Готовые подложки меню «Основа» (basemap.READY), добавленные
# пользователем, и источники, чьё предупреждение он принял.
READY_KEY = "PlanetX/ready_sources"
ACCEPTED_KEY = "PlanetX/ready_accepted"
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
GEOID_SCALE_KEY = "PlanetX/geoid_scale"  # масштаб режима «Геоид»
# Растягивать ли кору разреза Земли издалека, по умолчанию да.
STRETCH_KEY = "PlanetX/cutaway_stretch"
# Раскрашивать ли мантию разреза томографией, по умолчанию нет.
TOMO_KEY = "PlanetX/cutaway_tomo"
# Поток по путям (core/pathflow.py): шаг таймера штрихов, мс, подъём
# штриха над рельефом, м, на сколько пикселей штрих толще линии, на
# сколько ширин вида от точки взгляда считаются штрихи. Выбор
# помощника, утверждает автор.
FLOW_TICK = 40
FLOW_LIFT = 20.0
FLOW_WIDER = 1.5
FLOW_REACH = 2.0
# Сетка, звёзды, облака: ключ настройки и умолчание. Звёзды включены,
# как в Google Earth, сетка и облака выключены. Решение помощника от
# 29 сентября 2026 года, его утверждает автор. 3D-здания выключены,
# решение автора от 29 сентября 2026 года.
# Солнце выключено, умолчание плана работ после 0.16.0.
EXTRA_DEFAULTS = {"grid": False, "stars": True, "clouds": False,
                  "temperature": False, "buildings": False, "sun": False,
                  "slope": False, "aspect": False, "contours": False,
                  "quakes": False, "cutaway": False, "paleo": False,
                  "plates": False, "fires": False, "satellites": False,
                  "trains": False, "vessels": False, "aircraft": False,
                  "deposits": False, "mining": False,
                  "osm_mines": False,
                  "plants": False, "infra_osm": False,
                  "cables": False, "currents": False, "cadastre": False,
                  "magpoles": False, "emag": False, "geoid": False,
                  "magdecl": False, "seafloor_age": False,
                  "heatflow": False, "gravity": False, "bouguer": False,
                  "platemotion": False,
                  "volcanoes": False, "faults": False,
                  "geology": False, "air": True, "iscgem": False,
                  "glim": False, "worldcover": False,
                  "water_occurrence": False,
                  "water_transitions": False, "soil_clay": False,
                  "soil_sand": False, "soil_soc": False, "soil_ph": False,
                  **{key: False for key in tileoverlays.KEYS}}
# Уклон и экспозиция - один слой вида, включена одна из двух строк.
SURFACE_EXTRAS = ("slope", "aspect")
# Строки раздела «Слои», которые есть только у Земли.
EARTH_EXTRAS = ("clouds", "temperature", "buildings", "sun", "quakes",
                "cutaway", "paleo", "plates", "fires", "satellites",
                "trains", "vessels", "aircraft", "deposits", "mining",
                "osm_mines", "plants",
                "infra_osm",
                "cables", "currents", "cadastre", "magpoles", "emag",
                "geoid", "magdecl", "seafloor_age", "heatflow",
                "gravity", "bouguer", "platemotion", "volcanoes",
                "faults", "geology", "iscgem", "glim", "worldcover",
                "water_occurrence",
                "water_transitions", "soil_clay", "soil_sand", "soil_soc",
                "soil_ph") + tileoverlays.KEYS
# Магнитные полюса: цвета следа и точки, подпись источников. Цвета -
# выбор помощника, утверждает автор.
POLE_COLORS = {"north": (235, 70, 60, 255), "south": (70, 130, 235, 255)}
POLE_WIDTH = 2.0
# Линии склонения: восточное - красные, западное - синие, агона -
# зелёная толще. Подпись - у линии не короче DECL_LABEL_POINTS точек.
# Выбор помощника, утверждает автор.
DECL_EAST = (215, 70, 60, 220)
DECL_WEST = (60, 110, 215, 220)
DECL_ZERO = (40, 170, 70, 255)
DECL_WIDTH = 1.4
DECL_ZERO_WIDTH = 2.6
DECL_LABEL_POINTS = 8
# Стрелки скоростей плит (core/platemotion.py): цвет и толщина, выбор
# помощника, утверждает автор.
MOTION_COLOR = (255, 225, 60, 235)
MOTION_WIDTH = 1.8
POLE_FIRST = "1590-01-01"  # первый год таблицы NOAA
MAGNETIC_ATTRIBUTION = ("IGRF-14 IAGA, NOAA NCEI",
                        "https://www.ncei.noaa.gov/products/"
                        "wandering-geomagnetic-poles")
# Глубины морей и океанов - часть данных рельефа, флажок в свойствах
# вида. Решение автора от 2 октября 2026 года, по умолчанию включены.
SEA_KEY = "PlanetX/sea_depths"
# Файлы модуля: указатель зон плит Slab2 (tools/build_slabs.py).
DATA_DIR = os.path.join(PLUGIN_DIR, "data")
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
# Картинка 3D-модели больше - уменьшается, пикселей по большей стороне.
MODEL_SIDE = 2048
# Перелёт к модели без своего вида: расстояние, метры, и наклон.
MODEL_DISTANCE = 300.0
MODEL_TILT = 60.0
GRID_COLOR = (220, 220, 220, 255)
GRID_WIDTH = 1.0
CIRCLE_COLOR = (255, 230, 0, 255)  # экватор, тропики, полярные круги
# Подсветка участка кадастра под щелчком, как выделение на карте НСПД.
# Цвета - выбор помощника, утверждает автор.
PARCEL_COLOR = (200, 0, 200, 255)
PARCEL_FILL = (230, 120, 230, 90)


def parcel_labels():
    """Подписи полей сведений об участке, ключи - core.cadastre.FIELDS."""
    return {
        "cad_num": tr("Кадастровый номер"),
        "readable_address": tr("Адрес"),
        "specified_area": tr("Площадь уточнённая"),
        "declared_area": tr("Площадь декларированная"),
        "land_record_category_type": tr("Категория земель"),
        "permitted_use_established_by_document":
            tr("Вид разрешённого использования"),
        "ownership_type": tr("Форма собственности"),
        "right_type": tr("Вид права"),
        "cost_value": tr("Кадастровая стоимость"),
        "cost_index": tr("Удельная кадастровая стоимость"),
        "cost_determination_date": tr("Дата определения стоимости"),
        "cost_application_date": tr("Дата применения стоимости"),
        "land_record_reg_date": tr("Дата постановки на учёт"),
        "status": tr("Статус"),
        "quarter_cad_number": tr("Кадастровый квартал")}
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
# мс без движения ползунка непрозрачности до записи в «Мои метки».
OPACITY_DELAY = 120
PANEL_WIDTH = 300  # ширина левой панели при открытии, пикселей
MARGIN = 8  # отступ панели значков и подписи от края вида
# Подпись источников - неяркий светлый текст с тенью без плашки, как
# у Google Earth, просьба автора от 17 октября 2026 года. Вся строка -
# одна ссылка на окно «Источники данных» без вида ссылки.
CREDIT_LINK = ('<a href="sources" style="color: #e4e4e4; '
               'text-decoration: none;">{}</a>')
ATTRIBUTION_STYLE = "QLabel { background: transparent; padding: 1px; }"
BRAND_STYLE = "QToolButton { background: transparent; border: none; }"


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


def contours_prepare(floor, radius, insets=(), encoding="terrarium",
                     glyphs=None, levels=None, palette="map", store=None,
                     sea=True):
    """Работа рабочего потока для тайла горизонталей: высоты Terrarium
    с врезками своего рельефа, линии и подписи core/contours.py
    цифрами glyphs и мипмапы. sea=False - тело без моря."""
    def prepare(key, rgba):
        heights = decode(rgba, floor, encoding)
        # Соседи тайла высот - из хранилища вида, только читаются.
        neighbor = None if store is None else \
            (lambda k: getattr(store.tiles.get(k), "heights", None))
        # Уровень тайла высот решён при запросе (ContourSource), у тел -
        # сам тайл.
        source_level = levels(key) if levels is not None else key[0]
        if key[0] > source_level:
            # Глубже уровня съёмки - сглаженный предок, пересчитанный
            # кубически (core.contours.SOURCE_LEVEL).
            heights = contour_upsample(heights, ancestor(key, source_level),
                                       key, neighbor, smoothed=True)
        if insets:
            heights = apply_insets(insets, key, heights)
        return mip_chain(contour_rgba(heights, key[0], key[2], radius,
                                      glyphs=glyphs, palette=palette,
                                      sea=sea))
    return prepare


def prepare_temperature(key, rgba):
    """Работа рабочего потока для тайла температуры: раскраска GIBS
    с непрозрачностью и уровни мипмапов."""
    return mip_chain(temperature.overlay_rgba(rgba))


def prepare_theme(theme_key):
    """Работа рабочего потока для тайла темы NASA GIBS: прозрачность,
    прозрачные классы темы и уровни мипмапов."""
    if theme_key == themes.WAYBACK:
        # Снимок Wayback - подложка, без прозрачности раскраски.
        return lambda key, rgba: mip_chain(rgba)
    clear = themes.CLEAR.get(theme_key, ())
    return lambda key, rgba: mip_chain(themes.overlay_rgba(rgba,
                                                           clear=clear))


def prepare_field(name, key, rgba):
    """Работа рабочего потока для тайла карты значений name
    (core/fields.py): значения в раскраску и уровни мипмапов."""
    return mip_chain(fields.rgba(fields.FIELDS[name], rgba))


def prepare_geology(key, rgba):
    """Работа рабочего потока для тайла геологической карты Macrostrat
    (core/geology.py): премноженная альфа и уровни мипмапов, пустой
    тайл - None, на его месте остаётся предок."""
    picture = geology.rgba(rgba)
    return None if picture is None else mip_chain(picture)


def prepare_tilemap(name, key, rgba):
    """Работа рабочего потока для тайла карты картинками name
    (core/tilemaps.py): прозрачный цвет «нет данных», премноженная
    альфа и уровни мипмапов, пустой тайл - None."""
    picture = tilemaps.rgba(tilemaps.MAPS[name], rgba)
    return None if picture is None else mip_chain(picture)


def prepare_lights(key, rgba):
    """Работа рабочего потока для тайла огней городов: премноженная
    альфа и уровни мипмапов."""
    return mip_chain(themes.overlay_rgba(rgba, 1.0))


def cadastre_source():
    """Кадастр Росреестра: WMS НСПД с заголовком Referer, по одному
    запросу с паузой, core/cadastre.py."""
    source = basemap.WmsSource(
        tr("Кадастр Росреестра"), cadastre.URL, cadastre.MAX_LEVEL,
        cadastre.ATTRIBUTION, headers={"Referer": cadastre.REFERER},
        builtin=True)
    source.parallel = 1
    source.gap = cadastre.GAP
    return source


def ready_sources():
    """Готовые подложки меню «Основа», которые пользователь добавил,
    в порядке basemap.READY."""
    chosen = settings_list(READY_KEY)
    return [basemap.ready_source(key, is_russian())
            for key in basemap.READY_KEYS if key in chosen]


def all_sources():
    """Подложки Земли: встроенные, добавленные готовые, подключения XYZ
    QGIS."""
    return basemap.builtins() + ready_sources() + xyz_sources()


def settings_list(key):
    """Список строк из настройки QGIS, пустой, если её нет."""
    value = QgsSettings().value(key, [])
    if isinstance(value, str):
        return [value] if value else []
    return [str(v) for v in (value or [])]


def gibs_source(name):
    """Источник и подготовка тайла слоя GIBS по имени слоя вида."""
    if name == "cadastre":
        return cadastre_source(), prepare_lights
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
        # Ручка - там, где нарисован кружок угла: на поверхности, как
        # подпись (GlobeView.label_height). С эллипсоида в режиме
        # «Геоид» точка захвата уходила от кружка на сотни километров,
        # замечание автора от 15 октября 2026 года.
        xyz = geodetic_to_ecef(np.array([p[1] for p in points]),
                               np.array([p[2] for p in points]),
                               np.array([view.label_height(p[1], p[2])
                                         for p in points]))
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
