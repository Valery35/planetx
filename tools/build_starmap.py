# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Тайлы HiPS карты неба NASA SVS Deep Star Maps 2020 для planetx-terrain.

    python tools/build_starmap.py starmap_2020_64k.exr <папка вывода>

Исходник - https://svs.gsfc.nasa.gov/4851, файл starmap_2020_64k.exr,
65536×32768, звёзды Gaia DR2 и Hipparcos/Tycho с Млечным путём. Подпись
по условиям SVS: NASA/Goddard Space Flight Center Scientific
Visualization Studio, Gaia DR2: ESA/Gaia/DPAC. Решение автора от
24 октября 2026 года - вид неба при приближении из этой карты, DSS
только совсем вблизи.

Файл 4 ГБ целиком в память не входит. Первый проход читает блоки EXR
по одному, второй пишет яркость 0-255 в файл на диске (memmap, 6.4 ГБ
рядом с выводом). Яркость - как у картинки Млечного пути
(tools/build_sky.py) с тем же порогом и усилением, что ставит шейдер
render/sky.py, поэтому тайлы рисуются как есть и переход с картинки
на тайлы без скачка яркости. Тайлы порядка TOP - выборка из полной
карты, мельче - среднее четырёх детей, Allsky.jpg порядка 3 - тайлы
по 64 пикселя в ALLSKY_COLUMNS столбцов (core/hips.py).

