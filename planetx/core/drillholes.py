# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скважины: устья, интервалы, инклинометрия, ствол. Расчёт без Qt.

Подшаг 4.1 плана фазы 3 (doc/PLAN_PHASE3.md). Разметка данных - как
у Isoliner (grid_isolines/drillhole_core.py), устройство взято
образцом, общего кода нет.

- Устье (collar) - точка с полями hole_id, z (отметка устья), eoh
  (глубина забоя по стволу).
- Интервал (interval) - таблица hole_id, from, to (глубины по стволу,
  вниз положительные), code (пласт, литология). Прочие поля
  сохраняются.
- Инклинометрия (survey) - hole_id, md (глубина по стволу), azimuth,
  угол наклона. Без инклинометрии скважина вертикальная.

Строки приходят словарями «имя поля - значение». Имена полей ищутся
по синонимам без учёта регистра, FIELDS.

Ствол - метод минимальной кривизны: между станциями ствол идёт
по дуге окружности, приращения умножаются на коэффициент
rf = 2 / β · tg(β / 2), β - угол между направлениями станций.
Дуга делится на части не больше ARC_STEP, так ломаная ствола не
срезает дугу. Выше первой станции ствол идёт по её направлению,
ниже последней - по её направлению до забоя.

Угол наклона приводится к зениту, 0 - вниз отвесно. Поле zenith,
inc, inclination - уже зенит. Поле dip - угол от горизонта:
отрицательные значения (-90 - вниз отвесно) дают зенит 90 + dip,
положительные с медианой больше 45 - зенит 90 - dip, иначе значения
считаются зенитом. Правило взято у Isoliner (to_zenith).
"""
import hashlib
import math
from collections import namedtuple

import numpy as np

# Роль поля - имена-синонимы в порядке предпочтения.
FIELDS = {
    "hole_id": ("hole_id", "bhid", "dhid", "well", "holeid", "hole"),
    "z": ("z", "elev", "elevation", "rl", "collar_z"),
    "eoh": ("eoh", "td", "max_depth", "total_depth", "depth"),
    "from": ("from", "from_m", "depth_from"),
    "to": ("to", "to_m", "depth_to"),
    "code": ("code", "litho", "lith", "geol", "seam", "class"),
    "md": ("md", "depth", "at"),
    "azimuth": ("azimuth", "azi", "az", "brg", "bearing"),
    "angle": ("zenith", "inc", "inclination", "dip"),
}
ZENITH_NAMES = ("zenith", "inc", "inclination")
ARC_STEP = math.radians(3.0)  # наибольший угол части дуги ствола

Hole = namedtuple("Hole", "hole_id x y z eoh axis intervals")
Hole.__doc__ = """Скважина. x, y - положение устья, как пришло из слоя,
z - отметка устья, eoh - глубина забоя по стволу. axis - узлы ствола,
массив (n, 4): глубина по стволу, смещение на восток, на север
от устья в метрах, отметка. intervals - список Interval."""

Interval = namedtuple("Interval", "start end code extra")


def find_field(names, role):
    """Имя поля роли role среди names или None. Без учёта регистра,
    синонимы - FIELDS[role] по порядку."""
    lower = {str(n).lower(): n for n in names}
    for name in FIELDS[role]:
        if name in lower:
            return lower[name]
    return None


def _number(value):
    """Число или None для пустых и нечисловых значений."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _key(value):
    """Номер скважины строкой: 12 и 12.0 из разных таблиц совпадают."""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def zeniths(values, name):
    """Углы наклона поля name в зениты, градусы. 0 - вниз отвесно."""
    values = np.asarray(values, dtype=np.float64)
    if str(name).lower() in ZENITH_NAMES or not len(values):
        return values
    if np.nanmin(values) < 0.0:
        return 90.0 + values
    if np.nanmedian(values) > 45.0:
        return 90.0 - values
    return values


