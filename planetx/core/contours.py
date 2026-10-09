# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горизонтали рельефа по тайлу высот и изолинии растра. Расчёт без Qt.

Просьба автора от 9 октября 2026 года - «подумаем об изолиниях»,
выбор того же дня - горизонтали рельефа глобуса и изолинии на гридах
под землёй.

Горизонтали рисуются в картинке тайла, как уклон (core/slope.py), по
высотам тайла Terrarium. Сечение рельефа - шаг из ряда 1, 2, 2.5, 5
× 10ⁿ метров, чтобы горизонтали стояли не реже STEP_PIXELS пикселей
тайла на склоне в 45°, как на топографической карте масштаба тайла:
у уровня 15 средних широт - 5 м, у уровня 13 - 20 м. Шаг считается
по уровню тайла и широте его середины, у соседних тайлов он один.
Каждая INDEX-я горизонталь утолщённая.

Линия сглажена: расстояние от пикселя до горизонтали в пикселях -
доля сечения, делённая на градиент высоты (|h/шаг - round| · шаг /
(|∇h| · пиксель)). Так толщина одинакова на пологом и крутом склоне.
Где горизонтали чаще FADE пикселей, они бледнеют, иначе крутой склон
залился бы цветом линий. Ниже нуля - изобаты своего цвета.

Изолинии грида под землёй - ломаные по клеткам сетки узлов методом
квадратов (marching squares), отрезки по ячейкам с разными знаками
h - уровень на рёбрах.

Цвета, толщины и пороги - выбор помощника, утверждает автор.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from .tiling import lonlat_to_tile
except ImportError:  # headless-тесты
    from tiling import lonlat_to_tile

SIZE = 256
NICE = (1.0, 2.0, 2.5, 5.0)
STEP_PIXELS = 2.0  # пикселей тайла на шаг сечения при уклоне 45°
# Мельче сечение данные Terrarium не держат: на равнине горизонтали
# через 2 м обводили целые метры исходной съёмки ступенями.
MIN_STEP = 5.0
INDEX = 5  # каждая пятая горизонталь утолщённая
WIDTH = 0.45  # полутолщина линии, пиксели
INDEX_WIDTH = 0.9
FADE = 4.0  # пикселей между горизонталями, чаще - линии бледнее
# Тайлы глубже уровня высот (до LEVEL) считаются по высотам предка,
# пересчитанным билинейно, иначе линии предка растягивались бы на
# экране вчетверо и вшестнадцатеро.
LEVEL = 17
# Высоты Terrarium глубже уровня 12 - та же съёмка 20-90 м, пересчитанная
# мельче: на уровне 13 у Перми целые метры площадками по 2-3 пикселя,
# на 14-15 - их сглаженный пересчёт с изломами по старой сетке.
# Горизонтали по ним шли ступенями и петлями. Глубже SOURCE_LEVEL
# горизонтали считаются по сглаженному тайлу этого уровня, пересчитанному
# кубически (upsample). Замер 9 октября 2026 года, жалоба автора
# «плохо строит».
SOURCE_LEVEL = 12
# Рамка тайла высот из строк соседей перед пересчётом, пиксели.
FRAME = 3
# Глубины морей у Terrarium надёжны до уровня SEA_LEVEL. Глубже в морях
# нули (Японский жёлоб, Чёрное море на 11-12) или пятна до -13 км, в
# Атлантике - глубины. Замер 9 октября 2026 года, жалоба автора -
# изолинии на воде «зависают и не строятся». Тайл, у которого тайл
# уровня SEA_LEVEL целиком глубже SEA_DEPTH метров, берёт глубины оттуда.
SEA_LEVEL = 10
SEA_DEPTH = -50.0
LAND = (150, 85, 30)  # коричневый топографических карт
WATER = (40, 95, 175)  # изобаты
OPACITY = 0.85
# Цвета линий: (суша, изобаты, яркость обычных, яркость утолщённых).
# На карте - коричневый топографических карт, на космоснимке - жёлтый
# и голубой, их видно на тёмной земле и воде. Просьба автора от
# 9 октября 2026 года.
PALETTES = {"map": (LAND, WATER, 1.0, 0.75),
            "imagery": ((255, 214, 0), (120, 205, 255), 0.85, 1.0)}
