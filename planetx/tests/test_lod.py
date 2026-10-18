# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выбор тайлов по экранной ошибке."""
import math
import os
import sys
import time
import unittest
import zlib

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import camera as cm  # noqa: E402
import ellipsoid as el  # noqa: E402
import lod  # noqa: E402
import tiling as tl  # noqa: E402

PERM = (58.0105, 56.2294)
SIZE = dict(width=1920, height=1080)


def everything(key):
    return True


def half_ready(key):
    """Готова примерно половина тайлов, уровни 0-2 готовы всегда."""
    if key[0] <= 2:
        return True
    return zlib.crc32(repr(key).encode()) % 2 == 0


def view(lat, lon, distance, heading=0.0, tilt=0.0):
    return cm.Camera.look_at(lat, lon, distance, heading=heading,
                             tilt=tilt, **SIZE)


def centre_tile(cam, selection):
    origin, d = cam.ray(cam.width / 2, cam.height / 2)
    lat, lon, _ = el.ecef_to_geodetic(origin + d * el.ray_intersect(origin,
                                                                    d))
    found = [k for k in selection.draw
             if tl.lonlat_to_tile(float(lat), float(lon), k[0]) == k[1:]]
    return found


def coverage(cam, selection, samples=400, seed=11):
    """Сколько тайлов списка покрывают точку под случайным пикселем.

    Возвращает список количеств по пикселям, где луч встретил Землю
    в пределах сетки Mercator.
    """
    rng = np.random.default_rng(seed)
    holes = selection.holes or [None] * len(selection.draw)
    entries = list(zip(selection.draw, holes))
    counts = []
    for px, py in rng.uniform(0, 1, (samples, 2)) * [cam.width, cam.height]:
        origin, d = cam.ray(px, py)
        t = el.ray_intersect(origin, d)
        if t is None:
            continue
        lat, lon, _ = el.ecef_to_geodetic(origin + d * t)
        lat, lon = float(lat), float(lon)
        if abs(lat) >= tl.MAX_LAT:
            continue
        # Заплатка покрывает точку, только если та лежит в её дыре.
        counts.append(sum(
            1 for key, hole in entries
            if tl.lonlat_to_tile(lat, lon, key[0]) == key[1:]
            and (hole is None
                 or tl.lonlat_to_tile(lat, lon, hole[0]) == hole[1:])))
    return counts


CAMERAS = (
    ("космос над Пермью", PERM, 2.0e7, 0.0, 0.0),
    ("500 м над Пермью", PERM, 500.0, 0.0, 0.0),
    ("2 км над Пермью, наклон 70°", PERM, 2000.0, 30.0, 70.0),
    ("50 км, наклон 85°", PERM, 50000.0, 200.0, 85.0),
    ("линия смены дат", (10.0, 179.9), 3000.0, 0.0, 40.0),
    ("у края Mercator", (84.0, 20.0), 20000.0, 0.0, 30.0),
    ("экватор с высоты 1000 км", (0.0, 0.0), 1.0e6, 0.0, 0.0),
)


class TestLevels(unittest.TestCase):

    def test_space_view_is_coarse(self):
        sel = lod.select(view(*PERM, 2.0e7), everything)
        self.assertLessEqual(max(k[0] for k in sel.draw), 3)

    def test_street_view_reaches_level_17_or_18(self):
        cam = view(*PERM, 500.0)
        found = centre_tile(cam, lod.select(cam, everything))
        self.assertEqual(len(found), 1)
        self.assertIn(found[0][0], (17, 18))

    def test_no_more_than_400_tiles(self):
        for lat, lon in (PERM, (0.0, 0.0), (80.0, -40.0), (-33.9, 151.2)):
            for distance in (50.0, 300.0, 3e3, 3e4, 3e5, 3e6, 2e7, 4e7):
                sel = lod.select(view(lat, lon, distance), everything)
                self.assertLessEqual(len(sel.draw), 400,
                                     (lat, lon, distance))

    def test_max_level_is_respected(self):
        sel = lod.select(view(*PERM, 50.0), everything, max_level=15)
        self.assertLessEqual(max(k[0] for k in sel.draw), 15)


