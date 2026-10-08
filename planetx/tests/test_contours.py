# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Горизонтали тайла и изолинии сетки."""
import os
import sys
import unittest

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import contours as ct  # noqa: E402

R = 6378137.0


class TestStep(unittest.TestCase):

    def test_nice_series(self):
        self.assertEqual(ct.nice(4.9), 5.0)
        self.assertEqual(ct.nice(21.0), 20.0)
        self.assertEqual(ct.nice(2.3), 2.5)
        self.assertEqual(ct.nice(8.0), 10.0)

    def test_tile_step_by_level(self):
        # Тайлы у Перми, 58° с. ш.: уровень 15 - 5 м, 13 - 20 м.
        y15 = int((1 - np.arcsinh(np.tan(np.radians(58.0))) / np.pi) / 2
                  * (1 << 15))
        self.assertEqual(ct.tile_step(15, y15, R), 5.0)
        self.assertEqual(ct.tile_step(13, y15 >> 2, R), 20.0)


class TestTile(unittest.TestCase):

    def test_lines_on_slope_plane(self):
        # Плоскость, высота растёт на 1 м за пиксель вдоль столбцов:
        # горизонтали через 10 м - вертикальные полосы через 10 пикселей.
        h = np.tile(np.arange(256, dtype=np.float64), (256, 1))
        rgba = ct.contour_rgba(h, 15, 10000, R, step=10.0)
        alpha = rgba[128, :, 3]
        on = np.flatnonzero(alpha > 100)
        self.assertTrue(set(range(10, 250, 10)) <= set(on.tolist()))
        self.assertEqual(alpha[15], 0)
        # Утолщённая горизонталь (50 м) шире обычной (40 м).
        width = lambda c: int(rgba[128, c - 3:c + 4, 3].astype(int).sum())
        self.assertGreater(width(50), width(40))

    def test_flat_lake_on_level_is_not_filled(self):
        # Озеро ровно на отметке 100 м при сечении 10 м: прежде гладь
        # заливалась цветом линии целиком.
        h = np.full((256, 256), 100.0)
        h[:, 200:] += np.arange(56) * 0.5
        rgba = ct.contour_rgba(h, 15, 10000, R, step=10.0)
        self.assertEqual(int(rgba[:, :150, 3].max()), 0)

    def test_water_color_below_zero(self):
        h = np.tile(np.arange(-128, 128, dtype=np.float64), (256, 1))
        rgba = ct.contour_rgba(h, 15, 10000, R, step=10.0)
        under, over = rgba[100, 118], rgba[100, 148]
        self.assertGreater(under[2], under[0])
        self.assertGreater(over[0], over[2])


def fake_glyphs(height=7, width=5):
    """Цифры - сплошные прямоугольники, точка и минус уже."""
    glyphs = {"height": height}
    for c in "0123456789":
        glyphs[c] = np.ones((height, width), np.float32)
    glyphs["-"] = np.ones((height, 3), np.float32)
    glyphs["."] = np.ones((height, 2), np.float32)
    return glyphs


class TestLabels(unittest.TestCase):

    def test_label_text(self):
        self.assertEqual(ct.label_text(250.0), "250")
        self.assertEqual(ct.label_text(-1000.0), "-1000")
        self.assertEqual(ct.label_text(112.5), "112.5")

    def test_index_line_labelled_across_slope(self):
        # Подъём вдоль столбцов на 0.5 м за пиксель, сечение 5 м:
        # горизонтали через 10 пикселей, утолщённые (25 м) - через 50.
        h = np.tile(np.arange(256, dtype=np.float64) * 0.5, (256, 1))
        bare = ct.contour_rgba(h, 15, 10000, R, step=5.0)
        rgba = ct.contour_rgba(h, 15, 10000, R, step=5.0,
                               glyphs=fake_glyphs())
        smooth = ct.smooth(h)
        d_row, d_col, gap, spacing, index = ct.line_fields(smooth, 5.0)
        labels = ct.place_labels(smooth, d_row, d_col, 5.0,
                                 ct.label_spots(gap, index, spacing, 7),
                                 fake_glyphs())
        self.assertGreater(len(labels), 0)
        diff = np.abs(rgba[..., 3].astype(int) - bare[..., 3].astype(int))
        self.assertGreater(int((diff > 60).sum()), 30)
        for text, (rows, cols, ink, clear), value in labels:
            self.assertEqual(value % 25.0, 0.0)
            on = ink > 0.5
            r, c = rows[on], cols[on]
            # Подпись на утолщённой линии: столбец отметки value.
            self.assertLess(abs(np.median(c) - value / 0.5), 3)
            # Текст вдоль линии - по строкам, поперёк - высота цифр.
            self.assertLessEqual(np.ptp(c), 8)
            length = ct.label_strip(text, fake_glyphs()).shape[1]
            self.assertGreaterEqual(np.ptp(r), length - 2)
            self.assertEqual(text, ct.label_text(value))

    def test_no_labels_where_lines_crowd(self):
        # Горизонтали через 2 пикселя - цифрам места нет.
        h = np.tile(np.arange(256, dtype=np.float64), (256, 1))
        bare = ct.contour_rgba(h, 15, 10000, R, step=2.0)
        rgba = ct.contour_rgba(h, 15, 10000, R, step=2.0,
                               glyphs=fake_glyphs())
        self.assertTrue(np.array_equal(bare, rgba))


class TestSegments(unittest.TestCase):

    def test_cone_levels(self):
        r, c = np.mgrid[0:21, 0:21].astype(np.float64)
        z = 100.0 - np.hypot(r - 10, c - 10) * 5.0
        segs = ct.segments(z, 77.0)
        self.assertGreater(len(segs), 10)
        # Точки отрезков - на окружности радиуса 4.6 узла.
        d = np.hypot(segs[..., 0] - 10, segs[..., 1] - 10)
        self.assertTrue(np.allclose(d, 4.6, atol=0.3))

    def test_nan_cells_skipped(self):
        z = np.array([[0.0, 10.0], [0.0, np.nan]])
        self.assertEqual(len(ct.segments(z, 5.0)), 0)

    def test_grid_step_and_levels(self):
        z = np.array([[-306.0, 69.0], [np.nan, 0.0]])
        step = ct.grid_step(z)
        self.assertEqual(step, 25.0)
        lv = ct.levels(z, step)
        self.assertEqual((lv[0], lv[-1]), (-300.0, 50.0))


if __name__ == "__main__":
    unittest.main()
