# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетка аномалии Буге по аномалии в свободном воздухе и рельефу.

    python-qgis.bat tools/build_bouguer.py gravity.tif bed.tif \
        surface.tif ВЫХОД.tif

gravity.tif - аномалия в свободном воздухе tools/build_gravity.py,
середины клеток 0.25°. bed.tif и surface.tif - ETOPO 2022, шаг 60",
отметки коренного рельефа с дном морей и верха льда (NOAA NCEI,
общественное достояние США, doi:10.25921/fd45-gt74).

Простая поправка Буге - притяжение бесконечного плоского слоя
2πGρh. Масса выше уровня моря снимается - порода плотности RHO_CRUST
и лёд RHO_ICE, ниже уровня моря вода и лёд заменяются породой. Поправка
считается в каждой клетке 60" и осредняется на клетку 0.25° - так
крутой берег не смешивает воду и сушу до вычисления. Поправки на
рельеф вокруг (terrain correction) нет. Аномалия Буге - аномалия
в свободном воздухе минус поправка, мГал. Над океаном она
положительная, под горами отрицательная.
"""
import math
import sys

import numpy as np

G = 6.674e-11
RHO_CRUST = 2670.0  # кг/м³, принятая плотность верхней коры
RHO_WATER = 1030.0  # морская вода
RHO_ICE = 917.0
MGAL = 1.0e5  # м/с² в мГал
SLAB = 2.0 * math.pi * G * MGAL  # мГал на кг/м³ и метр
CELL = 15  # клеток 60" в клетке 0.25° по стороне


def correction(bed, surface):
    """Поправка Буге, мГал, по отметкам коренного рельефа bed и верха
    поверхности surface, метры. Между ними - лёд или вода озёр, их
    плотности близки, считается лёд. Выше нуля - снимаемая масса, ниже
    нуля - недостаток массы до породы."""
    bed = np.asarray(bed, dtype=np.float64)
    surface = np.maximum(np.asarray(surface, dtype=np.float64), bed)
    rock_above = np.maximum(bed, 0.0)
    ice_above = np.maximum(surface, 0.0) - rock_above
    ice_below = np.maximum(np.minimum(surface, 0.0) - bed, 0.0) \
        * (bed < 0.0)
    water_below = np.maximum(-bed, 0.0) - ice_below
    return SLAB * (RHO_CRUST * rock_above + RHO_ICE * ice_above
                   - (RHO_CRUST - RHO_ICE) * ice_below
                   - (RHO_CRUST - RHO_WATER) * water_below)


def block_mean(values, cell=CELL):
    """Среднее блоков cell × cell."""
    rows, cols = values.shape
    return values.reshape(rows // cell, cell, cols // cell, cell).mean(
        axis=(1, 3))


def main(gravity, bed_path, surface_path, out):
    from osgeo import gdal
    gdal.UseExceptions()
    # Набор держится в переменной: без него полоса теряет владельца.
    gravity_ds = gdal.Open(gravity)
    free_air = gravity_ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    bed_ds = gdal.Open(bed_path)
    surface_ds = gdal.Open(surface_path)
    cols, rows = bed_ds.RasterXSize, bed_ds.RasterYSize
    assert (rows // CELL, cols // CELL) == free_air.shape, (
        rows, cols, free_air.shape)
    x0, dx, _, y0, _, dy = bed_ds.GetGeoTransform()
    assert abs(x0 + 180.0) < 1e-9 and abs(y0 - 90.0) < 1e-9, (x0, y0)
    slab = np.zeros_like(free_air)
    band = CELL * 60  # строк 60" за раз
    for top in range(0, rows, band):
        count = min(band, rows - top)
        bed = bed_ds.GetRasterBand(1).ReadAsArray(0, top, cols, count)
        surface = surface_ds.GetRasterBand(1).ReadAsArray(0, top, cols,
                                                          count)
        slab[top // CELL:(top + count) // CELL] = block_mean(
            correction(bed, surface))
    grid = free_air - slab
    ds = gdal.GetDriverByName("GTiff").Create(
        out, grid.shape[1], grid.shape[0], 1, gdal.GDT_Float32,
        options=["COMPRESS=DEFLATE"])
    ds.SetGeoTransform((-180.0, 0.25, 0.0, 90.0, 0.0, -0.25))
    ds.GetRasterBand(1).WriteArray(grid.astype(np.float32))
    ds = None
    print(out, "mGal", float(np.percentile(grid, 1)),
          float(np.percentile(grid, 99)), float(grid.min()), float(grid.max()))


if __name__ == "__main__":
    main(*sys.argv[1:5])
