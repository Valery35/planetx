# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Пример проекта Pythagoras: выдуманный карьер у Березников.

    $PY tools/make_pyt_demo.py

Пишет planetx/demo/pythagoras/quarry.pyt в разметке, которую читает
core/pythagoras.py. Карьер тот же, что в демо «Карьер, свой рельеф»
(tools/make_quarry_demo.py): эллипс 1400 × 1000 м по верху, 10 уступов
по 15 м, отвал к северо-востоку. Отметки точек снимаются с растра
planetx/demo/quarry/quarry_dem.tif, поэтому бровки ложатся на его
рельеф. Координаты - UTM 40N (EPSG:32640). Состав и имена слоёв -
выбор помощника, данные выдуманы.
"""
import math
import os
import struct
import sys

from osgeo import gdal, osr

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import make_quarry_demo as quarry  # noqa: E402

DEM = quarry.OUT
OUT = os.path.join(ROOT, "planetx", "demo", "pythagoras", "quarry.pyt")
RING = 48  # вершин эллипса уступа
LAYERS = {0: "Подписи", 1: "Вскрышной_уступ", 2: "Добычной_уступ",
          3: "Контуры_карьера", 4: "Отвал", 5: "Дороги",
          6: "Опорные_пункты", 7: "Горный_отвод"}
OVERBURDEN = 4  # верхние уступы - вскрыша
COLOR = {1: 15, 2: 20, 3: 10, 4: 25, 5: 30, 6: 10, 7: 12, 0: 10}

gdal.UseExceptions()


def varint(v):
    out = bytearray()
    while True:
        b = v & 0x7F
        v >>= 7
        out.append(b | (0x80 if v else 0))
        if not v:
            return bytes(out)


def rec(field, *kids):
    return bytes([field]) + varint(len(kids)) + b"".join(kids)


def num(field, v):
    return bytes([0x40 | field]) + varint(v)


def dbl(field, v):
    return bytes([0x80 | field]) + struct.pack("<d", v)


def blob(field, b):
    return bytes([0xC0 | field]) + varint(len(b)) + b


def txt(field, s):
    return blob(field, s.encode("utf-8"))


def xy(field, p):
    return rec(field, dbl(1, p[0]), dbl(2, p[1]))


class Project:
    """Объекты в разметке .pyt с номерами по порядку."""

    def __init__(self, sample):
        self.sample = sample
        self.parts = []
        self.oid = 0
        self.coords = {}

    def head(self, layer, code=None):
        self.oid += 1
        kids = [num(1, self.oid)]
        if code:
            kids.append(txt(3, code))
        if layer:
            kids.append(num(8, layer))
        kids += [num(9, COLOR[layer]), num(10, 40000 + self.oid)]
        return self.oid, rec(1, *kids)

    def point(self, layer, p, code=None, sign=0):
        """Точка с отметкой с растра. sign 0 - точка построения, None -
        знак по умолчанию."""
        oid, head = self.head(layer, code)
        kids = [head, xy(5, p), dbl(6, self.sample(p))]
        if sign is not None:
            kids.append(rec(7, num(1, sign)))
        self.parts.append(rec(1, *kids))
        self.coords[oid] = p
        return oid

    def segment(self, layer, a, b, code=None):
        _, head = self.head(layer, code)
        self.parts.append(rec(2, head, num(5, a), num(6, b),
                              xy(7, self.coords[a]), xy(8, self.coords[b])))

    def polyline(self, layer, pts, code, closed=False):
        ids = [self.point(layer, p) for p in pts]
        for a, b in zip(ids, ids[1:] + (ids[:1] if closed else [])):
            self.segment(layer, a, b, code)
        return ids

    def area(self, layer, ids, code=None):
        ring = ids + ids[:1]
        pts = [self.coords[i] for i in ring]
        area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                       in zip(pts, pts[1:]))) / 2.0
        _, head = self.head(layer, code)
        ids = struct.pack("<%dI" % len(ring), *ring)
        self.parts.append(rec(3, head, num(5, len(ring)), dbl(10, area),
                              rec(20, blob(2, ids))))

    def arc(self, layer, center, radius, a, b, code=None):
        _, head = self.head(layer, code)
        self.parts.append(rec(6, head, xy(6, center), num(7, a), num(8, b),
                              dbl(9, radius)))

    def text(self, layer, p, s):
        _, head = self.head(layer)
        self.parts.append(rec(4, head, xy(15, p), txt(20, s)))


def ellipse(cx, cy, d, ratio, n=RING):
    return [(cx + d * math.cos(2 * math.pi * i / n),
             cy + d * ratio * math.sin(2 * math.pi * i / n))
            for i in range(n)]


def circle(cx, cy, r, n=RING):
    return ellipse(cx, cy, r, 1.0, n)


def main():
    ds = gdal.Open(DEM)
    gt = ds.GetGeoTransform()
    band = ds.GetRasterBand(1).ReadAsArray()

    def sample(p):
        col = int((p[0] - gt[0]) / gt[1])
        row = int((p[1] - gt[3]) / gt[5])
        col = min(max(col, 0), band.shape[1] - 1)
        row = min(max(row, 0), band.shape[0] - 1)
        return round(float(band[row, col]), 2)

    utm = osr.SpatialReference()
    utm.ImportFromEPSG(32640)
    wgs = osr.SpatialReference()
    wgs.ImportFromEPSG(4326)
    for s in (utm, wgs):
        s.SetAxisMappingStrategy(osr.OAMS_TRADITIONAL_GIS_ORDER)
    cx, cy, _ = osr.CoordinateTransformation(wgs, utm).TransformPoint(
        quarry.CENTER[1], quarry.CENTER[0])
    prj = Project(sample)
    ratio = quarry.PIT[1] / quarry.PIT[0]
    face = quarry.BENCH_HEIGHT / math.tan(quarry.FACE)
    step = face + quarry.BERM
    rims = []
    for k in range(quarry.BENCHES):
        layer = 1 if k < OVERBURDEN else 2
        crest = quarry.PIT[0] - k * step
        toe = crest - face
        ids = prj.polyline(layer, ellipse(cx, cy, crest, ratio),
                           "Бровка", closed=True)
        rims.append(ids)
        last = prj.polyline(layer, ellipse(cx, cy, toe, ratio),
                            "Подошва", closed=True)
        top = (cx, cy + (crest - 2) * ratio)
        prj.text(layer, top, "{:+.0f}".format(sample(top)))
    prj.area(3, rims[0], "Верхний контур карьера")
    prj.area(3, last, "Дно карьера")
    prj.text(0, (cx, cy), "Карьер «Пример»")
    # Отвал - основание и верхний ярус.
    dx, dy, radius, _ = quarry.DUMP
    for r, code in ((radius, "Подошва отвала"),
                    (radius - 120.0, "Бровка яруса")):
        ids = prj.polyline(4, circle(cx + dx, cy + dy, r), code,
                           closed=True)
        prj.area(4, ids, code)
    prj.text(4, (cx + dx, cy + dy), "Отвал")
    # Съезд от северной бровки к отвалу с поворотом по дуге.
    north = (cx, cy + quarry.PIT[1])
    bend = (cx, cy + quarry.PIT[1] + 150.0)
    out = (cx + 150.0, cy + quarry.PIT[1] + 300.0)
    near = (cx + dx - radius - 20.0, cy + quarry.PIT[1] + 300.0)
    a = prj.point(5, north, "Съезд")
    b = prj.point(5, bend, "Съезд")
    c = prj.point(5, out, "Съезд")
    d = prj.point(5, near, "Съезд")
    prj.segment(5, a, b, "Автодорога")
    prj.arc(5, (cx + 150.0, cy + quarry.PIT[1] + 150.0), 150.0, c, b,
            "Автодорога")
    prj.segment(5, c, d, "Автодорога")
    prj.text(5, (cx + 60.0, cy + quarry.PIT[1] + 260.0), "Автодорога")
    # Опорные пункты со знаком и горный отвод.
    for n, (sx, sy) in enumerate(((-950, -800), (950, -800), (950, 1050),
                                  (-950, 1050)), 1):
        p = (cx + sx, cy + sy)
        prj.point(6, p, "ОМС {}".format(n), sign=None)
        prj.text(6, (p[0] + 15.0, p[1] + 15.0), "ОМС {}".format(n))
    corners = [(cx - 1100, cy - 950), (cx + 1100, cy - 950),
               (cx + 1100, cy + 1150), (cx - 1100, cy + 1150)]
    ids = prj.polyline(7, corners, "Граница", closed=True)
    prj.area(7, ids, "Горный отвод")
    cells = [rec(1, txt(1, LAYERS[i])) if i in LAYERS else rec(1)
             for i in range(256)]
    table = rec(5, num(1, 16), rec(2, *cells), rec(3))
    data = b"SFS_ADW1" + bytes(40) + table + b"".join(prj.parts) + bytes(8)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "wb") as handle:
        handle.write(data)
    print(OUT, len(data), "objects", prj.oid)


if __name__ == "__main__":
    sys.exit(main())
