# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наборы слоёв под задачу, core/presets.py."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import presets  # noqa: E402

MANAGED = ("stars", "plates", "quakes", "deposits", "contours", "mining",
           "osm_mines", "infra_osm", "plants", "currents", "grid", "sun")


class TestPresets(unittest.TestCase):

    def test_changes_turn_on_own_and_off_others(self):
        extras = {"stars": True, "sun": True, "currents": True}
        out = presets.changes(presets.BY_KEY["geologist"], MANAGED, extras)
        self.assertEqual(out, {"plates": True, "quakes": True,
                               "deposits": True, "contours": True,
                               "sun": False, "currents": False})

    def test_no_changes_when_already_on(self):
        preset = presets.BY_KEY["miner"]
        extras = dict((key, True) for key in preset.extras)
        self.assertEqual(presets.changes(preset, MANAGED, extras), {})
        self.assertEqual(presets.current(MANAGED, extras, ""), "miner")

    def test_current_needs_theme(self):
        extras = {"stars": True, "currents": True, "contours": True}
        self.assertEqual(presets.current(MANAGED, extras, ""), "")
        self.assertEqual(presets.current(MANAGED, extras, "rain"),
                         "hydrologist")

    def test_unknown_mix_is_own_choice(self):
        extras = {"stars": True, "quakes": True, "plants": True}
        self.assertEqual(presets.current(MANAGED, extras, ""), "")

    def test_keys_unique(self):
        keys = [p.key for p in presets.PRESETS]
        self.assertEqual(len(keys), len(set(keys)))


if __name__ == "__main__":
    unittest.main()
