# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подложка под участком одним растром для окон анализа.

Тайлы идут через сеть модуля и дисковый кэш QGIS (net/ranges.py),
собираются в набор GDAL в памяти (core/tilemosaic.py), дальше он
читается тем же пересчётом на сетку участка, что растр проекта. Файла
снимка модуль не пишет.
"""
from ..core import tilemosaic
from ..net import ranges
from ..net.loader import decode_png


def read_images(source, keys, tick):
    """Картинки тайлов {ключ: RGBA или None}. Рабочий поток. Составной
    тайл (снимки Яндекса, служба WMS со своим районом) собирается
    из частей, без одной части его нет."""
    urls = {key: source.parts(*key) or [source.tile_url(*key)]
            for key in keys}
    data = ranges.fetch_source(
        source, sorted({url for parts in urls.values() for url in parts}),
        tick)
    out = {}
    for key, parts in urls.items():
        images = [None if data.get(url) is None
                  else decode_png(data[url], tilemosaic.SIZE)
                  for url in parts]
        if any(image is None for image in images):
            out[key] = None
        elif len(images) == 1:
            out[key] = images[0]
        else:
            out[key] = source.assemble(*key, images)
    return out


def dataset(source, z, frame, tick):
    """Набор GDAL в памяти с мозаикой RGBA в EPSG:3857 или None - ни один
    тайл не получен. Рабочий поток."""
    from osgeo import gdal, osr
    found = tilemosaic.gather(tilemosaic.tile_keys(z, frame),
                              lambda keys: read_images(source, keys, tick))
    if not found:
        return None
    rgba = tilemosaic.assemble(z, frame, found)
    rows, cols = rgba.shape[:2]
    data = gdal.GetDriverByName("MEM").Create("", cols, rows, 4,
                                              gdal.GDT_Byte)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(3857)
    data.SetProjection(srs.ExportToWkt())
    data.SetGeoTransform(tilemosaic.geotransform(z, frame))
    for number in range(4):
        data.GetRasterBand(number + 1).WriteArray(rgba[:, :, number])
    data.GetRasterBand(4).SetColorInterpretation(gdal.GCI_AlphaBand)
    return data, srs.ExportToWkt()
