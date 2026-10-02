# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Синтетические подземные данные у Березников для демо подземного
режима.

    $PY tools/make_subsurface_demo.py

Подшаг 4.3 плана фазы 3 (doc/PLAN_PHASE3.md). Пишет в
planetx/demo/subsurface:

- perm_subsurface.gpkg - таблицы как у Isoliner: collar (точки устьев,
  hole_id, z, eoh), interval (hole_id, from, to, code), survey
  (hole_id, depth, azimuth, dip), beds (code, ord, color, surface -
  файл растра кровли), sections (линии разрезов, sec_id, name),
  cut (многоугольник выреза блока).
- roof_NN.tif - кровли пластов, отметки в метрах, EPSG:32640.

Пласты - упрощённый разрез Верхнекамского месторождения по
справочнику Isoliner plast_reference_vkmks, цвета оттуда же. Кровля
наносов Q - рельеф Terrarium (те же тайлы, что у глобуса), остальные
кровли - плавные поверхности от средней отметки рельефа с волнами
и падением на восток. Данные синтетические, не съёмка.

Высоты рельефа читаются по сети из тайлов Terrarium уровня 12,
четыре тайла. Это проверочный скрипт, блокирующий запрос в нём
допустим (AGENTS, «Сеть не блокирует главный поток»).
"""
import math
import os
import sys
import urllib.request

import numpy as np
from osgeo import gdal, ogr, osr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "planetx", "core"))

import drillholes  # noqa: E402

gdal.UseExceptions()
OUT = os.path.join(ROOT, "planetx", "demo", "subsurface")
GPKG = os.path.join(OUT, "perm_subsurface.gpkg")
EPSG = 32640  # UTM 40N
# К востоку от Березников, на Верхнекамском месторождении. До 2 октября
# 2026 года участок стоял у Перми, перенесён по замечанию автора:
# разрез взят из справочника Верхнекамского месторождения.
CENTER = (59.45, 56.88)
WIDTH, HEIGHT = 4000.0, 3000.0  # метры
CELL = 50.0
TERRARIUM = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
             "{z}/{x}/{y}.png")
LEVEL = 12

# Пласты сверху вниз: код, цвет, глубина кровли под средней отметкой
# рельефа (у Q - сам рельеф), амплитуда волн.
BEDS = (
    ("Q", "#e8e0c8", None, 0.0),
    ("ПЦТ", "#8b6914", 18.0, 4.0),
    ("ТКТ", "#53e753", 70.0, 8.0),
    ("СМТ", "#499c49", 135.0, 10.0),
    ("ПП", "#add8e6", 190.0, 8.0),
    ("ПКС", "#1e3bff", 215.0, 6.0),
    ("КрII", "#ff0000", 262.0, 5.0),
    ("ПДКС", "#1e90ff", 280.0, 5.0),
    ("МГ", "#4d4d4d", 335.0, 4.0),
    ("НКС", "#4859ff", 345.0, 4.0),
)
BOTTOM = 400.0  # глубина подошвы НКС под средней отметкой
DIP = 2.0  # м на км, падение пластов на восток


def utm():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(EPSG)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def wgs():
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    srs.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    return srs


def tile_xy(lat, lon, z):
    n = 1 << z
    x = (lon + 180.0) / 360.0 * n
    y = (1.0 - np.arcsinh(np.tan(np.radians(lat))) / math.pi) / 2 * n
    return x, y


def terrain(lats, lons):
    """Высоты Terrarium в точках, билинейно по тайлам уровня LEVEL."""
    xs, ys = tile_xy(lats, lons, LEVEL)
    cache = {}
    out = np.empty(lats.shape)
    for idx in np.ndindex(lats.shape):
        fx, fy = xs[idx], ys[idx]
        tx, ty = int(fx), int(fy)
        key = (tx, ty)
        if key not in cache:
            url = TERRARIUM.format(z=LEVEL, x=tx, y=ty)
            # GDAL вне окружения QGIS не видит сертификаты, urllib
            # берёт их из Windows.
            with urllib.request.urlopen(url, timeout=30) as reply:
                gdal.FileFromMemBuffer("/vsimem/tile.png", reply.read())
            data = gdal.Open("/vsimem/tile.png").ReadAsArray().astype(float)
            gdal.Unlink("/vsimem/tile.png")
            cache[key] = data[0] * 256 + data[1] + data[2] / 256 - 32768
        heights = cache[key]
        px = (fx - tx) * 256 - 0.5
        py = (fy - ty) * 256 - 0.5
        x0 = int(np.clip(math.floor(px), 0, 254))
        y0 = int(np.clip(math.floor(py), 0, 254))
        ax, ay = np.clip(px - x0, 0, 1), np.clip(py - y0, 0, 1)
        top = heights[y0, x0] * (1 - ax) + heights[y0, x0 + 1] * ax
        bot = heights[y0 + 1, x0] * (1 - ax) + heights[y0 + 1, x0 + 1] * ax
        out[idx] = top * (1 - ay) + bot * ay
    return out


def grid():
    """Узлы сетки растров: x, y в UTM и широты, долготы."""
    to_utm = osr.CoordinateTransformation(wgs(), utm())
    cx, cy, _ = to_utm.TransformPoint(CENTER[1], CENTER[0])
    x0 = round((cx - WIDTH / 2) / CELL) * CELL
    y0 = round((cy - HEIGHT / 2) / CELL) * CELL
    cols, rows = int(WIDTH / CELL) + 1, int(HEIGHT / CELL) + 1
    xs = x0 + np.arange(cols) * CELL
    ys = y0 + HEIGHT - np.arange(rows) * CELL  # строки с севера на юг
    gx, gy = np.meshgrid(xs, ys)
    to_wgs = osr.CoordinateTransformation(utm(), wgs())
    pts = np.array(to_wgs.TransformPoints(
        np.stack([gx.ravel(), gy.ravel()], axis=1).tolist()))
    lons = pts[:, 0].reshape(gx.shape)
    lats = pts[:, 1].reshape(gx.shape)
    return gx, gy, lats, lons, x0, y0 + HEIGHT


def roofs(gx, gy, ground):
    """Кровли пластов по узлам: список массивов сверху вниз и подошва."""
    mean = float(ground.mean())
    east = (gx - gx.mean()) / 1000.0
    north = (gy - gy.mean()) / 1000.0
    out = [ground]
    for n, (_, _, depth, amp) in enumerate(BEDS[1:], start=1):
        wave = amp * (np.sin(east * 1.3 + n) * np.cos(north * 1.1 - n * 0.7))
        surface = mean - depth + wave - DIP * east
        out.append(surface)
    out.append(mean - BOTTOM - DIP * east)
    # Кровля ниже верхней хотя бы на 3 м, первая - ниже рельефа.
    for i in range(1, len(out)):
        out[i] = np.minimum(out[i], out[i - 1] - 3.0)
    return out


def write_raster(path, array, x0, y_top):
    driver = gdal.GetDriverByName("GTiff")
    rows, cols = array.shape
    ds = driver.Create(path, cols, rows, 1, gdal.GDT_Float32,
                       ["COMPRESS=DEFLATE"])
    ds.SetGeoTransform((x0 - CELL / 2, CELL, 0.0, y_top + CELL / 2, 0.0,
                        -CELL))
    ds.SetProjection(utm().ExportToWkt())
    band = ds.GetRasterBand(1)
    band.WriteArray(array.astype(np.float32))
    band.SetNoDataValue(-9999.0)
    ds = None


def sample(surface, gx0, gy_top, x, y):
    """Отметка поверхности в точке UTM, билинейно по узлам."""
    rows, cols = surface.shape
    fx = np.clip((x - gx0) / CELL, 0, cols - 1.001)
    fy = np.clip((gy_top - y) / CELL, 0, rows - 1.001)
    i, j = int(fy), int(fx)
    ax, ay = fx - j, fy - i
    top = surface[i, j] * (1 - ax) + surface[i, j + 1] * ax
    bot = surface[i + 1, j] * (1 - ax) + surface[i + 1, j + 1] * ax
    return top * (1 - ay) + bot * ay


def holes(surfaces, gx0, gy_top):
    """Скважины: устья, станции инклинометрии и интервалы по пересечению
    ствола с кровлями."""
    rng = np.random.default_rng(2026)
    out = []
    number = 0
    for row in range(4):
        for col in range(6):
            number += 1
            x = gx0 + 500.0 + col * 600.0 + rng.uniform(-80, 80)
            y = gy_top - 450.0 - row * 700.0 + rng.uniform(-80, 80)
            z = float(sample(surfaces[0], gx0, gy_top, x, y))
            inclined = number % 4 == 0
            zenith_end = 25.0 if inclined else 0.0
            azimuth = float(rng.uniform(0, 360))
            stations = [(md, min(zenith_end, zenith_end * md / 200.0),
                         azimuth) for md in range(0, 501, 50)]
            nodes = drillholes.axis(z, 500.0, stations)
            # Глубина по стволу, где ствол пересекает кровлю.
            crossings = [0.0]
            for surface in surfaces[1:]:
                for a, b in zip(nodes[:-1], nodes[1:]):
                    za = a[3] - sample(surface, gx0, gy_top, x + a[1],
                                       y + a[2])
                    zb = b[3] - sample(surface, gx0, gy_top, x + b[1],
                                       y + b[2])
                    if za >= 0.0 > zb:
                        share = za / (za - zb)
                        crossings.append(a[0] + (b[0] - a[0]) * share)
                        break
            eoh = crossings[-1] + 10.0
            intervals = [(round(s, 2), round(e, 2), BEDS[i][0])
                         for i, (s, e) in enumerate(zip(crossings,
                                                        crossings[1:]))]
            dip = [(md, -90.0 + zen, az) for md, zen, az in stations
                   if md <= eoh + 50]
            out.append(("C-%02d" % number, x, y, round(z, 2),
                        round(eoh, 1), dip, intervals))
    return out


def main():
    os.makedirs(OUT, exist_ok=True)
    gx, gy, lats, lons, gx0, gy_top = grid()
    ground = terrain(lats, lons)
    surfaces = roofs(gx, gy, ground)
    names = []
    for n, surface in enumerate(surfaces[1:-1], start=1):
        name = "roof_%02d.tif" % n
        write_raster(os.path.join(OUT, name), surface, gx0, gy_top)
        names.append(name)
    if os.path.exists(GPKG):
        os.remove(GPKG)
    driver = ogr.GetDriverByName("GPKG")
    ds = driver.CreateDataSource(GPKG)
    srs = utm()

    def layer(name, geom, fields):
        lyr = ds.CreateLayer(name, srs if geom != ogr.wkbNone else None,
                             geom)
        for field, kind in fields:
            lyr.CreateField(ogr.FieldDefn(field, kind))
        return lyr

    wells = holes(surfaces, gx0, gy_top)
    collar = layer("collar", ogr.wkbPoint, [("hole_id", ogr.OFTString),
                                            ("z", ogr.OFTReal),
                                            ("eoh", ogr.OFTReal)])
    interval = layer("interval", ogr.wkbNone, [("hole_id", ogr.OFTString),
                                               ("from", ogr.OFTReal),
                                               ("to", ogr.OFTReal),
                                               ("code", ogr.OFTString)])
    survey = layer("survey", ogr.wkbNone, [("hole_id", ogr.OFTString),
                                           ("depth", ogr.OFTReal),
                                           ("azimuth", ogr.OFTReal),
                                           ("dip", ogr.OFTReal)])
    for hole, x, y, z, eoh, stations, parts in wells:
        f = ogr.Feature(collar.GetLayerDefn())
        f.SetField("hole_id", hole)
        f.SetField("z", z)
        f.SetField("eoh", eoh)
        f.SetGeometry(ogr.CreateGeometryFromWkt("POINT (%f %f)" % (x, y)))
        collar.CreateFeature(f)
        for start, end, code in parts:
            f = ogr.Feature(interval.GetLayerDefn())
            f.SetField("hole_id", hole)
            f.SetField("from", start)
            f.SetField("to", end)
            f.SetField("code", code)
            interval.CreateFeature(f)
        for md, dip, az in stations:
            f = ogr.Feature(survey.GetLayerDefn())
            f.SetField("hole_id", hole)
            f.SetField("depth", md)
            f.SetField("azimuth", az)
            f.SetField("dip", dip)
            survey.CreateFeature(f)
    beds = layer("beds", ogr.wkbNone, [("code", ogr.OFTString),
                                       ("ord", ogr.OFTInteger),
                                       ("color", ogr.OFTString),
                                       ("surface", ogr.OFTString)])
    for n, (code, color, _, _) in enumerate(BEDS):
        f = ogr.Feature(beds.GetLayerDefn())
        f.SetField("code", code)
        f.SetField("ord", n + 1)
        f.SetField("color", color)
        f.SetField("surface", names[n - 1] if n else "")
        beds.CreateFeature(f)
    # Разрезы - запад-восток и север-юг через середину, вырез - северо-
    # восточная четверть между ними.
    cx, cy = gx0 + WIDTH / 2, gy_top - HEIGHT / 2
    sections = layer("sections", ogr.wkbLineString,
                     [("sec_id", ogr.OFTInteger), ("name", ogr.OFTString)])
    for sec, name, wkt in (
            (1, "Разрез 1-1", "LINESTRING (%f %f, %f %f)" % (
                gx0 + 200, cy, gx0 + WIDTH - 200, cy)),
            (2, "Разрез 2-2", "LINESTRING (%f %f, %f %f)" % (
                cx, gy_top - 200, cx, gy_top - HEIGHT + 200))):
        f = ogr.Feature(sections.GetLayerDefn())
        f.SetField("sec_id", sec)
        f.SetField("name", name)
        f.SetGeometry(ogr.CreateGeometryFromWkt(wkt))
        sections.CreateFeature(f)
    cut = layer("cut", ogr.wkbPolygon, [("name", ogr.OFTString)])
    f = ogr.Feature(cut.GetLayerDefn())
    f.SetField("name", "Вырез блока")
    f.SetGeometry(ogr.CreateGeometryFromWkt(
        "POLYGON ((%f %f, %f %f, %f %f, %f %f, %f %f))" % (
            cx, cy, gx0 + WIDTH - 200, cy, gx0 + WIDTH - 200, gy_top - 200,
            cx, gy_top - 200, cx, cy)))
    cut.CreateFeature(f)
    ds = None
    size = sum(os.path.getsize(os.path.join(OUT, n))
               for n in os.listdir(OUT))
    print(GPKG, "скважин", len(wells), "растров", len(names),
          "байт", size)
    print("рельеф", round(float(ground.min())), "-",
          round(float(ground.max())), "м")


if __name__ == "__main__":
    main()
