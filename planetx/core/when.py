# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Время меток, как TimeStamp и TimeSpan в KML Google Earth. Без Qt.

Время метки - пара строк (начало, конец) в записи KML, dateTime
XML Schema: «2026», «2026-09», «2026-09-30», «2026-09-30T12:00:00Z»,
с поясом «+05:00» или без. Момент - начало и конец одинаковые.
Пустая строка - открытый край промежутка. Строки хранятся как есть,
так файл Google Earth проходит туда и обратно без потерь. Для шкалы
времени строка переводится в секунды от 1970 года UTC. Время без пояса
считается UTC.

Время своё у метки и у её вида. Шкала времени глобуса своя, на
«Временный контроллер» QGIS она не опирается, решение автора от
30 сентября 2026 года.
"""
import calendar
import math
import re
import time as _time

_DATE = re.compile(
    r"^\s*(-?\d{4})(?:-(\d{2})(?:-(\d{2})(?:[T ](\d{2}):(\d{2})"
    r"(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?)?)?)?\s*$")


def parse(text):
    """Секунды от 1970 года UTC или None для пустой и неверной строки.
    Неполная дата - начало своего года, месяца или дня."""
    if not text:
        return None
    found = _DATE.match(str(text))
    if not found:
        return None
    year, month, day, hour, minute, second, fraction, zone = found.groups()
    try:
        month = int(month or 1)
        day = int(day or 1)
        if not (1 <= month <= 12 and 1 <= day <= 31):
            return None
        seconds = calendar.timegm((int(year), month, day, int(hour or 0),
                                   int(minute or 0), int(second or 0)))
    except (ValueError, OverflowError):
        return None
    if fraction:
        seconds += float("0." + fraction)
    if zone and zone != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        seconds -= sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return float(seconds)


def text(seconds):
    """Строка KML «2026-09-30T12:00:00Z» из секунд."""
    return _time.strftime("%Y-%m-%dT%H:%M:%SZ",
                          _time.gmtime(math.floor(seconds)))


def stamp(when):
    """Время-момент: пара одинаковых строк."""
    return (when, when)


def is_stamp(time):
    return time is not None and time[0] == time[1] and bool(time[0])


def interval(time):
    """Промежуток в секундах (от, до). None - время не задано,
    открытый край - бесконечность."""
    if not time or not (time[0] or time[1]):
        return None
    lo = parse(time[0])
    hi = parse(time[1])
    if lo is None and hi is None:
        return None
    return (lo if lo is not None else -math.inf,
            hi if hi is not None else math.inf)


def visible(time, lo, hi):
    """Видна ли метка со временем time в окне шкалы (lo, hi). Метка
    без времени видна всегда, как в Google Earth."""
    span = interval(time)
    if span is None:
        return True
    return span[0] <= hi and span[1] >= lo


def extent(times):
    """Охват шкалы по временам меток: (самое раннее, самое позднее)
    или None, если ни у кого нет конечного времени."""
    values = []
    for time in times:
        span = interval(time)
        if span is None:
            continue
        values.extend(v for v in span if math.isfinite(v))
    if not values:
        return None
    return min(values), max(values)


def pack(time):
    """Запись для поля файла: «начало/конец», момент - одна дата."""
    if not time or not (time[0] or time[1]):
        return ""
    if time[0] == time[1]:
        return time[0]
    return "{}/{}".format(time[0] or "", time[1] or "")


def unpack(value):
    """Обратно из поля файла: пара строк или None."""
    value = (value or "").strip()
    if not value:
        return None
    if "/" in value:
        begin, end = value.split("/", 1)
        return (begin.strip(), end.strip())
    return (value, value)
