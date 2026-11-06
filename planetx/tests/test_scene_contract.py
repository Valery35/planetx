# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Общий контракт сцены: разбор проверочных сцен хранилища
planetx-scene совпадает с ожидаемым expected/<сцена>.json.

Хранилище - переменная PLANETX_SCENE, иначе папка planetx-scene рядом
с рабочей копией модуля. Без него тест пропускается. Разбор модуля
меняется только вместе с SCENE.md и новым expected/ - тот же обход,
что tools/expected.py хранилища.
"""
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import kml  # noqa: E402
import scene as sc  # noqa: E402

ROOT = os.environ.get("PLANETX_SCENE") or os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))), "planetx-scene")


def walk(folder, out):
    """Счёт дерева меток, как tools/expected.py хранилища."""
    for child in folder.children:
        if hasattr(child, "children") and not hasattr(child, "kind"):
            out["folders"] += 1
            walk(child, out)
        elif hasattr(child, "overlay"):
            out["overlays"] += 1
            kinds = out["overlay_kinds"]
            kinds[child.kind] = kinds.get(child.kind, 0) + 1
        else:
            out["places"] += 1
            if child.tour:
                out["tours"] += 1
            kinds = out["place_kinds"]
            kinds[child.kind] = kinds.get(child.kind, 0) + 1
            out["names"].append(child.name)


def parse(data):
    scene, places = sc.read_scene(data)
    tree = {"folders": 0, "places": 0, "tours": 0, "overlays": 0,
            "place_kinds": {}, "overlay_kinds": {}, "names": []}
    if places:
        walk(kml.read_file(places, scene.places), tree)
    # Через JSON - кортежи и списки, ключи как в файле.
    return json.loads(json.dumps({"scene": scene.to_dict(),
                                  "places": tree}))


@unittest.skipUnless(os.path.isdir(os.path.join(ROOT, "expected")),
                     "нет хранилища planetx-scene")
class TestContract(unittest.TestCase):

    def test_scenes_match_expected(self):
        scenes = os.path.join(ROOT, "scenes")
        names = sorted(n for n in os.listdir(scenes)
                       if n.endswith(sc.EXTENSION))
        self.assertTrue(names)
        for name in names:
            stem = name[:-len(sc.EXTENSION)]
            with self.subTest(scene=stem):
                with open(os.path.join(scenes, name), "rb") as handle:
                    got = parse(handle.read())
                with open(os.path.join(ROOT, "expected", stem + ".json"),
                          encoding="utf-8") as handle:
                    want = json.load(handle)
                self.assertEqual(got, want)


if __name__ == "__main__":
    unittest.main()
