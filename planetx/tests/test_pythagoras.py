# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проект Pythagoras: поток полей, слои, объекты, кольцо с дугой."""
import math
import os
import struct
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import pythagoras as pyt  # noqa: E402


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


def txt(field, s):
    b = s.encode("utf-8") if isinstance(s, str) else s
    return bytes([0xC0 | field]) + varint(len(b)) + b


def head(oid, layer=None, code=None):
    kids = [num(1, oid)]
    if code:
        kids.append(txt(3, code))
    if layer:
        kids.append(num(8, layer))
    kids += [num(9, 10), num(10, 50000 + oid)]
    return rec(1, *kids)


def xy(field, x, y):
    return rec(field, dbl(1, x), dbl(2, y))


def point(oid, x, y, z=None, layer=None, sign=None):
    kids = [head(oid, layer), xy(5, x, y)]
    if z is not None:
        kids.append(dbl(6, z))
    if sign is not None:
        kids.append(rec(7, num(1, sign)))
    return rec(1, *kids)


def layer_table(names):
    cells = [rec(1, txt(1, names[i])) if i in names else rec(1)
             for i in range(200)]
    return rec(5, num(1, 16), rec(2, *cells), rec(3))


P = {1: (1000.0, 2000.0), 2: (1010.0, 2000.0), 3: (1010.0, 2010.0),
     4: (1000.0, 2010.0), 5: (1020.0, 2005.0)}


def sample():
    """Слои 0 и 7, четыре точки квадрата и точка построения, отрезок,
    надпись, дуга через точку 5 и площадь с дугой."""
    body = [layer_table({0: "Измерения", 7: "Дороги"})]
    for oid, (x, y) in P.items():
        body.append(point(oid, x, y, z=150.0 + oid, layer=7,
                          sign=0 if oid == 5 else None))
    body.append(rec(2, head(20, 7, "Бетон"), num(5, 1), num(6, 2),
                    xy(7, *P[1]), xy(8, *P[2])))
    body.append(rec(4, head(21), xy(15, 1005.0, 2005.0),
                    txt(20, "Склад")))
    # Дуга от 2 до 3 против часовой стрелки с центром справа от них -
    # выпуклая наружу полуокружность радиуса 5.
    body.append(rec(6, head(22, 7), xy(6, 1010.0, 2005.0), num(7, 2),
                    num(8, 3), dbl(9, 5.0)))
    ids = struct.pack("<6I", 1, 2, 22, 3, 4, 1)
    body.append(rec(3, head(23, 7), num(5, 6), dbl(10, 0.0),
                    rec(20, txt(2, ids))))
    return b"SFS_ADW1" + b"\x00" * 40 + b"".join(body) + b"\x00" * 8


class TestStream(unittest.TestCase):

    def test_kinds_of_fields(self):
        raw = rec(5, num(1, 300), dbl(2, 1.5), txt(3, "слой"), rec(4))
        f, kids, end = pyt.node(raw, 0)
        self.assertEqual(f, 5)
        self.assertEqual(end, len(raw))
        self.assertEqual(kids, [(1, 300), (2, 1.5),
                                (3, "слой".encode("utf-8")), (4, [])])

    def test_cut_record_is_bad(self):
        raw = rec(5, num(1, 300), dbl(2, 1.5))[:-3]
        with self.assertRaises(pyt.Bad):
            pyt.node(raw, 0)


class TestFile(unittest.TestCase):

    def setUp(self):
        self.layers, self.feats, self.lost = pyt.features(sample())
        self.by_id = {f["id"]: f for f in self.feats}

    def test_layer_table(self):
        self.assertEqual(self.layers, {0: "Измерения", 7: "Дороги"})

    def test_layer_of_object_and_default(self):
        self.assertEqual(self.by_id[20]["layer"], 7)
        self.assertEqual(self.by_id[20]["code"], "Бетон")
        # Без поля 8 - слой 0.
        self.assertEqual(self.by_id[21]["layer"], 0)
        self.assertEqual(self.by_id[21]["text"], "Склад")

    def test_points_and_symbol(self):
        p = self.by_id[3]
        self.assertEqual(p["kind"], "point")
        self.assertEqual(p["coords"], [P[3]])
        self.assertEqual(p["z"], 153.0)
        self.assertEqual(p["symbol"], 1)
        self.assertEqual(self.by_id[5]["symbol"], 0)

    def test_segment(self):
        self.assertEqual(self.by_id[20]["kind"], "line")
        self.assertEqual(self.by_id[20]["coords"], [P[1], P[2]])

    def test_area_ring_follows_arc(self):
        self.assertEqual(self.lost, 0)
        poly = self.by_id[23]
        self.assertEqual(poly["kind"], "polygon")
        pts = poly["coords"]
        self.assertEqual(pts[0], P[1])
        self.assertEqual(pts[-1], P[1])
        # Квадрат 10 x 10 и полукруг радиуса 5 наружу.
        area = 0.0
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            area += x0 * y1 - x1 * y0
        self.assertAlmostEqual(abs(area) / 2, 100 + math.pi * 12.5,
                               delta=0.5)
        self.assertGreater(max(x for x, _ in pts), 1014.9)

    def test_arc_line(self):
        arc = self.by_id[22]
        self.assertEqual(arc["kind"], "line")
        self.assertEqual(arc["coords"][0], P[2])
        for x, y in arc["coords"]:
            self.assertAlmostEqual(math.hypot(x - 1010.0, y - 2005.0), 5.0)

    def test_area_with_unknown_number_is_lost(self):
        raw = sample().replace(struct.pack("<6I", 1, 2, 22, 3, 4, 1),
                               struct.pack("<6I", 1, 2, 99, 3, 4, 1))
        _, feats, lost = pyt.features(raw)
        self.assertEqual(lost, 1)
        self.assertFalse(any(f["kind"] == "polygon" for f in feats))


class TestDemo(unittest.TestCase):
    """Пример модуля - выдуманный карьер (tools/make_pyt_demo.py)."""

    def test_demo_reads_whole(self):
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "demo", "pythagoras", "quarry.pyt")
        with open(path, "rb") as handle:
            layers, feats, lost = pyt.features(handle.read())
        self.assertEqual(len(layers), 8)
        self.assertEqual(lost, 0)
        kinds = {f["kind"] for f in feats}
        self.assertEqual(kinds, {"point", "line", "polygon", "text"})
        for f in feats:
            if f["kind"] != "polygon":
                continue
            pts = f["coords"]
            area = abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1)
                           in zip(pts, pts[1:]))) / 2
            self.assertAlmostEqual(area, f["area"], delta=1.0)
        # Опорные пункты - точки со знаком, вершины - точки построения.
        signs = [f for f in feats if f["kind"] == "point"
                 and f["symbol"] != 0]
        self.assertEqual(len(signs), 4)


if __name__ == "__main__":
    unittest.main()
