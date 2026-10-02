# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Собирает файлы зон Slab2 для хранилища planetx-terrain.

    $PY tools/build_slabs.py путь/к/Slab2Distribute_Mar2018.tar.gz \\
        [папка planetx-terrain]

Шаг 3 плана «сверху вниз», 2 октября 2026 года. Slab2 (Hayes, 2018,
doi:10.5066/F7PV6JNV) - погружающиеся плиты 27 зон субдукции, данные
USGS в общественном достоянии США. Из архива берутся сетки глубины
(dep), толщины (thk) и падения (dip) - NetCDF, шаг 0.05°, глубина в км
со знаком минус, долготы 0-360° - и контуры обрезки *_slab2_clp_*.csv.
Условие USGS - вне контура модель не применять, узлы вне контура
пустые.

Пишет slab2/<код>.npz в хранилище: долгота и широта северо-западного
узла и шаг (origin), глубина и толщина в десятых долях км int16
(пусто - EMPTY), падение в градусах uint8. Шаг 0.1° - каждый второй
узел. Указатель зон с рамками - planetx/data/slab2_index.json, он
входит в модуль: по нему модуль решает, какую зону просить, когда
разрез её касается (решение автора от 2 октября 2026 года).
"""
import io
import json
import os
import re
import sys
import tarfile

import numpy as np
from osgeo import gdal

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))

from subsurface import inside  # noqa: E402

gdal.UseExceptions()
INDEX = os.path.join(ROOT, "planetx", "data", "slab2_index.json")
TERRAIN = os.path.join(os.path.dirname(ROOT), "planetx-terrain")
THIN = 2  # каждый второй узел: 0.05° -> 0.1°
EMPTY = -32768
GRID = re.compile(r"/([a-z]{3})_slab2_(dep|thk|dip)_[0-9.]+\.grd$")
CLIP = re.compile(r"/([a-z]{3})_slab2_clp_[0-9.]+\.csv$")


def read_grid(data, name):
    """Сетка из байтов NetCDF: (lon0, lat0, step, значения с севера)."""
    path = "/vsimem/" + name
    gdal.FileFromMemBuffer(path, data)
    try:
        ds = gdal.Open(path)
        x0, dx, _, y0, _, dy = ds.GetGeoTransform()
        z = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    finally:
        gdal.Unlink(path)
    # Узел - середина клетки, GDAL даёт угол.
    lon0 = x0 + dx / 2.0
    lat0 = y0 + dy / 2.0
    if dy > 0:
        z = z[::-1]
        lat0 = y0 + dy * (z.shape[0] - 0.5)
    return lon0, lat0, abs(dx), z


def read_clip(text):
    """Контур обрезки: широты и долготы, долготы как в сетке."""
    lons, lats = [], []
    for line in text.splitlines():
        parts = line.replace(",", " ").split()
        if len(parts) >= 2:
            lons.append(float(parts[0]))
            lats.append(float(parts[1]))
    return np.array(lats), np.array(lons)


def pack(values, scale, dtype, empty):
    return np.where(np.isfinite(values), np.rint(values * scale),
                    empty).astype(dtype)


def build(archive, terrain):
    grids, clips = {}, {}
    with tarfile.open(archive) as tar:
        for member in tar.getmembers():
            grid = GRID.search(member.name)
            clip = CLIP.search(member.name)
            if grid:
                grids[grid.groups()] = read_grid(
                    tar.extractfile(member).read(),
                    member.name.split("/")[-1])
            elif clip:
                clips[clip.group(1)] = read_clip(
                    tar.extractfile(member).read().decode("ascii"))
    folder = os.path.join(terrain, "slab2")
    os.makedirs(folder, exist_ok=True)
    index = {}
    for code in sorted({c for c, _ in grids}):
        lon0, lat0, step, raw = grids[(code, "dep")]
        depth = -raw[::THIN, ::THIN]
        thick = grids[(code, "thk")][3][::THIN, ::THIN]
        dip = grids[(code, "dip")][3][::THIN, ::THIN]
        rows, cols = depth.shape
        lats = lat0 - np.arange(rows) * step * THIN
        lons = lon0 + np.arange(cols) * step * THIN
        glat, glon = np.meshgrid(lats, lons, indexing="ij")
        if code in clips:
            ring_lat, ring_lon = clips[code]
            keep = inside(glat.ravel(), glon.ravel(),
                          list(zip(ring_lat, ring_lon))).reshape(rows, cols)
            depth = np.where(keep, depth, np.nan)
        thick = np.where(np.isfinite(depth), thick, np.nan)
        dip = np.where(np.isfinite(depth) & np.isfinite(dip), dip, 0.0)
        west = lon0 - 360.0 if lon0 > 180.0 else lon0
        buffer = io.BytesIO()
        np.savez_compressed(
            buffer, origin=np.array([west, lat0, step * THIN]),
            depth=pack(depth, 10.0, np.int16, EMPTY),
            thickness=pack(thick, 10.0, np.int16, EMPTY),
            dip=np.clip(np.rint(dip), 0, 90).astype(np.uint8))
        data = buffer.getvalue()
        with open(os.path.join(folder, code + ".npz"), "wb") as fh:
            fh.write(data)
        filled = np.isfinite(depth)
        wrap = (glon[filled] + 180.0) % 360.0 - 180.0
        index[code] = {
            "south": round(float(glat[filled].min()), 2),
            "north": round(float(glat[filled].max()), 2),
            # Долготы рамки без перехода через линию перемены дат: запад
            # может быть больше востока, если зона её пересекает.
            "west": round(float((glon[filled].min() + 180.0) % 360.0
                                - 180.0), 2),
            "east": round(float((glon[filled].max() + 180.0) % 360.0
                                - 180.0), 2),
            "bytes": len(data)}
        print(code, rows, cols, "узлов", int(filled.sum()), "байт", len(data),
              "долготы", round(float(wrap.min()), 1),
              round(float(wrap.max()), 1))
    with open(INDEX, "w", encoding="utf-8") as fh:
        json.dump(index, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print(INDEX, len(index), "зон")


if __name__ == "__main__":
    build(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else TERRAIN)
