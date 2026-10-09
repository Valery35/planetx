# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проект Pythagoras (.pyt): слои и объекты. Расчёт без Qt.

Просьба автора от 9 октября 2026 года. Формат закрыт, разбор выведен
по файлу пользователя и экспорту SHP самого Pythagoras.

Файл - поток помеченных полей. Байт метки - вид в двух старших битах
и номер поля в шести младших:
    00 - запись, дальше количество полей (varint) и сами поля
    01 - целое varint (LEB128)
    10 - double, 8 байт little-endian
    11 - строка или байты, дальше длина (varint) и содержимое

Объект - запись, первое поле которой - шапка 1: 1 - номер объекта,
3 - код (текст), 8 - номер слоя (без поля - слой 0), 9 - цвет,
10 - внутренний номер. Таблица слоёв - запись 5 {41, 02 {...}}, номер
слоя - место имени в массиве 02.

Виды объектов (номер поля записи):
    1  точка - 5 {1 x, 2 y}, 6 z, 7 {1 знак, 0 - точка построения}
    2  отрезок - 5, 6 - номера концевых точек, 7, 8 - их координаты
    3  площадь - 20 {2 - номера кольца, uint32}, 10 - площадь
    4  надпись - 15 {1 x, 2 y}, 20 текст
    6  дуга - 6 {центр}, 7, 8 - номера концевых точек, 9 - радиус
    16 кривая - 7, 8 - концы, 10 {.. 2 {x, y}} - вершины
