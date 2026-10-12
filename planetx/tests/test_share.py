# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тесты страницы «Поделиться видом» (core/share.py)."""
import json
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "core"))

import share  # noqa: E402
from kml import KFolder, KPlace  # noqa: E402


def sample_tree():
    path = KPlace("Путь", "line", [(58.0, 56.2), (58.01, 56.25)],
                  color=(255, 0, 0, 255), width=3.0)
    zone = KPlace("Зона </script>", "polygon",
                  [(58.0, 56.2), (58.0, 56.3), (58.05, 56.3)],
                  color=(0, 0, 255, 255), fill=(0, 0, 255, 128),
                  description="<b>не тег</b>",
                  view=(58.02, 56.25, 5000.0, 30.0, 60.0))
    town = KPlace("Пермь", "point", [(58.01, 56.25)])
    hidden = KPlace("Скрытая", "point", [(1.0, 1.0)], visible=False)
    closed = KFolder("Закрытая", visible=False,
                     children=[KPlace("Внутри", "point", [(2.0, 2.0)])])
    return KFolder("Пермь", children=[
        path, KFolder("Вложенная", children=[zone]), town, hidden, closed])


def data_of(text):
    found = re.search(r'<script id="planetx-data" type="application/json">'
                      r'(.*?)</script>', text, re.S)
    return json.loads(found.group(1))


class TestPlaces(unittest.TestCase):
    def test_visible_places_in_order(self):
        names = [p.name for p in share.visible_places(sample_tree())]
        self.assertEqual(names, ["Путь", "Зона </script>", "Пермь"])

    def test_features_are_geojson(self):
        data = share.page_data((58.0, 56.2, 20000.0, 10.0, 30.0),
                               sample_tree())
        features = data["places"]["features"]
        self.assertEqual([f["geometry"]["type"] for f in features],
                         ["LineString", "Polygon", "Point"])
        line = features[0]
        self.assertEqual(line["geometry"]["coordinates"][0], [56.2, 58.0])
        self.assertEqual(line["properties"]["color"], "#ff0000")
        ring = features[1]["geometry"]["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])
        self.assertEqual(features[1]["properties"]["fill_opacity"], 0.502)
        self.assertEqual(features[0]["properties"]["fill_opacity"], 0.0)

    def test_camera_and_pitch_limit(self):
        data = share.page_data((58.0, 56.2, 20000.0, 10.0, 89.0))
        self.assertEqual(data["camera"], [58.0, 56.2, 20000.0, 10.0, 85.0])
        self.assertEqual(data["places"]["features"], [])
        self.assertIsNone(data["tour"])


class TestTour(unittest.TestCase):
    def test_stops_from_views_and_points(self):
        tour = share.tour(sample_tree())
        self.assertEqual([s["name"] for s in tour["stops"]],
                         ["Зона </script>", "Пермь"])
        self.assertEqual(tour["stops"][0]["view"],
                         [58.02, 56.25, 5000.0, 30.0, 60.0])
        self.assertEqual(tour["stops"][1]["view"],
                         [58.01, 56.25, share.POINT_DISTANCE, 0.0,
                          share.POINT_TILT])

    def test_recorded_tour_wins(self):
        poses = [(t, 58.0, 56.0 + t * 0.001, 3000.0, 0.0, 45.0)
                 for t in range(10)]
        tree = KFolder("Тур", children=[
            KPlace("Пермь", "point", [(58.01, 56.25)]),
            KFolder("Записи", children=[KPlace(
                "Облёт", "line", [(58.0, 56.0)], tour=poses)])])
        tour = share.tour(tree)
        self.assertEqual(len(tour["record"]), 10)
        self.assertEqual(tour["record"][3][2], 56.003)
        # Записанный тур - не метка страницы.
        self.assertEqual([p.name for p in share.visible_places(tree)],
                         ["Пермь"])


class TestPage(unittest.TestCase):
    def test_page_holds_data_without_closing_script(self):
        data = share.page_data((58.0, 56.2, 20000.0, 10.0, 30.0),
                               sample_tree(), relief=True, scale=2.0,
                               texts={"play": "▶ Облёт"})
        text = share.page("Пермь <вид>", data)
        self.assertIn("<title>Пермь &lt;вид&gt;</title>", text)
        self.assertIn(share.MAPLIBRE + ".js", text)
        self.assertEqual(text.count("</script>"), 3)
        back = data_of(text)
        self.assertEqual(back, data)
        self.assertEqual(back["scale"], 2.0)
        self.assertNotIn("{{", text)

    def test_page_takes_no_esri(self):
        text = share.page("x", share.page_data((0, 0, 1e7, 0, 0)))
        self.assertNotIn("arcgis", text.lower())
        self.assertIn(share.STYLE, text)


if __name__ == "__main__":
    unittest.main()