# Слова в адресе или названии подложки, по которым она - снимок.
IMAGERY_WORDS = ("imagery", "satellite", "sentinel", "landsat", "aerial",
                 "ortho", "орто", "снимк", "спутник", "lyrs=s", "lyrs=y",
                 "=sat", "/sat", "_sat", "bing")
# Подписи утолщённых горизонталей: соседние линии дальше LABEL_ROOM
# высот цифр, подписи не ближе LABEL_GAP пикселей, не больше LABEL_MAX
# на тайл, проверяется LABEL_TRIES точек. LABEL_PAD - разрыв линии
# вокруг цифр, пиксели.
LABEL_ROOM = 0.7
LABEL_GAP = 110.0
LABEL_MAX = 4
LABEL_TRIES = 4000
LABEL_PAD = 2.0
# Выгрузка горизонталей вида: около EXPORT_PIXELS пикселей высот поперёк
# участка, не больше EXPORT_TILES тайлов.
EXPORT_PIXELS = 1024
EXPORT_TILES = 64
# Склон положе FLAT метров на пиксель считается ровным местом, линий
# там нет. Шаг высот Terrarium - 1/256 м, сглаживание делит его ещё.
FLAT = 2e-3


def nice(value):
    """Ближайшее в логарифмах число ряда 1, 2, 2.5, 5 × 10ⁿ."""
    if value <= 0.0:
        return NICE[0]
    power = 10.0 ** math.floor(math.log10(value))
    candidates = [n * power for n in NICE] + [10.0 * power]
    return min(candidates, key=lambda c: abs(math.log(c / value)))


def tile_step(z, y, radius):
    """Сечение рельефа тайла (z, y), метры: по шагу пикселя на широте
    середины тайла."""
    n = 1 << z
    t = (y + 0.5) / n
    lat = math.atan(math.sinh(math.pi * (1.0 - 2.0 * t)))
    pixel = 2.0 * math.pi * radius * math.cos(lat) / (SIZE * n)
    return max(nice(pixel * STEP_PIXELS), MIN_STEP)


def is_imagery(name, url, builtin_body=False):
    """Подложка - снимок, а не карта: снимки тел (builtin_body) или
    слова IMAGERY_WORDS в названии или адресе."""
    if builtin_body:
        return True
    text = "{} {}".format(name or "", url or "").lower()
    return any(word in text for word in IMAGERY_WORDS)


def view_step(distance, lat, fov_y, height_px, radius, max_level=LEVEL):
    """Сечение горизонталей в середине вида: камера на расстоянии
    distance от точки взгляда на широте lat, поле зрения fov_y (рад),
    окно height_px пикселей. Уровень тайла - тот, у которого тексель
    не больше 1.5 пикселя экрана, как у выбора тайлов вида."""
    screen = 2.0 * distance * math.tan(fov_y / 2.0) / max(height_px, 1)
    ground = 2.0 * math.pi * radius * max(math.cos(math.radians(lat)),
                                          1e-6) / SIZE
    level = int(min(max_level, max(0, math.ceil(math.log2(
        ground / max(1.5 * screen, 1e-9))))))
    pixel = ground / (1 << level)
    return max(nice(pixel * STEP_PIXELS), MIN_STEP)


