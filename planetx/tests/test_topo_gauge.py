# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
# Перенесено из Isoliner, grid_isolines/tests/test_topo_gauge.py.
# Там - GPL-2.0-or-later, владелец тот же.
# Тесты ядра отчёта по створу. Синтетический рельеф, эталонные цифры
# посчитаны руками:
#     python grid_isolines/tests/test_topo_gauge.py
import math
import os
import sys

import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import topo_flow  # noqa: E402
import topo_gauge as tg  # noqa: E402

CELL = 10.0  # м


def _ramp():
    """Наклонная плоскость: вода течёт строго на восток вдоль строк.

    z падает с ростом столбца, ряды независимы. Аккумуляция в ячейке
    (r, c) равна c + 1, главный водоток от восточного края - вся строка.
    """
    ny, nx = 4, 6
    z = np.tile(np.arange(nx, 0, -1, dtype=np.float64), (ny, 1))  # 6..1
    _, down = topo_flow.d8_directions(z)
    acc = topo_flow.flow_accumulation(down, (ny, nx))
    return z, down, acc, (ny, nx)


def _valley():
    """V-долина с осевым водотоком по среднему столбцу, сток на юг.

    z = |c - 2| * 10 - r: бока круче оси, ось падает к югу. Весь грид
    стекает в низ среднего столбца.
    """
    ny, nx = 5, 5
    r = np.arange(ny, dtype=np.float64)[:, None]
    c = np.arange(nx, dtype=np.float64)[None, :]
    z = np.abs(c - 2) * 10.0 - r
    _, down = topo_flow.d8_directions(z)
    acc = topo_flow.flow_accumulation(down, (ny, nx))
    return z, down, acc, (ny, nx)


# --- притяжка ------------------------------------------------------------

def test_snap_to_max_acc():
    z, down, acc, shape = _ramp()
    # точка на середине строки 1, радиус 2 ячейки: максимум в окне - самый
    # восточный столбец. Ряды одинаковы, максимумы равны, берётся первый по
    # обходу окна - верхняя строка окна (документированный детерминизм)
    r, c = tg.snap_to_max_acc(acc, 1, 3, 2)
    assert (r, c) == (0, 5)
    # радиус 0: без притяжки
    assert tg.snap_to_max_acc(acc, 1, 3, 0) == (1, 3)
    # выход за край зажимается
    assert tg.snap_to_max_acc(acc, -5, 99, 0) == (0, 5)


def test_snap_deterministic_on_ties():
    acc = np.zeros((3, 3))
    acc[0, 1] = 7.0
    acc[2, 1] = 7.0
    # равные максимумы: берётся первый по обходу окна (верхний)
    assert tg.snap_to_max_acc(acc, 1, 1, 1) == (0, 1)


# --- бассейн и зональная статистика --------------------------------------

def test_basin_mask_ramp():
    z, down, acc, shape = _ramp()
    ny, nx = shape
    # створ на восточном краю строки 2: бассейн - ровно эта строка
    seed = 2 * nx + (nx - 1)
    mask = tg.basin_mask(down, shape, seed)
    assert int(mask.sum()) == nx
    assert mask[2].all() and not mask[1].any() and not mask[3].any()


def test_basin_mask_valley_full_grid():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seed = (ny - 1) * nx + 2  # низ оси долины
    mask = tg.basin_mask(down, shape, seed)
    assert int(mask.sum()) == ny * nx  # весь грид стекает через створ
    assert int(acc[ny - 1, 2]) == ny * nx


def test_zonal_stats_nodata_and_empty():
    v = np.array([[1.0, 2.0], [3.0, float("nan")]])
    mask = np.ones((2, 2), dtype=bool)
    mean, vmin, vmax = tg.zonal_stats(v, mask)
    assert (mean, vmin, vmax) == (2.0, 1.0, 3.0)  # nan исключён
    nodata = np.array([[False, True], [False, True]])
    mean, vmin, vmax = tg.zonal_stats(v, mask, nodata)
    assert (mean, vmin, vmax) == (2.0, 1.0, 3.0)
    assert tg.zonal_stats(v, np.zeros((2, 2), dtype=bool)) == (
        None, None, None)


# --- главный водоток ------------------------------------------------------

