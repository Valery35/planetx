# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Продукты MODIS в окне снимков. Расчёт без Qt.

Решение автора от 10 октября 2026 года - температура поверхности,
NDVI и EVI за 16 суток, снег и гари по месяцам. Каталог и файлы -
Microsoft Planetary Computer, коллекции версии 061, ключ SAS у каждой
коллекции свой, его выдаёт служба без учётной записи. Файлы - COG
по каналам в синусоидальной проекции, тайлы 10° (h, v). Сцена окна -
один день или один период одного спутника (Terra, Aqua, у гарей -
оба), тайлы, которые задевает участок, читаются вместе. Выдача - в UTM
середины участка с шагом продукта.

Значения каналов (описание продуктов NASA LP DAAC и NSIDC):
- LST_Day_1km, LST_Night_1km - кельвины × 50, 0 - нет данных;
- 250m_16_days_NDVI, EVI - × 10000, -3000 - нет данных,
  250m_16_days_pixel_reliability - -1 нет данных, 3 облака;
- NDSI_Snow_Cover - 0-100 % снега, 200 и выше - флаги, 250 облака;
- Maximum_Snow_Extent - 25 нет снега, 100 лёд на озере, 200 снег,
  50 облака, 0, 1, 11, 254, 255 - нет данных;
- Burn_Date - день года выгорания, 0 не горело, -1 и -2 нет данных.
"""
import math

import numpy as np

KELVIN = 273.15

# Спутник окна: коллекция, шаг выдачи, м, продукты, маска качества.
MISSIONS = {
    "modis_lst1": ("modis-11A1-061", 1000.0, ("lst_day", "lst_night"),
                   "LST_Day_1km"),
    "modis_lst8": ("modis-11A2-061", 1000.0, ("lst_day", "lst_night"),
                   "LST_Day_1km"),
    "modis_veg": ("modis-13Q1-061", 250.0, ("modis_ndvi", "modis_evi"),
                  "250m_16_days_pixel_reliability"),
    "modis_snow1": ("modis-10A1-061", 500.0, ("snow_cover",),
                    "NDSI_Snow_Cover"),
    "modis_snow8": ("modis-10A2-061", 500.0, ("snow_extent",),
                    "Maximum_Snow_Extent"),
    "modis_burn": ("modis-64A1-061", 500.0, ("burn_date",), "Burn_Date"),
}

TEMPERATURE = ((-30.0, 45.0),
               ((-30.0, (49, 54, 149)), (-10.0, (116, 173, 209)),
                (0.0, (224, 243, 248)), (15.0, (254, 224, 144)),
                (30.0, (244, 109, 67)), (45.0, (165, 0, 38))))
VEGETATION = ((-0.2, 0.9),
              ((-0.2, (165, 0, 38)), (0.0, (244, 109, 67)),
               (0.2, (254, 224, 139)), (0.4, (217, 239, 139)),
               (0.6, (102, 189, 99)), (0.9, (0, 104, 55))))
SNOW = ((0.0, 100.0),
        ((0.0, (120, 110, 90)), (30.0, (180, 200, 215)),
         (70.0, (120, 180, 230)), (100.0, (255, 255, 255))))
# Классы снега за 8 суток: 0 нет снега, 1 снег, 2 лёд на озере.
SNOW_CLASSES = ((0.0, 2.0),
                ((0.0, (120, 110, 90)), (1.0, (255, 255, 255)),
                 (2.0, (120, 200, 255))))
BURN = ((1.0, 366.0),
        ((1.0, (255, 255, 178)), (120.0, (254, 204, 92)),
         (200.0, (253, 141, 60)), (270.0, (240, 59, 32)),
         (366.0, (189, 0, 38))))

# Продукт: канал, шкала, цвета классами (True) или переходом.
PRODUCTS = {
    "lst_day": ("LST_Day_1km", TEMPERATURE, False),
    "lst_night": ("LST_Night_1km", TEMPERATURE, False),
    "modis_ndvi": ("250m_16_days_NDVI", VEGETATION, False),
    "modis_evi": ("250m_16_days_EVI", VEGETATION, False),
    "snow_cover": ("NDSI_Snow_Cover", SNOW, False),
    "snow_extent": ("Maximum_Snow_Extent", SNOW_CLASSES, True),
    "burn_date": ("Burn_Date", BURN, False),
}


def is_modis(mission):
    return mission in MISSIONS


def collection(mission):
    return MISSIONS[mission][0]


def products_of(mission):
    return MISSIONS[mission][2]


def step(mission):
    return MISSIONS[mission][1]


def quality_asset(mission):
    return MISSIONS[mission][3]


def mission_of(collection_id):
    """Спутник окна по коллекции элемента каталога или None."""
    for key, spec in MISSIONS.items():
        if spec[0] == collection_id:
            return key
    return None


def platform(item_id):
    """Спутник по номеру элемента: MOD - Terra, MYD - Aqua, MCD - оба."""
    return {"MOD": "Terra", "MYD": "Aqua", "MCD": "Terra+Aqua"}.get(
        str(item_id)[:3], "")


def tile_of(props):
    h = props.get("modis:horizontal-tile")
    v = props.get("modis:vertical-tile")
    if h is None or v is None:
        return ""
    return "h{:02d}v{:02d}".format(int(h), int(v))


def utm_epsg(ring):
    """EPSG системы UTM середины участка (широта, долгота)."""
    lat = sum(p[0] for p in ring) / len(ring)
    lon = sum(p[1] for p in ring) / len(ring)
    zone = int(math.floor((lon + 180.0) / 6.0)) % 60 + 1
    return (32600 if lat >= 0.0 else 32700) + zone


def needed(products):
    """Каналы продуктов MODIS."""
    keys = []
    for name in products:
        key = PRODUCTS[name][0]
        if key not in keys:
            keys.append(key)
    return keys


def value(name, raw):
    """Значения продукта из сырого канала, нет данных - NaN, float32."""
    raw = np.asarray(raw)
    data = raw.astype(np.float32)
    if name in ("lst_day", "lst_night"):
        out = data * np.float32(0.02) - np.float32(KELVIN)
        out[raw == 0] = np.nan
    elif name in ("modis_ndvi", "modis_evi"):
        out = data * np.float32(1e-4)
        out[raw <= -2000] = np.nan
    elif name == "snow_cover":
        out = data.copy()
        out[raw > 100] = np.nan
    elif name == "snow_extent":
        out = np.full(raw.shape, np.nan, dtype=np.float32)
        out[raw == 25] = 0.0
        out[raw == 200] = 1.0
        out[raw == 100] = 2.0
    else:  # burn_date
        out = data.copy()
        out[(raw <= 0) | (raw > 366)] = np.nan
    return out.astype(np.float32)


def quality(mission, raw, inside):
    """Облачность над участком по каналу качества: (доля облаков среди
    пикселей с данными, доля пикселей с данными), в процентах. У
    температуры пропуск значения - облако, у гарей облаков нет."""
    raw = np.asarray(raw)
    if mission in ("modis_lst1", "modis_lst8"):
        empty = np.zeros(raw.shape, dtype=bool)
        cloudy = raw == 0
    elif mission == "modis_veg":
        empty = raw < 0
        cloudy = raw == 3
    elif mission == "modis_snow1":
        empty = np.isin(raw, (200, 201, 211, 254, 255))
        cloudy = raw == 250
    elif mission == "modis_snow8":
        empty = np.isin(raw, (0, 1, 11, 254, 255))
        cloudy = raw == 50
    else:
        empty = raw < 0
        cloudy = np.zeros(raw.shape, dtype=bool)
    area = int(inside.sum())
    valid = inside & ~empty
    count = int(valid.sum())
    if area == 0 or count == 0:
        return 100.0, 0.0
    return (float(100.0 * (cloudy & valid).sum() / count),
            float(100.0 * count / area))


def clear(mission, raw):
    """Пиксели без облаков и пропусков по каналу качества."""
    raw = np.asarray(raw)
    if mission == "modis_veg":
        return raw >= 0
    if mission == "modis_snow1":
        return raw <= 100
    if mission == "modis_snow8":
        return np.isin(raw, (25, 100, 200))
    return np.ones(raw.shape, dtype=bool)


# Подпись: короткое имя продукта и архив NASA, где он хранится.
ARCHIVES = {"10A1": "NSIDC DAAC", "10A2": "NSIDC DAAC"}


def credit(item_id):
    """Подпись слоя: «MOD11A1 v061, NASA EOSDIS LP DAAC»."""
    short = str(item_id).split(".")[0]
    archive = ARCHIVES.get(short[3:], "LP DAAC")
    return "{} v061, NASA EOSDIS {}".format(short, archive)


def colorize(values, scale):
    """Картинка (3, строки, столбцы) uint8 по шкале продукта, нет
    данных - серый."""
    (lo, hi), stops = scale
    xs = np.array([s[0] for s in stops], dtype=np.float32)
    out = np.empty((3,) + values.shape, dtype=np.uint8)
    finite = np.isfinite(values)
    v = np.clip(np.where(finite, values, lo), lo, hi)
    for c in range(3):
        channel = np.interp(v, xs, [s[1][c] for s in stops])
        channel[~finite] = 90
        out[c] = channel.astype(np.uint8)
    return out


def merge_tiles(scenes):
    """Сцены одного дня или периода одного спутника - одна сцена,
    адреса каналов всех тайлов вместе. Порядок - от новых к старым."""
    groups = {}
    order = []
    for s in scenes:
        key = (s.when, s.tile.split(" ")[0])
        if key not in groups:
            groups[key] = s
            order.append(key)
            continue
        first = groups[key]
        assets = dict(first.assets)
        for name, asset in s.assets.items():
            if name in assets:
                assets[name] = assets[name]._replace(
                    href=tuple(assets[name].href) + tuple(asset.href))
        tiles = first.tile + "," + s.tile.split(" ")[-1]
        groups[key] = first._replace(assets=assets, tile=tiles)
    merged = [groups[k] for k in order]
    merged.sort(key=lambda s: s.when, reverse=True)
    return merged
