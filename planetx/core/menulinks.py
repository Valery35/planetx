# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свои пункты меню на глобусе: адрес-шаблон точки для браузера.

Просьба автора от 8 октября 2026 года - погоду в точке пользователи
добавят сами, нужен инструмент. Пункт - название и адрес с местами
{lat}, {lon} и {zoom}: широта и долгота точки под курсором и уровень
масштаба карты по ширине вида (geocode.link_zoom). Адрес открывает
браузер, модуль сам в сеть не ходит. Список хранится в настройках
QGIS строкой JSON.

Модуль Qt не знает.
"""
import json

FIELDS = ("lat", "lon", "zoom")
SCHEMES = ("https://", "http://")
EXAMPLE = ("Windy", "https://www.windy.com/{lat}/{lon}?{lat},{lon},{zoom}")


def check(name, template):
    """Причина, по которой пункт не годится, или "" - годится. Строки
    причин - ключи перевода окна (ui/menulinks.py)."""
    if not name.strip():
        return "name"
    if not template.strip().lower().startswith(SCHEMES):
        return "scheme"
    if "{lat}" not in template or "{lon}" not in template:
        return "place"
    try:
        fill(template, 0.0, 0.0, 1)
    except (KeyError, IndexError, ValueError):
        return "braces"
    return ""


def fill(template, lat, lon, zoom):
    """Адрес точки: места {lat} и {lon} - градусы с шестью знаками,
    {zoom} - уровень масштаба. Другие места в фигурных скобках - ошибка
    KeyError, лишняя скобка - ValueError."""
    return template.strip().format(lat="{:.6f}".format(lat),
                                   lon="{:.6f}".format(lon),
                                   zoom=int(zoom))


def load(text):
    """Пункты из строки настроек: список пар (название, шаблон).
    Испорченная строка и негодные пункты пропускаются."""
    try:
        items = json.loads(text) if text else []
    except ValueError:
        return []
    out = []
    if not isinstance(items, list):
        return out
    for item in items:
        if isinstance(item, (list, tuple)) and len(item) == 2 \
                and all(isinstance(part, str) for part in item) \
                and not check(*item):
            out.append((item[0].strip(), item[1].strip()))
    return out


def dump(items):
    """Строка настроек для пунктов."""
    return json.dumps([[name, template] for name, template in items],
                      ensure_ascii=False)
