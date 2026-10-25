# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вода по рельефу: затопление от точки до уровня, линия стока,
водосбор от точки.

Решение автора от 25 октября 2026 года - «делай 1 и 2, посмотри
Isoliner, там это реализовано». Ядро стока перенесено из Isoliner:
заполнение понижений (hydro_fill), направления D8 и аккумуляция
(topo_flow), морфометрия водосбора (topo_gauge). Здесь - сетка высот
вокруг точки и то, что глобусу нужно поверх ядра.

Сетка - узлы Web Mercator с равным шагом на местности в середине
участка. Шаг по осям Меркатора - шаг на местности, делённый на
косинус широты середины. На участке в десятки километров масштаб по
широте меняется меньше чем на процент. Строка 0 - северная, как у
topo_flow.

Затопление - уровень перелива. Для каждого узла это наименьший
уровень воды, при котором вода от точки доходит до него, то есть
наименьший по всем путям наибольший рельеф пути. Его даёт то же
заполнение понижений с единственным стоком в точке и без уклона
(fill_depressions(outlets=)). Узел затоплен водой уровня H, если
уровень перелива ниже H, поэтому смена уровня - одно сравнение
массива. Котловины, не связанные с точкой, остаются сухими. В
Isoliner полигон затопления связность не проверял.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import contours, topo_flow, topo_gauge
    from .hydro_fill import fill_depressions
except ImportError:  # headless-тесты
    import contours
    import topo_flow
    import topo_gauge
    from hydro_fill import fill_depressions

# Узлов сетки поперёк участка: шаг - диаметр / SIDE, но не мельче
# пикселя высот. 600 × 600 узлов заполняются за доли секунды - выбор
# помощника, утверждает автор.
SIDE = 600
# Стена вместо пустых высот у затопления: вода через неё не идёт.
WALL = 1e20
# Проходов заполнения у уровня перелива: путь от одной точки бывает
# извилистым, ему нужно больше проходов, чем стоку к краю.
SPILL_PASSES = 1000
# Уклон на плоских участках у заполнения для стока, м на ячейку.
EPSILON = 0.001
# Притяжка точки водосбора к водотоку: радиус SNAP_METRES, но не
# меньше SNAP_CELLS ячеек. Щелчок по реке на глобусе промахивается
# на десятки метров - выбор помощника.
SNAP_CELLS = 3
SNAP_METRES = 150.0
# Водотоки сети в отчёте водосбора - с водосбором от NET_AREA, м².
NET_AREA = 1e6
# Узлов сетки поверхности воды по стороне.
WATER_SIDE = 256

Grid = namedtuple("Grid", "lat lon x0 y0 step cell rows cols")
Grid.__doc__ = """Сетка высот вокруг точки lat, lon. x0, y0 - узел
[0, 0] в метрах Web Mercator (северо-западный), step - шаг в метрах
Меркатора, cell - шаг на местности в метрах, rows и cols - размер."""


def make_grid(lat, lon, radius_m, cell, radius):
    """Сетка квадрата со стороной 2 radius_m с серединой lat, lon, шаг
    на местности не мельче cell и не больше SIDE узлов поперёк. radius -
    радиус тела, метры."""
    cell = max(float(cell), 2.0 * radius_m / SIDE)
    n = int(math.ceil(2.0 * radius_m / cell)) | 1
    scale = 1.0 / max(math.cos(math.radians(lat)), 1e-6)
    step = cell * scale
    x, y = mercator(lat, lon, radius)
    half = (n - 1) / 2.0
    return Grid(lat, lon, x - half * step, y + half * step, step, cell, n, n)


def mercator(lat, lon, radius):
    """Широта и долгота в метрах Web Mercator."""
    lat = np.radians(np.clip(lat, -85.0511, 85.0511))
    return (radius * np.radians(lon),
            radius * np.log(np.tan(math.pi / 4.0 + lat / 2.0)))


def latlon(grid, rows, cols, radius):
    """Широта и долгота узлов с номерами rows, cols (можно дробными)."""
    x = grid.x0 + np.asarray(cols, dtype=np.float64) * grid.step
    y = grid.y0 - np.asarray(rows, dtype=np.float64) * grid.step
    lat = np.degrees(2.0 * np.arctan(np.exp(y / radius)) - math.pi / 2.0)
    return lat, np.degrees(x / radius)


