# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сегментация снимка: объекты по цвету и текстуре, классы объектов."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import rasterclass  # noqa: E402
import segments  # noqa: E402


def scene(noise=4.0):
    """Снимок 120 × 120: тёмный запад, светлый восток, в востоке пруд."""
    random = np.random.default_rng(5)
    bands = np.zeros((3, 120, 120), dtype=np.float32)
    bands[0, :, :60], bands[1, :, :60], bands[2, :, :60] = 40, 90, 50
    bands[0, :, 60:], bands[1, :, 60:], bands[2, :, 60:] = 190, 170, 110
    bands[:, 30:60, 80:110] = 30
    return bands + noise * random.normal(size=bands.shape).astype(np.float32)


def single(mask):
    """Клетки mask связны по сторонам: перебор в ширину."""
    rows, cols = np.nonzero(mask)
    seen = {(rows[0], cols[0])}
    queue = [(rows[0], cols[0])]
    while queue:
        r, c = queue.pop()
        for near in ((r + 1, c), (r - 1, c), (r, c + 1), (r, c - 1)):
            if near not in seen and 0 <= near[0] < mask.shape[0] \
                    and 0 <= near[1] < mask.shape[1] and mask[near]:
                seen.add(near)
                queue.append(near)
    return len(seen) == int(mask.sum())


class TestSegment(unittest.TestCase):
    def test_finds_parts_of_scene(self):
        labels = segments.segment(scene(), scale=25)
        west, east, pond = labels[60:, :50], labels[70:, 70:], \
            labels[35:55, 85:105]
        # Главный объект части покрывает её почти целиком.
        for part in (west, east, pond):
            share = np.bincount(part.ravel()).max() / part.size
            self.assertGreater(share, 0.95)
        self.assertEqual(len({int(np.median(p)) for p in (west, east, pond)}),
                         3)

    def test_objects_are_connected(self):
        labels = segments.segment(scene(), scale=25)
        for number in range(int(labels.max()) + 1):
            self.assertTrue(single(labels == number))

    def test_two_ponds_of_one_color_stay_apart(self):
        bands = np.full((1, 40, 40), 100.0, dtype=np.float32)
        bands[:, 5:12, 5:12] = 10.0
        bands[:, 25:35, 25:35] = 10.0
        labels = segments.segment(bands, scale=5, weight=0.0, least=1)
        self.assertNotEqual(labels[8, 8], labels[30, 30])

    def test_scale_changes_amount(self):
        grid = scene(20.0)
        few = int(segments.segment(grid, scale=40).max())
        many = int(segments.segment(grid, scale=3, least=1).max())
        self.assertGreater(many, few)

    def test_texture_separates_same_color(self):
        # Лес и луг одного среднего цвета: без текстуры - один объект.
        random = np.random.default_rng(1)
        bands = np.full((3, 100, 100), 100.0, dtype=np.float32)
        spots = 60.0 * random.choice((-1.0, 1.0), size=(100, 50))
        bands[:, :, 50:] += spots.astype(np.float32)
        labels = segments.segment(bands, scale=25, weight=0.8)
        self.assertNotEqual(np.median(labels[:, 5:40]),
                            np.median(labels[:, 60:95]))

    def test_least_removes_small_objects(self):
        grid = scene()
        grid[:, 100:102, 10:12] = 250.0
        kept = segments.segment(grid, scale=1, least=1)
        gone = segments.segment(grid, scale=1, least=16)
        self.assertLess(segments.areas(kept).min(), 16)
        self.assertGreaterEqual(segments.areas(gone).min(), 16)

    def test_no_data_and_outside_have_no_object(self):
        grid = scene()
        grid[1, 10:20, 10:20] = np.nan
        inside = np.ones(grid.shape[1:], dtype=bool)
        inside[:5, :] = False
        labels = segments.segment(grid, inside, scale=25)
        self.assertTrue((labels[10:20, 10:20] == -1).all())
        self.assertTrue((labels[:5, :] == -1).all())
        self.assertTrue((labels[30:, 30:] >= 0).all())

    def test_flat_raster_is_one_object(self):
        labels = segments.segment(np.full((2, 30, 30), 7.0, np.float32))
        self.assertEqual(int(labels.max()), 0)
        self.assertTrue((labels == 0).all())

    def test_nothing_usable(self):
        grid = np.full((2, 8, 8), np.nan, np.float32)
        self.assertTrue((segments.segment(grid) == -1).all())

    def test_progress_can_stop(self):
        class Stop(Exception):
            pass

        def stop(_):
            raise Stop()
        with self.assertRaises(Stop):
            segments.segment(scene(), progress=stop)


