# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки Sentinel-2 по участку: поиск, облачность над участком,
сочетания каналов и индексы. Расчёт без Qt.

Просьба автора от 9 октября 2026 года - профессиональная подборка
каналов по точке или объекту. Каталог - STAC API Earth Search
(Element 84), коллекция sentinel-2-l2a: поиск по геометрии, датам
и облачности сцены, ответ страницами со ссылкой next. Каналы - COG на
открытом хранилище AWS sentinel-cogs, без ключа. У каждого канала
в каталоге масштаб и сдвиг: отражение = значение × scale + offset,
у снимков с 2022 года сдвиг -0.1, у прежних 0.

Облачность над участком - по маске классов сцены SCL (20 м): доля
облаков, теней и перистых облаков среди пикселей участка с данными.
Сцена с облачностью 60 % бывает чистой над полем, и наоборот.

Участок - многоугольник в широтах и долготах. Точка становится
квадратом со стороной side метров. Рамка и маска считаются в системе
UTM сцены (proj:epsg) рядами Крюгера core/coords.py.

Landsat 4-9 - просьба автора от 10 октября 2026 года. Каталог - STAC
API Microsoft Planetary Computer, коллекция landsat-c2-l2 (Collection 2
Level-2, отражение и температура поверхности, 30 м, с 1982 года).
Файлы лежат в Azure и читаются по временному ключу SAS, его служба
Planetary Computer выдаёт без учётной записи, ключ живёт около часа
(sign). Облака - битовая маска qa_pixel: бит 0 - нет данных, 1 -
расширенная маска облака, 2 - перистые облака, 3 - облако, 4 - тень.
Каналы Landsat называются как у Sentinel-2, ближний ИК - nir08, его
же берут продукты с nir (band). Тепловой канал - lwir11 у Landsat
8-9 и lwir у 4-7, продукт lst - температура поверхности в °C.

Модуль Qt не знает.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from .coords import to_utm
except ImportError:  # headless-тесты
    from coords import to_utm

SEARCH = "https://earth-search.aws.element84.com/v1/search"
COLLECTION = "sentinel-2-l2a"
LANDSAT_SEARCH = "https://planetarycomputer.microsoft.com/api/stac/v1/search"
LANDSAT_COLLECTION = "landsat-c2-l2"
LANDSAT_SAS_URL = ("https://planetarycomputer.microsoft.com/api/sas/v1/token/"
                 + LANDSAT_COLLECTION)
SEARCHES = {"sentinel2": SEARCH, "landsat": LANDSAT_SEARCH}
COLLECTIONS = {"sentinel2": COLLECTION, "landsat": LANDSAT_COLLECTION}
# Маска облаков сцены: ключ ресурса и шаг чтения, м.
CLOUD_ASSET = {"sentinel2": ("scl", 20.0), "landsat": ("qa_pixel", 30.0)}
# Биты qa_pixel Landsat Collection 2.
QA_FILL = 1 << 0
QA_CLOUDY = (1 << 1) | (1 << 2) | (1 << 3) | (1 << 4)
LANDSAT_STEPS = (30.0, 60.0, 120.0)
LANDSAT_ATTRIBUTION = "Landsat {number} image courtesy of the U.S. " \
    "Geological Survey"
# Температура поверхности, °C: пределы шкалы и цвета.
TEMPERATURE = ((-20.0, 45.0),
               ((-20.0, (49, 54, 149)), (0.0, (116, 173, 209)),
                (10.0, (224, 243, 248)), (20.0, (254, 224, 144)),
                (30.0, (244, 109, 67)), (45.0, (165, 0, 38))))
KELVIN = 273.15
PAGE = 100  # сцен на страницу ответа каталога
MAX_SCENES = 400  # сцен в поиске, дальше страницы не просятся
# Классы SCL: 0 нет данных, 1 насыщенные и дефектные, 3 тени облаков,
# 8 и 9 облака средней и высокой вероятности, 10 перистые облака.
SCL_EMPTY = (0, 1)
SCL_CLOUDY = (3, 8, 9, 10)
# Пикселей участка в выдаче не больше MAX_PIXELS по стороне, иначе шаг
# растёт: 10, 20, 60 м.
MAX_PIXELS = 4000
# Сумма отражений, ниже которой нормированная разность не считается.
MIN_SUM = 1e-3
STEPS = (10.0, 20.0, 60.0)
ATTRIBUTION = "Contains modified Copernicus Sentinel data {year}"

