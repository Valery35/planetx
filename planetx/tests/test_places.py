# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слой place векторного тайла и выбор надписей."""
import gzip
import os
import struct
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import places as pl  # noqa: E402
import tiling as tl  # noqa: E402


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


def field(number, wire, payload):
    key = varint((number << 3) | wire)
    if wire == 0:
        return key + varint(payload)
    if wire == 2:
        return key + varint(len(payload)) + payload
    return key + payload


def zigzag(value):
    return (value << 1) ^ (value >> 63)


def value_message(value):
    if isinstance(value, str):
        return field(1, 2, value.encode())
    if isinstance(value, float):
        return field(3, 1, struct.pack("<d", value))
    return field(5, 0, value)


def layer(name, features, extent=4096):
    """Слой MVT. features - (номер, тип, атрибуты, точки)."""
    keys = []
    values = []
    body = field(15, 0, 2) + field(1, 2, name.encode())
    for fid, kind, attrs, points in features:
        tags = bytearray()
        for k, v in attrs.items():
            if k not in keys:
                keys.append(k)
            if v not in values:
                values.append(v)
            tags += varint(keys.index(k)) + varint(values.index(v))
        geometry = bytearray(varint((len(points) << 3) | 1))
        x = y = 0
        for px, py in points:
            geometry += varint(zigzag(px - x)) + varint(zigzag(py - y))
            x, y = px, py
        feature = (field(1, 0, fid) + field(2, 2, bytes(tags))
                   + field(3, 0, kind) + field(4, 2, bytes(geometry)))
        body += field(2, 2, feature)
    for k in keys:
        body += field(3, 2, k.encode())
    for v in values:
        body += field(4, 2, value_message(v))
    body += field(5, 0, extent)
    return field(3, 2, body)


PERM = {"class": "city", "name": "Perm", "name:ru": "Пермь", "rank": 4}
TILE = (layer("water", [(1, 3, {"class": "lake"}, [(5, 5)])])
        + layer("place", [
            (11, 1, PERM, [(1000, 2000)]),
            (12, 1, {"class": "village", "name": "Kultayevo", "rank": 12},
             [(1100, 2100)]),
            (13, 1, {"class": "suburb", "name": "Motovilikha"},
             [(1200, 2200)]),
            (14, 1, {"class": "city", "name": "Moscow", "capital": 2},
             [(10, 10)]),
            (15, 1, {"class": "town", "name": "Buffer"}, [(-40, 100)]),
            (16, 2, {"class": "city", "name": "Line"},
             [(1, 1), (2, 2)])]))


class TestDecode(unittest.TestCase):

    def test_place_layer_only_points(self):
        features, extent = pl.decode_layer(TILE)
        self.assertEqual(extent, 4096)
        self.assertEqual([f[0] for f in features], [11, 12, 13, 14, 15])
        self.assertEqual(features[0][1]["name:ru"], "Пермь")
        self.assertEqual(features[0][1]["rank"], 4)
        self.assertEqual(features[0][2], [(1000, 2000)])
        self.assertEqual(features[4][2], [(-40, 100)])

    def test_gzip(self):
        self.assertEqual(pl.decode_layer(gzip.compress(TILE)),
                         pl.decode_layer(TILE))

    def test_missing_layer(self):
        self.assertEqual(pl.decode_layer(layer("water", [])), ([], 4096))

    def test_broken_tile(self):
        with self.assertRaises(pl.DecodeError):
            pl.decode_layer(TILE[:-3])

    def test_places(self):
        key = (8, 170, 76)
        out = pl.decode_places(key, TILE, languages=("ru",))
        names = [p.name for p in out]
        # Пригород не показывается, точка за краем тайла - дубль соседа.
        self.assertEqual(names, ["Пермь", "Kultayevo", "Moscow"])
        self.assertEqual([p.kind for p in out],
                         ["city", "village", "capital"])
        self.assertEqual([p.rank for p in out], [4, 12, 99])
        lat, lon = pl.tile_point(*key, 1000, 2000, 4096)
        self.assertAlmostEqual(out[0].lat, lat)
        english = pl.decode_places(key, TILE, languages=("en",))
        self.assertEqual(english[0].name, "Perm")

    def test_tile_point_matches_tiling(self):
        key = (8, 170, 76)
        west, south, east, north = tl.tile_bounds(*key)
        self.assertAlmostEqual(pl.tile_point(*key, 0, 0, 4096)[0], north)
        self.assertAlmostEqual(pl.tile_point(*key, 0, 0, 4096)[1], west)
        lat, lon = pl.tile_point(*key, 4096, 4096, 4096)
        self.assertAlmostEqual(lat, south)
        self.assertAlmostEqual(lon, east)

    def test_levels(self):
        self.assertEqual([pl.label_level(z) for z in (0, 2, 5, 16, 19)],
                         [0, 0, 3, 14, 14])

    def test_importance(self):
        a = pl.Place(1, "B", "city", 5, 0, 0)
        b = pl.Place(2, "A", "capital", 9, 0, 0)
        c = pl.Place(3, "C", "city", 2, 0, 0)
        d = pl.Place(4, "D", "village", 1, 0, 0)
        self.assertEqual(sorted([a, b, c, d], key=pl.importance),
                         [b, c, a, d])


