# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подложки из подключений XYZ QGIS."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import basemap as bm  # noqa: E402

ESRI = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}")
TERRARIUM = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
             "{z}/{x}/{y}.png")

# Подключения, как их показал QGIS 4.0.3 26 сентября 2026 года,
# и Esri World Imagery с другим адресом сервиса. С адресом встроенной
# подложки подключение пропускается, это проверяет
# TestSettings.test_connection_with_builtin_url_is_skipped.
ESRI_OTHER = ESRI.replace("//server.", "//services.")
SETTINGS = {
    "OpenStreetMap": {"url": bm.OSM_URL, "zmin": "0", "zmax": "19",
                      "http-header": {}, "referer": "", "authcfg": ""},
    "Mapzen Global Terrain": {"url": TERRARIUM, "zmin": "0", "zmax": "15",
                              "interpretation": "terrariumterrain"},
    "Esri World Imagery": {"url": ESRI_OTHER, "zmin": "0", "zmax": "18"},
}


class TestUrl(unittest.TestCase):

    def test_xyz(self):
        self.assertEqual(bm.tile_url(ESRI, 3, 5, 2),
                         ESRI.replace("{z}/{y}/{x}", "3/2/5"))

    def test_tms(self):
        # {-y} считает строки снизу: на уровне 3 строка 2 сверху - 5 снизу.
        self.assertEqual(bm.tile_url("t/{z}/{x}/{-y}", 3, 1, 2), "t/3/1/5")

    def test_quadkey(self):
        # Пример из описания системы тайлов Bing Maps.
        self.assertEqual(bm.quadkey(3, 3, 5), "213")
        self.assertEqual(bm.tile_url("q/{q}.jpg", 3, 3, 5), "q/213.jpg")
        self.assertEqual(bm.quadkey(0, 0, 0), "")

    def test_valid(self):
        self.assertTrue(bm.valid_url(ESRI))
        self.assertTrue(bm.valid_url("a/{q}"))
        self.assertTrue(bm.valid_url("a/{z}/{x}/{-y}"))
        self.assertFalse(bm.valid_url("a/{z}/{x}"))
        self.assertFalse(bm.valid_url("a/{z}/{x}/{y}/{switch:a,b}"))
        self.assertFalse(bm.valid_url("a/b.png"))


class TestSettings(unittest.TestCase):

    def test_list(self):
        sources = bm.from_settings(SETTINGS)
        self.assertEqual([s.name for s in sources], ["Esri World Imagery"])
        esri = sources[0]
        self.assertEqual(esri.max_level, 18)
        self.assertIn("Esri", esri.attribution[0])
        self.assertEqual(esri.parallel, bm.OTHER_PARALLEL)

    def test_terrain_skipped(self):
        names = [s.name for s in bm.from_settings(SETTINGS)]
        self.assertNotIn("Mapzen Global Terrain", names)

    def test_levels(self):
        items = {
            "deep": {"url": "a/{z}/{x}/{y}", "zmax": "23"},
            "empty": {"url": "b/{z}/{x}/{y}", "zmax": ""},
            "shallow": {"url": "c/{z}/{x}/{y}", "zmax": "1"},
            "late": {"url": "d/{z}/{x}/{y}", "zmin": "5"},
        }
        levels = {s.name: s.max_level for s in bm.from_settings(items)}
        self.assertEqual(levels, {"deep": bm.MAX_LEVEL,
                                  "empty": bm.DEFAULT_MAX})

    def test_headers(self):
        items = {"x": {"url": "a/{z}/{x}/{y}", "referer": "https://r/",
                       "http-header": {"X-Key": "1", "Empty": ""}}}
        source = bm.from_settings(items)[0]
        self.assertEqual(source.headers,
                         {"X-Key": "1", "Referer": "https://r/"})
        self.assertEqual(source.attribution, ("x", ""))

    def test_login(self):
        items = {"with": {"url": "a/{z}/{x}/{y}", "username": "u",
                          "password": "p"},
                 "without": {"url": "b/{z}/{x}/{y}", "username": "",
                             "password": ""}}
        sources = {s.name: s for s in bm.from_settings(items)}
        self.assertEqual((sources["with"].username,
                          sources["with"].password), ("u", "p"))
        self.assertIsNone(sources["without"].username)

    def test_osm(self):
        source = bm.osm()
        self.assertTrue(source.builtin)
        self.assertEqual(source.parallel, bm.OSM_PARALLEL)
        self.assertEqual(source.tile_url(1, 0, 1),
                         "https://tile.openstreetmap.org/1/0/1.png")
        self.assertFalse(source.example)

    def test_esri_example_is_default(self):
        first = bm.builtins()[0]
        self.assertEqual(first.name, "Esri World Imagery")
        self.assertTrue(first.builtin and first.example)
        self.assertEqual(first.parallel, bm.OTHER_PARALLEL)
        self.assertIn("Esri", first.attribution[0])
        self.assertEqual(
            first.tile_url(3, 5, 2),
            "https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/3/2/5")

    def test_connection_with_builtin_url_is_skipped(self):
        items = {"Моя Esri": {"url": bm.ESRI_URL, "zmin": "0",
                              "zmax": "19"}}
        self.assertEqual(bm.from_settings(items), [])



