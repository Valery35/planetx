# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Темы NASA GIBS: ряд дат, выбор дня, шкала, прозрачность."""
import calendar
import datetime
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import themes  # noqa: E402

# Ответ DescribeDomains SMAP за 5 октября 2026 года, с пропусками.
SMAP = ("<Domains><DimensionDomain><ows:Identifier>time</ows:Identifier>"
        "<Domain>2026-08-01/2026-09-02/P1D,2026-09-04/2026-09-08/P1D,"
        "2026-09-10/2026-09-19/P1D,2026-09-21/2026-09-29/P1D,"
        "2026-10-01/2026-10-01/P1D</Domain><Size>5</Size>"
        "</DimensionDomain></Domains>")
MONTHLY = "<Domain>1980-01-01/2026-07-01/P1M</Domain>"
SIXTEEN = "<Domain>2000-03-05/2026-08-29/P16D</Domain>"
# Цветовая карта по образцу GPM_Precipitation_Rate.
COLORMAP = """<ColorMaps>
<ColorMap title="Classifications"><Entries/>
<Legend type="classification">
<LegendEntry rgb="128,128,128" tooltip="No Data" id="0"/>
<LegendEntry rgb="191,191,191" tooltip="Insignificant" id="1"/>
</Legend></ColorMap>
<ColorMap title="Rain Rate" units="mm/hr"><Entries/>
<Legend type="continuous" minLabel="0.1" maxLabel="&#8805; 53.0">
<LegendEntry rgb="0,118,78" tooltip="0.1" id="2"/>
<LegendEntry rgb="0,148,36" tooltip="0.2" showTick="true" showLabel="true"
 label="0.2" id="3"/>
<LegendEntry rgb="195,228,0" tooltip="1" showTick="true" id="4"/>
<LegendEntry rgb="255,0,0" tooltip="53" id="5"/>
</Legend></ColorMap></ColorMaps>"""


def stamp(year, month, day):
    return float(calendar.timegm(datetime.date(year, month,
                                               day).timetuple()))


class TestDomains(unittest.TestCase):

    def test_parse(self):
        intervals = themes.parse_domains(SMAP)
        self.assertEqual(len(intervals), 5)
        self.assertEqual(intervals[0][2:], (1, "D"))

    def test_latest_without_moment(self):
        self.assertEqual(themes.pick_day(themes.parse_domains(SMAP)),
                         "2026-10-01")

    def test_unprocessed_day_is_dropped(self):
        # 1 октября в 12:00 UTC этот день ещё не готов: последним
        # остаётся 29 сентября, промежуток 1 октября отброшен.
        ready = themes.ready_intervals(themes.parse_domains(SMAP),
                                       stamp(2026, 10, 1) + 43200)
        self.assertEqual(themes.pick_day(ready), "2026-09-29")
        self.assertEqual(len(ready), 4)
        ready = themes.ready_intervals(themes.parse_domains(SIXTEEN),
                                       stamp(2026, 9, 1))
        self.assertEqual(themes.pick_day(ready), "2026-08-29")

    def test_compare_day_is_year_back(self):
        # Шторка: левая часть - день ряда год назад, у ряда через
        # 16 суток - ближайший шаг не позже. Короткий ряд - первый день.
        daily = themes.parse_domains("<Domain>2000-01-01/2026-10-05/P1D"
                                     "</Domain>")
        self.assertEqual(themes.compare_day(daily), "2025-10-05")
        self.assertEqual(themes.compare_day(daily, stamp(2020, 3, 1)),
                         "2019-03-02")
        sixteen = themes.parse_domains(SIXTEEN)
        self.assertEqual(themes.compare_day(sixteen), "2025-08-17")
        self.assertEqual(themes.compare_day(themes.parse_domains(SMAP)),
                         "2026-08-01")
        self.assertIsNone(themes.compare_day([]))

    def test_step_day_follows_series(self):
        intervals = themes.parse_domains(SMAP)
        self.assertEqual(themes.step_day(intervals, "2026-09-02", 1),
                         "2026-09-04")
        self.assertEqual(themes.step_day(intervals, "2026-09-04", -1),
                         "2026-09-02")
        self.assertIsNone(themes.step_day(intervals, "2026-10-01", 1))
        self.assertIsNone(themes.step_day(intervals, "2026-09-03", 1))

    def test_gap_gives_previous_day(self):
        # 3 сентября в ряду нет: берётся 2 сентября.
        intervals = themes.parse_domains(SMAP)
        self.assertEqual(themes.pick_day(intervals, stamp(2026, 9, 3)),
                         "2026-09-02")
        self.assertEqual(themes.pick_day(intervals, stamp(2026, 9, 15)),
                         "2026-09-15")

    def test_before_and_after_series(self):
        intervals = themes.parse_domains(SMAP)
        self.assertEqual(themes.pick_day(intervals, stamp(2020, 1, 1)),
                         "2026-08-01")
        self.assertEqual(themes.pick_day(intervals, stamp(2027, 1, 1)),
                         "2026-10-01")

    def test_monthly(self):
        intervals = themes.parse_domains(MONTHLY)
        self.assertEqual(themes.pick_day(intervals, stamp(2010, 5, 20)),
                         "2010-05-01")
        self.assertEqual(themes.pick_day(intervals, stamp(2026, 9, 20)),
                         "2026-07-01")

    def test_sixteen_days(self):
        intervals = themes.parse_domains(SIXTEEN)
        day = themes.pick_day(intervals, stamp(2000, 3, 25))
        self.assertEqual(day, "2000-03-21")

    def test_days_skip_gaps(self):
        found = themes.days(themes.parse_domains(SMAP))
        self.assertEqual(found[0], "2026-08-01")
        self.assertEqual(found[-1], "2026-10-01")
        self.assertNotIn("2026-09-03", found)
        self.assertNotIn("2026-09-30", found)
        monthly = themes.days(themes.parse_domains(MONTHLY))
        self.assertEqual(monthly[:2], ["1980-01-01", "1980-02-01"])
        self.assertEqual(len(monthly), 46 * 12 + 7)

    def test_span(self):
        lo, hi = themes.span(themes.parse_domains(SMAP))
        self.assertEqual((lo, hi), (stamp(2026, 8, 1), stamp(2026, 10, 1)))
        self.assertIsNone(themes.span([]))

    def test_empty(self):
        self.assertEqual(themes.parse_domains("<Domains/>"), [])
        self.assertIsNone(themes.pick_day([]))


