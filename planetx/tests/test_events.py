# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки событий Vantor и Planet: картинки COG (core/cog.py), каталоги
STAC и тайл дня (core/events.py).

Картинка-файл собирается здесь же без сжатия, тайл раскодирует простой
читатель TIFF теста вместо Qt. С Qt 6.11 QGIS 4.0.3 сверено 25 октября
2026 года на файлах Vantor (EPSG:4326, LZW), PlanetScope (UTM, LZW,
предиктор 2) и мозаике Planet (EPSG:3857, JPEG плоскостями)."""
import math
import os
import struct
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import cog  # noqa: E402
import coords  # noqa: E402
import events  # noqa: E402


def make_picture(pixels, tile=8, planar=1, origin=(10.0, 50.0),
                 step=(0.001, 0.001), keys=(1, 1, 0, 1, 1024, 0, 1, 2)):
    """TIFF с тайлами RGBA без сжатия: каналы вперемежку или
    плоскостями."""
    h, w, n = pixels.shape
    across, down = -(-w // tile), -(-h // tile)
    padded = np.zeros((down * tile, across * tile, n), np.uint8)
    padded[:h, :w] = pixels
    blobs = []
    planes = range(n) if planar == 2 else [None]
    for plane in planes:
        for r in range(down):
            for c in range(across):
                part = padded[r * tile:(r + 1) * tile,
                              c * tile:(c + 1) * tile]
                blobs.append((part if plane is None
                              else part[..., plane]).tobytes())
    entries = [
        (256, 3, [w]), (257, 3, [h]), (258, 3, [8] * n), (259, 3, [1]),
        (262, 3, [2]), (277, 3, [n]), (284, 3, [planar]),
        (322, 3, [tile]), (323, 3, [tile]), (324, 4, None),
        (325, 4, [len(b) for b in blobs]), (338, 3, [2]),
        (339, 3, [1] * n), (33550, 12, [step[0], step[1], 0.0]),
        (33922, 12, [0.0, 0.0, 0.0, origin[0], origin[1], 0.0]),
        (34735, 3, list(keys))]
    fmt = {3: "H", 4: "I", 12: "d"}
    count = len(entries)
    extra_at = 8 + 2 + count * 12 + 4
    layout, size = [], 0
    for tag, kind, values in entries:
        values = values if values is not None else [0] * len(blobs)
        raw = struct.pack("<%d%s" % (len(values), fmt[kind]), *values)
        layout.append((tag, kind, len(values), raw))
        if len(raw) > 4:
            size += len(raw) + len(raw) % 2
    offsets, at = [], extra_at + size
    for blob in blobs:
        offsets.append(at)
        at += len(blob)
    out = b"II*\0" + struct.pack("<I", 8) + struct.pack("<H", count)
    extra, cursor = b"", extra_at
    for tag, kind, n_values, raw in layout:
        if tag == 324:
            raw = struct.pack("<%dI" % n_values, *offsets)
        if len(raw) <= 4:
            out += struct.pack("<HHI", tag, kind, n_values) \
                + raw.ljust(4, b"\0")
        else:
            out += struct.pack("<HHII", tag, kind, n_values, cursor)
            raw = raw + b"\0" * (len(raw) % 2)
            extra += raw
            cursor += len(raw)
    return out + struct.pack("<I", 0) + extra + b"".join(blobs)


def read_strips(blob):
    """Теги и полосы TIFF из tiff_bytes - для проверки обёртки."""
    count = struct.unpack_from("<H", blob, 8)[0]
    tags = {}
    for i in range(count):
        tag, kind, n = struct.unpack_from("<HHI", blob, 10 + 12 * i)
        code, size = {3: ("H", 2), 4: ("I", 4), 7: ("B", 1)}[kind]
        at = 10 + 12 * i + 8
        if size * n > 4:
            at = struct.unpack_from("<I", blob, at)[0]
        tags[tag] = struct.unpack_from("<%d%s" % (n, code), blob, at)
    strips = [blob[o:o + c] for o, c in zip(tags[273], tags[279])]
    return tags, strips


def decode(blob):
    """Раскодирование тайла без сжатия, как сделал бы Qt."""
    tags, strips = read_strips(blob)
    w, h, n = tags[256][0], tags[257][0], tags[277][0]
    if tags[284][0] == 2:
        planes = [np.frombuffer(s, np.uint8).reshape(h, w) for s in strips]
        pixels = np.stack(planes, axis=2)
    else:
        pixels = np.frombuffer(strips[0], np.uint8).reshape(h, w, n)
    if n == 3:
        pixels = np.concatenate(
            [pixels, np.full((h, w, 1), 255, np.uint8)], axis=2)
    return pixels.copy()


class Reader:
    def __init__(self, data):
        self.data = data
        self.calls = 0

    def __call__(self, start, length):
        self.calls += 1
        return self.data[start:start + length]


def two_colors(h=16, w=16):
    """Левая половина красная, правая синяя, непрозрачные."""
    pixels = np.zeros((h, w, 4), np.uint8)
    pixels[:, :w // 2] = (200, 0, 0, 255)
    pixels[:, w // 2:] = (0, 0, 200, 255)
    return pixels


class TestPicture(unittest.TestCase):

    def test_wrap_keeps_tile_bytes_and_tags(self):
        for planar in (1, 2):
            pixels = two_colors()
            file = cog.Cog(Reader(make_picture(pixels, planar=planar)))
            image = file.images[0]
            self.assertTrue(image.picture)
            self.assertEqual(file.epsg, 4326)
            tile = file.picture(0, 1, 0, decode)
            self.assertEqual(tile.shape, (8, 8, 4))
            self.assertTrue((tile == (0, 0, 200, 255)).all())
            tags, strips = read_strips(cog.tiff_bytes(image, [b"abc"] * (
                4 if planar == 2 else 1)))
            self.assertEqual(tags[284], (planar,))
            self.assertEqual(tags[338], (2,))
            self.assertEqual(strips[-1], b"abc")

    def test_planes_of_tile_in_one_request(self):
        file = cog.Cog(Reader(make_picture(two_colors(), planar=2)))
        before = file.fetch.calls
        file.picture(0, 0, 0, decode)
        self.assertEqual(file.fetch.calls - before, 1)

    def test_sample_centres_and_edge(self):
        pixels = two_colors()
        pixels[:, 8:, 3] = 0  # правая половина прозрачная
        file = cog.Cog(Reader(make_picture(pixels)))
        # Середина пикселя (2, 3) и граница половин.
        xs = np.array([10.0 + 2.5 * 0.001, 10.0 + 8.0 * 0.001,
                       9.0])
        ys = np.array([50.0 - 3.5 * 0.001, 50.0 - 3.5 * 0.001, 50.0])
        rgba = file.sample_rgba(xs, ys, 0, decode)
        self.assertEqual(tuple(rgba[0]), (200, 0, 0, 255))
        # Край снимка не темнеет: цвет красный, прозрачность половина.
        self.assertEqual(tuple(rgba[1][:3]), (200, 0, 0))
        self.assertEqual(rgba[1][3], 128)
        self.assertEqual(rgba[2][3], 0)  # вне снимка

    def test_three_bands_black_is_transparent(self):
        pixels = np.zeros((8, 8, 3), np.uint8)
        pixels[:, 4:] = (10, 20, 30)
        file = cog.Cog(Reader(make_picture(pixels)))
        tile = file.picture(0, 0, 0, decode)
        self.assertEqual(tile[0, 0, 3], 0)
        self.assertEqual(tile[0, 5, 3], 255)

    def test_epsg_of_projected_file(self):
        keys = (1, 1, 0, 2, 1024, 0, 1, 1, 3072, 0, 1, 32618)
        file = cog.Cog(Reader(make_picture(two_colors(), keys=keys)))
        self.assertEqual(file.epsg, 32618)


class TestCrs(unittest.TestCase):

    def test_utm_arrays_match_scalar(self):
        lat = np.array([5.26, -33.9, 61.0, 0.0])
        lon = np.array([-75.36, 18.4, 30.2, 3.0])
        for zone, south, i in ((18, False, 0), (34, True, 1),
                               (36, False, 2), (31, False, 3)):
            e, n = coords.utm_arrays(lat[i:i + 1], lon[i:i + 1], zone,
                                     south)
            _, _, east, north = coords.to_utm(lat[i], lon[i], zone)
            self.assertAlmostEqual(float(e[0]), east, places=4)
            self.assertAlmostEqual(float(n[0]), north, places=4)

    def test_to_crs(self):
        x, y = cog.to_crs(3857, np.array([180.0]), np.array([0.0]))
        self.assertAlmostEqual(float(x[0]), math.pi * cog.RADIUS, places=3)
        self.assertAlmostEqual(float(y[0]), 0.0, places=6)
        lon, lat = cog.to_crs(4326, np.array([1.0]), np.array([2.0]))
        self.assertEqual((lon[0], lat[0]), (1.0, 2.0))
        e, n = cog.to_crs(32718, np.array([-75.0]), np.array([-10.0]))
        self.assertGreater(float(n[0]), 8.8e6)  # ложный север юга
        with self.assertRaises(cog.CogError):
            cog.to_crs(2154, np.array([0.0]), np.array([0.0]))


VANTOR_ITEM = {
    "type": "Feature", "id": "103001012263FC00",
    "bbox": [-5.35, 36.65, -4.96, 36.86],
    "assets": {"visual": {
        "href": "https://example.org/events/E/103001012263FC00.tif",
        "type": "image/tiff; application=geotiff; profile=cloud-optimized"}},
    "properties": {"datetime": "2026-02-15T11:41:24.955033Z",
                   "phase": "post", "pan_gsd": 0.83, "vehicle_name": "WV02"}}

PLANET_ITEM = {
    "type": "Feature", "id": "585-1059", "bbox": [-77.17, 6.14, -76.99, 6.31],
    "assets": {"visual": {"href": "./585-1059_visual.tif",
                          "type": "image/tiff; application=geotiff"}},
    "properties": {"datetime": "2026-05-16T12:00:00Z", "gsd": 4.77,
                   "pl:mosaic": "global_quarterly_2026q2_mosaic"}}


class TestCatalog(unittest.TestCase):

    def test_vantor_item(self):
        item = events.parse_item(VANTOR_ITEM, "https://example.org/e.json",
                                 events.VANTOR)
        self.assertEqual(item.day, "2026-02-15")
        self.assertEqual(item.phase, events.POST)
        self.assertAlmostEqual(item.gsd, 0.83)
        self.assertEqual(item.platform, "WV02")

    def test_planet_item_phase_from_path_and_relative_href(self):
        url = ("https://data.example/planet/e/pre-event/basemap/items/"
               "585-1059/585-1059.json")
        item = events.parse_item(PLANET_ITEM, url, events.PLANET,
                                 events.phase_of(url))
        self.assertEqual(item.phase, events.PRE)
        self.assertTrue(item.href.endswith(
            "/items/585-1059/585-1059_visual.tif"))
        self.assertEqual(item.platform, "Planet basemap")

    def test_item_without_visual_is_skipped(self):
        doc = dict(VANTOR_ITEM, assets={"thumbnail": {"href": "t.png"}})
        self.assertIsNone(events.parse_item(doc, "u", events.VANTOR))

    def test_event_title_and_day(self):
        doc = {"type": "Catalog", "id": "colombia-earthquake-2026-08-10",
               "title": "Planet Crisis Response — Colombia Earthquake "
                        "(2026)", "description": "M7.4"}
        event = events.parse_event(doc, "u", events.PLANET)
        self.assertEqual(event.title, "Colombia Earthquake (2026)")
        self.assertEqual(event.day, "2026-08-10")
        doc = {"type": "Collection", "id": "Spain-Portugal-Flooding-Feb-2026",
               "title": "", "extent": {
                   "spatial": {"bbox": [[-5.3, 36.6, -4.9, 36.8]]},
                   "temporal": {"interval": [["2026-02-15T11:41Z", None]]}}}
        event = events.parse_event(doc, "u", events.VANTOR)
        self.assertEqual(event.title, "Spain Portugal Flooding Feb 2026")
        self.assertEqual(event.day, "2026-02-15")
        self.assertEqual(event.box, (-5.3, 36.6, -4.9, 36.8))
        self.assertEqual(event.key, "vantor/Spain-Portugal-Flooding-Feb-2026")
        # Название, равное id, - тоже без дефисов.
        doc["title"] = doc["id"]
        self.assertEqual(events.parse_event(doc, "u", events.VANTOR).title,
                         "Spain Portugal Flooding Feb 2026")
        self.assertTrue(cog.known_crs(32718))
        self.assertFalse(cog.known_crs(2154))

    def test_links_are_absolute(self):
        doc = {"links": [{"rel": "child", "href": "./a/catalog.json"},
                         {"rel": "item", "href": "../b.json"},
                         {"rel": "license", "href": "https://x/l"}]}
        found = events.children(doc, "https://h/root/sub/catalog.json")
        self.assertEqual(found, [
            ("child", "https://h/root/sub/a/catalog.json"),
            ("item", "https://h/root/b.json")])

    def test_days_order_and_level(self):
        def item(day, phase, gsd, t):
            return events.Item(day + phase, "p", day, t, phase,
                               (0.0, 0.0, 1.0, 1.0), "h", gsd, "")
        items = [item("2026-05-16", "pre", 4.77, 1.0),
                 item("2026-08-10", "post", 3.8, 2.0),
                 item("2026-08-11", "post", 0.66, 3.0)]
        self.assertEqual(events.pre_day(items), "2026-05-16")
        self.assertEqual(events.post_day(items), "2026-08-11")
        self.assertEqual(len(events.intervals(items)), 3)
        self.assertEqual([i.day for i in events.shown(items, "2026-08-10")],
                         ["2026-08-10", "2026-05-16"])
        # 0.66 м у экватора - уровень 18 (0.6 м).
        self.assertEqual(events.max_level(items), 18)


class FakeCog:
    """Снимок одного цвета в EPSG:4326 или чужой системе."""

    def __init__(self, color, epsg=4326):
        self.color = color
        self.epsg = epsg

    def level_for(self, step):
        return 0

    def sample_rgba(self, xs, ys, level, decode):
        out = np.zeros(xs.shape + (4,), np.uint8)
        out[...] = self.color
        return out


class TestPaint(unittest.TestCase):

    def test_newer_over_older(self):
        box = events.tile_box(10, 600, 400)
        files = {"top": FakeCog((255, 0, 0, 128)),
                 "low": FakeCog((0, 0, 255, 255)),
                 "far": FakeCog((0, 255, 0, 255)),
                 "odd": FakeCog((0, 255, 0, 255), epsg=2154)}

        def item(name, where):
            return events.Item(name, "p", "2026-01-01", 0.0, "", where,
                               name, 1.0, "")
        far = (box[2] + 1.0, box[1], box[2] + 2.0, box[3])
        items = [item("odd", box), item("top", box), item("far", far),
                 item("low", box)]
        opened = []

        def open_cog(href):
            opened.append(href)
            return files[href]
        rgba = events.paint(items, 10, 600, 400, open_cog, None)
        self.assertNotIn("far", opened)
        pixel = rgba[100, 100]
        self.assertEqual(pixel[3], 255)
        self.assertAlmostEqual(int(pixel[0]), 128, delta=1)
        self.assertAlmostEqual(int(pixel[2]), 127, delta=1)

    def test_empty_tile_is_transparent(self):
        rgba = events.paint([], 3, 1, 1, None, None)
        self.assertEqual(rgba.shape, (256, 256, 4))
        self.assertFalse(rgba.any())


if __name__ == "__main__":
    unittest.main()
