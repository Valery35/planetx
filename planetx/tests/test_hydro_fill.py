# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/tests/test_hydro_fill.py.
# Там - GPL-2.0-or-later, владелец тот же.
"""Тесты гидрокоррекции. Без сети и без QGIS."""

import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

from hydro_fill import fill_depressions  # noqa: E402


def has_no_interior_pit(z, mask=None):
    """Проверка: у каждой внутренней ячейки есть сосед не выше её минус eps.

    Точнее: нет ячейки, которая строго ниже всех восьми соседей.
    """
    ny, nx = z.shape
    for i in range(1, ny - 1):
        for j in range(1, nx - 1):
            if mask is not None and mask[i, j]:
                continue
            neigh = [z[i + di, j + dj]
                     for di in (-1, 0, 1) for dj in (-1, 0, 1)
                     if not (di == 0 and dj == 0)
                     and not (mask is not None and mask[i + di, j + dj])]
            if neigh and z[i, j] < min(neigh) - 1e-12:
                return False
    return True


class _Feedback(object):
    """Заглушка обратной связи Processing: копит строки."""

    def __init__(self):
        self.messages = []

    def pushInfo(self, text):
        self.messages.append(text)


class TestFill(unittest.TestCase):

    def test_single_pit_filled_eps_zero(self):
        # Epsilon 0: поднимаются только настоящие ямы, ровно до слива.
        z = np.full((7, 7), 10.0)
        z[3, 3] = 5.0
        filled, n_raised, max_raise = fill_depressions(z, epsilon=0.0)
        self.assertEqual(n_raised, 1)
        self.assertEqual(filled[3, 3], 10.0)
        self.assertAlmostEqual(max_raise, 5.0)

    def test_single_pit_with_epsilon_raises_flats_too(self):
        # Epsilon > 0 дополнительно строит уклон на плоском плато,
        # это штатное поведение для гидрокоррекции.
        z = np.full((7, 7), 10.0)
        z[3, 3] = 5.0
        eps = 0.01
        filled, n_raised, _ = fill_depressions(z, epsilon=eps)
        self.assertEqual(n_raised, 25)  # все внутренние ячейки
        self.assertGreaterEqual(filled[3, 3], 10.0)
        self.assertTrue(has_no_interior_pit(filled))
        # Подъём плато ограничен eps на шаг до стока.
        plateau_raise = filled[1:-1, 1:-1] - z[1:-1, 1:-1]
        plateau_raise[2, 2] = 0.0  # сама яма не в счёт
        self.assertLessEqual(float(plateau_raise.max()), 3 * eps + 1e-12)

    def test_epsilon_gradient_in_filled_lake(self):
        # Котловина 3x3 в плато: после заполнения от каждой ячейки
        # должен существовать невозрастающий путь к краю с шагом >= eps.
        z = np.full((9, 9), 20.0)
        z[3:6, 3:6] = 2.0
        eps = 0.05
        filled, n_raised, _ = fill_depressions(z, epsilon=eps)
        self.assertGreaterEqual(n_raised, 9)
        self.assertTrue(has_no_interior_pit(filled))
        # Центр котловины выше её края минимум на eps.
        self.assertGreaterEqual(filled[4, 4], filled[3, 3] + eps - 1e-12)

    def test_flat_gets_drainage(self):
        # Идеальная плоскость: внутренние ячейки поднимаются на eps-уклон,
        # чтобы поток не останавливался.
        z = np.full((6, 6), 100.0)
        filled, n_raised, _ = fill_depressions(z, epsilon=0.001)
        self.assertGreater(n_raised, 0)
        self.assertTrue(has_no_interior_pit(filled))
        # Граница не тронута.
        self.assertTrue(np.all(filled[0, :] == 100.0))
        self.assertTrue(np.all(filled[:, -1] == 100.0))

    def test_slope_untouched(self):
        # Монотонный склон без ям меняться не должен.
        z = np.add.outer(np.arange(8) * 2.0, np.arange(8) * 1.0) + 50.0
        filled, n_raised, max_raise = fill_depressions(z, epsilon=0.001)
        self.assertEqual(n_raised, 0)
        self.assertEqual(max_raise, 0.0)
        self.assertTrue(np.allclose(filled, z))

    def test_nodata_acts_as_outlet(self):
        # Яма примыкает к nodata-дыре: вода уходит в дыру,
        # заполнения почти нет.
        z = np.full((9, 9), 30.0)
        z[4, 4] = 1.0
        mask = np.zeros_like(z, dtype=bool)
        mask[4, 5] = True  # дыра рядом с ямой
        filled, n_raised, _ = fill_depressions(z, nodata_mask=mask,
                                               epsilon=0.0)
        # Ячейка ямы соседствует с nodata, значит она сток и не поднимается.
        self.assertEqual(filled[4, 4], 1.0)
        self.assertEqual(n_raised, 0)
        # Значение под маской не изменилось.
        self.assertEqual(filled[4, 5], 30.0)

    def test_nan_treated_as_nodata(self):
        z = np.full((7, 7), 10.0)
        z[2, 2] = np.nan
        z[4, 4] = 3.0
        filled, n_raised, _ = fill_depressions(z, epsilon=0.01)
        self.assertTrue(np.isnan(filled[2, 2]))
        self.assertGreaterEqual(filled[4, 4], 10.0)

    def test_nested_pits(self):
        # Яма в яме: обе выталкиваются до уровня стока.
        z = np.full((11, 11), 50.0)
        z[3:8, 3:8] = 20.0
        z[5, 5] = 5.0
        filled, _, _ = fill_depressions(z, epsilon=0.01)
        self.assertTrue(has_no_interior_pit(filled))
        self.assertGreaterEqual(filled[5, 5], 50.0)

    def test_valley_to_edge_not_filled(self):
        # Долина с выходом на край: настоящего понижения нет.
        z = np.full((7, 9), 40.0)
        z[3, :] = np.linspace(10.0, 2.0, 9)  # падает к правому краю
        filled, n_raised, _ = fill_depressions(z, epsilon=0.0)
        self.assertEqual(n_raised, 0)
        self.assertTrue(np.allclose(filled[3, :], z[3, :]))

    def test_determinism(self):
        rng = np.random.default_rng(7)
        z = rng.uniform(0.0, 100.0, size=(30, 40))
        f1, n1, m1 = fill_depressions(z, epsilon=0.005)
        f2, n2, m2 = fill_depressions(z, epsilon=0.005)
        self.assertTrue(np.array_equal(f1, f2))
        self.assertEqual((n1, m1), (n2, m2))

    def test_random_terrain_no_pits_left(self):
        rng = np.random.default_rng(123)
        z = rng.uniform(0.0, 100.0, size=(40, 40))
        filled, _, _ = fill_depressions(z, epsilon=0.01)
        self.assertTrue(has_no_interior_pit(filled))
        # Заполнение никогда не опускает рельеф.
        self.assertTrue(np.all(filled >= z - 1e-12))

    def test_convergence_is_reported_on_ordinary_relief(self):
        # Сходимость должна распознаваться, а не упираться в предел проходов.
        # Флаг грязных линий у крайней линии каждого направления снимается,
        # иначе цикл всегда доходит до max_passes и печатает предупреждение.
        rng = np.random.default_rng(42)
        z = rng.uniform(0.0, 100.0, size=(60, 60))
        fb = _Feedback()
        fill_depressions(z, epsilon=0.001, feedback=fb)
        joined = " ".join(fb.messages)
        self.assertIn("сошлось", joined)
        self.assertNotIn("предел", joined)

    def test_result_independent_of_pass_limit(self):
        # Раз заполнение сходится, потолок проходов на результат не влияет.
        rng = np.random.default_rng(11)
        z = rng.uniform(0.0, 100.0, size=(50, 50))
        f_low, n_low, m_low = fill_depressions(z, epsilon=0.001,
                                               max_passes=100)
        f_high, n_high, m_high = fill_depressions(z, epsilon=0.001,
                                                  max_passes=1000)
        self.assertTrue(np.array_equal(f_low, f_high))
        self.assertEqual((n_low, m_low), (n_high, m_high))

    def test_bad_input(self):
        with self.assertRaises(ValueError):
            fill_depressions(np.zeros((1, 5)))
        with self.assertRaises(ValueError):
            fill_depressions(np.zeros((5, 5)), epsilon=-1.0)


if __name__ == "__main__":
    unittest.main()
