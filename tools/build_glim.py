# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тайлы литологической карты GLiM для planetx-terrain.

    python-qgis.bat tools/build_glim.py raster "LiMW_GIS 2015.gdb" glim.tif
    python-qgis.bat tools/build_glim.py tiles glim.tif C:/Dev/planetx-terrain

Источник - база GLiM_export (Hartmann, Moosdorf 2012, архив
LiMW_GIS 2015.gdb.zip по ссылке со страницы PANGAEA 788537), проекция
World Eckert IV. Шаг raster пишет растр номеров классов core/glim.py
с клеткой CELL в той же проекции - по проходу gdal.RasterizeLayer на
класс с фильтром поля xx, затем обзоры по моде. Шаг tiles режет тайлы
Web Mercator уровней 0-glim.MAX_LEVEL ближайшим соседом с обзорами,
PNG RGBA с цветом класса, пустой тайл - прозрачный.
"""
import os
import sys

from osgeo import gdal, ogr, osr

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "planetx", "core"))
import glim  # noqa: E402

CELL = 1000.0  # м, клетка растра в Eckert IV
SIZE = 256
HALF = 20037508.342789244  # половина мира Web Mercator, м


def raster(gdb, out):
    gdal.UseExceptions()
    ogr.UseExceptions()
    source = ogr.Open(gdb)
    layer = source.GetLayer("GLiM_export")
    west, east, south, north = layer.GetExtent()
    width = int((east - west) / CELL) + 1
    height = int((north - south) / CELL) + 1
    target = gdal.GetDriverByName("GTiff").Create(
        out, width, height, 1, gdal.GDT_Byte,
        options=["COMPRESS=DEFLATE", "TILED=YES", "BIGTIFF=YES"])
    target.SetGeoTransform((west, CELL, 0.0, north, 0.0, -CELL))
    target.SetProjection(layer.GetSpatialRef().ExportToWkt())
    target.GetRasterBand(1).SetNoDataValue(0)
    for code, number, _ in glim.CLASSES:
        layer.SetAttributeFilter("xx = '{}'".format(code))
        gdal.RasterizeLayer(target, [1], layer, burn_values=[number])
        print(code, number, flush=True)
    layer.SetAttributeFilter(None)
    target.FlushCache()
    target.BuildOverviews("MODE", [2, 4, 8, 16, 32, 64, 128])
    # 17 октября 2026 года файл вышел без геопривязки и «нет данных»,
    # они ставятся ещё раз после обзоров.
    target.SetGeoTransform((west, CELL, 0.0, north, 0.0, -CELL))
    target.SetProjection(layer.GetSpatialRef().ExportToWkt())
    target.GetRasterBand(1).SetNoDataValue(0)
    target = None


def tile_bounds(z, x, y):
    step = 2.0 * HALF / (1 << z)
    west = -HALF + x * step
    north = HALF - y * step
    return west, north - step, west + step, north


def tiles(source, terrain):
    gdal.UseExceptions()
    table = glim.palette()
    ds = gdal.Open(source)
    mercator = osr.SpatialReference()
    mercator.ImportFromEPSG(3857)
    out_dir = os.path.join(terrain, glim.FOLDER)
    count = 0
    for z in range(glim.MAX_LEVEL + 1):
        for x in range(1 << z):
            for y in range(1 << z):
                warped = gdal.Warp("", ds, format="MEM",
                                   dstSRS=mercator.ExportToWkt(),
                                   outputBounds=tile_bounds(z, x, y),
                                   width=SIZE, height=SIZE,
                                   resampleAlg="near", srcNodata=0,
                                   dstNodata=0)
                numbers = warped.GetRasterBand(1).ReadAsArray()
                warped = None
                # Пустой тайл тоже пишется, прозрачный PNG около 100 байт:
                # отказ 404 загрузчик считал бы ошибкой источника.
                picture = table[numbers]
                path = os.path.join(out_dir, str(z), str(x), "%d.png" % y)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                mem = gdal.GetDriverByName("MEM").Create(
                    "", SIZE, SIZE, 4, gdal.GDT_Byte)
                for band in range(4):
                    mem.GetRasterBand(band + 1).WriteArray(
                        picture[..., band])
                gdal.GetDriverByName("PNG").CreateCopy(
                    path, mem, options=["ZLEVEL=9"])
                count += 1
        print("level", z, "tiles", count, flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "raster":
        raster(sys.argv[2], sys.argv[3])
    else:
        tiles(sys.argv[2], sys.argv[3])
