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
from ellipsoid import (ecef_to_geodetic, geodetic_to_ecef,  # noqa: E402
                       surface_normal)

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
        low = np.full(len(self.fp.height), np.inf)
        np.minimum.at(low, self.fp.owner, ground)
        want = (low + self.fp.height)[self.fp.owner]
        self.assertLess(float(np.abs(h[top:] - want).max()), 0.01)

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


def _timed(func, *args):
    start = time.perf_counter()
    func(*args)
    return time.perf_counter() - start


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



def box(lat, lon, size, height, base=0.0):
    """Здание-коробка size × size метров с центром в lat, lon."""
    dlat = size / 2.0 / 111320.0
    dlon = dlat / math.cos(math.radians(lat))
    latlon = np.array([[lat - dlat, lon - dlon], [lat - dlat, lon + dlon],
                       [lat + dlat, lon + dlon], [lat + dlat, lon - dlon]])
    return bd.Footprint(
        PERM, latlon, np.array([1, 2, 3, 0]), np.ones(4, dtype=bool),
        np.zeros(4, dtype=np.int64), np.array([height]), np.array([base]),
        np.array([[200, 200, 200]], dtype=np.uint8),
        np.array([0, 1, 2, 0, 2, 3], dtype=np.uint32))


class TestRayHit(unittest.TestCase):
    """Попадание луча в здание: крыша, стена, промах, ближнее из двух."""

    LAT, LON = 58.0, 56.2

    def setUp(self):
        self.mesh = bd.mesh(box(self.LAT, self.LON, 20.0, 30.0))

    def test_ray_from_above_hits_roof(self):
        origin = geodetic_to_ecef(self.LAT, self.LON, 500.0)
        down = -surface_normal(self.LAT, self.LON)
        distance, point = bd.ray_hit([self.mesh], origin, down)
        self.assertAlmostEqual(distance, 470.0, delta=0.01)
        _, _, height = ecef_to_geodetic(point)
        self.assertAlmostEqual(float(height), 30.0, delta=0.01)

    def test_level_ray_hits_wall(self):
        # Луч на высоте 10 м идёт с запада на восток из точки в 100 м
        # от центра, стена стоит в 10 м от центра, около 90 м пути.
        dlon = 100.0 / (111320.0 * math.cos(math.radians(self.LAT)))
        origin = geodetic_to_ecef(self.LAT, self.LON - dlon, 10.0)
        target = geodetic_to_ecef(self.LAT, self.LON, 10.0)
        distance, point = bd.ray_hit([self.mesh], origin, target - origin)
        wall = geodetic_to_ecef(self.LAT, self.LON - dlon / 10.0, 10.0)
        self.assertAlmostEqual(distance, float(np.linalg.norm(wall - origin)),
                               delta=0.01)
        _, _, height = ecef_to_geodetic(point)
        self.assertAlmostEqual(float(height), 10.0, delta=0.05)

    def test_miss_and_ray_away(self):
        origin = geodetic_to_ecef(self.LAT + 0.01, self.LON, 500.0)
        down = -surface_normal(self.LAT + 0.01, self.LON)
        self.assertIsNone(bd.ray_hit([self.mesh], origin, down))
        origin = geodetic_to_ecef(self.LAT, self.LON, 500.0)
        up = surface_normal(self.LAT, self.LON)
        self.assertIsNone(bd.ray_hit([self.mesh], origin, up))

    def test_ray_above_roof_misses(self):
        dlon = 100.0 / (111320.0 * math.cos(math.radians(self.LAT)))
        origin = geodetic_to_ecef(self.LAT, self.LON - dlon, 40.0)
        target = geodetic_to_ecef(self.LAT, self.LON + dlon, 40.0)
        self.assertIsNone(bd.ray_hit([self.mesh], origin, target - origin))

    def test_nearest_of_two(self):
        low = bd.mesh(box(self.LAT, self.LON, 40.0, 10.0))
        origin = geodetic_to_ecef(self.LAT, self.LON, 500.0)
        down = -surface_normal(self.LAT, self.LON)
        distance, _ = bd.ray_hit([low, self.mesh], origin, down)
        self.assertAlmostEqual(distance, 470.0, delta=0.01)
        self.assertIsNone(bd.ray_hit([], origin, down))


if __name__ == "__main__":
    unittest.main()
