# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака из NASA GIBS: дата снимка, адрес тайла, прозрачность, без Qt.

Слой - VIIRS SNPP Corrected Reflectance True Color, снимок за сутки
в цвете, как его видит глаз. Отдельного слоя облаков в цвете у GIBS
нет. Облако - белое и серое, поэтому прозрачность тайла считается
по белизне пикселя: светлый пиксель без насыщенности становится
облаком, суша, море, пустыня и чёрные полосы между проходами спутника
пропадают. Снег и лёд тоже белые и остаются, на подложке они того же
цвета. Решение помощника от 29 сентября 2026 года, его утверждает
автор.

Снимок за вчерашние сутки UTC GIBS собирает до утра. Поэтому берутся
сутки, начало которых было не меньше LAG секунд назад: до полудня
UTC - позавчерашние, после - вчерашние.
"""
import datetime

import numpy as np

LAYER = "VIIRS_SNPP_CorrectedReflectance_TrueColor"
URL = ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/" + LAYER
       + "/default/{date}/GoogleMapsCompatible_Level9/{{z}}/{{y}}/{{x}}.jpg")
MAX_LEVEL = 9  # GoogleMapsCompatible_Level9, пиксель около 300 м
LAG = 36 * 3600  # секунд от начала суток снимка до показа
ATTRIBUTION = ("NASA GIBS, VIIRS",
               "https://www.earthdata.nasa.gov/engage/open-data-services"
               "-software/earthdata-developer-portal/gibs-api")
# Белизна: наименьший из трёх каналов, доля от 0 до 1. Ниже LOW
# облака нет, выше HIGH оно непрозрачно.
LOW, HIGH = 0.42, 0.85
# Насыщенность (наибольший - наименьший) / наибольший. Облако
# серое, песок и сухая трава желтее. Выше GREY_END облака нет.
GREY_START, GREY_END = 0.10, 0.28
FADE_START, FADE_END = 80.0, 85.0  # широты угасания облаков у полюсов


def image_date(unix_time):
    """Дата снимка «YYYY-MM-DD» для момента unix_time."""
    moment = datetime.datetime.fromtimestamp(unix_time - LAG,
                                             tz=datetime.timezone.utc)
    return moment.strftime("%Y-%m-%d")


def url_template(unix_time):
    """Адрес тайла для загрузчика, с полями {z}, {x}, {y}."""
    return URL.format(date=image_date(unix_time))


def _smooth(edge0, edge1, value):
    t = np.clip((value - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def row_latitudes(key, size):
    """Широты середин строк пикселей тайла key, градусы."""
    z, _, y = key
    rows = (y + (np.arange(size) + 0.5) / size) / float(1 << z)
    return np.degrees(np.arctan(np.sinh(np.pi * (1.0 - 2.0 * rows))))


def cloud_rgba(rgba, key=None):
    """Тайл снимка в облака: RGBA uint8 с премноженной альфой.

    Цвет облака - цвет пикселя, так видны тени и толщина облака.
    key - тайл снимка. С ним облака гаснут от FADE_START до FADE_END
    широты. Выше кончается Web Mercator и лежит одноцветная шапка,
    без угасания облака обрывались у неё ровным кругом.
    """
    rgb = np.asarray(rgba, dtype=np.float32)[..., :3] / 255.0
    low = rgb.min(axis=2)
    high = rgb.max(axis=2)
    grey = (high - low) / np.maximum(high, 1e-3)
    alpha = _smooth(LOW, HIGH, low) * (1.0 - _smooth(GREY_START, GREY_END,
                                                     grey))
    if key is not None:
        lat = np.abs(row_latitudes(key, rgb.shape[0]))
        alpha = alpha * (1.0 - _smooth(FADE_START, FADE_END, lat))[:, None]
    out = np.empty(rgb.shape[:2] + (4,), dtype=np.uint8)
    out[..., :3] = np.rint(rgb * alpha[..., None] * 255.0)
    out[..., 3] = np.rint(alpha * 255.0)
    return out


def source_key(key):
    """Тайл снимка для тайла глобуса: сам тайл или предок уровня
    MAX_LEVEL."""
    z, x, y = key
    if z <= MAX_LEVEL:
        return key
    shift = z - MAX_LEVEL
    return MAX_LEVEL, x >> shift, y >> shift