Asset = namedtuple("Asset", "href scale offset nodata res")
Scene = namedtuple("Scene", "id when cloud tile epsg sun thumbnail assets "
                            "mission", defaults=("sentinel2",))
Scene.__doc__ = """Сцена: номер, время UTC «ГГГГ-ММ-ДД ЧЧ:ММ», облачность
сцены в процентах, тайл MGRS или спутник с витком и рядом WRS у Landsat,
EPSG системы UTM, высота солнца в градусах, адрес превью, каналы
{ключ: Asset}, спутник - sentinel2 или landsat."""

# Сочетания каналов (красный, зелёный, синий канал картинки) и
# отражение, растягиваемое на полную яркость, если по снимку не
# посчитано. Состав - принятые в дистанционном зондировании сочетания
# Sentinel-2.
COMPOSITES = {
    "natural": ("red", "green", "blue"),         # B4 B3 B2
    "infrared": ("nir", "red", "green"),         # B8 B4 B3
    "agriculture": ("swir16", "nir", "blue"),    # B11 B8 B2
    "swir": ("swir22", "nir08", "red"),          # B12 B8A B4
    "geology": ("swir22", "swir16", "blue"),     # B12 B11 B2
    "urban": ("swir22", "swir16", "red"),        # B12 B11 B4
}
# Нормированные разности (a - b) / (a + b), пределы шкалы и цвета.
INDICES = {
    "ndvi": (("nir", "red"), (-0.2, 0.9),
             ((-0.2, (165, 0, 38)), (0.0, (244, 109, 67)),
              (0.2, (254, 224, 139)), (0.4, (217, 239, 139)),
              (0.6, (102, 189, 99)), (0.9, (0, 104, 55)))),
    "ndwi": (("green", "nir"), (-0.6, 0.6),
             ((-0.6, (245, 240, 220)), (0.0, (198, 219, 239)),
              (0.3, (66, 146, 198)), (0.6, (8, 48, 107)))),
    "ndmi": (("nir08", "swir16"), (-0.5, 0.6),
             ((-0.5, (140, 81, 10)), (0.0, (246, 232, 195)),
              (0.3, (90, 180, 172)), (0.6, (1, 102, 94)))),
    "nbr": (("nir", "swir22"), (-0.5, 0.8),
            ((-0.5, (103, 0, 13)), (0.0, (252, 187, 161)),
             (0.3, (199, 233, 192)), (0.8, (0, 109, 44)))),
    "ndsi": (("green", "swir16"), (-0.5, 1.0),
             ((-0.5, (120, 90, 60)), (0.0, (200, 200, 200)),
              (0.4, (166, 206, 227)), (1.0, (255, 255, 255)))),
}
PRODUCTS = tuple(COMPOSITES) + tuple(INDICES)
LANDSAT_PRODUCTS = PRODUCTS + ("lst",)


def products_of(mission):
    """Продукты спутника: у Landsat ещё температура поверхности."""
    return LANDSAT_PRODUCTS if mission == "landsat" else PRODUCTS


def band(key, mission):
    """Ключ ресурса канала у спутника: ближний ИК Landsat - nir08."""
    if mission == "landsat" and key == "nir":
        return "nir08"
    return key


# Каталог.

def search_body(geometry, start, end, max_cloud, limit=PAGE,
                mission="sentinel2"):
    """Тело запроса поиска: geometry - GeoJSON, start и end - дни
    «ГГГГ-ММ-ДД», max_cloud - облачность сцены по оценке поставщика."""
    return {"collections": [COLLECTIONS[mission]],
            "intersects": geometry,
            "datetime": "{}T00:00:00Z/{}T23:59:59Z".format(start, end),
            "limit": int(limit),
            "query": {"eo:cloud_cover": {"lte": float(max_cloud)}},
            "sortby": [{"field": "properties.datetime",
                        "direction": "desc"}]}