def contour_rgba(heights, z, y, radius, step=None, glyphs=None,
                 palette="map"):
    """Картинка горизонталей тайла: RGBA uint8 с премноженной альфой.
    glyphs - картинки цифр для подписей утолщённых горизонталей
    (label_strip), без них подписей нет."""
    h = smooth(np.asarray(heights, dtype=np.float64))
    step = step or tile_step(z, y, radius)
    d_row, d_col, gap, spacing, index = line_fields(h, step)
    width = np.where(index, INDEX_WIDTH, WIDTH)
    alpha = np.clip(width + 0.5 - gap, 0.0, 1.0)
    alpha *= np.clip(spacing / FADE, 0.0, 1.0)
    alpha = (alpha * OPACITY).astype(np.float32)
    land, water, shade, index_shade = PALETTES[palette]
    rgb = np.where((h < 0.0)[..., None], np.array(water, np.float32),
                   np.array(land, np.float32))
    rgb = rgb * np.where(index, index_shade, shade)[..., None]
    if glyphs:
        labels = place_labels(h, d_row, d_col, step,
                              label_spots(gap, index, spacing,
                                          glyphs["height"]), glyphs)
        for (text, box, value) in labels:
            rows, cols, ink, clear = box
            # Разрыв линии под подписью, потом цифры цветом линии.
            alpha[rows, cols] *= 1.0 - clear
            color = np.array(water if value < 0.0 else land,
                             np.float32) * index_shade
            rgb[rows, cols] = color
            alpha[rows, cols] = np.maximum(alpha[rows, cols],
                                           ink * OPACITY)
    out = np.empty(h.shape + (4,), dtype=np.uint8)
    out[..., :3] = np.rint(rgb * alpha[..., None])
    out[..., 3] = np.rint(alpha * 255.0)
    return out


def label_spots(gap, index, spacing, height):
    """Где может стоять подпись: на утолщённой горизонтали, соседние
    линии дальше LABEL_ROOM высот цифр."""
    return index & (gap < 0.5) & (spacing >= LABEL_ROOM * height)


def line_fields(h, step):
    """Поля линий по сглаженным высотам h: производные по строкам
    и столбцам, расстояние до горизонтали и между горизонталями
    в пикселях, утолщённая ли ближняя горизонталь."""
    d_row, d_col = np.gradient(h)
    grad = np.maximum(np.hypot(d_row, d_col), 1e-6)
    level = h / step
    near = np.rint(level)
    gap = np.abs(level - near) * step / grad
    # Ровная гладь озера на самой отметке - не линия: без склона
    # расстояние до горизонтали выходило нулём по всей глади.
    gap[grad < FLAT] = np.inf
    index = np.mod(near, INDEX) == 0
    return d_row, d_col, gap, step / grad, index


def label_text(value):
    """Подпись отметки: целые метры без точки, дробные - с одним знаком."""
    if abs(value - round(value)) < 1e-6:
        return str(int(round(value)))
    return "%.1f" % value


def label_strip(text, glyphs):
    """Картинка подписи - альфа цифр подряд (высота, длина), float."""
    parts = [glyphs[c] for c in text if c in glyphs]
    if not parts:
        return None
    gap = np.zeros((glyphs["height"], 1), np.float32)
    strip = [parts[0]]
    for p in parts[1:]:
        strip += [gap, p]
    return np.hstack(strip)


def place_labels(h, d_row, d_col, step, candidates, glyphs):
    """Подписи утолщённых горизонталей тайла.

    Подпись стоит на линии, где соседние горизонтали дальше высоты
    цифр (candidates), вдоль линии, верхом к подъёму, как на
    топографической карте. Подпись целиком внутри тайла, концы её
    лежат на той же горизонтали, поэтому у края тайла и на крутом
    изгибе её нет. Подписи не ближе LABEL_GAP пикселей друг к другу,
    первыми - ближние к середине тайла, так у соседних кадров одна
    раскладка. Возвращает (текст, (строки, столбцы, цифры, разрыв),
    отметка)."""
    size = h.shape[0]
    rows, cols = np.nonzero(candidates)
    if not len(rows):
        return []
    mid = (size - 1) / 2.0
    order = np.argsort((rows - mid) ** 2 + (cols - mid) ** 2,
                       kind="stable")
    height = glyphs["height"]
    placed = []
    out = []
    for i in order[:LABEL_TRIES]:
        r, c = int(rows[i]), int(cols[i])
        if any((r - pr) ** 2 + (c - pc) ** 2 < LABEL_GAP ** 2
               for pr, pc in placed):
            continue
        gx, gy = d_col[r, c], d_row[r, c]
        norm = math.hypot(gx, gy)
        if norm <= 0.0:
            continue
        value = round(h[r, c] / step) * step
        strip = label_strip(label_text(value), glyphs)
        if strip is None:
            continue
        box = _label_box(h, r, c, gx / norm, gy / norm, norm, value,
                         strip, height)
        if box is None:
            continue
        placed.append((r, c))
        out.append((label_text(value), box, value))
        if len(out) >= LABEL_MAX:
            break
    return out


