# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Похожие области: образец, похожесть объектов, порог."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import segments  # noqa: E402
import similar  # noqa: E402


def field():
    """Сетка 90 × 90: фон и три пруда, рядом с первым луг цвета пруда
    с крупной рябью."""
    random = np.random.default_rng(3)
    grid = np.full((3, 90, 90), 120.0, dtype=np.float32)
    grid[:, 10:30, 10:30] = 40.0
    grid[:, 10:30, 60:80] = 40.0
    grid[:, 60:80, 10:30] = 40.0
    grid[:, 60:80, 60:80] = 40.0 + 40.0 * random.choice((-1.0, 1.0),
                                                        size=(20, 20))
    return grid + 2.0 * random.normal(size=grid.shape).astype(np.float32)


def found(grid, mask, weight=0.3, limit=0.7):
    parts = segments.segment(grid, scale=10, weight=weight)
    table = segments.table(grid, parts)
    score = similar.scores(table, segments.areas(parts),
                           similar.sample_rows(table, parts, mask), weight)
    return parts, score, similar.pick(parts, score, limit)


class TestScores(unittest.TestCase):
    def test_finds_other_ponds_not_background(self):
        grid = field()
        mask = np.zeros(grid.shape[1:], bool)
        mask[14:26, 14:26] = True
        _, _, (labels, _) = found(grid, mask)
        self.assertGreaterEqual(labels[20, 20], 0)
        self.assertGreaterEqual(labels[20, 70], 0)
        self.assertGreaterEqual(labels[70, 20], 0)
        self.assertEqual(labels[45, 45], -1)

    def test_texture_tells_rippled_field_from_pond(self):
        grid = field()
        mask = np.zeros(grid.shape[1:], bool)
        mask[14:26, 14:26] = True
        with_it = found(grid, mask, weight=0.5)[2][0]
        self.assertEqual(with_it[70, 70], -1)

    def test_outline_with_some_foreign_cells_still_works(self):
        # Контур чуть шире пруда: образец смешан, поиск остаётся.
        grid = field()
        mask = np.zeros(grid.shape[1:], bool)
        mask[9:31, 9:31] = True
        labels = found(grid, mask, limit=0.5)[2][0]
        self.assertGreaterEqual(labels[20, 70], 0)
        self.assertEqual(labels[45, 45], -1)

    def test_nearest_of_two_samples(self):
        grid = field()
        parts = segments.segment(grid, scale=10, weight=0.3)
        table = segments.table(grid, parts)
        sizes = segments.areas(parts)
        pond = np.zeros(grid.shape[1:], bool)
        pond[14:26, 14:26] = True
        rest = np.zeros(grid.shape[1:], bool)
        rest[40:50, 40:50] = True
        first = similar.sample_rows(table, parts, pond)
        one = similar.scores(table, sizes, first)
        two = similar.scores(table, sizes, np.concatenate(
            (first, similar.sample_rows(table, parts, rest))))
        self.assertTrue((two >= one - 1e-9).all())
        self.assertGreater(two[parts[45, 45]], one[parts[45, 45]])

    def test_same_object_scores_full(self):
        grid = np.zeros((1, 10, 10), dtype=np.float32)
        grid[:, :, 5:] = 10.0
        grid[:, 0, 0] = 1.0
        parts = np.zeros((10, 10), dtype=np.int32)
        parts[:, 5:] = 1
        table = segments.table(grid, parts)
        score = similar.scores(table, segments.areas(parts),
                               table[:, 0, :1].T)
        self.assertAlmostEqual(float(score[0]), 1.0)
        self.assertLess(float(score[1]), 0.5)

    def test_flat_site_has_no_scores(self):
        grid = np.full((2, 6, 6), 5.0, dtype=np.float32)
        parts = np.zeros((6, 6), dtype=np.int32)
        parts[:, 3:] = 1
        table = segments.table(grid, parts)
        self.assertIsNone(similar.scores(table, segments.areas(parts),
                                         table[:, 0, :1].T))

    def test_drawing_tells_rows_from_grass(self):
        # Вырубка рядами и трава одного цвета и разброса: по одному
        # table они одинаково похожи на образец вырубки, с рисунком
        # (segments.pattern) трава отпадает.
        random = np.random.default_rng(4)
        n = 40
        rows = np.sin(np.arange(n) * 2 * np.pi / 6)[None, :] \
            * np.ones((n, 1))
        parts = []
        for k in range(4):
            if k % 2:
                part = random.normal(size=(n, n))
            else:
                part = rows / rows.std() * 0.8 \
                    + 0.6 * random.normal(size=(n, n))
            parts.append(part / part.std())
        # Пятый объект - тёмный лес: участок не из одного цвета.
        parts.append(random.normal(size=(n, n)) - 4.0)
        bright = np.concatenate(parts, axis=1)
        grid = np.stack([100 + 20 * bright, 90 + 18 * bright]) \
            .astype(np.float32)
        labels = np.repeat(np.arange(5, dtype=np.int32), n)[None, :] \
            .repeat(n, axis=0)
        sizes = segments.areas(labels)
        plain = segments.table(grid, labels)
        full = np.concatenate((plain, segments.pattern(grid, labels)))
        before = similar.scores(plain, sizes, plain[:, 0, :1].T, 0.5)
        after = similar.scores(full, sizes, full[:, 0, :1].T, 0.5,
                               grid.shape[0])
        self.assertGreater(float(before[1]), 0.7)
        self.assertGreater(float(after[2]), 0.7)
        self.assertLess(float(after[1]), 0.3)
        self.assertLess(float(after[3]), 0.3)

    def test_area_weight_keeps_small_objects_from_scale(self):
        # Тысяча мелких объектов не сжимает различие двух больших частей.
        table = np.zeros((2, 1, 1002), dtype=np.float32)
        table[0, 0, 1] = 100.0
        table[0, 0, 2:] = 0.0
        sizes = np.ones(1002)
        sizes[:2] = 10000.0
        score = similar.scores(table, sizes, table[:, 0, :1].T, 0.0)
        self.assertLess(float(score[1]), 0.1)


