# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/tests/test_topo_trace.py.
# Там - GPL-2.0-or-later, владелец тот же.
# Линии стока: куда стечёт вода из заданной ячейки. Ход идёт по тем же
# указателям D8, что и водотоки с водосборами, поэтому трасса и река
# по одному руслу совпадают вершина в вершину.
#
# Обрыв трассы естественный и бывает четырёх видов: сток (ниже некуда),
# край листа, приход в приёмник (водоём или водоток) и слияние с уже
# пройденной трассой. Последнее нужно на площадных источниках: отвал в
# тысячу ячеек иначе даст тысячу копий одного русла.
#
#     python grid_isolines/tests/test_topo_trace.py
import os
import sys

import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))
import topo_flow as tf                    # noqa: E402


def _slope(ny=20, nx=20, step=1.0):
    r, _c = np.mgrid[0:ny, 0:nx]
    return 200.0 - r * step


def test_trace_runs_downhill_to_the_edge():
    z = _slope()
    _idx, ds = tf.d8_directions(z)
    path = tf.trace_downhill(ds, [0 * 20 + 10], z.shape)[0]
    assert len(path) == 20, len(path)
    rows = [i // 20 for i in path]
    assert rows == list(range(20)), "трасса обязана идти строго вниз"
    assert tf.path_reason(path, ds, z.shape) == "край листа"


def test_trace_stops_in_a_pit():
    """Незаполненная впадина обрывает трассу: ниже некуда."""
    z = _slope()
    z[10, 10] = 150.0
    _idx, ds = tf.d8_directions(z)
    path = tf.trace_downhill(ds, [5 * 20 + 10], z.shape)[0]
    assert path[-1] == 10 * 20 + 10
    assert tf.path_reason(path, ds, z.shape) == "сток"


def test_trace_stops_at_a_receiver():
    """Водоток или водоём принимает трассу и дальше её не ведёт."""
    z = _slope()
    _idx, ds = tf.d8_directions(z)
    stop = set(int(12 * 20 + c) for c in range(20))
    path = tf.trace_downhill(ds, [0 * 20 + 10], z.shape, stop=stop)[0]
    assert path[-1] == 12 * 20 + 10
    assert tf.path_reason(path, ds, z.shape, stop=stop) == "приёмник"


def test_merging_traces_walk_each_cell_once():
    """С обрывом при слиянии выходит дерево, а не пачка копий русла.

    Площадной источник даёт столько стартов, сколько в нём ячеек. Ниже
    по склону они сходятся в одно русло, и без обрыва по нему пройдёт
    каждая трасса целиком.
    """
    z = _slope(ny=30, nx=30)
    z += np.abs(np.mgrid[0:30, 0:30][1] - 15) * 0.2      # ложбина по центру
    _idx, ds = tf.d8_directions(z)
    starts = [2 * 30 + c for c in range(10, 21)]
    loose = tf.trace_downhill(ds, starts, z.shape)
    seen = set()
    tree = tf.trace_downhill(ds, starts, z.shape, seen=seen)
    assert sum(len(p) for p in loose) > sum(len(p) for p in tree)
    # трасса доводится ДО места слияния и там обрывается: последняя
    # ячейка общая, иначе дерево распалось бы на несвязанные куски
    inner = [i for p in tree for i in p[:-1]]
    assert len(inner) == len(set(inner)), "ячейка пройдена дважды"
    ends = [p[-1] for p in tree if p]
    assert len(set(inner) & set(ends)) <= len(ends)
    assert all(len(p) >= 1 for p in tree)


def test_metrics_measure_the_path():
    z = _slope(ny=11, nx=11, step=2.0)
    _idx, ds = tf.d8_directions(z)
    path = tf.trace_downhill(ds, [0 * 11 + 5], z.shape)[0]
    m = tf.path_metrics(path, z, z.shape, 10.0)
    assert m["cells"] == 11
    assert abs(m["length"] - 100.0) < 1e-9      # десять шагов по 10 м
    assert abs(m["drop"] - 20.0) < 1e-9
    assert abs(m["slope"] - 0.2) < 1e-9
    assert m["z_start"] > m["z_end"]


def test_metrics_take_a_rectangular_cell():
    z = _slope(ny=5, nx=5)
    _idx, ds = tf.d8_directions(z)
    path = tf.trace_downhill(ds, [0 * 5 + 2], z.shape)[0]
    m = tf.path_metrics(path, z, z.shape, 10.0, cell_y=25.0)
    assert abs(m["length"] - 100.0) < 1e-9, m["length"]


def test_single_cell_path_is_not_an_error():
    z = _slope()
    _idx, ds = tf.d8_directions(z)
    m = tf.path_metrics([19 * 20 + 3], z, z.shape, 5.0)
    assert m["cells"] == 1 and m["length"] == 0.0 and m["slope"] == 0.0


def test_start_outside_the_grid_gives_an_empty_path():
    z = _slope()
    _idx, ds = tf.d8_directions(z)
    assert tf.trace_downhill(ds, [-1, 10 ** 6], z.shape) == [[], []]


def test_loop_in_a_foreign_grid_does_not_hang():
    """Указатели из чужого инструмента могут зациклиться, ход всё равно
    обязан закончиться."""
    ds = np.array([1, 0], dtype=np.int64)          # две ячейки друг на друга
    paths = tf.trace_downhill(ds, [0], (1, 2))
    assert paths[0] == [0, 1]


def load_tests(loader, tests, pattern):
    """Функции test_* модуля - случаями unittest."""
    suite = unittest.TestSuite()
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            suite.addTest(unittest.FunctionTestCase(func))
    return suite