def _label_box(h, r, c, ux_up, uy_up, grad, value, strip, height):
    """Пиксели подписи в точке (r, c): направление подъёма (ux_up,
    uy_up) в столбцах и строках. None, если подпись не помещается
    в тайл или концы её уходят с горизонтали."""
    size = h.shape[0]
    length = strip.shape[1]
    # Ось текста вдоль линии, «вниз» текста - под уклон.
    ux, uy = -uy_up, ux_up
    vx, vy = -ux_up, -uy_up
    half = length / 2.0 + LABEL_PAD
    reach = math.hypot(half, height / 2.0 + LABEL_PAD)
    if not (reach + 1 <= r <= size - 2 - reach
            and reach + 1 <= c <= size - 2 - reach):
        return None
    # Концы подписи на той же горизонтали не дальше трети высоты цифр.
    for sign in (-1.0, 1.0):
        er = int(round(r + sign * uy * length / 2.0))
        ec = int(round(c + sign * ux * length / 2.0))
        if abs(h[er, ec] - value) / max(grad, 1e-6) > height / 3.0:
            return None
    r0, r1 = int(r - reach), int(r + reach) + 1
    c0, c1 = int(c - reach), int(c + reach) + 1
    gr, gc = np.mgrid[r0:r1, c0:c1].astype(np.float64)
    dx, dy = gc - c, gr - r
    lx = dx * ux + dy * uy + length / 2.0 - 0.5
    ly = dx * vx + dy * vy + height / 2.0 - 0.5
    clear = np.clip(np.minimum(half - np.abs(dx * ux + dy * uy),
                               height / 2.0 + 1.0
                               - np.abs(dx * vx + dy * vy)) + 0.5,
                    0.0, 1.0)
    ink = _bilinear(strip, ly, lx)
    return gr.astype(int), gc.astype(int), ink.astype(np.float32), \
        clear.astype(np.float32)


def _bilinear(img, y, x):
    """Значения img в дробных точках (y, x), вне картинки - 0."""
    hgt, wid = img.shape
    pad = np.pad(img, 1)
    y = y + 1.0
    x = x + 1.0
    inside = (y >= 0) & (y <= hgt + 1) & (x >= 0) & (x <= wid + 1)
    y = np.clip(y, 0, hgt + 0.999)
    x = np.clip(x, 0, wid + 0.999)
    y0 = np.floor(y).astype(int)
    x0 = np.floor(x).astype(int)
    fy, fx = y - y0, x - x0
    v = (pad[y0, x0] * (1 - fy) * (1 - fx) + pad[y0, x0 + 1] * (1 - fy) * fx
         + pad[y0 + 1, x0] * fy * (1 - fx) + pad[y0 + 1, x0 + 1] * fy * fx)
    return np.where(inside, v, 0.0)


def footprint_high(tile_heights, tile_key, key):
    """Наибольшая высота тайла высот tile_key (предка key) под
    тайлом key с полосой в пиксель вокруг."""
    scale = 1 << (key[0] - tile_key[0])
    size = SIZE / scale
    c0 = (key[1] - tile_key[1] * scale) * size
    r0 = (key[2] - tile_key[2] * scale) * size
    lo_c = max(int(math.floor(c0)) - 1, 0)
    lo_r = max(int(math.floor(r0)) - 1, 0)
    hi_c = min(int(math.ceil(c0 + size)) + 1, SIZE)
    hi_r = min(int(math.ceil(r0 + size)) + 1, SIZE)
    return float(np.max(tile_heights[lo_r:hi_r, lo_c:hi_c]))