def parse_page(data):
    """Сцены страницы ответа и тело запроса следующей или None."""
    scenes = []
    for feature in (data or {}).get("features") or []:
        s = parse_item(feature)
        if s is not None:
            scenes.append(s)
    following = None
    for link in (data or {}).get("links") or []:
        if link.get("rel") == "next" and isinstance(link.get("body"), dict):
            following = link["body"]
    return scenes, following


def parse_item(feature):
    """Сцена из элемента STAC или None, если нет каналов."""
    props = feature.get("properties") or {}
    if str(props.get("platform") or "").startswith("landsat"):
        return _landsat_item(feature, props)
    # Смещение -1000 уже вычтено из значений, а поле offset у каналов
    # осталось. Проверено 9 октября 2026 года - красный над лесом 224.
    applied = bool(props.get("earthsearch:boa_offset_applied"))
    assets = {}
    for key, value in (feature.get("assets") or {}).items():
        href = value.get("href") or ""
        if not href.startswith("http"):
            continue
        bands = value.get("raster:bands") or [{}]
        band = bands[0] if bands else {}
        offset = 0.0 if applied else float(band.get("offset", 0.0))
        assets[key] = Asset(href, float(band.get("scale", 1.0)), offset,
                            band.get("nodata"),
                            band.get("spatial_resolution"))
    if "red" not in assets or "scl" not in assets:
        return None
    epsg = props.get("proj:epsg")
    if epsg is None:
        tile = str(props.get("s2:mgrs_tile") or props.get("mgrs:utm_zone")
                   or "")
        epsg = _epsg_from_tile(tile, props)
    when = str(props.get("datetime") or "").replace("T", " ")[:16]
    cloud = props.get("eo:cloud_cover")
    thumbnail = (assets.get("thumbnail") or Asset("", 1, 0, None, None)).href
    return Scene(str(feature.get("id") or ""), when,
                 float(cloud) if cloud is not None else 100.0,
                 _tile(feature, props), int(epsg) if epsg else None,
                 props.get("view:sun_elevation"), thumbnail, assets)


def _landsat_item(feature, props):
    """Сцена Landsat Planetary Computer: каналы с масштабом и сдвигом
    из каталога, превью - картинка службы данных."""
    assets = {}
    preview = ""
    for key, value in (feature.get("assets") or {}).items():
        href = value.get("href") or ""
        if not href.startswith("https://"):
            continue
        if key == "rendered_preview":
            preview = href
            continue
        bands = value.get("raster:bands") or [{}]
        info = bands[0] if bands else {}
        assets[key] = Asset(href, float(info.get("scale") or 1.0),
                            float(info.get("offset") or 0.0),
                            info.get("nodata"),
                            info.get("spatial_resolution"))
    if "red" not in assets or "qa_pixel" not in assets:
        return None
    if "lwir11" in assets and "lwir" not in assets:
        assets["lwir"] = assets["lwir11"]
    number = str(props.get("platform") or "").split("-")[-1]
    tile = "L{} {}/{}".format(number, props.get("landsat:wrs_path", ""),
                              props.get("landsat:wrs_row", ""))
    epsg = props.get("proj:epsg")
    cloud = props.get("eo:cloud_cover")
    return Scene(str(feature.get("id") or ""),
                 str(props.get("datetime") or "").replace("T", " ")[:16],
                 float(cloud) if cloud is not None else 100.0, tile,
                 int(epsg) if epsg else None,
                 props.get("view:sun_elevation"), preview, assets,
                 "landsat")


def sign(href, sas):
    """Адрес файла Planetary Computer с ключом SAS."""
    if not sas:
        return href
    return href + ("&" if "?" in href else "?") + sas


def _tile(feature, props):
    zone = props.get("mgrs:utm_zone")
    band = props.get("mgrs:latitude_band")
    square = props.get("mgrs:grid_square")
    if zone and band and square:
        return "{:02d}{}{}".format(int(zone), band, square)
    parts = str(feature.get("id") or "").split("_")
    return parts[1] if len(parts) > 1 else ""


def _epsg_from_tile(tile, props):
    zone = props.get("mgrs:utm_zone")
    band = props.get("mgrs:latitude_band")
    if not zone or not band:
        return None
    return (32600 if str(band).upper() >= "N" else 32700) + int(zone)


# Участок.