class TestManyBands(unittest.TestCase):
    def test_embedding_bands_reduce_and_find_parts(self):
        # 64 канала: две части сцены различаются смесью всех каналов.
        random = np.random.default_rng(7)
        mix = random.normal(size=64)
        side = np.ones((80, 80), dtype=np.float32)
        side[:, 40:] = -1.0
        grid = mix[:, None, None].astype(np.float32) * side \
            + 0.3 * random.normal(size=(64, 80, 80)).astype(np.float32)
        good = np.ones((80, 80), dtype=bool)
        data = segments.features(grid, good, weight=0.0)
        self.assertEqual(data.shape[0], segments.PARTS)
        self.assertAlmostEqual(float(data.var(axis=1).sum()), 1.0, delta=0.05)
        labels = segments.segment(grid, scale=15, weight=0.0)
        self.assertNotEqual(int(np.median(labels[:, :30])),
                            int(np.median(labels[:, 50:])))


class TestDissolve(unittest.TestCase):
    def test_neighbors_of_one_class_merge(self):
        labels = np.array([[0, 0, 1, 1, 2],
                           [0, 0, 1, 1, 2],
                           [3, 3, 3, -1, 2]], dtype=np.int32)
        kinds = np.array([0, 0, 1, 0])
        out, joined = segments.dissolve(labels, kinds)
        # 0, 1 и 3 связаны, 2 - другой класс.
        self.assertEqual(int(out.max()) + 1, 2)
        self.assertEqual(out[0, 0], out[0, 2])
        self.assertEqual(out[0, 0], out[2, 0])
        self.assertNotEqual(out[0, 0], out[0, 4])
        self.assertEqual(out[2, 3], -1)
        self.assertEqual(sorted(joined.tolist()), [0, 1])

    def test_far_objects_of_one_class_stay_apart(self):
        labels = np.array([[0, 1, 2]], dtype=np.int32)
        out, joined = segments.dissolve(labels, np.array([0, 1, 0]))
        self.assertEqual(int(out.max()) + 1, 3)
        self.assertEqual(joined.tolist(), [0, 1, 0])

    def test_no_class_does_not_merge(self):
        labels = np.array([[0, 1]], dtype=np.int32)
        out, _ = segments.dissolve(labels, np.array([-1, -1]))
        self.assertEqual(int(out.max()) + 1, 2)

    def test_long_chain_joins(self):
        labels = np.arange(500, dtype=np.int32).reshape(1, -1)[:, ::-1]
        out, joined = segments.dissolve(labels.copy(), np.zeros(500, int))
        self.assertTrue((out == 0).all())
        self.assertEqual(joined.tolist(), [0])


class TestPairs(unittest.TestCase):
    def test_each_region_in_one_pair_on_equal_costs(self):
        a = np.array([0, 1, 2, 3])
        b = np.array([1, 2, 3, 4])
        chosen = segments._pairs(a, b, np.zeros(4), 5)
        used = np.concatenate((a[chosen], b[chosen]))
        self.assertEqual(len(used), len(set(used.tolist())))
        self.assertGreater(len(chosen), 0)

    def test_mutual_best_only(self):
        # Область 1 ближе к 2, поэтому пара 0-1 ждёт.
        a = np.array([0, 1])
        b = np.array([1, 2])
        chosen = segments._pairs(a, b, np.array([5.0, 1.0]), 3)
        self.assertEqual(chosen.tolist(), [1])


class TestTexture(unittest.TestCase):
    def test_box_sum_matches_direct(self):
        random = np.random.default_rng(2)
        value = random.normal(size=(9, 11))
        got = segments._box_sum(value, 2)
        self.assertAlmostEqual(got[4, 5], value[2:7, 3:8].sum())
        self.assertAlmostEqual(got[0, 0], value[:3, :3].sum())
        self.assertAlmostEqual(got[8, 10], value[6:, 8:].sum())

    def test_flat_has_no_texture(self):
        out = segments.texture(np.full((6, 6), 3.0), np.ones((6, 6), bool))
        self.assertLess(out.max(), 1e-6)

    def test_masked_cells_do_not_count(self):
        # Яркий выброс вне участка не делает клетку шероховатой.
        value = np.full((7, 7), 1.0)
        value[3, 3] = 1e6
        good = np.ones((7, 7), bool)
        good[3, 3] = False
        self.assertLess(segments.texture(value, good).max(), 1e-6)


