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

Глубины морей на выбор - решение автора от 17 октября 2026 года после
списка открытых данных помощника. Terrarium даёт дно до уровня 10,
у Японского жёлоба на уровнях 11-12 в нём нули, на глубоководных
равнинах - пятна до -13 км. GEBCO 2026 Grid (сетка 15", около 450 м)
заменяет высоты тайла там, где и у тайла, и у GEBCO ниже нуля
(merge_sea), с уровня SEA_MIN_LEVEL. GEBCO - общественное достояние,
условие - подпись источника и запрет выдавать данные за одобренные
GEBCO, IHO и IOC, для навигации данные не годятся. Файл COG с уровнями
обзора - копия Source Cooperative (giswqs/gebco-bathymetry), её
выложил Qiusheng Wu, у самого GEBCO файлы только архивом. Проверено
17 октября 2026 года - 86 400 × 43 200, Int16, DEFLATE, обзоры до
1350 × 675.
"""
import math

import numpy as np

TERRARIUM = "terrarium"
COPERNICUS = "copernicus30"
GEDTM = "gedtm30"
CHOICES = (TERRARIUM, COPERNICUS, GEDTM)
GEBCO = "gebco2026"
# Глубины морей: только тайлы высот или GEBCO поверх них. По умолчанию
# GEBCO - выбор помощника, утверждает автор.
SEA_CHOICES = (TERRARIUM, GEBCO)
SEA_DEFAULT = GEBCO

# С этого уровня тайла высот суша берётся из модели 30 м. Пиксель
# тайла уровня 9 - около 300 м у экватора, мельче модель 30 м
# не нужна, а чтение файлов в сети дороже тайла Terrarium.
MIN_LEVEL = 9
# Глубже этого уровня окно модели не читается, а пересчитывается из
# окна предка: пиксель тайла уровня 12 - 38 м у экватора и 20 м на
# широте 58°, подробнее модели 30 м. Чтений сети на вид в разы меньше.
READ_LEVEL = 12
# GEBCO: с уровня 5 (пиксель тайла около 4.9 км у экватора, мельче
# тайлы Terrarium не хуже) до уровня 9 (около 300 м, мельче сетки
# 450 м), глубже - пересчёт окна предка. Выбор помощника.
SEA_MIN_LEVEL = 5
SEA_READ_LEVEL = 9

COPERNICUS_URL = ("https://copernicus-dem-30m.s3.amazonaws.com/"
                  "{name}/{name}.tif")
GEDTM_URL = ("https://s3.opengeohub.org/global/dtm/v1.2/"
             "gedtm_rf_m_30m_s_20060101_20151231_go_epsg.4326.3855_v1.2.tif")
GEBCO_URL = ("https://data.source.coop/giswqs/gebco-bathymetry/gebco_2026/"
             "gebco_2026.tif")

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
    GEBCO: ("Bathymetry: GEBCO Compilation Group (2026) GEBCO 2026 Grid",
            "https://www.gebco.net/data-products/gridded-bathymetry/"
            "terms-of-use"),
}

EARTH_RADIUS = 6378137.0


def choice(value):
    """Выбор рельефа по настройке: неизвестное значение - Terrarium."""
    return value if value in CHOICES else TERRARIUM


def sea_choice(value):
    """Выбор глубин морей по настройке: пусто или неизвестное значение -
    SEA_DEFAULT."""
    return value if value in SEA_CHOICES else SEA_DEFAULT


def levels(kind):
    """Уровни модели kind: с какого тайла она берётся и глубже какого
    окно пересчитывается из предка."""
    if kind == GEBCO:
        return SEA_MIN_LEVEL, SEA_READ_LEVEL
    return MIN_LEVEL, READ_LEVEL


def has_sea(base):
    """Есть ли в тайле высот пиксели не выше нуля - без них окно GEBCO
    не читается."""
    return bool((np.asarray(base) <= 0.0).any())


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


def merge_sea(base, sea):
    """Высоты тайла base с глубинами sea того же размера: глубина GEBCO
    берётся там, где и у тайла, и у GEBCO ниже нуля или ноль у тайла.
    Ноль - пустое место дна Terrarium на уровнях 11-12. Суша тайла
    остаётся, береговая линия - его."""
    if sea is None:
        return base
    use = np.isfinite(sea) & (sea < 0.0) & (base <= 0.0)
    out = base.astype(np.float32, copy=True)
    out[use] = sea[use]
    return out