OTHERS = (
    layer("mountain_peak", [
        (21, 1, {"class": "volcano", "name": "Elbrus", "name:ru": "Эльбрус",
                 "ele": 5642, "rank": 1}, [(100, 100)])])
    + layer("water_name", [
        (22, 2, {"class": "lake", "name": "Kama Reservoir"},
         [(10, 10), (20, 20), (30, 40)]),
        (23, 1, {"class": "sea", "name": "Caspian Sea"}, [(50, 50)])])
    + layer("park", [
        (24, 1, {"class": "national_park", "name": "Prielbrusye"},
         [(60, 60)]),
        (25, 1, {"class": "park", "name": "City park"}, [(61, 61)])])
    + layer("aerodrome_label", [
        (26, 1, {"class": "international", "name": "Bolshoye Savino"},
         [(70, 70)])])
    + layer("transportation_name", [
        (27, 2, {"class": "trunk", "ref": "Р-243;E 22"},
         [(0, 0), (80, 80), (160, 160)]),
        (28, 2, {"class": "minor", "ref": "57К-0001"}, [(1, 1), (2, 2)]),
        (29, 2, {"class": "trunk", "name": "No ref"}, [(3, 3), (4, 4)])]))


class TestOtherLayers(unittest.TestCase):

    def places(self):
        return {p.name: p for p in pl.decode_places((8, 170, 76), OTHERS,
                                                    languages=("ru",))}

    def test_kinds_and_info(self):
        found = self.places()
        self.assertEqual(sorted(found), sorted([
            "Эльбрус", "Kama Reservoir", "Caspian Sea", "Prielbrusye",
            "Bolshoye Savino", "Р-243"]))
        self.assertEqual(found["Эльбрус"].kind, "peak")
        self.assertEqual(found["Эльбрус"].info, 5642)
        self.assertEqual(found["Caspian Sea"].rank, 2)
        self.assertEqual(found["Kama Reservoir"].rank, 5)
        self.assertEqual(found["Prielbrusye"].kind, "park")
        self.assertEqual(found["Bolshoye Savino"].kind, "airport")
        self.assertEqual(found["Р-243"].kind, "road_ref")
        self.assertIsNone(found["Р-243"].info)

    def test_line_anchor_is_middle_vertex(self):
        found = self.places()
        lat, lon = pl.tile_point(8, 170, 76, 20, 20, 4096)
        self.assertAlmostEqual(found["Kama Reservoir"].lat, lat)
        self.assertAlmostEqual(found["Kama Reservoir"].lon, lon)
        lat, lon = pl.tile_point(8, 170, 76, 80, 80, 4096)
        self.assertAlmostEqual(found["Р-243"].lat, lat)

    def test_collect_by_kinds(self):
        store = pl.PlaceStore()
        store.add((6, 42, 18), list(self.places().values()))
        draw = [(8, 168, 72)]
        self.assertEqual({p.kind for p in store.collect(draw)},
                         {"peak", "water", "park", "airport", "road_ref"})
        self.assertEqual([p.name for p in store.collect(draw, {"peak"})],
                         ["Эльбрус"])
        self.assertEqual(store.collect(draw, set()), [])


class TestStore(unittest.TestCase):

    def test_wanted_levels(self):
        store = pl.PlaceStore()
        self.assertEqual(store.wanted([(10, 600, 300), (10, 601, 301),
                                       (1, 1, 0)]),
                         {(8, 150, 75), (0, 0, 0)})
        self.assertEqual(store.wanted([(19, 1 << 18, 5)]),
                         {(14, 1 << 13, 0)})

    def test_source_falls_back_to_ancestor(self):
        store = pl.PlaceStore()
        self.assertIsNone(store.source((10, 600, 300)))
        store.add((6, 37, 18), [])
        self.assertEqual(store.source((10, 600, 300)), (6, 37, 18))
        store.add((8, 150, 75), [])
        self.assertEqual(store.source((10, 600, 300)), (8, 150, 75))

    def test_collect_prefers_finer_and_sorts(self):
        store = pl.PlaceStore()
        coarse = pl.Place(7, "Пермь", "city", 4, 58.0, 56.2)
        fine = pl.Place(7, "Пермь", "city", 4, 58.01, 56.23)
        village = pl.Place(9, "Култаево", "village", 12, 57.9, 55.9)
        store.add((6, 37, 18), [coarse])
        store.add((8, 150, 75), [village, fine])
        out = store.collect([(10, 600, 300), (7, 74, 36)])
        self.assertEqual(out, [fine, village])
        self.assertIs(store.collect([(10, 600, 300), (7, 74, 36)]), out)


