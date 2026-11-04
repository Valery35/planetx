# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Трассировка участка снимка в многоугольники по цветам.

Просьба автора от 3 ноября 2026 года по образцу «Векторизации растра»
Inkscape и сообщения Василия Швалёва - снимок раскладывается на цвета,
области обводятся гладкими контурами методом Potrace (Selinger 2003).

Порядок:
- сглаживание снимка окном 3 × 3 (blur) - меньше шума на границах;
- цвета k-средними по каналам, приведённым к разбросу 1 (quantize);
- связные области одного цвета (regions), области меньше least клеток
  сливаются с соседом по самой длинной общей границе (merge_small);
- границы клеток между областями - цепочки между узлами, где сходятся
  три области и больше (chains). У соседних областей цепочка общая
  и сглаживается один раз, поэтому щелей и наложений между
  многоугольниками нет;
- цепочка упрощается Дугласом-Пекером и сглаживается кривыми Безье по
  правилу углов Potrace: вершина с alpha не ниже corner остаётся углом
  (smooth_chain);
- кольца областей собираются из цепочек (rings).

Координаты - углы клеток: x - столбец, y - строка сверху вниз.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import rasterclass, segments
except ImportError:  # headless-тесты
    import rasterclass
    import segments

COLORS = 8  # цветов по умолчанию
SMOOTH = 1  # проходов сглаживания снимка
LEAST = 25  # клеток в наименьшей области
CORNER = 1.0  # alphamax Potrace: выше - круглее, 0 - одни углы
TOLERANCE = 0.75  # клетки, допуск упрощения ломаной по границе клеток
SAMPLE = 100000  # клеток для поиска цветов
ROUNDS = 25  # проходов k-средних
CURVE_STEP = 1.0  # клетки между точками кривой
CURVE_POINTS = 16  # точек на кривую не больше
MERGE_ROUNDS = 30  # проходов слияния мелких областей


def blur(grid, good, passes=SMOOTH):
    """Среднее окна 3 × 3 по клеткам good, passes раз. Клетки вне good
    в среднее не входят и остаются прежними."""
    out = np.array(grid, dtype=np.float64)
    if passes <= 0:
        return out.astype(np.float32)
    weight = good.astype(np.float64)
    count = _box3(weight)
    for _ in range(passes):
        for band in range(out.shape[0]):
            value = np.where(good, out[band], 0.0)
            total = _box3(value)
            out[band] = np.where(good, total / np.maximum(count, 1.0),
                                 out[band])
    return out.astype(np.float32)


def _box3(values):
    padded = np.pad(values, 1)
    rows, cols = values.shape
    total = np.zeros(values.shape, dtype=np.float64)
    for dr in range(3):
        for dc in range(3):
            total += padded[dr:dr + rows, dc:dc + cols]
    return total


def quantize(grid, good, count=COLORS, seed=0):
    """Цвета клеток: (номера цветов клеток int32, -1 вне good, средние
    значения каналов цветов (цвета, каналы)). Каналы приводятся к разбросу
    1, цвета ищутся k-средними по выборке до SAMPLE клеток."""
    rows, cols = good.shape
    labels = np.full((rows, cols), -1, dtype=np.int32)
    cells = int(good.sum())
    if not cells:
        return labels, np.zeros((0, grid.shape[0]))
    mean, spread = rasterclass.scales(grid, good)
    spread = np.where(spread > 0.0, spread, 1.0)
    data = ((grid[:, good].astype(np.float64) - mean[:, None])
            / spread[:, None]).T
    rng = np.random.default_rng(seed)
    pick = data if cells <= SAMPLE else data[rng.choice(cells, SAMPLE,
                                                        replace=False)]
    centers = _seeds(pick, min(count, len(pick)), rng)
    for _ in range(ROUNDS):
        near = _nearest(pick, centers)
        moved = centers.copy()
        for n in range(len(centers)):
            mine = pick[near == n]
            if len(mine):
                moved[n] = mine.mean(axis=0)
        if np.allclose(moved, centers):
            break
        centers = moved
    near = _nearest(data, centers)
    used, near = np.unique(near, return_inverse=True)
    labels[good] = near.astype(np.int32)
    raw = grid[:, good].astype(np.float64).T
    sums = np.zeros((len(used), grid.shape[0]))
    np.add.at(sums, near, raw)
    sizes = np.bincount(near, minlength=len(used)).astype(np.float64)
    return labels, sums / sizes[:, None]