def test_trace_ramp_row():
    z, down, acc, shape = _ramp()
    ny, nx = shape
    seed = 1 * nx + (nx - 1)
    length, path = tg.trace_main_stream(down, acc, shape, seed, CELL)
    # вся строка: 5 шагов по 10 м, путь от створа к истоку
    assert abs(length - (nx - 1) * CELL) < 1e-9
    assert path[0] == seed and path[-1] == 1 * nx + 0
    assert len(path) == nx


def test_trace_valley_axis():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seed = (ny - 1) * nx + 2
    length, path = tg.trace_main_stream(down, acc, shape, seed, CELL)
    # вверх по оси долины 4 шага, а с верха оси трасса правильно уходит в
    # сильнейший приток (боковые ячейки строки 0) до ячейки без притоков:
    # водоток ведётся до истока, всего 6 шагов по 10 м
    assert abs(length - 6 * CELL) < 1e-9
    assert [p % nx for p in path] == [2, 2, 2, 2, 2, 3, 4]
    assert path[-1] == 4  # исток: угловая ячейка без притоков


def test_trace_stops_at_source():
    z, down, acc, shape = _ramp()
    ny, nx = shape
    # створ в истоке (западный столбец): пути нет, длина ноль
    length, path = tg.trace_main_stream(down, acc, shape, 0, CELL)
    assert length == 0.0 and path == [0]


# --- сборный отчёт --------------------------------------------------------

def test_gauge_report_ramp_hand_numbers():
    z, down, acc, shape = _ramp()
    ny, nx = shape
    seed = 2 * nx + (nx - 1)
    rep = tg.gauge_report(z, down, acc, shape, seed, CELL)
    # площадь: 6 ячеек по 100 м² = 600 м² = 0.0006 км²
    assert abs(rep["area_km2"] - 6 * CELL * CELL / 1e6) < 1e-12
    assert rep["cells"] == nx
    # высоты строки: 6..1
    assert (rep["z_min"], rep["z_max"]) == (1.0, 6.0)
    assert abs(rep["z_mean"] - 3.5) < 1e-12
    assert rep["z_gauge"] == 1.0
    # водоток: 50 м, падение 6 - 1 = 5 м, уклон 100 промилле
    assert abs(rep["stream_km"] - 0.05) < 1e-12
    assert abs(rep["stream_fall_m"] - 5.0) < 1e-12
    assert abs(rep["stream_ppm"] - 100.0) < 1e-9
    # уклон бассейна не подавали - None, а не ноль
    assert rep["slope_mean"] is None


def test_gauge_report_valley_with_slope():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seed = (ny - 1) * nx + 2
    slope = np.full(shape, 2.5)
    rep = tg.gauge_report(z, down, acc, shape, seed, CELL, slope=slope)
    assert rep["cells"] == ny * nx
    assert abs(rep["slope_mean"] - 2.5) < 1e-12
    # трасса до истока (0, 4): z от -4 (створ) до 20, падение 24 м на 60 м
    assert abs(rep["stream_fall_m"] - 24.0) < 1e-12
    assert abs(rep["stream_km"] - 0.06) < 1e-12
    assert abs(rep["stream_ppm"] - 400.0) < 1e-9
    assert rep["z_gauge"] == -4.0


def test_gauge_report_nodata_excluded():
    z, down, acc, shape = _ramp()
    ny, nx = shape
    nodata = np.zeros(shape, dtype=bool)
    nodata[2, 0] = True  # исток строки выключен из статистики
    seed = 2 * nx + (nx - 1)
    rep = tg.gauge_report(z, down, acc, shape, seed, CELL,
                          nodata_mask=nodata)
    assert rep["cells"] == nx - 1
    assert rep["z_max"] == 5.0  # ячейка с z=6 в nodata


def test_report_lines():
    z, down, acc, shape = _ramp()
    seed = 2 * shape[1] + (shape[1] - 1)
    rep = tg.gauge_report(z, down, acc, shape, seed, CELL)
    lines = tg.report_lines(rep)
    assert len(lines) == 2
    assert "0.001" in lines[0] and "1.00...6.00" in lines[0]
    assert "100.0" in lines[1]
    # переводчику отдаются шаблоны, тождественный ничего не меняет
    seen = []
    assert tg.report_lines(rep, lambda t: (seen.append(t) or t)) == lines
    assert any("%s" in t for t in seen)


