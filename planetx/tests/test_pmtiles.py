# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Архив PMTiles v3 (core/pmtiles.py): архив собирается здесь же по
спецификации, с корнем и листовым каталогом. С архивом зданий Overture
2026-10-21.0 сверено 25 октября 2026 года: заголовок, метаданные и тайл
z14 у Перми читаются."""
import gzip
import os
import struct
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import pmtiles  # noqa: E402


def varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def encode(entries):
    """Каталог: записи (номер, серия, смещение, длина) по номерам."""
    out = varint(len(entries))
    last = 0
    for ident, _, _, _ in entries:
        out += varint(ident - last)
        last = ident
    for _, run, _, _ in entries:
        out += varint(run)
    for _, _, _, length in entries:
        out += varint(length)
    previous = None
    for ident, run, offset, length in entries:
        if previous is not None and offset == previous[0] + previous[1]:
            out += varint(0)
        else:
            out += varint(offset + 1)
        previous = (offset, length)
    return gzip.compress(out)


def build(tiles, leaf_after=None):
    """Архив из тайлов {(z, x, y): байты}. leaf_after - номера тайлов
    больше него уходят в листовой каталог."""
    data = b""
    rows = []
    for key in sorted(tiles, key=lambda k: pmtiles.tile_id(*k)):
        blob = gzip.compress(tiles[key])
        rows.append((pmtiles.tile_id(*key), 1, len(data), len(blob)))
        data += blob
    leaves = b""
    if leaf_after is not None:
        near = [r for r in rows if r[0] <= leaf_after]
        far = [r for r in rows if r[0] > leaf_after]
        leaves = encode(far)
        rows = near + [(far[0][0], 0, 0, len(leaves))]
    root = encode(rows)
    root_at = 127
    leaf_at = root_at + len(root)
    data_at = leaf_at + len(leaves)
    head = b"PMTiles" + bytes([3]) + struct.pack(
        "<QQQQQQQQQQQBBBBBB", root_at, len(root), 0, 0, leaf_at,
        len(leaves), data_at, len(data), len(tiles), len(tiles),
        len(tiles), 1, 2, 2, 1, 0, 14)
    head = head.ljust(127, b"\0")
    return head + root + leaves + data


class Reader:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def __call__(self, start, length):
        self.calls += 1
        return self.data[start:start + length]


class TestPmtiles(unittest.TestCase):

    def test_tile_ids_of_spec(self):
        self.assertEqual(pmtiles.tile_id(0, 0, 0), 0)
        self.assertEqual([pmtiles.tile_id(1, *xy) for xy in
                          ((0, 0), (0, 1), (1, 1), (1, 0))], [1, 2, 3, 4])
        self.assertEqual(pmtiles.tile_id(2, 0, 0), 5)
        # Номера уровня 14 идут подряд после всех мельче.
        self.assertEqual(pmtiles.tile_id(14, 0, 0),
                         (4 ** 14 - 1) // 3)

    def test_tiles_from_root_and_leaf(self):
        tiles = {(0, 0, 0): b"world", (14, 10500, 5100): b"perm",
                 (14, 10501, 5100): b"east", (5, 20, 9): b"five"}
        for leaf in (None, pmtiles.tile_id(5, 20, 9)):
            archive = pmtiles.Archive(Reader(build(tiles, leaf)))
            self.assertEqual(archive.max_zoom, 14)
            for key, blob in tiles.items():
                self.assertEqual(archive.tile(*key), blob)
            self.assertIsNone(archive.tile(14, 10502, 5100))
            self.assertIsNone(archive.tile(15, 0, 0))

    def test_leaf_read_once(self):
        tiles = {(14, 10500 + i, 5100): b"t%d" % i for i in range(5)}
        # Все тайлы - в листовом каталоге.
        data = build(tiles, min(pmtiles.tile_id(*k) for k in tiles) - 1)
        archive = pmtiles.Archive(Reader(data))
        archive.tile(14, 10503, 5100)
        before = archive.fetch.calls
        archive.tile(14, 10504, 5100)
        self.assertEqual(archive.fetch.calls - before, 1)  # только тайл

    def test_not_pmtiles(self):
        with self.assertRaises(pmtiles.PmtilesError):
            pmtiles.Archive(Reader(b"GIF89a" + b"\0" * 200))


if __name__ == "__main__":
    unittest.main()
