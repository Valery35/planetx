# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Исторические землетрясения ISC-GEM: промежутки, разбор, файл."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import iscgem  # noqa: E402

# Начало ответа ComCat catalog=iscgem 17 октября 2026 года, сокращено.
CSV = (
    "time,latitude,longitude,depth,mag,magType,nst,gap,dmin,rms,net,id,"
    "updated,place,type\n"
    "1904-04-04T10:02:34.560Z,41.802,23.108,15,7.02,mw,,,,,iscgem,"
    "iscgem16957905,2022-04-26T18:08:12.000Z,\"1 km NE of Kresna, "
    "Bulgaria\",earthquake\n"
    "1906-04-18T13:12:26Z,37.75,-122.55,,7.9,mw,,,,,iscgem,"
    "iscgem16957602,2022-04-26T18:08:12.000Z,San Francisco,earthquake\n"
    "1910-01-01T00:00:00.000Z,,,10,6.0,mw,,,,,iscgem,bad,,,earthquake\n")


class TestIscGem(unittest.TestCase):
    def test_periods_cover_years_without_gaps(self):
        periods = iscgem.periods(2026)
        self.assertEqual(periods[0], ("1900-01-01", "1960-01-01"))
        self.assertEqual(periods[-1][1], "2027-01-01")
        for (_, end), (start, _) in zip(periods, periods[1:]):
            self.assertEqual(end, start)

    def test_parse_skips_rows_without_place(self):
        events = iscgem.parse(CSV.encode("utf-8"))
        self.assertEqual(len(events), 2)
        first, second = events
        self.assertAlmostEqual(first.lat, 41.802)
        self.assertAlmostEqual(first.mag, 7.02)
        self.assertEqual(first.place, "1 km NE of Kresna, Bulgaria")
        self.assertTrue(first.url.endswith("/iscgem16957905"))
        # Секунды до 1970 года отрицательны, время без долей тоже читается.
        self.assertLess(second.time, 0)
        self.assertEqual(second.depth, 0.0)

    def test_file_round_trip(self):
        events = iscgem.parse(CSV)
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, iscgem.FILE)
            iscgem.save(events, path)
            back = iscgem.load(path)
        self.assertEqual(back, events)


if __name__ == "__main__":
    unittest.main()
