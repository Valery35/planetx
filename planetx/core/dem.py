# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Рельеф Земли на выбор: Terrarium или модель 30 м поверх него.

Решение автора от 10 октября 2026 года - в окне «Источники данных»
выбираются Terrarium (по умолчанию), Copernicus DEM GLO-30 и GEDTM30.
Тайлы Terrarium грузятся всегда, они дают дно морей и мелкие уровни.
С уровня MIN_LEVEL высоты суши в тайле заменяет модель 30 м, её окно
читает GDAL из файлов в сети (ui/inset.py, DemSource).

Copernicus DEM GLO-30 - модель поверхности (DSM), лес и дома входят
в высоту. Файлы по градусу на открытом хранилище AWS, над морем файлов
нет. Условия - лицензия ESA для Copernicus DEM, подпись ниже.

GEDTM30 v1.2 (OpenGeoHub, Ho и др., PeerJ 2025) - модель рельефа без
леса и домов (DTM), один глобальный файл COG в EPSG:4326, высоты в
метрах над EGM2008, CC BY 4.0. В файле стоит множитель 0.1, но
значения - метры: Народная 1860 м, Эльбрус 5447 м, у Copernicus
1877 и 5453 м, проверено 10 октября 2026 года.
"""
import math

import numpy as np

TERRARIUM = "terrarium"
COPERNICUS = "copernicus30"
GEDTM = "gedtm30"
CHOICES = (TERRARIUM, COPERNICUS, GEDTM)

# С этого уровня тайла высот суша берётся из модели 30 м. Пиксель
# тайла уровня 9 - около 300 м у экватора, мельче модель 30 м
# не нужна, а чтение файлов в сети дороже тайла Terrarium.
MIN_LEVEL = 9
# Глубже этого уровня окно модели не читается, а пересчитывается из
# окна предка: пиксель тайла уровня 12 - 38 м у экватора и 20 м на
# широте 58°, подробнее модели 30 м. Чтений сети на вид в разы меньше.
READ_LEVEL = 12

COPERNICUS_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
                  "{name}/{name}.tif")
GEDTM_URL = ("https://s3.opengeohub.org/global/dtm/v1.2/"
             "gedtm_rf_m_30m_s_20060101_20151231_go_epsg.4326.3855_v1.2.tif")

ATTRIBUTION = {
    COPERNICUS: ("Produced using Copernicus WorldDEM-30 © DLR e.V. "
                 "2010-2014 and © Airbus Defence and Space GmbH 2014-2018 "
                 "provided under COPERNICUS by the European Union and ESA; "
                 "all rights reserved",
                 "https://dataspace.copernicus.eu/explore-data/"
                 "data-collections/copernicus-contributing-missions/"
                 "collections-description/COP-DEM"),
    GEDTM: ("GEDTM30 v1.2: OpenGeoHub, Ho et al. 2025, CC BY 4.0",
            "https://doi.org/10.7717/peerj.19673"),
}

EARTH_RADIUS = 6378137.0


def choice(value):
    """Выбор рельефа по настройке: неизвестное значение - Terrarium."""
    return value if value in CHOICES else TERRARIUM


def tile_degrees(z, x, y):
    """Рамка тайла XYZ в градусах: запад, юг, восток, север."""
    n = 2 ** z

    def lat(row):
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return (x / n * 360.0 - 180.0, lat(y + 1),
            (x + 1) / n * 360.0 - 180.0, lat(y))


def tile_meters(z, x, y):
    """Рамка тайла XYZ в EPSG:3857: запад, юг, восток, север."""
    side = 2 * math.pi * EARTH_RADIUS / 2 ** z
    west = -math.pi * EARTH_RADIUS + x * side
    north = math.pi * EARTH_RADIUS - y * side
    return west, north - side, west + side, north


def copernicus_name(lat, lon):
    """Имя файла Copernicus DEM градуса с юго-западным углом lat, lon."""
    return "Copernicus_DSM_COG_10_{}{:02d}_00_{}{:03d}_00_DEM".format(
        "N" if lat >= 0 else "S", abs(lat), "E" if lon >= 0 else "W",
        abs(lon))


def copernicus_cells(west, south, east, north):
    """Градусы (широта и долгота юго-западного угла), которые задевает
    рамка в градусах."""
    cells = []
    for lat in range(math.floor(south), math.ceil(north)):
        if not -90 <= lat < 90:
            continue
        for lon in range(math.floor(west), math.ceil(east)):
            cells.append((lat, (lon + 180) % 360 - 180))
    return cells


def copernicus_url(lat, lon):
    return COPERNICUS_URL.format(name=copernicus_name(lat, lon))


def merge(base, dem):
    """Высоты тайла base с моделью dem того же размера: где у модели
    есть значение, берётся оно. Дно моря остаётся от base: у Copernicus
    над морем 0, у GEDTM нет данных."""
    if dem is None:
        return base
    use = np.isfinite(dem) & ~((dem <= 0.0) & (base < 0.0))
    out = base.astype(np.float32, copy=True)
    out[use] = dem[use]
    return out
