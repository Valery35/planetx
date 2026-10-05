# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложения картинок: углы, место на экране, фото, KML и KMZ."""
import io
import math
import os
import sys
import unittest
import zipfile

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import ellipsoid  # noqa: E402
import kml  # noqa: E402
import overlays  # noqa: E402

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 16
GROUND = b"""<kml xmlns="http://www.opengis.net/kml/2.2"
 xmlns:gx="http://www.google.com/kml/ext/2.2"><Document><name>D</name>
<GroundOverlay><name>Box</name><color>80ffffff</color>
<drawOrder>2</drawOrder><Icon><href>files/a.png</href></Icon>
<LatLonBox><north>11</north><south>10</south><east>21</east>
<west>20</west></LatLonBox></GroundOverlay>
<GroundOverlay><name>Quad</name><Icon><href>./files/a.png</href></Icon>
<gx:LatLonQuad><coordinates>20,10 21,10 21.5,11 20.2,11</coordinates>
</gx:LatLonQuad></GroundOverlay>
<ScreenOverlay><name>Logo</name><Icon><href>files/a.png</href></Icon>
<overlayXY x="0" y="1" xunits="fraction" yunits="fraction"/>
<screenXY x="10" y="10" xunits="pixels" yunits="insetPixels"/>
<size x="0.2" y="0" xunits="fraction" yunits="fraction"/>
</ScreenOverlay>
<PhotoOverlay><name>Photo</name><Icon><href>files/a.png</href></Icon>
<Camera><longitude>56</longitude><latitude>58</latitude>
<altitude>500</altitude><heading>30</heading><tilt>80</tilt>
<roll>0</roll></Camera><ViewVolume><leftFov>-20</leftFov>
<rightFov>20</rightFov><bottomFov>-15</bottomFov><topFov>15</topFov>
<near>100</near></ViewVolume><Point><coordinates>56,58,500</coordinates>
</Point></PhotoOverlay>
</Document></kml>"""