def test_report_keys_order_stable():
    assert tg.REPORT_KEYS[0] == "area_km2"
    assert tg.REPORT_KEYS[-1] == "cells"
    assert len(set(tg.REPORT_KEYS)) == len(tg.REPORT_KEYS)


# --- линейный водосбор (канава) -------------------------------------------

def _grid_geo():
    """Геопривязка для тестовых гридов: начало (0, 0), ячейка 10 м, ось Y
    вниз, как в GeoTIFF."""
    return 0.0, 0.0, CELL


def test_cells_along_polyline_straight():
    ox, oy, cell = _grid_geo()
    # линия вдоль строки 1 через весь грид 4x6
    verts = [(5.0, -15.0), (55.0, -15.0)]
    got = tg.cells_along_polyline(verts, ox, oy, cell, (4, 6))
    assert got == [1 * 6 + c for c in range(6)]


def test_cells_along_polyline_diagonal_no_gaps():
    ox, oy, cell = _grid_geo()
    verts = [(5.0, -5.0), (45.0, -45.0)]      # по диагонали
    got = tg.cells_along_polyline(verts, ox, oy, cell, (5, 5))
    assert got == [0, 6, 12, 18, 24]          # без пропусков


def test_cells_along_polyline_clips_and_dedups():
    ox, oy, cell = _grid_geo()
    # уходит за левый край и возвращается: наружные точки отброшены
    verts = [(-100.0, -15.0), (25.0, -15.0), (25.0, -15.0)]
    got = tg.cells_along_polyline(verts, ox, oy, cell, (4, 6))
    assert got == [1 * 6 + 0, 1 * 6 + 1, 1 * 6 + 2]
    assert len(got) == len(set(got))          # повторов нет


def test_cells_in_polygon_square():
    """Квадрат 3x3 ячейки: внутренность строчной развёрткой, контур в тех
    же ячейках, ничего лишнего."""
    ox, oy, cell = _grid_geo()
    ny, nx = 6, 6
    # x 22..48, y -48..-22: центры ячеек 25/35/45 внутри по обеим осям
    ring = [(22, -22), (48, -22), (48, -48), (22, -48), (22, -22)]
    got = set(tg.cells_in_polygon([ring], ox, oy, cell, (ny, nx)))
    want = {r * nx + c for r in range(2, 5) for c in range(2, 5)}
    assert got == want


def test_cells_in_polygon_tiny_boundary_only():
    """Полигон меньше ячейки: ни один центр не внутри, ячейку даёт контур."""
    ox, oy, cell = _grid_geo()
    ring = [(21, -21), (23, -21), (23, -23), (21, -23)]
    got = tg.cells_in_polygon([ring], ox, oy, cell, (6, 6))
    assert got == [2 * 6 + 2]


def test_cells_in_polygon_clips_to_grid():
    """Кольцо шире грида: наружные ячейки отбрасываются, дублей нет."""
    ox, oy, cell = _grid_geo()
    ny, nx = 3, 3
    ring = [(-50, 50), (80, 50), (80, -80), (-50, -80)]
    got = tg.cells_in_polygon([ring], ox, oy, cell, (ny, nx))
    assert sorted(got) == list(range(ny * nx))
    assert len(got) == len(set(got))


def test_polygon_seed_catchment_over_depression():
    """Затравка карьера внутренностью: снаружи трассировка по реальному
    рельефу, внутри залитой ямы условные направления не мешают.

    Канал рядов 2..4 падает на запад и огорожен гребнями в рядах 1 и 5,
    в середине канала (столбцы 2..4) вырыта яма глубиной 5. После
    заполнения вода канала восточнее ямы идёт на запад сквозь неё,
    гребни сливаются в канал по прямой, ряды 0 и 6 идут мимо, всё
    западнее ямы лежит ниже по стоку и в водосбор не входит.
    """
    ox, oy, cell = _grid_geo()
    ny, nx = 7, 7
    c = np.arange(nx, dtype=np.float64)[None, :]
    z = np.tile(c * 0.1, (ny, 1))
    z[1, :] += 100.0
    z[5, :] += 100.0
    z[0, :] += 0.05     # крайние ряды чуть выше, чтобы гребень
    z[6, :] += 0.05     # сливался в канал без ничьих по уклону
    z[2:5, 2:5] -= 5.0
    import hydro_fill
    zf, _n, _m = hydro_fill.fill_depressions(z, epsilon=1e-3)
    _, down = topo_flow.d8_directions(zf)
    ring = [(22, -22), (48, -22), (48, -48), (22, -48)]
    seeds = tg.cells_in_polygon([ring], ox, oy, cell, (ny, nx))
    assert set(seeds) == {r * nx + cc for r in range(2, 5)
                          for cc in range(2, 5)}
    m = tg.catchment_mask(down, (ny, nx), seeds)
    want = np.zeros((ny, nx), dtype=bool)
    want[2:5, 2:5] = True     # сама затравка
    want[2:5, 5:] = True      # канал восточнее ямы
    want[1, 2:] = True        # гребни сливаются в канал по прямой на юг
    want[5, 2:] = True        # и на север, восточнее западного края ямы
    assert (m == want).all()