Скрипту нужен Qt для записи JPG, как build_sky.py.
"""
import math
import os
import struct
import sys
import zlib

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "planetx", "core"))

import build_sky  # noqa: E402
import hips  # noqa: E402
import stars  # noqa: E402

TOP = 4  # наибольший порядок: пиксель 25.8″ при 19.8″ исходника
QUALITY = 85
SAMPLE_BLOCKS = 16  # каждый такой блок - в выборку яркости
SAMPLE_COLUMNS = 4


def blocks(path):
    """Блоки EXR по одному: (первая строка, массив (строки, 3, ширина)
    float32 каналов R, G, B), и размеры картинки."""
    with open(path, "rb") as f:
        head = f.read(1 << 16)
        attrs, pos = build_sky.read_header(head)
        if attrs["compression"][1][0] != 3:
            raise ValueError("сжатие не ZIP")
        names = build_sky.channels(attrs["channels"][1])
        x0, y0, x1, y1 = struct.unpack("<4i", attrs["dataWindow"][1])
        width, height = x1 - x0 + 1, y1 - y0 + 1
        count = -(-height // build_sky.LINES_PER_BLOCK)
        f.seek(pos)
        offsets = struct.unpack("<%dQ" % count, f.read(8 * count))
        order = [[n for n, _ in names].index(c) for c in "RGB"]

        def read(index):
            f.seek(offsets[index])
            y, size = struct.unpack("<2i", f.read(8))
            lines = min(build_sky.LINES_PER_BLOCK, y1 + 1 - y)
            raw_size = lines * len(names) * width * 2
            t = np.frombuffer(zlib.decompress(f.read(size)), dtype=np.uint8)
            if len(t) != raw_size:
                raise ValueError("размер блока")
            t = build_sky.undo_predictor(t)
            half = (raw_size + 1) // 2
            raw = np.empty(raw_size, dtype=np.uint8)
            raw[0::2] = t[:half]
            raw[1::2] = t[half:]
            block = raw.view("<f2").reshape(lines, len(names), width)
            return y - y0, block[:, order, :].astype(np.float32)

        yield (width, height, count)
        for index in range(count):
            yield read(index)


def tone_levels(path):
    """Точки чёрного и белого по выборке блоков, как build_sky.tone."""
    gen = blocks(path)
    width, height, count = next(gen)
    sample = []
    for index, (row, block) in enumerate(gen):
        if index % SAMPLE_BLOCKS == 0:
            sample.append(block.mean(axis=1)[:, ::SAMPLE_COLUMNS].ravel())
    lum = np.concatenate(sample)
    return (float(np.percentile(lum, build_sky.BLACK)),
            float(np.percentile(lum, build_sky.WHITE)))


def shade(rgb, black, white):
    """Яркость 0-1 как у картинки Млечного пути после шейдера неба."""
    jpg = np.clip((rgb - black) / (white - black), 0.0, 1.0) ** build_sky.GAMMA
    return np.clip((jpg - stars.SKY_FLOOR) / (1.0 - stars.SKY_FLOOR), 0.0,
                   1.0) * stars.SKY_GAIN


def write_map(path, target, black, white):
    """Карта 0-255 (высота, ширина, 3) в файл target, строки исходника."""
    gen = blocks(path)
    width, height, count = next(gen)
    image = np.lib.format.open_memmap(target, mode="w+", dtype=np.uint8,
                                      shape=(height, width, 3))
    for index, (row, block) in enumerate(gen):
        rgb = block.transpose(0, 2, 1)
        image[row:row + len(rgb)] = np.rint(
            shade(rgb, black, white) * 255.0).astype(np.uint8)
        if index % 256 == 0:
            print("блок %d из %d" % (index, count), flush=True)
    image.flush()
    return image


def source_xy(dirs, width, height):
    """Столбец и строка исходника SVS для направлений (..., 3).
    У SVS нулевой час в середине, восхождение растёт влево
    (build_sky.canonical)."""
    ra = np.degrees(np.arctan2(dirs[..., 1], dirs[..., 0])) % 360.0
    col = ra / 360.0 * width - 0.5
    src = (width - 1) - np.mod(col - width // 2, width)
    row = np.arccos(np.clip(dirs[..., 2], -1.0, 1.0)) / math.pi * height \
        - 0.5
    return src, np.clip(row, 0.0, height - 1.0)


def sample(image, dirs):
    """Билинейная выборка карты по направлениям, uint8 (..., 3)."""
    height, width = image.shape[:2]
    x, y = source_xy(dirs, width, height)
    x0 = np.floor(x).astype(np.int64)
    y0 = np.floor(y).astype(np.int64)
    fx = (x - x0)[..., None]
    fy = (y - y0)[..., None]
    x0 %= width
    x1 = (x0 + 1) % width
    y1 = np.minimum(y0 + 1, height - 1)
    out = (image[y0, x0] * (1 - fx) * (1 - fy) + image[y0, x1] * fx
           * (1 - fy) + image[y1, x0] * (1 - fx) * fy
           + image[y1, x1] * fx * fy)
    return np.rint(out).astype(np.uint8)


def tile_dirs(order, ipix):
    """Направления середин пикселей тайла, (512, 512, 3), ряд сверху."""
    face, ix, iy = hips.nest_xyf(order, ipix)
    side = 1 << order
    t = np.arange(hips.TILE) + 0.5
    col, row = np.meshgrid(t, t)
    fx, fy = hips.pixel_face(col, row)
    return hips.face_directions(int(face), (int(ix) + fx) / side,
                                (int(iy) + fy) / side)


def tile_path(out, order, ipix):
    folder = os.path.join(out, "Norder%d" % order,
                          "Dir%d" % (ipix // 10000 * 10000))
    os.makedirs(folder, exist_ok=True)
    return os.path.join(folder, "Npix%d.jpg" % ipix)


def save_jpg(rgb8, path):
    build_sky.QUALITY = QUALITY
    build_sky.save_jpg(rgb8, path)


def parent(children):
    """Тайл предка из четырёх детей: ребёнок k - ряды (k & 1),
    столбцы (k >> 1), как доли x, y грани (core.hips.pixel_face)."""
    half = hips.TILE // 2
    out = np.empty((hips.TILE, hips.TILE, 3), dtype=np.uint8)
    for k, child in enumerate(children):
        small = child.reshape(half, 2, half, 2, 3).mean(axis=(1, 3))
        r, c = (k & 1) * half, (k >> 1) * half
        out[r:r + half, c:c + half] = np.rint(small).astype(np.uint8)
    return out


def main(source, out, keep_map=False):
    os.makedirs(out, exist_ok=True)
    map_path = os.path.join(out, "..", "starmap_u8.npy")
    if os.path.exists(map_path):
        image = np.load(map_path, mmap_mode="r")
    else:
        black, white = tone_levels(source)
        print("чёрный %.4g, белый %.4g" % (black, white), flush=True)
        image = write_map(source, map_path, black, white)
    tiles = {}
    for ipix in range(12 * 4 ** TOP):
        rgb = sample(image, tile_dirs(TOP, ipix))
        save_jpg(rgb, tile_path(out, TOP, ipix))
        tiles[ipix] = rgb
        if ipix % 256 == 0:
            print("порядок %d: %d" % (TOP, ipix), flush=True)
    for order in range(TOP - 1, -1, -1):
        upper = {}
        for ipix in range(12 * 4 ** order):
            rgb = parent([tiles[ipix * 4 + k] for k in range(4)])
            save_jpg(rgb, tile_path(out, order, ipix))
            upper[ipix] = rgb
        tiles = upper
        if order == hips.ALLSKY_ORDER:
            allsky(tiles, out)
    with open(os.path.join(out, "properties"), "w", encoding="utf-8") as f:
        f.write("obs_title = NASA SVS Deep Star Maps 2020\n"
                "obs_copyright = NASA/Goddard Space Flight Center "
                "Scientific Visualization Studio. Gaia DR2: ESA/Gaia/DPAC\n"
                "hips_order = %d\nhips_tile_width = %d\n"
                "hips_tile_format = jpeg\nhips_frame = equatorial\n"
                % (TOP, hips.TILE))
    return 0


def allsky(tiles, out):
    """Allsky.jpg порядка 3: тайлы по 64 пикселя в ALLSKY_COLUMNS
    столбцов, как у служб CDS."""
    cell = hips.TILE // 8
    count = len(tiles)
    rows = -(-count // hips.ALLSKY_COLUMNS)
    sheet = np.zeros((rows * cell, hips.ALLSKY_COLUMNS * cell, 3),
                     dtype=np.uint8)
    for ipix, rgb in tiles.items():
        small = rgb.reshape(cell, 8, cell, 8, 3).mean(axis=(1, 3))
        r = ipix // hips.ALLSKY_COLUMNS * cell
        c = ipix % hips.ALLSKY_COLUMNS * cell
        sheet[r:r + cell, c:c + cell] = np.rint(small).astype(np.uint8)
    save_jpg(sheet, os.path.join(out, "Norder%d" % hips.ALLSKY_ORDER,
                                 "Allsky.jpg"))


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
