# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Магнитное поле: модель IGRF-14 и полюса NOAA."""
import math
import os
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))

import geomag  # noqa: E402

DATA = os.path.join(os.path.dirname(HERE), "data")


def load():
    with open(os.path.join(DATA, "igrf14coeffs.txt"), encoding="ascii") as fh:
        model = geomag.parse_igrf(fh.read())
    with open(os.path.join(DATA, "magnetic_poles.json"),
              encoding="utf-8") as fh:
        poles = geomag.parse_poles(fh.read())
    return model, poles


class TestGrid(unittest.TestCase):
    """Поле сеткой и линии равного склонения."""

    def setUp(self):
        self.model, _ = load()
        self.coeffs = self.model.at(2020.0)

    def test_grid_matches_point_field(self):
        lats = [-60.0, 0.0, 55.75]
        lons = [-150.0, 37.62, 100.0]
        x, y, z = geomag.components_grid(self.coeffs, self.model.nmax,
                                         lats, lons)
        for i, lat in enumerate(lats):
            for j, lon in enumerate(lons):
                px, py, pz = geomag.components(self.coeffs, self.model.nmax,
                                               lat, lon)
                self.assertAlmostEqual(x[i, j], px, delta=1e-6)
                self.assertAlmostEqual(y[i, j], py, delta=1e-6)
                self.assertAlmostEqual(z[i, j], pz, delta=1e-6)

    def test_isogonic_points_have_their_declination(self):
        lats, lons, values = geomag.declination_grid(self.coeffs,
                                                     self.model.nmax)
        lines = geomag.isogonic_lines(lats, lons, values)
        levels = {level for level, _ in lines}
        self.assertIn(0.0, levels)
        self.assertIn(10.0, levels)
        self.assertIn(-10.0, levels)
        worst = 0.0
        for level, points in lines:
            if abs(level) > 40.0:
                continue
            for lat, lon in points[::7]:
                found = geomag.field(self.model, lat, lon, 2020.0)
                if abs(lat) > 70.0 or found["horizontal"] < 10000.0:
                    # У полюсов Земли и у магнитных полюсов, где линии
                    # сходятся, склонение меняется быстрее шага сетки.
                    continue
                worst = max(worst, abs(found["declination"] - level))
        # Сетка 2°: между узлами склонение линейно с точностью до градуса.
        self.assertLess(worst, 1.0)


class TestModel(unittest.TestCase):
    def setUp(self):
        self.model, self.poles = load()

    def test_years_of_model(self):
        self.assertEqual(self.model.nmax, 13)
        self.assertEqual(self.model.first, 1900.0)
        self.assertEqual(self.model.last, 2030.0)
        self.assertIsNone(geomag.field(self.model, 55.0, 37.0, 1899.0))
        self.assertIsNone(geomag.field(self.model, 55.0, 37.0, 2031.0))
        # g10 на 2025 год - коэффициент файла как есть.
        self.assertAlmostEqual(self.model.at(2025.0)[0], -29350.0)
        self.assertAlmostEqual(self.model.at(2027.0)[0], -29350.0 + 2 * 12.6)

    def test_field_points_down_in_north(self):
        north = geomag.field(self.model, 55.75, 37.62, 2020.0)
        south = geomag.field(self.model, -33.87, 151.21, 2020.0)
        self.assertGreater(north["inclination"], 60.0)
        self.assertLess(south["inclination"], -60.0)
        self.assertTrue(20000.0 < north["total"] < 70000.0)

    def test_declination_east_where_known(self):
        # Склонение восточное в Боулдере (около +8° в 2020 году) и
        # в Москве (около +11.5°). Сторож знака восточной составляющей:
        # полюс по нулю горизонтальной составляющей знака не видит.
        boulder = geomag.field(self.model, 40.0, -105.25, 2020.0)
        moscow = geomag.field(self.model, 55.75, 37.62, 2020.0)
        self.assertTrue(7.5 < boulder["declination"] < 9.0)
        self.assertTrue(10.5 < moscow["declination"] < 12.5)

    def test_igrf_pole_matches_noaa_table(self):
        # Сторож расчёта поля: точка нулевой горизонтальной составляющей
        # по IGRF-14 - полюс таблицы NOAA. На прежних ошибках знаков
        # и пересчёта широты поиск уходит на сотни километров.
        for key, years in (("south", (1950.0, 2000.0, 2020.0)),
                           ("north", (2020.0,))):
            track = self.poles[key]
            for year in years:
                table = geomag.pole_at(track, year)
                found = geomag.dip_pole(self.model, year, table)
                self.assertIsNotNone(found, (key, year))
                self.assertLess(abs(found[0] - table[0]), 0.05, (key, year))
                field = geomag.field(self.model, found[0], found[1], year)
                self.assertLess(field["horizontal"], 1.0)


class TestPoles(unittest.TestCase):
    def setUp(self):
        self.model, self.poles = load()

    def test_table_years(self):
        for key in ("north", "south"):
            track = self.poles[key]
            self.assertEqual(track[0][0], 1590.0)
            self.assertEqual(track[-1][0], 2025.0)
            self.assertTrue(all(-180.0 <= lon <= 180.0
                                for _, _, lon in track))

    def test_between_years_on_arc(self):
        track = self.poles["north"]
        a = geomag.pole_at(track, 1900.0)
        b = geomag.pole_at(track, 1901.0)
        mid = geomag.pole_at(track, 1900.5)
        self.assertTrue(min(a[0], b[0]) - 0.01 <= mid[0]
                        <= max(a[0], b[0]) + 0.01)

    def test_after_table_from_igrf(self):
        track = self.poles["north"]
        late = geomag.pole(self.model, track, 2028.0)
        self.assertIsNotNone(late)
        # Полюс идёт к Сибири - за три года сдвиг меньше 300 км.
        last = track[-1][1:]
        dot = sum(p * q for p, q in zip(geomag._unit(*late),
                                         geomag._unit(*last)))
        self.assertLess(math.degrees(math.acos(min(dot, 1.0))), 3.0)
        self.assertIsNone(geomag.pole(self.model, track, 1500.0))

    def test_trail_ends_at_year(self):
        trail = geomag.trail(self.poles["south"], 1600.0)
        self.assertEqual(len(trail), 11)

    def test_trail_starts_at_left_handle(self):
        # Левый бегунок обрезает начало следа - замечание пользователя
        # от 14 октября 2026 года.
        track = self.poles["north"]
        whole = geomag.trail(track, 2000.0)
        cut = geomag.trail(track, 2000.0, start=1900.0)
        self.assertLess(len(cut), len(whole))
        self.assertEqual(cut[0], geomag.pole_at(track, 1900.0))
        self.assertEqual(cut[-1], whole[-1])
        # Левый бегунок раньше таблицы - след целиком.
        self.assertEqual(geomag.trail(track, 2000.0, start=1500.0), whole)

    def test_year_of_seconds(self):
        # 1 января - целый год, средним годом выходило 2019.997.
        self.assertAlmostEqual(geomag.year_of(0.0), 1970.0)
        self.assertEqual(geomag.year_of(1577836800.0), 2020.0)
        self.assertAlmostEqual(geomag.year_of(-2208988800.0), 1900.0)
        self.assertAlmostEqual(geomag.year_of(1593561600.0),
                               2020.0 + 182.0 / 366.0)


if __name__ == "__main__":
    unittest.main()
