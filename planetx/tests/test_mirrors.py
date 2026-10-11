# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выбор зеркала службы по состоянию."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import mirrors  # noqa: E402

A, B, C = "https://a/api", "https://b/api", "https://c/api"


class TestMirrors(unittest.TestCase):

    def test_first_server_by_default(self):
        pool = mirrors.Mirrors([A, B, C])
        self.assertEqual(pool.pick(0.0), (A, 0.0))

    def test_quick_failure_takes_server_out_for_long(self):
        pool = mirrors.Mirrors([A, B, C])
        pause = pool.failed(A, 0.3, 0.0)
        self.assertEqual(pause, mirrors.BROKEN)
        self.assertEqual(pool.pick(1.0)[0], B)
        self.assertEqual(pool.failed(A, 0.3, 1.0), 2.0 * mirrors.BROKEN)

    def test_slow_failure_is_short_pause(self):
        pool = mirrors.Mirrors([A, B])
        self.assertEqual(pool.failed(A, 9.0, 0.0), mirrors.BUSY)
        self.assertEqual(pool.pick(1.0)[0], B)
        # Пауза вышла - главный сервер снова первый.
        self.assertEqual(pool.pick(mirrors.BUSY + 1.0)[0], A)

    def test_faster_mirror_wins(self):
        pool = mirrors.Mirrors([A, B])
        pool.ok(A, 12.0)
        pool.ok(B, 3.0)
        self.assertEqual(pool.pick(0.0)[0], B)

    def test_all_down_waits_for_earliest(self):
        pool = mirrors.Mirrors([A, B])
        pool.failed(A, 0.2, 0.0)
        pool.failed(B, 10.0, 0.0)
        url, wait = pool.pick(5.0)
        self.assertEqual(url, B)
        self.assertAlmostEqual(wait, mirrors.BUSY - 5.0)

    def test_success_clears_failures(self):
        pool = mirrors.Mirrors([A, B])
        pool.failed(A, 10.0, 0.0)
        pool.ok(A, 4.0)
        self.assertEqual(pool.failed(A, 10.0, 100.0), mirrors.BUSY)

    def test_gap_between_requests_to_one_server(self):
        pool = mirrors.Mirrors([A], gap=2.0)
        pool.sent(A, 10.0)
        self.assertEqual(pool.pick(10.5), (A, 1.5))

    def test_describe_hides_paths(self):
        pool = mirrors.Mirrors(["https://host.example/api/interpreter"])
        self.assertNotIn("/api", pool.describe(0.0))


if __name__ == "__main__":
    unittest.main()
