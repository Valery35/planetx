# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Камера и матрицы с отсчётом от глаза."""
import math
import os
import sys
import unittest

import numpy as np

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import camera as cm  # noqa: E402
import ellipsoid as el  # noqa: E402
import tiling as tl  # noqa: E402

PERM = (58.0105, 56.2294)


def street_camera():
    """Камера в 100 м над Пермью, взгляд под 60° от отвеса."""
    cam = cm.Camera.look_at(*PERM, distance=200.0, heading=30.0,
                            tilt=60.0)
    return cam


def visible(cam, pixels, in_front):
    """Точки перед камерой и не дальше половины окна за его краем."""
    x, y = pixels[..., 0], pixels[..., 1]
    return (in_front & (x > -0.5 * cam.width) & (x < 1.5 * cam.width)
            & (y > -0.5 * cam.height) & (y < 1.5 * cam.height))


def shader_pixels(cam, mvp32, points32):
    """Путь вершины в шейдере, вся арифметика в float32."""
    ones = np.ones((len(points32), 1), dtype=np.float32)
    v = np.concatenate([points32, ones], axis=1)
    clip = v @ mvp32.T
    # В контрольном прогоне с мировыми координатами в float32 w местами
    # обращается в ноль. Такие точки дают бесконечность и в сравнение
    # попадают как ошибка.
    with np.errstate(divide="ignore", invalid="ignore"):
        ndc = clip[:, :2] / clip[:, 3:4]
    return cam.ndc_to_pixels(ndc.astype(np.float64))


def street_tiles(cam):
    """Тайлы уровней 16-18 вокруг точки взгляда."""
    out = []
    for z in (16, 17, 18):
        x0, y0 = tl.lonlat_to_tile(*PERM, z)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.append(tl.tile_mesh(z, x0 + dx, y0 + dy))
    return out


class TestRelativeToEye(unittest.TestCase):

    def errors(self, world_in_float32):
        cam = street_camera()
        worst = 0.0
        count = 0
        for mesh in street_tiles(cam):
            side = mesh.segments + 1
            exact = tl.grid_ecef(mesh.z, mesh.x, mesh.y).reshape(-1, 3)
            reference, in_front = cam.project(exact)
            if world_in_float32:
                model_view = np.eye(4)
                model_view[:3, :3] = cam.rotation.T
                model_view[:3, 3] = -cam.rotation.T @ cam.eye
                mvp = (cam.projection() @ model_view).astype(np.float32)
                points = exact.astype(np.float32)
            else:
                mvp = cam.tile_mvp(mesh.center)
                points = mesh.positions[:side * side]
            got = shader_pixels(cam, mvp, points)
            mask = visible(cam, reference, in_front)
            count += int(mask.sum())
            if mask.any():
                diff = np.linalg.norm(got[mask] - reference[mask], axis=1)
                worst = max(worst, float(diff.max()))
        return worst, count

    def test_street_level_error_under_hundredth_of_pixel(self):
        worst, count = self.errors(world_in_float32=False)
        self.assertGreater(count, 500)
        self.assertLess(worst, 0.01)

    def test_world_coordinates_in_float32_fail(self):
        # Сторож приёма. Без отсчёта от глаза ошибка больше пикселя.
        worst, _ = self.errors(world_in_float32=True)
        self.assertGreater(worst, 1.0)

    def test_space_view_error_under_hundredth_of_pixel(self):
        cam = cm.Camera.look_at(*PERM, distance=2.0e7)
        worst = 0.0
        for x in range(4):
            for y in range(4):
                mesh = tl.tile_mesh(2, x, y)
                exact = tl.grid_ecef(2, x, y).reshape(-1, 3)
                reference, in_front = cam.project(exact)
                side = mesh.segments + 1
                got = shader_pixels(cam, cam.tile_mvp(mesh.center),
                                    mesh.positions[:side * side])
                mask = visible(cam, reference, in_front)
                if mask.any():
                    diff = np.linalg.norm(got[mask] - reference[mask],
                                          axis=1)
                    worst = max(worst, float(diff.max()))
        self.assertLess(worst, 0.01)