def test_ditch_report_seed_km2():
    z, down, acc, shape = _valley()
    nx = shape[1]
    seeds = [3 * nx + c for c in range(nx)]
    rep = tg.ditch_report(z, down, shape, seeds, CELL)
    assert abs(rep["seed_km2"] - nx * CELL * CELL / 1e6) < 1e-12
    assert "seed_km2" in tg.DITCH_KEYS
    assert len(set(tg.DITCH_KEYS)) == len(tg.DITCH_KEYS)


def test_burn_sloped_bottom_is_monotone_to_outfall():
    """Дно жёлоба монотонно падает к стоку, перевала через борт нет.

    Приём Иванова: постоянная глубина на волнистом рельефе даёт дно,
    которое поднимается по ходу трассы, и вода переваливает. Жёлоб обязан
    это исключить.
    """
    ox, oy, cell = _grid_geo()
    ny, nx = 3, 10
    # волнистый профиль вдоль ряда 1: вниз, потом горб
    z = np.zeros((ny, nx))
    z[1, :] = [10, 9, 8, 9.5, 11, 8, 7, 8.5, 6, 5]
    run = [1 * nx + c for c in range(nx)]
    out = tg.burn_trace_sloped(z, [run], depth=1.0, slope=0.01, cell=cell)
    bottom = out.ravel()[np.asarray(run)]
    # сток к концу (правый край ниже), падение строго монотонное
    assert (np.diff(bottom) <= -0.01 * cell + 1e-12).all()
    # дно нигде не выше исходной врезки
    assert (bottom <= z[1, :] - 1.0 + 1e-12).all()
    # чужие ячейки не тронуты
    assert (out[0, :] == z[0, :]).all() and (out[2, :] == z[2, :]).all()


def test_burn_sloped_direction_follows_low_end():
    """Направление стока выбирается по нижнему концу трассы."""
    ox, oy, cell = _grid_geo()
    nx = 8
    z = np.zeros((1, nx))
    z[0, :] = np.linspace(2.0, 9.0, nx)   # низкий конец слева
    run = list(range(nx))
    out = tg.burn_trace_sloped(z, [run], depth=0.5, slope=0.01, cell=cell)
    bottom = out.ravel()[np.asarray(run)]
    assert (np.diff(bottom) >= 0.01 * cell - 1e-12).all()  # падает к началу


def test_burn_sloped_zero_slope_still_monotone():
    """Нулевой уклон даёт бегущий минимум: рост дна запрещён и без него."""
    ox, oy, cell = _grid_geo()
    z = np.array([[5.0, 3.0, 6.0, 2.0]])
    run = [0, 1, 2, 3]
    out = tg.burn_trace_sloped(z, [run], depth=1.0, slope=0.0, cell=cell)
    bottom = out.ravel()[np.asarray(run)]
    assert (np.diff(bottom) <= 1e-12).all()
    assert bottom[-1] == 1.0


def test_burn_sloped_nodata_and_degenerate():
    ox, oy, cell = _grid_geo()
    z = np.array([[5.0, 4.0, 3.0]])
    mask = np.array([[False, True, False]])
    out = tg.burn_trace_sloped(z, [[0, 1, 2]], 1.0, 0.01, cell,
                               nodata_mask=mask)
    assert out[0, 1] == 4.0            # nodata не тронута
    assert out[0, 0] == 4.0 and out[0, 2] <= 2.0
    # пустые входы - копия без изменений
    assert (tg.burn_trace_sloped(z, [], 1.0, 0.01, cell) == z).all()
    assert (tg.burn_trace_sloped(z, [[0]], 0.0, 0.01, cell) == z).all()


