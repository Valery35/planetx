# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Границы литосферных плит PB2002 в data/plates.json.

    $PY tools/build_plates.py ПАПКА

ПАПКА - GeoJSON из github.com/fraxen/tectonicplates (Hugo Ahlenius,
Nordpil, по модели Peter Bird 2003, Open Data Commons Attribution 1.0):
PB2002_steps.json и PB2002_plates.json.

Шаги границы (STEPCLASS, VELOCITYLE) склеиваются в линии по паре плит,
классу шага и непрерывности концов. На линии глобуса шаги лежат
своими концами, координаты округляются до 0.001°. Скорость линии -
средняя по длине шагов, мм/год. Подписи плит - точка внутри
многоугольника плиты, ближайшая к центру тяжести его вершин.
"""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "planetx", "core"))

import plates  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "planetx", "data", "plates.json")
JOIN = 0.01  # концы шагов ближе, градусы - одна линия


def runs(steps):
    """Линии из шагов: (класс группы, пара, точки, скорость)."""
    out = []
    current = None
    for f in sorted(steps, key=lambda f: f["properties"]["SEQNUM"]):
        p = f["properties"]
        group = p["STEPCLASS"]
        if group not in plates.GROUP:
            continue
        start = (round(p["STARTLAT"], 3), round(p["STARTLONG"], 3))
        end = (round(p["FINALLAT"], 3), round(p["FINALLONG"], 3))
        if abs(start[1] - end[1]) > 180.0:
            # Шаг через линию перемены дат на карте в EPSG:3857 лёг бы
            # линией через весь шар. Шаг пропускается, разрыв - один шаг.
            current = None
            continue
        length = float(p["STEPLENGTH"])
        speed = float(p["VELOCITYLE"])
        if (current is not None and current["group"] == group
                and current["pair"] == p["PLATEBOUND"]
                and abs(current["points"][-1][0] - start[0]) < JOIN
                and abs(current["points"][-1][1] - start[1]) < JOIN):
            current["points"].append(end)
            current["length"] += length
            current["speed"] += speed * length
            continue
        current = {"group": group, "pair": p["PLATEBOUND"],
                   "points": [start, end], "length": length,
                   "speed": speed * length}
        out.append(current)
    return [{"class": r["group"], "pair": r["pair"],
             "speed": round(r["speed"] / r["length"], 1)
             if r["length"] else 0.0,
             "points": [list(pt) for pt in r["points"]]} for r in out]


def label_point(ring):
    """Точка подписи плиты - среднее вершин контура. Долготы считаются
    вокруг первой вершины, так плита через линию перемены дат не
    разваливается."""
    lats = [p[1] for p in ring]
    # Долготы через линию перемены дат - вокруг первой вершины.
    base = ring[0][0]
    lons = [base + ((p[0] - base + 180.0) % 360.0 - 180.0) for p in ring]
    clat = sum(lats) / len(lats)
    clon = sum(lons) / len(lons)
    clon = (clon + 180.0) % 360.0 - 180.0
    return round(clat, 2), round(clon, 2)


def main(folder):
    with open(os.path.join(folder, "PB2002_steps.json"),
              encoding="utf-8") as fh:
        steps = json.load(fh)["features"]
    with open(os.path.join(folder, "PB2002_plates.json"),
              encoding="utf-8") as fh:
        polys = json.load(fh)["features"]
    lines = runs(steps)
    names = []
    for f in polys:
        ring = f["geometry"]["coordinates"][0]
        if f["geometry"]["type"] == "MultiPolygon":
            ring = max((part[0] for part in f["geometry"]["coordinates"]),
                       key=len)
        lat, lon = label_point(ring)
        names.append([f["properties"]["Code"], f["properties"]["PlateName"],
                      lat, lon])
    data = {"source": " ".join(plates.ATTRIBUTION), "boundaries": lines,
            "plates": names}
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    points = sum(len(r["points"]) for r in lines)
    print(OUT, os.path.getsize(OUT), "lines", len(lines), "points", points,
          "plates", len(names))
    for group in sorted({r["class"] for r in lines}):
        print(group, sum(1 for r in lines if r["class"] == group))
    print("longest run", max(len(r["points"]) for r in lines),
          "speed range", min(r["speed"] for r in lines),
          max(r["speed"] for r in lines))


if __name__ == "__main__":
    main(sys.argv[1])
