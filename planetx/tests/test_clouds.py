# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака: дата снимка, адрес, прозрачность по белизне, тайл снимка."""
import calendar
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import clouds  # noqa: E402


def utc(*parts):
    return calendar.timegm(parts + (0,) * (6 - len(parts)))


class TestDate(unittest.TestCase):

    def test_yesterday_after_noon(self):
        self.assertEqual(clouds.image_date(utc(2026, 9, 29, 13)),
                         "2026-09-28")

    def test_day_before_in_the_morning(self):
        # Вчерашние сутки GIBS утром ещё собирает.
        self.assertEqual(clouds.image_date(utc(2026, 9, 29, 6)),
                         "2026-09-27")

    def test_url_has_date_and_fields(self):
        url = clouds.url_template(utc(2026, 9, 29, 13))
        self.assertIn("/2026-09-28/GoogleMapsCompatible_Level9/", url)
        self.assertTrue(url.endswith("/{z}/{y}/{x}.jpg"))


class TestAlpha(unittest.TestCase):

    def alpha(self, rgb):
        return int(clouds.cloud_rgba(np.array([[rgb + (255,)]],
                                              dtype=np.uint8))[0, 0, 3])

    def test_white_is_cloud(self):
        self.assertEqual(self.alpha((250, 250, 250)), 255)

    def test_dark_and_gap_are_clear(self):
        self.assertEqual(self.alpha((0, 0, 0)), 0)
        self.assertEqual(self.alpha((20, 60, 110)), 0)
        self.assertEqual(self.alpha((60, 90, 40)), 0)

    def test_sand_is_clear(self):
        self.assertEqual(self.alpha((225, 195, 150)), 0)

    def test_colour_is_premultiplied(self):
        out = clouds.cloud_rgba(np.full((1, 1, 4), 170, dtype=np.uint8))
        self.assertLess(out[0, 0, 3], 255)
        self.assertLessEqual(out[0, 0, 0], out[0, 0, 3])


class TestPolarFade(unittest.TestCase):

    def test_clouds_fade_towards_the_cap(self):
        # Тайл 3/0/0 - от 85° до 79.2° северной широты, сверху вниз.
        white = np.full((256, 256, 4), 250, dtype=np.uint8)
        alpha = clouds.cloud_rgba(white, (3, 0, 0))[:, 0, 3]
        self.assertEqual(alpha[-1], 255)
        self.assertLess(alpha[0], 5)
        self.assertTrue(np.all(np.diff(alpha.astype(int)) >= 0))

    def test_south_is_symmetric(self):
        lat = clouds.row_latitudes((3, 0, 7), 4)
        self.assertLess(lat[-1], -80.0)
        self.assertAlmostEqual(clouds.row_latitudes((0, 0, 0), 2)[0],
                               -clouds.row_latitudes((0, 0, 0), 2)[1])

    def test_middle_latitudes_untouched(self):
        white = np.full((8, 8, 4), 250, dtype=np.uint8)
        self.assertTrue(np.all(clouds.cloud_rgba(white, (3, 4, 2))[..., 3]
                               == 255))


class TestSourceKey(unittest.TestCase):

    def test_deep_tile_takes_level_nine(self):
        self.assertEqual(clouds.source_key((12, 2800, 1200)),
                         (9, 350, 150))
        self.assertEqual(clouds.source_key((5, 20, 9)), (5, 20, 9))


if __name__ == "__main__":
    unittest.main()
