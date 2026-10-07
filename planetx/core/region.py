# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Region KML: метка или папка видна только вблизи.

Просьба автора от 8 октября 2026 года - «у KML есть скрытие меток
дальше дистанции». Region - рамка LatLonAltBox и Lod с minLodPixels
и maxLodPixels. Метка видна, когда размер рамки на экране, корень из
её площади в пикселях, не меньше minLodPixels и не больше
maxLodPixels, -1 - без предела. Так делает Google Earth.

Размер рамки считается с постоянным фокусным расстоянием REF_FOCAL,
а не по окну глобуса. Тогда поле «Скрывать дальше, км» окна свойств
действует на том расстоянии, которое в нём записано, при любом окне.
REF_FOCAL - окно высотой 1000 пикселей с полем зрения 60°. Поле
пишется в KML тем же Region (for_distance), Google Earth читает его
так же. Расстояние - от глаза до середины рамки на уровне эллипсоида.

Модуль Qt не знает.
"""
import json
import math
from collections import namedtuple

try:  # внутри плагина QGIS
    from .ellipsoid import geodetic_to_ecef
except ImportError:  # headless-тесты
    from ellipsoid import geodetic_to_ecef

M_PER_DEGREE = 111320.0
REF_FOCAL = 500.0 / math.tan(math.radians(30.0))  # 866 пикселей
BOX_SIDE = 1000.0  # м, сторона рамки точки или очень малой фигуры

Region = namedtuple("Region", "north south east west min_lod max_lod")
Region.__doc__ = """Region KML: рамка в градусах и пределы Lod в
пикселях, max_lod -1 - без предела."""


def _span(region):
    """Ширина и высота рамки в метрах."""
    east = region.east if region.east >= region.west \
        else region.east + 360.0
    middle = math.radians((region.north + region.south) / 2.0)
    width = (east - region.west) * M_PER_DEGREE * math.cos(middle)
    height = (region.north - region.south) * M_PER_DEGREE
    return max(width, 0.0), max(height, 0.0)


def side(region):
    """Корень из площади рамки, метры."""
    width, height = _span(region)
    return math.sqrt(width * height)


def center(region):
    east = region.east if region.east >= region.west \
        else region.east + 360.0
    lon = (region.west + east) / 2.0
    return (region.north + region.south) / 2.0, (lon + 180.0) % 360.0 - 180.0


def pixels(region, eye):
    """Размер рамки на экране в пикселях при глазе eye (ECEF, метры)."""
    lat, lon = center(region)
    x, y, z = geodetic_to_ecef(lat, lon, 0.0)
    distance = math.sqrt((eye[0] - x) ** 2 + (eye[1] - y) ** 2
                         + (eye[2] - z) ** 2)
    return side(region) * REF_FOCAL / max(distance, 1.0)


def active(region, eye):
    """Видна ли метка с Region при глазе eye. Без Region - видна."""
    if region is None:
        return True
    size = pixels(region, eye)
    if size < region.min_lod:
        return False
    return region.max_lod < 0 or size <= region.max_lod


def box(points):
    """Рамка точек (широта, долгота): (север, юг, восток, запад). Малая
    рамка растягивается до BOX_SIDE метров."""
    lats = [p[0] for p in points]
    lons = [p[1] for p in points]
    north, south, east, west = max(lats), min(lats), max(lons), min(lons)
    half_lat = BOX_SIDE / 2.0 / M_PER_DEGREE
    if north - south < 2.0 * half_lat:
        middle = (north + south) / 2.0
        north, south = middle + half_lat, middle - half_lat
    half_lon = half_lat / max(math.cos(math.radians((north + south) / 2.0)),
                              0.01)
    if east - west < 2.0 * half_lon:
        middle = (east + west) / 2.0
        east, west = middle + half_lon, middle - half_lon
    return north, south, east, west


def for_distance(points, km, old=None):
    """Region, который скрывает метку дальше km километров. Рамка -
    прежняя old или рамка точек, maxLodPixels - прежний или -1."""
    if old is not None:
        rect = (old.north, old.south, old.east, old.west)
        max_lod = old.max_lod
    else:
        rect = box(points)
        max_lod = -1.0
    probe = Region(*rect, 0.0, -1.0)
    min_lod = side(probe) * REF_FOCAL / (float(km) * 1000.0)
    return Region(*rect, round(min_lod, 6), max_lod)


def distance_km(region):
    """Расстояние, дальше которого метка скрыта, км, или None."""
    if region is None or region.min_lod <= 0.0:
        return None
    return side(region) * REF_FOCAL / region.min_lod / 1000.0


def text(region):
    """Region для поля файла меток: JSON, пустая строка - нет."""
    if region is None:
        return ""
    return json.dumps([round(v, 7) for v in region])


def parse(value):
    """Region из поля файла меток или None."""
    if not value:
        return None
    try:
        data = json.loads(str(value))
        region = Region(*(float(v) for v in data))
    except (ValueError, TypeError):
        return None
    if region.north < region.south:
        return None
    return region


def kml(region):
    """Region для записи в KML."""
    if region is None:
        return ""
    return ("<Region><LatLonAltBox><north>{:.7f}</north>"
            "<south>{:.7f}</south><east>{:.7f}</east><west>{:.7f}</west>"
            "</LatLonAltBox><Lod><minLodPixels>{:g}</minLodPixels>"
            "<maxLodPixels>{:g}</maxLodPixels></Lod></Region>").format(
                region.north, region.south, region.east, region.west,
                region.min_lod, region.max_lod)