class TestClasses(unittest.TestCase):
    def test_object_table_and_classes(self):
        grid = scene()
        labels = segments.segment(grid, scale=25)
        table = segments.table(grid, labels)
        self.assertEqual(table.shape[:2], (6, 1))
        west = int(labels[60, 20])
        self.assertAlmostEqual(float(table[0, 0, west]), 40.0, delta=2.0)
        self.assertLess(float(table[3, 0, west]), 10.0)
        east, pond = int(labels[90, 90]), int(labels[45, 95])
        samples = table[:, 0, [west, east, pond]]
        kinds, _ = rasterclass.classify(table, samples, [0, 1, 2])
        self.assertEqual(kinds[0, west], 0)
        self.assertEqual(kinds[0, east], 1)
        self.assertEqual(kinds[0, pond], 2)

    def test_pattern_tells_rows_from_grass_of_same_spread(self):
        # Трава - мелкий шум, вырубка - ряды, лес - пятна крон 3 × 3.
        # Цвет и разброс внутри объекта у всех трёх одни, table их
        # не различает. Сторож замечания Василия Швалёва от 2 ноября
        # 2026 года.
        random = np.random.default_rng(3)
        n = 60
        grass = random.normal(size=(n, n))
        rows = np.sin(np.arange(n) * 2 * np.pi / 6)[None, :] \
            * np.ones((n, 1))
        cut = rows / rows.std() * 0.8 + 0.6 * random.normal(size=(n, n))
        crowns = np.kron(random.normal(size=(n // 3, n // 3)),
                         np.ones((3, 3)))
        bright = np.concatenate([part / part.std()
                                 for part in (grass, cut, crowns)], axis=1)
        grid = np.stack([100 + 20 * bright, 90 + 18 * bright,
                         70 + 14 * bright]).astype(np.float32)
        labels = np.repeat(np.arange(3, dtype=np.int32), n)[None, :] \
            .repeat(n, axis=0)
        spread = segments.table(grid, labels)[3:, 0]
        self.assertLess(float(np.ptp(spread, axis=1).max()), 0.5)
        drawing = segments.pattern(grid, labels)[:, 0]
        self.assertEqual(drawing.shape[0], segments.PATTERN)
        # Направленность: ряды - высокая, шум и кроны - около нуля.
        self.assertGreater(drawing[2, 1], 0.4)
        self.assertLess(drawing[2, 0], 0.1)
        self.assertLess(drawing[2, 2], 0.1)
        # Зерно: кроны крупнее травы.
        self.assertLess(drawing[1, 2], drawing[1, 0] - 0.2)

    def test_pattern_ignores_neighbour_objects(self):
        # Резкая граница двух ровных объектов не даёт им перепадов.
        grid = np.zeros((1, 10, 20), np.float32)
        grid[:, :, 10:] = 100.0
        labels = np.zeros((10, 20), np.int32)
        labels[:, 10:] = 1
        self.assertLess(float(np.abs(segments.pattern(grid,
                                                      labels)).max()), 1e-6)

    def test_borders(self):
        labels = np.array([[0, 0, 1], [0, 0, 1], [-1, -1, 1]])
        edge = segments.borders(labels)
        self.assertTrue(edge[0, 1])
        self.assertFalse(edge[0, 0])
        self.assertFalse(edge[2, 0])

    def test_site_scale_keeps_share_of_site(self):
        # Та же сцена на сетке вчетверо грубее: объекты те же.
        grid = scene(2.0)
        fine = segments.segment(
            grid, scale=segments.site_scale(600, grid[0].size), least=4)
        coarse = grid[:, ::4, ::4]
        rough = segments.segment(
            coarse, scale=segments.site_scale(600, coarse[0].size), least=4)
        self.assertEqual(int(fine.max()), int(rough.max()))

    def test_too_big(self):
        self.assertFalse(segments.too_big(800, 800))
        self.assertTrue(segments.too_big(3000, 3000))


if __name__ == "__main__":
    unittest.main()
