# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наборы слоёв под задачу. Без Qt.

Решение автора от 11 октября 2026 года, шаг 2 плана «интерфейс над
возможностями» в AGENTS.md. Набор включает свои слои и карту витрины
и выключает остальные управляемые строки. Камера не двигается, рельеф,
подложка и слои проекта не меняются. Состав наборов - выбор помощника,
утверждает автор.

Набор - Preset. key - ключ, extras - включённые строки слоёв, theme -
карта витрины или "", place - действие окна после включения ("rumsey"
- окно карт Рамсея у вида) или "".
"""
from collections import namedtuple

Preset = namedtuple("Preset", "key extras theme place")

# Звёзды включены во всех наборах - их видно только из космоса.
PRESETS = (
    Preset("clean", ("stars",), "", ""),
    Preset("geologist", ("stars", "plates", "quakes", "deposits",
                         "contours"), "", ""),
    Preset("miner", ("stars", "deposits", "mining", "osm_mines",
                     "infra_osm", "plants", "contours"), "", ""),
    Preset("hydrologist", ("stars", "currents", "contours"), "rain", ""),
    Preset("historian", ("stars", "grid"), "", "rumsey"),
    # Просьба автора от 11 октября 2026 года - «не забудь
    # разработчика». Сетка, здания и горизонтали - проверка геометрии
    # и высот своих данных, журнал - действием строки «Поиск».
    Preset("developer", ("stars", "grid", "buildings", "contours"), "", ""),
)
BY_KEY = dict((p.key, p) for p in PRESETS)


def changes(preset, managed, extras):
    """Строки, которые набор меняет: {ключ: включить}. managed - ключи
    строк, которыми наборы управляют, extras - нынешние флажки."""
    wanted = set(preset.extras)
    out = {}
    for key in managed:
        on = key in wanted
        if bool(extras.get(key)) != on:
            out[key] = on
    return out


def current(managed, extras, theme):
    """Ключ набора, с которым совпадает нынешнее состояние, или ""."""
    shown = set(key for key in managed if extras.get(key))
    for preset in PRESETS:
        if shown == set(preset.extras) & set(managed) \
                and (theme or "") == preset.theme:
            return preset.key
    return ""