class TestCoverage(unittest.TestCase):
    """Точка под пикселем лежит ровно в одном тайле списка."""

    def check(self, ready):
        for name, (lat, lon), distance, heading, tilt in CAMERAS:
            cam = view(lat, lon, distance, heading, tilt)
            counts = coverage(cam, lod.select(cam, ready))
            self.assertGreater(len(counts), 50, name)
            self.assertEqual(sorted(set(counts)), [1], name)

    def test_all_ready(self):
        self.check(everything)

    def test_half_ready(self):
        self.check(half_ready)

    def test_only_start_levels_ready(self):
        self.check(lambda key: key[0] <= 2)


class TestReplacement(unittest.TestCase):

    def test_parent_stays_until_all_children_ready(self):
        # Не готов ни тайл z11 под камерой, ни его потомки. Закрыть
        # его место нечем, поэтому родитель z10 рисуется заплаткой на
        # месте z11, а готовые братья z11 - своими потомками.
        cam = view(*PERM, 500.0)
        missing = (11,) + tl.lonlat_to_tile(*PERM, 11)
        parent = (10, missing[1] // 2, missing[2] // 2)

        def ready(key):
            z, x, y = key
            if z < 11:
                return True
            return (x >> (z - 11), y >> (z - 11)) != missing[1:]

        sel = lod.select(cam, ready)
        pairs = list(zip(sel.draw, sel.holes))
        self.assertIn((parent, missing), pairs)
        self.assertNotIn((parent, None), pairs)
        for (z, x, y), hole in pairs:
            if z > 11:
                self.assertNotEqual((x >> (z - 11), y >> (z - 11)),
                                    missing[1:], "потомок в дыре")
        self.assertIn(missing, sel.want)

    def test_far_missing_tile_keeps_near_detail(self):
        # Камера низко с наклоном, как при облёте. Не готов дальний
        # тайл у края кадра. Прежде его предок рисовался целиком вместо
        # всех потомков, и местность под камерой становилась размытой.
        cam = view(*PERM, 450.0, 130.0, 72.0)
        full = lod.select(cam, everything)
        near = centre_tile(cam, full)[0]
        # Брат предка тайла под камерой на самом глубоком уровне, где
        # он виден: их общий родитель прежде рисовался целиком.
        far = None
        for level in range(near[0] - 1, 3, -1):
            shift = near[0] - level
            mine = (near[1] >> shift, near[2] >> shift)
            far = next((k for k in sorted(full.keep)
                        if k[0] == level and k[1:] != mine
                        and (k[1] >> 1, k[2] >> 1) == (mine[0] >> 1,
                                                       mine[1] >> 1)),
                       None)
            if far is not None:
                break
        self.assertIsNotNone(far)

        def ready(key):
            z, x, y = key
            if z < far[0]:
                return True
            up = z - far[0]
            return (x >> up, y >> up) != far[1:]
        sel = lod.select(cam, ready)
        self.assertIn((near, None), list(zip(sel.draw, sel.holes)))
        self.assertEqual(sorted(set(coverage(cam, sel))), [1])

    def test_no_tile_drawn_with_its_ancestor(self):
        # Предок рядом с потомком - только заплатка на чужом месте.
        sel = lod.select(view(*PERM, 2000.0, 30.0, 70.0), half_ready)
        pairs = list(zip(sel.draw, sel.holes))
        whole = {key for key, hole in pairs if hole is None}
        for (z, x, y), hole in pairs:
            for up in range(1, z + 1):
                anc = (z - up, x >> up, y >> up)
                self.assertNotIn(anc, whole)
                for key, ahole in pairs:
                    if key == anc and ahole is not None \
                            and ahole[0] <= z:
                        shift = z - ahole[0]
                        self.assertNotEqual((x >> shift, y >> shift),
                                            ahole[1:])


class TestWant(unittest.TestCase):

    def test_ready_tiles_are_not_wanted(self):
        sel = lod.select(view(*PERM, 500.0), half_ready)
        self.assertTrue(sel.want)
        self.assertFalse([k for k in sel.want if half_ready(k)])

    def test_coarser_tiles_come_first(self):
        # У предка экранная ошибка не меньше. При равенстве, например
        # когда камера внутри обеих описанных сфер и ошибка бесконечна,
        # предок уходит первым как раньше попавший в очередь.
        sel = lod.select(view(*PERM, 500.0), lambda key: key[0] <= 2)
        order = list(sel.want)
        for (z, x, y), priority in sel.want.items():
            if z > 3:
                parent = (z - 1, x // 2, y // 2)
                self.assertGreaterEqual(sel.want[parent], priority)
                self.assertLess(order.index(parent), order.index((z, x, y)))

    def test_only_loading_front_is_wanted(self):
        # У самой земли с готовыми уровнями 0-2 просятся только тайлы
        # уровня 3. Раньше просились тысячи тайлов до уровня 19.
        for cam in (view(*PERM, 500.0), view(*PERM, 400.0, 0.0, 80.0)):
            sel = lod.select(cam, lambda key: key[0] <= 2)
            self.assertEqual({k[0] for k in sel.want}, {3})
            self.assertLess(len(sel.want), 20)

    def test_priority_is_finite(self):
        sel = lod.select(view(*PERM, 50.0), lambda key: key[0] <= 12)
        self.assertTrue(sel.want)
        for priority in sel.want.values():
            self.assertLess(priority, lod.INFINITE_PRIORITY + 1)
        self.assertGreater(lod.priority(math.inf, 3),
                           lod.priority(math.inf, 4))

    def test_keep_covers_draw_and_want(self):
        sel = lod.select(view(*PERM, 2000.0, 30.0, 70.0), half_ready)
        self.assertTrue(set(sel.draw) <= sel.keep)
        self.assertTrue(set(sel.want) <= sel.keep)


class TestCulling(unittest.TestCase):

    def test_far_side_is_culled(self):
        cam = view(*PERM, 1.0e6)
        sel = lod.select(cam, everything)
        far = (5,) + tl.lonlat_to_tile(-PERM[0], PERM[1] - 180.0, 5)
        self.assertNotIn(far, sel.keep)
        for z, x, y in sel.keep:
            if z >= 5:
                info = lod.tile_info(z, x, y)
                self.assertGreater(float(np.dot(info.direction,
                                                cam.eye / np.linalg.norm(
                                                    cam.eye))), 0.0)

    def test_behind_the_camera_is_culled(self):
        # Взгляд на север вдоль земли. Тайлы южнее камеры не нужны.
        cam = view(*PERM, 2000.0, 0.0, 80.0)
        sel = lod.select(cam, everything)
        south = (14,) + tl.lonlat_to_tile(PERM[0] - 0.3, PERM[1], 14)
        self.assertNotIn(south, sel.keep)

    def test_street_view_visits_few_nodes(self):
        sel = lod.select(view(*PERM, 500.0), everything)
        self.assertLess(sel.visited, 1500)


class TestScalarEcef(unittest.TestCase):

    def test_matches_numpy_version(self):
        rng = np.random.default_rng(9)
        for lat, lon in rng.uniform([-90, -180], [90, 180], (500, 2)):
            got = np.array(lod._ecef(lat, lon))
            self.assertLess(np.abs(got - el.geodetic_to_ecef(lat, lon))
                            .max(), 1e-6)

    def test_tile_rows_match_tiling(self):
        for z, y in ((0, 0), (5, 7), (12, 1300), (19, 200000)):
            info_lat = lod.tile_info(z, 0, y)
            exact = el.geodetic_to_ecef(
                float(tl.lat_of_row((y + 0.5) / (1 << z))),
                0.5 / (1 << z) * 360.0 - 180.0)
            self.assertLess(np.abs(np.array(info_lat.center) - exact).max(),
                            1e-6)


class TestTerrainHeights(unittest.TestCase):

    def test_peak_beyond_the_horizon_is_kept(self):
        # Глаз в 1 км над экватором смотрит на восток вдоль земли.
        # Отсечение считает горизонт по сфере радиуса B, на экваторе
        # это 4.8° дуги с запасом. Вершина высотой 8 км видна ещё
        # на 2.9° дальше. Тайл на 7.2° без высот отсекается, с высотой
        # 8 км остаётся.
        cam = view(0.0, 0.0, 1000.0, heading=90.0, tilt=89.0)

        def covers(selection):
            # Грубые предки уровней 0-5 накрывают точку всегда.
            return any(tl.lonlat_to_tile(0.0, 7.2, z) == (x, y)
                       for z, x, y in selection.keep if z >= 6)

        self.assertFalse(covers(lod.select(cam, everything)))
        mountains = lod.select(cam, everything,
                               heights=lambda key: (0.0, 8000.0))
        self.assertTrue(covers(mountains))

    def test_coverage_holds_with_heights(self):
        cam = view(*PERM, 2000.0, 30.0, 70.0)
        counts = coverage(cam, lod.select(cam, half_ready,
                                          heights=lambda key: (0.0, 3000.0)))
        self.assertEqual(sorted(set(counts)), [1])

    def test_mountains_do_not_explode_the_tree(self):
        # Камера в 250 м над склоном на высоте 4 км. Склон 20 %: толщина
        # слоя высот тайла - пятая часть его ширины. Сфера тайла
        # поднимается к слою и раздувается на половину толщины.
        # Склон ближе к камере, чем равнина, и деталей нужно больше.
        # Замер 26 сентября 2026 года - в 1.38 раза. С размахом всей
        # высоты гор в радиусе было в 2.4 раза. Порог - 1.5.
        import math

        def layer(key):
            width = 40075016.0 * math.cos(math.radians(43.35)) \
                / (1 << key[0])
            thickness = min(4000.0, 0.2 * width)
            return (4000.0 - thickness, 4000.0)

        flat = lod.select(cm.Camera.look_at(43.35, 42.44, 500.0, tilt=60.0,
                                            **SIZE), everything)
        cam = cm.Camera.look_at(43.35, 42.44, 500.0, tilt=60.0, h=4000.0,
                                **SIZE)
        hills = lod.select(cam, everything, heights=layer)
        self.assertLess(len(hills.draw), 1.5 * len(flat.draw))


def reference_select(camera, ready, heights=None):
    """Прежний обход через _Frame.visible и _Frame.error, образец."""
    frame = lod._Frame(camera, lod.THRESHOLD)
    want, keep = {}, set()

    def span(key):
        return heights(key) if heights is not None else (0.0, 0.0)

    def visit(key):
        z = key[0]
        keep.add(key)
        error = frame.error(lod.tile_info(*key), *span(key))
        is_ready = ready(key)
        if not is_ready:
            want[key] = lod.priority(error, z)
        if z < lod.MAX_LEVEL and error > lod.THRESHOLD:
            kids = [k for k in lod.children(key)
                    if frame.visible(k[0], lod.tile_info(*k), *span(k))]
            if not kids:
                keep.discard(key)
                want.pop(key, None)
                return [], []
            if not is_ready and not any(ready(k) for k in kids):
                return [], [key]
            draws, holes = [], []
            for kid in kids:
                d, h = visit(kid)
                draws.extend(d)
                holes.extend(h)
            if holes and is_ready:
                return draws + [(key, h) for h in holes], []
            return draws, holes
        return ([(key, None)], []) if is_ready else ([], [key])

    pairs, _ = visit((0, 0, 0))
    return [k for k, _ in pairs], want, keep, [h for _, h in pairs]


class TestFastPath(unittest.TestCase):
    """Обход с величинами в локальных переменных совпадает с образцом."""

    def test_same_selection(self):
        def hills(key):
            return (0.0, 3000.0) if key[0] % 2 else (200.0, 900.0)

        for name, (lat, lon), distance, heading, tilt in CAMERAS:
            cam = view(lat, lon, distance, heading, tilt)
            for ready in (everything, half_ready, lambda k: k[0] <= 2):
                for heights in (None, hills):
                    sel = lod.select(cam, ready, heights=heights)
                    draw, want, keep, holes = reference_select(cam, ready,
                                                               heights)
                    self.assertEqual(sel.draw, draw, name)
                    self.assertEqual(sel.holes, holes, name)
                    self.assertEqual(sel.keep, keep, name)
                    # Расстояние считается через sqrt, а не math.dist,
                    # приоритеты расходятся в последнем знаке.
                    self.assertEqual(set(sel.want), set(want), name)
                    for key, value in want.items():
                        self.assertTrue(math.isclose(sel.want[key], value,
                                                     rel_tol=1e-12), name)


class TestMemo(unittest.TestCase):
    """Память узлов не меняет выбор и сбрасывается при сдвиге камеры."""

    def test_same_selection_while_tiles_arrive(self):
        cam = view(*PERM, 2000.0, 30.0, 70.0)
        memo = lod.Memo()
        ready = set()
        full = lod.select(cam, lambda k: True)
        for step in range(6):
            # Тайлы приходят, готовность меняется, камера стоит.
            ready.update(k for k in full.keep if hash(k) % 6 == step)

            def is_ready(k):
                return k[0] <= 2 or k in ready

            with_memo = lod.select(cam, is_ready,
                                   memo=memo.bind(cam, lod.THRESHOLD, 0))
            plain = lod.select(cam, is_ready)
            self.assertEqual(with_memo.draw, plain.draw)
            self.assertEqual(with_memo.want, plain.want)
            self.assertEqual(with_memo.keep, plain.keep)

    def test_partial_reset_when_heights_arrive(self):
        # Высоты приходят по одному тайлу, камера стоит. Память забывает
        # только узлы под пришедшим тайлом и даёт тот же выбор, что
        # расчёт с нуля.
        import numpy as np
        import terrain as tr
        cam = view(*PERM, 2000.0, 30.0, 70.0)
        store = tr.HeightStore()
        flat = np.zeros((256, 256, 4), dtype=np.uint8)
        flat[..., 0] = 128  # высота 0 в кодировке Terrarium
        store.add(tr.make_tile(0, 0, 0, flat))
        memo = lod.Memo()
        rng = np.random.default_rng(2)
        for step in range(8):
            values = memo.bind(cam, lod.THRESHOLD, store.version,
                               store.take_added())
            with_memo = lod.select(cam, everything, heights=store.range_for,
                                   memo=values)
            plain = lod.select(cam, everything, heights=store.range_for)
            self.assertEqual(with_memo.draw, plain.draw, step)
            self.assertEqual(with_memo.keep, plain.keep, step)
            # Следующий тайл высот - над одним из нарисованных тайлов.
            key = with_memo.draw[int(rng.integers(len(with_memo.draw)))]
            hz = tr.height_level(key[0])
            shift = key[0] - hz
            hills = flat.copy()
            hills[..., 0] = 128 + (step + 1) * 4  # высота растёт
            store.add(tr.make_tile(hz, key[1] >> shift, key[2] >> shift,
                                   hills))

    def test_reset_on_camera_and_heights(self):
        memo = lod.Memo()
        cam = view(*PERM, 2000.0, 30.0, 70.0)
        values = memo.bind(cam, lod.THRESHOLD, 0)
        lod.select(cam, everything, memo=values)
        self.assertTrue(values)
        self.assertIs(memo.bind(cam, lod.THRESHOLD, 0), values)
        self.assertIsNot(memo.bind(cam, lod.THRESHOLD, 1), values)
        moved = view(*PERM, 2100.0, 30.0, 70.0)
        self.assertEqual(memo.bind(moved, lod.THRESHOLD, 1), {})


class TestSpeed(unittest.TestCase):

    def test_selection_fits_the_frame_budget(self):
        # Кэш границ прогрет, как во втором и следующих кадрах.
        cam = view(*PERM, 2000.0, 30.0, 70.0)
        lod.select(cam, everything)
        started = time.perf_counter()
        for _ in range(5):
            lod.select(cam, everything)
        spent = (time.perf_counter() - started) / 5
        self.assertLess(spent, 0.008, "%.1f мс" % (spent * 1000))


class TestNearKeys(unittest.TestCase):
    """Уклон и горизонтали - только вблизи глаза."""

    def test_far_tiles_dropped_near_kept(self):
        eye = el.geodetic_to_ecef(PERM[0], PERM[1], 2000.0)
        z = 12
        n = 1 << z
        x0 = int((PERM[1] + 180.0) / 360.0 * n)
        lat = math.radians(PERM[0])
        y0 = int((1.0 - math.asinh(math.tan(lat)) / math.pi) / 2.0 * n)
        under = (z, x0, y0)
        far = (z, x0 + 40, y0)  # около 400 км восточнее
        near = lod.near_keys([under, far], tuple(eye), 30000.0)
        self.assertEqual(near, {under})

    def test_reach_is_relative(self):
        self.assertGreater(lod.ANALYSIS_REACH, 1.0)


if __name__ == "__main__":
    unittest.main()