def source_level(key, sea_high, land_level=SOURCE_LEVEL):
    """Уровень тайла высот, по которому строятся горизонтали тайла key.
    sea_high - наибольшая высота тайла уровня SEA_LEVEL над key или
    None, если его нет: целиком глубже SEA_DEPTH - открытое море, глубины
    с SEA_LEVEL, иначе - land_level. Не глубже самого key."""
    if sea_high is not None and sea_high < SEA_DEPTH:
        return min(key[0], SEA_LEVEL)
    return min(key[0], land_level)


def _cubic(p0, p1, p2, p3, t):
    """Кубическая кривая Катмулла-Рома через четыре значения."""
    return p1 + 0.5 * t * (p2 - p0 + t * (2.0 * p0 - 5.0 * p1 + 4.0 * p2
                                          - p3 + t * (3.0 * (p1 - p2)
                                                      + p3 - p0)))


def upsample(heights, source, key, neighbor=None, smoothed=False):
    """Высоты тайла key по высотам тайла-предка source (z, x, y):
    кубический пересчёт без изломов по сетке предка, массив (256,
    256). neighbor(ключ) - высоты соседнего тайла уровня source или
    None: их строки встают за край, без них значения за краем
    продолжаются линейно. smoothed - сначала сгладить предка вместе
    с этой рамкой (smooth)."""
    big = _framed(heights, source, neighbor)
    if smoothed:
        big = smooth(big)
    scale = 1 << (key[0] - source[0])
    pos = (np.arange(SIZE) + 0.5) / scale - 0.5
    off_x = (key[1] - (source[1] * scale)) * SIZE / scale
    off_y = (key[2] - (source[2] * scale)) * SIZE / scale
    return _sample(big, FRAME, off_y + pos, off_x + pos)


def _framed(heights, source, neighbor):
    """Тайл высот с рамкой FRAME пикселей: строки соседей, где они
    есть, иначе линейное продолжение. Без соседей у тайлов из разных
    предков уровня 10 горизонтали расходились на шве на 3-5 м при шаге
    высот 0.15 м внутри, у Японского жёлоба 9 октября 2026 года."""
    big = np.pad(np.asarray(heights, dtype=np.float64), FRAME,
                 mode="reflect", reflect_type="odd")
    if neighbor is None:
        return big
    z, x, y = source
    n = 1 << z
    parts = {-1: (slice(0, FRAME), slice(SIZE - FRAME, SIZE)),
             0: (slice(FRAME, FRAME + SIZE), slice(0, SIZE)),
             1: (slice(FRAME + SIZE, None), slice(0, FRAME))}
    for dy in (-1, 0, 1):
        if not 0 <= y + dy < n:
            continue
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            other = neighbor((z, (x + dx) % n, y + dy))
            if other is None:
                continue
            rows, src_rows = parts[dy]
            cols, src_cols = parts[dx]
            big[rows, cols] = np.asarray(other)[src_rows, src_cols]
    return big


def crop_refine(grid, x0, y0, factor, box):
    """Мозаика уровня предков (левый верхний тайл x0, y0), обрезанная
    по тайлам box (x0, y0, x1, y1) уровня в factor раз подробнее
    и пересчитанная до него: (мозаика, x0, y0) этого уровня. Без
    обрезки мозаика предков, пересчитанная в 16 раз, весила бы сотни
    мегабайт."""
    bx0, by0, bx1, by1 = box
    size = SIZE / factor  # пикселей предка на тайл подробного уровня
    c0 = (bx0 - x0 * factor) * size
    r0 = (by0 - y0 * factor) * size
    cols = (bx1 - bx0 + 1) * SIZE
    rows = (by1 - by0 + 1) * SIZE
    xs = c0 + (np.arange(cols) + 0.5) / factor - 0.5
    ys = r0 + (np.arange(rows) + 0.5) / factor - 0.5
    return _resample(grid, ys, xs), bx0, by0


