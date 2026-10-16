# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Источники данных: свои адреса рельефа и основы, запись высот."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import sources  # noqa: E402
import terrain as tr  # noqa: E402


def mapbox_rgb(height):
    value = int(round((height + 10000.0) / 0.1))
    return (value >> 16) & 255, (value >> 8) & 255, value & 255


class TestAddresses(unittest.TestCase):

    def test_terrain_falls_back_to_default(self):
        self.assertEqual(sources.terrain("", "mapbox"),
                         (sources.TERRAIN_URL, "terrarium"))
        self.assertEqual(sources.terrain("https://x/{z}/{y}.png", "mapbox"),
                         (sources.TERRAIN_URL, "terrarium"))
        own = "https://dem.example/{z}/{x}/{y}.png"
        self.assertEqual(sources.terrain(own, "mapbox"), (own, "mapbox"))
        self.assertEqual(sources.terrain(own, "other"), (own, "terrarium"))

    def test_vector_and_probe(self):
        self.assertEqual(sources.vector(""), sources.VECTOR_TILEJSON)
        self.assertEqual(sources.vector("ftp://x"), sources.VECTOR_TILEJSON)
        self.assertEqual(sources.vector(" https://v.example/tiles.json "),
                         "https://v.example/tiles.json")
        self.assertEqual(sources.tile_probe("https://a/{z}/{x}/{y}.png", 3, 4,
                                            5), "https://a/3/4/5.png")


class TestEncoding(unittest.TestCase):

    def test_mapbox_terrain_rgb(self):
        heights = [-10000.0, -432.1, 0.0, 1234.5, 8848.8]
        rgba = np.zeros((1, len(heights), 4), dtype=np.uint8)
        for n, h in enumerate(heights):
            rgba[0, n, :3] = mapbox_rgb(h)
        got = tr.decode(rgba, None, "mapbox")[0]
        self.assertTrue(np.allclose(got, heights, atol=0.06))
        # Пол высот действует и у этой записи.
        self.assertEqual(float(tr.decode(rgba, 0.0, "mapbox")[0, 1]), 0.0)

    def test_terrarium_is_default(self):
        rgba = np.array([[[128, 0, 0, 255]]], dtype=np.uint8)
        self.assertEqual(float(tr.decode(rgba, None)[0, 0]), 0.0)


class TestShortCredits(unittest.TestCase):

    def test_names_without_labels_licenses_and_repeats(self):
        found = sources.short_credits([
            "Esri, Vantor, Earthstar Geographics, and the GIS User Community",
            "Gravity: XGM2019e, Zingerle et al. 2020, ICGEM, CC BY 4.0",
            "Bouguer anomaly: XGM2019e, Zingerle et al. 2020, ICGEM, "
            "CC BY 4.0; relief: ETOPO 2022, NOAA NCEI",
            "© OpenStreetMap contributors",
            "Submarine cables: © OpenStreetMap contributors",
            "Earthquakes: USGS · Slabs: USGS Slab2",
            "CRUST1.0, Laske, Masters, Ma, Pasyanos, 2013"])
        self.assertEqual(found, [
            "Esri, Vantor, Earthstar Geographics, and the GIS User Community",
            "XGM2019e", "ETOPO 2022", "© OpenStreetMap contributors",
            "USGS", "USGS Slab2", "CRUST1.0"])

    def test_kept_credits_stay_whole(self):
        found = sources.short_credits(
            ["Esri, Vantor", "Terrain: Mapzen, SRTM, GMTED, ETOPO1 and others",
             "NASA GIBS, VIIRS"], keep=2)
        self.assertEqual(found, ["Esri, Vantor",
                                 "Terrain: Mapzen, SRTM, GMTED, ETOPO1 and "
                                 "others", "NASA GIBS"])


if __name__ == "__main__":
    unittest.main()
