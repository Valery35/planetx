# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек LAS, LAZ и COPC: клетки, выбор по экрану, разбор, цвета.

Облако - слой QGIS, точки читает pdal.exe из состава QGIS по файлу
COPC (LAS и LAZ переводятся в COPC один раз). Облако делится на клетки
квадродерева в системе координат файла, клетка уровня L берётся
у PDAL с шагом точек resolution(L) - сторона клетки / CELL_GRID
(readers.copc, параметры bounds и resolution). Клетка делится, когда
её шаг на экране больше POINT_PIXELS, и заменяется детьми только
целиком, как тайл глобуса (core/lod.py). Точек в кадре не больше
POINT_BUDGET, сначала делятся клетки с наибольшей экранной ошибкой.

PDAL отдаёт клетку файлом LAS без сжатия в градусах EPSG:4326, высоты -
в единицах файла (read_las). Вершины для видеокарты - смещения от
центра клетки в ECEF (vertices), мировые координаты в видеокарту
не попадают.
"""
import heapq
import json
import math
import struct
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from .lod import TileInfo, priority
except ImportError:  # headless-тесты
    import ellipsoid
    from lod import TileInfo, priority

# Величины - выбор помощника, утверждает автор.
POINT_BUDGET = 3000000  # точек в кадре, не больше
POINT_PIXELS = 2.0  # шаг точек на экране, после которого клетка делится
CELL_GRID = 256  # шаг точек клетки - её сторона / CELL_GRID
MAX_LEVEL = 24
POINT_SIZE = 2.0  # логических пикселей, по умолчанию
MARGIN = 1.05  # запас радиуса описанной сферы клетки

Points = namedtuple("Points", "x y z cls rgb intensity")
Points.__doc__ = """Точки клетки: x, y - долгота и широта (или координаты
файла), z - отметка в единицах файла, cls - класс ASPRS (uint8), rgb -
(n, 3) uint8 или None, intensity - uint16."""

Cloud = namedtuple("Cloud", "xmin ymin xmax ymax zmin zmax count")
Cloud.__doc__ = """Охват облака в системе файла и количество точек."""

# Смещения полей записи точки LAS по формату: (класс, его маска, RGB).
# Форматы 0-5 хранят класс в пяти младших битах байта 15, 6-10 - байт 16.
_FORMATS = {0: (15, 0x1F, None), 1: (15, 0x1F, None), 2: (15, 0x1F, 20),
            3: (15, 0x1F, 28), 4: (15, 0x1F, None), 5: (15, 0x1F, 28),
            6: (16, 0xFF, None), 7: (16, 0xFF, 30), 8: (16, 0xFF, 30),
            9: (16, 0xFF, None), 10: (16, 0xFF, 30)}

# Цвета классов ASPRS (LAS 1.4, таблица 17) - выбор помощника.
CLASS_COLORS = {
    0: (170, 170, 170), 1: (170, 170, 170), 2: (166, 118, 60),
    3: (200, 230, 120), 4: (110, 180, 60), 5: (40, 120, 40),
    6: (230, 90, 60), 7: (230, 0, 230), 8: (200, 200, 0),
    9: (40, 110, 230), 10: (120, 90, 70), 11: (110, 110, 110),
    12: (240, 240, 140), 13: (255, 200, 0), 14: (255, 120, 0),
    15: (180, 0, 180), 16: (255, 255, 120), 17: (150, 150, 200),
    18: (255, 0, 120)}
OTHER_COLOR = (200, 200, 200)
# Высоты - от синего через зелёный и жёлтый к красному.
HEIGHT_STOPS = ((0.0, (40, 60, 200)), (0.25, (40, 170, 210)),
                (0.5, (70, 190, 70)), (0.75, (240, 210, 50)),
                (1.0, (210, 50, 40)))
MODES = ("rgb", "class", "height", "intensity")

_VERTICAL = {"m": 1.0, "ft": 0.3048, "us-ft": 1200.0 / 3937.0,
             "km": 1000.0}


def vertical_factor(proj):
    """Множитель отметок облака к метрам по строке PROJ системы файла:
    +vunits, без него +units, иначе метры."""
    found = {}
    for part in proj.split():
        if part.startswith("+") and "=" in part:
            name, value = part[1:].split("=", 1)
            found[name] = value
    unit = found.get("vunits") or found.get("units") or "m"
    return _VERTICAL.get(unit, 1.0)


def read_las(data):
    """Точки файла LAS без сжатия (bytes или массив uint8)."""
    raw = np.frombuffer(data, dtype=np.uint8) \
        if isinstance(data, (bytes, bytearray, memoryview)) \
        else np.asarray(data, dtype=np.uint8)
    head = raw[:375].tobytes()
    if head[:4] != b"LASF":
        raise ValueError("not a LAS file")
    version = (head[24], head[25])
    offset = struct.unpack_from("<I", head, 96)[0]
    fmt = head[104] & 0x3F
    if head[104] & 0xC0:
        raise ValueError("compressed LAS")
    length = struct.unpack_from("<H", head, 105)[0]
    count = struct.unpack_from("<I", head, 107)[0]
    if version >= (1, 4) and len(head) >= 255:
        count = struct.unpack_from("<Q", head, 247)[0] or count
    if fmt not in _FORMATS:
        raise ValueError("point format {}".format(fmt))
    sx, sy, sz, ox, oy, oz = struct.unpack_from("<6d", head, 131)
    count = min(count, (len(raw) - offset) // length) if length else 0
    rows = raw[offset:offset + count * length].reshape(count, length)
    xyz = np.ascontiguousarray(rows[:, :12]).view("<i4").reshape(count, 3)
    x = xyz[:, 0] * sx + ox
    y = xyz[:, 1] * sy + oy
    z = xyz[:, 2] * sz + oz
    intensity = np.ascontiguousarray(rows[:, 12:14]).view("<u2") \
        .reshape(count)
    at, mask, rgb_at = _FORMATS[fmt]
    cls = rows[:, at] & mask
    rgb = None
    if rgb_at is not None:
        wide = np.ascontiguousarray(rows[:, rgb_at:rgb_at + 6]).view("<u2") \
            .reshape(count, 3)
        if wide.size and int(wide.max()) > 0:
            # Цвет в LAS 16-битный, у части съёмок он записан 8-битным.
            shift = 8 if int(wide.max()) > 255 else 0
            rgb = (wide >> shift).astype(np.uint8)
    return Points(x, y, z, cls.astype(np.uint8), rgb, intensity)


def side(cloud):
    """Сторона корневой клетки - больший размах охвата."""
    return max(cloud.xmax - cloud.xmin, cloud.ymax - cloud.ymin, 1e-9)


def bounds(cloud, key):
    """Рамка клетки (xmin, ymin, xmax, ymax) в системе файла."""
    level, ix, iy = key
    size = side(cloud) / (1 << level)
    x0 = cloud.xmin + ix * size
    y0 = cloud.ymin + iy * size
    return x0, y0, x0 + size, y0 + size


def resolution(cloud, level):
    """Шаг точек клетки уровня level в единицах файла."""
    return side(cloud) / (1 << level) / CELL_GRID


def spacing(cloud):
    """Средний шаг точек облака по площади охвата."""
    area = max((cloud.xmax - cloud.xmin) * (cloud.ymax - cloud.ymin), 1e-9)
    return math.sqrt(area / max(cloud.count, 1))


def max_level(cloud):
    """Уровень, глубже которого клетки не делятся: шаг клетки уже не
    крупнее собственного шага облака."""
    native = spacing(cloud)
    level = 0
    while level < MAX_LEVEL and resolution(cloud, level) > native:
        level += 1
    return level


def children(key):
    level, ix, iy = key
    return [(level + 1, 2 * ix + dx, 2 * iy + dy)
            for dy in (0, 1) for dx in (0, 1)]


def cell_info(cloud, key, to_geo, zfactor, scale):
    """Описанная сфера клетки для выбора (lod.TileInfo).

    to_geo(xs, ys) - долготы и широты точек файла, zfactor - множитель
    отметок к метрам, scale - масштаб рельефа (высота на экране)."""
    x0, y0, x1, y1 = bounds(cloud, key)
    xs = np.array([x0, x1, x0, x1, (x0 + x1) / 2.0], dtype=np.float64)
    ys = np.array([y0, y0, y1, y1, (y0 + y1) / 2.0], dtype=np.float64)
    lons, lats = to_geo(xs, ys)
    lons = np.asarray(lons, dtype=np.float64)
    lats = np.asarray(lats, dtype=np.float64)
    low, high = (display(np.array([cloud.zmin, cloud.zmax]), cloud, zfactor,
                         scale))
    points = []
    for h in (low, high):
        xyz = ellipsoid.geodetic_to_ecef(lats, lons, np.full(5, h))
        points.append(np.stack(xyz, axis=-1)
                      if isinstance(xyz, tuple) else xyz)
    points = np.concatenate(points)
    center = points.mean(axis=0)
    radius = float(np.max(np.linalg.norm(points - center, axis=1))) * MARGIN
    norm = float(np.linalg.norm(center))
    direction = tuple(float(c) / norm for c in center)
    cos = np.clip(points @ np.array(direction) /
                  np.linalg.norm(points, axis=1), -1.0, 1.0)
    alpha = min(math.pi, float(np.max(np.arccos(cos))) * MARGIN)
    # Шаг точек в метрах - сторона клетки по её углам на эллипсоиде,
    # делённая на CELL_GRID: единицы файла бывают футами и градусами.
    low_ring = points[:4]
    width = max(float(np.linalg.norm(low_ring[1] - low_ring[0])),
                float(np.linalg.norm(low_ring[2] - low_ring[0])))
    texel = width / CELL_GRID
    return TileInfo(tuple(float(c) for c in center), radius, direction,
                    alpha, texel)


def display(z, cloud, zfactor, scale):
    """Высота точек на экране по отметкам файла. С рельефом - отметка
    в метрах, умноженная на масштаб рельефа, как у моделей. Без рельефа
    (scale 0) облако стоит на эллипсоиде низом."""
    z = np.asarray(z, dtype=np.float64) * zfactor
    if scale:
        return z * scale
    return z - cloud.zmin * zfactor


Selection = namedtuple("Selection", "draw want points")
Selection.__doc__ = """draw - клетки для рисования без перекрытий, want -
[(приоритет, клетка)] для загрузки, points - точек в draw."""


def select(cloud, frame, ready, info_of, budget=POINT_BUDGET,
           threshold=POINT_PIXELS, deepest=None):
    """Клетки облака для кадра.

    frame - lod._Frame камеры, ready - {клетка: количество точек}
    пришедших клеток (0 - пустая), info_of(клетка) - lod.TileInfo.
    Делится клетка с наибольшей экранной ошибкой, пока точек не больше
    budget. Клетка заменяется детьми, когда готовы все её видимые дети,
    до того рисуется она сама, а дети просятся."""
    deepest = max_level(cloud) if deepest is None else deepest
    root = (0, 0, 0)
    want = []
    info = info_of(root)
    if not frame.visible(3, info):
        return Selection([], [], 0)
    if root not in ready:
        return Selection([], [(0.0, root)], 0)
    total = ready[root]
    draw = {root}
    heap = [(-frame.error(info), root)]
    while heap:
        neg, key = heapq.heappop(heap)
        error = -neg
        if error <= threshold or key[0] >= deepest:
            continue
        kids = []
        missing = []
        for kid in children(key):
            kinfo = info_of(kid)
            if not frame.visible(3, kinfo):
                continue
            if kid in ready:
                kids.append((kid, kinfo))
            else:
                missing.append(kid)
        if missing:
            for kid in missing:
                want.append((priority(error, kid[0]), kid))
            continue
        added = sum(ready[kid] for kid, _ in kids)
        if total - ready[key] + added > budget:
            continue
        draw.discard(key)
        total += added - ready[key]
        for kid, kinfo in kids:
            if ready[kid]:
                draw.add(kid)
            heapq.heappush(heap, (-frame.error(kinfo), kid))
    want.sort()
    return Selection(sorted(draw), want, total)


def pipeline(source, cloud, key, out, out_srs="EPSG:4326", requests=None):
    """Конвейер PDAL клетки: readers.copc по рамке и шагу, пересчёт
    в out_srs, LAS 1.4 формата 7 без сжатия в файл out. requests -
    потоков чтения файла, None - по умолчанию PDAL."""
    x0, y0, x1, y1 = bounds(cloud, key)
    reader = {"type": "readers.copc", "filename": source,
              "bounds": "([{!r}, {!r}], [{!r}, {!r}])".format(x0, x1, y0,
                                                              y1),
              "resolution": resolution(cloud, key[0])}
    if requests:
        reader["requests"] = int(requests)
    stages = [
        reader,
        {"type": "filters.reprojection", "out_srs": out_srs},
        {"type": "writers.las", "filename": out, "compression": False,
         "minor_version": 4, "dataformat_id": 7,
         "scale_x": 1e-7, "scale_y": 1e-7, "scale_z": 0.001,
         "offset_x": "auto", "offset_y": "auto", "offset_z": "auto"}]
    return json.dumps({"pipeline": stages})


def convert_pipeline(source, out):
    """Конвейер PDAL перевода LAS или LAZ в COPC."""
    return json.dumps({"pipeline": [
        {"type": "readers.las", "filename": source},
        {"type": "writers.copc", "filename": out}]})


def _ramp(share, stops):
    share = np.clip(np.nan_to_num(share), 0.0, 1.0)
    at = np.array([s for s, _ in stops])
    rgb = np.array([c for _, c in stops], dtype=np.float64)
    return np.stack([np.interp(share, at, rgb[:, i]) for i in range(3)],
                    axis=-1).astype(np.uint8)


def colors(points, mode, zrange=None, alpha=255):
    """Цвета точек (n, 4) uint8. mode - "rgb" (без цвета в файле -
    по классу), "class", "height" (zrange - отметки низа и верха шкалы),
    "intensity"."""
    count = len(points.x)
    if mode == "rgb" and points.rgb is not None:
        rgb = points.rgb
    elif mode == "height":
        low, high = zrange if zrange else (float(np.min(points.z)),
                                           float(np.max(points.z)))
        rgb = _ramp((points.z - low) / max(high - low, 1e-9), HEIGHT_STOPS)
    elif mode == "intensity":
        values = points.intensity.astype(np.float64)
        top = float(np.percentile(values, 98)) if count else 1.0
        gray = np.clip(values / max(top, 1.0) * 255.0, 0, 255)
        rgb = np.repeat(gray.astype(np.uint8)[:, None], 3, axis=1)
    else:
        table = np.array([CLASS_COLORS.get(c, OTHER_COLOR)
                          for c in range(256)], dtype=np.uint8)
        rgb = table[points.cls]
    out = np.empty((count, 4), dtype=np.uint8)
    out[:, :3] = rgb
    out[:, 3] = alpha
    return out


def anchor(cloud, key, to_geo):
    """Центр клетки на эллипсоиде в ECEF и нормаль в нём - от них
    вершины клетки (vertices), высоту с масштабом рельефа ставит
    шейдер."""
    x0, y0, x1, y1 = bounds(cloud, key)
    lons, lats = to_geo(np.array([(x0 + x1) / 2.0]),
                        np.array([(y0 + y1) / 2.0]))
    lat, lon = float(np.asarray(lats)[0]), float(np.asarray(lons)[0])
    center = np.array(ellipsoid.geodetic_to_ecef(lat, lon, 0.0),
                      dtype=np.float64)
    up = np.array(ellipsoid.surface_normal(lat, lon), dtype=np.float64)
    return center, up / np.linalg.norm(up)


def vertices(points, center, zfactor):
    """Вершины клетки: смещения точек на эллипсоиде от центра клетки
    в ECEF (float32, n × 3) и отметки в метрах (float32). Высоту на
    экране шейдер ставит вдоль нормали клетки - масштаб рельефа
    меняется без нового чтения точек. Нормаль одна на клетку: у клетки
    в километр с высотой 1700 м при масштабе 2 сдвиг точки меньше 0.3 м."""
    xyz = ellipsoid.geodetic_to_ecef(np.asarray(points.y, dtype=np.float64),
                                     np.asarray(points.x, dtype=np.float64),
                                     np.zeros(len(points.x)))
    xyz = np.stack(xyz, axis=-1) if isinstance(xyz, tuple) else xyz
    offsets = (xyz - np.asarray(center, dtype=np.float64)).astype(np.float32)
    heights = (np.asarray(points.z, dtype=np.float64) * zfactor) \
        .astype(np.float32)
    return offsets, heights


def keep_classes(points, allowed):
    """Точки только классов allowed (множество), None - все."""
    if allowed is None:
        return points
    mask = np.isin(points.cls, np.array(sorted(allowed), dtype=np.uint8))
    rgb = points.rgb[mask] if points.rgb is not None else None
    return Points(points.x[mask], points.y[mask], points.z[mask],
                  points.cls[mask], rgb, points.intensity[mask])


SIZES = (1.0, 2.0, 3.0, 4.0, 6.0)  # размеры точки в меню слоя
PICK_PIXELS = 6.0  # точка облака под курсором - не дальше, пикселей
PICK_LIMIT = 4000  # точек запроса опроса, не больше


def style(data):
    """Настройки облака из записи проекта: цвет, размер точки, классы
    (None - все). Неизвестное заменяется умолчанием."""
    data = data if isinstance(data, dict) else {}
    mode = data.get("mode") if data.get("mode") in MODES else "rgb"
    try:
        size = float(data.get("size", POINT_SIZE))
    except (TypeError, ValueError):
        size = POINT_SIZE
    size = min(max(size, 1.0), 16.0)
    classes = data.get("classes")
    if isinstance(classes, (list, tuple)):
        classes = sorted({int(c) for c in classes
                          if isinstance(c, (int, float)) and 0 <= c < 256})
    else:
        classes = None
    return {"mode": mode, "size": size, "classes": classes}


def ray_span(origin, direction, low, high):
    """Отрезок луча взгляда между высотами high и low над эллипсоидом:
    две точки ECEF или None, если луч не доходит до high."""
    o = np.asarray(origin, dtype=np.float64)
    d = np.asarray(direction, dtype=np.float64)
    d = d / np.linalg.norm(d)
    far = ellipsoid.ray_intersect(o, d, high)
    if far is None:
        return None
    near = ellipsoid.ray_intersect(o, d, low)
    if near is None:
        # Луч уходит в небо, не дойдя до низа облака: отрезок длиной
        # в толщину облака от встречи с верхом.
        near = far + float(high - low)
    return o + d * float(far), o + d * float(near)


def pick(pixels, front, distances, px, py, limit=PICK_PIXELS):
    """Номер точки под курсором: ближайшая на экране не дальше limit
    пикселей, из равных - ближняя к глазу. None - такой нет."""
    pixels = np.asarray(pixels, dtype=np.float64)
    if not len(pixels):
        return None
    gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
    good = np.asarray(front, dtype=bool) & (gap <= limit)
    if not good.any():
        return None
    order = np.lexsort((np.asarray(distances, dtype=np.float64)[good],
                        np.round(gap[good])))
    return int(np.flatnonzero(good)[order[0]])

