# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""
Тайлы высот Марса и Луны в разметке Terrarium из сеток PDS.

    $PY tools/build_body_terrain.py mars megt90n000fb.lbl папка 10
    $PY tools/build_body_terrain.py moon ldem_64.lbl папка 20

Последнее число - шаг округления высот в метрах.

Сетки высот:
- Марс - MOLA MEGDR, 32 точки на градус, высоты над ареоидом, файлы
  megt90n000fb.lbl и .img из PDS Geosciences Node,
  https://pds-geosciences.wustl.edu/mgs/mgs-m-mola-5-megdr-l3-v1/
- Луна - LOLA GDR, 64 точки на градус, высоты над сферой 1737.4 км,
  файлы ldem_64.lbl и .img оттуда же, lro-l-lola-3-rdr-v1.

Данные NASA, условия - общественное достояние, источник указывается.
Сетка - равнопромежуточная, север вверху, долгота от западного края
файла на восток. Тайл уровня z - картинка 256×256 в сетке Web Mercator,
высота пикселя - в его центре, билинейно из сетки. Высота округляется
до STEP метров и пишется как Terrarium: R·256 + G + B/256 - 32768,
B = 0. Шаг выбран по замеру 1 октября 2026 года. У Марса на 40 тайлах
уровня 5 шаг 1 м дал 52 КБ на тайл, шаг 10 м - 26 КБ, все уровни
0-5 с шагом 10 м - 45 МБ. У Луны с шагом 10 м 75 МБ, поверхность
в кратерах сжимается хуже, шаг взят 20 м, 59 МБ. Пиксель уровня 5
у экватора - 2.6 км у Марса и 1.3 км у Луны.
Пишутся уровни 0..MAX_LEVEL в папка/{z}/{x}/{y}.png. Папки mars
и moon кладутся в хранилище planetx-terrain, модуль читает тайлы
оттуда по одному (core/planets.py).
"""
import math
import os
import re
import sys

import numpy as np
from PIL import Image

MAX_LEVEL = 5
SIZE = 256
STEP = 10.0  # метров, шаг округления высот по умолчанию


def label(path):
    """Нужные поля метки PDS3: размер, тип отсчёта, масштаб, сдвиг,
    границы по долготе и широте."""
    with open(path, encoding="latin-1") as fh:
        text = fh.read()

    def field(name, default=None):
        found = re.search(r"^\s*%s\s*=\s*\"?([^\"\r\n<]+)" % name, text, re.M)
        return found.group(1).strip() if found else default
    return {
        "lines": int(field("LINES")),
        "samples": int(field("LINE_SAMPLES")),
        "type": field("SAMPLE_TYPE"),
        "bits": int(field("SAMPLE_BITS")),
        "scale": float(field("SCALING_FACTOR", "1")),
        "offset": float(field("OFFSET", "0")),
        "west": float(field("WESTERNMOST_LONGITUDE", "0")),
        "north": float(field("MAXIMUM_LATITUDE", "90")),
        "south": float(field("MINIMUM_LATITUDE", "-90")),
        "east": float(field("EASTERNMOST_LONGITUDE", "360")),
    }


def grid(lbl_path, radius_offset):
    """Сетка высот в метрах над опорной сферой тела, float32 (строки
    с севера, столбцы от западного края) и её метка.

    radius_offset вычитается из значения: у LDEM OFFSET - радиус
    сферы, высота нужна над ней."""
    meta = label(lbl_path)
    img = os.path.splitext(lbl_path)[0] + ".img"
    order = ">" if "MSB" in meta["type"] or meta["type"].startswith(
        "SUN") else "<"
    raw = np.fromfile(img, dtype=order + "i%d" % (meta["bits"] // 8))
    raw = raw.reshape(meta["lines"], meta["samples"])
    heights = raw.astype(np.float32) * meta["scale"] + meta["offset"] \
        - radius_offset
    return heights, meta


def tile_latlon(z, x, y):
    """Широта и долгота центров пикселей тайла, два массива 256×256."""
    n = 1 << z
    i = (np.arange(SIZE) + 0.5) / SIZE
    lon = (x + i) / n * 360.0 - 180.0
    merc = math.pi * (1.0 - 2.0 * (y + i) / n)
    lat = np.degrees(np.arctan(np.sinh(merc)))
    return np.meshgrid(lat, lon, indexing="ij")


def sample(heights, meta, lat, lon):
    """Высоты сетки в точках, билинейно, долгота по кругу."""
    rows, cols = heights.shape
    ppd_x = cols / (meta["east"] - meta["west"])
    ppd_y = rows / (meta["north"] - meta["south"])
    c = ((lon - meta["west"]) % 360.0) * ppd_x - 0.5
    r = np.clip((meta["north"] - lat) * ppd_y - 0.5, 0.0, rows - 1.001)
    c0 = np.floor(c).astype(np.int64)
    r0 = np.floor(r).astype(np.int64)
    fc = (c - c0).astype(np.float32)
    fr = (r - r0).astype(np.float32)
    c0 %= cols
    c1 = (c0 + 1) % cols
    r1 = np.minimum(r0 + 1, rows - 1)
    top = heights[r0, c0] * (1 - fc) + heights[r0, c1] * fc
    low = heights[r1, c0] * (1 - fc) + heights[r1, c1] * fc
    return top * (1 - fr) + low * fr


def encode(heights, step=STEP):
    """Высоты в метрах в картинку Terrarium RGB, с шагом step."""
    v = np.clip(np.round(heights / step) * step + 32768.0, 0,
                65535).astype(np.uint32)
    rgb = np.zeros(heights.shape + (3,), dtype=np.uint8)
    rgb[..., 0] = v // 256
    rgb[..., 1] = v % 256
    return rgb


def build(body, lbl_path, out, step=STEP):
    radius = {"mars": 0.0, "moon": 1737400.0}[body]
    heights, meta = grid(lbl_path, radius)
    print(body, heights.shape, "высоты от %.0f до %.0f м"
          % (float(heights.min()), float(heights.max())))
    count = 0
    total = 0
    for z in range(MAX_LEVEL + 1):
        n = 1 << z
        for x in range(n):
            folder = os.path.join(out, str(z), str(x))
            os.makedirs(folder, exist_ok=True)
            for y in range(n):
                lat, lon = tile_latlon(z, x, y)
                rgb = encode(sample(heights, meta, lat, lon), step)
                path = os.path.join(folder, "%d.png" % y)
                Image.fromarray(rgb, "RGB").save(path, optimize=True)
                count += 1
                total += os.path.getsize(path)
    print("тайлов %d, %.1f МБ" % (count, total / 1e6))


if __name__ == "__main__":
    if len(sys.argv) not in (4, 5):
        sys.exit(__doc__)
    build(sys.argv[1], sys.argv[2], sys.argv[3],
          float(sys.argv[4]) if len(sys.argv) == 5 else STEP)
