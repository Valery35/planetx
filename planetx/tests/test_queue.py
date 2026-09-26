# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Очередь загрузки тайлов."""
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

from tile_queue import TileQueue  # noqa: E402


def drain(queue):
    out = []
    while True:
        key = queue.next()
        if key is None:
            return out
        out.append(key)


class TestOrder(unittest.TestCase):

    def test_higher_priority_goes_first(self):
        q = TileQueue(max_active=10)
        for key, priority in (("a", 1.0), ("b", 5.0), ("c", 3.0)):
            q.want(key, priority)
        self.assertEqual(drain(q), ["b", "c", "a"])

    def test_ties_keep_request_order(self):
        q = TileQueue(max_active=10)
        for key in "dcba":
            q.want(key, 1.0)
        self.assertEqual(drain(q), list("dcba"))

    def test_raising_priority_keeps_place_among_equals(self):
        q = TileQueue(max_active=10)
        q.want("a", 1.0)
        q.want("b", 1.0)
        q.want("a", 1.0)
        self.assertEqual(drain(q), ["a", "b"])
        q = TileQueue(max_active=10)
        q.want("a", 1.0)
        q.want("b", 2.0)
        q.want("a", 3.0)
        self.assertEqual(drain(q), ["a", "b"])


class TestLimit(unittest.TestCase):

    def test_no_more_than_max_active(self):
        q = TileQueue(max_active=2)
        for i in range(10):
            q.want(i, float(i))
        self.assertEqual(drain(q), [9, 8])
        self.assertIsNone(q.next())
        q.done(9)
        self.assertEqual(drain(q), [7])
        self.assertEqual(len(q.active), 2)

    def test_active_tile_is_not_asked_twice(self):
        q = TileQueue(max_active=2)
        q.want("a", 1.0)
        self.assertEqual(q.next(), "a")
        self.assertFalse(q.want("a", 9.0))
        self.assertIsNone(q.next())


class TestCancel(unittest.TestCase):

    def test_retain_drops_waiting(self):
        q = TileQueue(max_active=1)
        for key in "abcd":
            q.want(key, 1.0)
        self.assertEqual(q.next(), "a")
        self.assertEqual(q.retain(["a", "c"]), [])
        self.assertEqual(set(q.waiting), {"c"})

    def test_retain_returns_active_to_abort(self):
        q = TileQueue(max_active=2)
        for key in "abc":
            q.want(key, 1.0)
        drain(q)
        self.assertEqual(q.retain(["b"]), ["a"])
        # Активный тайл снимает вызывающий, потом сообщает done.
        q.done("a", ok=True)
        self.assertEqual(q.active, {"b"})

    def test_empty_retain_clears(self):
        q = TileQueue(max_active=2)
        for key in "abc":
            q.want(key, 1.0)
        drain(q)
        self.assertEqual(q.retain([]), ["a", "b"])
        self.assertFalse(q.waiting)


class TestRetry(unittest.TestCase):

    def test_failed_tile_waits(self):
        q = TileQueue(max_active=2, retry_after=30.0)
        q.want("a", 1.0, now=0.0)
        q.next()
        q.done("a", ok=False, now=10.0)
        self.assertFalse(q.want("a", 1.0, now=20.0))
        self.assertTrue(q.want("a", 1.0, now=40.0))

    def test_success_clears_failure(self):
        q = TileQueue(max_active=2, retry_after=30.0)
        q.want("a", 1.0)
        q.next()
        q.done("a", ok=False, now=0.0)
        q.want("a", 1.0, now=31.0)
        q.next()
        q.done("a", ok=True, now=32.0)
        self.assertNotIn("a", q.failed_at)
        self.assertTrue(q.want("a", 1.0, now=33.0))


if __name__ == "__main__":
    unittest.main()