class TestBatch(unittest.TestCase):

    def test_batch_equals_one_by_one(self):
        cam = street_camera()
        meshes = street_tiles(cam)
        centers = [m.center for m in meshes]
        scales = [1.0] * (len(meshes) - 3) + [1.0 - 1000.0 / el.A] * 3
        batch = cam.tiles_mvp(centers, scales=scales)
        self.assertEqual(batch.shape, (len(meshes), 4, 4))
        self.assertEqual(batch.dtype, np.float32)
        self.assertTrue(batch.flags["C_CONTIGUOUS"])
        for i, (c, s) in enumerate(zip(centers, scales)):
            single = cam.tile_mvp(c, scale=s)
            np.testing.assert_allclose(batch[i], single, rtol=1e-6,
                                       atol=1e-6)

    def test_batch_keeps_street_precision(self):
        cam = street_camera()
        meshes = street_tiles(cam)
        batch = cam.tiles_mvp([m.center for m in meshes])
        worst = 0.0
        for mvp, mesh in zip(batch, meshes):
            side = mesh.segments + 1
            exact = tl.grid_ecef(mesh.z, mesh.x, mesh.y).reshape(-1, 3)
            reference, in_front = cam.project(exact)
            got = shader_pixels(cam, mvp, mesh.positions[:side * side])
            mask = visible(cam, reference, in_front)
            if mask.any():
                worst = max(worst, float(np.linalg.norm(
                    got[mask] - reference[mask], axis=1).max()))
        self.assertLess(worst, 0.01)


class TestScaledTile(unittest.TestCase):

    def test_scale_shrinks_towards_the_centre(self):
        # Подстилка: тайл, сжатый к центру Земли, ложится туда же,
        # куда лёг бы тайл из точек, умноженных на scale.
        cam = cm.Camera.look_at(*PERM, distance=2.0e6, tilt=30.0)
        scale = 1.0 - 1000.0 / el.A
        mesh = tl.tile_mesh(2, 2, 1)
        side = mesh.segments + 1
        exact = tl.grid_ecef(2, 2, 1).reshape(-1, 3) * scale
        reference, in_front = cam.project(exact)
        got = shader_pixels(cam, cam.tile_mvp(mesh.center, scale=scale),
                            mesh.positions[:side * side])
        mask = visible(cam, reference, in_front)
        self.assertGreater(int(mask.sum()), 20)
        diff = np.linalg.norm(got[mask] - reference[mask], axis=1)
        self.assertLess(float(diff.max()), 0.01)


class TestOrientation(unittest.TestCase):

    def test_rotation_is_proper(self):
        for heading in (0.0, 45.0, 200.0):
            for tilt in (0.0, 30.0, 89.0):
                r = cm.orientation(*PERM, heading, tilt)
                self.assertLess(np.abs(r.T @ r - np.eye(3)).max(), 1e-12)
                self.assertAlmostEqual(np.linalg.det(r), 1.0, places=12)

    def test_target_is_in_the_centre(self):
        for heading, tilt in ((0.0, 0.0), (30.0, 60.0), (250.0, 80.0)):
            cam = cm.Camera.look_at(*PERM, distance=5000.0,
                                    heading=heading, tilt=tilt)
            px, front = cam.project(el.geodetic_to_ecef(*PERM))
            self.assertTrue(front)
            self.assertAlmostEqual(px[0], cam.width / 2, delta=1e-6)
            self.assertAlmostEqual(px[1], cam.height / 2, delta=1e-6)

    def test_heading_turns_north(self):
        north = el.geodetic_to_ecef(PERM[0] + 0.001, PERM[1])
        cam = cm.Camera.look_at(*PERM, distance=5000.0, heading=0.0)
        px, _ = cam.project(north)
        self.assertLess(px[1], cam.height / 2 - 10)
        self.assertAlmostEqual(px[0], cam.width / 2, delta=0.5)
        # Верх экрана смотрит на восток, север уходит влево.
        cam = cm.Camera.look_at(*PERM, distance=5000.0, heading=90.0)
        px, _ = cam.project(north)
        self.assertLess(px[0], cam.width / 2 - 10)

    def test_tilt(self):
        up = el.surface_normal(*PERM)
        down = cm.Camera.look_at(*PERM, distance=1000.0, tilt=0.0)
        self.assertAlmostEqual(float(down.forward @ up), -1.0, places=12)
        level = cm.Camera.look_at(*PERM, distance=1000.0, tilt=90.0)
        self.assertAlmostEqual(float(level.forward @ up), 0.0, places=12)

    def test_distance_and_altitude(self):
        cam = street_camera()
        self.assertAlmostEqual(cam.altitude(), 100.0, delta=0.01)


