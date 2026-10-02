# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Погружающиеся плиты Slab2 на разрезах. Без Qt.

Шаг 3 плана «сверху вниз», 2 октября 2026 года. Slab2 (Hayes, 2018,
doi:10.5066/F7PV6JNV) - верхняя поверхность, толщина и падение плиты
в 27 зонах субдукции, данные USGS в общественном достоянии США.

Решение автора от 2 октября 2026 года - плиты не отдельный слой. Плита
видна на разрезе полосой с толщиной там, где разрез проходит через
зону, и данные зоны запрашиваются, когда разрез её касается. Файлы
зон лежат в хранилище planetx-terrain (URL), их собирает
tools/build_slabs.py. Указатель зон с рамками - data/slab2_index.json
в модуле.

Полоса на вертикальном разрезе - от верхней поверхности плиты вниз
на видимую толщину: толщина по нормали к плите, делённая на косинус
падения, не больше MAX_DIP. На разрезе вкрест простирания это
настоящая толщина в вертикальном сечении, на косом разрезе - оценка.
"""
import io
import json
from collections import namedtuple

import numpy as np

URL = ("https://raw.githubusercontent.com/Valery35/planetx-terrain/main/"
       "slab2/{code}.npz")
EMPTY = -32768
MAX_DIP = 75.0  # градусы: круче видимая толщина не растёт
ATTRIBUTION = ("Slabs: USGS Slab2",
               "https://www.usgs.gov/data/slab2-a-comprehensive-subduction-"
               "zone-geometry-model")

Slab = namedtuple("Slab", "code lon0 lat0 step depth thickness dip")
Slab.__doc__ = """Зона: код USGS, долгота и широта первого узла (северо-
западного), шаг в градусах, глубина и толщина в км, падение в градусах
(rows, cols), пусто - NaN. Строки с севера на юг, столбцы с запада на
восток."""


class SlabError(ValueError):
    """Файл зоны не того вида."""


def read_index(text):
    """Указатель зон: {код: (юг, север, запад, восток)}."""
    data = json.loads(text)
    return {code: (v["south"], v["north"], v["west"], v["east"])
            for code, v in data.items()}


def load(data, code):
    """Зона из байтов файла slab2/<код>.npz."""
    try:
        with np.load(io.BytesIO(data)) as npz:
            lon0, lat0, step = (float(v) for v in npz["origin"])
            depth = npz["depth"]
            thickness = npz["thickness"]
            dip = npz["dip"].astype(np.float64)
    except (OSError, KeyError, ValueError) as error:
        raise SlabError(str(error)) from error
    return Slab(code, lon0, lat0, step,
                np.where(depth == EMPTY, np.nan, depth / 10.0),
                np.where(thickness == EMPTY, np.nan, thickness / 10.0), dip)


def in_box(box, lats, lons):
    """Признак «точка в рамке зоны» для широт и долгот. Рамка с западом
    больше востока пересекает линию перемены дат."""
    south, north, west, east = box
    lats = np.asarray(lats, dtype=np.float64)
    lons = (np.asarray(lons, dtype=np.float64) + 180.0) % 360.0 - 180.0
    if west <= east:
        across = (lons >= west) & (lons <= east)
    else:
        across = (lons >= west) | (lons <= east)
    return (lats >= south) & (lats <= north) & across


def touched(index, lats, lons):
    """Коды зон, рамку которых задевают точки разреза."""
    return sorted(code for code, box in index.items()
                  if np.any(in_box(box, lats, lons)))


def _cells(slab, lats, lons):
    """Номера ближайших узлов и признак «внутри сетки»."""
    rows, cols = slab.depth.shape
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    i = np.rint((slab.lat0 - lats) / slab.step).astype(np.int64)
    j = np.rint(((lons - slab.lon0) % 360.0) / slab.step).astype(np.int64)
    ok = (i >= 0) & (i < rows) & (j >= 0) & (j < cols)
    return np.clip(i, 0, rows - 1), np.clip(j, 0, cols - 1), ok


def depth_at(slab, lat, lon):
    """Глубина плиты в точке по ближайшему узлу, км, или NaN."""
    i, j, ok = _cells(slab, [lat], [lon])
    return float(slab.depth[i[0], j[0]]) if ok[0] else float("nan")


def band(zones, lats, lons):
    """Полоса плит вдоль разреза: верх и низ в км для каждой точки,
    NaN - плиты нет. Из нескольких зон берётся первая с плитой."""
    lats = np.asarray(lats, dtype=np.float64)
    top = np.full(lats.shape, np.nan)
    bottom = np.full(lats.shape, np.nan)
    for slab in zones:
        i, j, ok = _cells(slab, lats, lons)
        depth = np.where(ok, slab.depth[i, j], np.nan)
        thick = np.where(ok, slab.thickness[i, j], np.nan)
        dip = np.minimum(np.where(ok, slab.dip[i, j], 0.0), MAX_DIP)
        seen = np.isnan(top) & np.isfinite(depth) & np.isfinite(thick)
        top[seen] = depth[seen]
        bottom[seen] = depth[seen] + thick[seen] / np.cos(
            np.radians(dip[seen]))
    return top, bottom


def url_of(code, base=None):
    """Адрес файла зоны. base - шаблон вместо URL, для проверки на
    локальной копии хранилища."""
    return (base or URL).format(code=code)

