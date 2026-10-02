# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Дерево «Моих меток»: порядок, перенос, обход."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import placetree as pt  # noqa: E402


def tree():
    # корень: a, F1 (b, F2 (c)), d
    return [pt.Node("point:1", None, 0, "a"),
            pt.Node("folder:1", None, 1, "F1"),
            pt.Node("line:2", "folder:1", 0, "b"),
            pt.Node("folder:2", "folder:1", 1, "F2"),
            pt.Node("point:3", "folder:2", 0, "c"),
            pt.Node("polygon:4", None, 2, "d")]


def keys(nodes):
    return [n.key for n in nodes]


class TestOrder(unittest.TestCase):

    def test_walk_depth_first(self):
        self.assertEqual(keys(pt.walk(tree())),
                         ["point:1", "folder:1", "line:2", "folder:2",
                          "point:3", "polygon:4"])
        self.assertEqual(pt.descendants(tree(), "folder:1"),
                         ["line:2", "folder:2", "point:3"])

    def test_unnumbered_after_numbered_by_name(self):
        nodes = [pt.Node("point:9", None, None, "Б"),
                 pt.Node("point:8", None, None, "А"),
                 pt.Node("point:7", None, 5, "Я")]
        self.assertEqual(keys(pt.children(nodes, None)),
                         ["point:7", "point:8", "point:9"])
        self.assertEqual(pt.next_position(nodes, None), 6)
        self.assertEqual(pt.next_position([], None), 0)


class TestMove(unittest.TestCase):

    def apply(self, nodes, plan):
        for n in nodes:
            if n.key in plan:
                n.parent, n.position = plan[n.key]
        return nodes

    def test_move_down_within_parent(self):
        nodes = tree()
        plan = pt.move_plan(nodes, "point:1", None, 3)  # в конец корня
        self.assertEqual(keys(pt.children(self.apply(nodes, plan), None)),
                         ["folder:1", "polygon:4", "point:1"])

    def test_move_into_folder_and_out(self):
        nodes = tree()
        self.apply(nodes, pt.move_plan(nodes, "polygon:4", "folder:2", 0))
        self.assertEqual(keys(pt.children(nodes, "folder:2")),
                         ["polygon:4", "point:3"])
        self.apply(nodes, pt.move_plan(nodes, "point:3", None, 0))
        self.assertEqual(keys(pt.children(nodes, None)),
                         ["point:3", "point:1", "folder:1"])

    def test_folder_not_into_itself_or_descendant(self):
        nodes = tree()
        self.assertEqual(pt.move_plan(nodes, "folder:1", "folder:1", 0), {})
        self.assertEqual(pt.move_plan(nodes, "folder:1", "folder:2", 0), {})
        plan = pt.move_plan(nodes, "folder:2", None, 0)
        self.assertEqual(plan["folder:2"], (None, 0))

    def test_same_place_is_no_change(self):
        self.assertEqual(pt.move_plan(tree(), "folder:1", None, 1), {})
        self.assertEqual(pt.move_plan(tree(), "folder:1", None, 2), {})


class TestMany(unittest.TestCase):

    def apply(self, nodes, plan):
        return TestMove.apply(self, nodes, plan)

    def test_top_keys_drop_inside_of_chosen_folder(self):
        self.assertEqual(pt.top_keys(tree(), ["point:3", "folder:1",
                                              "polygon:4"]),
                         ["folder:1", "polygon:4"])

    def test_chosen_go_together_in_list_order(self):
        nodes = tree()
        plan = pt.move_many_plan(nodes, ["polygon:4", "point:1"],
                                 "folder:2", 1)
        self.apply(nodes, plan)
        self.assertEqual(keys(pt.children(nodes, "folder:2")),
                         ["point:3", "point:1", "polygon:4"])
        self.assertEqual(keys(pt.children(nodes, None)), ["folder:1"])

    def test_index_counts_moved_siblings(self):
        nodes = tree()
        # a и d в конец корня: перед ними остаётся одна F1.
        self.apply(nodes, pt.move_many_plan(nodes, ["point:1", "polygon:4"],
                                            None, 3))
        self.assertEqual(keys(pt.children(nodes, None)),
                         ["folder:1", "point:1", "polygon:4"])

    def test_folder_with_its_child_not_into_itself(self):
        self.assertEqual(pt.move_many_plan(
            tree(), ["folder:1", "point:1"], "folder:2", 0), {})


class TestNumberedName(unittest.TestCase):

    def test_first_and_next(self):
        self.assertEqual(pt.numbered_name("Моя метка", []), "Моя метка 1")
        self.assertEqual(pt.numbered_name(
            "Моя метка", ["Моя метка 1", "Моя метка 4", "Пермь"]),
            "Моя метка 5")

    def test_other_names_do_not_count(self):
        names = ["Моя метка", "Моя метка 2a", "Мой путь 7", "Моя метка -3"]
        self.assertEqual(pt.numbered_name("Моя метка", names),
                         "Моя метка 1")



class TestFolderTools(unittest.TestCase):
    """«Сортировать от А до Я» и папка-переключатель, 2 октября 2026."""

    def test_sort_plan(self):
        nodes = [pt.Node("point:1", None, 0, "в"),
                 pt.Node("folder:1", None, 1, "А"),
                 pt.Node("line:2", None, 2, "б")]
        self.assertEqual(pt.sort_plan(nodes, None),
                         {"folder:1": 0, "line:2": 1, "point:1": 2})

    def test_radio_one_turned_on_switches_siblings_off(self):
        nodes = tree()
        out = pt.radio_states(nodes, {"folder:1"}, {"folder:2": True})
        self.assertEqual(out, {"folder:2": True, "line:2": False})

    def test_radio_folder_checked_keeps_first(self):
        nodes = tree()
        out = pt.radio_states(nodes, {"folder:1"},
                              {"line:2": True, "folder:2": True,
                               "point:3": True})
        self.assertEqual(out["line:2"], True)
        self.assertEqual(out["folder:2"], False)

    def test_radio_choice_is_not_cleared_by_its_own_click(self):
        out = pt.radio_states(tree(), {"folder:1"}, {"line:2": False})
        self.assertEqual(out, {"line:2": True})
        # Флажок самой папки гасит всё.
        out = pt.radio_states(tree(), {"folder:1"},
                              {"folder:1": False, "line:2": False,
                               "folder:2": False})
        self.assertFalse(any(out.values()))

    def test_plain_folder_untouched(self):
        states = {"line:2": True, "folder:2": True}
        self.assertEqual(pt.radio_states(tree(), set(), states), states)

if __name__ == "__main__":
    unittest.main()