def nodes(grid, radius, stride=1):
    """Широты и долготы всех узлов (rows, cols), через stride."""
    r = np.arange(0, grid.rows, stride)
    c = np.arange(0, grid.cols, stride)
    cols, rows = np.meshgrid(c, r)
    return latlon(grid, rows, cols, radius)


def index_of(grid, lat, lon, radius):
    """Узел (строка, столбец), ближайший к точке."""
    x, y = mercator(lat, lon, radius)
    c = int(round((float(x) - grid.x0) / grid.step))
    r = int(round((grid.y0 - float(y)) / grid.step))
    return (min(max(r, 0), grid.rows - 1), min(max(c, 0), grid.cols - 1))


# --- затопление ------------------------------------------------------------

def spill_levels(z, seed):
    """Уровень перелива от узла seed (строка, столбец): массив той же
    формы. Пустые высоты (NaN) - стена, у них inf."""
    z = np.asarray(z, dtype=np.float64)
    empty = ~np.isfinite(z)
    work = np.where(empty, WALL, z)
    outlets = np.zeros(z.shape, dtype=bool)
    outlets[seed] = True
    levels, _, _ = fill_depressions(work, epsilon=0.0, outlets=outlets,
                                    max_passes=SPILL_PASSES)
    levels[empty | (levels >= WALL)] = np.inf
    return levels


Flood = namedtuple("Flood", "mask area volume depth edge")
Flood.__doc__ = """Затопление уровнем: mask - затопленные узлы, area -
площадь, м², volume - объём воды, м³, depth - наибольшая глубина, м,
edge - вода дошла до края сетки и может идти дальше."""


def flood(z, levels, level, cell):
    """Затопление водой уровня level по уровню перелива levels."""
    z = np.asarray(z, dtype=np.float64)
    mask = levels < float(level)
    if not mask.any():
        return Flood(mask, 0.0, 0.0, 0.0, False)
    depth = float(level) - z[mask]
    area = float(cell) ** 2
    edge = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any()
                or mask[:, -1].any())
    return Flood(mask, area * int(mask.sum()), area * float(depth.sum()),
                 float(depth.max()), edge)


