# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шторка слоёв проекта: слой слева, справа или на обеих сторонах.

Просьба автора от 27 октября 2026 года - сравнивать слои шторкой без
годов карт и шкалы времени. Слой «Слева» не рисуется правее шторки,
слой «Справа» - левее, прочие слои видны на обеих сторонах.
"""
import json

LEFT = "left"
RIGHT = "right"
SIDES = (LEFT, RIGHT)
NAMES_SHOWN = 2  # названий слоёв на бирке шторки, дальше «…»


def parse(text):
    """Стороны слоёв из строки JSON записи проекта: {номер: сторона}."""
    try:
        data = json.loads(text) if text else {}
    except ValueError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): v for k, v in data.items() if v in SIDES}


def dump(sides):
    return json.dumps({k: v for k, v in sides.items() if v in SIDES},
                      sort_keys=True)


def on_side(sides, layer_ids, side):
    """Номера слоёв из layer_ids на стороне side, в порядке layer_ids."""
    return [i for i in layer_ids if sides.get(i) == side]


def hidden(sides, layer_ids, side):
    """Номера слоёв, скрытых на стороне side, - слои другой стороны."""
    other = RIGHT if side == LEFT else LEFT
    return frozenset(on_side(sides, layer_ids, other))


def active(sides, layer_ids):
    """Есть ли среди слоёв хоть один слой со своей стороной."""
    return any(sides.get(i) in SIDES for i in layer_ids)


def label(names, empty):
    """Бирка стороны: названия слоёв, не больше NAMES_SHOWN, иначе
    empty - на стороне только общие слои и подоснова."""
    if not names:
        return empty
    text = ", ".join(names[:NAMES_SHOWN])
    return text + (", …" if len(names) > NAMES_SHOWN else "")
