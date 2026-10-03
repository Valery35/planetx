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

Годы до нашей эры пишутся со знаком, как в XML Schema 1.0: «-0264» -
264 год до н. э., нулевого года нет. Календарь - пролептический
григорианский, счёт дней свой: calendar и time.gmtime таких дат
не берут.

Время своё у метки и у её вида. Шкала времени глобуса своя, на
«Временный контроллер» QGIS она не опирается, решение автора от
30 сентября 2026 года.
"""
import math
import re

_DATE = re.compile(
    r"^\s*(-?\d{4})(?:-(\d{2})(?:-(\d{2})(?:[T ](\d{2}):(\d{2})"
    r"(?::(\d{2})(?:\.(\d+))?)?\s*(Z|[+-]\d{2}:?\d{2})?)?)?)?\s*$")


def _days(year, month, day):
    """Дней от 1 января 1970 года до даты. Год астрономический:
    0 - это 1 год до н. э."""
    y = year - (month <= 2)
    era = y // 400
    yoe = y - era * 400
    doy = (153 * (month + (-3 if month > 2 else 9)) + 2) // 5 + day - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def civil(seconds):
    """Дата и время UTC: (год, месяц, день, час, минута, секунда).
    Год астрономический: 0 - это 1 год до н. э., -263 - 264 год
    до н. э."""
    days, rest = divmod(int(math.floor(seconds)), 86400)
    z = days + 719468
    era = z // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    day = doy - (153 * mp + 2) // 5 + 1
    month = mp + (3 if mp < 10 else -9)
    year = yoe + era * 400 + (month <= 2)
    return (year, month, day, rest // 3600, rest % 3600 // 60, rest % 60)


def parse(text):
    """Секунды от 1970 года UTC или None для пустой и неверной строки.
    Неполная дата - начало своего года, месяца или дня."""
    if not text:
        return None
    found = _DATE.match(str(text))
    if not found:
        return None
    year, month, day, hour, minute, second, fraction, zone = found.groups()
    year = int(year)
    if year < 0:
        # «-0264» - 264 год до н. э., астрономический год -263.
        year += 1
    month = int(month or 1)
    day = int(day or 1)
    hour = int(hour or 0)
    minute = int(minute or 0)
    second = int(second or 0)
    if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 24
            and minute <= 59 and second <= 61):
        return None
    seconds = _days(year, month, day) * 86400 + hour * 3600 \
        + minute * 60 + second
    if fraction:
        seconds += float("0." + fraction)
    if zone and zone != "Z":
        sign = -1 if zone[0] == "-" else 1
        digits = zone[1:].replace(":", "")
        seconds -= sign * (int(digits[:2]) * 3600 + int(digits[2:]) * 60)
    return float(seconds)


def text(seconds):
    """Строка KML «2026-09-30T12:00:00Z» из секунд."""
    year, month, day, hour, minute, second = civil(seconds)
    era = "%04d" % year if year > 0 else "-%04d" % (1 - year)
    return "%s-%02d-%02dT%02d:%02d:%02dZ" % (era, month, day, hour,
                                            minute, second)


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


def share(time, moment):
    """Доля промежутка time, прошедшая к моменту moment, от 0 до 1.
    Без конечного начала и конца - 1: расти нечему."""
    span = interval(time)
    if span is None or not (math.isfinite(span[0])
                            and math.isfinite(span[1])) \
            or span[1] <= span[0]:
        return 1.0
    return min(max((moment - span[0]) / (span[1] - span[0]), 0.0), 1.0)


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
