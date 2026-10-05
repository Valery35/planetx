# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/satellites.py."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid  # noqa: E402
import satellites  # noqa: E402
import sgp4  # noqa: E402

HEAD = ("OBJECT_NAME,OBJECT_ID,EPOCH,MEAN_MOTION,ECCENTRICITY,INCLINATION,"
        "RA_OF_ASC_NODE,ARG_OF_PERICENTER,MEAN_ANOMALY,EPHEMERIS_TYPE,"
        "CLASSIFICATION_TYPE,NORAD_CAT_ID,ELEMENT_SET_NO,REV_AT_EPOCH,"
        "BSTAR,MEAN_MOTION_DOT,MEAN_MOTION_DDOT\n")
ISS = ("ISS (ZARYA),1998-067A,2026-10-05T01:07:02.318304,15.48738655,"
       ".00068562,51.6316,116.4131,223.9771,136.0673,0,U,25544,999,58878,"
       ".98342731E-4,.4924E-4,0\n")
# Геостационарный спутник, придуманные элементы около 60° в. д.
GEO = ("TEST GEO,2020-001A,2026-10-05T00:00:00.000000,1.00270000,"
       ".0001000,0.0500,80.0000,90.0000,150.0000,0,U,90001,999,100,"
       "0,0,0\n")
# Эпоха ISS в секундах UTC от 1970 года.
ISS_EPOCH = (sgp4.jday(2026, 10, 5, 1, 7, 2.318304) - sgp4.JD_1970) * 86400.0


def swarm(*rows, group="stations"):
    s = satellites.Swarm()
    s.set_group(group, sgp4.parse_csv(HEAD + "".join(rows)))
    while not s.init_some(budget=1):
        pass
    return s


class TestSpline(unittest.TestCase):

    def test_spline_matches_model_between_samples(self):
        s = swarm(ISS)
        worst = 0.0
        for k in range(1, 60, 7):
            moment = ISS_EPOCH + 3600.0 + k
            got, ok = s.positions(moment)
            jd = sgp4.unix_jd(moment)
            r, v, _ = sgp4.propagate(
                s.f, (jd - sgp4.JD_EPOCH0 - s.f["epoch"]) * 1440.0)
            want, _ = satellites.to_ecef(r, v, jd)
            self.assertTrue(ok[0])
            worst = max(worst, float(np.linalg.norm(got[0] - want[0])))
        # Метры на шаге 60 с у низкой орбиты.
        self.assertLess(worst, 10.0)

    def test_ecef_velocity_is_derivative(self):
        s = swarm(ISS)
        jd = sgp4.unix_jd(ISS_EPOCH + 600.0)
        dt = 0.5
        out = []
        for shift in (-dt, 0.0, dt):
            j = jd + shift / 86400.0
            r, v, _ = sgp4.propagate(
                s.f, (j - sgp4.JD_EPOCH0 - s.f["epoch"]) * 1440.0)
            out.append(satellites.to_ecef(r, v, j))
        numeric = (out[2][0][0] - out[0][0][0]) / (2.0 * dt)
        # Скорость SGP4 - не точная производная её положения, у ISS
        # они расходятся на десятые доли метра в секунду. Поправка
        # за вращение Земли - около 500 м/с, её ошибка видна сразу.
        np.testing.assert_allclose(out[1][1][0], numeric, atol=0.5)

    def test_geostationary_stands_still(self):
        s = swarm(GEO, group="geo")
        a, _ = s.positions(ISS_EPOCH)
        b, _ = s.positions(ISS_EPOCH + 6 * 3600.0)
        lat, lon, h = ellipsoid.ecef_to_geodetic(a[0])
        # Спутник висит над одной долготой: за 6 часов сдвиг меньше
        # 100 км при высоте около 35 800 км.
        self.assertLess(float(np.linalg.norm(a[0] - b[0])), 100e3)
        self.assertAlmostEqual(float(h) / 1000.0, 35786.0, delta=150.0)


