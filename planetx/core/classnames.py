# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Названия классов трассировки от ИИ-помощника.

Вариант В, выбор автора от 3 ноября 2026 года: помощник получает таблицу
классов - средние значения каналов с их ролями, долю участка, количество
и средний размер областей, место и месяц съёмки, название по правилам
окна «Выделение объектов», если оно есть, - и предлагает названия.
Снимок, имена слоёв и файлов в модель не уходят. Ответ - JSON
{"names": [...]} по порядку классов, названия правятся в таблице.

Запрос один, без инструментов и разговора (ui/assistant.py complete).
"""
import json
import re

ROLE_NAMES = {"blue": "синий", "green": "зелёный", "red": "красный",
              "nir": "ближний ИК", "swir1": "SWIR 1,6 мкм",
              "swir2": "SWIR 2,2 мкм", "coastal": "береговой",
              "re1": "край красного 1", "re2": "край красного 2",
              "re3": "край красного 3", "vapour": "водяной пар",
              "thermal": "тепловой, K"}
NAME_LIMIT = 40  # знаков в названии, длиннее обрезается


def system_text(language):
    """Системная подсказка: дешифровщик снимка, ответ только JSON."""
    lang = "русском" if language == "ru" else "английском"
    return (
        "Ты помогаешь дешифрировать снимок Земли. Тебе дают классы цветов, "
        "на которые трассировка разложила участок снимка: средние значения "
        "каналов, долю участка, количество и средний размер областей. "
        "Назови, что вероятнее всего изображает каждый класс, - вода, "
        "хвойный лес, лиственный лес, луг, посевы, пашня, рубка, гарь, "
        "застройка, дорога, болото, снег, облака, тень и подобное. "
        "Учитывай роли каналов и место съёмки. Если два класса - одно и "
        "то же, дай им одно название. Если не понять, напиши «неясно». "
        "Названия - на {} языке, от одного до трёх слов. Ответь только "
        "JSON вида {{\"names\": [\"...\", ...]}} - по названию на класс "
        "в том же порядке, без пояснений.".format(lang))


def _number(value):
    if abs(value) >= 10:
        return "{:.1f}".format(value)
    return "{:.3f}".format(value)


def question(rows, roles, units, place=None, month=None):
    """Текст вопроса. rows - классы по порядку: {"means": [значения по
    каналам], "share": доля участка, "regions": областей, "area_ha":
    средняя область, "rule": название по правилам или None}. roles -
    роли каналов или None, units - что за значения («отражение 0-1»,
    «яркость 0-255»). place - (широта, долгота), month - месяц."""
    lines = []
    if place is not None:
        lines.append("Место - широта {:.2f}°, долгота {:.2f}°.".format(
            *place))
    if month is not None:
        lines.append("Месяц съёмки - {}.".format(month))
    count = len(rows[0]["means"]) if rows else 0
    names = [ROLE_NAMES.get(r, r) if r else "канал {}".format(n + 1)
             for n, r in enumerate((roles or [None] * count)[:count])]
    names += ["канал {}".format(n + 1) for n in range(len(names), count)]
    lines.append("Каналы - {}. Значения - {}.".format(", ".join(names),
                                                      units))
    for n, row in enumerate(rows, 1):
        text = "Класс {} - {}, доля участка {:.0f} %, областей {}, " \
               "средняя область {} га".format(
                   n, ", ".join(_number(v) for v in row["means"]),
                   100.0 * row["share"], row["regions"],
                   _number(row["area_ha"]))
        if row.get("rule"):
            text += ", по правилам отражения - {}".format(row["rule"])
        lines.append(text + ".")
    return "\n".join(lines)


def _json_at(text, start):
    """Значение JSON с места start или None, если там не JSON."""
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except ValueError:
        return None


def parse_names(text, count):
    """Названия из ответа модели: список count строк или None. Берётся
    первый объект JSON с полем names или первый список строк."""
    if not text:
        return None
    found = None
    for match in re.finditer(r"[\[{]", text):
        value = _json_at(text, match.start())
        if isinstance(value, dict):
            value = value.get("names")
        if isinstance(value, list) and value \
                and all(isinstance(v, str) for v in value):
            found = value
            break
    if found is None or len(found) < count:
        return None
    return [name.strip()[:NAME_LIMIT] for name in found[:count]]
