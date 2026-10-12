# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки ASTER окна снимков: каналы, перевод значений, продукты.
Расчёт без Qt.

Просьба автора от 12 октября 2026 года - «может астер добавишь».
В Earth Engine ASTER только с учётной записью каждого пользователя,
без входа его даёт Microsoft Planetary Computer - коллекция aster-l1t
(ASTER L1T, 2000-2006 годы, ключ SAS - тот же). Сцена - три файла COG
в UTM: VNIR (каналы 1, 2, 3N, 15 м), SWIR (4-9, 30 м, коротковолновые
каналы отказали в 2008 году, у части сцен их нет), TIR (10-14, 90 м).
Значения - целые числа прибора без масштаба в каталоге.

Яркость L = (DN - 1) × UCC, коэффициенты UCC - таблица руководства
пользователя ASTER (Abrams и др.) для нормального усиления. Режим
усиления сцены в этой копии не записан - ни в XML, ни в файлах,
проверено 12 октября 2026 года. Большинство сцен снято в нормальном
усилении, при другом отражение канала выходит в постоянное число раз
больше или меньше, отношения каналов с растяжением по снимку этого
почти не замечают. Отражение на верху атмосферы - π L d² / (ESUN
sin h), ESUN - Thome (по Smith), d - расстояние до Солнца по дню года,
h - высота солнца сцены. Тепловые каналы - яркостная температура
K2 / ln(K1 / L + 1).

Минеральные индексы - принятые отношения каналов (Rowan, Mars 2003,
Ninomiya 2003): каолинит и алунит (4 + 6) / 5 - поглощение у
2.17 мкм, серицит и мусковит (5 + 7) / 6 - у 2.2 мкм, Mg-OH
и карбонаты (7 + 9) / 8, оксиды железа 2 / 1, кварц 11² / (10 × 12)
по яркости тепловых каналов. Шкала - растяжение по участку 2-98 %.
Проверено на Куприте (Невада) 12 октября 2026 года - (4 + 6) / 5
выделяет обе известные зоны изменённых пород, на холмах 2.18 против
2.05 на юго-западе, (5 + 7) / 6 их не выделяет - там алунит
и каолинит, не серицит. NDVI у ASTER не выдаётся - он зависит от
усиления каналов 2 и 3N, а его в этой копии нет: у сцены Куприта
отражение каналов 1, 2, 3N при нормальном усилении вышло 0.51, 0.48,
0.27, NDVI пустыни -0.28.

Облачной маски у L1T нет: облачность над участком - облачность
сцены, доля данных - по каналу 1.

