# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Вид метки, как «Вид» метки Google Earth, без Qt.

Вид - пять чисел: широта и долгота точки взгляда, расстояние до неё
(«диапазон» Google Earth), азимут («курс») и наклон («угол обзора»).
Точка взгляда может не совпадать с меткой. Вид ставит «Снимок вида»
в меню метки или кнопка в окне свойств, по нему идут перелёт к метке
и остановка тура, он уходит в KML элементом LookAt. Решение автора
от 29 сентября 2026 года.

До того вид был только у меток «Сохранить вид» и хранился тремя
числами - расстояние, азимут, наклон, точкой взгляда была сама метка.
Такие виды читаются по-прежнему.

Слои вида - строки раздела «Слои» (ключ строки - включена ли), которые
перелёт к метке и остановка тура включают и выключают. Их запоминает
«Снимок текущего вида» окна свойств вместе с камерой. Просьба автора
от 16 октября 2026 года - остановка тура со своими слоями и временем
для показа.
"""
import json

MAX_TILT = 85.0
# Метка «Сохранить вид» стоит в точке своего вида. Доля градуса, до
# которой точки считаются одной.
SAME_POINT = 1e-7


def make(lat, lon, distance, heading=0.0, tilt=0.0):
    """Вид из пяти чисел с азимутом 0-360 и наклоном 0-MAX_TILT.
    None, если расстояние не больше нуля."""
    if distance <= 0.0:
        return None
    return (float(lat), float(lon), float(distance),
            float(heading) % 360.0, min(max(float(tilt), 0.0), MAX_TILT))


def parse(text, anchor=None):
    """Вид из поля файла меток. Три числа - прежний вид, его точка
    взгляда - anchor (широта, долгота метки). None при пустом или
    неверном поле."""
    try:
        values = [float(v) for v in str(text or "").split(",") if v.strip()]
    except ValueError:
        return None
    if len(values) == 5:
        return make(*values)
    if len(values) == 3 and anchor is not None:
        return make(anchor[0], anchor[1], *values)
    return None


def text(view):
    """Вид в поле файла меток, пустая строка без вида."""
    return ",".join(repr(float(v)) for v in view) if view else ""


def is_view_mark(kind, points, view):
    """Метка «Сохранить вид»: точка, которая стоит в точке своего вида.
    У неё в списке значок камеры."""
    if kind != "point" or not view or not points:
        return False
    lat, lon = points[0]
    return abs(lat - view[0]) < SAME_POINT and abs(lon - view[1]) < SAME_POINT


# Ключ состояния вида среди строк «Слоёв» начинается этим знаком:
# сектор разреза Земли, земля над подземной моделью, непрозрачности
# строк. Просьба автора от 17 октября 2026 года - остановка тура
# хранит и эти настройки. Прежний модуль такие ключи пропускает.
STATE = "@"
WEDGE = "@wedge"  # [запад, восток, юг, север], градусы
GROUND = "@ground"  # {"opacity": 0..1, "cut": bool, "under": bool}
OPACITY = "@opacity"  # {ключ строки: непрозрачность 0..1}


def _state_value(key, value):
    """Значение ключа состояния, годное для записи, иначе None."""
    if key == WEDGE:
        if isinstance(value, (list, tuple)) and len(value) == 4 \
                and all(isinstance(v, (int, float)) and
                        not isinstance(v, bool) for v in value):
            return [float(v) for v in value]
        return None
    if key == GROUND:
        if not isinstance(value, dict):
            return None
        out = {}
        if isinstance(value.get("opacity"), (int, float)) \
                and not isinstance(value.get("opacity"), bool):
            out["opacity"] = min(1.0, max(0.0, float(value["opacity"])))
        for name in ("cut", "under"):
            if isinstance(value.get(name), (bool, int)):
                out[name] = bool(value[name])
        return out or None
    if key == OPACITY:
        if not isinstance(value, dict):
            return None
        out = {str(k): min(1.0, max(0.0, float(v)))
               for k, v in value.items()
               if isinstance(v, (int, float)) and not isinstance(v, bool)}
        return out or None
    return None


def layers_text(layers):
    """Слои вида в поле файла меток - JSON {ключ: 0 или 1} и ключи
    состояния вида STATE, пустая строка без слоёв."""
    if not layers:
        return ""
    out = {}
    for key, value in sorted(layers.items()):
        key = str(key)
        if key.startswith(STATE):
            value = _state_value(key, value)
            if value is not None:
                out[key] = value
        else:
            out[key] = int(bool(value))
    return json.dumps(out, separators=(",", ":")) if out else ""


def layers_parse(text):
    """Слои вида из поля файла меток или KML, None при пустом или
    неверном поле."""
    try:
        data = json.loads(text) if text else None
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    out = {}
    for key, value in data.items():
        key = str(key)
        if key.startswith(STATE):
            value = _state_value(key, value)
            if value is not None:
                out[key] = value
        elif isinstance(value, (bool, int)):
            out[key] = bool(value)
    return out or None


def switches(layers):
    """Только строки «Слоёв» {ключ: включена}, без состояния вида."""
    return {k: v for k, v in (layers or {}).items()
            if not str(k).startswith(STATE)}