# Сторона участка точки, км - ширина видимой полосы глобуса в этих
# пределах.
SIDE_MIN = 1.0
SIDE_MAX = 100.0


def side_for_view(width):
    """Сторона участка точки в км по ширине видимой полосы width метров,
    с шагом 0.1 км."""
    side = min(max(width / 1000.0, SIDE_MIN), SIDE_MAX)
    return round(side, 1)


def square(lat, lon, side):
    """Квадрат со стороной side метров вокруг точки: кольцо (широта,
    долгота) без повтора первой точки."""
    half_lat = math.degrees(side / 2.0 / 6371008.8)
    half_lon = half_lat / max(math.cos(math.radians(lat)), 1e-6)
    return [(lat - half_lat, lon - half_lon), (lat - half_lat, lon + half_lon),
            (lat + half_lat, lon + half_lon), (lat + half_lat, lon - half_lon)]


def geojson(ring):
    """Многоугольник GeoJSON из кольца (широта, долгота)."""
    points = [[float(lon), float(lat)] for lat, lon in ring]
    if points and points[0] != points[-1]:
        points.append(points[0])
    return {"type": "Polygon", "coordinates": [points]}


def ring_utm(ring, epsg):
    """Кольцо участка в метрах UTM системы epsg (326zz или 327zz)."""
    zone = int(epsg) % 100
    south = int(epsg) // 100 == 327
    out = []
    for lat, lon in ring:
        utm = to_utm(lat, lon, zone)
        if utm is None:
            raise ValueError("outside UTM")
        east, north = utm[2], utm[3]
        # to_utm ставит ложный север по полушарию точки, участок у
        # экватора может пересечь его: система сцены одна.
        if south and lat >= 0.0:
            north += 10000000.0
        elif not south and lat < 0.0:
            north -= 10000000.0
        out.append((east, north))
    return out


def bounds(xy, res):
    """Рамка (xmin, ymin, xmax, ymax), выровненная на шаг res."""
    xs = [p[0] for p in xy]
    ys = [p[1] for p in xy]
    return (math.floor(min(xs) / res) * res, math.floor(min(ys) / res) * res,
            math.ceil(max(xs) / res) * res, math.ceil(max(ys) / res) * res)


def step_for(xy, mission="sentinel2"):
    """Шаг выдачи: 10 м у Sentinel-2 и 30 м у Landsat, если сторона
    участка не больше MAX_PIXELS пикселей, иначе крупнее."""
    steps = LANDSAT_STEPS if mission == "landsat" else STEPS
    box = bounds(xy, 1.0)
    side = max(box[2] - box[0], box[3] - box[1])
    for res in steps:
        if side / res <= MAX_PIXELS:
            return res
    return steps[-1]


def mask(xy, box, res):
    """Пиксели рамки box с шагом res внутри кольца xy: массив bool,
    первая строка - север."""
    cols = int(round((box[2] - box[0]) / res))
    rows = int(round((box[3] - box[1]) / res))
    px = box[0] + (np.arange(cols) + 0.5) * res
    py = box[3] - (np.arange(rows) + 0.5) * res
    x, y = np.meshgrid(px, py)
    inside = np.zeros((rows, cols), dtype=bool)
    n = len(xy)
    for i in range(n):
        x1, y1 = xy[i]
        x2, y2 = xy[(i + 1) % n]
        if y1 == y2:
            continue
        cross = (y1 > y) != (y2 > y)
        at = x1 + (y - y1) * (x2 - x1) / (y2 - y1)
        inside ^= cross & (x < at)
    return inside


# Облачность над участком.

def cloud_share(scl, inside):
    """Облачность над участком по маске SCL: (доля облаков и теней
    среди пикселей с данными, доля пикселей с данными), в процентах."""
    scl = np.asarray(scl)
    area = inside.sum()
    if area == 0:
        return 100.0, 0.0
    valid = inside & ~np.isin(scl, SCL_EMPTY)
    count = valid.sum()
    if count == 0:
        return 100.0, 0.0
    cloudy = valid & np.isin(scl, SCL_CLOUDY)
    # Числа Python: сравнение с numpy.float64 даёт numpy.bool, его
    # не берут методы Qt вроде setHidden.
    return (float(100.0 * cloudy.sum() / count),
            float(100.0 * count / area))


