# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Каталог привязанных карт коллекции Дэвида Рамсея для planetx-terrain.

    $PY tools/build_rumsey.py АРХИВ ПАПКА

АРХИВ - luna_omo_metadata_56628_20220724.zip из набора Стэнфорда
«David Rumsey Map Collection: Georeferenced Maps Metadata»
(purl.stanford.edu/ss311gz1992, CC0). ПАПКА - planetx-terrain/rumsey.

Пишется index.json - все карты: номер, рамка (запад, юг, восток,
север), год, название, масштаб, клетка. Рамка - обрезка поля карты,
переведённая в градусы аффинным приближением по опорным точкам.
Подробности карт - файлы cells/<клетка>.json по клеткам CELL градусов
по середине рамки: адрес изображения IIIF, способ привязки, опорные
точки (пиксель x, y, долгота, широта), обрезка в пикселях, страница
карты. Изображения карт в каталог не входят, их скачивает модуль.
"""
import ast
import csv
import io
import json
import math
import os
import sys
import zipfile

import numpy as np

CELL = 10  # градусов, клетка файлов подробностей
TITLE = 120  # знаков названия в указателе
IIIF = "https://images.iiifhosting.com/iiif/"


def year_of(text):
    try:
        return int(float(str(text).strip("'")))
    except ValueError:
        return None


def affine(gcps):
    """Аффинное приближение пиксель - градусы по опорным точкам."""
    px = np.array([[g["pixel"][0], g["pixel"][1], 1.0] for g in gcps])
    geo = np.array([g["location"] for g in gcps], dtype=np.float64)
    coef, *_ = np.linalg.lstsq(px, geo, rcond=None)
    return coef


def box_of(gcps, cutline):
    points = cutline or [g["pixel"] for g in gcps]
    if len(gcps) >= 3:
        coef = affine(gcps)
        xy = np.array([[p[0], p[1], 1.0] for p in points]) @ coef
        lons, lats = xy[:, 0], xy[:, 1]
    else:
        lons = np.array([g["location"][0] for g in gcps])
        lats = np.array([g["location"][1] for g in gcps])
    return (max(-180.0, float(lons.min())), max(-90.0, float(lats.min())),
            min(180.0, float(lons.max())), min(90.0, float(lats.max())))


def cell_of(box):
    lon = (box[0] + box[2]) / 2.0
    lat = (box[1] + box[3]) / 2.0
    return "{}_{}".format(int(math.floor(lat / CELL) * CELL),
                          int(math.floor(lon / CELL) * CELL))


def main(archive, folder):
    csv.field_size_limit(10 ** 9)
    z = zipfile.ZipFile(archive)
    rows = csv.DictReader(io.TextIOWrapper(z.open(z.namelist()[0]),
                                           encoding="utf-8"))
    index, cells = [], {}
    for n, row in enumerate(rows):
        gcps = ast.literal_eval(row["gcps"] or "[]")
        if len(gcps) < 2:
            continue
        cutline = ast.literal_eval(row["cutline"] or "[]")
        box = box_of(gcps, cutline)
        if box[0] >= box[2] or box[1] >= box[3]:
            continue
        cell = cell_of(box)
        image = row["image_url"]
        if image.startswith(IIIF):
            image = image[len(IIIF):].replace("/info.json", "")
        scale = year_of(row["scale"])
        index.append([n] + [round(v, 4) for v in box]
                     + [year_of(row["date"]),
                        (row["title"] or "")[:TITLE], scale, cell])
        cells.setdefault(cell, {})[str(n)] = {
            "i": image, "m": row["transformation_method"],
            "g": [[round(g["pixel"][0], 1), round(g["pixel"][1], 1),
                   round(g["location"][0], 6), round(g["location"][1], 6)]
                  for g in gcps],
            "k": [[int(round(p[0])), int(round(p[1]))] for p in cutline],
            "u": row["link_url"], "c": row["creator"]}
    os.makedirs(os.path.join(folder, "cells"), exist_ok=True)
    with open(os.path.join(folder, "index.json"), "w", encoding="utf-8",
              newline="\n") as fh:
        json.dump({"source": "David Rumsey Map Collection, Stanford "
                   "Georeferenced Maps Metadata (CC0)",
                   "cell": CELL, "maps": index}, fh, ensure_ascii=False,
                  separators=(",", ":"))
    for cell, maps in cells.items():
        with open(os.path.join(folder, "cells", cell + ".json"), "w",
                  encoding="utf-8", newline="\n") as fh:
            json.dump(maps, fh, ensure_ascii=False, separators=(",", ":"))
    sizes = [os.path.getsize(os.path.join(folder, "cells", c + ".json"))
             for c in cells]
    print(len(index), "maps,", len(cells), "cells, index",
          os.path.getsize(os.path.join(folder, "index.json")) // 1024,
          "KB, largest cell", max(sizes) // 1024, "KB")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