def _direction(zenith, azimuth):
    """Единичное направление ствола (восток, север, вниз), радианы."""
    return np.array([math.sin(zenith) * math.sin(azimuth),
                     math.sin(zenith) * math.cos(azimuth),
                     math.cos(zenith)])


def _slerp(a, b, share):
    """Направление на доле share дуги от a к b."""
    dot = float(np.clip(np.dot(a, b), -1.0, 1.0))
    angle = math.acos(dot)
    if angle < 1e-9:
        return a
    return (math.sin((1.0 - share) * angle) * a
            + math.sin(share * angle) * b) / math.sin(angle)


def _arc_step(start, t1, t2, length):
    """Приращение (восток, север, вниз) по минимальной кривизне между
    направлениями t1 и t2 на длине ствола length."""
    beta = math.acos(float(np.clip(np.dot(t1, t2), -1.0, 1.0)))
    rf = 1.0 if beta < 1e-9 else 2.0 / beta * math.tan(beta / 2.0)
    return start + length / 2.0 * (t1 + t2) * rf


def axis(z, eoh, stations=()):
    """Узлы ствола: массив (n, 4) - md, восток, север, отметка.

    stations - (md, зенит, азимут) в градусах, по возрастанию md.
    Пустой список - вертикальная скважина до eoh."""
    stations = sorted((float(md), math.radians(zen), math.radians(az))
                      for md, zen, az in stations)
    if not stations:
        return np.array([[0.0, 0.0, 0.0, z], [eoh, 0.0, 0.0, z - eoh]])
    first = _direction(stations[0][1], stations[0][2])
    nodes = [(0.0, np.zeros(3))]
    position = np.zeros(3)
    md = 0.0
    if stations[0][0] > 0.0:
        md = min(stations[0][0], eoh)
        position = first * md
        nodes.append((md, position))
    for (m1, z1, a1), (m2, z2, a2) in zip(stations, stations[1:]):
        if m1 >= eoh:
            break
        m2 = min(m2, eoh)
        t1, t2 = _direction(z1, a1), _direction(z2, a2)
        beta = math.acos(float(np.clip(np.dot(t1, t2), -1.0, 1.0)))
        parts = max(1, int(math.ceil(beta / ARC_STEP)))
        for k in range(parts):
            a = _slerp(t1, t2, k / parts)
            b = _slerp(t1, t2, (k + 1) / parts)
            position = _arc_step(position, a, b, (m2 - m1) / parts)
            md = m1 + (m2 - m1) * (k + 1) / parts
            nodes.append((md, position))
    if md < eoh:
        last = _direction(stations[-1][1], stations[-1][2])
        position = position + last * (eoh - md)
        nodes.append((eoh, position))
    out = np.array([[m, p[0], p[1], z - p[2]] for m, p in nodes])
    # Повторные глубины - от станций на одной глубине.
    keep = np.concatenate([[True], np.diff(out[:, 0]) > 1e-9])
    return out[keep]


def point_at(nodes, md):
    """Точка ствола (восток, север, отметка) на глубине md. За забоем
    ствол продолжается по последнему отрезку."""
    m = nodes[:, 0]
    if md <= m[0]:
        return nodes[0, 1:].copy()
    i = int(np.searchsorted(m, md))
    if i >= len(m):
        i = len(m) - 1
    a, b = nodes[i - 1], nodes[i]
    share = (md - a[0]) / (b[0] - a[0]) if b[0] > a[0] else 0.0
    return a[1:] + (b[1:] - a[1:]) * share


def piece(nodes, start, end):
    """Узлы ствола между глубинами start и end, с концами: (k, 3)."""
    inner = nodes[(nodes[:, 0] > start) & (nodes[:, 0] < end), 1:]
    return np.vstack([point_at(nodes, start), inner, point_at(nodes, end)])


