# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Томография мантии: файл netCDF модели EMC в файл профиля.

Работа рабочего потока (executor «deposits»): GDAL читает netCDF
многомерным доступом, core.tomography.make приводит сетку, save пишет
файл профиля. Qt не трогает.
"""
import os

from osgeo import gdal

from ..core import tomography


def parse_tomo(nc_path, out_path):
    """Модель из файла netCDF nc_path (переменные depth, latitude,
    longitude, dvs) в файл out_path. Возвращает core.tomography.Tomo.
    Файл netCDF после разбора удаляется."""
    ds = gdal.OpenEx(nc_path, gdal.OF_MULTIDIM_RASTER)
    if ds is None:
        raise ValueError("tomography: file not read")
    root = ds.GetRootGroup()
    arrays = {name: root.OpenMDArray(name)
              for name in root.GetMDArrayNames()}
    for name in ("depth", "latitude", "longitude", "dvs"):
        if name not in arrays:
            raise ValueError("tomography: no {}".format(name))
    tomo = tomography.make(arrays["depth"].ReadAsArray(),
                           arrays["latitude"].ReadAsArray(),
                           arrays["longitude"].ReadAsArray(),
                           arrays["dvs"].ReadAsArray())
    del arrays, root, ds
    tomography.save(tomo, out_path)
    # Файл netCDF больше не нужен. Не удалился - он останется в профиле
    # и будет перезаписан следующей загрузкой.
    if os.path.exists(nc_path):
        os.remove(nc_path)
    return tomo