class TestMinLevel(unittest.TestCase):

    def test_states_only_from_finer_tiles(self):
        store = pl.PlaceStore()
        state = pl.Place(5, "Пермский край", "state", 2, 59.0, 56.0)
        country = pl.Place(6, "Россия", "country", 1, 60.0, 90.0)
        store.add((2, 2, 1), [state, country])
        self.assertEqual(store.collect([(4, 11, 5)]), [country])
        store.add((3, 5, 2), [state])
        self.assertEqual(store.collect([(5, 22, 10)]), [state])


class TestLanguages(unittest.TestCase):

    ATTRS = {"name": "Пермь", "name:de": "Perm", "name_latin": "Perm'",
             "name:zh": "彼尔姆"}

    def name(self, choice, ui="ru"):
        return pl.place_name(self.ATTRS, pl.name_languages(choice, ui))

    def test_as_qgis_follows_interface(self):
        self.assertEqual(pl.name_languages(pl.AS_QGIS, "ru"), ("ru",))
        self.assertEqual(pl.name_languages(pl.AS_QGIS, "de"),
                         ("de", "latin"))

    def test_unknown_interface_language_gives_english(self):
        self.assertEqual(pl.name_languages(pl.AS_QGIS, "fi"),
                         ("en", "latin"))

    def test_local_names(self):
        self.assertEqual(self.name(pl.LOCAL), "Пермь")

    def test_chosen_language(self):
        self.assertEqual(self.name("de"), "Perm")
        self.assertEqual(self.name("zh"), "彼尔姆")

    def test_fallback_latin_or_local(self):
        self.assertEqual(self.name("fr"), "Perm'")
        self.assertEqual(self.name("ja"), "Пермь")


class TestMaxHeight(unittest.TestCase):

    KINDS = {"city", "peak", "airport", "road_ref", "park"}

    def test_airports_and_road_numbers_only_below_1000_km(self):
        self.assertLessEqual({"airport", "road_ref"},
                             pl.kinds_at(self.KINDS, 9.9e5))
        self.assertEqual(pl.kinds_at(self.KINDS, 1.01e6), {"city", "park"})

    def test_peaks_only_below_400_km(self):
        self.assertIn("peak", pl.kinds_at(self.KINDS, 3.9e5))
        self.assertNotIn("peak", pl.kinds_at(self.KINDS, 4.1e5))

    def test_parks_only_below_3000_km(self):
        self.assertIn("park", pl.kinds_at(self.KINDS, 2.9e6))
        self.assertEqual(pl.kinds_at(self.KINDS, 3.1e6), {"city"})

    def test_other_classes_have_no_limit(self):
        self.assertEqual(pl.kinds_at({"city", "country"}, 2.0e7),
                         {"city", "country"})


class TestSelect(unittest.TestCase):

    def test_overlap_keeps_first(self):
        boxes = [(0, 0, 100, 20), (50, 10, 150, 30), (200, 0, 300, 20)]
        self.assertEqual(pl.select_labels(boxes, [0, 0, 0]), [0, 2])

    def test_touching_boxes_do_not_clash(self):
        boxes = [(0, 0, 100, 20), (100, 0, 200, 20)]
        self.assertEqual(pl.select_labels(boxes, [0, 0]), [0, 1])

    def test_previous_wins_inside_class_only(self):
        boxes = [(0, 0, 100, 20), (50, 10, 150, 30), (60, 5, 160, 25)]
        tiers = [2, 4, 4]
        # Надпись 2 была видна, внутри класса 4 она идёт раньше 1.
        self.assertEqual(pl.select_labels(boxes, tiers, previous={2}),
                         [0])
        boxes[0] = (1000, 0, 1100, 20)
        self.assertEqual(pl.select_labels(boxes, tiers, previous={2}),
                         [0, 2])
        # Прошлая надпись класса ниже не вытесняет более важную.
        self.assertEqual(pl.select_labels(
            [(0, 0, 10, 10), (5, 5, 15, 15)], [1, 3], previous={1}), [0])

    def test_matches_brute_force(self):
        import random
        rng = random.Random(3)
        boxes = []
        for _ in range(300):
            x, y = rng.uniform(0, 1500), rng.uniform(0, 900)
            boxes.append((x, y, x + rng.uniform(20, 200),
                          y + rng.uniform(10, 30)))
        tiers = [0] * len(boxes)
        placed = []
        for i, (x0, y0, x1, y1) in enumerate(boxes):
            if all(not (x0 < a1 and a0 < x1 and y0 < b1 and b0 < y1)
                   for a0, b0, a1, b1 in (boxes[j] for j in placed)):
                placed.append(i)
        self.assertEqual(pl.select_labels(boxes, tiers), placed)


if __name__ == "__main__":
    unittest.main()