class TestSwarm(unittest.TestCase):

    def test_same_satellite_once(self):
        s = satellites.Swarm()
        s.set_group("stations", sgp4.parse_csv(HEAD + ISS))
        s.set_group("visual", sgp4.parse_csv(HEAD + ISS + GEO))
        while not s.init_some(budget=1):
            pass
        self.assertEqual(len(s), 2)
        self.assertEqual(s.group_of, ["stations", "visual"])
        s.keep({"visual"})
        while not s.init_some():
            pass
        self.assertEqual(len(s), 2)
        self.assertEqual(s.group_of, ["visual", "visual"])

    def test_info(self):
        s = swarm(ISS)
        info = s.info(0, ISS_EPOCH + 1800.0)
        self.assertEqual(info["name"], "ISS (ZARYA)")
        self.assertEqual(info["number"], 25544)
        self.assertGreater(info["height"], 380.0)
        self.assertLess(info["height"], 450.0)
        self.assertAlmostEqual(info["speed"], 7.66, delta=0.05)

    def test_old_elements_not_shown(self):
        s = swarm(ISS, GEO)
        later = ISS_EPOCH + 60 * 86400.0
        points, ok = s.positions(later)
        self.assertEqual(list(ok), [False, False])
        self.assertEqual(s.info(0, later)["error"], satellites.STALE)
        points, ok = s.positions(ISS_EPOCH + 86400.0)
        self.assertEqual(list(ok), [True, True])

    def test_empty(self):
        s = satellites.Swarm()
        self.assertTrue(s.init_some())
        points, ok = s.positions(ISS_EPOCH)
        self.assertEqual(points.shape, (0, 3))


class TestPath(unittest.TestCase):

    def test_iss_orbit_and_track(self):
        s = swarm(ISS)
        moment = ISS_EPOCH + 3600.0
        lat, lon, h, tlat, tlon = satellites.path(s.f, 0, moment)
        self.assertEqual(len(lat), satellites.ORBIT_POINTS + 1)
        # Виток на один период почти замкнут: прецессия узла и торможение
        # за полтора часа - десятки километров.
        ring = ellipsoid.geodetic_to_ecef(lat, lon, h)
        self.assertLess(float(np.linalg.norm(ring[0] - ring[-1])), 100e3)
        self.assertGreater(float(h.min()), 380e3)
        self.assertLess(float(h.max()), 450e3)
        # След не выходит за наклонение орбиты 51.6°.
        self.assertLess(float(np.abs(tlat).max()), 51.8)
        self.assertGreater(float(np.abs(tlat).max()), 50.0)
        # Середина следа - точка под спутником в сам момент.
        point = s.motion(0, moment)[0]
        here = ellipsoid.ecef_to_geodetic(point)
        mid = satellites.ORBIT_POINTS // 2
        self.assertAlmostEqual(float(tlat[mid]), float(here[0]), places=4)
        self.assertAlmostEqual(float(tlon[mid]), float(here[1]), places=4)
        # Первая точка витка - сам спутник.
        self.assertAlmostEqual(float(lat[0]), float(here[0]), places=4)

    def test_old_elements_no_path(self):
        s = swarm(ISS)
        self.assertIsNone(satellites.path(s.f, 0, ISS_EPOCH + 60 * 86400.0))
        self.assertIsNone(s.motion(0, ISS_EPOCH + 60 * 86400.0))

    def test_heading(self):
        a = ellipsoid.A
        self.assertAlmostEqual(satellites.heading(
            np.array([a, 0.0, 0.0]), np.array([0.0, 1.0, 0.0])), 90.0)
        self.assertAlmostEqual(satellites.heading(
            np.array([a, 0.0, 0.0]), np.array([0.0, 0.0, 1.0])), 0.0)
        self.assertAlmostEqual(satellites.heading(
            np.array([a, 0.0, 0.0]), np.array([0.0, -1.0, 0.0])), 270.0)

    def test_index_of(self):
        s = swarm(ISS, GEO)
        self.assertEqual(s.index_of(90001), 1)
        self.assertIsNone(s.index_of(12345))


class TestHidden(unittest.TestCase):

    def test_far_side_hidden_near_side_seen(self):
        a = ellipsoid.A
        eye = np.array([3.0 * a, 0.0, 0.0])
        points = np.array([[1.2 * a, 0.0, 0.0],   # над точкой под глазом
                           [-1.2 * a, 0.0, 0.0],  # за Землёй
                           [0.0, 1.5 * a, 0.0],   # сбоку, виден
                           [-0.2 * a, 1.5 * a, 0.0]])
        self.assertEqual(list(satellites.hidden(eye, points)),
                         [False, True, False, False])

    def test_eye_inside_sees_nothing_hidden(self):
        hidden = satellites.hidden(np.zeros(3),
                                   np.array([[2.0 * ellipsoid.A, 0, 0]]))
        self.assertFalse(hidden[0])


if __name__ == "__main__":
    unittest.main()
