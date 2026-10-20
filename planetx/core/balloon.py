# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Шаблон всплывающего окна метки - BalloonStyle KML, без Qt.

Текст шаблона - HTML с местами $[...], как у Google Earth: $[name] -
название, $[description] - описание, $[поле] - значение поля объекта
(ExtendedData), $[поле/displayName] - подпись поля. Неизвестное место
и $[geDirections] дают пустую строку. Значения полей и название
экранируются, описание - HTML метки, оно вставляется как есть.
Просьба автора от 20 октября 2026 года, недостающее из спецификации
KML.
"""
import html
import re

_PLACE = re.compile(r"\$\[([^\]]+)\]")


def fill(template, name="", description="", data=None):
    """HTML окна метки по шаблону template."""
    values = {}
    for key, value in data or ():
        values.setdefault(str(key), str(value))

    def one(match):
        key = match.group(1).strip()
        if key == "name":
            return html.escape(name or "")
        if key == "description":
            return description or ""
        if key.endswith("/displayName"):
            field = key[:-len("/displayName")]
            return html.escape(field) if field in values else ""
        if key in values:
            return html.escape(values[key])
        return ""

    return _PLACE.sub(one, template or "")
