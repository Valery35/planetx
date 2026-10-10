# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Месторождения USGS: группы, разбор архивов, файл профиля."""
import io
import os
import sys
import tempfile
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))
import deposits as dp  # noqa: E402


def _zip(name, text):
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr(name, text)
    return out.getvalue()


MRDS = ("dep_id,site_name,latitude,longitude,country,commod1,commod2,"
        "commod3,dep_type,dev_stat\n"
        "10001,Carlin,40.9,-116.3,United States,\"Gold, Silver\",,,"
        "Sediment-hosted,Producer\n"
        "10002,Без координат,,,Russia,Copper,,,,Occurrence\n"
        "10003,Sand pit,45.0,-100.0,United States,\"Sand and Gravel\",,,,"
        "Past Producer\n")
MAJOR = ("gid,dep_name,country,latitude,longitude,commodity,dep_type,"
         "type_detail,model_name\n"
         "1536,Abakanskoye,Russia,52.4166,90.0333,Iron,Hydrothermal,,\n")


class TestDeposits(unittest.TestCase):
    def test_groups(self):
        names = [g[0] for g in dp.GROUPS]
        self.assertEqual(names[dp.group_of("Gold, Silver")], "precious")
        self.assertEqual(names[dp.group_of("Copper, Gold")], "base")
        self.assertEqual(names[dp.group_of("Sand and Gravel, Construction")],
                         "industrial")
        self.assertEqual(names[dp.group_of("Geothermal")], "energy")
        self.assertEqual(dp.group_of(""), dp.OTHER)
        self.assertEqual(dp.colors([0, dp.OTHER]).shape, (2, 3))

    def test_parse_both_and_round_trip(self):
        data = dp.parse(_zip("mrds.csv", MRDS),
                        _zip("ofr20051294/deposit.csv", MAJOR))
        self.assertEqual(len(data), 3)  # строка без координат пропущена
        self.assertTrue(data.major[0])
        self.assertEqual(data.text(0)[0], "Abakanskoye")
        self.assertEqual(data.text(1)[:3],
                         ["Carlin", "United States", "Gold, Silver"])
        self.assertEqual(data.text(1)[5], "10001")
        self.assertEqual(dp.STATUSES[data.status[1]], "Producer")
        self.assertEqual(list(dp.sizes(data.major, data.status)),
                         [dp.MAJOR_SIZE, 4.5, 4.0])
        path = os.path.join(tempfile.mkdtemp(), "d.npz")
        dp.save(data, path)
        back = dp.load(path)
        self.assertEqual(back.text(2)[0], "Sand pit")
        self.assertTrue(np.allclose(back.lat, data.lat, atol=1e-4))
        self.assertEqual(list(back.group), list(data.group))


if __name__ == "__main__":
    unittest.main()