class TestThemes(unittest.TestCase):

    def test_keys_unique_and_groups_known(self):
        keys = [t.key for t in themes.THEMES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(all(t.group in themes.GROUPS
                            for t in themes.THEMES))

    def test_url(self):
        url = themes.BY_KEY["rain"].url("2026-10-03")
        self.assertIn("/IMERG_Precipitation_Rate/default/2026-10-03/"
                      "GoogleMapsCompatible_Level6/{z}/{y}/{x}.png", url)

    def test_colormap(self):
        found = themes.parse_colormap(COLORMAP)
        self.assertEqual(found["kind"], "continuous")
        self.assertEqual(found["units"], "mm/hr")
        self.assertEqual(len(found["colors"]), 4)
        self.assertEqual(found["labels"], [(0.375, "0.2")])

    def test_colormap_without_labels_uses_ends(self):
        data = COLORMAP.replace('showLabel="true"', "")
        labels = themes.parse_colormap(data)["labels"]
        self.assertEqual(labels, [(0.0, "0.1"), (1.0, "≥ 53.0")])

    def test_gallery_has_every_map_once(self):
        items = themes.gallery_items()
        keys = [k for k, _, _ in items]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual(set(keys), set(themes.BY_KEY) | {"fires",
                                                          "temperature"})
        self.assertEqual(themes.gallery_group("fires"), "fire")
        self.assertEqual(themes.gallery_group("temperature"), "weather")
        self.assertEqual(dict((k, v) for k, _, v in items)["snow"], "gibs")
        self.assertIn("/1/0/1.png", themes.thumb_url(themes.BY_KEY["snow"],
                                                     "2026-10-05"))

    def test_overlay_clears_no_snow_class(self):
        rgba = np.array([[[82, 98, 106, 255], [89, 94, 111, 255]]],
                        np.uint8)
        out = themes.overlay_rgba(rgba, 1.0,
                                  clear=themes.CLEAR["snow_mass"])
        self.assertEqual(out[0, 0, 3], 0)
        self.assertEqual(out[0, 1, 3], 255)

    def test_overlay_keeps_no_data_clear(self):
        rgba = np.array([[[200, 100, 50, 255], [9, 9, 9, 0]]], np.uint8)
        out = themes.overlay_rgba(rgba, 0.5)
        self.assertEqual(out[0, 1].tolist(), [0, 0, 0, 0])
        self.assertEqual(out[0, 0].tolist(), [100, 50, 25, 128])


if __name__ == "__main__":
    unittest.main()