def _resample(values, ys, xs):
    """Значения values в дробных строках ys и столбцах xs (отсчёт от
    центров пикселей) кубически, за краем - линейное продолжение."""
    big = np.pad(np.asarray(values, dtype=np.float64), 2, mode="reflect",
                 reflect_type="odd")
    return _sample(big, 2, ys, xs)


def _sample(big, pad, ys, xs):
    """Кубическая выборка массива big с рамкой pad пикселей вокруг
    данных: ys и xs - строки и столбцы данных, не дальше полупикселя
    за краем."""
    rows, cols = big.shape[0] - 2 * pad, big.shape[1] - 2 * pad
    xs = np.clip(xs, -0.5, cols - 0.5) + pad
    ys = np.clip(ys, -0.5, rows - 0.5) + pad
    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)
    tx = (xs - x0)[None, :]
    ty = (ys - y0)[:, None]
    out = []
    for dy in (-1, 0, 1, 2):
        r = big[(y0 + dy)[:, None], x0[None, :] + np.array(
            [-1, 0, 1, 2])[:, None, None]]
        out.append(_cubic(r[0], r[1], r[2], r[3], tx))
    return _cubic(out[0], out[1], out[2], out[3], ty)


def smooth(h):
    """Высоты, сглаженные окном [1, 2, 1] / 4 по строкам и столбцам:
    без него ступеньки целых метров Terrarium давали бусы на линиях."""
    p = np.pad(h, 1, mode="edge")
    rows = (p[:-2] + 2.0 * p[1:-1] + p[2:]) / 4.0
    return (rows[:, :-2] + 2.0 * rows[:, 1:-1] + rows[:, 2:]) / 4.0


def export_tiles(lat, lon, width, height, radius, max_level):
    """Тайлы высот участка width × height метров с серединой (lat, lon)
    для выгрузки горизонталей: (уровень, ключи). Уровень - тот, у
    которого поперёк участка около EXPORT_PIXELS пикселей, не глубже
    max_level и не больше EXPORT_TILES тайлов."""
    coslat = max(math.cos(math.radians(lat)), 1e-6)
    dlat = math.degrees(height / 2.0 / radius)
    dlon = math.degrees(width / 2.0 / (radius * coslat))
    north = min(lat + dlat, 85.0)
    south = max(lat - dlat, -85.0)
    west = max(lon - dlon, -180.0)
    east = min(lon + dlon, 179.999999)
    pixel = max(width, 1.0) / EXPORT_PIXELS
    ground = 2.0 * math.pi * radius * coslat / SIZE
    level = int(min(max_level, max(0, math.ceil(math.log2(ground
                                                          / pixel)))))
    while True:
        x0, y0 = lonlat_to_tile(north, west, level)
        x1, y1 = lonlat_to_tile(south, east, level)
        if (x1 - x0 + 1) * (y1 - y0 + 1) <= EXPORT_TILES or level == 0:
            break
        level -= 1
    return level, [(level, x, y) for y in range(y0, y1 + 1)
                   for x in range(x0, x1 + 1)]


def mosaic(keys, heights_of):
    """Высоты тайлов keys одного уровня одним массивом: (массив, x0,
    y0) - номера левого верхнего тайла. heights_of(key) - массив
    (256, 256) или None, пустые тайлы - NaN."""
    xs = [k[1] for k in keys]
    ys = [k[2] for k in keys]
    x0, y0 = min(xs), min(ys)
    grid = np.full(((max(ys) - y0 + 1) * SIZE, (max(xs) - x0 + 1) * SIZE),
                   np.nan, dtype=np.float32)
    for key in keys:
        heights = heights_of(key)
        if heights is None:
            continue
        r, c = (key[2] - y0) * SIZE, (key[1] - x0) * SIZE
        grid[r:r + SIZE, c:c + SIZE] = heights
    return grid, x0, y0


