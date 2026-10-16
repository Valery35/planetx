# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сейсмическая томография мантии на гранях разреза Земли. Без Qt.

Просьба автора от 16 октября 2026 года после списка геофизики. Модель
SEISGLOB2 (Durand и соавторы 2017, GJI 211, 1628,
doi:10.1093/gji/ggx405) - отклонение скорости поперечных волн dVs от
PREM в процентах, сетка 1°, 57 глубин от 50 до 2850 км через 50 км.
Медленная мантия (красная) - горячее вещество, плюмы под Исландией
и Гавайями, быстрая (синяя) - холодные погрузившиеся плиты. Модель
лежит в каталоге EarthScope EMC, лицензии у неё нет, только просьба
ссылаться, поэтому модуль её не распространяет: файл netCDF (URL)
скачивается при включении, разбор - в рабочем потоке, итог - файл
профиля (save, load).

Модуль Qt не знает.
"""
from collections import namedtuple

import numpy as np

URL = ("https://data.earthscope.org/archive/seismology/products/emc/"
       "netcdf/SEISGLOB2_percent.r0.0-n4c.nc")
ATTRIBUTION = ("Tomography: SEISGLOB2, Durand et al. 2017, EarthScope EMC",
               "https://doi.org/10.17611/DP/EMCSEISGLOB2")
CMB = 2891.0  # км, граница ядра и мантии
# Раскраска dVs, %: медленнее PREM - красная, быстрее - синяя. Пределы -
# выбор помощника, утверждает автор.
STOPS = ((-2.0, (180, 25, 25)), (-0.8, (240, 130, 80)),
         (0.0, (245, 242, 235)), (0.8, (120, 165, 230)),
         (2.0, (25, 55, 165)))

Tomo = namedtuple("Tomo", "depths lats lons dvs")
Tomo.__doc__ = """Модель: depths (K,) км по возрастанию, lats (R,) по
возрастанию, lons (C,) от 0 с равным шагом, dvs (K, R, C) float32, %,
NaN - нет данных."""


def make(depths, lats, lons, dvs):
    """Tomo из массивов файла: широты по возрастанию, долготы 0-360."""
    depths = np.asarray(depths, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64) % 360.0
    dvs = np.asarray(dvs, dtype=np.float32)
    if dvs.shape != (len(depths), len(lats), len(lons)):
        raise ValueError("tomography grid {} for {} {} {}".format(
            dvs.shape, len(depths), len(lats), len(lons)))
    dvs = np.where(np.abs(dvs) > 1.0e4, np.nan, dvs)
    if lats[0] > lats[-1]:
        lats, dvs = lats[::-1], dvs[:, ::-1]
    order = np.argsort(lons)
    return Tomo(depths, lats, lons[order], dvs[:, :, order])


def sample(tomo, lats, lons, depth):
    """dVs, %, в точках (n) на глубине depth км: билинейно по широте
    и долготе, линейно по глубине. За краями сетки - край."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64) % 360.0
    d = np.clip(depth, tomo.depths[0], tomo.depths[-1])
    k = int(np.clip(np.searchsorted(tomo.depths, d) - 1, 0,
                    len(tomo.depths) - 2))
    span = tomo.depths[k + 1] - tomo.depths[k]
    w = 0.0 if span <= 0 else (d - tomo.depths[k]) / span
    step = tomo.lons[1] - tomo.lons[0]
    fc = (lons - tomo.lons[0]) / step
    c0 = np.floor(fc).astype(int) % len(tomo.lons)
    c1 = (c0 + 1) % len(tomo.lons)
    dc = fc - np.floor(fc)
    fr = np.interp(lats, tomo.lats, np.arange(len(tomo.lats)))
    r0 = np.clip(np.floor(fr).astype(int), 0, len(tomo.lats) - 2)
    dr = np.clip(fr - r0, 0.0, 1.0)

    def layer(grid):
        a = grid[r0, c0]
        b = grid[r0, c1]
        c = grid[r0 + 1, c0]
        e = grid[r0 + 1, c1]
        return (a * (1 - dc) * (1 - dr) + b * dc * (1 - dr)
                + c * (1 - dc) * dr + e * dc * dr)
    return layer(tomo.dvs[k]) * (1.0 - w) + layer(tomo.dvs[k + 1]) * w


def colors(dvs):
    """dVs, %, в RGB uint8 (n, 3), NaN - цвет нуля."""
    dvs = np.nan_to_num(np.asarray(dvs, dtype=np.float64), nan=0.0)
    at = [s for s, _ in STOPS]
    out = np.zeros(dvs.shape + (3,), np.uint8)
    for k in range(3):
        out[..., k] = np.round(np.interp(dvs, at, [c[k] for _, c in STOPS]))
    return out


def rows(tomo):
    """Глубины рядов сетки грани: глубины модели и низ мантии."""
    depths = [d for d in tomo.depths if 0.0 < d < CMB]
    return np.array(depths + [CMB], dtype=np.float64)


def save(tomo, path):
    np.savez_compressed(path, depths=tomo.depths, lats=tomo.lats,
                        lons=tomo.lons, dvs=tomo.dvs.astype(np.float16))


def load(path):
    with np.load(path, allow_pickle=False) as data:
        return Tomo(data["depths"], data["lats"], data["lons"],
                    data["dvs"].astype(np.float32))
