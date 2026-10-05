# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/sgp4.py.

Ожидаемые положения - из контрольного набора к статье Vallado,
Crawford, Hujsak, Kelso, «Revisiting Spacetrack Report #3», AIAA
2006-6753 (SGP4-VER.TLE и tcppver.out), км в системе TEME. Набор
охватывает околоземные орбиты с торможением и низким перигеем,
полусуточный и суточный резонансы, отрицательное время, поправку
Лиддейна и счёт на 3.5 года от эпохи.
"""
import math
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import sgp4  # noqa: E402

CASES = (
    ('1 00005U 58002B   00179.78495062  .00000023  00000-0  28098-4 0  4753',
     '2 00005  34.2682 348.7242 1859667 331.7664  19.3264 10.82419157413667',
     ((0.0, (7022.46529266, -1400.08296755, 0.03995155)),
      (2160.0, (190.19796988, 7746.96653614, 5110.00675412)),
      (4320.0, (-9060.47373569, 4658.70952502, 813.68673153)))),
    ('1 06251U 62025E   06176.82412014  .00008885  00000-0  12808-3 0  3985',
     '2 06251  58.0579  54.0425 0030035 139.1568 221.1854 15.56387291  6774',
     ((0.0, (3988.31022699, 5498.96657235, 0.90055879)),
      (1440.0, (-2777.14682335, -5663.16031708, -2462.54889123)),
      (2880.0, (1159.27802897, 5056.60175495, 4353.49418579)))),
    ('1 08195U 75081A   06176.33215444  .00000099  00000-0  11873-3 0   813',
     '2 08195  64.1586 279.0717 6877146 264.7651  20.2257  2.00491383225656',
     ((0.0, (2349.8948335, -14785.93811562, 0.02119378)),
      (1440.0, (2890.80638268, -15446.439523, 948.77010176)),
      (2880.0, (3417.20931586, -16038.79510665, 1894.74934058)))),
    ('1 09998U 74033F   05148.79417928 -.00000112  00000-0  00000+0 0  4480',
     '2 09998   9.4958 313.1750 0270971 327.5225  30.8097  1.16186785 45878',
     ((0.0, (25532.98947267, -27244.26327953, -1.11572421)),
      (-1080.0, (37732.454386, 288.18821054, 4643.87587495)),
      (-720.0, (-8535.81598158, 38171.79073851, 3331.00311285)))),
    ('1 14128U 83058A   06176.02844893 -.00000158  00000-0  10000-3 0  9627',
     '2 14128  11.4384  35.2134 0011562  26.4582 333.5652  0.98870114 46093',
     ((0.0, (34747.57932696, 24502.37114079, -1.32832986)),
      (1440.0, (36366.59147396, 22023.5424572, -601.47121821)),
      (2880.0, (37802.25393045, 19433.57330019, -1198.66634226)))),
    ('1 20413U 83020D   05363.79166667  .00000000  00000-0  00000+0 0  7041',
     '2 20413  12.3514 187.4253 7864447 196.3027 356.5478  0.24690082  7978',
     ((0.0, (25123.29290741, -13225.49966286, 3249.40351869)),
      (1844170.0, (-17163.94050833, -48981.47771614, 7620.3708488)),
      (1844340.0, (5091.5554638, -5030.01134361, -1222.14210549)))),
    ('1 23599U 95029B   06171.76535463  .00085586  12891-6  12956-2 0  2905',
     '2 23599   6.9327   0.2849 5782022 274.4436  25.2425  4.47796565123555',
     ((0.0, (9892.63794341, 35.76144969, -1.08228838)),
      (360.0, (11376.23941678, 12858.97121366, 1563.40660172)),
      (720.0, (7140.41945884, 20539.25485336, 2501.21469368)))),
    ('1 28350U 04020A   06167.21788666  .16154492  76267-5  18678-3 0  8894',
     '2 28350  64.9977 345.6130 0024870 260.7578  99.9590 16.47856722116490',
     ((0.0, (6333.08123128, -1580.82852326, 90.6935572)),
      (720.0, (-446.42460916, 2932.28872588, 5759.19389757)),
      (1440.0, (-4527.90871828, -723.29199041, -4527.44608319)))),
    ('1 28872U 05037B   05333.02012661  .25992681  00000-0  24476-3 0  1534',
     '2 28872  96.4736 157.9986 0303955 244.0492 110.6523 16.46015938 10708',
     ((0.0, (-6131.82730456, 2446.52815528, -253.64211033)),
      (25.0, (896.73799533, 447.12357305, 6607.22400507)),
      (50.0, (5548.43325922, -2480.16469245, -1979.24314527)))),
)
# Эталон не может вычислить: фокальный параметр меньше нуля, код 4.
FAILING = (
    '1 33333U 05037B   05333.02012661  .25992681  00000-0  24476-3 0  1534',
    '2 33333  96.4736 157.9986 9950000 244.0492 110.6523  4.00004038 10708')

CSV = (
    "OBJECT_NAME,OBJECT_ID,EPOCH,MEAN_MOTION,ECCENTRICITY,INCLINATION,"
    "RA_OF_ASC_NODE,ARG_OF_PERICENTER,MEAN_ANOMALY,EPHEMERIS_TYPE,"
    "CLASSIFICATION_TYPE,NORAD_CAT_ID,ELEMENT_SET_NO,REV_AT_EPOCH,BSTAR,"
    "MEAN_MOTION_DOT,MEAN_MOTION_DDOT\n"
    "ISS (ZARYA),1998-067A,2026-10-05T01:07:02.318304,15.48738655,"
    ".00068562,51.6316,116.4131,223.9771,136.0673,0,U,25544,999,58878,"
    ".98342731E-4,.4924E-4,0\n")


def orbits(lines):
    orb = sgp4.Orbits(sgp4.parse_tle(lines))
    orb.init_some()
    return orb


class TestVallado(unittest.TestCase):

    def test_positions_match_reference(self):
        for one, two, rows in CASES:
            orb = orbits([one, two])
            for tsince, expected in rows:
                r, v, err = sgp4.propagate(orb.f, np.array([tsince]))
                with self.subTest(sat=one[2:7], t=tsince):
                    self.assertEqual(int(err[0]), 0)
                    np.testing.assert_allclose(r[0], expected, atol=1e-6)

    def test_all_satellites_in_one_call(self):
        # Все спутники сразу дают то же, что по одному.
        elements = sgp4.parse_tle(
            [line for one, two, _ in CASES for line in (one, two)])
        orb = sgp4.Orbits(elements)
        orb.init_some(budget=4)
        self.assertFalse(orb.ready)
        orb.init_some()
        self.assertTrue(orb.ready)
        tsince = np.array([rows[1][0] for _, _, rows in CASES])
        r, v, err = sgp4.propagate(orb.f, tsince)
        expected = np.array([rows[1][1] for _, _, rows in CASES])
        np.testing.assert_allclose(r, expected, atol=1e-6)
        self.assertFalse(err.any())

    def test_resonance_state_does_not_change_result(self):
        # Запомненное состояние интегратора даёт тот же результат, что
        # счёт от эпохи, и вперёд, и после шага назад.
        orb = orbits(list(CASES[5][:2]))
        cache = sgp4.Cache(orb.f)
        for tsince in (1844170.0, 1844340.0, 10000.0, 1844340.0):
            r1, _, _ = sgp4.propagate(orb.f, np.array([tsince]), cache)
            r2, _, _ = sgp4.propagate(orb.f, np.array([tsince]))
            np.testing.assert_array_equal(r1, r2)

    def test_error_code_and_nan(self):
        orb = orbits(list(FAILING))
        r1, _, err1 = sgp4.propagate(orb.f, np.array([20.0]))
        r2, _, err2 = sgp4.propagate(orb.f, np.array([25.0]))
        self.assertEqual((int(err1[0]), int(err2[0])), (0, 4))
        self.assertTrue(np.isfinite(r1[0]).all())
        self.assertTrue(np.isnan(r2[0]).all())


class TestInput(unittest.TestCase):

    def test_csv_and_tle_give_same_elements(self):
        el = sgp4.parse_csv(CSV)
        self.assertEqual(el.name, ["ISS (ZARYA)"])
        self.assertEqual(int(el.number[0]), 25544)
        self.assertAlmostEqual(float(el.inclo[0]), math.radians(51.6316))
        self.assertAlmostEqual(float(el.no[0]),
                               15.48738655 * 2 * math.pi / 1440.0)
        # 5 октября 2026 года 01:07:02.318 от 0 января 1950 года.
        jd = sgp4.jday(2026, 10, 5, 1, 7, 2.318304)
        self.assertAlmostEqual(float(el.epoch[0]), jd - sgp4.JD_EPOCH0)

    def test_bad_rows_skipped(self):
        el = sgp4.parse_csv(CSV + "BROKEN,1998-067A,нет даты,15.4\n")
        self.assertEqual(len(el), 1)
        self.assertEqual(len(sgp4.parse_csv("")), 0)
        self.assertEqual(len(sgp4.parse_csv("A,B\n1,2\n")), 0)

    def test_iss_altitude(self):
        el = sgp4.parse_csv(CSV)
        orb = sgp4.Orbits(el)
        jd = sgp4.JD_EPOCH0 + float(el.epoch[0]) + 0.25
        r, v, err = orb.at(jd)
        height = np.linalg.norm(r[0]) - sgp4.RADIUS
        self.assertGreater(height, 380.0)
        self.assertLess(height, 450.0)
        self.assertAlmostEqual(float(np.linalg.norm(v[0])), 7.66, delta=0.05)


class TestFrame(unittest.TestCase):

    def test_sidereal_time_at_j2000(self):
        # Среднее звёздное время 1 января 2000 года, 12 ч UT1 -
        # 280.46061837°.
        self.assertAlmostEqual(math.degrees(float(sgp4.gstime(2451545.0))),
                               280.46061837, places=6)

    def test_ecef_rotation(self):
        jd = 2451545.0
        g = float(sgp4.gstime(jd))
        # Точка TEME в направлении Гринвича ложится на ось x Земли.
        r = np.array([[math.cos(g) * 7000.0, math.sin(g) * 7000.0, 10.0]])
        out = sgp4.teme_to_ecef(r, jd)
        np.testing.assert_allclose(out[0], (7000.0, 0.0, 10.0), atol=1e-9)

    def test_unix_jd(self):
        self.assertEqual(sgp4.unix_jd(0.0), 2440587.5)
        self.assertEqual(sgp4.unix_jd(86400.0), 2440588.5)


if __name__ == "__main__":
    unittest.main()