class TestSample(unittest.TestCase):
    table = np.arange(12, dtype=np.float32).reshape(4, 1, 3)

    def test_objects_filling_outline(self):
        parts = np.array([[0, 0, 0, 0, 0, 0, 0, 1, 1, 2]], dtype=np.int32)
        mask = np.ones(parts.shape, bool)
        rows = similar.sample_rows(self.table, parts, mask)
        self.assertEqual(rows.shape, (1, 4))
        self.assertEqual(rows[0, 1], self.table[1, 0, 0])

    def test_outline_over_two_objects_gives_two(self):
        parts = np.array([[0, 0, 1, 1]], dtype=np.int32)
        rows = similar.sample_rows(self.table, parts,
                                   np.ones(parts.shape, bool))
        self.assertEqual(len(rows), 2)

    def test_scattered_outline_takes_largest(self):
        parts = np.arange(12, dtype=np.int32).reshape(1, -1) % 6
        parts[0, 0] = 1
        table = np.zeros((2, 1, 6), dtype=np.float32)
        table[0, 0, 1] = 5.0
        rows = similar.sample_rows(table, parts, np.ones(parts.shape, bool))
        self.assertEqual(rows[:, 0].tolist(), [5.0])

    def test_outline_without_objects(self):
        parts = np.full((2, 2), -1, dtype=np.int32)
        rows = similar.sample_rows(self.table, parts,
                                   np.ones(parts.shape, bool))
        self.assertEqual(len(rows), 0)

class TestPick(unittest.TestCase):
    parts = np.array([[0, 0, 1, 2], [0, 0, 1, 2]], dtype=np.int32)

    def test_limit_moves_without_new_scores(self):
        score = np.array([0.9, 0.5, 0.2])
        wide = similar.pick(self.parts, score, 0.4)[0]
        tight = similar.pick(self.parts, score, 0.8)[0]
        self.assertEqual((wide >= 0).sum(), 6)
        self.assertEqual((tight >= 0).sum(), 4)

    def test_join_merges_neighbours_area_weighted(self):
        score = np.array([0.9, 0.6, 0.2])
        out, mean = similar.pick(self.parts, score, 0.5)
        self.assertEqual(int(out.max()), 0)
        self.assertAlmostEqual(float(mean[0]), (4 * 0.9 + 2 * 0.6) / 6)
        out, mean = similar.pick(self.parts, score, 0.5, join=False)
        self.assertEqual(int(out.max()), 1)

    def test_nothing_found(self):
        out, mean = similar.pick(self.parts, np.zeros(3), 0.5)
        self.assertEqual(int(out.max()), -1)
        self.assertEqual(len(mean), 0)

    def test_no_object_cells_stay_empty(self):
        parts = np.array([[0, -1, 1]], dtype=np.int32)
        out, _ = similar.pick(parts, np.array([1.0, 1.0]), 0.5, join=False)
        self.assertEqual(out[0, 1], -1)


if __name__ == "__main__":
    unittest.main()