def kmz(text, files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("doc.kml", text)
        for name, data in files.items():
            archive.writestr(name, data)
    return buffer.getvalue()


class TestCorners(unittest.TestCase):

    def test_box_without_rotation(self):
        corners = overlays.box_corners(11.0, 10.0, 21.0, 20.0)
        self.assertEqual(corners, [(10.0, 20.0), (10.0, 21.0), (11.0, 21.0),
                                   (11.0, 20.0)])
        self.assertEqual(overlays.corners_box(corners),
                         (11.0, 10.0, 21.0, 20.0))

    def test_rotation_turns_counterclockwise(self):
        corners = overlays.box_corners(1.0, -1.0, 1.0, -1.0, 90.0)
        # Левый нижний угол после поворота на 90° против часовой - справа
        # снизу.
        lat, lon = corners[0]
        self.assertAlmostEqual(lat, -1.0, places=6)
        self.assertAlmostEqual(lon, 1.0, places=6)
        self.assertIsNone(overlays.corners_box(
            overlays.box_corners(1.0, -1.0, 1.0, -1.0, 30.0)))

    def test_affine_of_rotated_box(self):
        corners = overlays.box_corners(11.0, 10.0, 21.0, 20.0, 15.0)
        x0, a, b, y0, d, e = overlays.affine(corners)
        # Нижний правый угол - сумма обеих сторон.
        self.assertAlmostEqual(x0 + a + b, corners[1][1], places=7)
        self.assertAlmostEqual(y0 + d + e, corners[1][0], places=7)

    def test_affine_rejects_free_quad(self):
        quad = [(10.0, 20.0), (10.0, 21.0), (11.0, 21.5), (11.0, 20.2)]
        self.assertIsNone(overlays.affine(quad))

    def test_box_kept_with_rotation(self):
        overlay = overlays.Overlay("ground", box=(11, 10, 21, 20, 30))
        self.assertEqual(len(overlay.corners), 4)
        back = overlays.from_params("ground", overlay.params())
        self.assertEqual(back.box, (11.0, 10.0, 21.0, 20.0, 30.0))
        overlay.set_corners(overlay.corners)
        self.assertIsNone(overlay.box)

    def test_drag_corner_keeps_opposite(self):
        box = (11.0, 10.0, 21.0, 20.0, 0.0)
        new = overlays.box_drag(box, "corner", 2, 12.0, 22.0)
        north, south, east, west, rotation = new
        self.assertAlmostEqual(south, 10.0, places=6)
        self.assertAlmostEqual(west, 20.0, places=6)
        self.assertAlmostEqual(north, 12.0, places=6)
        self.assertAlmostEqual(east, 22.0, places=4)

    def test_drag_side_and_centre(self):
        box = (11.0, 10.0, 21.0, 20.0, 0.0)
        north = overlays.box_drag(box, "side", 2, 12.0, 20.5)
        self.assertAlmostEqual(north[0], 12.0, places=6)
        self.assertAlmostEqual(north[1], 10.0, places=6)
        self.assertAlmostEqual(north[2], 21.0, places=6)
        moved = overlays.box_drag(box, "center", 0, 0.5, 0.5)
        self.assertAlmostEqual((moved[0] + moved[1]) / 2.0, 0.5, places=6)
        wide = overlays.box_drag(box, "corner", 1, 9.0, 22.0, centred=True)
        self.assertAlmostEqual(wide[0], 12.0, places=4)

    def test_rotate_handle(self):
        box = (1.0, -1.0, 1.0, -1.0, 0.0)
        # Ромб к западу от середины - поворот на 90° против часовой.
        turned = overlays.box_drag(box, "rotate", 0, 0.0, -1.0)
        self.assertAlmostEqual(turned[4], 90.0, places=6)
        corners, sides, centre, rotate = overlays.box_handles(turned)
        self.assertAlmostEqual(rotate[0], 0.0, places=6)
        self.assertLess(rotate[1], 0.0)

    def test_fit_keeps_aspect(self):
        corners = overlays.fit_corners(0.0, 0.0, 2000.0, 2.0)
        north, south, east, west = overlays.corners_box(corners)
        my, mx = overlays._metres_per_degree(0.0)
        self.assertAlmostEqual((east - west) * mx, 2000.0, places=3)
        self.assertAlmostEqual((north - south) * my, 1000.0, places=3)


class TestScreen(unittest.TestCase):

    def test_top_left_inset(self):
        overlay = overlays.Overlay(
            "screen", overlay_xy=(0, 1, "fraction", "fraction"),
            screen_xy=(10, 10, "pixels", "insetPixels"),
            size=(0.2, 0, "fraction", "fraction"))
        x, y, w, h = overlays.screen_rect(overlay, 1000, 500, 200, 100)
        self.assertEqual((x, y, w, h), (10.0, 10.0, 200.0, 100.0))

    def test_native_size_centre(self):
        overlay = overlays.Overlay(
            "screen", overlay_xy=(0.5, 0.5, "fraction", "fraction"),
            screen_xy=(0.5, 0.5, "fraction", "fraction"))
        self.assertEqual(overlays.screen_rect(overlay, 800, 600, 100, 50),
                         (350.0, 275.0, 100, 50))


class TestPhoto(unittest.TestCase):

    def test_corners_at_near_distance(self):
        camera = (58.0, 56.0, 500.0, 30.0, 80.0, 0.0)
        corners = overlays.photo_corners(camera, (-20, 20, -15, 15), 100.0)
        eye = ellipsoid.geodetic_to_ecef(58.0, 56.0, 500.0)
        centre = np.mean(np.array(corners), axis=0)
        self.assertAlmostEqual(np.linalg.norm(centre - eye), 100.0, places=6)
        width = np.linalg.norm(np.array(corners[1]) - np.array(corners[0]))
        self.assertAlmostEqual(width, 200.0 * math.tan(math.radians(20)),
                               places=6)

    def test_looking_down_is_below_eye(self):
        camera = (0.0, 0.0, 1000.0, 0.0, 0.0, 0.0)
        corners = overlays.photo_corners(camera, (-10, 10, -10, 10), 100.0)
        heights = [ellipsoid.ecef_to_geodetic(np.array(c))[2]
                   for c in corners]
        for height in heights:
            self.assertAlmostEqual(height, 900.0, delta=1.0)

    def test_pose_looks_at_ground(self):
        lat, lon, distance, heading, tilt = overlays.photo_pose(
            (0.0, 0.0, 1000.0, 90.0, 45.0, 0.0), 100.0)
        self.assertAlmostEqual(distance, 1000.0 * math.sqrt(2.0), places=6)
        self.assertGreater(lon, 0.0)
        self.assertAlmostEqual(tilt, 45.0)

    def test_params_round_trip(self):
        overlay = overlays.Overlay("photo", camera=(1, 2, 3, 4, 5, 6),
                                   fov=(-1, 1, -2, 2), near=50.0,
                                   color=(255, 255, 255, 128))
        back = overlays.from_params("photo", overlay.params())
        self.assertEqual(back.camera, (1, 2, 3, 4, 5, 6))
        self.assertEqual(back.fov, (-1, 1, -2, 2))
        self.assertEqual(back.color, (255, 255, 255, 128))


class TestKml(unittest.TestCase):

    def test_read_kmz_with_images(self):
        tree = kml.read_file(kmz(GROUND, {"files/a.png": PNG}))
        items = tree.overlays()
        self.assertEqual([i.kind for i in items],
                         ["ground", "ground", "screen", "photo"])
        self.assertTrue(all(i.image == PNG for i in items))
        box, quad, screen, photo = items
        self.assertEqual(box.overlay.order, 2)
        self.assertEqual(box.overlay.box, (11.0, 10.0, 21.0, 20.0, 0.0))
        self.assertIsNone(quad.overlay.box)
        self.assertEqual(box.overlay.color[3], 128)
        self.assertEqual(quad.overlay.corners[2], (11.0, 21.5))
        self.assertEqual(screen.overlay.screen_xy,
                         (10.0, 10.0, "pixels", "insetPixels"))
        self.assertEqual(photo.overlay.camera[:3], (58.0, 56.0, 500.0))
        # Наложения не входят в метки.
        self.assertEqual(tree.places(), [])

    def test_kmz_round_trip(self):
        tree = kml.read_file(kmz(GROUND, {"files/a.png": PNG}))
        back = kml.read_file(kml.write_kmz(tree))
        items = back.overlays()
        self.assertEqual(len(items), 4)
        self.assertTrue(all(i.image == PNG for i in items))
        self.assertEqual(items[0].overlay.corners,
                         tree.overlays()[0].overlay.corners)
        for a, b in zip(items[1].overlay.corners,
                        tree.overlays()[1].overlay.corners):
            self.assertAlmostEqual(a[0], b[0], places=7)
            self.assertAlmostEqual(a[1], b[1], places=7)
        self.assertEqual(items[3].overlay.fov, (-20.0, 20.0, -15.0, 15.0))

    def test_plain_kml_keeps_href(self):
        tree = kml.read_file(GROUND)
        item = tree.overlays()[0]
        self.assertIsNone(item.image)
        self.assertEqual(item.href, "files/a.png")


class TestRefresh(unittest.TestCase):
    """Обновление картинки по ссылке через промежуток."""

    LINKED = GROUND.replace(
        b"<Icon><href>files/a.png</href></Icon>\n<LatLonBox>",
        b"<Icon><href>https://example.org/a.png</href>"
        b"<refreshMode>onInterval</refreshMode>"
        b"<refreshInterval>60</refreshInterval></Icon>\n<LatLonBox>")

    def test_interval_has_floor(self):
        self.assertEqual(overlays.refresh_interval(0), 0.0)
        self.assertEqual(overlays.refresh_interval(None), 0.0)
        self.assertEqual(overlays.refresh_interval(-5), 0.0)
        self.assertEqual(overlays.refresh_interval("x"), 0.0)
        self.assertEqual(overlays.refresh_interval(float("inf")), 0.0)
        self.assertEqual(overlays.refresh_interval(4),
                         overlays.MIN_REFRESH)
        self.assertEqual(overlays.refresh_interval(300), 300.0)

    def test_params_keep_interval(self):
        overlay = overlays.Overlay("screen", refresh=120)
        back = overlays.from_params("screen", overlay.params())
        self.assertEqual(back.refresh, 120.0)
        plain = overlays.Overlay("screen")
        self.assertNotIn("refresh", plain.params())

    def test_kml_round_trip(self):
        self.assertIn(b"onInterval", self.LINKED)
        tree = kml.read_file(self.LINKED)
        box = tree.overlays()[0]
        self.assertEqual(box.overlay.refresh, 60.0)
        self.assertEqual(tree.overlays()[1].overlay.refresh, 0.0)
        text = kml.write_kml(tree)
        self.assertEqual(text.count("<refreshMode>onInterval"), 1)
        back = kml.read_file(text.encode("utf-8"))
        self.assertEqual(back.overlays()[0].overlay.refresh, 60.0)

    def test_kml_default_interval_raised_to_floor(self):
        text = self.LINKED.replace(
            b"<refreshInterval>60</refreshInterval>", b"")
        tree = kml.read_file(text)
        self.assertEqual(tree.overlays()[0].overlay.refresh,
                         overlays.MIN_REFRESH)


if __name__ == "__main__":
    unittest.main()
