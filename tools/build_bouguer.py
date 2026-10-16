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
и лёд RHO_ICE, ниже уровня моря вода и лёд заменяются породой.

Поправка на рельеф вокруг (terrain correction) - с 16 октября 2026 года,
просьба автора. Вода и лёд пересчитываются в высоту породы той же массы
(rock-equivalent topography, ret), тогда простая поправка - 2πGρh_ret,
а поправка на рельеф в линейном приближении Moritz (1968)
TC(P) = Gρ / 2 · Σ (h_Q - h_P)² / r³ · ΔS по клеткам 60" в круге REACH
вокруг точки. Сумма - три свёртки БПФ полосами широт по 1° (ширина
клетки по долготе - на середине полосы), долгота замкнута. Поправка всегда
положительна, она прибавляется к простой аномалии Буге. Выше |MAX_LAT|
её нет - сетка градусов у полюса не плоская. Всё считается в клетке 60"
и осредняется на клетку 0.25°. Аномалия Буге - аномалия в свободном
воздухе минус простая поправка плюс поправка на рельеф, мГал.
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
RADIUS = 6371000.0  # м, средний радиус Земли для размеров клеток
REACH = 166700.0  # м, внешний радиус зон Хейфорда (зона O)
BAND = 60  # строк 60" в полосе широт
MAX_LAT = 85.0


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


def rock_equivalent(bed, surface):
    """Высота породы той же массы, метры: простая поправка, делённая на
    2πGρ породы."""
    return correction(bed, surface) / (SLAB * RHO_CRUST)


def kernel(dx, dy, reach, rows, cols):
    """Ядро ΔS / r³ на сетке свёртки (rows, cols) с началом в [0, 0]
    и отрицательными сдвигами в конце осей. Клетка точки - 0."""
    kr = int(reach // dy)
    kc = min(int(reach // dx), cols // 2 - 1)
    i = np.arange(-kr, kr + 1)[:, None]
    j = np.arange(-kc, kc + 1)[None, :]
    r = np.hypot(i * dy, j * dx)
    with np.errstate(divide="ignore"):
        k = np.where((r > 0.0) & (r <= reach), dx * dy / r ** 3, 0.0)
    out = np.zeros((rows, cols))
    out[np.ix_(i[:, 0] % rows, j[0] % cols)] = k
    return out


def terrain_correction(h, dx, dy, reach=REACH, density=RHO_CRUST):
    """Поправка на рельеф, мГал, в каждой клетке плоской сетки высот h
    (строки, столбцы), шаг dx по столбцам и dy по строкам, метры.
    Столбцы замкнуты (долгота), строки - нет, у края полосы сумма
    неполная. Линейное приближение Gρ/2 Σ (h_Q - h_P)² / r³ ΔS."""
    h = np.asarray(h, dtype=np.float64)
    rows, cols = h.shape
    pad = rows + int(reach // dy) + 1
    k = np.fft.rfft2(kernel(dx, dy, reach, pad, cols))

    def conv(values):
        return np.fft.irfft2(np.fft.rfft2(values, s=(pad, cols)) * k,
                             s=(pad, cols))[:rows]
    s0 = conv(np.ones_like(h))
    s1 = conv(h)
    s2 = conv(h * h)
    value = s2 - 2.0 * h * s1 + h * h * s0
    return np.maximum(value, 0.0) * 0.5 * G * density * MGAL


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
    x0, step, _, y0, _, _ = bed_ds.GetGeoTransform()
    assert abs(x0 + 180.0) < 1e-9 and abs(y0 - 90.0) < 1e-9, (x0, y0)
    dy = RADIUS * math.radians(step)
    over = int(REACH // dy) + 1
    slab = np.zeros_like(free_air)
    terrain = np.zeros_like(free_air)

    def read(top, count):
        bed = bed_ds.GetRasterBand(1).ReadAsArray(0, top, cols, count)
        surface = surface_ds.GetRasterBand(1).ReadAsArray(0, top, cols,
                                                          count)
        return bed, surface

    for top in range(0, rows, BAND):
        bed, surface = read(top, BAND)
        slab[top // CELL:(top + BAND) // CELL] = block_mean(
            correction(bed, surface))
        lat = 90.0 - (top + BAND / 2.0) * step
        if abs(lat) > MAX_LAT:
            continue
        start, stop = max(0, top - over), min(rows, top + BAND + over)
        bed, surface = read(start, stop - start)
        ret = rock_equivalent(bed, surface)
        dx = RADIUS * math.radians(step) * math.cos(math.radians(lat))
        tc = terrain_correction(ret, dx, dy)[top - start:top - start + BAND]
        terrain[top // CELL:(top + BAND) // CELL] = block_mean(tc)
        if top % (BAND * 10) == 0:
            print("широта", round(lat, 1), "поправка до",
                  round(float(tc.max()), 1), flush=True)
    grid = free_air - slab + terrain
    for path, values in ((out, grid),
                         (out.replace(".tif", "_tc.tif"), terrain)):
        ds = gdal.GetDriverByName("GTiff").Create(
            path, values.shape[1], values.shape[0], 1, gdal.GDT_Float32,
            options=["COMPRESS=DEFLATE"])
        ds.SetGeoTransform((-180.0, 0.25, 0.0, 90.0, 0.0, -0.25))
        ds.GetRasterBand(1).WriteArray(values.astype(np.float32))
        ds = None
    print(out, "mGal", float(np.percentile(grid, 1)),
          float(np.percentile(grid, 99)), float(grid.min()), float(grid.max()),
          "поправка на рельеф до", float(terrain.max()))


if __name__ == "__main__":
    main(*sys.argv[1:5])
