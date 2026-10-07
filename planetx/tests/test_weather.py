# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/weather.py: часы и выпуски GFS, индекс, поле."""
import calendar
import datetime
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import weather as w  # noqa: E402


def utc(*args):
    return float(calendar.timegm(datetime.datetime(*args).timetuple()))


# Строки индекса выпуска 12 UTC 6 октября 2026 года, час 24.
INDEX = """1:0:d=2026100612:PRMSL:mean sea level:24 hour fcst:
581:417551237:d=2026100612:TMP:2 m above ground:24 hour fcst:
582:418063107:d=2026100612:TMP:2 m above ground:18-24 hour max fcst:
588:422157490:d=2026100612:UGRD:10 m above ground:24 hour fcst:
589:423127024:d=2026100612:VGRD:10 m above ground:24 hour fcst:
590:424101000:d=2026100612:SPFH:2 m above ground:24 hour fcst:
593:425278190:d=2026100612:PRATE:surface:24 hour fcst:
595:426753859:d=2026100612:PRATE:surface:18-24 hour ave fcst:
636:446287564:d=2026100612:TCDC:entire atmosphere:24 hour fcst:
637:447105255:d=2026100612:TCDC:entire atmosphere:18-24 hour ave fcst:
"""


class TestRuns(unittest.TestCase):

    def test_hours(self):
        hours = w.hours()
        self.assertEqual(hours[:3], [0, 1, 2])
        self.assertIn(120, hours)
        self.assertNotIn(121, hours)
        self.assertIn(123, hours)
        self.assertEqual(hours[-1], 384)

    def test_runs_and_hours(self):
        now = utc(2026, 10, 6, 19, 30)
        self.assertEqual(w.run_time(now), utc(2026, 10, 6, 18))
        runs = w.candidate_runs(now)
        # Через 4 часа после выпуска 12 UTC свежий - он, 18 UTC ещё нет.
        self.assertEqual(runs[0], utc(2026, 10, 6, 12))
        self.assertEqual(runs[1], utc(2026, 10, 6, 6))
        run = runs[0]
        self.assertEqual(w.pick_hour(run, utc(2026, 10, 7, 12)), 24)
        self.assertEqual(w.pick_hour(run, utc(2026, 10, 7, 12, 40)), 25)
        # После 120 часа - кратные трём.
        self.assertEqual(w.pick_hour(run, run + 121.4 * 3600), 120)
        self.assertEqual(w.pick_hour(run, run + 122 * 3600), 123)
        self.assertEqual(w.pick_hour(run, run - 3600), 0)
        self.assertEqual(w.step_moment(run, run + 3600, 1), run + 7200)
        self.assertIsNone(w.step_moment(run, run, -1))
        # Прошлое - из выпуска не позже момента.
        self.assertEqual(w.source_run(run, utc(2026, 10, 1, 7)),
                         utc(2026, 10, 1, 6))
        self.assertEqual(w.source_run(run, utc(2026, 10, 9)), run)

    def test_file_url(self):
        url = w.file_url(utc(2026, 10, 6, 12), 24)
        self.assertEqual(url, w.BUCKET + "/gfs.20261006/12/atmos/"
                         "gfs.t12z.pgrb2.0p25.f024")


class TestIndex(unittest.TestCase):

    def test_ranges(self):
        self.assertEqual(w.byte_range(INDEX, w.BY_KEY["temperature"], 24),
                         (417551237, 418063106))
        # Ветер - U и V подряд одним участком.
        self.assertEqual(w.byte_range(INDEX, w.BY_KEY["wind"], 24),
                         (422157490, 424100999))
        # Осадки - в момент, не среднее за 6 часов.
        self.assertEqual(w.byte_range(INDEX, w.BY_KEY["precipitation"], 24),
                         (425278190, 426753858))
        # Последняя строка индекса - до конца файла.
        self.assertEqual(w.byte_range(INDEX, w.BY_KEY["clouds"], 24),
                         (446287564, 447105254))
        self.assertIsNone(w.byte_range(INDEX, w.BY_KEY["temperature"], 0))
        self.assertIsNone(w.byte_range("", w.BY_KEY["clouds"], 24))


class TestGrid(unittest.TestCase):

    def grid(self, values):
        # Сетка 1°: узлы от -180 до 179 по долготе, от 90 до -90.
        return w.make_grid(values, (-180.5, 1.0, 0.0, 90.5, 0.0, -1.0),
                           0.0, 0)

    def test_sample_bilinear_and_wrap(self):
        lat = np.repeat(np.linspace(90, -90, 181)[:, None], 360, axis=1)
        grid = self.grid(lat.astype(np.float32))
        self.assertAlmostEqual(float(w.sample(grid, 45.5, 10.0)), 45.5,
                               places=4)
        lon = np.tile(np.arange(360, dtype=np.float32), (181, 1))
        grid = self.grid(lon)
        # Между 179° и -180°: середина значений 359 и 0.
        self.assertAlmostEqual(float(w.sample(grid, 0.0, 179.5)), 179.5,
                               places=3)
        self.assertAlmostEqual(float(w.sample(grid, 0.0, -179.5)), 0.5,
                               places=3)

    def test_wind_speed_and_units(self):
        u = np.full((2, 2), 3.0)
        v = np.full((2, 2), 4.0)
        self.assertTrue(np.allclose(w.values_of(w.BY_KEY["wind"], [u, v]),
                                    5.0))
        rate = w.values_of(w.BY_KEY["precipitation"],
                           [np.full((2, 2), 1.0 / 3600.0)])
        self.assertTrue(np.allclose(rate, 1.0))

    def test_colors(self):
        rain = w.BY_KEY["precipitation"]
        rgba = w.colorize(rain, np.array([0.0, 0.05, 1.0, np.nan]))
        self.assertEqual(int(rgba[0, 3]), 0)
        self.assertEqual(int(rgba[1, 3]), 0)
        self.assertGreater(int(rgba[2, 3]), 200)
        self.assertEqual(int(rgba[3, 3]), 0)
        scale = w.legend(w.BY_KEY["temperature"])
        self.assertEqual(scale["units"], "°C")
        self.assertEqual(scale["labels"][0], (0.0, "-40"))
        self.assertEqual(scale["labels"][-1], (1.0, "40"))
