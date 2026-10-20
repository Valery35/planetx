# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Демо «Карьерные самосвалы»: Качканар и Лебединский карьер.

Просьба автора от 19 октября 2026 года - «грузовики на Качканаре
и в Гае, там реальные карьеры со спиральными ходами». Самосвалы ездят
по настоящей дороге карьера, если она есть в haul_roads.json рядом -
замечания автора того же дня «веди по дороге, не по склону», «по
снимку возьми». Дороги сняты помощником по снимку Esri World Imagery
уровня 17: у Качканара - от забоя на дне вдоль восточного борта
к площадке у перегрузки, у Лебединского карьера - серпантин от забоя
с экскаватором вниз. Гай убран 20 октября 2026 года - карьер остановлен,
борта осыпались и зарастают, замечание автора. Начало съезда - нижний
конец дороги по рельефу.
Без дороги съезд строится по рельефу: Copernicus DEM 30 м (съёмка
2011-2015 годов) в окне вокруг карьера переводится в метры UTM,
дно - наименьшая отметка у середины карьера. Съезд идёт от дна вдоль
горизонталей сглаженного рельефа
с подъёмом GRADE - спиралью по уступам против часовой стрелки - пока
не выйдет из карьера на ровное, дальше по прямой к отвалу на EXIT
метров. Первый вариант ставил точки на лучах из дна, у вытянутого
Главного карьера путь шёл поперёк уступов, кадр 19 октября 2026 года.

Самосвалы ездят по съезду по кругу: погрузка у дна LOAD_WAIT, подъём
гружёным UP_SPEED, разгрузка DUMP_WAIT, спуск порожним DOWN_SPEED.
Точки трека - через STEP секунд, время - условные сутки DAY.
Файлы - planetx/demo/haul: haul_<карьер>.gpkg (слой trucks: точки,
поля truck, time, loaded) и haul_truck.glb - условный самосвал, ось
Y вверх, вперёд - минус Z. Сцены - tools/make_demo.py, haul_*.

