# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Каталог старых карт сайта «Это Место» (etomesto.com) по точке.

Решение автора от 13 октября 2026 года - каталогом, карты сайта модуль
не показывает. Сайт отдаёт список карт, накрывающих точку, страницей
listmap.php по широте y и долготе x, без ключа и учётной записи,
проверено в тот же день: у Перми 227 карт. Строка списка - год,
название и имя страницы карты. Карта открывается на сайте браузером,
по адресу страницы, тайлы сайта модуль не запрашивает - они закрыты
ключом сеанса, файлы карт сайт даёт для личного некоммерческого
использования. Запрос - один на действие пользователя.

Модуль Qt не знает.
"""
import html
import re

SITE = "https://etomesto.com/"
LIST_URL = SITE + "listmap.php?y={lat:.6f}&x={lon:.6f}"
PAGE_URL = SITE + "map-{name}/?y={lat:.6f}&x={lon:.6f}"
ATTRIBUTION = ("Это Место", SITE)
ROW = re.compile(
    r"<b>([^<]*)</b>\s*</td>\s*<td[^>]*>\s*"
    r"<a href=\"JavaScript:gomap\('([A-Za-z0-9_.\-]+)'\);\"[^>]*>"
    r"([^<]*)</a>", re.IGNORECASE)
YEAR = re.compile(r"(?<!\d)(1[0-9]{3}|20[0-9]{2})(?!\d)")


def list_url(lat, lon):
    """Адрес списка карт у точки."""
    return LIST_URL.format(lat=lat, lon=lon)


def page_url(name, lat, lon):
    """Страница карты на сайте, вид на точке."""
    return PAGE_URL.format(name=name, lat=lat, lon=lon)


def _year(text, title, name=""):
    """Год карты из столбца года, иначе первый год в названии, иначе
    в имени страницы («perm_permskaya-gub-1800»)."""
    for source in (text, title, name):
        found = YEAR.search(source or "")
        if found:
            return int(found.group(1))
    return None


def parse_list(text):
    """Страница listmap.php - список (год или None, название, имя
    страницы) в порядке сайта, без повторов имени."""
    if isinstance(text, (bytes, bytearray)):
        text = bytes(text).decode("utf-8", errors="replace")
    out = []
    seen = set()
    for year_text, name, title in ROW.findall(text):
        if name in seen:
            continue
        seen.add(name)
        title = " ".join(html.unescape(title).split())
        out.append((_year(html.unescape(year_text), title, name), title,
                    name))
    return out


def matches(item, words):
    """Подходит ли строка списка под слова поиска - все слова в названии
    или в годе."""
    year, title, _ = item
    hay = "{} {}".format(year or "", title).lower()
    return all(word in hay for word in words.lower().split())
