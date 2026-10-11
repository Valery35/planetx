# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подводные кабели OpenStreetMap в data/cables.json.

    $PY tools/build_cables.py ПАПКА

ПАПКА - ответы Overpass в JSON с геометрией (out geom tags):
telecom.json - линии связи под водой (communication=line или
telecom=line с location underwater или submarine, communication=line
с submarine=yes), power.json - силовые кабели под водой (power=cable
с location underwater или submarine). Данные OpenStreetMap под ODbL,
файл модуля - производная база под той же лицензией, doc/SOURCES.md.

Линии упрощаются методом Дугласа-Пекера с допуском TOLERANCE градусов,
координаты округляются до 0.001°. Силовые кабели короче MIN_POWER км
отбрасываются - это переходы через реки и протоки, они есть в строке
«ЛЭП, кабели и трубопроводы OSM» у вида.
"""
import datetime
import json
import math
import os
import sys

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "planetx", "data", "cables.json")
TOLERANCE = 0.005  # градусы, около 500 м
MIN_POWER = 5.0  # км


def length_km(points):
    total = 0.0
    for (la1, lo1), (la2, lo2) in zip(points, points[1:]):
        p1, p2 = math.radians(la1), math.radians(la2)
        dl = math.radians(lo2 - lo1)
        h = math.sin((p2 - p1) / 2) ** 2 \
            + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        total += 2 * 6371.0 * math.asin(min(1.0, math.sqrt(h)))
    return total


def simplify(points, tolerance):
    """Дуглас-Пекер на плоскости широты и долготы, без рекурсии."""
    if len(points) < 3:
        return list(points)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        first, last = stack.pop()
        (y1, x1), (y2, x2) = points[first], points[last]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy)
        worst, index = -1.0, None
        for i in range(first + 1, last):
            y, x = points[i]
            if norm == 0.0:
                d = math.hypot(x - x1, y - y1)
            else:
                d = abs(dy * (x - x1) - dx * (y - y1)) / norm
            if d > worst:
                worst, index = d, i
        if index is not None and worst > tolerance:
            keep[index] = True
            stack.append((first, index))
            stack.append((index, last))
    return [p for p, k in zip(points, keep) if k]


def lines(path, kind):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    out = []
    for element in data.get("elements", ()):
        geometry = element.get("geometry") or []
        points = [(g["lat"], g["lon"]) for g in geometry if g]
        if len(points) < 2:
            continue
        if kind == "power" and length_km(points) < MIN_POWER:
            continue
        tags = element.get("tags") or {}
        points = simplify(points, TOLERANCE)
        out.append({
            "kind": kind,
            "name": tags.get("name") or tags.get("name:en") or "",
            "operator": tags.get("operator") or "",
            "voltage": tags.get("voltage") or "",
            "osm": "way/{}".format(element.get("id")),
            "points": [[round(la, 3), round(lo, 3)] for la, lo in points]})
    return out


def main(folder):
    cables = lines(os.path.join(folder, "telecom.json"), "telecom") \
        + lines(os.path.join(folder, "power.json"), "power")
    data = {"date": datetime.date.today().isoformat(), "cables": cables}
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    kinds = {}
    for c in cables:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    print(kinds, os.path.getsize(OUT) // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1])