Запуск: python-qgis.bat tools/make_haul_demo.py. Величины - выбор
помощника, утверждает автор.
"""
import datetime
import json
import math
import os
import struct
import sys

import numpy as np
from osgeo import gdal, ogr, osr

HERE = os.path.dirname(os.path.abspath(__file__))
ROADS = os.path.join(HERE, "haul_roads.json")
sys.path.insert(0, os.path.join(HERE, "..", "planetx", "core"))
import dem  # noqa: E402

# PLANETX_HAUL_OUT - другая папка, пока файлы демо открыты в QGIS.
OUT = os.environ.get("PLANETX_HAUL_OUT") or os.path.join(
    HERE, "..", "planetx", "demo", "haul")
GRADE = 0.08  # подъём съезда, доля
CELL = 10.0  # м, шаг сетки рельефа в UTM
ROAD_STEP = 5.0  # м, шаг пути съезда
SMOOTH_CELLS = 4.0  # клеток, сглаживание рельефа против уступов
MAX_ROAD = 15000.0  # м, предел длины съезда
TOP_SHARE = 0.85  # верх съезда - эта доля отметок окна
STUCK_STEPS = 60  # шагов, за которые путь обязан подняться
FLAT = 0.04  # крутизна ровного места за бортом
EXIT = 400.0  # м за бортом до отвала
TRUCKS = 6
UP_SPEED = 15.0 / 3.6  # м/с гружёный на подъёме
DOWN_SPEED = 30.0 / 3.6  # м/с порожний на спуске
LOAD_WAIT = 150.0  # с погрузки
DUMP_WAIT = 60.0  # с разгрузки
STEP = 4.0  # с между точками трека слоя GeoPackage
# Допуск упрощения дороги для треков KML, м: точки трека - только на
# вершинах упрощённой дороги и на сменах стоянки и хода.
SIMPLIFY = 1.5
HOURS = 1.0  # часов записи
DAY = datetime.datetime(2026, 10, 20, 8, 0, 0)

# Карьер: ключ, название, середина по контуру OSM (way 41428246
# «Главный карьер», way 30961943 «Карьер Лебединского ГОКа»),
# полуширина окна рельефа, м, радиус поиска дна, м, азимут начала
# съезда, градусы.
PITS = (("kachkanar", "Качканар, Главный карьер", 58.7559, 59.5058,
         2600.0, 1200.0, 0.0),
        ("lebedinsky", "Губкин, Лебединский карьер", 51.2767, 37.6343,
         2600.0, 1200.0, 0.0))


def utm_epsg(lat, lon):
    zone = int((lon + 180.0) // 6.0) + 1
    return (32600 if lat >= 0 else 32700) + zone


def read_dem(lat, lon, half):
    """Рельеф Copernicus в окне 2·half вокруг точки, сетка CELL м UTM:
    (массив отметок, x0, y0 верхнего левого угла, epsg)."""
    epsg = utm_epsg(lat, lon)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(epsg)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    x, y, _ = osr.CoordinateTransformation(wgs, utm).TransformPoint(lon, lat)
    span = half / 60000.0 + 0.05
    cells = dem.copernicus_cells(lon - span * 2, lat - span, lon + span * 2,
                                 lat + span)
    sources = ["/vsicurl/" + dem.copernicus_url(a, b) for a, b in cells]
    gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "EMPTY_DIR")
    out = gdal.Warp("", sources, format="MEM", dstSRS="EPSG:{}".format(epsg),
                    outputBounds=(x - half, y - half, x + half, y + half),
                    xRes=CELL, yRes=CELL, resampleAlg="bilinear")
    z = out.GetRasterBand(1).ReadAsArray().astype(np.float64)
    return z, x - half, y + half, epsg


def sample(z, x0, y0, xs, ys):
    """Отметки рельефа в точках UTM, билинейно; вне окна - NaN."""
    c = (np.asarray(xs) - x0) / CELL - 0.5
    r = (y0 - np.asarray(ys)) / CELL - 0.5
    rows, cols = z.shape
    ok = (c >= 0) & (r >= 0) & (c < cols - 1) & (r < rows - 1)
    c = np.clip(c, 0, cols - 1.001)
    r = np.clip(r, 0, rows - 1.001)
    c0 = c.astype(int)
    r0 = r.astype(int)
    fc = c - c0
    fr = r - r0
    v = (z[r0, c0] * (1 - fc) * (1 - fr) + z[r0, c0 + 1] * fc * (1 - fr)
         + z[r0 + 1, c0] * (1 - fc) * fr + z[r0 + 1, c0 + 1] * fc * fr)
    return np.where(ok, v, np.nan)


def bottom(z, x0, y0, cx, cy, radius):
    """Самая низкая точка рельефа в круге radius у середины карьера."""
    rows, cols = z.shape
    xs = x0 + (np.arange(cols) + 0.5) * CELL
    ys = y0 - (np.arange(rows) + 0.5) * CELL
    gx, gy = np.meshgrid(xs, ys)
    inside = (gx - cx) ** 2 + (gy - cy) ** 2 <= radius ** 2
    flat = np.where(inside, z, np.inf)
    k = int(np.argmin(flat))
    return float(gx.flat[k]), float(gy.flat[k]), float(z.flat[k])


def smooth(z, sigma):
    """Сглаживание Гаусса по строкам и столбцам, sigma в клетках."""
    radius = int(3 * sigma)
    k = np.exp(-0.5 * (np.arange(-radius, radius + 1) / sigma) ** 2)
    k /= k.sum()
    pad = np.pad(z, radius, mode="edge")
    rows = np.apply_along_axis(lambda r: np.convolve(r, k, mode="valid"),
                               1, pad)
    return np.apply_along_axis(lambda c: np.convolve(c, k, mode="valid"),
                               0, rows)


def spiral(z, x0, y0, bx, by, bz, top):
    """Съезд от дна вверх по бортам: точки UTM (x, y, отметка).

    Путь идёт вдоль горизонталей сглаженного рельефа и поднимается
    ровно на GRADE: направление - касательная к горизонтали, повёрнутая
    к подъёму на угол с синусом GRADE / крутизна. Где склон положе
    GRADE, путь идёт прямо вверх. Обход - против часовой стрелки, так
    съезд ложится спиралью по уступам. Конец - отметка top, дальше
    EXIT метров к отвалу."""
    soft = smooth(np.nan_to_num(z, nan=float(np.nanmedian(z))),
                  SMOOTH_CELLS)
    gy, gx = np.gradient(soft, CELL)
    gy = -gy  # строки идут на юг
    x, y = bx, by
    out = [(x, y)]
    level = bz
    walked = 0.0
    climbed = [bz]  # отметки через каждые STUCK_STEPS шагов
    while level < top and walked < MAX_ROAD:
        # Вышел из карьера на ровное или перестал подниматься - съезд
        # кончился: у Гая верх окна выше борта, путь кружил на седловине.
        if len(out) % STUCK_STEPS == 0:
            if level - climbed[-1] < STUCK_STEPS * ROAD_STEP * GRADE / 3:
                break
            climbed.append(level)
        ux = float(sample(gx, x0, y0, [x], [y])[0])
        uy = float(sample(gy, x0, y0, [x], [y])[0])
        g = math.hypot(ux, uy)
        if not math.isfinite(g):
            break
        if g < 1e-6:
            ux, uy, g = (x - bx) or 1.0, (y - by), 1.0
            g = math.hypot(ux, uy)
            ux, uy = ux / g, uy / g
            g = 0.0
        else:
            ux, uy = ux / g, uy / g
        if g < FLAT and level - bz > 0.6 * (top - bz):
            break
        tx, ty = -uy, ux
        share = min(GRADE / g, 1.0) if g > 0 else 1.0
        cos = math.sqrt(1.0 - share * share)
        dx = cos * tx + share * ux
        dy = cos * ty + share * uy
        x += ROAD_STEP * dx
        y += ROAD_STEP * dy
        walked += ROAD_STEP
        out.append((x, y))
        level = float(sample(soft, x0, y0, [x], [y])[0])
        if not math.isfinite(level):
            break
    # Выход за борт к отвалу - прямо по последнему направлению.
    if len(out) > 1:
        (ax, ay), (lx, ly) = out[-2], out[-1]
        d = math.hypot(lx - ax, ly - ay) or 1.0
        for k in range(1, int(EXIT / ROAD_STEP) + 1):
            out.append((lx + (lx - ax) / d * ROAD_STEP * k,
                        ly + (ly - ay) / d * ROAD_STEP * k))
    xs = np.array([p[0] for p in out])
    ys = np.array([p[1] for p in out])
    hs = sample(z, x0, y0, xs, ys)
    return np.column_stack([xs, ys, hs])


def road(coords, z, x0, y0, epsg):
    """Съезд по дороге OSM: точки UTM (x, y, отметка) через ROAD_STEP,
    от нижнего конца к верхнему."""
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(epsg)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    to = osr.CoordinateTransformation(wgs, utm)
    pts = np.array([to.TransformPoint(lon, lat)[:2] for lat, lon in coords])
    s = np.concatenate([[0.0], np.cumsum(np.hypot(
        np.diff(pts[:, 0]), np.diff(pts[:, 1])))])
    d = np.arange(0.0, s[-1], ROAD_STEP)
    xs = np.interp(d, s, pts[:, 0])
    ys = np.interp(d, s, pts[:, 1])
    hs = sample(z, x0, y0, xs, ys)
    path = np.column_stack([xs, ys, hs])
    if hs[0] > hs[-1]:
        path = path[::-1]
    return path


def runs(path):
    """Расстояния вдоль пути от начала, м."""
    d = np.hypot(np.diff(path[:, 0]), np.diff(path[:, 1]))
    return np.concatenate([[0.0], np.cumsum(d)])


def schedule(length):
    """Положение самосвала на пути (расстояние от дна) и гружёность по
    времени цикла: функция t -> (s, гружёный)."""
    up = length / UP_SPEED
    down = length / DOWN_SPEED
    cycle = LOAD_WAIT + up + DUMP_WAIT + down

    def at(t):
        t %= cycle
        if t < LOAD_WAIT:
            return 0.0, True
        t -= LOAD_WAIT
        if t < up:
            return t * UP_SPEED, True
        t -= up
        if t < DUMP_WAIT:
            return length, False
        t -= DUMP_WAIT
        return max(length - t * DOWN_SPEED, 0.0), False
    return at, cycle


def write_gpkg(path, name, points, epsg):
    """Слой trucks: точки WGS84 с полями truck, time, loaded."""
    if os.path.exists(path):
        os.remove(path)
    driver = ogr.GetDriverByName("GPKG")
    ds = driver.CreateDataSource(path)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    layer = ds.CreateLayer("trucks", srs, ogr.wkbPoint)
    for field, kind in (("truck", ogr.OFTString), ("time", ogr.OFTDateTime),
                        ("loaded", ogr.OFTInteger)):
        layer.CreateField(ogr.FieldDefn(field, kind))
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(epsg)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    back = osr.CoordinateTransformation(utm, srs)
    layer.StartTransaction()
    for truck, when, x, y, loaded in points:
        lon, lat, _ = back.TransformPoint(float(x), float(y))
        feature = ogr.Feature(layer.GetLayerDefn())
        feature.SetField("truck", truck)
        feature.SetField("time", when.strftime("%Y/%m/%d %H:%M:%S"))
        feature.SetField("loaded", int(loaded))
        geometry = ogr.Geometry(ogr.wkbPoint)
        geometry.AddPoint_2D(lon, lat)
        feature.SetGeometry(geometry)
        layer.CreateFeature(feature)
    layer.CommitTransaction()
    ds = None
    print(name, path, os.path.getsize(path))


def simplify(xy, tolerance):
    """Номера вершин ломаной xy после Дугласа-Пекера."""
    keep = np.zeros(len(xy), dtype=bool)
    keep[0] = keep[-1] = True
    stack = [(0, len(xy) - 1)]
    while stack:
        a, b = stack.pop()
        if b - a < 2:
            continue
        p, q = xy[a], xy[b]
        d = q - p
        span = np.hypot(*d)
        pts = xy[a + 1:b] - p
        gaps = np.abs(d[0] * pts[:, 1] - d[1] * pts[:, 0]) / span \
            if span > 0 else np.hypot(pts[:, 0], pts[:, 1])
        k = int(np.argmax(gaps))
        if gaps[k] > tolerance:
            keep[a + 1 + k] = True
            stack += [(a, a + 1 + k), (a + 1 + k, b)]
    return np.flatnonzero(keep)


def track_rows(path, s, at, cycle, shift, back, epoch):
    """Строки gx:Track самосвала: [секунды, широта, долгота, 0, азимут,
    0, 0] на вершинах упрощённой дороги и сменах стоянки и хода за HOURS
    часов. Азимут - по ходу, на стоянке - прежний."""
    keep = simplify(path[:, :2], SIMPLIFY)
    marks = s[keep]
    length = float(s[-1])
    up = length / UP_SPEED
    down = length / DOWN_SPEED
    local = [0.0, LOAD_WAIT, LOAD_WAIT + up, LOAD_WAIT + up + DUMP_WAIT]
    local += [LOAD_WAIT + m / UP_SPEED for m in marks]
    local += [LOAD_WAIT + up + DUMP_WAIT + (length - m) / DOWN_SPEED
              for m in marks]
    end = HOURS * 3600.0
    times = {0.0, end}
    for m in range(-1, int(end / cycle) + 2):
        for u in local:
            t = u - shift + m * cycle
            if 0.0 <= t <= end:
                times.add(round(t, 2))
    rows = []
    for t in sorted(times):
        d, _ = at(t + shift)
        x = float(np.interp(d, s, path[:, 0]))
        y = float(np.interp(d, s, path[:, 1]))
        rows.append([t, x, y])
    headings = [None] * len(rows)
    for i in range(len(rows) - 1):
        dx = rows[i + 1][1] - rows[i][1]
        dy = rows[i + 1][2] - rows[i][2]
        if abs(dx) + abs(dy) > 0.01:
            headings[i] = float(np.degrees(np.arctan2(dx, dy)) % 360.0)
    last = next((h for h in headings if h is not None), 0.0)
    out = []
    for (t, x, y), heading in zip(rows, headings):
        last = heading if heading is not None else last
        lon, lat, _ = back.TransformPoint(x, y)
        out.append([round(epoch + t, 2), round(lat, 7), round(lon, 7), 0.0,
                    round(last, 1), 0.0, 0.0])
    return out


def build(key, title, lat, lon, half, radius, start):
    z, x0, y0, epsg = read_dem(lat, lon, half)
    utm = osr.SpatialReference()
    utm.ImportFromEPSG(epsg)
    utm.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    wgs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    cx, cy, _ = osr.CoordinateTransformation(wgs, utm).TransformPoint(
        lon, lat)
    roads = {}
    if os.path.exists(ROADS):
        with open(ROADS, encoding="utf-8") as fh:
            roads = json.load(fh)
    if key in roads:
        path = road(roads[key]["coords"], z, x0, y0, epsg)
        bx, by, bz = path[0]
        rim = float(np.nanmax(path[:, 2]))
    else:
        bx, by, bz = bottom(z, x0, y0, cx, cy, radius)
        rim = float(np.nanpercentile(z, TOP_SHARE * 100.0))
        path = spiral(z, x0, y0, bx, by, bz, rim)
    s = runs(path)
    length = float(s[-1])
    grades = np.diff(path[:, 2]) / np.maximum(np.diff(s), 1e-6)
    print(key, "дно", round(bz), "верх окна", round(rim), "съезд",
          round(length), "м, точек", len(path), "подъём медиана",
          round(float(np.nanmedian(grades)), 3), "95%",
          round(float(np.nanpercentile(np.abs(grades), 95)), 3),
          "конец", round(float(path[-1, 2])))
    at, cycle = schedule(length)
    points = []
    steps = int(HOURS * 3600 / STEP)
    for n in range(TRUCKS):
        shift = cycle * n / TRUCKS
        name = "БелАЗ {}".format(n + 1)
        for k in range(steps + 1):
            t = k * STEP
            d, loaded = at(t + shift)
            x = float(np.interp(d, s, path[:, 0]))
            y = float(np.interp(d, s, path[:, 1]))
            points.append((name, DAY + datetime.timedelta(seconds=t), x, y,
                           loaded))
    os.makedirs(OUT, exist_ok=True)
    write_gpkg(os.path.join(OUT, "haul_{}.gpkg".format(key)), title,
               points, epsg)
    # Треки KML: те же самосвалы, точки - на вершинах дороги.
    back = osr.CoordinateTransformation(utm, wgs)
    epoch = (DAY - datetime.datetime(1970, 1, 1)).total_seconds()
    tracks = {"БелАЗ {}".format(n + 1): track_rows(
        path, s, at, cycle, cycle * n / TRUCKS, back, epoch)
        for n in range(TRUCKS)}
    tracks_path = os.path.join(OUT, "haul_{}_tracks.json".format(key))
    with open(tracks_path, "w", encoding="utf-8") as fh:
        json.dump(tracks, fh, ensure_ascii=False, separators=(",", ":"))
    print(key, "треки KML, точек на самосвал",
          [len(r) for r in tracks.values()], os.path.getsize(tracks_path))
    # Середина и вид для сцены: середина съезда, азимут взгляда.
    back = osr.CoordinateTransformation(utm, wgs)
    mx, my = float(np.mean(path[:, 0])), float(np.mean(path[:, 1]))
    mlon, mlat, _ = back.TransformPoint(mx, my)
    blon, blat, _ = back.TransformPoint(bx, by)
    return {"key": key, "center": (mlat, mlon), "bottom": (blat, blon),
            "length": length, "cycle": cycle, "depth": rim - bz}


# Условный карьерный самосвал: метры, ось Y вверх, вперёд - минус Z.
# Длина около 11.5 м, ширина 6.4 м, высота 5.5 м - самосвал
# грузоподъёмностью 130 т. Цвета - жёлтый кузов, тёмные колёса.
def _box(x0, x1, y0, y1, z0, z1):
    v = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
         (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = ((0, 3, 2, 1), (4, 5, 6, 7), (0, 1, 5, 4), (2, 3, 7, 6),
             (1, 2, 6, 5), (3, 0, 4, 7))
    out = []
    for a, b, c, d in faces:
        out += [v[a], v[b], v[c], v[a], v[c], v[d]]
    return out


def _wheel(x, z, radius=1.5, width=1.2, sides=14):
    """Колесо - многогранная шайба вдоль оси X."""
    out = []
    for k in range(sides):
        a0 = 2 * math.pi * k / sides
        a1 = 2 * math.pi * (k + 1) / sides
        p = [(z + radius * math.cos(a), radius + radius * math.sin(a))
             for a in (a0, a1)]
        for sx in (x - width / 2, x + width / 2):
            out += [(sx, radius, z), (sx, p[0][1], p[0][0]),
                    (sx, p[1][1], p[1][0])]
        out += [(x - width / 2, p[0][1], p[0][0]),
                (x + width / 2, p[0][1], p[0][0]),
                (x + width / 2, p[1][1], p[1][0]),
                (x - width / 2, p[0][1], p[0][0]),
                (x + width / 2, p[1][1], p[1][0]),
                (x - width / 2, p[1][1], p[1][0])]
    return out


def truck_glb():
    """Байты .glb условного самосвала."""
    blob = bytearray()
    views, accessors = [], []

    def add(array):
        array = np.ascontiguousarray(array, dtype=np.float32)
        while len(blob) % 4:
            blob.append(0)
        views.append({"buffer": 0, "byteOffset": len(blob),
                      "byteLength": array.nbytes})
        blob.extend(array.tobytes())
        accessors.append({"bufferView": len(views) - 1,
                          "componentType": 5126, "count": len(array),
                          "type": "VEC3",
                          "min": array.min(axis=0).tolist(),
                          "max": array.max(axis=0).tolist()})
        return len(accessors) - 1
    # Рама и кабина впереди (минус Z), кузов сзади с козырьком над
    # кабиной.
    frame = _box(-2.2, 2.2, 1.0, 2.0, -5.6, 5.4)
    cab = _box(-3.1, -0.9, 2.0, 4.6, -5.8, -4.0)
    deck = _box(-3.1, 3.1, 2.0, 2.6, -5.8, -4.2)
    body = _box(-3.2, 3.2, 2.4, 3.0, -3.8, 5.6) \
        + _box(-3.2, -2.9, 3.0, 5.4, -3.8, 5.6) \
        + _box(2.9, 3.2, 3.0, 5.4, -3.8, 5.6) \
        + _box(-3.2, 3.2, 3.0, 5.6, -4.2, -3.8) \
        + _box(-3.2, 3.2, 5.0, 5.4, -5.6, -3.8)
    wheels = []
    for z in (-4.0, 3.2):
        for x in (-2.6, 2.6):
            wheels += _wheel(x, z)
    for x in (-3.8, 3.8):
        wheels += _wheel(x, 3.2)
    parts = ((frame + deck, (0.25, 0.25, 0.27)), (cab, (0.95, 0.75, 0.10)),
             (body, (0.96, 0.78, 0.12)), (wheels, (0.08, 0.08, 0.08)))
    meshes = []
    materials = []
    for n, (triangles, color) in enumerate(parts):
        meshes.append({"primitives": [{"attributes": {
            "POSITION": add(triangles)}, "material": n}]})
        materials.append({"pbrMetallicRoughness": {
            "baseColorFactor": [color[0], color[1], color[2], 1.0]}})
    doc = {"asset": {"version": "2.0", "generator": "PlanetX make_haul_demo"},
           "scene": 0, "scenes": [{"nodes": list(range(len(meshes)))}],
           "nodes": [{"mesh": n} for n in range(len(meshes))],
           "meshes": meshes, "materials": materials,
           "accessors": accessors, "bufferViews": views}
    while len(blob) % 4:
        blob.append(0)
    doc["buffers"] = [{"byteLength": len(blob)}]
    text = json.dumps(doc).encode("utf-8")
    text += b" " * (-len(text) % 4)
    total = 12 + 8 + len(text) + 8 + len(blob)
    return (b"glTF" + struct.pack("<II", 2, total)
            + struct.pack("<I", len(text)) + b"JSON" + text
            + struct.pack("<I", len(blob)) + b"BIN\x00" + bytes(blob))


def main():
    gdal.UseExceptions()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "haul_truck.glb"), "wb") as fh:
        fh.write(truck_glb())
    found = [build(*pit) for pit in PITS]
    with open(os.path.join(OUT, "haul.json"), "w", encoding="utf-8") as fh:
        json.dump(found, fh, ensure_ascii=False, indent=1)
    print(json.dumps(found, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