Модуль Qt не знает.
"""
import math
from urllib.parse import urlencode

import numpy as np

COLLECTION = "aster-l1t"
MISSION = "aster"
# ASTER после 2006 года - просьба автора того же дня («добавь давай
# тоже»), вопрос Надежды «после 6 он не весь поломался». Каналы VNIR
# и TIR снимают и сейчас, SWIR отказали в 2008 году. Открытой копии
# нет: каталог NASA CMR (AST_L1T версии 004) отвечает без входа, файлы
# в хранилище LP DAAC lp-prod-protected - по ключу Earthdata каждого
# пользователя. Файл канала - отдельный COG «…_VNIR_B01.tif». Без
# ключа хранилище отвечает переадресацией 303 на страницу входа,
# проверено 12 октября 2026 года.
NASA_MISSION = "aster_nasa"
NASA_SEARCH = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
NASA_COLLECTION = "C3306888411-LPCLOUD"
NASA_FIRST = "2007-01-01"
NASA_PAGE = 200  # сцен в ответе каталога
LOGIN_HOST = "urs.earthdata.nasa.gov"
FIRST_DAY = "2000-03-04"
LAST_DAY = "2006-12-31"
STEPS = (15.0, 30.0, 90.0)
CREDIT = ("ASTER data courtesy of NASA/METI/AIST/Japan Spacesystems "
          "and U.S./Japan ASTER Science Team")

# Канал: файл сцены, номер канала в файле, длина волны, мкм, UCC
# нормального усиления, Вт/(м² ср мкм) на единицу значения.
BANDS = {
    "b1": ("VNIR", 1, 0.56, 1.688),
    "b2": ("VNIR", 2, 0.66, 1.415),
    "b3n": ("VNIR", 3, 0.82, 0.862),
    "b4": ("SWIR", 1, 1.65, 0.2174),
    "b5": ("SWIR", 2, 2.165, 0.0696),
    "b6": ("SWIR", 3, 2.205, 0.0625),
    "b7": ("SWIR", 4, 2.26, 0.0597),
    "b8": ("SWIR", 5, 2.33, 0.0417),
    "b9": ("SWIR", 6, 2.395, 0.0318),
    "b10": ("TIR", 1, 8.3, 0.006822),
    "b11": ("TIR", 2, 8.65, 0.006780),
    "b12": ("TIR", 3, 9.11, 0.006590),
    "b13": ("TIR", 4, 10.6, 0.005693),
    "b14": ("TIR", 5, 11.3, 0.005225),
}
ORDER = tuple(BANDS)
# Солнечная постоянная канала, Вт/(м² мкм).
ESUN = {"b1": 1845.99, "b2": 1555.74, "b3n": 1119.47, "b4": 231.25,
        "b5": 79.81, "b6": 74.99, "b7": 68.66, "b8": 59.74, "b9": 56.92}
# Постоянные K1, Вт/(м² ср мкм), и K2, К, яркостной температуры.
THERMAL = {"b10": (3040.136402, 1735.337945),
           "b11": (2482.375199, 1666.398761),
           "b12": (1935.060183, 1585.420044),
           "b13": (866.468575, 1350.069147),
           "b14": (641.326517, 1271.221673)}

# Продукты: сочетания (каналы на красный, зелёный, синий), индекс NDVI
# со шкалой core.sentinel, отношения с растяжением, все каналы.
COMPOSITES = {"aster_false": ("b3n", "b2", "b1"),
              "aster_swir": ("b4", "b6", "b8")}
RATIOS = ("kaolinite", "aloh", "mgoh", "ferric", "quartz")
PRODUCTS = ("aster_false", "aster_swir", "kaolinite", "aloh", "mgoh",
            "ferric", "quartz", "all_bands")
DEFAULT = ("aster_false", "aster_swir", "kaolinite")
# Цвета отношений от малых к большим, доля 0-1 растяжения.
RAMP = ((0.0, (43, 131, 186)), (0.25, (171, 221, 164)),
        (0.5, (255, 255, 191)), (0.75, (253, 174, 97)),
        (1.0, (215, 25, 28)))


def is_aster(mission):
    """ASTER открытой копии 2000-2006 или NASA после 2006 года."""
    return mission in (MISSION, NASA_MISSION)


def has(key, assets):
    """Канал есть у сцены: файл канала (NASA) или файл группы каналов
    (Planetary Computer)."""
    return key in assets or BANDS[key][0] in assets


def file_suffix(key):
    """Окончание имени файла канала NASA: «VNIR_B03N», «TIR_B10»."""
    name = key[1:].upper()
    number = name.rstrip("N")
    return "{}_B{:02d}{}".format(BANDS[key][0], int(number),
                                 name[len(number):])


def cmr_url(ring, start, end, max_cloud, page_size=NASA_PAGE):
    """Адрес поиска сцен NASA CMR: рамка кольца (широта, долгота), дни
    «ГГГГ-ММ-ДД», облачность сцены, новые первыми."""
    lats = [p[0] for p in ring]
    lons = [p[1] for p in ring]
    query = [("collection_concept_id", NASA_COLLECTION),
             ("bounding_box", "{:.6f},{:.6f},{:.6f},{:.6f}".format(
                 min(lons), min(lats), max(lons), max(lats))),
             ("temporal", "{}T00:00:00Z,{}T23:59:59Z".format(start, end)),
             ("cloud_cover", "0,{:g}".format(float(max_cloud))),
             ("sort_key", "-start_date"),
             ("page_size", str(int(page_size)))]
    return NASA_SEARCH + "?" + urlencode(query)


def _number(text):
    """Число из поля каталога или None."""
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def parse_cmr(data):
    """Сцены ответа CMR: словари id, when, cloud, epsg, sun, preview,
    files {канал: адрес}. Ночные сцены (солнце ниже горизонта, только
    тепловые каналы) отброшены."""
    out = []
    for item in (data or {}).get("items") or []:
        umm = item.get("umm") or {}
        attrs = {a.get("Name"): (a.get("Values") or [None])[0]
                 for a in umm.get("AdditionalAttributes") or []}
        sun = _number(attrs.get("SolarElevationAngle"))
        zone = _number(attrs.get("UTMZone"))
        if sun is None or zone is None or sun <= 0.0:
            continue
        zone = int(zone)
        files = {}
        preview = ""
        for link in umm.get("RelatedUrls") or []:
            url = str(link.get("URL") or "")
            if not url.startswith("https://"):
                continue
            if link.get("Type") == "GET RELATED VISUALIZATION":
                preview = url
                continue
            if link.get("Type") != "GET DATA":
                continue
            for key in BANDS:
                if url.endswith("_" + file_suffix(key) + ".tif"):
                    files[key] = url
        if "b1" not in files:
            continue
        lats = []
        geometry = ((umm.get("SpatialExtent") or {})
                    .get("HorizontalSpatialDomain") or {}).get("Geometry")
        for polygon in (geometry or {}).get("GPolygons") or []:
            for point in (polygon.get("Boundary") or {}).get("Points") or []:
                lats.append(float(point.get("Latitude", 0.0)))
        north = (sum(lats) / len(lats)) >= 0.0 if lats else True
        when = (umm.get("TemporalExtent") or {}).get("SingleDateTime") or ""
        cloud = umm.get("CloudCover")
        out.append({"id": str(umm.get("GranuleUR") or ""),
                    "when": str(when).replace("T", " ")[:16],
                    "cloud": float(cloud) if cloud is not None else 100.0,
                    "epsg": (32600 if north else 32700) + zone,
                    "sun": sun, "preview": preview, "files": files})
    return out


def needed(products, assets=None):
    """Каналы для продуктов по порядку номеров. С assets - только
    каналы сцены: «Все каналы» у сцены без SWIR - 8 каналов."""
    keys = set()
    for name in products:
        if name in COMPOSITES:
            keys.update(COMPOSITES[name])
        elif name == "kaolinite":
            keys.update(("b4", "b5", "b6"))
        elif name == "aloh":
            keys.update(("b5", "b6", "b7"))
        elif name == "mgoh":
            keys.update(("b7", "b8", "b9"))
        elif name == "ferric":
            keys.update(("b1", "b2"))
        elif name == "quartz":
            keys.update(("b10", "b11", "b12"))
        elif name == "all_bands":
            keys.update(ORDER)
    return [k for k in ORDER if k in keys
            and (assets is None or has(k, assets))]


def files_of(keys):
    """Файлы сцены для каналов: {файл: [каналы]}."""
    out = {}
    for key in keys:
        out.setdefault(BANDS[key][0], []).append(key)
    return out


def available(products, assets):
    """Продукты, файлы которых есть у сцены, - у части сцен нет SWIR."""
    return [p for p in products
            if (p == "all_bands" and has("b1", assets))
            or all(has(k, assets) for k in needed([p]))]


def sun_distance(day_of_year):
    """Расстояние Земля - Солнце в астрономических единицах."""
    return 1.0 - 0.01672 * math.cos(math.radians(0.9856
                                                 * (day_of_year - 4)))


def radiance(dn, key):
    """Яркость канала, нет данных (0) - NaN, float32."""
    dn = np.asarray(dn)
    out = (dn.astype(np.float32) - np.float32(1.0)) \
        * np.float32(BANDS[key][3])
    out[dn == 0] = np.nan
    return out


def value(dn, key, sun_elevation, day_of_year):
    """Значение канала в выдаче: отражение на верху атмосферы у VNIR
    и SWIR, яркостная температура, К, у TIR."""
    lum = radiance(dn, key)
    if key in THERMAL:
        k1, k2 = THERMAL[key]
        with np.errstate(divide="ignore", invalid="ignore"):
            out = k2 / np.log(k1 / lum + 1.0)
        out[~(lum > 0)] = np.nan
        return out.astype(np.float32)
    sine = math.sin(math.radians(float(sun_elevation)))
    if sine <= 0.0:
        raise ValueError("sun below horizon")
    d = sun_distance(day_of_year)
    return (lum * np.float32(math.pi * d * d / (ESUN[key] * sine))) \
        .astype(np.float32)


def _ratio(a, b):
    with np.errstate(divide="ignore", invalid="ignore"):
        out = a / b
    out[~np.isfinite(out)] = np.nan
    return out.astype(np.float32)


def product(name, bands):
    """Массив продукта по значениям каналов (value). Кварц - по
    яркости тепловых каналов, она передаётся в bands под ключами
    «L10», «L11», «L12»."""
    if name in COMPOSITES:
        return np.stack([bands[k] for k in COMPOSITES[name]])
    if name == "kaolinite":
        return _ratio(bands["b4"] + bands["b6"], bands["b5"])
    if name == "aloh":
        return _ratio(bands["b5"] + bands["b7"], bands["b6"])
    if name == "mgoh":
        return _ratio(bands["b7"] + bands["b9"], bands["b8"])
    if name == "ferric":
        return _ratio(bands["b2"], bands["b1"])
    if name == "quartz":
        return _ratio(bands["L11"] * bands["L11"],
                      bands["L10"] * bands["L12"])
    if name == "all_bands":
        return np.stack([bands[k] for k in ORDER if k in bands])
    raise KeyError(name)


def label(key):
    """Подпись канала в файле «Все каналы»: «B3N 0.82 мкм», у
    тепловых - с единицей."""
    name = "B" + key[1:].upper()
    text = "{} {:g} um".format(name, BANDS[key][2])
    return text + ", K" if key in THERMAL else text


def file_name(day, name):
    """Имя файла продукта: «AST_20060815_aloh»."""
    return "AST_{}_{}".format(day.replace("-", ""), name)
