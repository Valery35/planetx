# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строка «Поиск»: подсказки при вводе, точное совпадение, история.
Без Qt.

Просьба автора от 4 октября 2026 года - «сделай строку поиска
максимально продвинутой». Подсказки берутся из своих источников -
«Моих меток», истории запросов и, в виде неба, звёзд и созвездий.
Nominatim при вводе не спрашивается: правила службы запрещают
автодополнение, запрос к ней уходит только по Enter.

Подсказка - Suggestion. Порядок - сначала совпадение с началом названия,
потом с началом слова, потом внутри слова. При равенстве - метки, небо,
история, короче выше.
"""
import re
from collections import namedtuple

Suggestion = namedtuple("Suggestion", "kind text key lat lon fov")
Suggestion.__doc__ = """Подсказка строки поиска.

kind - "place" (своя метка, key - её ключ), "star", "constellation"
(lat - склонение, lon - прямое восхождение, градусы, fov - поле
зрения), "history" (text - прежний запрос). text - название."""

KIND_ORDER = {"place": 0, "constellation": 1, "star": 1, "history": 2}
LIMIT = 12  # подсказок в списке
HISTORY = 30  # запросов в истории
# Поле зрения при перелёте к объекту неба, градусы - выбор помощника.
STAR_FOV = 12.0
CONSTELLATION_FOV = 45.0

_SPACES = re.compile(r"\s+")


def norm(text):
    """Строка для сравнения: нижний регистр, ё как е, одиночные
    пробелы."""
    return _SPACES.sub(" ", (text or "").lower().replace("ё", "е")).strip()


def rank(query, name):
    """Насколько name подходит к query: 0 - начало названия, 1 - начало
    слова, 2 - внутри, None - не подходит. query уже в norm."""
    target = norm(name)
    if not query or not target:
        return None
    if target.startswith(query):
        return 0
    if (" " + target).find(" " + query) >= 0:
        return 1
    if query in target:
        return 2
    return None


def suggestions(query, places=(), history=(), sky=(), limit=LIMIT):
    """Подсказки к query. places - (ключ, название, широта, долгота),
    history - прежние запросы от новых к старым, sky - Suggestion
    звёзд и созвездий. Пустой query - последние запросы истории."""
    q = norm(query)
    if not q:
        return [Suggestion("history", h, None, None, None, None)
                for h in list(history)[:limit]]
    found = []
    for key, name, lat, lon in places:
        r = rank(q, name)
        if r is not None:
            found.append((r, Suggestion("place", name, key, lat, lon,
                                        None)))
    for item in sky:
        r = rank(q, item.text)
        if r is not None:
            found.append((r, item))
    for text in history:
        r = rank(q, text)
        if r is not None and norm(text) != q:
            found.append((r, Suggestion("history", text, None, None, None,
                                        None)))
    found.sort(key=lambda pair: (pair[0], KIND_ORDER[pair[1].kind],
                                 len(pair[1].text)))
    out, seen = [], set()
    for _, s in found:
        mark = (s.kind, norm(s.text), s.key)
        if mark in seen:
            continue
        seen.add(mark)
        out.append(s)
        if len(out) >= limit:
            break
    return out


def exact(query, items):
    """Подсказки, чьё название совпадает с query целиком."""
    q = norm(query)
    return [s for s in items if q and norm(s.text) == q]


def drop_repeats(items):
    """Подсказки без прежних запросов, которые повторяют название
    метки, звезды или созвездия из тех же подсказок. Такой запрос
    по Enter ведёт к тому же объекту, вторая строка лишняя."""
    named = set(norm(s.text) for s in items if s.kind != "history")
    return [s for s in items
            if s.kind != "history" or norm(s.text) not in named]


def remember(history, query, size=HISTORY):
    """История с query в начале, без повторов, не длиннее size."""
    q = norm(query)
    if not q:
        return list(history)
    return ([query.strip()] + [h for h in history if norm(h) != q])[:size]


def sky_objects(data, language="ru"):
    """Звёзды и созвездия неба из data/constellations.json как
    подсказки. language - "ru" или "en"."""
    out = []

    def lon_of(ra):
        return ra - 360.0 if ra > 180.0 else ra

    for item in data.get("names", ()):
        out.append(Suggestion("constellation",
                              item.get(language) or item.get("en", ""),
                              item.get("id"), float(item["dec"]),
                              lon_of(float(item["ra"])), CONSTELLATION_FOV))
    for item in data.get("stars", ()):
        out.append(Suggestion("star", item.get(language) or item.get("en", ""),
                              None, float(item["dec"]),
                              lon_of(float(item["ra"])), STAR_FOV))
    return [s for s in out if s.text]