def water_nodes(mask, side=WATER_SIDE):
    """Узлы поверхности воды не больше side по стороне: (шаг, маска
    узлов). Узел мокрый, если затоплен любой узел его клетки - иначе
    узкая протока пропадала бы между узлами. Лишняя вода у берега
    уходит под рельеф и не видна."""
    stride = max(1, int(math.ceil(max(mask.shape) / float(side))))
    if stride == 1:
        return 1, mask
    rows = int(math.ceil(mask.shape[0] / float(stride))) * stride
    cols = int(math.ceil(mask.shape[1] / float(stride))) * stride
    padded = np.zeros((rows, cols), dtype=bool)
    padded[:mask.shape[0], :mask.shape[1]] = mask
    blocks = padded.reshape(rows // stride, stride, cols // stride, stride)
    return stride, blocks.any(axis=(1, 3))


# --- сток ------------------------------------------------------------------

def drainage(z):
    """Решётка стока: (заполненные высоты, downstream, пустые узлы).
    Пустые высоты (NaN) - край, вода уходит в них, как в Isoliner."""
    z = np.asarray(z, dtype=np.float64)
    empty = ~np.isfinite(z)
    filled, _, _ = fill_depressions(z, nodata_mask=empty, epsilon=EPSILON)
    _, downstream = topo_flow.d8_directions(filled, nodata_mask=empty)
    return filled, downstream, empty


Line = namedtuple("Line", "rows cols length drop end")
Line.__doc__ = """Линия стока: номера узлов rows, cols от старта вниз,
length - длина, м, drop - падение по исходным высотам, м, end - чем
кончилась: "edge" (край сетки), "pit" (сток, ниже некуда), "stream"
(дошла до водотока), "flat" (рельеф выположился), "merge" (влилась
в линию, построенную раньше)."""

# Короче MIN_LINE ячеек линии от метки не идут в ответ: старт у самой
# чужой линии сливается с ней через шаг.
MIN_LINE = 3


def flow_lines(z, seeds, cell, area=None, flat=None, merge=False):
    """Линии стока от узлов seeds - плоских номеров (инструмент 2.23
    Isoliner «Линии стока от точек, линий и контуров»). area - линия
    кончается на водотоке с водосбором от area м², flat - (уклон
    в градусах, длина участка в метрах): линия кончается, где средний
    уклон на этой длине ниже порога. merge - линия кончается, вливаясь
    в построенную раньше, без merge каждая идёт до конца. Со слиянием
    линии строятся от высоких узлов к низким: первые - самые длинные,
    узлы, через которые прошла линия, своих линий не дают."""
    filled, downstream, empty = drainage(z)
    shape = filled.shape
    if merge:
        seeds = np.asarray(list(seeds), dtype=np.int64)
        heights = np.nan_to_num(filled.ravel()[seeds], nan=-np.inf)
        seeds = seeds[np.argsort(-heights, kind="stable")]
    rivers = set()
    if area:
        acc = topo_flow.flow_accumulation(downstream, shape,
                                          nodata_mask=empty)
        rivers = set(int(i) for i in np.flatnonzero(
            acc.ravel() >= float(area) / float(cell) ** 2))
    owned = set()
    stop = set(rivers)
    out = []
    for start in seeds:
        start = int(start)
        if start in owned:
            continue
        path = topo_flow.trace_downhill(downstream, [start], shape,
                                        stop=stop)[0]
        if not path:
            continue
        last = int(path[-1])
        if len(path) > 1 and last in rivers:
            end = "stream"
        elif len(path) > 1 and last in owned:
            end = "merge"
        else:
            end = "pit"
        rows, cols = np.divmod(np.asarray(path, dtype=np.int64), shape[1])
        # По краю сетки D8 ведёт воду вдоль рамки до угла: линия
        # кончается на первом узле края, дальше рельефа нет.
        edge = np.flatnonzero((rows == 0) | (rows == shape[0] - 1)
                              | (cols == 0) | (cols == shape[1] - 1))
        if edge.size and (int(edge[0]) + 1 < len(path) or end == "pit"):
            path = path[:int(edge[0]) + 1]
            end = "edge"
        if flat:
            path, cut = topo_flow.cut_on_flattening(
                path, z, shape, float(cell),
                topo_flow.slope_from_degrees(flat[0]), float(flat[1]))
            if cut:
                end = "flat"
        path = [int(i) for i in path]
        if merge:
            # Обрезанное выполаживанием не занято: линия ниже по склону
            # может идти через эти узлы дальше.
            owned.update(path)
            stop.update(path)
        rows, cols = np.divmod(np.asarray(path, dtype=np.int64), shape[1])
        metrics = topo_flow.path_metrics(path, z, shape, float(cell))
        drop = metrics["drop"] if math.isfinite(metrics["drop"]) else 0.0
        out.append(Line(rows, cols, metrics["length"], drop, end))
    return out


def flow_line(z, seed, cell, area=None, flat=None):
    """Линия стока от узла seed по заполненному рельефу."""
    start = seed[0] * np.asarray(z).shape[1] + seed[1]
    return flow_lines(z, [start], cell, area=area, flat=flat)[0]


Region = namedtuple("Region", "mask area")
Region.__doc__ = """Бассейн квадрата: mask - узлы, area - площадь, м²."""


def outlet_basins(z, cell, area=NET_AREA):
    """Бассейны квадрата от устьев - узлов, где вода уходит из квадрата
    с водосбором от area м² (инструмент 2.07 Isoliner «Бассейны» без
    точек). Каждый узел квадрата получает бассейн своего устья, узлы
    с меньших устьев в ответ не идут. Крупные первыми."""
    filled, downstream, empty = drainage(z)
    shape = filled.shape
    acc = topo_flow.flow_accumulation(downstream, shape, nodata_mask=empty)
    labels = topo_flow.basins(downstream, shape, nodata_mask=empty, acc=acc,
                              threshold=max(1.0, float(area)
                                            / float(cell) ** 2))
    counts = np.bincount(labels.ravel())
    out = []
    for label in np.flatnonzero(counts):
        if label == 0:
            continue
        out.append(Region(labels == label,
                          float(counts[label]) * float(cell) ** 2))
    out.sort(key=lambda region: -region.area)
    return out


Basin = namedtuple("Basin", "mask seed report stream edge")
Basin.__doc__ = """Водосбор: mask - узлы водосбора, seed - створ после
притяжки к водотоку, report - словарь topo_gauge.REPORT_KEYS, stream -
главный водоток от створа к истоку (rows, cols), edge - водосбор дошёл
до края сетки и неполон."""


def watershed(z, seed, cell, snap=None):
    """Водосбор узла seed: створ притягивается к ячейке наибольшей
    аккумуляции в snap ячейках, как в инструменте «Бассейны» Isoliner.
    Без snap - SNAP_METRES, не меньше SNAP_CELLS."""
    if snap is None:
        snap = max(SNAP_CELLS, int(round(SNAP_METRES / float(cell))))
    filled, downstream, empty = drainage(z)
    shape = filled.shape
    acc = topo_flow.flow_accumulation(downstream, shape, nodata_mask=empty)
    r, c = topo_gauge.snap_to_max_acc(acc, seed[0], seed[1], snap)
    start = r * shape[1] + c
    z = np.asarray(z, dtype=np.float64)
    finite = z[np.isfinite(z)]
    interval = contours.grid_step(finite) if finite.size else 0.0
    report = topo_gauge.gauge_report(
        filled, downstream, acc, shape, start, float(cell),
        nodata_mask=empty, iso_interval=interval,
        net_threshold=NET_AREA / float(cell) ** 2)
    mask = topo_gauge.basin_mask(downstream, shape, start) & ~empty
    _, path = topo_gauge.trace_main_stream(downstream, acc, shape, start,
                                          float(cell))
    stream = np.divmod(np.asarray(path, dtype=np.int64), shape[1])
    edge = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any()
                or mask[:, -1].any())
    return Basin(mask, (r, c), report, stream, edge)


