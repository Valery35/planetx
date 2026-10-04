# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строка «Поиск»: подсказки, точное совпадение, история."""
import json
import os
import sys
import unittest

CORE = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core")
sys.path.insert(0, CORE)

import searchbar as sb  # noqa: E402

SKY = os.path.join(os.path.dirname(CORE), "data", "constellations.json")
PLACES = [("point:1", "Вокзал Пермь-1", 58.02, 56.25),
          ("point:2", "Пермский университет", 58.0, 56.18),
          ("line:3", "Путь вдоль Камы", 58.05, 56.3),
          ("point:4", "Ёлка на эспланаде", 58.0, 56.22)]


class TestSuggestions(unittest.TestCase):

    def test_order_prefix_word_inside(self):
        found = sb.suggestions("перм", PLACES)
        self.assertEqual([s.text for s in found],
                         ["Пермский университет", "Вокзал Пермь-1"])
        inside = sb.suggestions("амы", PLACES)
        self.assertEqual([s.text for s in inside], ["Путь вдоль Камы"])

    def test_yo_and_case(self):
        self.assertEqual(sb.suggestions("ЕЛКА", PLACES)[0].key, "point:4")

    def test_places_before_history_and_no_echo(self):
        history = ["пермь", "Пермский край"]
        found = sb.suggestions("пермь", PLACES, history)
        kinds = [s.kind for s in found]
        self.assertEqual(kinds[0], "place")
        # Запрос, равный введённому, в подсказки не идёт.
        self.assertNotIn("пермь", [s.text for s in found
                                   if s.kind == "history"])

    def test_empty_query_shows_history(self):
        found = sb.suggestions("", PLACES, ["Казань", "Пермь"])
        self.assertEqual([s.text for s in found], ["Казань", "Пермь"])
        self.assertTrue(all(s.kind == "history" for s in found))

    def test_limit(self):
        many = [("point:%d" % n, "Метка %d" % n, 0.0, 0.0)
                for n in range(50)]
        self.assertEqual(len(sb.suggestions("метка", many)), sb.LIMIT)

    def test_exact(self):
        items = sb.suggestions("вокзал пермь-1", PLACES)
        self.assertEqual(sb.exact("Вокзал  Пермь-1", items)[0].key,
                         "point:1")
        self.assertEqual(sb.exact("Вокзал", items), [])

    def test_exact_takes_first_of_same_names(self):
        # Две метки с одним названием: первой идёт первая по списку.
        twins = [("point:7", "Дом", 1.0, 2.0), ("point:8", "дом", 3.0, 4.0),
                 ("point:9", "Домик", 5.0, 6.0)]
        found = sb.exact("дом", sb.suggestions("дом", twins))
        self.assertEqual([s.key for s in found], ["point:7", "point:8"])

    def test_drop_repeats(self):
        # Прежний запрос с названием метки из подсказок не повторяется,
        # прочие запросы остаются.
        history = ["Вокзал Пермь-1", "вокзал Казань"]
        found = sb.suggestions("вокзал", PLACES, history)
        self.assertEqual([(s.kind, s.text) for s in found],
                         [("place", "Вокзал Пермь-1"),
                          ("history", "вокзал Казань"),
                          ("history", "Вокзал Пермь-1")])
        self.assertEqual([(s.kind, s.text) for s in sb.drop_repeats(found)],
                         [("place", "Вокзал Пермь-1"),
                          ("history", "вокзал Казань")])
        # Без метки с таким названием запрос остаётся.
        alone = sb.suggestions("вокзал", (), history)
        self.assertEqual(sb.drop_repeats(alone), alone)


class TestHistory(unittest.TestCase):

    def test_remember_moves_to_front_and_limits(self):
        h = sb.remember(["Казань", "Пермь"], " пермь ")
        self.assertEqual(h, ["пермь", "Казань"])
        h = sb.remember([str(n) for n in range(40)], "новый")
        self.assertEqual(len(h), sb.HISTORY)
        self.assertEqual(h[0], "новый")
        self.assertEqual(sb.remember(["А"], "  "), ["А"])


class TestSky(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        with open(SKY, encoding="utf-8") as fh:
            cls.data = json.load(fh)

    def test_stars_and_constellations(self):
        ru = sb.sky_objects(self.data, "ru")
        sirius = sb.exact("Сириус", ru)[0]
        self.assertEqual(sirius.kind, "star")
        self.assertAlmostEqual(sirius.lat, -16.7161)
        # Прямое восхождение 101.29° - долгота позы та же.
        self.assertAlmostEqual(sirius.lon, 101.2872)
        orion = sb.exact("Орион", ru)[0]
        self.assertEqual(orion.kind, "constellation")
        self.assertEqual(orion.fov, sb.CONSTELLATION_FOV)
        en = sb.sky_objects(self.data, "en")
        self.assertTrue(sb.exact("Sirius", en))
        # Восхождение больше 180° - отрицательная долгота позы.
        self.assertTrue(all(-180.0 <= s.lon <= 180.0 for s in ru))


if __name__ == "__main__":
    unittest.main()
