# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты core/superoverlay.py: дерево сетевых ссылок с Region."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import kml  # noqa: E402
import netlink  # noqa: E402
import superoverlay as so  # noqa: E402
from ellipsoid import geodetic_to_ecef  # noqa: E402
from sync import view_box  # noqa: E402

# Рамка верхнего тайла образца Google mv-070501/1.kml.
NORTH, SOUTH, EAST, WEST = 37.44140625, 37.265625, -121.9921875, -122.16796875


def doc(north, south, east, west, children):
    """Документ тайла: Region, картинка и ссылки на детей."""
    def region(n, s, e, w):
        return ("<Region><Lod><minLodPixels>128</minLodPixels>"
                "<maxLodPixels>-1</maxLodPixels></Lod><LatLonAltBox>"
                "<north>{}</north><south>{}</south><east>{}</east>"
                "<west>{}</west></LatLonAltBox></Region>").format(n, s, e, w)
    links = "".join(
        "<NetworkLink><name>{0}</name>{1}<Link><href>{0}</href>"
        "<viewRefreshMode>onRegion</viewRefreshMode></Link></NetworkLink>"
        .format(href, region(*rect)) for href, rect in children)
    return ("<kml xmlns='http://earth.google.com/kml/2.1'><Document>{}{}"
            "<GroundOverlay><drawOrder>{}</drawOrder><Icon><href>t.jpg</href>"
            "</Icon><LatLonBox><north>{}</north><south>{}</south>"
            "<east>{}</east><west>{}</west></LatLonBox></GroundOverlay>"
            "</Document></kml>").format(
                region(north, south, east, west), links,
                len(children) and 1 or 2, north, south, east, west).encode()


def view(lat, lon, height, focal=800.0, width=None):
    eye = geodetic_to_ecef(lat, lon, height)
    span = width or 2.0 * height
    return eye, (lat, lon), focal, view_box(lat, lon, span, span)


class TestSuperoverlay(unittest.TestCase):

    def setUp(self):
        mid_lat = (NORTH + SOUTH) / 2.0
        self.children = [
            ("a.kml", (NORTH, mid_lat, EAST, WEST)),
            ("b.kml", (mid_lat, SOUTH, EAST, WEST))]
        top = kml.read_file(doc(NORTH, SOUTH, EAST, WEST, self.children))
        link = top.children[0]
        self.assertTrue(link.link)
        self.assertEqual(link.view_mode, "onRegion")
        self.tree = so.Tree("http://x/1.kml")
        netlink.resolve_tree(top, "http://x/1.kml")
        self.tree.loaded(self.tree.root, top)

    def test_far_view_shows_only_top_tile(self):
        wanted, tiles = self.tree.step(*view(37.35, -122.08, 200000.0),
                                       now=1.0)
        # С 200 км тайл ~19 км меньше 128 пикселей - не виден вовсе.
        self.assertEqual(tiles, [])
        self.assertEqual(wanted, [])
        wanted, tiles = self.tree.step(*view(37.35, -122.08, 30000.0),
                                       now=2.0)
        self.assertEqual(len(tiles), 1)
        self.assertEqual(tiles[0][0].href, "http://x/t.jpg")
        # Дети не загружены - тайл ничем не закрыт.
        self.assertIsNone(tiles[0][1])
        # Дети ~10 км на экране шире 128 пикселей - пора загружать обоих.
        self.assertEqual(sorted(n.url for n in wanted),
                         ["http://x/a.kml", "http://x/b.kml"])

    def test_child_tiles_drawn_over_parent(self):
        _, _ = self.tree.step(*view(37.40, -122.08, 30000.0), now=1.0)
        child = [n for n in self.tree.root.children
                 if n.url.endswith("a.kml")][0]
        mid_lat = (NORTH + SOUTH) / 2.0
        sub = kml.read_file(doc(NORTH, mid_lat, EAST, WEST, []))
        netlink.resolve_tree(sub, child.url)
        self.tree.loaded(child, sub)
        wanted, tiles = self.tree.step(*view(37.40, -122.08, 30000.0),
                                       now=2.0)
        self.assertEqual(len(tiles), 2)
        # Ребёнок с большим drawOrder - последним, поверх родителя.
        self.assertEqual(tiles[-1][0].corners[0][0], mid_lat)
        # Второй ребёнок на виде не загружен - родитель не закрыт.
        self.assertIsNone(tiles[0][1])
        # Ребёнок в стороне от вида не просится и не виден.
        _, tiles = self.tree.step(*view(37.29, -122.08, 3000.0), now=3.0)
        self.assertTrue(all(t.corners[0][0] < mid_lat for t, _ in tiles))

    def test_parent_covered_by_loaded_children(self):
        self.tree.step(*view(37.35, -122.08, 30000.0), now=1.0)
        mid_lat = (NORTH + SOUTH) / 2.0
        for child, (n, s) in zip(self.tree.root.children,
                                 ((NORTH, mid_lat), (mid_lat, SOUTH))):
            sub = kml.read_file(doc(n, s, EAST, WEST, []))
            netlink.resolve_tree(sub, child.url)
            self.tree.loaded(child, sub)
        _, tiles = self.tree.step(*view(37.35, -122.08, 30000.0), now=2.0)
        parent = [c for t, c in tiles if t.key.startswith("http://x/1")]
        self.assertEqual(len(parent), 1)
        self.assertEqual(len(parent[0]), 2)
        # Ребёнок вне вида родителя не держит: с 3 км над нижней половиной
        # закрыт одним нижним ребёнком.
        _, tiles = self.tree.step(*view(37.29, -122.08, 3000.0), now=3.0)
        parent = [c for t, c in tiles if t.key.startswith("http://x/1")]
        self.assertEqual(parent, [("http://x/b.kml#0",)])

    def test_view_across_dateline(self):
        rect = so.kml_region.Region(10.0, 0.0, -179.0, 179.0, 0.0, -1.0)
        self.assertTrue(so.overlaps(rect, (178.0, -5.0, -178.0, 5.0)))
        self.assertFalse(so.overlaps(rect, (170.0, -5.0, 175.0, 5.0)))
        self.assertEqual(so.nearest(rect, 5.0, 179.5), (5.0, 179.5))

    def test_trim_drops_old_documents(self):
        old = so.MAX_LOADED
        so.MAX_LOADED = 0
        try:
            for node in self.tree.root.children:
                node.state = "ready"
                node.used = 1.0
            dropped = self.tree.trim(now=5.0)
        finally:
            so.MAX_LOADED = old
        self.assertEqual(len(dropped), 2)
        self.assertTrue(all(n.state == "new"
                            for n in self.tree.root.children))


if __name__ == "__main__":
    unittest.main()
