# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетка аномалии силы тяжести в свободном воздухе по модели XGM2019e.

    python-qgis.bat tools/build_gravity.py XGM2019e_2159.zip ВЫХОД.tif

Модель XGM2019e (Zingerle и соавторы 2020, ICGEM, CC BY 4.0,
doi:10.5880/icgem.2019.007) - коэффициенты Стокса до степени 2190.
Сетки аномалий с понятной разрешительной лицензией и без входа нет:
WGM2012 BGI запрещает распространение, у морской сетки Sandwell
условия не найдены. Поэтому аномалия считается здесь.

Аномалия в свободном воздухе в сферическом приближении на сфере
радиуса модели:
Δg(φ, λ) = GM / a² Σ_{n=2}^{N} (n - 1) Σ_m (ΔC̄nm cos mλ + S̄nm sin mλ)
P̄nm(sin φ), где ΔC̄ - коэффициенты без нормального поля GRS80 (чётные
зональные до степени 10). Степень N - DEGREE, сетка - середины клеток
STEP градусов, сумма по m - обратным БПФ по долготе. Функции Лежандра
полностью нормированы, рекурсия по столбцам массивами по широтам.
Сферическое приближение даёт ошибку порядка мГал, для показа она
не видна. Итог - GeoTIFF float32 в мГал для tools/build_field.py.
"""
import io
import math
import sys
import zipfile

import numpy as np

DEGREE = 719
STEP = 0.25
# GRS80.
GRS_GM = 3.986005e14
GRS_A = 6378137.0
GRS_J2 = 1.08263e-3
GRS_E2 = 0.00669438002290


def read_gfc(path, nmax):
    """GM, a и коэффициенты C, S (nmax + 1, nmax + 1) из файла gfc
    в архиве ZIP или как есть."""
    if path.lower().endswith(".zip"):
        archive = zipfile.ZipFile(path)
        name = next(n for n in archive.namelist()
                    if n.lower().endswith(".gfc"))
        stream = io.TextIOWrapper(archive.open(name), encoding="ascii",
                                  errors="replace")
    else:
        stream = open(path, encoding="ascii", errors="replace")
    gm = radius = None
    c = np.zeros((nmax + 1, nmax + 1))
    s = np.zeros((nmax + 1, nmax + 1))
    body = False
    with stream:
        for line in stream:
            parts = line.split()
            if not parts:
                continue
            if not body:
                key = parts[0].lower()
                if key == "earth_gravity_constant":
                    gm = float(parts[1].replace("D", "E"))
                elif key == "radius":
                    radius = float(parts[1].replace("D", "E"))
                elif key == "end_of_head":
                    body = True
                continue
            if parts[0] != "gfc":
                continue
            n, m = int(parts[1]), int(parts[2])
            if n > nmax:
                continue
            c[n, m] = float(parts[3].replace("D", "E"))
            s[n, m] = float(parts[4].replace("D", "E"))
    return gm, radius, c, s


def normal_zonals(gm, radius, nmax=10):
    """Полностью нормированные C̄_{2k,0} нормального поля GRS80 в масштабе
    модели (GM, a)."""
    out = {}
    e2 = GRS_E2
    for k in range(1, nmax // 2 + 1):
        j = (-1) ** (k + 1) * 3.0 * e2 ** k / ((2 * k + 1) * (2 * k + 3)) \
            * (1.0 - k + 5.0 * k * GRS_J2 / e2)
        c = -j / math.sqrt(4 * k + 1)
        out[2 * k] = c * (GRS_GM / gm) * (GRS_A / radius) ** (2 * k)
    return out


def synthesis(gm, radius, c, s, nmax, step):
    """Аномалия, мГал, на сетке середин клеток: строки с севера,
    долготы от -180 + step / 2."""
    lats = 90.0 - step / 2.0 - np.arange(int(round(180.0 / step))) * step
    cols = int(round(360.0 / step))
    t = np.sin(np.radians(lats))  # cos кошироты
    u = np.cos(np.radians(lats))  # sin кошироты
    weight = np.array([n - 1.0 if n >= 2 else 0.0 for n in range(nmax + 1)])
    a_m = np.zeros((len(lats), nmax + 1))
    b_m = np.zeros((len(lats), nmax + 1))
    # P̄mm по диагонали, затем столбец m рекурсией по n.
    pmm = np.ones_like(t)
    for m in range(nmax + 1):
        if m == 1:
            pmm = math.sqrt(3.0) * u * pmm
        elif m > 1:
            pmm = math.sqrt((2.0 * m + 1.0) / (2.0 * m)) * u * pmm
        p_prev = np.zeros_like(t)
        p = pmm.copy()
        acc_c = weight[m] * c[m, m] * p
        acc_s = weight[m] * s[m, m] * p
        for n in range(m + 1, nmax + 1):
            a = math.sqrt((2.0 * n - 1.0) * (2.0 * n + 1.0)
                          / ((n - m) * (n + m)))
            b = math.sqrt((2.0 * n + 1.0) * (n + m - 1.0) * (n - m - 1.0)
                          / ((n - m) * (n + m) * (2.0 * n - 3.0)))
            p, p_prev = a * t * p - b * p_prev, p
            acc_c += weight[n] * c[n, m] * p
            acc_s += weight[n] * s[n, m] * p
        a_m[:, m] = acc_c
        b_m[:, m] = acc_s
    # Σ_m (A cos mλ + B sin mλ) на долготах λ_j = λ0 + j·Δ - через БПФ.
    lam0 = math.radians(-180.0 + step / 2.0)
    shift = np.exp(1j * np.arange(nmax + 1) * lam0)
    spectrum = np.zeros((len(lats), cols // 2 + 1), dtype=np.complex128)
    # irfft удваивает действительную часть при m > 0, поэтому половина.
    spectrum[:, :nmax + 1] = (a_m - 1j * b_m) * shift / 2.0
    spectrum[:, 0] = a_m[:, 0]
    grid = np.fft.irfft(spectrum, n=cols, axis=1) * cols
    return lats, grid * gm / radius ** 2 * 1.0e5


def main(source, out):
    gm, radius, c, s = read_gfc(source, DEGREE)
    for n, value in normal_zonals(gm, radius).items():
        c[n, 0] -= value
    from osgeo import gdal
    _, grid = synthesis(gm, radius, c, s, DEGREE, STEP)
    rows, cols = grid.shape
    gdal.UseExceptions()
    ds = gdal.GetDriverByName("GTiff").Create(out, cols, rows, 1,
                                              gdal.GDT_Float32,
                                              options=["COMPRESS=DEFLATE"])
    ds.SetGeoTransform((-180.0, STEP, 0.0, 90.0, 0.0, -STEP))
    ds.GetRasterBand(1).WriteArray(grid.astype(np.float32))
    ds = None
    print(out, "mGal", float(np.percentile(grid, 1)),
          float(np.percentile(grid, 99)), float(grid.min()), float(grid.max()))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