def shape_grid(points, radius, reach=3.0, least=2000.0, most=50000.0):
    """Середина и полусторона квадрата расчёта для метки: квадрат
    накрывает метку и reach её полуразмеров вокруг, не меньше least
    и не больше most метров. points - (широта, долгота)."""
    pts = np.radians(np.asarray(points, dtype=np.float64))
    lat0 = float(np.mean(pts[:, 0]))
    lon0 = float(np.mean(pts[:, 1]))
    north = (pts[:, 0] - lat0) * radius
    east = (pts[:, 1] - lon0) * radius * math.cos(lat0)
    half = float(max(np.abs(north).max(), np.abs(east).max()))
    side = min(max(half * reach, least), most)
    return math.degrees(lat0), math.degrees(lon0), side


def shape_seeds(grid, kind, points, radius):
    """Узлы сетки под меткой: у пути - вдоль линии, у многоугольника -
    внутренность и контур, у точки - узел точки (topo_gauge,
    инструмент 2.16 Isoliner «Водосбор линий и контуров»). Возвращает
    (плоские номера, длина метки в метрах)."""
    lats, lons = np.asarray(points, dtype=np.float64).T
    x, y = mercator(lats, lons, radius)
    cols = (x - grid.x0) / grid.step
    rows = (grid.y0 - y) / grid.step
    # Координаты узлов для topo_gauge: x - столбец, y - минус строка,
    # левый верхний угол клетки узла [0, 0] - (-0.5, 0.5).
    xy = list(zip(cols.tolist(), (-rows).tolist()))
    shape = (grid.rows, grid.cols)
    if kind == "polygon" and len(xy) >= 3:
        seeds = topo_gauge.cells_in_polygon([xy], -0.5, 0.5, 1.0, shape)
        length = topo_gauge.polyline_length(xy + xy[:1])
    else:
        seeds = topo_gauge.cells_along_polyline(xy, -0.5, 0.5, 1.0, shape)
        length = topo_gauge.polyline_length(xy)
    return seeds, length * grid.cell