def qa_cloudy(qa):
    """Пиксели облаков и теней по qa_pixel Landsat: (облака, нет
    данных) - массивы bool."""
    qa = np.asarray(qa).astype(np.int64)
    empty = (qa & QA_FILL) != 0
    return ((qa & QA_CLOUDY) != 0) & ~empty, empty


def cloud_share_qa(qa, inside):
    """Облачность над участком по qa_pixel Landsat, как cloud_share."""
    cloudy, empty = qa_cloudy(qa)
    area = inside.sum()
    valid = inside & ~empty
    count = valid.sum()
    if area == 0 or count == 0:
        return 100.0, 0.0
    return (float(100.0 * (cloudy & valid).sum() / count),
            float(100.0 * count / area))


def clouds_of(scene, raw, inside):
    """Облачность над участком по маске сцены любого спутника."""
    if scene.mission == "landsat":
        return cloud_share_qa(raw, inside)
    return cloud_share(raw, inside)


def clear_mask(scene, raw):
    """Пиксели без облаков, теней и пропусков по маске сцены."""
    if scene.mission == "landsat":
        cloudy, empty = qa_cloudy(raw)
        return ~(cloudy | empty)
    return ~np.isin(raw, SCL_CLOUDY + SCL_EMPTY)


# Каналы и выдача.

def needed(products, mission="sentinel2"):
    """Каналы сцены для продуктов: ключи ресурсов STAC."""
    keys = []
    for product in products:
        if product == "lst":
            bands = ("lwir",)
        elif product in COMPOSITES:
            bands = COMPOSITES[product]
        else:
            bands = INDICES[product][0]
        for name in bands:
            key = band(name, mission)
            if key not in keys:
                keys.append(key)
    return keys


def reflectance(dn, asset):
    """Отражение из значений канала, нет данных - NaN, float32."""
    dn = np.asarray(dn)
    out = dn.astype(np.float32) * np.float32(asset.scale) \
        + np.float32(asset.offset)
    nodata = 0 if asset.nodata is None else asset.nodata
    out[dn == nodata] = np.nan
    return out


def normalized_difference(a, b):
    """(a - b) / (a + b) в пределах -1..1. Где сумма не больше
    MIN_SUM, индекс не определён - NaN."""
    total = a + b
    with np.errstate(divide="ignore", invalid="ignore"):
        out = (a - b) / total
    out[~(total > MIN_SUM)] = np.nan
    np.clip(out, -1.0, 1.0, out=out)
    return out.astype(np.float32)


def product(name, bands, mission="sentinel2"):
    """Массив продукта: сочетание - (3, строки, столбцы), индекс и
    температура - (строки, столбцы). bands - отражения {ключ: массив},
    у теплового канала - кельвины."""
    if name == "lst":
        return (bands["lwir"] - np.float32(KELVIN)).astype(np.float32)
    if name in COMPOSITES:
        return np.stack([bands[band(k, mission)]
                         for k in COMPOSITES[name]])
    a, b = INDICES[name][0]
    return normalized_difference(bands[band(a, mission)],
                                 bands[band(b, mission)])


def stretch(values, low=2.0, high=98.0):
    """Пределы растяжения канала по процентилям значений без NaN."""
    finite = values[np.isfinite(values)]
    if finite.size == 0:
        return 0.0, 0.3
    lo, hi = np.percentile(finite, [low, high])
    if hi <= lo:
        hi = lo + 1e-3
    return float(lo), float(hi)


def file_name(s, name):
    """Имя файла продукта: «S2_20260929_40VDK_ndvi»,
    «L9_20250923_166-020_ndvi»."""
    day = s.when[:10].replace("-", "")
    if s.mission == "landsat":
        sat, _, place = s.tile.partition(" ")
        return "{}_{}_{}_{}".format(sat, day, place.replace("/", "-"),
                                    name)
    return "S2_{}_{}_{}".format(day, s.tile, name)


def credit(s):
    """Подпись снимка: изменённые данные Copernicus с годом или
    снимок Landsat от USGS."""
    if s.mission == "landsat":
        return LANDSAT_ATTRIBUTION.format(number=s.tile.split(" ")[0][1:])
    return ATTRIBUTION.format(year=s.when[:4])
