# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты готовыми картинками тайлов - литология, поверхностные воды,
почвы. Без Qt.

Решение автора от 17 октября 2026 года - «делай первые три и почвы»
по списку открытых данных помощника. Карты приходят уже раскрашенными,
модуль только делает прозрачным цвет «нет данных» (clear), умножает
альфу на непрозрачность (rgba) и узнаёт значение под щелчком - по цвету
пикселя тайла (value_of) или запросом GetFeatureInfo службы (query).

- Литология GLiM (Hartmann, Moosdorf 2012) - тайлы planetx-terrain,
  их собирает tools/build_glim.py, классы - core/glim.py.
- Поверхностные воды JRC Global Surface Water 1984-2021 (Pekel и
  соавторы 2016) - тайлы самой службы JRC до уровня 13. Повторяемость
  воды - синий канал (доля лет с водой), переходы - классы по цвету,
  цвета сверены по тайлам Арала и Волги 17 октября 2026 года.
- Почвы SoilGrids 2.0 (ISRIC), слой 0-5 см, среднее предсказание, WMS
  maps.isric.org в EPSG:3857, цвета - шкалы службы по её легендам.
  «Нет данных» и вода - белый цвет. Значение в точке - GetFeatureInfo
  text/html, служба пишет целое в единицах хранения (г/кг × 10 и pH × 10).
  REST API SoilGrids 17 октября 2026 года отвечал 503.