Catchment = namedtuple("Catchment", "mask report edge")
Catchment.__doc__ = """Водосбор метки: mask - узлы, report - словарь
topo_gauge.DITCH_KEYS, edge - водосбор дошёл до края сетки."""


def shape_catchment(z, seeds, cell, length=None):
    """Водосбор узлов seeds - всё, откуда вода приходит в метку."""
    filled, downstream, empty = drainage(z)
    shape = filled.shape
    report = topo_gauge.ditch_report(filled, downstream, shape, seeds,
                                     float(cell), trace_len=length,
                                     nodata_mask=empty)
    mask = topo_gauge.catchment_mask(downstream, shape, seeds) & ~empty
    edge = bool(mask[0].any() or mask[-1].any() or mask[:, 0].any()
                or mask[:, -1].any())
    return Catchment(mask, report, edge)


Stream = namedtuple("Stream", "rows cols order area")
Stream.__doc__ = """Звено речной сети: узлы вниз по течению, порядок
по Стралеру и площадь водосбора в замыкании звена, м²."""


def rivers(z, cell, area=NET_AREA, order=1):
    """Речная сеть сетки - водотоки с водосбором от area м², звенья
    с порядком Стралера (topo_flow.river_network, инструмент 2.06
    Isoliner). order - наименьший порядок звена в ответе, порядки
    считаются по всей сети."""
    filled, downstream, empty = drainage(z)
    shape = filled.shape
    acc = topo_flow.flow_accumulation(downstream, shape, nodata_mask=empty)
    cells = max(1.0, float(area) / float(cell) ** 2)
    out = []
    for link in topo_flow.river_network(downstream, acc, cells, shape):
        if int(link["order"]) < order:
            continue
        chain = list(link["cells"])
        # Звено кончается перед узлом слияния: узел приёмника замыкает
        # линию, иначе звенья на глобусе шли бы с разрывами.
        nxt = int(downstream[chain[-1]])
        if nxt >= 0:
            chain.append(nxt)
        idx = np.asarray(chain, dtype=np.int64)
        if idx.size < 2:
            continue
        r, c = np.divmod(idx, shape[1])
        out.append(Stream(r, c, int(link["order"]),
                          float(link["acc_out"]) * float(cell) ** 2))
    return out


# --- контур ----------------------------------------------------------------

def outline(mask, tolerance=0.5):
    """Кольца границы маски в дробных номерах узлов (строка, столбец):
    список массивов (k, 2), первое - самое длинное. Граница проходит
    посередине между мокрым и сухим узлом, вершины упрощены по
    Дугласу-Пекеру с допуском tolerance ячеек."""
    padded = np.zeros((mask.shape[0] + 2, mask.shape[1] + 2))
    padded[1:-1, 1:-1] = mask
    rings = []
    for line in contours.chain(contours.segments(padded, 0.5)):
        if len(line) < 4:
            continue
        ring = simplify(line[:-1] - 1.0 if _closed(line) else line - 1.0,
                        tolerance)
        if len(ring) >= 3:
            rings.append(ring)
    rings.sort(key=lambda ring: -len(ring))
    return rings


def _closed(line):
    return bool(np.allclose(line[0], line[-1]))


def simplify(points, tolerance):
    """Дуглас-Пекер без рекурсии: вершины points (k, 2), которые
    остаются."""
    points = np.asarray(points, dtype=np.float64)
    if len(points) < 3:
        return points
    keep = np.zeros(len(points), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        if last - first < 2:
            continue
        a, b = points[first], points[last]
        inner = points[first + 1:last]
        d = b - a
        # Расстояние до отрезка, а не до прямой: у кольца концы
        # соседние, и точки далеко вдоль их прямой иначе выпадали.
        norm = float(d[0] * d[0] + d[1] * d[1])
        t = np.zeros(len(inner)) if norm == 0.0 else np.clip(
            ((inner - a) @ d) / norm, 0.0, 1.0)
        near = a + t[:, None] * d
        dist = np.hypot(inner[:, 0] - near[:, 0], inner[:, 1] - near[:, 1])
        worst = int(np.argmax(dist))
        if dist[worst] > tolerance:
            index = first + 1 + worst
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return points[keep]