def code_color(code, palette=None):
    """Цвет кода пласта (r, g, b). palette - словарь код - цвет
    «#rrggbb», иначе цвет из хэша кода, один и тот же у кода всегда."""
    if palette and code in palette:
        text = palette[code].lstrip("#")
        return tuple(int(text[i:i + 2], 16) for i in (0, 2, 4))
    digest = hashlib.md5(str(code).encode("utf-8")).digest()
    hue = digest[0] / 255.0
    r, g, b = _hsv(hue, 0.55 + digest[1] / 255.0 * 0.35,
                   0.70 + digest[2] / 255.0 * 0.25)
    return (int(r * 255), int(g * 255), int(b * 255))


def _hsv(h, s, v):
    i = int(h * 6.0) % 6
    f = h * 6.0 - int(h * 6.0)
    p, q, t = v * (1 - s), v * (1 - s * f), v * (1 - s * (1 - f))
    return ((v, t, p), (q, v, p), (p, v, t), (p, q, v), (t, p, v),
            (v, p, q))[i]


def assemble(collars, intervals=(), surveys=()):
    """Скважины из строк таблиц. collars - словари полей устья, у
    каждого ещё ключи "x" и "y" - положение из геометрии слоя.
    Возвращает (скважины, сводка пропусков - словарь причина - число).
    """
    skipped = {}

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    collars = list(collars)
    names = collars[0].keys() if collars else ()
    f_id, f_z, f_eoh = (find_field(names, r)
                        for r in ("hole_id", "z", "eoh"))
    # Станции инклинометрии по скважинам.
    surveys = list(surveys)
    by_hole = {}
    if surveys:
        names = surveys[0].keys()
        s_id, s_md, s_az, s_angle = (find_field(names, r) for r in
                                     ("hole_id", "md", "azimuth", "angle"))
        if None in (s_id, s_md, s_az, s_angle):
            skip("survey_fields")
        else:
            rows = [(_key(r[s_id]), _number(r[s_md]), _number(r[s_az]),
                     _number(r[s_angle])) for r in surveys]
            rows = [r for r in rows if None not in r]
            zen = zeniths([r[3] for r in rows], s_angle)
            for (hole, md, az, _), z in zip(rows, zen):
                by_hole.setdefault(hole, {})[md] = (md, z, az)
    # Интервалы по скважинам.
    intervals = list(intervals)
    parts = {}
    if intervals:
        names = intervals[0].keys()
        i_id, i_from, i_to, i_code = (find_field(names, r) for r in
                                      ("hole_id", "from", "to", "code"))
        for row in intervals:
            start, end = _number(row.get(i_from)), _number(row.get(i_to))
            if i_id is None or start is None or end is None:
                skip("interval_fields")
                continue
            if end < start:
                start, end = end, start
                skip("interval_swapped")
            if end == start:
                skip("interval_empty")
                continue
            extra = {k: v for k, v in row.items()
                     if k not in (i_id, i_from, i_to, i_code)}
            code = row.get(i_code) if i_code else None
            parts.setdefault(_key(row[i_id]), []).append(
                Interval(start, end, "" if code is None else str(code),
                         extra))
    holes = []
    seen = set()
    for row in collars:
        hole = _key(row.get(f_id)) if f_id else None
        z = _number(row.get(f_z)) if f_z else None
        if not hole or z is None:
            skip("collar_fields")
            continue
        own = sorted(parts.get(hole, []), key=lambda p: (p.start, p.end))
        eoh = _number(row.get(f_eoh)) if f_eoh else None
        deepest = max((p.end for p in own), default=0.0)
        if eoh is None or eoh < deepest:
            eoh = deepest
        if eoh <= 0.0:
            skip("collar_no_depth")
            continue
        stations = list(by_hole.get(hole, {}).values())
        holes.append(Hole(hole, row.get("x"), row.get("y"), z, eoh,
                          axis(z, eoh, stations), own))
        seen.add(hole)
    for hole in parts:
        if hole not in seen:
            skip("interval_no_collar")
    return holes, skipped