def test_polyline_length():
    assert abs(tg.polyline_length([(0, 0), (30, 40)]) - 50.0) < 1e-9
    assert tg.polyline_length([(0, 0)]) == 0.0


def test_catchment_of_line_across_valley():
    """Канава поперёк долины перехватывает всё, что выше неё по стоку."""
    z, down, acc, shape = _valley()
    ny, nx = shape
    seeds = [3 * nx + c for c in range(nx)]   # трасса вдоль строки 3
    mask = tg.catchment_mask(down, shape, seeds)
    # строки 0..3 стекают в трассу, нижняя строка 4 уже ниже неё
    assert mask[:4].all()
    assert not mask[4].any()
    assert int(mask.sum()) == 4 * nx


def test_catchment_of_single_cell_matches_gauge():
    """Линейный водосбор из одной ячейки совпадает с точечным створом."""
    z, down, acc, shape = _ramp()
    ny, nx = shape
    seed = 2 * nx + (nx - 1)
    m_line = tg.catchment_mask(down, shape, [seed])
    m_point = tg.basin_mask(down, shape, seed)
    assert (m_line == m_point).all()


def test_catchment_empty_seeds():
    z, down, acc, shape = _ramp()
    assert tg.catchment_mask(down, shape, []).sum() == 0


def test_burn_trace_lowers_only_trace():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seeds = [3 * nx + c for c in range(nx)]
    zb = tg.burn_trace(z, seeds, 5.0)
    assert (zb[3] == z[3] - 5.0).all()
    assert (zb[0] == z[0]).all()
    assert z[3][0] != zb[3][0]                # исходный массив не тронут


def test_burn_trace_respects_nodata_and_zero_depth():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seeds = [3 * nx + c for c in range(nx)]
    nod = np.zeros(shape, dtype=bool)
    nod[3, 0] = True
    zb = tg.burn_trace(z, seeds, 5.0, nodata_mask=nod)
    assert zb[3, 0] == z[3, 0]                # nodata не трогаем
    assert zb[3, 1] == z[3, 1] - 5.0
    assert (tg.burn_trace(z, seeds, 0.0) == z).all()


def test_ditch_report_hand_numbers():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seeds = [3 * nx + c for c in range(nx)]
    slope = np.full(shape, 1.5)
    rep = tg.ditch_report(z, down, shape, seeds, CELL,
                          trace_len=(nx - 1) * CELL, slope=slope)
    assert rep["cells"] == 4 * nx
    assert abs(rep["area_km2"] - 4 * nx * CELL * CELL / 1e6) < 1e-12
    assert rep["trace_cells"] == nx
    assert abs(rep["trace_km"] - 0.04) < 1e-12
    assert abs(rep["slope_mean"] - 1.5) < 1e-12
    # высоты только по водосбору: строки 0..3 долины
    assert rep["z_max"] == 20.0 and rep["z_min"] == -3.0


def test_ditch_report_nodata_excluded():
    z, down, acc, shape = _valley()
    ny, nx = shape
    seeds = [3 * nx + c for c in range(nx)]
    nod = np.zeros(shape, dtype=bool)
    nod[0, :] = True
    rep = tg.ditch_report(z, down, shape, seeds, CELL, nodata_mask=nod)
    assert rep["cells"] == 3 * nx


def test_ditch_report_lines():
    z, down, acc, shape = _valley()
    nx = shape[1]
    seeds = [3 * nx + c for c in range(nx)]
    rep = tg.ditch_report(z, down, shape, seeds, CELL, trace_len=40.0)
    lines = tg.ditch_report_lines(rep)
    assert len(lines) == 2
    assert "0.002" in lines[0]
    assert "0.040" in lines[1] and "ячеек трассы 5" in lines[1]
    seen = []
    assert tg.ditch_report_lines(rep, lambda t: (seen.append(t) or t)) == lines
    assert any("%s" in t for t in seen)


def load_tests(loader, tests, pattern):
    """Функции test_* модуля - случаями unittest."""
    suite = unittest.TestSuite()
    for name, func in sorted(globals().items()):
        if name.startswith("test_") and callable(func):
            suite.addTest(unittest.FunctionTestCase(func))
    return suite
