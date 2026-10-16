# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты значений геофизики: запись тайла, раскраска, значение."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import emag  # noqa: E402
import fields  # noqa: E402


class TestFields(unittest.TestCase):

    def test_scale_round_trip(self):
        # Возраст с множителем 10 держит десятые доли млн лет.
        field = fields.FIELDS["seafloor_age"]
        values = np.array([[0.0, 1.8, 132.6, np.nan]])
        back = fields.decode(fields.encode(values, field.scale), field.scale)
        self.assertTrue(np.isnan(back[0, 3]))
        self.assertTrue(np.allclose(back[0, :3], values[0, :3], atol=0.051))

    def test_emag_same_as_before(self):
        # Магнитные аномалии - та же запись и раскраска, что у core/emag.
        values = np.array([[-300.0, -40.0, 0.0, 269.0, np.nan]])
        rgb = emag.encode(values)
        self.assertTrue(np.array_equal(
            rgb, fields.encode(values, fields.FIELDS["emag"].scale)))
        self.assertTrue(np.array_equal(
            emag.rgba(rgb), fields.rgba(fields.FIELDS["emag"], rgb)))

    def test_value_at_and_empty(self):
        field = fields.FIELDS["heatflow"]
        rgb = fields.encode(np.array([[178.1, np.nan]]), field.scale)
        self.assertAlmostEqual(fields.value_at(field, rgb, 0, 0), 178.1,
                               places=3)
        self.assertIsNone(fields.value_at(field, rgb, 1, 0))
        colors = fields.rgba(field, rgb)
        self.assertEqual(int(colors[0, 1, 3]), 0)
        self.assertGreater(int(colors[0, 0, 3]), 0)

    def test_every_field_is_described(self):
        self.assertEqual(set(fields.KEYS), set(fields.FIELDS))
        for key, field in fields.FIELDS.items():
            self.assertEqual(field.key, key)
            stops = [s for s, _ in field.stops]
            self.assertEqual(stops, sorted(stops), key)
            # Код Terrarium - до 65535: предел раскраски влезает.
            self.assertLess(abs(stops[-1]) * field.scale, 32767, key)
            self.assertTrue(fields.url(field).endswith(
                field.folder + "/{z}/{x}/{y}.png"))


if __name__ == "__main__":
    unittest.main()