class TestMirrors(unittest.TestCase):
    """Зеркала тайлов planetx-terrain."""

    def test_terrain_tiles_get_jsdelivr(self):
        url = ("https://raw.githubusercontent.com/Valery35/planetx-terrain/"
               "main/mars/{z}/{x}/{y}.png")
        src = bm.Source("Mars", url)
        self.assertEqual(len(src.urls), 2)
        self.assertEqual(src.tile_url(1, 0, 1), url.replace(
            "{z}/{x}/{y}", "1/0/1"))
        self.assertTrue(src.next_mirror(100.0))
        self.assertEqual(src.tile_url(1, 0, 1),
                         "https://cdn.jsdelivr.net/gh/Valery35/"
                         "planetx-terrain@main/mars/1/0/1.png")
        # Не чаще паузы, потом - обратно на главный.
        self.assertFalse(src.next_mirror(110.0))
        self.assertTrue(src.next_mirror(100.0 + bm.MIRROR_PAUSE))
        self.assertEqual(src.mirror, 0)

    def test_other_sources_without_mirrors(self):
        src = bm.Source("OSM", bm.OSM_URL)
        self.assertEqual(src.urls, (bm.OSM_URL,))
        self.assertFalse(src.next_mirror(1000.0))


class TestReady(unittest.TestCase):
    """Готовые источники меню «Основа»."""

    def test_every_ready_source_has_valid_url_and_terms(self):
        for row in bm.READY:
            key, ru, en, url, top, credit, terms, warned, kind = row
            self.assertTrue(bm.valid_url(url), key)
            self.assertTrue(terms.startswith("https://"), key)
            self.assertLessEqual(top, bm.MAX_LEVEL, key)
            src = bm.ready_source(key, russian=False)
            self.assertEqual((src.name, src.ready), (en, key))
            self.assertEqual(src.attribution, (credit, terms))
        warned = {r[0] for r in bm.READY if r[7]}
        self.assertTrue({"google_satellite", "bing_aerial",
                         "yandex_satellite", "dgis_map"} <= warned)
        self.assertNotIn("opentopomap", warned)

    def test_menu_groups_cover_every_source_once(self):
        grouped = [k for _, keys in bm.READY_GROUPS for k in keys]
        self.assertEqual(sorted(grouped), sorted(bm.READY_KEYS))
        self.assertEqual(len(grouped), len(set(grouped)))
        warned = {r[0] for r in bm.READY if r[7]}
        self.assertEqual(set(dict(bm.READY_GROUPS)["warned"]), warned)

    def test_osm_france_servers_get_two_requests(self):
        for key in ("osm_hot", "osm_fr", "cyclosm"):
            self.assertEqual(bm.ready_source(key).parallel,
                             bm.OSM_PARALLEL, key)
        self.assertEqual(bm.ready_source("esri_ocean").parallel,
                         bm.OTHER_PARALLEL)

    def test_bing_uses_quadkey(self):
        src = bm.ready_source("bing_aerial")
        self.assertIn("/a030.jpeg", src.tile_url(3, 2, 2))

    def test_unknown_key(self):
        self.assertIsNone(bm.ready_entry("nope"))
        with self.assertRaises(KeyError):
            bm.ready_source("nope")


class TestElliptic(unittest.TestCase):
    """Снимки Яндекса в эллиптическом Меркаторе EPSG:3395."""

    def test_rows_at_perm_shift_south(self):
        # Тайл z=12 над Пермью: в EPSG:3395 он ниже на 3-4 тайла (у этой
        # широты северное смещение около 36 км, тайл около 5.2 км).
        first, last, at = bm.elliptic_rows(12, 1197)
        self.assertIn(first, (1200, 1201))
        self.assertIn(last - first, (0, 1))
        self.assertTrue(np.all(np.diff(at) > 0))

    def test_equator_tile_unchanged(self):
        # У экватора проекции совпадают: тайл встаёт сам на себя.
        first, last, at = bm.elliptic_rows(2, 2)
        self.assertEqual(first, 2)
        self.assertAlmostEqual(float(at[0]), 0.0, delta=1.0)

    def test_tile_takes_rows_from_both_parts(self):
        # Картинки частей - номер строки в столбце мира, тайл глобуса
        # берёт значения точно по elliptic_rows.
        z, y = 10, 299
        first, last, at = bm.elliptic_rows(z, y)
        images = []
        for row in range(first, last + 1):
            image = np.zeros((256, 256, 4), np.uint8)
            image[..., 0] = (np.arange(256) // 2 + (row - first) * 128)[
                :, None]
            images.append(image)
        tile = bm.elliptic_tile(z, y, images)
        self.assertEqual(tile.shape, (256, 256, 4))
        expected = np.clip(at, 0, len(images) * 256 - 1) / 2.0
        self.assertLess(float(np.max(np.abs(tile[:, 0, 0] - expected))),
                        1.01)

    def test_source_asks_one_or_two_tiles_of_column(self):
        src = bm.ready_source("yandex_satellite")
        urls = src.parts(12, 2687, 1197)
        self.assertIn(len(urls), (1, 2))
        self.assertTrue(all("x=2687" in u for u in urls))


class TestWms(unittest.TestCase):
    def test_bbox_of_tile(self):
        west, south, east, north = bm.tile_bbox(1, 0, 0)
        self.assertAlmostEqual(west, -bm.MERCATOR_HALF)
        self.assertAlmostEqual(north, bm.MERCATOR_HALF)
        self.assertAlmostEqual(east, 0.0, places=3)
        self.assertAlmostEqual(south, 0.0, places=3)

    def test_wms_source_puts_bbox(self):
        src = bm.WmsSource("w", "https://h/wms?BBOX={bbox}&W=256")
        url = src.tile_url(1, 1, 1)
        self.assertEqual(url, "https://h/wms?BBOX=0.00,-20037508.34,"
                              "20037508.34,0.00&W=256")


if __name__ == "__main__":
    unittest.main()
