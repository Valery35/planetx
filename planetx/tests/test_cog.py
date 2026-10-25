# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение COG без GDAL (core/cog.py): файл собирается здесь же по
спецификации TIFF 6.0 и GeoTIFF, читается частями.

С GDAL 3.13 из QGIS 4.0.3 сверено 23 октября 2026 года на Copernicus
DEM у Валдая (уровни 9, 10, 12) и GEBCO 2026 (уровни 9, 12): окно
тайла совпало с gdal.Warp bilinear до 0.0 м во всех 65 536 точках."""
import os
import struct
import sys
import unittest
import zlib

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import cog  # noqa: E402


def float_predictor(tile):
    """Предиктор 3 TIFF: байты строки по плоскостям, старшие первыми,
    затем разности соседних байтов."""
    h, w = tile.shape
    raw = tile.astype("<f4").view(np.uint8).reshape(h, w, 4)[:, :, ::-1]
    planes = np.ascontiguousarray(raw.transpose(0, 2, 1)).reshape(h, 4 * w)
    diff = planes.copy()
    diff[:, 1:] = planes[:, 1:] - planes[:, :-1]
    return diff.tobytes()


def lzw_encode(data):
    """Кодировщик LZW в разметке TIFF для проверки разбора: сброс в начале,
    ширина растёт на код раньше, конец - код 257."""
    out, acc, bits = bytearray(), 0, 0

    def put(code, width):
        nonlocal acc, bits
        acc = (acc << width) | code
        bits += width
        while bits >= 8:
            bits -= 8
            out.append((acc >> bits) & 0xff)

    table = {bytes((i,)): i for i in range(256)}
    width, word = 9, b""
    put(256, width)
    for byte in data:
        grown = word + bytes((byte,))
        if grown in table:
            word = grown
            continue
        put(table[word], width)
        table[grown] = len(table) + 2
        if len(table) + 2 >= (1 << width) and width < 12:
            width += 1
        if len(table) + 2 >= 4093:
            put(256, width)
            table = {bytes((i,)): i for i in range(256)}
            width = 9
        word = bytes((byte,))
    if word:
        put(table[word], width)
    put(257, width)
    if bits:
        out.append((acc << (8 - bits)) & 0xff)
    return bytes(out)


def make_tiff(image, tile=16, point=True, predictor=3, nodata=None,
              origin=(33.0, 58.0), step=(0.01, 0.01), lzw=False):
    """Простой TIFF с тайлами Float32, DEFLATE и привязкой GeoTIFF."""
    h, w = image.shape
    across, down = -(-w // tile), -(-h // tile)
    padded = np.full((down * tile, across * tile), -9999.0, np.float32)
    padded[:h, :w] = image
    blobs = []
    for r in range(down):
        for c in range(across):
            part = padded[r * tile:(r + 1) * tile, c * tile:(c + 1) * tile]
            raw = float_predictor(part) if predictor == 3 \
                else part.astype("<f4").tobytes()
            blobs.append(lzw_encode(raw) if lzw else zlib.compress(raw))
    keys = [1, 1, 0, 1, 1025, 0, 1, 2 if point else 1]
    entries = [
        (256, 3, [w]), (257, 3, [h]), (258, 3, [32]),
        (259, 3, [5 if lzw else 8]),
        (277, 3, [1]), (317, 3, [predictor]), (322, 3, [tile]),
        (323, 3, [tile]), (324, 4, None), (325, 4, [len(b) for b in blobs]),
        (339, 3, [3]), (33550, 12, [step[0], step[1], 0.0]),
        (33922, 12, [0.0, 0.0, 0.0, origin[0], origin[1], 0.0]),
        (34735, 3, keys)]
    if nodata is not None:
        entries.append((42113, 2, (str(nodata) + "\0").encode("ascii")))
    count = len(entries)
    ifd_at = 8
    extra_at = ifd_at + 2 + count * 12 + 4
    extra = b""
    fmt = {3: "H", 4: "I", 12: "d"}
    layout = []
    for tag, kind, values in entries:
        if kind == 2:
            raw = values
            n = len(raw)
        else:
            values = values if values is not None else [0] * len(blobs)
            raw = struct.pack("<%d%s" % (len(values), fmt[kind]), *values)
            n = len(values)
        layout.append((tag, kind, n, raw))
        if len(raw) > 4:
            extra += raw + b"\0" * (len(raw) % 2)
    data_at = extra_at + len(extra)
    offsets, at = [], data_at
    for blob in blobs:
        offsets.append(at)
        at += len(blob)
    out = b"II*\0" + struct.pack("<I", ifd_at)
    out += struct.pack("<H", count)
    extra, cursor = b"", extra_at
    for tag, kind, n, raw in layout:
        if tag == 324:
            raw = struct.pack("<%dI" % n, *offsets)
        if len(raw) <= 4:
            out += struct.pack("<HHI", tag, kind, n) + raw.ljust(4, b"\0")
        else:
            out += struct.pack("<HHII", tag, kind, n, cursor)
            raw = raw + b"\0" * (len(raw) % 2)
            extra += raw
            cursor += len(raw)
    out += struct.pack("<I", 0) + extra + b"".join(blobs)
    return out


class Reader:
    """fetch по байтам файла, считает запросы."""

    def __init__(self, data):
        self.data = data
        self.calls = 0

    def __call__(self, start, length):
        self.calls += 1
        return self.data[start:start + length]


class TestCog(unittest.TestCase):

    def setUp(self):
        y, x = np.mgrid[0:40, 0:50].astype(np.float32)
        self.image = (x * 10.0 + y + 0.5).astype(np.float32)

    def test_tiles_and_predictor(self):
        file = cog.Cog(Reader(make_tiff(self.image)))
        image = file.images[0]
        self.assertEqual((image.width, image.height), (50, 40))
        self.assertEqual(image.across, 4)
        block = file._block(0, 0, 0, 49, 39)
        self.assertTrue(np.array_equal(block, self.image))
        plain = cog.Cog(Reader(make_tiff(self.image, predictor=1)))
        self.assertTrue(np.array_equal(plain._block(0, 3, 5, 20, 30),
                                       self.image[5:31, 3:21]))

    def test_pixel_is_point_shift(self):
        point = cog.Cog(Reader(make_tiff(self.image, point=True)))
        area = cog.Cog(Reader(make_tiff(self.image, point=False)))
        self.assertAlmostEqual(point.transform[0], 33.0 - 0.005)
        self.assertAlmostEqual(point.transform[3], 58.0 + 0.005)
        self.assertAlmostEqual(area.transform[0], 33.0)

    def test_sample_bilinear_and_outside(self):
        file = cog.Cog(Reader(make_tiff(self.image, point=False)))
        # Середина пикселя (2, 3) - точно его значение, между пикселями -
        # среднее, за краем - NaN.
        lon = np.array([33.0 + 2.5 * 0.01, 33.0 + 3.0 * 0.01, 32.0])
        lat = np.array([58.0 - 3.5 * 0.01, 58.0 - 3.5 * 0.01, 58.0])
        got = file.sample(lon, lat, 0)
        self.assertAlmostEqual(float(got[0]), 2 * 10 + 3 + 0.5, places=4)
        self.assertAlmostEqual(float(got[1]), 25 + 3 + 0.5, places=4)
        self.assertTrue(np.isnan(got[2]))

    def test_nodata_and_cache(self):
        image = self.image.copy()
        image[0, 0] = -32767.0
        reader = Reader(make_tiff(image, nodata=-32767))
        file = cog.Cog(reader)
        self.assertTrue(np.isnan(file._block(0, 0, 0, 1, 1)[0, 0]))
        before = reader.calls
        file._block(0, 0, 0, 1, 1)
        self.assertEqual(reader.calls, before)

    def test_lzw_tiles(self):
        # LZW у ALOS AW3D30 и USGS 3DEP, 25 октября 2026 года: прежде
        # разбор отвечал «compression 5».
        for predictor in (1, 3):
            file = cog.Cog(Reader(make_tiff(self.image, predictor=predictor,
                                            lzw=True)))
            self.assertTrue(np.array_equal(file._block(0, 0, 0, 49, 39),
                                           self.image))

    def test_lzw_long_stream_resets_table(self):
        rng = np.random.default_rng(5)
        data = rng.integers(0, 256, 30000, dtype=np.uint8).tobytes()
        self.assertEqual(cog.lzw_decode(lzw_encode(data)), data)
        self.assertEqual(cog.lzw_decode(lzw_encode(b"a" * 9000)), b"a" * 9000)

    def test_lzw_tiff_wraps_stream(self):
        raw = lzw_encode(bytes(range(64)))
        wrapped = cog.lzw_tiff(raw, 16, 4)
        self.assertTrue(wrapped.startswith(b"II*\0"))
        self.assertTrue(wrapped.endswith(raw))

    def test_not_tiff(self):
        with self.assertRaises(cog.CogError):
            cog.Cog(Reader(b"<html>no</html>" * 4))

    def test_tile_window_covers_tile(self):
        lon, lat = cog.tile_points(9, 303, 149)
        self.assertEqual(lon.shape, (256, 256))
        self.assertTrue((np.diff(lon[0]) > 0).all())
        self.assertTrue((np.diff(lat[:, 0]) < 0).all())


if __name__ == "__main__":
    unittest.main()
