# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сетка тайлов Web Mercator и сетка вершин тайла."""
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import ellipsoid as el  # noqa: E402
import tiling as tl  # noqa: E402

# Эталон - QGIS 4.0.3, перевод в EPSG:3857 и деление на тайлы,
# 26 сентября 2026. Порядок - имя, широта, долгота, z, x, y.
QGIS_TILES = (
    ("Пермь", 58.0105, 56.2294, 5, 20, 9),
    ("Пермь", 58.0105, 56.2294, 16, 43004, 19735),
    ("Пермь", 58.0105, 56.2294, 19, 344033, 157881),
    ("Гринвич", 0.0, 0.0, 16, 32768, 32768),
    ("Сидней", -33.8568, 151.2153, 16, 60295, 39325),
    ("Сидней", -33.8568, 151.2153, 19, 482367, 314600),
    ("Анкоридж", 61.2176, -149.8997, 16, 5479, 18579),
    ("Анкоридж", 61.2176, -149.8997, 19, 43836, 148639),
)


def sample_tiles(seed=5):
    """Тайлы всех уровней, включая крайние столбцы и строки."""
    rng = np.random.default_rng(seed)
    out = [(0, 0, 0)]
    for z in range(1, tl.MAX_LEVEL + 1):
        n = 1 << z
        out.append((z, n - 1, 0))
        out.append((z, 0, n - 1))
        for _ in range(3):
            out.append((z, int(rng.integers(n)), int(rng.integers(n))))
    return out


def world(mesh):
    """Вершины в ECEF, так их соберёт шейдер из центра и смещения."""
    return mesh.center + mesh.positions.astype(np.float64)


def exact_world(z, x, y):
    """Узлы сетки без округления смещений до float32."""
    return tl.grid_ecef(z, x, y)


class TestTileNumbers(unittest.TestCase):

    def test_matches_qgis(self):
        for name, lat, lon, z, x, y in QGIS_TILES:
            self.assertEqual(tl.lonlat_to_tile(lat, lon, z), (x, y),
                             "%s z%d" % (name, z))

    def test_edges_of_the_world(self):
        n = 1 << 10
        self.assertEqual(tl.lonlat_to_tile(90.0, -180.0, 10), (0, 0))
        self.assertEqual(tl.lonlat_to_tile(-90.0, 180.0, 10),
                         (n - 1, n - 1))

    def test_max_lat(self):
        self.assertAlmostEqual(tl.MAX_LAT, 85.0511287798, places=9)
        self.assertEqual(tl.tile_bounds(0, 0, 0),
                         (-180.0, -tl.MAX_LAT, 180.0, tl.MAX_LAT))

    def test_bounds_contain_the_point(self):
        for _, lat, lon, z, x, y in QGIS_TILES:
            west, south, east, north = tl.tile_bounds(z, x, y)
            self.assertTrue(west <= lon < east and south < lat <= north)