class TestRay(unittest.TestCase):

    def test_centre_ray_is_forward(self):
        cam = street_camera()
        _, d = cam.ray(cam.width / 2, cam.height / 2)
        self.assertLess(np.abs(d - cam.forward).max(), 1e-12)

    def test_ray_and_project_agree(self):
        cam = street_camera()
        rng = np.random.default_rng(7)
        for px, py in rng.uniform(0, 1, (50, 2)) * [cam.width, cam.height]:
            origin, d = cam.ray(px, py)
            back, front = cam.project(origin + d * 150.0)
            self.assertTrue(front)
            self.assertAlmostEqual(back[0], px, delta=1e-6)
            self.assertAlmostEqual(back[1], py, delta=1e-6)

    def test_ray_hits_the_target(self):
        cam = street_camera()
        origin, d = cam.ray(cam.width / 2, cam.height / 2)
        t = el.ray_intersect(origin, d)
        hit = origin + d * t
        self.assertLess(np.linalg.norm(hit - el.geodetic_to_ecef(*PERM)),
                        1e-3)


class TestEarthMask(unittest.TestCase):

    def test_disk_area_from_space(self):
        # Видимый радиус диска на расстоянии d - arcsin(R / d).
        cam = cm.Camera.look_at(0.0, 0.0, 2.0e7, width=800, height=600)
        mask = cam.earth_mask()
        d = 2.0e7 + el.A
        half = math.asin(el.A / d)
        focal = cam.height / 2 / math.tan(math.radians(cam.fov_y) / 2)
        radius = focal * math.tan(half)
        self.assertAlmostEqual(mask.sum() / (math.pi * radius ** 2), 1.0,
                               delta=0.01)
        self.assertTrue(mask[300, 400])
        self.assertFalse(mask[0, 0])

    def test_erode_removes_the_rim(self):
        cam = cm.Camera.look_at(0.0, 0.0, 2.0e7, width=400, height=300)
        full = cam.earth_mask()
        inner = cam.earth_mask(erode=2)
        self.assertTrue((inner <= full).all())
        self.assertLess(inner.sum(), full.sum())

    def test_street_view_is_all_earth(self):
        cam = cm.Camera.look_at(*PERM, distance=300.0, width=160,
                                height=90)
        self.assertTrue(cam.earth_mask().all())


class TestClipRange(unittest.TestCase):

    def test_ratio_and_coverage(self):
        for h in (50.0, 100.0, 300.0, 1e3, 1e4, 1e5, 1e6, 2e7, 4e7):
            near, far = cm.clip_range(h)
            self.assertLessEqual(far / near, cm.MAX_DEPTH_RATIO * 1.000001)
            # Ближе высоты камеры поверхности нет, она не срезается.
            self.assertLessEqual(near, h)
            horizon = math.sqrt(h * (2 * el.A + h))
            self.assertGreater(far, horizon)


if __name__ == "__main__":
    unittest.main()
