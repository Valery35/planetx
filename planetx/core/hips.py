# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Обзоры неба HiPS (IVOA Hierarchical Progressive Surveys), без Qt.

Небо нарезано сеткой HEALPix с вложенной нумерацией: 12 граней, у
порядка k по 4^k ячеек на грань. Тайл порядка k - картинка 512 × 512
ячейки HEALPix, её пиксели - ячейки порядка k + 9. Адрес тайла
Norder{k}/Dir{ipix // 10000 * 10000}/Npix{ipix}.jpg. Весь порядок 3 -
картинка Norder3/Allsky.jpg, 768 тайлов по 64 пикселя рядами по 27.

Точка ячейки - непрерывные координаты грани x, y от 0 до 1 (xyf2loc
библиотеки HEALPix), направление - прямое восхождение и склонение
J2000 у обзоров в экваториальной системе.
"""
import math

import numpy as np

TILE = 512  # пикселей на сторону тайла
ALLSKY_ORDER = 3
ALLSKY_COLUMNS = 27  # тайлов в ряду Allsky.jpg
MIN_ORDER = 3
CELL_STEPS = 8  # сетка вершин тайла на сторону

# Начальная строка грани и смещение долготы, как jrll и jpll HEALPix.
JRLL = (2, 2, 2, 2, 3, 3, 3, 3, 4, 4, 4, 4)
JPLL = (1, 3, 5, 7, 0, 2, 4, 6, 1, 3, 5, 7)

CDS = "https://alasky.cds.unistra.fr/"

# Обзоры: ключ, адрес, наибольший порядок, названия по-русски
# и по-английски, подпись источника и её ссылка. Условия -
# doc/SOURCES.md.
SURVEYS = (
    ("dss", CDS + "DSS/DSSColor/", 9,
     "DSS, видимый свет", "DSS, visible light",
     "DSS: STScI/NASA, CDS", "https://archive.stsci.edu/dss/"
     "acknowledging.html"),
    ("2mass", CDS + "2MASS/Color/", 9,
     "2MASS, ближний инфракрасный", "2MASS, near infrared",
     "2MASS: UMass, IPAC/Caltech, CDS", "https://www.ipac.caltech.edu/"
     "2mass/"),
)


def survey(key):
    for item in SURVEYS:
        if item[0] == key:
            return item
    return None


def tile_url(base, order, ipix):
    return "{}Norder{}/Dir{}/Npix{}.jpg".format(
        base, order, ipix // 10000 * 10000, ipix)


def allsky_url(base):
    return "{}Norder{}/Allsky.jpg".format(base, ALLSKY_ORDER)


def _compress(value):
    """Чётные биты числа подряд - обратное чередованию битов."""
    out = np.zeros_like(value)
    bit = 0
    while np.any(value >> (2 * bit)):
        out |= ((value >> (2 * bit)) & 1) << bit
        bit += 1
    return out


def nest_xyf(order, ipix):
    """Ячейка вложенной нумерации: грань и номер ix, iy в грани."""
    ipix = np.asarray(ipix, dtype=np.int64)
    face = ipix >> (2 * order)
    inner = ipix & ((1 << (2 * order)) - 1)
    return face, _compress(inner), _compress(inner >> 1)


def face_directions(face, x, y):
    """Направления точек грани face с координатами x, y от 0 до 1,
    массивы (..., 3)."""
    face = np.asarray(face)
    x = np.asarray(x, dtype=np.float64)
    y = np.asarray(y, dtype=np.float64)
    jr = np.asarray(JRLL)[face] - x - y
    north = jr < 1.0
    south = jr > 3.0
    nr = np.where(north, jr, np.where(south, 4.0 - jr, 1.0))
    z = np.where(north, 1.0 - nr * nr / 3.0,
                 np.where(south, nr * nr / 3.0 - 1.0,
                          (2.0 - jr) * 2.0 / 3.0))
    tmp = np.asarray(JPLL)[face] * nr + x - y
    tmp = np.mod(tmp, 8.0)
    phi = np.where(nr < 1e-15, 0.0,
                   math.pi / 4.0 * tmp / np.maximum(nr, 1e-15))
    st = np.sqrt(np.maximum(0.0, 1.0 - z * z))
    return np.stack([st * np.cos(phi), st * np.sin(phi), z], axis=-1)


def pixel_face(col, row, size=TILE):
    """Доли x, y грани внутри тайла для пикселя col, row картинки
    (ряд сверху): x растёт вниз по рядам, y - вправо по столбцам.
    Сверено 24 октября 2026 года по ярким звёздам на тайлах DSS
    порядка 3 - из восьми поворотов и отражений только этот ставит
    Бетельгейзе, Вегу, Арктур и Капеллу ближе 0.05° к каталогу."""
    col = np.asarray(col, dtype=np.float64)
    row = np.asarray(row, dtype=np.float64)
    return row / size, col / size


def tile_mesh(order, ipix, steps=CELL_STEPS):
    """Вершины тайла: направления ((steps+1)², 3) и доли картинки
    u, v ((steps+1)², 2), v сверху вниз. Треугольники - mesh_indices."""
    face, ix, iy = nest_xyf(order, ipix)
    side = 1 << order
    t = np.linspace(0.0, 1.0, steps + 1)
    u, v = np.meshgrid(t, t)
    fx, fy = pixel_face(u * TILE, v * TILE)
    dirs = face_directions(int(face), (int(ix) + fx) / side,
                           (int(iy) + fy) / side)
    return dirs.reshape(-1, 3), np.stack([u.ravel(), v.ravel()], axis=1)


def mesh_indices(steps=CELL_STEPS):
    """Треугольники сетки (steps+1)² вершин."""
    n = steps + 1
    a = np.arange(steps)
    r, c = np.meshgrid(a, a, indexing="ij")
    i = (r * n + c).ravel()
    quads = np.stack([i, i + 1, i + n, i + 1, i + n + 1, i + n], axis=1)
    return quads.ravel().astype(np.uint32)


def cell_size(order):
    """Сторона ячейки порядка order, радианы."""
    return math.sqrt(4.0 * math.pi / (12 * 4 ** order))


def order_for(radians_per_pixel, top):
    """Порядок тайлов, у которых пиксель не крупнее пикселя экрана.
    None - хватает Allsky.jpg порядка 3 по 64 пикселя."""
    allsky = cell_size(ALLSKY_ORDER) / (TILE // 8)
    if allsky <= radians_per_pixel * 1.5:
        return None
    for order in range(MIN_ORDER, top + 1):
        if cell_size(order) / TILE <= radians_per_pixel * 1.5:
            return order
    return top


def centers(order, ipix):
    """Направления середин ячеек, (N, 3)."""
    face, ix, iy = nest_xyf(order, ipix)
    side = 1 << order
    return face_directions(face, (ix + 0.5) / side, (iy + 0.5) / side)


def visible(order, axis, reach):
    """Ячейки порядка order, задевающие конус вокруг направления axis
    с полууглом reach (радианы). Спуск от порядка 0 по детям."""
    axis = np.asarray(axis, dtype=np.float64)
    cells = np.arange(12, dtype=np.int64)
    for level in range(order + 1):
        if level:
            cells = (cells[:, None] * 4 + np.arange(4)).ravel()
        # Ячейка вписана в круг радиусом около стороны.
        radius = cell_size(level) * (1.6 if level < 2 else 1.0)
        cos = centers(level, cells) @ axis
        cells = cells[cos >= math.cos(min(math.pi, reach + radius))]
    return cells


def allsky_rect(ipix, width, height):
    """Доли Allsky.jpg под тайлом порядка 3: u0, v0, du, dv."""
    side = width / ALLSKY_COLUMNS
    col = ipix % ALLSKY_COLUMNS
    row = ipix // ALLSKY_COLUMNS
    return (col * side / width, row * side / height,
            side / width, side / height)
