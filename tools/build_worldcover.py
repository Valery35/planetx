# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Мелкие уровни покрытия земель ESA WorldCover для planetx-terrain.

    python tools/build_worldcover.py fetch C:/Dev/data/worldcover
    python tools/build_worldcover.py tiles C:/Dev/data/worldcover \
        C:/Dev/planetx-terrain

Раскрашенные тайлы мозаики Planetary Computer (core/tilemaps.py,
WORLDCOVER) есть только с уровня 6, мельче служба отвечает 204. Шаг
fetch скачивает все 4096 тайлов уровня 6 в папку, по 8 запросов
сразу, готовые файлы не скачивает снова. Шаг tiles собирает из них
уровни 5-0 в planetx-terrain/worldcover: тайл - мозаика четырёх детей,
уменьшенная вдвое ближайшим соседом (классы не смешиваются). Пустые
тайлы тоже пишутся, прозрачным PNG.
"""
import concurrent.futures
import os
import sys
import time
import urllib.request

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "planetx", "core"))
import tilemaps  # noqa: E402

LEVEL = tilemaps.WORLDCOVER_SPLIT  # первый уровень службы
SIZE = 256
AGENT = "PlanetX/build (+https://github.com/Valery35/planetx)"


def fetch(folder):
    os.makedirs(folder, exist_ok=True)
    n = 1 << LEVEL
    jobs = [(x, y) for x in range(n) for y in range(n)]

    def one(job):
        x, y = job
        path = os.path.join(folder, "%d_%d.png" % (x, y))
        if os.path.exists(path):
            return 0
        url = tilemaps.WORLDCOVER_URL.format(z=LEVEL, x=x, y=y)
        for attempt in range(4):
            try:
                request = urllib.request.Request(
                    url, headers={"User-Agent": AGENT})
                with urllib.request.urlopen(request, timeout=120) as answer:
                    data = answer.read()
                break
            except OSError as error:
                if attempt == 3:
                    print("fail", x, y, error, flush=True)
                    return 0
                time.sleep(3 * (attempt + 1))
        with open(path + ".part", "wb") as out:
            out.write(data)
        os.replace(path + ".part", path)
        return 1

    done = 0
    with concurrent.futures.ThreadPoolExecutor(8) as pool:
        for count in pool.map(one, jobs):
            done += count
            if done and done % 200 == 0:
                print("fetched", done, flush=True)
    print("fetched", done, flush=True)


def _read(path):
    from osgeo import gdal
    data = open(path, "rb").read() if os.path.exists(path) else b""
    if not data:
        return np.zeros((SIZE, SIZE, 4), np.uint8)
    gdal.FileFromMemBuffer("/vsimem/wc.png", data)
    ds = gdal.Open("/vsimem/wc.png")
    bands = ds.ReadAsArray()
    ds = None
    gdal.Unlink("/vsimem/wc.png")
    if bands.shape[0] == 3:
        alpha = np.full(bands.shape[1:], 255, np.uint8)
        bands = np.concatenate([bands, alpha[None]], axis=0)
    return np.ascontiguousarray(np.moveaxis(bands, 0, -1))


def _write(path, picture):
    from osgeo import gdal
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mem = gdal.GetDriverByName("MEM").Create("", SIZE, SIZE, 4,
                                             gdal.GDT_Byte)
    for band in range(4):
        mem.GetRasterBand(band + 1).WriteArray(picture[..., band])
    gdal.GetDriverByName("PNG").CreateCopy(path, mem,
                                           options=["ZLEVEL=9"])


def tiles(folder, terrain):
    from osgeo import gdal
    gdal.UseExceptions()
    level = {}
    n = 1 << LEVEL
    for x in range(n):
        for y in range(n):
            level[(x, y)] = _read(os.path.join(folder, "%d_%d.png" % (x, y)))
    out_dir = os.path.join(terrain, tilemaps.WORLDCOVER_FOLDER)
    for z in range(LEVEL - 1, -1, -1):
        upper = {}
        for x in range(1 << z):
            for y in range(1 << z):
                block = np.zeros((2 * SIZE, 2 * SIZE, 4), np.uint8)
                for dx in (0, 1):
                    for dy in (0, 1):
                        block[dy * SIZE:(dy + 1) * SIZE,
                              dx * SIZE:(dx + 1) * SIZE] = \
                            level[(2 * x + dx, 2 * y + dy)]
                picture = np.ascontiguousarray(block[::2, ::2])
                upper[(x, y)] = picture
                _write(os.path.join(out_dir, str(z), str(x), "%d.png" % y),
                       picture)
        level = upper
        print("level", z, "tiles", len(upper), flush=True)


if __name__ == "__main__":
    if sys.argv[1] == "fetch":
        fetch(sys.argv[2])
    else:
        tiles(sys.argv[2], sys.argv[3])
