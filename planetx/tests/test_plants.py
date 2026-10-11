# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Электростанции WRI: разбор, топливо, размер по мощности, файл."""
import io
import os
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import plants  # noqa: E402

CSV = ("country,country_long,name,gppd_idnr,capacity_mw,latitude,longitude,"
       "primary_fuel,other_fuel1,other_fuel2,other_fuel3,commissioning_year,"
       "owner,source,url\n"
       "RUS,Russia,Beloyarsk,X1,1485.0,56.84,61.32,Nuclear,,,,1964.0,"
       "Rosenergoatom,src,http://example.org/b\n"
       "RUS,Russia,Bad,X2,10,,,Gas,,,,,,,\n"
       "RUS,Russia,Kama HPP,X3,522,58.07,56.33,Hydro,,,,1954,RusHydro,,\n")


class TestPlants(unittest.TestCase):

    def test_parse_zip_fuel_and_round_trip(self):
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w") as archive:
            archive.writestr("global_power_plant_database.csv", CSV)
        data = plants.parse(out.getvalue())
        self.assertEqual(len(data), 2)  # без координат - пропущена
        keys = [f[0] for f in plants.FUELS]
        self.assertEqual(keys[data.fuel[0]], "nuclear")
        self.assertEqual(keys[data.fuel[1]], "hydro")
        self.assertEqual(data.text(0), ["Beloyarsk", "Russia", "Nuclear",
                                        "1964", "Rosenergoatom",
                                        "http://example.org/b"])
        path = os.path.join(tempfile.mkdtemp(), "p.npz")
        plants.save(data, path)
        back = plants.load(path)
        self.assertEqual(back.text(1)[0], "Kama HPP")
        self.assertTrue(np.allclose(back.capacity, [1485.0, 522.0]))

    def test_sizes_grow_with_capacity(self):
        s = plants.sizes([0.5, 1.0, 100.0, 5000.0, 20000.0])
        self.assertEqual(s[0], plants.SIZE_MIN)
        self.assertEqual(s[-1], plants.SIZE_MAX)
        self.assertTrue(s[1] < s[2] < s[3])
        self.assertEqual(plants.fuel_of("Petcoke"), 0)
        self.assertEqual(plants.fuel_of("Unknown"), len(plants.FUELS) - 1)


if __name__ == "__main__":
    unittest.main()
