# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Растр дна Бриенцского озера для демо «Бриенцское озеро, своя
батиметрия».

Источник - swissBATHY3D swisstopo, озеро Brienzersee, сетки ESRI ASCII
1 м тайлами по 1 км, система LV95 (EPSG:2056), высоты LN02 - отметки
дна, не глубины. Условия - открытые данные swisstopo с указанием
источника, doc/SOURCES.md. Архив озера (около 130 МБ) скачивается
вручную со страницы swissBATHY3D и распаковывается в папку, она - первый
аргумент. Растр пересобирается с шагом STEP в GeoTIFF planetx/demo/
brienz/brienzersee_bed.tif.

    $PY tools/make_bathy_demo.py <папка с .asc>
"""
import glob
import os
import sys

from osgeo import gdal

STEP = 10.0  # м, шаг демо-растра
OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "planetx", "demo", "brienz", "brienzersee_bed.tif")


def main(folder):
    gdal.UseExceptions()
    files = sorted(glob.glob(os.path.join(folder, "*.asc")))
    if not files:
        raise SystemExit("нет файлов .asc в " + folder)
    mosaic = gdal.BuildVRT("", files)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    gdal.Warp(OUT, mosaic, format="GTiff", srcSRS="EPSG:2056",
              dstSRS="EPSG:2056", xRes=STEP, yRes=STEP,
              resampleAlg="average", outputType=gdal.GDT_Float32,
              dstNodata=-9999.0,
              creationOptions=["COMPRESS=DEFLATE", "PREDICTOR=3",
                               "TILED=YES"])
    out = gdal.Open(OUT)
    band = out.GetRasterBand(1)
    low, high = band.ComputeRasterMinMax(False)
    print("{}: {} x {}, дно {:.1f}-{:.1f} м, {:.0f} КБ".format(
        OUT, out.RasterXSize, out.RasterYSize, low, high,
        os.path.getsize(OUT) / 1024.0))


if __name__ == "__main__":
    main(sys.argv[1])