На глобусе карта делит слой вида «emag» с картами значений геофизики
и геологической картой, на глобусе одна такая карта. Непрозрачность
и уровни - выбор помощника, утверждает автор.
"""
import re
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import glim
    from .fields import TERRAIN
except ImportError:  # headless-тесты
    import glim
    from fields import TERRAIN

TileMap = namedtuple("TileMap", "key url max_level wms attribution opacity "
                                "stops ticks classes unit digits query "
                                "scale clear coarse split",
                     defaults=("", 0))
TileMap.__doc__ = """Карта картинками: key - ключ строки «Слоёв», url -
шаблон тайла ({z}/{x}/{y} или {bbox} WMS в EPSG:3857), max_level -
глубший уровень, wms - (адрес службы, слой) WMS или "", attribution -
(подпись, адрес), opacity - непрозрачность, stops и ticks - шкала
значений или None, classes - (код, (r, g, b)) классов или None, unit -
единица, digits - знаков после запятой, query - шаблон GetFeatureInfo
с {west} {south} {east} {north} или
None, scale - множитель ответа query, clear - цвет «нет данных»,
coarse - шаблон тайлов мельче уровня split или "" - один шаблон."""

GSW = "https://storage.googleapis.com/global-surface-water/tiles2021/"
GSW_ATTRIBUTION = ("Surface water: EC JRC/Google, Pekel et al. 2016",
                   "https://global-surface-water.appspot.com/")
SOIL_SERVICE = "https://maps.isric.org/mapserv?map=/map/{prop}.map"
SOIL_LAYER = "{prop}_0-5cm_mean"
SOIL_WMS = "&SERVICE=WMS&VERSION=1.1.1&STYLES=&LAYERS={layer}"
SOIL_TILE = ("&REQUEST=GetMap&SRS=EPSG:3857&BBOX={bbox}&WIDTH=256"
             "&HEIGHT=256&FORMAT=image/png")
# Точка - середина сетки 3 × 3 пикселя по 0.004° вокруг неё.
SOIL_QUERY = ("&REQUEST=GetFeatureInfo&QUERY_LAYERS={prop}_0-5cm_mean"
              "&SRS=EPSG:4326&BBOX={{west:.5f}},{{south:.5f}},{{east:.5f}},"
              "{{north:.5f}}&WIDTH=3&HEIGHT=3&X=1&Y=1&INFO_FORMAT=text/html")
SOIL_ATTRIBUTION = ("Soil: SoilGrids 2.0, ISRIC, CC BY 4.0",
                    "https://soilgrids.org/")
WORLDCOVER_URL = (
    "https://planetarycomputer.microsoft.com/api/data/v1/mosaic/"
    "287434fc0e0024667464141a8cb3f231/tiles/WebMercatorQuad/{z}/{x}/{y}@1x"
    "?collection=esa-worldcover&assets=map&colormap_name=esa-worldcover"
    "&format=png")
WORLDCOVER_FOLDER = "worldcover"
WORLDCOVER_SPLIT = 6  # с этого уровня тайлы службы, мельче - planetx-terrain
WORLDCOVER_ATTRIBUTION = (
    "Land cover: ESA WorldCover 2021, CC BY 4.0, Microsoft Planetary "
    "Computer", "https://esa-worldcover.org/")
# Классы ESA WorldCover и цвета её карты, сверены по тайлам службы
# 17 октября 2026 года.
LAND_COVER = (
    ("tree", (0, 100, 0)),
    ("shrub", (255, 187, 34)),
    ("grass", (255, 255, 76)),
    ("crop", (240, 150, 255)),
    ("built", (250, 0, 0)),
    ("bare", (180, 180, 180)),
    ("snow", (240, 240, 240)),
    ("water", (0, 100, 200)),
    ("wetland", (0, 150, 160)),
    ("mangrove", (0, 207, 117)),
    ("moss", (250, 230, 160)))
SOIL_LEVEL = 11  # пиксель около 75 м у экватора, сетка SoilGrids 250 м
WHITE = (255, 255, 255)
# Пиксель запроса мельче сетки 250 м служба оставляет пустым, окно
# 0.002° 17 октября 2026 года отвечало пустой страницей, 0.01° - числом.
QUERY_HALF = 0.006

# Переходы воды 1984-2021 - классы карты JRC в порядке её легенды.
TRANSITIONS = (
    ("permanent", (0, 0, 221)),
    ("new_permanent", (34, 177, 76)),
    ("lost_permanent", (209, 45, 62)),
    ("seasonal", (153, 217, 234)),
    ("new_seasonal", (181, 230, 29)),
    ("lost_seasonal", (230, 161, 170)),
    ("seasonal_to_permanent", (255, 127, 39)),
    ("permanent_to_seasonal", (255, 201, 14)),
    ("ephemeral_permanent", (127, 127, 127)),
    ("ephemeral_seasonal", (195, 195, 195)))

# Шкалы почв - цвета легенд SoilGrids в единицах карты.
TEXTURE = ((0.0, (242, 218, 193)), (21.1, (212, 159, 107)),
           (41.5, (180, 123, 65)), (62.0, (147, 94, 41)),
           (79.9, (118, 70, 21)))
SOC = ((0.0, (251, 249, 249)), (10.6, (223, 212, 209)),
       (29.9, (187, 163, 156)), (63.3, (155, 120, 110)),
       (111.4, (137, 95, 83)), (217.4, (118, 70, 57)))
PH = ((4.5, (241, 238, 45)), (5.4, (224, 228, 27)), (5.6, (165, 219, 54)),
      (6.0, (114, 201, 76)), (6.5, (66, 181, 50)), (7.0, (53, 165, 54)),
      (7.6, (44, 152, 64)), (8.0, (54, 185, 147)), (8.3, (27, 193, 199)),
      (9.2, (15, 204, 217)))


def _soil(key, prop, stops, ticks, unit, digits):
    service = SOIL_SERVICE.format(prop=prop)
    layer = SOIL_LAYER.format(prop=prop)
    base = service + SOIL_WMS.format(layer=layer)
    return TileMap(key, base + SOIL_TILE, SOIL_LEVEL, (service, layer),
                   SOIL_ATTRIBUTION, 0.8, stops, ticks, None, unit, digits,
                   base + SOIL_QUERY.format(prop=prop), 0.1, WHITE)


MAPS = {
    "glim": TileMap(
        "glim", TERRAIN + glim.FOLDER + "/{z}/{x}/{y}.png", glim.MAX_LEVEL,
        "", glim.ATTRIBUTION, glim.OPACITY, None, (),
        tuple((code, color) for code, _, color in glim.CLASSES
              if color is not None), "", 0, None, 1.0, None),
    "water_occurrence": TileMap(
        "water_occurrence", GSW + "occurrence/{z}/{x}/{y}.png", 13, "",
        GSW_ATTRIBUTION, 0.9, ((0.0, (255, 0, 0)), (100.0, (0, 0, 255))),
        (0, 25, 50, 75, 100), None, "%", 0, None, 1.0, None),
    "water_transitions": TileMap(
        "water_transitions", GSW + "transitions/{z}/{x}/{y}.png", 13, "",
        GSW_ATTRIBUTION, 0.9, None, (), TRANSITIONS, "", 0, None, 1.0,
        None),
    "soil_clay": _soil("soil_clay", "clay", TEXTURE, (0, 20, 40, 60, 80),
                       "%", 1),
    "soil_sand": _soil("soil_sand", "sand", TEXTURE, (0, 20, 40, 60, 80),
                       "%", 1),
    "soil_soc": _soil("soil_soc", "soc", SOC, (0, 50, 100, 150, 200),
                      "g/kg", 1),
    "soil_ph": _soil("soil_ph", "phh2o", PH, (5, 6, 7, 8, 9), "pH", 1),
    # Покрытие земель 10 м, служба отдаёт уровни от WORLDCOVER_SPLIT,
    # мельче - тайлы tools/build_worldcover.py в planetx-terrain.
    "worldcover": TileMap(
        "worldcover", WORLDCOVER_URL, 14, "", WORLDCOVER_ATTRIBUTION, 0.75,
        None, (), LAND_COVER, "", 0, None, 1.0, None,
        TERRAIN + WORLDCOVER_FOLDER + "/{z}/{x}/{y}.png", WORLDCOVER_SPLIT),
}
# Порядок строк каталога.
KEYS = ("glim", "worldcover", "water_occurrence", "water_transitions",
        "soil_clay", "soil_sand", "soil_soc", "soil_ph")
CLASS_TOLERANCE = 40


def rgba(tmap, tile, opacity=None):
    """Тайл карты (h, w, 4) uint8 в слой вида: цвет «нет данных»
    прозрачен, альфа умножена на непрозрачность, цвет предумножен.
    Тайл без единого пикселя карты - None, рисуется предок."""
    tile = np.asarray(tile)
    opacity = tmap.opacity if opacity is None else opacity
    alpha = tile[..., 3].astype(np.float32) / 255.0 * opacity
    if tmap.clear is not None:
        same = np.all(np.abs(tile[..., :3].astype(np.int16)
                             - np.array(tmap.clear, np.int16)) <= 2,
                      axis=-1)
        alpha[same] = 0.0
    if not np.any(alpha > 0.0):
        return None
    out = np.empty(tile.shape[:2] + (4,), dtype=np.uint8)
    for band in range(3):
        out[..., band] = np.round(tile[..., band].astype(np.float32)
                                  * alpha)
    out[..., 3] = np.round(alpha * 255.0)
    return out


def class_of(classes, rgb, tolerance=CLASS_TOLERANCE):
    """Код класса, цвет которого ближе всего к rgb, или None."""
    best, score = None, tolerance
    for code, color in classes:
        d = sum(abs(int(a) - int(b)) for a, b in zip(rgb[:3], color))
        if d < score:
            best, score = code, d
    return best


def value_of(tmap, pixel):
    """Значение под щелчком по пикселю (r, g, b, a) тайла: код класса,
    повторяемость воды в процентах или None - пусто или карта без
    значения в цвете."""
    if len(pixel) > 3 and pixel[3] == 0:
        return None
    if tmap.classes:
        return class_of(tmap.classes, pixel)
    if tmap.key == "water_occurrence":
        return round(float(pixel[2]) / 255.0 * 100.0)
    return None


def tile_url(tmap, url, z, x, y):
    """Адрес тайла карты: мельче уровня split - шаблон coarse, иначе url
    (url может быть своей копией, шаги проверки ставят локальную)."""
    template = tmap.coarse if tmap.coarse and z < tmap.split else url
    return template.replace("{z}", str(z)).replace("{x}", str(x)).replace(
        "{y}", str(y))


def query_url(tmap, lat, lon):
    """Адрес GetFeatureInfo значения в точке или None."""
    if not tmap.query:
        return None
    return tmap.query.format(west=lon - QUERY_HALF, south=lat - QUERY_HALF,
                             east=lon + QUERY_HALF, north=lat + QUERY_HALF)


_VALUE = re.compile(r'id="value">\s*(-?\d+(?:\.\d+)?)\s*<')


def parse_query(tmap, data):
    """Значение из ответа GetFeatureInfo в единицах карты или None -
    в точке нет данных."""
    if isinstance(data, (bytes, bytearray)):
        data = bytes(data).decode("utf-8", "replace")
    found = _VALUE.search(data)
    if found is None:
        return None
    value = float(found.group(1)) * tmap.scale
    return value if value >= 0.0 else None
