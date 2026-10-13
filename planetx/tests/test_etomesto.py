# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Каталог карт «Это Место»: адреса и разбор списка карт у точки."""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "core"))

import etomesto  # noqa: E402

# Три строки ответа listmap.php у Перми 13 октября 2026 года в разметке
# сайта: с годом, без года (год в имени страницы) и повтор.
ROWS = """<table>
<tr><td rowspan=2 valign=top bgcolor=#EDEBD3 class=s><b>1782</b></td>
<td width=100% bgcolor=#ecece1><a href="JavaScript:gomap('perm_1782');"
 class=bb>План города Перми 1782 года</a></td><td bgcolor=#ebebe5>
<a href="JavaScript:pm(5836,'79d769c','perm_1782');" class=bb>
<img src=/i/toprev1.gif></a></td></tr>
<tr><td rowspan=2 valign=top bgcolor=#EDEBD3 class=s><b></b></td>
<td width=100% bgcolor=#dff0f6>
<a href="JavaScript:gomap('perm_permskaya-gub-1800');"
 class=bb>Карта Пермской губернии из атласа Вильбрехта</a></td></tr>
<tr><td rowspan=2 valign=top bgcolor=#EDEBD3 class=s><b>1782</b></td>
<td width=100% bgcolor=#ecece1><a href="JavaScript:gomap('perm_1782');"
 class=bb>План города Перми 1782 года</a></td></tr>
</table>"""


class TestList(unittest.TestCase):
    def test_rows(self):
        items = etomesto.parse_list(ROWS.encode("utf-8"))
        self.assertEqual(items, [
            (1782, "План города Перми 1782 года", "perm_1782"),
            (1800, "Карта Пермской губернии из атласа Вильбрехта",
             "perm_permskaya-gub-1800")])

    def test_addresses(self):
        self.assertEqual(etomesto.list_url(58.0105, 56.2502),
                         "https://etomesto.com/listmap.php"
                         "?y=58.010500&x=56.250200")
        self.assertEqual(etomesto.page_url("perm_1782", 58.0105, 56.2502),
                         "https://etomesto.com/map-perm_1782/"
                         "?y=58.010500&x=56.250200")

    def test_search_words(self):
        item = (1782, "План города Перми 1782 года", "perm_1782")
        self.assertTrue(etomesto.matches(item, "перми план"))
        self.assertTrue(etomesto.matches(item, "1782"))
        self.assertFalse(etomesto.matches(item, "казань"))
        self.assertTrue(etomesto.matches(item, ""))

    def test_foreign_page_gives_nothing(self):
        self.assertEqual(etomesto.parse_list("<html>Not found</html>"), [])


if __name__ == "__main__":
    unittest.main()