def mercator_transform(z, x0, y0, radius):
    """Геопреобразование GDAL мозаики с левым верхним тайлом (x0, y0)
    уровня z в метрах EPSG:3857."""
    world = 2.0 * math.pi * radius
    pixel = world / (SIZE * (1 << z))
    return (-world / 2.0 + x0 * SIZE * pixel, pixel, 0.0,
            world / 2.0 - y0 * SIZE * pixel, 0.0, -pixel)


def index_step(step):
    """Шаг утолщённых горизонталей при сечении step."""
    return step * INDEX


def levels(values, step):
    """Отметки изолиний через step в пределах значений, без NaN."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite) or step <= 0.0:
        return np.zeros(0)
    lo = math.ceil(finite.min() / step) * step
    hi = math.floor(finite.max() / step) * step
    if hi < lo:
        return np.zeros(0)
    return np.arange(lo, hi + step * 0.5, step)


def grid_step(values, lines=12.0):
    """Шаг изолиний грида: около lines линий на размах значений."""
    finite = np.asarray(values, dtype=np.float64)
    finite = finite[np.isfinite(finite)]
    if not len(finite):
        return 0.0
    span = float(finite.max() - finite.min())
    return nice(span / lines) if span > 0.0 else 0.0


def segments(z, level):
    """Отрезки изолинии level по сетке z (rows, cols), NaN - пусто.
    Возвращает массив (n, 2, 2) точек в долях индексов узлов (строка,
    столбец). Ячейка с пустым углом пропускается."""
    z = np.asarray(z, dtype=np.float64)
    a, b = z[:-1, :-1], z[:-1, 1:]
    c, d = z[1:, :-1], z[1:, 1:]
    ok = np.isfinite(a) & np.isfinite(b) & np.isfinite(c) & np.isfinite(d)
    rows, cols = np.nonzero(ok)
    if not len(rows):
        return np.zeros((0, 2, 2))
    va, vb = a[rows, cols], b[rows, cols]
    vc, vd = c[rows, cols], d[rows, cols]
    # Рёбра ячейки: верх a-b, право b-d, низ c-d, лево a-c.
    edges = ((va, vb, 0.0, 0.0, 0.0, 1.0), (vb, vd, 0.0, 1.0, 1.0, 1.0),
             (vc, vd, 1.0, 0.0, 1.0, 1.0), (va, vc, 0.0, 0.0, 1.0, 0.0))
    points = []
    hits = []
    for v0, v1, r0, c0, r1, c1 in edges:
        # Узел ровно на уровне считается выше: линия не пропадает.
        cross = (v0 >= level) != (v1 >= level)
        t = np.where(cross, (level - v0) / np.where(v1 != v0, v1 - v0, 1.0),
                     0.0)
        pr = rows + r0 + (r1 - r0) * t
        pc = cols + c0 + (c1 - c0) * t
        points.append(np.stack([pr, pc], axis=-1))
        hits.append(cross)
    points = np.stack(points, axis=1)  # (n, 4, 2)
    hits = np.stack(hits, axis=1)  # (n, 4)
    count = hits.sum(axis=1)
    out = []
    two = count == 2
    if two.any():
        idx = np.argsort(~hits[two], axis=1, kind="stable")[:, :2]
        p = points[two]
        out.append(np.stack([p[np.arange(len(p)), idx[:, 0]],
                             p[np.arange(len(p)), idx[:, 1]]], axis=1))
    four = count == 4
    if four.any():
        # Седло: две пары рёбер, по среднему значению ячейки.
        p = points[four]
        mid = (va + vb + vc + vd)[four] / 4.0
        high = (mid > level) == (va[four] > level)
        first = np.where(high[:, None, None], p[:, [0, 1]], p[:, [0, 3]])
        second = np.where(high[:, None, None], p[:, [2, 3]], p[:, [1, 2]])
        out += [first, second]
    return np.concatenate(out) if out else np.zeros((0, 2, 2))
