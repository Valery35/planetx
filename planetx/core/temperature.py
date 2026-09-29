# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Температура поверхности из NASA GIBS: слои, адреса, шкалы, без Qt.

Суша - MODIS Terra, температура поверхности днём, сводка за 8 дней.
В дневном слое суши много дыр под облаками, в сводке их меньше.
Море - GHRSST MUR, температура поверхности моря за сутки, без дыр.
Оба слоя - картинки PNG уровней 0-7 с готовой раскраской GIBS
и прозрачностью там, где данных нет. Дата не задаётся, GIBS отдаёт
последнюю готовую. Решение автора от 29 сентября 2026 года.

Опорные цвета шкал выписаны из шкал GIBS MODIS_Land_Surface_Temp
и GHRSST_Sea_Surface_Temperature, v1.3, 29 сентября 2026 года,
13 точек на шкалу. Шкала суши у GIBS в кельвинах, здесь в °C.
"""
import numpy as np

URL = ("https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/{layer}"
       "/default/default/GoogleMapsCompatible_Level7/{{z}}/{{y}}/{{x}}.png")
MAX_LEVEL = 7
LAND = "MODIS_Terra_L3_Land_Surface_Temp_8Day_Day"
SEA = "GHRSST_L4_MUR_Sea_Surface_Temperature"
OPACITY = 0.75  # непрозрачность раскраски поверх снимка
ATTRIBUTION = ("NASA GIBS, MODIS, GHRSST MUR",
               "https://www.earthdata.nasa.gov/engage/open-data-services"
               "-software/earthdata-developer-portal/gibs-api")
KELVIN = 273.15

# (°C, цвет) от холодного к тёплому.
LAND_STOPS = tuple((round(k - KELVIN, 1), rgb) for k, rgb in (
    (200.3, (197, 0, 255)), (212.9, (113, 0, 255)), (225.5, (29, 0, 255)),
    (237.5, (0, 71, 255)), (250.1, (0, 179, 255)), (262.7, (26, 255, 196)),
    (274.7, (98, 255, 26)), (287.3, (175, 255, 0)), (299.9, (255, 255, 0)),
    (312.5, (255, 193, 0)), (325.1, (255, 127, 0)), (337.1, (255, 67, 0)),
    (349.7, (255, 4, 0))))
SEA_STOPS = (
    (0.1, (45, 0, 28)), (2.8, (101, 3, 93)), (5.3, (94, 8, 105)),
    (8.0, (30, 18, 78)), (10.7, (32, 57, 133)), (13.3, (37, 103, 185)),
    (16.0, (46, 163, 239)), (18.7, (32, 179, 13)), (21.2, (208, 239, 0)),
    (23.9, (255, 180, 0)), (26.6, (242, 95, 0)), (29.2, (202, 37, 0)),
    (31.9, (110, 3, 0)))
LAND_TICKS = (-60, -30, 0, 30, 60)  # подписи шкалы суши, °C
SEA_TICKS = (0, 10, 20, 30)


def url_template(layer):
    """Адрес тайла слоя для загрузчика, с полями {z}, {x}, {y}."""
    return URL.format(layer=layer)


def overlay_rgba(rgba):
    """Раскраска GIBS в RGBA uint8 с премноженной альфой
    и непрозрачностью OPACITY. Где данных нет, прозрачно."""
    rgba = np.asarray(rgba, dtype=np.float32)
    alpha = rgba[..., 3:4] / 255.0 * OPACITY
    out = np.empty(rgba.shape, dtype=np.uint8)
    out[..., :3] = np.rint(rgba[..., :3] * alpha)
    out[..., 3:] = np.rint(alpha * 255.0)
    return out


def share(stops, value):
    """Место значения на шкале от 0 до 1."""
    low, high = stops[0][0], stops[-1][0]
    return min(max((value - low) / (high - low), 0.0), 1.0)


def color_at(stops, value):
    """Цвет шкалы для значения, между опорными точками линейно."""
    values = [v for v, _ in stops]
    return tuple(int(round(np.interp(value, values,
                                     [c[i] for _, c in stops])))
                 for i in range(3))