class TestMesh(unittest.TestCase):

    def test_neighbours_share_edges_bit_exact(self):
        for z, x, y in sample_tiles():
            n = 1 << z
            here = exact_world(z, x, y)
            east = exact_world(z, (x + 1) % n, y)
            self.assertTrue(np.array_equal(here[:, -1], east[:, 0]),
                            "восточный край %s" % ((z, x, y),))
            if y + 1 < n:
                south = exact_world(z, x, y + 1)
                self.assertTrue(np.array_equal(here[-1], south[0]),
                                "южный край %s" % ((z, x, y),))

    def test_float32_offsets_stay_close(self):
        # Смещение в float32 теряет не больше 1.2e-7 своей длины.
        for z, x, y in sample_tiles():
            mesh = tl.tile_mesh(z, x, y)
            side = mesh.segments + 1
            got = world(mesh)[:side * side].reshape(side, side, 3)
            error = np.linalg.norm(got - exact_world(z, x, y), axis=2).max()
            self.assertLessEqual(error, 1.2e-7 * mesh.radius, (z, x, y))

    def test_street_level_error_under_a_millimetre(self):
        x, y = tl.lonlat_to_tile(58.0105, 56.2294, 16)
        mesh = tl.tile_mesh(16, x, y)
        side = mesh.segments + 1
        got = world(mesh)[:side * side].reshape(side, side, 3)
        self.assertLess(np.abs(got - exact_world(16, x, y)).max(), 1e-3)

    def test_grid_lies_on_the_ellipsoid(self):
        mesh = tl.tile_mesh(7, 88, 38)
        side = mesh.segments + 1
        _, _, h = el.ecef_to_geodetic(world(mesh)[:side * side])
        self.assertLess(np.abs(h).max(), 0.01)

    def test_skirt_hangs_below_by_its_depth(self):
        for z in (0, 3, 9, 17):
            mesh = tl.tile_mesh(z, 0, 0)
            side = mesh.segments + 1
            _, _, h = el.ecef_to_geodetic(world(mesh)[side * side:])
            # Допуск - погрешность смещений float32, как в тесте выше.
            self.assertLess(np.abs(h + tl.skirt_depth(z)).max(),
                            max(0.01, 1.2e-7 * mesh.radius), z)

    def test_skirt_covers_coarser_neighbour_sag(self):
        # Середина хорды соседа уровнем грубее не глубже юбки.
        for z in range(1, tl.MAX_LEVEL + 1):
            parent = exact_world(z - 1, 0, (1 << (z - 1)) // 2)
            mid = (parent[0, :-1] + parent[0, 1:]) / 2.0
            _, _, h = el.ecef_to_geodetic(mid)
            self.assertLess(-h.min(), tl.skirt_depth(z), z)

    def test_triangles_face_outward(self):
        for z, x, y in ((0, 0, 0), (2, 1, 1), (12, 2500, 1300)):
            mesh = tl.tile_mesh(z, x, y)
            pos = world(mesh)
            tri = mesh.indices.reshape(-1, 3)
            side = mesh.segments + 1
            grid = tri[(tri < side * side).all(axis=1)]
            skirt = tri[(tri >= side * side).any(axis=1)]
            a, b, c = pos[grid[:, 0]], pos[grid[:, 1]], pos[grid[:, 2]]
            normal = np.cross(b - a, c - a)
            centre = (a + b + c) / 3.0
            self.assertTrue(((normal * centre).sum(axis=1) > 0).all(), z)
            # Стенка юбки смотрит наружу от середины тайла.
            a, b, c = pos[skirt[:, 0]], pos[skirt[:, 1]], pos[skirt[:, 2]]
            normal = np.cross(b - a, c - a)
            up = el.surface_normal(*tl_centre_latlon(mesh))
            out = (a + b + c) / 3.0 - mesh.center
            out -= np.outer(out @ up, up)
            if z == 0:
                continue  # у тайла уровня 0 нет наружной стороны
            self.assertTrue(((normal * out).sum(axis=1) > 0).all(), z)

    def test_indices_and_uv(self):
        for z in (0, 1, 2, 10):
            mesh = tl.tile_mesh(z, 0, 0)
            seg = mesh.segments
            count = (seg + 1) ** 2 + 4 * seg
            self.assertEqual(len(mesh.positions), count)
            self.assertEqual(len(mesh.uv), count)
            self.assertEqual(len(mesh.indices), 6 * seg * seg + 24 * seg)
            self.assertLess(int(mesh.indices.max()), count)
            self.assertEqual(mesh.indices.dtype, np.uint16)
            self.assertEqual(mesh.positions.dtype, np.float32)
            self.assertEqual(tuple(mesh.uv[0]), (0.0, 0.0))
            self.assertEqual(tuple(mesh.uv[(seg + 1) ** 2 - 1]), (1.0, 1.0))

    def test_uv_follows_the_picture(self):
        # Северо-западный угол картинки - первая вершина сетки.
        mesh = tl.tile_mesh(3, 5, 2)
        west, _, _, north = tl.tile_bounds(3, 5, 2)
        corner = el.geodetic_to_ecef(north, west)
        self.assertLess(np.linalg.norm(world(mesh)[0] - corner), 1.0)

    def test_segments_by_level(self):
        self.assertEqual([tl.segments(z) for z in range(5)],
                         [64, 32, 16, 16, 16])


def height_tile(z, x, y, fn):
    """Тайл высот, высота - функция доли мира u, v."""
    import terrain as tr
    n = 1 << z
    cols = (x + (np.arange(tr.SIZE) + 0.5) / tr.SIZE) / n
    rows = (y + (np.arange(tr.SIZE) + 0.5) / tr.SIZE) / n
    u, v = np.meshgrid(cols, rows)
    heights = fn(u, v).astype(np.float32)
    return tr.HeightTile(z, x, y, heights, float(heights.min()),
                         float(heights.max()))


class TestTerrainMesh(unittest.TestCase):

    def setUp(self):
        import terrain
        self.tr = terrain
        # Склон: высота растёт на юго-восток, 0-3000 м на тайл уровня 8.
        self.z8 = (8, 160, 90)

        def slope(u, v):
            return ((u * 256 - 160) + (v * 256 - 90)) * 1500.0
        self.slope = height_tile(*self.z8, slope)

    def test_vertices_sit_at_sampled_heights(self):
        mesh = tl.tile_mesh(10, 641, 361, self.slope)
        side = mesh.segments + 1
        pos = (mesh.center + mesh.positions.astype(np.float64))[:side * side]
        _, _, h = el.ecef_to_geodetic(pos)
        u, v = self.tr.grid_shares(10, 641, 361, mesh.segments)
        expected = self.tr.sample(self.slope, u, v).ravel()
        self.assertLess(np.abs(h - expected).max(), 0.01)

    def test_neighbours_share_edges_with_same_heights(self):
        a = tl.tile_mesh(10, 641, 361, self.slope)
        b = tl.tile_mesh(10, 642, 361, self.slope)
        side = a.segments + 1
        pa = (a.center + a.positions.astype(np.float64))[:side * side]
        pb = (b.center + b.positions.astype(np.float64))[:side * side]
        east = pa.reshape(side, side, 3)[:, -1]
        west = pb.reshape(side, side, 3)[:, 0]
        self.assertLess(np.abs(east - west).max(), 0.01)
        sa = a.shade[:side * side].reshape(side, side)[:, -1]
        sb = b.shade[:side * side].reshape(side, side)[:, 0]
        self.assertLess(np.abs(sa - sb).max(), 1e-5)

    def test_sea_lowers_mesh_to_sea_level(self):
        # Проход воды опускает вершину на a_sea.w вдоль a_sea.xyz: узлы
        # и юбка ложатся на эллипсоид, высота в sea - высота узла.
        mesh = tl.tile_mesh(10, 641, 361, self.slope, exaggeration=2.0)
        self.assertEqual(mesh.sea.shape, (len(mesh.positions), 4))
        pos = mesh.center + mesh.positions.astype(np.float64)
        flat = pos - mesh.sea[:, :3] * mesh.sea[:, 3:]
        _, _, h = el.ecef_to_geodetic(flat)
        self.assertLess(np.abs(h).max(), 0.05)
        side = mesh.segments + 1
        _, _, grid_h = el.ecef_to_geodetic(pos[:side * side])
        self.assertLess(np.abs(grid_h - mesh.sea[:side * side, 3]).max(),
                        0.05)
        cap = tl.polar_cap_mesh(True)
        self.assertTrue(np.all(cap.sea[:, 3] == 0.0))

    def test_flat_ground_is_not_shaded(self):
        flat = height_tile(*self.z8, lambda u, v: np.zeros_like(u))
        mesh = tl.tile_mesh(10, 641, 361, flat)
        self.assertLess(np.abs(mesh.shade - 1.0).max(), 1e-4)
        plain = tl.tile_mesh(10, 641, 361)
        self.assertTrue(np.all(plain.shade == 1.0))

    def test_slopes_face_the_light_or_not(self):
        # Высота растёт на юго-восток: склон смотрит на северо-запад,
        # к свету. Обратный склон смотрит на юго-восток, в тень.
        lit = tl.tile_mesh(10, 641, 361, self.slope)
        dark = tl.tile_mesh(10, 641, 361, height_tile(
            *self.z8, lambda u, v: 3000.0 - ((u * 256 - 160)
                                             + (v * 256 - 90)) * 1500.0))
        # Уклон около 3 %, разница небольшая, но знак обязан быть верным.
        self.assertGreater(float(np.median(lit.shade)), 1.005)
        self.assertLess(float(np.median(dark.shade)), 0.995)
        # Крутой склон, около 40 %, затенён заметно.
        steep = tl.tile_mesh(10, 641, 361, height_tile(
            *self.z8, lambda u, v: 20.0 * (3000.0 - ((u * 256 - 160)
                                                     + (v * 256 - 90))
                                          * 1500.0)))
        self.assertLess(float(np.median(steep.shade)), 0.8)

    def test_normals_for_the_sun(self):
        # Нормали единичные. У гладкого тайла - нормаль эллипсоида,
        # у склона на юго-восток нормаль наклонена к северо-западу,
        # у соседей на общем краю нормаль одна.
        plain = tl.tile_mesh(10, 641, 361)
        side = plain.segments + 1
        lengths = np.linalg.norm(plain.normals, axis=1)
        self.assertLess(np.abs(lengths - 1.0).max(), 1e-5)
        lat, lon = tl.grid_latlon(10, 641, 361)
        up = tl.surface_normal(lat, lon).reshape(-1, 3)
        self.assertLess(np.abs(plain.normals[:side * side] - up).max(), 1e-6)
        a = tl.tile_mesh(10, 641, 361, self.slope)
        b = tl.tile_mesh(10, 642, 361, self.slope)
        na = a.normals[:side * side].reshape(side, side, 3)[:, -1]
        nb = b.normals[:side * side].reshape(side, side, 3)[:, 0]
        self.assertLess(np.abs(na - nb).max(), 1e-5)
        la, lo = np.radians(lat.ravel()), np.radians(lon.ravel())
        north = np.stack([-np.sin(la) * np.cos(lo), -np.sin(la) * np.sin(lo),
                          np.cos(la)], axis=1)
        east = np.stack([-np.sin(lo), np.cos(lo), np.zeros_like(lo)], axis=1)
        tilt = a.normals[:side * side]
        self.assertGreater(float(np.median((tilt * north).sum(axis=1))), 0.0)
        self.assertLess(float(np.median((tilt * east).sum(axis=1))), 0.0)
        self.assertEqual(len(a.normals), len(a.positions))

    def test_skirt_goes_below_the_height_spread(self):
        mesh = tl.tile_mesh(10, 641, 361, self.slope)
        side = mesh.segments + 1
        pos = mesh.center + mesh.positions.astype(np.float64)
        _, _, h_grid = el.ecef_to_geodetic(pos[:side * side])
        _, _, h_skirt = el.ecef_to_geodetic(pos[side * side:])
        spread = h_grid.max() - h_grid.min()
        self.assertLess(h_skirt.max(), h_grid.max() - spread + 1.0)

    def test_radius_covers_heights(self):
        mesh = tl.tile_mesh(10, 641, 361, self.slope)
        dist = np.linalg.norm(mesh.positions.astype(np.float64), axis=1)
        self.assertLessEqual(dist.max(), mesh.radius + 1e-6)


class TestPolarCap(unittest.TestCase):

    def test_cap_rim_and_pole(self):
        for north in (True, False):
            cap = tl.polar_cap_mesh(north)
            lat, _, h = el.ecef_to_geodetic(
                cap.center + cap.positions.astype(np.float64))
            sign = 1.0 if north else -1.0
            self.assertAlmostEqual(float(lat[0]), sign * 90.0, places=6)
            self.assertLess(np.abs(lat[1:] - sign * tl.MAX_LAT).max(), 1e-6)
            self.assertLess(np.abs(h).max(), 1.0)

    def test_cap_faces_outward(self):
        for north in (True, False):
            cap = tl.polar_cap_mesh(north)
            pos = cap.center + cap.positions.astype(np.float64)
            tri = cap.indices.reshape(-1, 3)
            a, b, c = pos[tri[:, 0]], pos[tri[:, 1]], pos[tri[:, 2]]
            normal = np.cross(b - a, c - a)
            self.assertTrue((((a + b + c) * normal).sum(axis=1) > 0).all(),
                            north)

    def test_cap_meets_the_tiles(self):
        # Край шапки совпадает с краем сетки тайлов уровня 0.
        grid = tl.grid_ecef(0, 0, 0)
        cap = tl.polar_cap_mesh(True, count=tl.segments(0))
        rim = cap.center + cap.positions[1:].astype(np.float64)
        self.assertLess(np.abs(rim - grid[0, :-1]).max(), 2.0)


def tl_centre_latlon(mesh):
    west, south, east, north = tl.tile_bounds(mesh.z, mesh.x, mesh.y)
    lat, _, _ = el.ecef_to_geodetic(mesh.center)
    return float(lat), (west + east) / 2.0


class TestHoleMargin(unittest.TestCase):
    """Полоса счётчика дыр у края диска покрывает просадку хорд."""

    def measured_sag(self, z):
        # Середины сторон и центры треугольников всех тайлов уровня,
        # без юбки: у её треугольников вершины ниже поверхности.
        low = 0.0
        n = 1 << z
        for x in range(n):
            for y in range(n):
                m = tl.tile_mesh(z, x, y)
                p = m.positions.astype(np.float64) + m.center
                hv = el.ecef_to_geodetic(p)[2]
                tri = m.indices.reshape(-1, 3)
                tri = tri[np.all(np.abs(hv[tri]) < 1.0, axis=1)]
                for w in ((1 / 3, 1 / 3, 1 / 3), (0.5, 0.5, 0.0),
                          (0.0, 0.5, 0.5), (0.5, 0.0, 0.5)):
                    q = (p[tri[:, 0]] * w[0] + p[tri[:, 1]] * w[1]
                         + p[tri[:, 2]] * w[2])
                    low = min(low, float(np.min(el.ecef_to_geodetic(q)[2])))
        return -low

    def test_cell_sag_matches_mesh(self):
        for z in (2, 3):
            measured = self.measured_sag(z)
            self.assertLessEqual(measured, tl.cell_sag(z) * 1.001, z)
            self.assertGreater(measured, tl.cell_sag(z) * 0.95, z)

    def test_margin_covers_level_2_and_underlay(self):
        # Кадр без уровней глубже 2 бывает в новом окне, пока идёт
        # загрузка. Полоса 10 км давала там ложные дыры, 26 сентября 2026.
        self.assertGreater(tl.HOLE_MARGIN,
                           tl.cell_sag(2) + tl.UNDERLAY_DEPTH)


if __name__ == "__main__":
    unittest.main()