В кольце площади номер дуги стоит между номерами её концевых точек.
"""
import math
import re
import struct

# Виды объектов по номеру поля записи.
KINDS = {1: "point", 2: "segment", 3: "area", 4: "text", 6: "arc",
         16: "curve"}
# Точек на полный оборот дуги.
ARC_STEPS = 72
# Запись длиннее MAX_COUNT полей - не запись, а случайные байты.
MAX_COUNT = 1000000
# Начало записи объекта: вид, количество полей, шапка 1. Просмотр
# вперёд - кандидаты перекрываются, ложное совпадение не должно
# поглотить начало настоящей записи.
_START = re.compile(
    b"(?=[\x01\x02\x03\x04\x06\x10][\x80-\xff]{0,3}[\x00-\x7f]\x01)")


class Bad(Exception):
    """Байты не складываются в запись."""


def _varint(raw, pos):
    out = 0
    shift = 0
    while True:
        if pos >= len(raw):
            raise Bad("eof")
        b = raw[pos]
        pos += 1
        out |= (b & 0x7F) << shift
        if b < 0x80:
            return out, pos
        shift += 7
        if shift > 63:
            raise Bad("varint")


def node(raw, pos, depth=0):
    """(номер поля, значение, следующая позиция). Значение записи -
    список пар (поле, значение), строки - байты."""
    if depth > 40:
        raise Bad("deep")
    if pos >= len(raw):
        raise Bad("eof")
    tag = raw[pos]
    kind, field = tag >> 6, tag & 0x3F
    pos += 1
    if kind == 0:
        count, pos = _varint(raw, pos)
        if count > MAX_COUNT:
            raise Bad("count")
        kids = []
        for _ in range(count):
            f, v, pos = node(raw, pos, depth + 1)
            kids.append((f, v))
        return field, kids, pos
    if kind == 1:
        v, pos = _varint(raw, pos)
        return field, v, pos
    if kind == 2:
        if pos + 8 > len(raw):
            raise Bad("eof")
        return field, struct.unpack_from("<d", raw, pos)[0], pos + 8
    n, pos = _varint(raw, pos)
    if pos + n > len(raw):
        raise Bad("eof")
    return field, bytes(raw[pos:pos + n]), pos + n


def _get(kids, field, default=None):
    if not isinstance(kids, list):
        return default
    for f, v in kids:
        if f == field:
            return v
    return default


def _xy(kids):
    x = _get(kids, 1)
    y = _get(kids, 2)
    if isinstance(x, float) and isinstance(y, float):
        return x, y
    return None


def text(b):
    """Строка из байтов UTF-8 или cp1251, иначе None."""
    if not isinstance(b, bytes):
        return None
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("cp1251", errors="replace")


def _try_node(raw, pos):
    """node или None, если байты с pos не складываются в запись."""
    try:
        return node(raw, pos)
    except (Bad, RecursionError):
        return None


def read_layers(raw):
    """{номер слоя: имя} из таблицы слоёв."""
    mark = b"\x05\x03\x41"
    i = raw.find(mark)
    while i >= 0:
        found = _try_node(raw, i)
        arr = _get(found[1], 2) if found else None
        if isinstance(arr, list) and len(arr) > 100:
            out = {}
            for n, (_, e) in enumerate(arr):
                if isinstance(e, list) and e:
                    name = text(e[0][1])
                    if name:
                        out[n] = name
            return out
        i = raw.find(mark, i + 1)
    return {}


def _header(kids):
    if not kids:
        return None
    f, h = kids[0]
    if f != 1 or not isinstance(h, list):
        return None
    out = {}
    for k, v in h:
        if isinstance(v, list):
            return None
        out[k] = v
    return out if 1 in out and 10 in out else None


def read_objects(raw):
    """Список (вид, шапка, поля) всех объектов файла."""
    out = []
    pos = 0
    for m in _START.finditer(raw):
        found = None if m.start() < pos else _try_node(raw, m.start())
        if found is None:
            continue
        f, kids, end = found
        h = _header(kids)
        if h is not None:
            out.append((KINDS[f], h, kids))
            pos = end
    return out


def arc_points(center, radius, a, b):
    """Точки дуги от a до b против часовой стрелки."""
    t0 = math.atan2(a[1] - center[1], a[0] - center[0])
    t1 = math.atan2(b[1] - center[1], b[0] - center[0])
    while t1 <= t0:
        t1 += 2 * math.pi
    k = max(2, int(ARC_STEPS * (t1 - t0) / (2 * math.pi)))
    return [(center[0] + radius * math.cos(t0 + (t1 - t0) * i / k),
             center[1] + radius * math.sin(t0 + (t1 - t0) * i / k))
            for i in range(k + 1)]


def ring(nums, points, arcs):
    """Кольцо площади по номерам точек и дуг, None - номер не найден."""
    out = []
    for i, n in enumerate(nums):
        if n in points:
            out.append(points[n][0])
            continue
        arc = arcs.get(n)
        if arc is None or i == 0 or i + 1 >= len(nums):
            return None
        c, r, a, b = arc
        if a not in points or b not in points:
            return None
        bend = arc_points(c, r, points[a][0], points[b][0])
        if nums[i - 1] == b:
            bend = bend[::-1]
        out.extend(bend[1:-1])
    return out


def _curve(kids):
    pts = [_xy(_get(kids, 7))]
    for f, v in kids:
        if f == 10 and isinstance(v, list):
            pts.extend(_xy(p) for k, p in v if k == 2)
    pts.append(_xy(_get(kids, 8)))
    return [p for p in pts if p]


def features(raw):
    """(слои, объекты, площадей без кольца).

    Объект - словарь: kind - point, line, polygon или text, layer -
    номер слоя, id - номер Pythagoras, code, color, z и symbol у точки,
    area у площади, text у надписи, coords - список (x, y).
    """
    layers = read_layers(raw)
    objs = read_objects(raw)
    points = {}
    arcs = {}
    for kind, h, kids in objs:
        if kind == "point":
            xy = _xy(_get(kids, 5))
            z = _get(kids, 6)
            if xy:
                points[h[1]] = (xy, z if isinstance(z, float) else None)
        elif kind == "arc":
            c = _xy(_get(kids, 6))
            r = _get(kids, 9)
            if c and isinstance(r, float):
                arcs[h[1]] = (c, r, _get(kids, 7), _get(kids, 8))
    out = []
    lost = 0
    for kind, h, kids in objs:
        rec = {"id": h[1], "layer": h.get(8, 0), "code": text(h.get(3)),
               "color": h.get(9)}
        if kind == "point" and h[1] in points:
            xy, z = points[h[1]]
            look = _get(kids, 7)
            rec.update(kind="point", coords=[xy], z=z,
                       symbol=_get(look, 1, 1))
        elif kind == "segment":
            a, b = _xy(_get(kids, 7)), _xy(_get(kids, 8))
            if not (a and b):
                continue
            rec.update(kind="line", coords=[a, b])
        elif kind == "curve":
            pts = _curve(kids)
            if len(pts) < 2:
                continue
            rec.update(kind="line", coords=pts)
        elif kind == "arc" and h[1] in arcs:
            c, r, a, b = arcs[h[1]]
            if a not in points or b not in points:
                continue
            rec.update(kind="line", coords=arc_points(
                c, r, points[a][0], points[b][0]))
        elif kind == "area":
            ids = _get(_get(kids, 20), 2)
            pts = None
            if isinstance(ids, bytes) and len(ids) >= 16:
                nums = struct.unpack("<%dI" % (len(ids) // 4),
                                     ids[:len(ids) // 4 * 4])
                pts = ring(nums, points, arcs)
            if not pts or len(pts) < 4:
                lost += 1
                continue
            area = _get(kids, 10)
            rec.update(kind="polygon", coords=pts,
                       area=area if isinstance(area, float) else None)
        elif kind == "text":
            xy = _xy(_get(kids, 15))
            if not xy:
                continue
            rec.update(kind="text", coords=[xy],
                       text=text(_get(kids, 20)))
        else:
            continue
        out.append(rec)
    return layers, out, lost
