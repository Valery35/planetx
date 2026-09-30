# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Сцена: запись, чтение, проверка файла."""
import io
import json
import os
import sys
import unittest
import zipfile

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import scene as sc  # noqa: E402


def sample():
    return sc.Scene(
        (58.01, 56.23, 12000.0, 30.0, 55.0),
        time={"mode": 1, "start": "2026-09-28T10:00:00",
              "end": "2026-09-28T10:20:00", "frame": 4, "step": 60.0},
        layers=[{"name": "Скважины", "provider": "ogr",
                 "source": "C:/data/wells.gpkg|layername=wells",
                 "kind": "vector"}],
        view={"basemap": "Esri World Imagery", "relief": True,
              "scale": 2.0, "groups": ["borders", "places"],
              "language": "ru"},
        places="Маршрут", name="Пермь")


class TestScene(unittest.TestCase):

    def test_round_trip_with_places(self):
        data = sc.write_scene(sample(), "<kml/>")
        scene, kml = sc.read_scene(data)
        self.assertEqual(scene.camera, (58.01, 56.23, 12000.0, 30.0, 55.0))
        self.assertEqual(scene.time["frame"], 4)
        self.assertEqual(scene.layers[0]["name"], "Скважины")
        self.assertEqual(scene.view["groups"], ["borders", "places"])
        self.assertEqual((scene.places, scene.name), ("Маршрут", "Пермь"))
        self.assertEqual(kml, b"<kml/>")

    def test_without_places_and_time(self):
        scene, kml = sc.read_scene(sc.write_scene(
            sc.Scene((0.0, 0.0, 1.0e6))))
        self.assertIsNone(scene.time)
        self.assertEqual(kml, b"")

    def test_body(self):
        mars = sc.Scene((18.65, -133.8, 1.2e7), body="mars")
        scene, _ = sc.read_scene(sc.write_scene(mars))
        self.assertEqual(scene.body, "mars")
        # Сцена до планет, без тела в камере, - земная.
        old = sample().to_dict()
        del old["camera"]["body"]
        self.assertEqual(sc.Scene.from_dict(old).body, "earth")

    def test_bad_files(self):
        def pack(payload):
            buffer = io.BytesIO()
            with zipfile.ZipFile(buffer, "w") as archive:
                archive.writestr(sc.SCENE_FILE, payload)
            return buffer.getvalue()
        newer = dict(sample().to_dict(), format=sc.FORMAT + 1)
        far = sample().to_dict()
        far["camera"]["lat"] = 120.0
        for data in (b"not a zip", pack("{"), pack("[]"),
                     pack(json.dumps(newer)), pack(json.dumps(far)),
                     pack(json.dumps({"format": 1}))):
            with self.assertRaises(sc.SceneError):
                sc.read_scene(data)


if __name__ == "__main__":
    unittest.main()