def _seeds(data, count, rng):
    """Начальные цвета k-means++: каждый следующий - с вероятностью по
    квадрату расстояния до ближайшего прежнего."""
    centers = [data[int(rng.integers(len(data)))]]
    far = ((data - centers[0]) ** 2).sum(axis=1)
    for _ in range(1, count):
        total = far.sum()
        if total <= 0.0:
            break
        choice = int(np.searchsorted(np.cumsum(far), rng.random() * total))
        centers.append(data[min(choice, len(data) - 1)])
        far = np.minimum(far, ((data - centers[-1]) ** 2).sum(axis=1))
    return np.array(centers)


def _nearest(data, centers, chunk=200000):
    out = np.empty(len(data), dtype=np.int64)
    for start in range(0, len(data), chunk):
        part = data[start:start + chunk]
        dist = ((part[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        out[start:start + chunk] = dist.argmin(axis=1)
    return out


def regions(colors):
    """Связные (по сторонам клеток) области одного цвета: номера областей
    клеток, -1 вне участка, и цвет каждой области."""
    has = colors >= 0
    cells = np.full(colors.shape, -1, dtype=np.int32)
    cells[has] = np.arange(int(has.sum()), dtype=np.int32)
    if not has.any():
        return cells, np.zeros(0, dtype=np.int32)
    return segments.dissolve(cells, colors[has].astype(np.int64))


def merge_small(colors, least=LEAST):
    """Области меньше least клеток перекрашиваются в цвет соседа по самой
    длинной общей границе, крупный сосед главнее мелкого. Итог - (номера
    областей, цвета областей, цвета клеток). Мелкая область без соседей
    на участке остаётся."""
    colors = colors.copy()
    for _ in range(MERGE_ROUNDS):
        parts, kinds = regions(colors)
        count = len(kinds)
        if count == 0 or least <= 1:
            return parts, kinds, colors
        sizes = np.bincount(parts[parts >= 0], minlength=count)
        small = sizes < least
        if not small.any():
            return parts, kinds, colors
        a = np.concatenate((parts[:, :-1].ravel(), parts[:-1, :].ravel(),
                            parts[:, 1:].ravel(), parts[1:, :].ravel()))
        b = np.concatenate((parts[:, 1:].ravel(), parts[1:, :].ravel(),
                            parts[:, :-1].ravel(), parts[:-1, :].ravel()))
        keep = (a >= 0) & (b >= 0) & (a != b)
        a, b = a[keep].astype(np.int64), b[keep].astype(np.int64)
        keep = small[a]
        a, b = a[keep], b[keep]
        if not len(a):
            return parts, kinds, colors
        pairs, shared = np.unique(a * count + b, return_counts=True)
        pa, pb = pairs // count, pairs % count
        # Мелкий сосед берёт цвет только у мелкого с большим номером:
        # два мелких не меняются цветами по кругу.
        allowed = ~small[pb] | (pb > pa)
        pa, pb, shared = pa[allowed], pb[allowed], shared[allowed]
        if not len(pa):
            return parts, kinds, colors
        score = shared + np.where(small[pb], 0, sizes.max() + 1)
        order = np.lexsort((-score, pa))
        first = np.ones(len(order), dtype=bool)
        first[1:] = pa[order][1:] != pa[order][:-1]
        target = np.arange(count)
        target[pa[order][first]] = pb[order][first]
        new = kinds[target]
        if (new == kinds).all():
            return parts, kinds, colors
        has = parts >= 0
        colors[has] = new[parts[has]]
    parts, kinds = regions(colors)
    return parts, kinds, colors


def chains(parts):
    """Цепочки границ клеток между областями: список (точки углов [(x, y)],
    область слева, область справа, замкнута ли, узел начала, узел конца,
    клетка слева у начала, клетка слева у конца). Направление - от начала
    к концу, «слева» - на экране со строками сверху вниз. -1 - вне участка.
    У замкнутой цепочки узлов нет (None)."""
    rows, cols = parts.shape
    padded = np.full((rows + 2, cols + 2), -1, dtype=np.int64)
    padded[1:-1, 1:-1] = parts
    width = cols + 2
    span = cols + 1
    # Отвесные трещины: между клетками (r, c - 1) и (r, c), вниз от угла
    # (r, c) к (r + 1, c). Слева при ходе вниз - восточная клетка.
    r, c = np.mgrid[0:rows, 0:cols + 1]
    east = padded[r + 1, c + 1]
    west = padded[r + 1, c]
    cut = east != west
    vu = (r * span + c)[cut]
    vv = ((r + 1) * span + c)[cut]
    vl, vr = east[cut], west[cut]
    vlp = ((r + 1) * width + c + 1)[cut]
    vrp = ((r + 1) * width + c)[cut]
    # Ровные трещины: между (r - 1, c) и (r, c), вправо от угла (r, c)
    # к (r, c + 1). Слева при ходе вправо - северная клетка.
    r, c = np.mgrid[0:rows + 1, 0:cols]
    north = padded[r, c + 1]
    south = padded[r + 1, c + 1]
    cut = north != south
    hu = (r * span + c)[cut]
    hv = (r * span + c + 1)[cut]
    hl, hr = north[cut], south[cut]
    hlp = (r * width + c + 1)[cut]
    hrp = ((r + 1) * width + c + 1)[cut]
    u = np.concatenate((vu, hu))
    v = np.concatenate((vv, hv))
    left = np.concatenate((vl, hl))
    right = np.concatenate((vr, hr))
    lpix = np.concatenate((vlp, hlp))
    rpix = np.concatenate((vrp, hrp))
    total = len(u)
    if not total:
        return []
    ends = np.concatenate((u, v))
    edge = np.concatenate((np.arange(total), np.arange(total)))
    order = np.argsort(ends, kind="stable")
    ends, edge = ends[order], edge[order]
    corners, first, degree = np.unique(ends, return_index=True,
                                       return_counts=True)
    slot = {}
    for corner, at, deg in zip(corners.tolist(), first.tolist(),
                               degree.tolist()):
        slot[corner] = (at, deg)
    edge = edge.tolist()
    u, v = u.tolist(), v.tolist()
    left, right = left.tolist(), right.tolist()
    lpix, rpix = lpix.tolist(), rpix.tolist()
    seen = bytearray(total)
    out = []

    def walk(start, e):
        points = [start]
        cur = start
        first_e, first_fw = e, u[e] == start
        while True:
            seen[e] = 1
            forward = u[e] == cur
            nxt = v[e] if forward else u[e]
            points.append(nxt)
            at, deg = slot[nxt]
            if deg != 2 or nxt == start:
                return points, first_e, first_fw, e, forward
            a, b = edge[at], edge[at + 1]
            e = b if a == e else a
            cur = nxt

    def record(points, fe, ffw, le, lfw, closed):
        xy = [(p % span, p // span) for p in points]
        out.append((xy, left[fe] if ffw else right[fe],
                    right[fe] if ffw else left[fe], closed,
                    None if closed else points[0],
                    None if closed else points[-1],
                    lpix[fe] if ffw else rpix[fe],
                    lpix[le] if lfw else rpix[le]))

    for corner, (at, deg) in slot.items():
        if deg == 2:
            continue
        for k in range(at, at + deg):
            e = edge[k]
            if not seen[e]:
                record(*walk(corner, e), False)
    for e in range(total):
        if not seen[e]:
            record(*walk(u[e], e), True)
    return out


def simplify(points, tolerance=TOLERANCE, closed=False):
    """Ломаная Дугласа-Пекера: (n, 2) float. У замкнутой первая точка
    повторена в конце, её место - как у открытой."""
    pts = np.asarray(points, dtype=np.float64)
    if len(pts) <= 2:
        return pts
    if closed:
        # Замкнутую делит пополам самая дальняя от начала точка.
        far = int(np.argmax(((pts - pts[0]) ** 2).sum(axis=1)))
        if far == 0:
            return pts[:1]
        one = simplify(pts[:far + 1], tolerance)
        two = simplify(pts[far:], tolerance)
        return np.concatenate((one, two[1:]))
    keep = np.zeros(len(pts), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(pts) - 1)]
    while stack:
        lo, hi = stack.pop()
        if hi - lo < 2:
            continue
        a, b = pts[lo], pts[hi]
        seg = b - a
        length = math.hypot(seg[0], seg[1])
        mid = pts[lo + 1:hi]
        if length == 0.0:
            dist = np.hypot(mid[:, 0] - a[0], mid[:, 1] - a[1])
        else:
            dist = np.abs(seg[0] * (mid[:, 1] - a[1])
                          - seg[1] * (mid[:, 0] - a[0])) / length
        n = int(np.argmax(dist))
        if dist[n] > tolerance:
            keep[lo + 1 + n] = True
            stack.append((lo, lo + 1 + n))
            stack.append((lo + 1 + n, hi))
    return pts[keep]


def corner_alpha(prev, vertex, nxt):
    """alpha вершины по правилу Potrace: отход вершины от прямой соседей,
    отнесённый к длине L1 этой прямой. 0 - прямая, больше - острее."""
    dx, dy = nxt[0] - prev[0], nxt[1] - prev[1]
    denom = abs(dx) + abs(dy)
    if denom == 0.0:
        return 4.0 / 3.0
    cross = abs((vertex[0] - prev[0]) * dy - (vertex[1] - prev[1]) * dx)
    dd = cross / denom
    return (1.0 - 1.0 / dd) / 0.75 if dd > 1.0 else 0.0


def _bezier(p0, p1, p2, p3):
    chord = math.hypot(p3[0] - p0[0], p3[1] - p0[1]) \
        + math.hypot(p1[0] - p0[0], p1[1] - p0[1]) \
        + math.hypot(p3[0] - p2[0], p3[1] - p2[1])
    count = max(2, min(CURVE_POINTS, int(chord / CURVE_STEP)))
    out = []
    for k in range(1, count + 1):
        t = k / float(count)
        s = 1.0 - t
        out.append((s * s * s * p0[0] + 3 * s * s * t * p1[0]
                    + 3 * s * t * t * p2[0] + t * t * t * p3[0],
                    s * s * s * p0[1] + 3 * s * s * t * p1[1]
                    + 3 * s * t * t * p2[1] + t * t * t * p3[1]))
    return out


def smooth_chain(points, closed=False, corner=CORNER, tolerance=TOLERANCE):
    """Гладкая цепочка: упрощение и кривые Безье Potrace. У открытой концы
    на месте - это узлы, общие с другими цепочками. Итог - [(x, y)],
    у замкнутой первая точка повторена в конце."""
    poly = simplify(points, tolerance, closed)
    if closed:
        ring = [tuple(p) for p in poly[:-1]]
        if len(ring) < 3:
            return [tuple(p) for p in poly]
        n = len(ring)
        mids = [((ring[i][0] + ring[(i + 1) % n][0]) / 2.0,
                 (ring[i][1] + ring[(i + 1) % n][1]) / 2.0)
                for i in range(n)]
        out = [mids[-1]]
        for j in range(n):
            out += _around(ring[j - 1], ring[j], ring[(j + 1) % n],
                           mids[j - 1], mids[j], corner)
        return out
    verts = [tuple(p) for p in poly]
    if len(verts) <= 2:
        return verts
    out = [verts[0]]
    mids = [((verts[i][0] + verts[i + 1][0]) / 2.0,
             (verts[i][1] + verts[i + 1][1]) / 2.0)
            for i in range(len(verts) - 1)]
    out.append(mids[0])
    for j in range(1, len(verts) - 1):
        out += _around(verts[j - 1], verts[j], verts[j + 1], mids[j - 1],
                       mids[j], corner)
    out.append(verts[-1])
    return out


def _around(prev, vertex, nxt, start, end, corner):
    """Путь от середины start до середины end мимо вершины: угол или
    кривая Безье с контрольными точками к вершине на долю alpha."""
    alpha = corner_alpha(prev, vertex, nxt)
    if alpha >= corner:
        return [vertex, end]
    alpha = min(max(alpha, 0.55), 1.0)
    c1 = (start[0] + alpha * (vertex[0] - start[0]),
          start[1] + alpha * (vertex[1] - start[1]))
    c2 = (end[0] + alpha * (vertex[0] - end[0]),
          end[1] + alpha * (vertex[1] - end[1]))
    return _bezier(start, c1, c2, end)


def ring_area(ring):
    """Площадь кольца со знаком, в клетках."""
    pts = np.asarray(ring, dtype=np.float64)
    x, y = pts[:, 0], pts[:, 1]
    return 0.5 * float((x * np.roll(y, -1) - np.roll(x, -1) * y).sum())


def rings(found, corner=CORNER, tolerance=TOLERANCE, progress=None):
    """Многоугольники областей: {область: (наружное кольцо, [дыры])},
    кольца - [(x, y)] с повтором первой точки. found - итог chains.
    progress зовётся раз на тысячу цепочек."""
    smooth = []
    for n, item in enumerate(found):
        if progress is not None and n % 1000 == 0:
            progress()
        smooth.append(smooth_chain(item[0], item[3], corner, tolerance))
    starts = {}
    for n, item in enumerate(found):
        if item[3]:
            continue
        for forward in (True, False):
            region = item[1] if forward else item[2]
            if region < 0:
                continue
            node = item[4] if forward else item[5]
            starts.setdefault((node, region), []).append((n, forward))
    loops = {}
    used = set()
    for n, item in enumerate(found):
        if item[3]:
            for forward in (True, False):
                region = item[1] if forward else item[2]
                if region >= 0:
                    pts = smooth[n] if forward else smooth[n][::-1]
                    loops.setdefault(region, []).append(list(pts))
            continue
        for forward in (True, False):
            region = item[1] if forward else item[2]
            if region < 0 or (n, forward) in used:
                continue
            ring = _assemble(found, smooth, starts, used, n, forward,
                             region)
            if ring is not None:
                loops.setdefault(region, []).append(ring)
    out = {}
    for region, all_rings in loops.items():
        sized = sorted(all_rings, key=lambda r: -abs(ring_area(r)))
        out[region] = (sized[0], sized[1:])
    return out


def _assemble(found, smooth, starts, used, n, forward, region):
    """Кольцо области region из цепочек от направленной цепочки n: на узле
    следующая - цепочка с той же областью слева, при двух - та, что
    огибает ту же клетку."""
    ring = []
    cur = (n, forward)
    for _ in range(len(found) + 1):
        used.add(cur)
        k, fw = cur
        pts = smooth[k] if fw else smooth[k][::-1]
        ring += pts[:-1]
        item = found[k]
        node = item[5] if fw else item[4]
        pixel = item[7] if fw else item[6]
        options = [d for d in starts.get((node, region), ())
                   if d not in used or d == (n, forward)]
        if not options:
            return None
        nxt = options[0]
        if len(options) > 1:
            for d in options:
                other = found[d[0]]
                if (other[6] if d[1] else other[7]) == pixel:
                    nxt = d
                    break
        if nxt == (n, forward):
            ring.append(ring[0])
            return ring
        cur = nxt
    return None


def trace(grid, good, colors=COLORS, smooth=SMOOTH, least=LEAST,
          corner=CORNER, progress=None):
    """Трассировка сетки grid (каналы, строки, столбцы) по клеткам good:
    {"classes": цвета клеток, "kinds": цвета областей, "parts": области,
    "centers": средние каналы цветов, "shapes": {область: кольца}}."""
    values = blur(grid, good, smooth)
    if progress is not None:
        progress()
    classes, centers = quantize(values, good, colors)
    if progress is not None:
        progress()
    parts, kinds, classes = merge_small(classes, least)
    if progress is not None:
        progress()
    found = chains(parts)
    shapes = rings(found, corner, progress=progress)
    return {"classes": classes, "kinds": kinds, "parts": parts,
            "centers": centers, "shapes": shapes}


def class_shapes(classes, least=LEAST, corner=CORNER, progress=None):
    """Сглаженные многоугольники классов окна «Распознавание»: области
    меньше least клеток сливаются с соседом, границы - цепочки, общие
    у соседних областей, сглаживание Potrace. Итог - {"kinds": класс
    области, "shapes": {область: кольца}}, классы растра не меняются."""
    parts, kinds, _ = merge_small(np.asarray(classes, dtype=np.int64), least)
    if progress is not None:
        progress()
    found = chains(parts)
    return {"kinds": kinds, "shapes": rings(found, corner,
                                            progress=progress)}


def join_colors(target):
    """Цвета трассировки в классы: target[n] - цвет, с которым слит цвет
    n, сам n или -1 - не слит. Цепочка слияний доходит до цвета, который
    не слит, у круга слияний класс - наименьший цвет круга. Итог -
    (lookup, keep): lookup[n] - номер класса цвета n, keep - цвета-классы
    по порядку."""
    count = len(target)
    roots = []
    for n in range(count):
        path = [n]
        m = n
        while 0 <= target[m] < count and target[m] != m:
            m = int(target[m])
            if m in path:
                m = min(path[path.index(m):])
                break
            path.append(m)
        roots.append(m)
    keep = sorted(set(roots))
    lookup = np.array([keep.index(r) for r in roots], dtype=np.int64)
    return lookup, keep


def joined(classes, kinds, lookup):
    """Цвета клеток и областей после слияния в классы, -1 остаётся."""
    classes = np.asarray(classes)
    kinds = np.asarray(kinds)
    lookup = np.asarray(lookup)
    return (np.where(classes >= 0, lookup[np.maximum(classes, 0)], -1),
            np.where(kinds >= 0, lookup[np.maximum(kinds, 0)], -1))


def ranked_colors(grid, good, count=COLORS, smooth=SMOOTH, least=LEAST):
    """Цвета снимка окна «Распознавание», источник «Цвета снимка» -
    сглаживание, k-средние и слияние мелких областей, как у трассировки.
    Цвета идут по убыванию доли участка. Итог - (номер цвета клетки,
    -1 вне good, средние каналов цветов в том же порядке)."""
    labels, _ = quantize(blur(grid, good, smooth), good, count)
    _, _, labels = merge_small(labels, least)
    cells = np.full(good.shape, -1, dtype=np.int64)
    has = labels >= 0
    if not has.any():
        return cells, np.zeros((0, grid.shape[0]))
    sizes = np.bincount(labels[has])
    used = np.flatnonzero(sizes)
    order = used[np.argsort(-sizes[used], kind="stable")]
    rank = np.full(len(sizes), -1, dtype=np.int64)
    rank[order] = np.arange(len(order))
    cells[has] = rank[labels[has]]
    data = grid[:, has].astype(np.float64)
    centers = np.full((len(order), grid.shape[0]), np.nan)
    for band in range(grid.shape[0]):
        values = data[band]
        fine = np.isfinite(values)
        sums = np.bincount(cells[has][fine], values[fine],
                           minlength=len(order))
        found = np.bincount(cells[has][fine], minlength=len(order))
        centers[:, band] = np.where(found > 0,
                                    sums / np.maximum(found, 1), np.nan)
    return cells, centers


def display_colors(centers):
    """Цвета RGB 0-255 цветов трассировки: первые три канала (один канал -
    серый). Значения 0-255 берутся как есть, отражение 0-1 и прочие -
    растяжением по цветам."""
    centers = np.asarray(centers, dtype=np.float64)
    if not len(centers):
        return []
    rgb = centers[:, :3] if centers.shape[1] >= 3 \
        else np.repeat(centers[:, :1], 3, axis=1)
    if rgb.min() < 0.0 or rgb.max() > 255.0 or rgb.max() <= 1.5:
        low, high = rgb.min(axis=0), rgb.max(axis=0)
        rgb = 255.0 * (rgb - low) / np.where(high > low, high - low, 1.0)
    rgb = np.clip(np.round(rgb), 0, 255).astype(int)
    return [tuple(int(v) for v in row) for row in rgb]
