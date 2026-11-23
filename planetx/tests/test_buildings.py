# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-здания: разбор слоя building, обрезка, крыши, сетка.

Данные - слой building двух тайлов OpenFreeMap уровня 14 от
29 сентября 2026 года, центр Перми и Берлин-Митте. © OpenMapTiles,
© участники OpenStreetMap, ODbL.
"""
import math
import os
import sys
import time
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import buildings as bd  # noqa: E402
from ellipsoid import ecef_to_geodetic  # noqa: E402

DATA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
PERM = (14, 10751, 4933)
BERLIN = (14, 8802, 5373)


def load(name, key):
    path = os.path.join(DATA, "building_{}_{}_{}_{}.mvt".format(name, *key))
    with open(path, "rb") as f:
        return f.read()


def tri_area(points, indices):
    t = points[indices.reshape(-1, 3)]
    return bd._orient(t[:, 0], t[:, 1], t[:, 2]) * 0.5


def square(x0, y0, size):
    """Кольцо против часовой стрелки в координатах тайла."""
    return np.array([[x0, y0], [x0 + size, y0], [x0 + size, y0 + size],
                     [x0, y0 + size]], dtype=np.float64)


class TestDecode(unittest.TestCase):
    def test_perm_tile(self):
        buildings, extent = bd.decode(load("perm", PERM))
        self.assertEqual(extent, 4096)
        # Проба 29 сентября 2026 года: 627 контуров и 4 двора.
        self.assertEqual(len(buildings), 627)
        self.assertEqual(sum(len(b.rings) - 1 for b in buildings), 4)
        for b in buildings:
            self.assertGreater(bd.area(b.rings[0]), 0.0)
            for hole in b.rings[1:]:
                self.assertLess(bd.area(hole), 0.0)
            self.assertGreater(b.height, b.base)

    def test_heights_follow_levels(self):
        buildings, _ = bd.decode(load("perm", PERM))
        heights = {b.height for b in buildings}
        # Этажи × 3.66 с округлением вверх и 5 м по умолчанию.
        self.assertTrue({4.0, 5.0, 8.0, 15.0, 19.0} <= heights)

    def test_hide_3d_is_skipped(self):
        data = load("berlin", BERLIN)
        buildings, _ = bd.decode(data)
        self.assertGreater(len(buildings), 0)
        fields = list(bd._fields(bd._unpack(data)))
        layer = list(bd._fields(fields[0][2]))
        keys = [bytes(v).decode() for n, w, v in layer if n == 3 and w == 2]
        self.assertIn("hide_3d", keys)
        total = sum(1 for n, w, v in layer if n == 2)
        hidden = 0
        raw = [v for n, w, v in layer if n == 4 and w == 2]
        for n, w, feature in layer:
            if n != 2:
                continue
            for fn, fw, fv in bd._fields(feature):
                if fn == 2:
                    tags = bd._packed(fv)
                    for k, v in zip(tags[0::2], tags[1::2]):
                        if keys[k] == "hide_3d" and bd._value(raw[v]):
                            hidden += 1
        self.assertGreater(hidden, 0)
        self.assertLess(hidden, total)

    def test_parse_color(self):
        self.assertEqual(bd.parse_color("#ff8000"), (255, 128, 0))
        self.assertEqual(bd.parse_color("#abc"), (170, 187, 204))
        self.assertIsNone(bd.parse_color("red"))
        self.assertIsNone(bd.parse_color(None))


class TestOvertureHeights(unittest.TestCase):
    def test_schemas(self):
        # Схема OpenMapTiles главнее, у Overture - высота, иначе этажи.
        self.assertEqual(bd.heights({"render_height": 20,
                                     "render_min_height": 5,
                                     "height": 99}), (20.0, 5.0))
        self.assertEqual(bd.heights({"height": 31.5, "min_height": 3}),
                         (31.5, 3.0))
        top, base = bd.heights({"num_floors": 4, "min_floor": 1})
        self.assertAlmostEqual(top, 4 * bd.FLOOR)
        self.assertAlmostEqual(base, bd.FLOOR)
        self.assertEqual(bd.heights({}), (bd.DEFAULT_HEIGHT, 0.0))


class TestClip(unittest.TestCase):
    def test_inside_ring_is_kept(self):
        ring = square(10, 10, 20)
        self.assertIs(bd.clip(ring, 4096), ring)

    def test_ring_over_edge_is_cut(self):
        ring = square(-30, 100, 60)
        out = bd.clip(ring, 4096)
        self.assertEqual(out[:, 0].min(), 0.0)
        self.assertAlmostEqual(bd.area(out), 30 * 60)

    def test_ring_outside_is_dropped(self):
        self.assertIsNone(bd.clip(square(-100, 10, 50), 4096))

    def test_no_wall_on_tile_edge(self):
        fp = bd.footprints((14, 0, 0), _tile([[square(-30, 100, 60)]]))
        on_edge = (fp.latlon[:, 1] == fp.latlon[fp.next, 1]) \
            & ~fp.wall
        self.assertEqual(int(np.count_nonzero(~fp.wall)), 1)
        self.assertEqual(int(np.count_nonzero(on_edge)), 1)


class TestRoof(unittest.TestCase):
    def check(self, rings):
        points = np.vstack(rings)
        index = []
        start = 0
        for r in rings:
            index.append(list(range(start, start + len(r))))
            start += len(r)
        tri = bd.roof(points, index)
        areas = tri_area(points, tri)
        self.assertTrue(np.all(areas >= -1e-9))
        self.assertAlmostEqual(float(areas.sum()),
                               sum(bd.area(r) for r in rings), places=6)

    def test_concave(self):
        self.check([np.array([[0, 0], [10, 0], [10, 10], [5, 4], [0, 10]],
                             dtype=np.float64)])

    def test_comb(self):
        teeth = []
        for k in range(20):
            teeth += [[k * 2, 10], [k * 2 + 1, 1]]
        ring = np.array([[0, 0], [40, 0], [40, 10]] + teeth[::-1][:-1],
                        dtype=np.float64)
        if bd.area(ring) < 0:
            ring = ring[::-1]
        self.check([ring])

    def test_courtyards(self):
        outer = square(0, 0, 100)
        holes = [square(10, 10, 20)[::-1], square(60, 50, 30)[::-1]]
        self.check([outer] + holes)

    def test_bridge_not_through_vertex(self):
        # Здание Берлина: мост от двора прошёл через его вершину
        # (892, 3323), нарезка встала, веер лёг за контур.
        outer = [[858, 3308], [879, 3287], [921, 3350], [889, 3370],
                 [871, 3339], [874, 3338], [876, 3333]]
        hole = [[888, 3316], [892, 3323], [898, 3318], [894, 3312]]
        points = np.array(outer + hole, dtype=np.float64)
        ring = bd.bridge(points, list(range(7)), [list(range(7, 11))])
        tri = bd._cut(points, ring)
        self.assertTrue(np.all(tri_area(points, tri) > -1e-9))
        self.assertAlmostEqual(float(tri_area(points, tri).sum()),
                               bd.area(points[:7]) + bd.area(points[7:]))

    def test_real_tiles(self):
        for name, key in (("perm", PERM), ("berlin", BERLIN)):
            fp = bd.footprints(key, load(name, key))
            buildings, extent = bd.decode(load(name, key))
            expected = 0.0
            for b in buildings:
                rings = [bd.clip(r, float(extent)) for r in b.rings]
                if rings[0] is None:
                    continue
                expected += sum(bd.area(r) for r in rings if r is not None)
            # Площадь в единицах тайла, по точкам в градусах не считается.
            _, got, least = _roof_area(key, load(name, key))
            self.assertAlmostEqual(got / expected, 1.0, places=6, msg=name)
            # Сумма со знаком сходится и у веера за контуром, поэтому
            # вывернутых треугольников быть не должно.
            self.assertGreater(least, -1e-6, msg=name)
            self.assertEqual(len(fp.roof) % 3, 0)

    def test_speed(self):
        # Отсечение ушей из core.features резало берлинский тайл 356 мс,
        # footprints - 57 мс, 29 сентября 2026 года.
        data = load("berlin", BERLIN)
        best = min(_timed(bd.footprints, BERLIN, data) for _ in range(3))
        self.assertLess(best, 0.15)


class TestMesh(unittest.TestCase):
    def setUp(self):
        self.fp = bd.footprints(PERM, load("perm", PERM))

    def test_counts(self):
        m = bd.mesh(self.fp)
        self.assertEqual(len(m.vertices), bd.vertex_count(self.fp))
        self.assertEqual(len(m.indices) % 3, 0)
        self.assertLess(int(m.indices.max()), len(m.vertices))

    def test_precision(self):
        def slope(lats, lons):
            return 100.0 + (lats - 58.0) * 5000.0
        m = bd.mesh(self.fp, slope)
        xyz = m.center + m.vertices["position"].astype(np.float64)
        lat, lon, h = ecef_to_geodetic(xyz)
        top = len(m.vertices) - len(self.fp.latlon)
        ground = slope(self.fp.latlon[:, 0], self.fp.latlon[:, 1])
        high = np.full(len(self.fp.height), -np.inf)
        np.maximum.at(high, self.fp.owner, ground)
        want = (high + self.fp.height)[self.fp.owner]
        self.assertLess(float(np.abs(h[top:] - want).max()), 0.01)

    def test_datum_is_high(self):
        # Отметка дома - наивысшая точка рельефа под ним: на склоне дом
        # от низкой точки уходил под землю (просьба автора 19.11.2026).
        fp = bd.footprints((14, 0, 0), _tile([[square(100, 100, 50)]]))

        def slope(lats, lons):
            return 100.0 + lons * 0.0 + lats * 1000.0

        m = bd.mesh(fp, slope)
        xyz = m.center + m.vertices["position"].astype(np.float64)
        lat, lon, h = ecef_to_geodetic(xyz)
        ring = fp.latlon[fp.owner == 0]
        highest = float(slope(ring[:, 0], ring[:, 1]).max())
        self.assertAlmostEqual(float(h.max()), highest + fp.height[0],
                               places=2)

    def test_bottom_reaches_surface(self):
        # Низ стены - до самой низкой земли под контуром: на склоне
        # стена висела бы в воздухе (просьба автора 23.11.2026).
        fp = bd.footprints((14, 0, 0), _tile([[square(100, 100, 50)]]))

        def slope(lats, lons):
            return 100.0 + lats * 1000.0

        m = bd.mesh(fp, slope)
        xyz = m.center + m.vertices["position"].astype(np.float64)
        lat, lon, h = ecef_to_geodetic(xyz)
        walls = 4 * int(np.count_nonzero(fp.wall))
        quad = h[:walls].reshape(-1, 4)
        bottom = quad[:, :2].ravel()
        ring = fp.latlon[fp.owner == 0]
        lowest = float(slope(ring[:, 0], ring[:, 1]).min())
        self.assertAlmostEqual(float(bottom.max()), lowest, places=2)
        self.assertAlmostEqual(float(bottom.min()), lowest, places=2)

    def test_inner_bump_lifts(self):
        # Середина контура бывает выше краёв: проба середины поднимает
        # отметку дома, бугор не выпирает сквозь стены (23.11.2026).
        fp = bd.footprints((14, 0, 0), _tile([[square(100, 100, 50)]]))
        self.assertIsNotNone(fp.inner_latlon)
        bump = fp.inner_latlon[0]

        def terrain(lats, lons):
            out = np.full(len(lats), 100.0)
            hit = (np.abs(lats - bump[0]) < 1e-12) \
                & (np.abs(lons - bump[1]) < 1e-12)
            out[hit] = 130.0
            return out

        m = bd.mesh(fp, terrain)
        xyz = m.center + m.vertices["position"].astype(np.float64)
        lat, lon, h = ecef_to_geodetic(xyz)
        top = h[len(h) - len(fp.latlon):]
        self.assertAlmostEqual(float(top.max()), 130.0 + fp.height[0],
                               places=2)
        # Низ остаётся у низкой земли краёв, а не у бугра.
        walls = 4 * int(np.count_nonzero(fp.wall))
        quad = h[:walls].reshape(-1, 4)
        self.assertAlmostEqual(float(quad[:, :2].max()), 100.0, places=2)

    def test_concave_inner_inside(self):
        # У вогнутого контура проба середины берётся только внутри:
        # среднее вершин Г-образного дома лежит снаружи.
        lshape = [[(100, 100), (150, 100), (150, 120), (130, 120),
                  (130, 150), (100, 150)]]
        fp = bd.footprints((14, 0, 0), _tile([lshape]))
        ring = fp.latlon[fp.owner == 0]
        lo = fp.inner_latlon[:, 0] >= ring[:, 0].min() - 1e-12
        hi = fp.inner_latlon[:, 0] <= ring[:, 0].max() + 1e-12
        self.assertTrue(bool((lo & hi).all()))
        self.assertLessEqual(len(fp.inner_latlon), 1)

    def test_mesh_ok(self):
        m = bd.mesh(self.fp)
        self.assertTrue(bd.mesh_ok(m))
        beyond = m.indices.copy()
        beyond[5] = len(m.vertices)
        self.assertFalse(bd.mesh_ok(m._replace(indices=beyond)))
        self.assertFalse(bd.mesh_ok(m._replace(indices=m.indices[:-1])))
        broken = m.vertices.copy()
        broken["position"][3, 1] = np.nan
        self.assertFalse(bd.mesh_ok(m._replace(vertices=broken)))

    def test_walls_face_out(self):
        fp = bd.footprints((14, 0, 0), _tile([[square(100, 100, 50)]]))
        m = bd.mesh(fp)
        walls = m.vertices[:16]
        pos = walls["position"].astype(np.float64).reshape(4, 4, 3)
        middle = pos.mean(axis=1)
        center = middle.mean(axis=0)
        normal = walls["normal"][::4, :3].astype(np.float64)
        self.assertTrue(np.all(((middle - center) * normal).sum(axis=1)
                               > 0.0))


class TestNearTiles(unittest.TestCase):
    def eye(self, height, heading=0.0, tilt=0.0):
        from camera import Camera
        cam = Camera.look_at(58.0105, 56.2294, height, heading=heading,
                             tilt=tilt)
        return cam.eye, cam.forward

    def test_under_eye_first(self):
        eye, forward = self.eye(1500.0)
        near = bd.near_tiles(eye, forward)
        self.assertEqual(near[0][0], PERM)
        self.assertTrue(all(d < bd.RANGE for _, d in near))
        self.assertLessEqual(len(near), bd.MAX_TILES)
        distances = [d for _, d in near]
        self.assertEqual(distances, sorted(distances))

    def test_too_high(self):
        eye, forward = self.eye(bd.RANGE + 100.0)
        self.assertEqual(bd.near_tiles(eye, forward), [])

    def test_ground_counts(self):
        # Над плато в 2 км камера в 7.5 км над эллипсоидом ещё видит дома.
        eye, forward = self.eye(7500.0)
        self.assertTrue(bd.near_tiles(eye, forward, ground=2000.0))

    def test_behind_is_skipped(self):
        eye, forward = self.eye(300.0, heading=0.0, tilt=80.0)
        keys = [k for k, _ in bd.near_tiles(eye, forward, limit=1000)]
        _, x, y = PERM
        south = [k for k in keys if k[2] > y + 1]
        north = [k for k in keys if k[2] < y - 1]
        self.assertGreater(len(north), 0)
        self.assertEqual(south, [])


class TestRoofShapes(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(bd.roof_attrs({"roof_shape": "gabled",
                                        "roof_direction": 90,
                                        "roof_height": 3.5}),
                         bd.Roof(bd.GABLED, 90.0, 3.5))
        self.assertEqual(bd.roof_attrs({"roof_shape": "HiPPed"}).shape,
                         bd.HIPPED)
        self.assertEqual(bd.roof_attrs({"roof_shape": "half-hipped"}).shape,
                         bd.HALF_HIPPED)
        self.assertEqual(bd.roof_attrs({"roof_shape": "round"}).shape,
                         bd.ROUND)
        self.assertEqual(bd.roof_attrs({}).shape, bd.FLAT)
        # Односкатные: skillion и его имена в Overture.
        for name in ("skillion", "lean_to", "lean-to", "monopitch", "shed"):
            self.assertEqual(bd.roof_attrs({"roof_shape": name}).shape,
                             bd.SKILLION)
        # Кривые и пилообразные профили эталона.
        for name, kind in (("round", bd.ROUND),
                           ("bellcast_gable", bd.BELLCAST_GABLE),
                           ("bellcast-gable", bd.BELLCAST_GABLE),
                           ("butterfly", bd.BUTTERFLY),
                           ("crosspitched", bd.CROSSPITCHED),
                           ("sawtooth", bd.SAWTOOTH)):
            self.assertEqual(bd.roof_attrs({"roof_shape": name}).shape,
                             kind)
        # Тела вращения: купол, луковица, конус.
        for name, kind in (("dome", bd.DOME), ("spherical", bd.DOME),
                           ("onion", bd.ONION), ("cone", bd.CONE)):
            self.assertEqual(bd.roof_attrs({"roof_shape": name}).shape,
                             kind)

    def test_rise(self):
        pts = square(0, 0, 40)
        roof = bd.Roof(bd.GABLED, None, 4.0)
        self.assertEqual(bd._roof_rise(roof, 10, 0, pts), 4.0)
        roof = bd.Roof(bd.GABLED, None, None)
        # полуширина 20 единиц тайла
        want = math.tan(math.radians(bd.ROOF_PITCH)) * 20.0
        self.assertAlmostEqual(bd._roof_rise(roof, 100, 0, pts), want)
        # полуширина в единицах тайла переводится в метры через scale
        self.assertAlmostEqual(bd._roof_rise(roof, 100, 0, pts, 0.5),
                               want * 0.5)
        # оценённая крыша не выше половины здания
        self.assertEqual(bd._roof_rise(roof, 10, 0, pts), 5.0)
        # крыша ниже половины метра не рисуется
        self.assertEqual(bd._roof_rise(roof, 0.6, 0, pts), 0.0)

    def test_frame(self):
        # Рамка ложится по длинной стороне, полуразмеры - половины сторон.
        pts = np.array([[0, 0], [100, 0], [100, 10], [0, 10]],
                       dtype=np.float64)
        frame = bd._roof_frame(pts, None)
        self.assertIsNotNone(frame)
        self.assertAlmostEqual(frame[3], 50.0, places=3)  # L
        self.assertAlmostEqual(frame[4], 5.0, places=3)   # W

    def test_gabled_cover(self):
        pts = square(0, 0, 40)
        verts, rise, tri = bd.roof_surface(pts, bd.GABLED, None, 5.0)
        self.assertIsNotNone(verts)
        t = verts[tri.reshape(-1, 3)]
        plan = bd._orient(t[:, 0, :2], t[:, 1, :2], t[:, 2, :2]) * 0.5
        # Крыша покрывает ровно контур, за стены не свисает.
        self.assertAlmostEqual(float(plan.sum()), bd.area(pts), places=6)
        self.assertGreaterEqual(float(plan.min()), -1e-9)
        self.assertAlmostEqual(float(rise.min()), 0.0)
        self.assertAlmostEqual(float(rise.max()), 1.0)

    def test_hipped_ridge_short(self):
        pts = np.array([[0, 0], [60, 0], [60, 20], [0, 20]],
                       dtype=np.float64)
        verts, rise, tri = bd.roof_surface(pts, bd.HIPPED, None, 5.0)
        self.assertIsNotNone(verts)
        ridge = verts[rise > 0.5]
        self.assertLess(float(np.ptp(ridge[:, 0])), 60.0)

    def test_l_shaped_roof(self):
        # Вогнутый контур кроется целиком: покрытие равно площади
        # контура, а не прямоугольника вокруг него.
        pts = np.array([[0, 0], [40, 0], [40, 20], [20, 20], [20, 40],
                        [0, 40]], dtype=np.float64)
        verts, rise, tri = bd.roof_surface(pts, bd.GABLED, None, 5.0)
        self.assertIsNotNone(verts)
        t = verts[tri.reshape(-1, 3)]
        plan = bd._orient(t[:, 0, :2], t[:, 1, :2], t[:, 2, :2]) * 0.5
        self.assertAlmostEqual(float(plan.sum()), bd.area(pts), places=6)

    def test_skillion_one_slope(self):
        # Односкатная: одна плоскость от карниза до верха стены.
        # До правки skillion считался плоским и профиля не было вовсе.
        groups = bd._roof_profile(bd.SKILLION, 5.0, 20.0, 10.0)
        self.assertEqual(len(groups), 1)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, -10.0), 0.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 0.0), 2.5)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 10.0), 5.0)
        pts = np.array([[0, 0], [40, 0], [40, 20], [0, 20]],
                       dtype=np.float64)
        verts, rise, tri = bd.roof_surface(pts, bd.SKILLION, None, 5.0)
        self.assertIsNotNone(verts)
        t = verts[tri.reshape(-1, 3)]
        plan = bd._orient(t[:, 0, :2], t[:, 1, :2], t[:, 2, :2]) * 0.5
        # Отвесные полосы под краем крыши в плане нулевые.
        self.assertAlmostEqual(float(plan.sum()), bd.area(pts), places=6)
        self.assertAlmostEqual(float(rise.min()), 0.0)
        self.assertAlmostEqual(float(rise.max()), 1.0)
        high = verts[rise > 1.0 - 1e-6]
        # Верхняя кромка идёт вдоль длинной стороны: конька посередине нет.
        self.assertAlmostEqual(float(np.ptp(high[:, 1])), 0.0, places=6)

    def test_long_building_ridge_along_long_side(self):
        # Длинный дом: конёк вдоль длинной стороны, поперёк - ноль.
        pts = np.array([[0, 0], [100, 0], [100, 10], [0, 10]],
                       dtype=np.float64)
        verts, rise, tri = bd.roof_surface(pts, bd.GABLED, None, 5.0)
        self.assertIsNotNone(verts)
        ridge = verts[rise > 0.5]
        self.assertAlmostEqual(float(np.ptp(ridge[:, 0])), 100.0, places=3)
        self.assertAlmostEqual(float(np.ptp(ridge[:, 1])), 0.0, places=3)

    def test_shaped_footprint_and_mesh(self):
        data = _tile_roof([[square(100, 100, 40)]], height=10,
                          roof_shape="gabled", roof_height=4)
        fp = bd.footprints((14, 0, 0), data)
        self.assertIsNotNone(fp.roof_tri)
        self.assertEqual(fp.roof_h[0], 4.0)
        m = bd.mesh(fp)
        self.assertTrue(bd.mesh_ok(m))
        self.assertEqual(len(m.vertices), bd.vertex_count(fp))
        # Скатная крыша - последние вершины сетки, конёк выше карниза.
        tri = fp.roof_tri.reshape(-1, 3)
        pos = m.vertices["position"][-3 * len(tri):].astype(np.float64)
        _, _, h = ecef_to_geodetic(m.center + pos)
        self.assertGreater(float(h.max() - h.min()), 2.0)

    def test_roof_ring_after_courtyard(self):
        # Двор (2 кольца) идёт первым, скат - вторым: крыша второго
        # должна стоять у его контура, а не у чужого кольца.
        specs = [
            ([square(100, 100, 60), square(110, 110, 10)[::-1]],
             {"render_height": 10}),
            ([square(20, 20, 10)],
             {"render_height": 10, "roof_shape": "gabled",
              "roof_height": 3}),
        ]
        fp = bd.footprints((14, 0, 0), _tile_features(specs))
        self.assertIsNotNone(fp.roof_tri)
        tri = fp.roof_tri.reshape(-1, 3)
        mask = fp.roof_owner[tri[:, 0]] == 1
        self.assertTrue(mask.any())
        roof = fp.roof_xy[tri[mask]]
        own = fp.latlon[fp.owner == 1]
        self.assertLess(abs(float(roof[..., 0].mean() - own[:, 0].mean())),
                        1e-4)
        self.assertLess(abs(float(roof[..., 1].mean() - own[:, 1].mean())),
                        1e-4)

    def test_round_roof(self):
        # До правки round считался плоским; теперь полукруглый профиль.
        data = _tile_roof([[square(100, 100, 40)]], height=10,
                          roof_shape="round")
        fp = bd.footprints((14, 0, 0), data)
        self.assertIsNotNone(fp.roof_tri)
        self.assertGreater(float(fp.roof_h[0]), 0.0)
        self.assertTrue(bd.mesh_ok(bd.mesh(fp)))

    def test_profile_shapes_cover(self):
        # Кривые и пилообразные профили кроют контур ровно, без свисания.
        pts = np.array([[0, 0], [40, 0], [40, 20], [0, 20]],
                       dtype=np.float64)
        for kind in (bd.ROUND, bd.BELLCAST_GABLE, bd.BUTTERFLY,
                     bd.CROSSPITCHED, bd.SAWTOOTH):
            verts, rise, tri = bd.roof_surface(pts, kind, None, 5.0)
            self.assertIsNotNone(verts, kind)
            self.assertAlmostEqual(_plan_area(verts, tri), bd.area(pts),
                                   places=6)
            self.assertAlmostEqual(float(rise.min()), 0.0)
            self.assertAlmostEqual(float(rise.max()), 1.0)

    def test_butterfly_and_crosspitched(self):
        groups = bd._roof_profile(bd.BUTTERFLY, 5.0, 20.0, 10.0)
        # Ложбина посередине, карнизы по длинным сторонам.
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 0.0), 0.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 10.0), 5.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, -10.0), 5.0)
        groups = bd._roof_profile(bd.CROSSPITCHED, 5.0, 20.0, 10.0)
        # Два конька крестом: в центре конёк, в углах карниз.
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 0.0), 5.0)
        self.assertAlmostEqual(bd._roof_at(groups, 20.0, 10.0), 0.0)

    def test_bellcast_two_slopes(self):
        groups = bd._roof_profile(bd.BELLCAST_GABLE, 5.0, 20.0, 10.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 0.0), 5.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, -10.0), 0.0)
        # У карниза отлив пологий, к коньку скат крутой.
        self.assertLess(bd._roof_at(groups, 0.0, -8.0), 1.0)
        self.assertGreater(bd._roof_at(groups, 0.0, -3.0), 3.0)

    def test_round_arc(self):
        groups = bd._roof_profile(bd.ROUND, 5.0, 20.0, 10.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 0.0), 5.0)
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 10.0), 0.0, places=6)

    def test_sawtooth_teeth(self):
        # Полуширина 20 единиц, зуб 8: пять зубов, высота у верха ~H.
        groups = bd._roof_profile(bd.SAWTOOTH, 5.0, 20.0, 20.0, 1.0)
        self.assertEqual(len(groups), 5)
        # Середина зуба - половина высоты, у остекления почти полная.
        self.assertAlmostEqual(bd._roof_at(groups, 0.0, 0.0), 2.5,
                               delta=0.1)
        self.assertGreater(bd._roof_at(groups, 0.0, -3.9), 4.5)

    def test_rise_rounded_and_sawtooth(self):
        pts = square(0, 0, 40)
        # Купол: подъём по умолчанию - полуширина, не выше половины стены.
        roof = bd.Roof(bd.DOME, None, None)
        self.assertAlmostEqual(bd._roof_rise(roof, 100, 0, pts), 20.0)
        self.assertAlmostEqual(bd._roof_rise(roof, 10, 0, pts), 5.0)
        # Пила: по половине зуба, зубов пять на полуширине 20.
        roof = bd.Roof(bd.SAWTOOTH, None, None)
        want = math.tan(math.radians(bd.ROOF_PITCH)) * 20.0 / 5.0
        self.assertAlmostEqual(bd._roof_rise(roof, 100, 0, pts), want)

    def test_radial_shapes(self):
        pts = np.array([[0, 0], [40, 0], [40, 20], [0, 20]],
                       dtype=np.float64)
        for kind in (bd.CONE, bd.DOME, bd.ONION):
            verts, rise, tri = bd._radial_surface(pts, 5.0, kind)
            self.assertIsNotNone(verts, kind)
            self.assertGreater(len(tri), 0)
            self.assertAlmostEqual(float(rise.min()), 0.0)
            self.assertAlmostEqual(float(rise.max()), 1.0)
        # Конус, купол и луковица доходят до карниза: покрытие равно
        # контуру. У луковицы нижнее кольцо добавлено у самой стены.
        for kind in (bd.CONE, bd.DOME, bd.ONION):
            verts, rise, tri = bd._radial_surface(pts, 5.0, kind)
            self.assertAlmostEqual(_plan_area(verts, tri), bd.area(pts),
                                   places=6)

    def test_radial_footprint(self):
        data = _tile_roof([[square(100, 100, 40)]], height=10,
                          roof_shape="dome")
        fp = bd.footprints((14, 0, 0), data)
        self.assertIsNotNone(fp.roof_tri)
        self.assertGreater(float(fp.roof_h[0]), 0.0)
        self.assertTrue(bd.mesh_ok(bd.mesh(fp)))

    def test_huge_footprint_stays_flat(self):
        # Огромный контур (у автора 139x88 м) скат рисует плитой:
        # выше MAX_ROOF_AREA крыша плоская, просьба автора 19.11.2026.
        # Тайл (14,0,0) у полюса, единица тайла там ~0.05 м, поэтому
        # контур в 1000 единиц - около 2700 м².
        data = _tile_roof([[square(100, 100, 1000)]], height=20,
                          roof_shape="saltbox")
        fp = bd.footprints((14, 0, 0), data)
        self.assertIsNone(fp.roof_tri)
        self.assertEqual(float(fp.roof_h[0]), 0.0)

    def test_small_footprint_keeps_roof(self):
        # Дом под порогом площади остаётся со скатом.
        data = _tile_roof([[square(100, 100, 40)]], height=10,
                          roof_shape="saltbox")
        fp = bd.footprints((14, 0, 0), data)
        self.assertIsNotNone(fp.roof_tri)
        self.assertGreater(float(fp.roof_h[0]), 0.0)

def _timed(func, *args):
    start = time.perf_counter()
    func(*args)
    return time.perf_counter() - start


def _plan_area(verts, tri):
    """Площадь крыши в плане по её треугольникам."""
    t = verts[tri.reshape(-1, 3)]
    return float((bd._orient(t[:, 0, :2], t[:, 1, :2], t[:, 2, :2])
                  * 0.5).sum())


def _roof_area(key, data):
    """Площадь крыш в единицах тайла по треугольникам footprints."""
    buildings, extent = bd.decode(data)
    points = []
    for b in buildings:
        rings = []
        for number, r in enumerate(b.rings):
            r = bd.clip(r, float(extent))
            if r is None:
                if number == 0:
                    break
                continue
            rings.append(r)
        points.extend(rings)
    xy = np.vstack(points)
    fp = bd.footprints(key, data)
    areas = tri_area(xy, fp.roof)
    return fp, float(areas.sum()), float(areas.min())


def _varint(value):
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            return bytes(out)


def _field(number, wire, payload):
    key = _varint((number << 3) | wire)
    if wire == 0:
        return key + _varint(payload)
    return key + _varint(len(payload)) + payload


def _zz(v):
    return (v << 1) ^ (v >> 63)


def _tile(polygons, height=10):
    """Тайл со слоем building: многоугольники - списки колец."""
    features = b""
    for rings in polygons:
        geometry = []
        x = y = 0
        for ring in rings:
            ring = np.asarray(ring, dtype=np.int64)
            geometry += [9, _zz(int(ring[0, 0]) - x), _zz(int(ring[0, 1]) - y)]
            x, y = int(ring[0, 0]), int(ring[0, 1])
            geometry.append(((len(ring) - 1) << 3) | 2)
            for px, py in ring[1:]:
                geometry += [_zz(int(px) - x), _zz(int(py) - y)]
                x, y = int(px), int(py)
            geometry.append(15)
        packed = b"".join(_varint(v) for v in geometry)
        features += _field(2, 2, _field(2, 2, _varint(0) + _varint(0))
                           + _field(3, 0, 3) + _field(4, 2, packed))
    layer = (_field(15, 0, 2) + _field(1, 2, b"building") + features
             + _field(3, 2, b"render_height")
             + _field(4, 2, _field(5, 0, height)) + _field(5, 0, 4096))
    return _field(3, 2, layer)


def _tile_roof(polygons, height=10, roof_shape=None, roof_height=None):
    """Тайл со слоем building и полями крыши Overture."""
    features = b""
    for rings in polygons:
        geometry = []
        x = y = 0
        for ring in rings:
            ring = np.asarray(ring, dtype=np.int64)
            geometry += [9, _zz(int(ring[0, 0]) - x),
                         _zz(int(ring[0, 1]) - y)]
            x, y = int(ring[0, 0]), int(ring[0, 1])
            geometry.append(((len(ring) - 1) << 3) | 2)
            for px, py in ring[1:]:
                geometry += [_zz(int(px) - x), _zz(int(py) - y)]
                x, y = int(px), int(py)
            geometry.append(15)
        packed = b"".join(_varint(v) for v in geometry)
        keys = ["render_height"]
        values = [_field(5, 0, height)]
        tags = _varint(0) + _varint(0)
        for key, value in (("roof_shape", roof_shape),
                           ("roof_height", roof_height)):
            if value is None:
                continue
            ki, vi = len(keys), len(values)
            keys.append(key)
            values.append(
                _field(1, 2, value.encode()) if isinstance(value, str)
                else _field(5, 0, int(value)))
            tags += _varint(ki) + _varint(vi)
        features += _field(2, 2, _field(2, 2, tags)
                           + _field(3, 0, 3) + _field(4, 2, packed))
    layer = _field(15, 0, 2) + _field(1, 2, b"building") + features
    for key in keys:
        layer += _field(3, 2, key.encode())
    for value in values:
        layer += _field(4, 2, value)
    return _field(3, 2, layer + _field(5, 0, 4096))


def _tile_features(specs):
    """Тайл со слоем building: список (rings, attrs) с разными полями.

    attrs - словарь поле -> строка или число. Нужен, когда у зданий
    тайла разные roof_shape (двор и скат в одном тайле).
    """
    keys = []
    values = []
    key_at = {}
    value_at = {}
    features = b""
    for rings, attrs in specs:
        geometry = []
        x = y = 0
        for ring in rings:
            ring = np.asarray(ring, dtype=np.int64)
            geometry += [9, _zz(int(ring[0, 0]) - x),
                         _zz(int(ring[0, 1]) - y)]
            x, y = int(ring[0, 0]), int(ring[0, 1])
            geometry.append(((len(ring) - 1) << 3) | 2)
            for px, py in ring[1:]:
                geometry += [_zz(int(px) - x), _zz(int(py) - y)]
                x, y = int(px), int(py)
            geometry.append(15)
        packed = b"".join(_varint(v) for v in geometry)
        tags = b""
        for key, value in attrs.items():
            if key not in key_at:
                key_at[key] = len(keys)
                keys.append(key)
            payload = (_field(1, 2, value.encode()) if isinstance(value, str)
                       else _field(5, 0, int(value)))
            if payload not in value_at:
                value_at[payload] = len(values)
                values.append(payload)
            tags += _varint(key_at[key]) + _varint(value_at[payload])
        features += _field(2, 2, _field(2, 2, tags)
                           + _field(3, 0, 3) + _field(4, 2, packed))
    layer = _field(15, 0, 2) + _field(1, 2, b"building") + features
    for key in keys:
        layer += _field(3, 2, key.encode())
    for value in values:
        layer += _field(4, 2, value)
    return _field(3, 2, layer + _field(5, 0, 4096))


if __name__ == "__main__":
    unittest.main()
