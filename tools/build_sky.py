# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Картинка неба с Млечным путём из NASA SVS Deep Star Maps 2020.

    python tools/build_sky.py milkyway_2020_8k.exr sky_2020_8k.jpg

Исходник - https://svs.gsfc.nasa.gov/4851, файл milkyway_2020_8k.exr,
8192×4096, EXR со сжатием ZIP и каналами половинной точности. Подпись
по условиям SVS: NASA/Goddard Space Flight Center Scientific
Visualization Studio. Gaia DR2: ESA/Gaia/DPAC.

EXR разбирается здесь на NumPy, GDAL из QGIS его не читает. Картинка
приводится к виду, который ждёт render/sky.py: прямое восхождение
от 0 до 360° слева направо, склонение +90° в верхней строке. Где
в исходнике нулевой час, скрипт проверяет по центру Галактики - самое
яркое место Млечного пути. Яркость сжимается степенью: небо слабое,
вся шкала JPG уходит на Млечный путь.

Скрипту нужен Qt для записи JPG. Python из QGIS находит его, если
в PATH есть apps\\Qt6\\bin и bin каталога QGIS.
"""
import struct
import sys
import zlib

import numpy as np

LINES_PER_BLOCK = 16  # сжатие ZIP в EXR - по 16 строк
GALACTIC_CENTER = (266.40, -28.94)  # прямое восхождение и склонение, °
WHITE = 99.8  # процентиль яркости, который становится белым
BLACK = 50.0  # процентиль яркости, который становится чёрным
GAMMA = 0.7  # степень сжатия яркости
QUALITY = 80  # при 85 файл 11.2 МБ, при 80 меньше 10 МБ


def read_header(data):
    """Атрибуты заголовка EXR: имя -> (тип, байты) и конец заголовка."""
    if data[:4] != b"\x76\x2f\x31\x01":
        raise ValueError("не EXR")
    pos = 8
    attrs = {}
    while data[pos] != 0:
        end = data.index(b"\0", pos)
        name = data[pos:end].decode()
        pos = end + 1
        end = data.index(b"\0", pos)
        kind = data[pos:end].decode()
        pos = end + 1
        size = struct.unpack_from("<i", data, pos)[0]
        pos += 4
        attrs[name] = (kind, data[pos:pos + size])
        pos += size
    return attrs, pos + 1


def channels(raw):
    """Имена каналов и типы: 1 - половинная точность."""
    out = []
    pos = 0
    while raw[pos] != 0:
        end = raw.index(b"\0", pos)
        name = raw[pos:end].decode()
        kind = struct.unpack_from("<i", raw, end + 1)[0]
        out.append((name, kind))
        pos = end + 1 + 16
    return out


def undo_predictor(t):
    """Обратная разность EXR: t[i] = t[i-1] + d[i] - 128 по модулю 256."""
    d = t.astype(np.int64)
    d[1:] -= 128
    return (np.cumsum(d) % 256).astype(np.uint8)


def read_exr(path):
    """Картинка EXR со сжатием ZIP в массив (высота, ширина, 3) float32,
    каналы R, G, B."""
    with open(path, "rb") as f:
        data = f.read()
    attrs, pos = read_header(data)
    if attrs["compression"][1][0] != 3:
        raise ValueError("сжатие не ZIP")
    names = channels(attrs["channels"][1])
    if any(kind != 1 for _, kind in names):
        raise ValueError("каналы не половинной точности")
    x0, y0, x1, y1 = struct.unpack("<4i", attrs["dataWindow"][1])
    width, height = x1 - x0 + 1, y1 - y0 + 1
    blocks = -(-height // LINES_PER_BLOCK)
    offsets = struct.unpack_from("<%dQ" % blocks, data, pos)
    image = np.empty((height, len(names), width), dtype=np.float16)
    for offset in offsets:
        y, size = struct.unpack_from("<2i", data, offset)
        lines = min(LINES_PER_BLOCK, y1 + 1 - y)
        raw_size = lines * len(names) * width * 2
        t = np.frombuffer(zlib.decompress(
            data[offset + 8:offset + 8 + size]), dtype=np.uint8)
        if len(t) != raw_size:
            raise ValueError("размер блока")
        t = undo_predictor(t)
        half = (raw_size + 1) // 2
        raw = np.empty(raw_size, dtype=np.uint8)
        raw[0::2] = t[:half]
        raw[1::2] = t[half:]
        row = y - y0
        image[row:row + lines] = raw.view("<f2").reshape(
            lines, len(names), width)
    order = [[n for n, _ in names].index(c) for c in "RGB"]
    return np.ascontiguousarray(
        image[:, order, :].transpose(0, 2, 1)).astype(np.float32)


def brightest_column(rgb, dec):
    """Столбец, где в полосе склонения dec ярче всего, сглажено."""
    height, width = rgb.shape[:2]
    row = int((90.0 - dec) / 180.0 * height)
    band = rgb[max(0, row - height // 60):row + height // 60].mean(axis=(0, 2))
    kernel = np.ones(width // 90) / (width // 90)
    smooth = np.convolve(np.concatenate((band, band[:len(kernel)])),
                         kernel, mode="same")[:width]
    return int(np.argmax(smooth))


def canonical(rgb):
    """Прямое восхождение 0-360° слева направо. У SVS нулевой час
    в середине картинки, восхождение растёт влево, как небо изнутри.
    Сверено 29 сентября 2026 года по приметам LANDMARKS."""
    return np.roll(rgb[:, ::-1], rgb.shape[1] // 2, axis=1)


# Места Млечного пути: название, склонение, прямое восхождение, °.
# Самое яркое место полосы склонения лежит в пределах TOLERANCE.
LANDMARKS = (("центр Галактики", GALACTIC_CENTER[1], GALACTIC_CENTER[0]),
             ("Лебедь", 40.0, 305.0), ("Кассиопея", 62.0, 12.9),
             ("Южный Крест", -60.0, 170.0))
# Приметы грубые, полоса Млечного пути широкая. Обратная ориентация
# даёт промахи в десятки градусов, этого допуска хватает.
TOLERANCE = 20.0


def check(rgb):
    """Приметы на своих местах, иначе ошибка."""
    width = rgb.shape[1]
    for name, dec, ra in LANDMARKS:
        seen = brightest_column(rgb, dec) / width * 360.0
        miss = abs((seen - ra + 180.0) % 360.0 - 180.0)
        print("%s: %.1f° вместо %.1f°" % (name, seen, ra))
        if miss > TOLERANCE:
            raise ValueError("%s не на месте" % name)


def tone(rgb):
    """Яркость HDR в 0-255 со сжатием степенью. Половина неба
    ниже точки чёрного, там только шум и свечение, оно становится
    чёрным и не занимает места в JPG."""
    lum = rgb.mean(axis=2)
    black = float(np.percentile(lum, BLACK))
    white = float(np.percentile(lum, WHITE))
    out = np.clip((rgb - black) / (white - black), 0.0, 1.0) ** GAMMA
    return np.rint(out * 255.0).astype(np.uint8), white


def save_jpg(rgb8, path):
    from PyQt6.QtGui import QImage
    height, width = rgb8.shape[:2]
    data = np.ascontiguousarray(rgb8)
    image = QImage(data.data, width, height, width * 3,
                   QImage.Format.Format_RGB888)
    if not image.save(path, "JPG", QUALITY):
        raise OSError("JPG не записан")


def main(source, target):
    rgb = canonical(read_exr(source))
    print("картинка %d×%d" % (rgb.shape[1], rgb.shape[0]))
    check(rgb)
    rgb8, white = tone(rgb)
    save_jpg(rgb8, target)
    print("белый %.3g, записан %s" % (white, target))
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
