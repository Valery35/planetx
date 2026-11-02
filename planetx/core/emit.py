# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Минеральные карты EMIT: продукт NASA EMIT L2B MIN, определение
минералов по спектрам снимков спектрометра EMIT на МКС, пиксель 60 м.

Просьба автора от 2 ноября 2026 года, третий пункт классификации по
спектрам. Каталог - NASA CMR без входа, коллекции EMITL2BMIN версий 001
и 002, у сцены одной съёмки берётся старшая версия. Файл - netCDF4
в хранилище LP DAAC lp-prod-protected, по ключу Earthdata, как ASTER
после 2006 года. Данные файла - полоса съёмки без геопривязки:
group_1_mineral_id и group_1_band_depth (группа 1 - железистые минералы,
полосы поглощения 0.4-1.3 мкм), group_2_* (группа 2 - глины, слюда,
карбонаты, сульфаты, 2.0-2.5 мкм), группа location - таблица GLT: для
клетки сетки широт и долгот номер строки и столбца полосы с 1, 0 - нет
данных. Названия минералов - группа mineral_metadata того же файла.
Метод определения - Tetracorder (Clark и др., 2003).

Модуль только на NumPy, переносится в PlanetX Lite без изменений.
"""
import math
from urllib.parse import urlencode

import numpy as np

try:  # внутри плагина QGIS
    from .subsurface import inside
except ImportError:  # headless-тесты
    from subsurface import inside

SEARCH = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
# Версия 002 - пересчёт архива с 2025 года, у части сцен её ещё нет.
COLLECTIONS = (("C4079846859-LPCLOUD", "002"),
               ("C2408034484-LPCLOUD", "001"))
FIRST_DAY = "2022-08-09"
PAGE = 200  # сцен в ответе каталога
STEP = 60.0  # м, пиксель продукта
LOGIN_HOST = "urs.earthdata.nasa.gov"
GROUPS = (1, 2)
SAMPLES = 15  # точек на сторону участка при оценке покрытия сценой
MOST = 254  # минералов в растре классов, остальные - «прочие»
CREDIT = "EMIT L2B MIN, NASA JPL, LP DAAC"
# Цвета минералов по номеру - выбор помощника.
PALETTE = ((230, 25, 75), (60, 180, 75), (255, 225, 25), (0, 130, 200),
           (245, 130, 48), (145, 30, 180), (70, 240, 240), (240, 50, 230),
           (210, 245, 60), (250, 190, 212), (0, 128, 128), (220, 190, 255),
           (170, 110, 40), (255, 250, 200), (128, 0, 0), (170, 255, 195),
           (128, 128, 0), (255, 215, 180), (0, 0, 128), (128, 128, 128))


def cmr_url(ring, start, end, max_cloud, collection, page_size=PAGE):
    """Адрес поиска сцен коллекции в CMR: рамка участка (широта,
    долгота), дни «ГГГГ-ММ-ДД», облачность, новые первыми."""
    lats = [p[0] for p in ring]
    lons = [p[1] for p in ring]
    query = [("collection_concept_id", collection),
             ("bounding_box", "{:.6f},{:.6f},{:.6f},{:.6f}".format(
                 min(lons), min(lats), max(lons), max(lats))),
             ("temporal", "{}T00:00:00Z,{}T23:59:59Z".format(start, end)),
             ("cloud_cover", "0,{:g}".format(float(max_cloud))),
             ("sort_key", "-start_date"),
             ("page_size", str(int(page_size)))]
    return SEARCH + "?" + urlencode(query)


def _when(umm):
    extent = umm.get("TemporalExtent") or {}
    when = (extent.get("RangeDateTime") or {}).get("BeginningDateTime") \
        or extent.get("SingleDateTime") or ""
    return str(when).replace("T", " ").rstrip("Z")[:19]


def parse_cmr(data, version=""):
    """Сцены ответа CMR: словари id, when, cloud, polygon [(широта,
    долгота)], url файла MIN, preview, version."""
    out = []
    for item in (data or {}).get("items") or []:
        umm = item.get("umm") or {}
        url, preview = "", ""
        for link in umm.get("RelatedUrls") or []:
            href = str(link.get("URL") or "")
            if not href.startswith("https://"):
                continue
            name = href.rsplit("/", 1)[-1]
            if link.get("Type") == "GET RELATED VISUALIZATION" \
                    and name.endswith(".png"):
                preview = href
            elif link.get("Type") == "GET DATA" and name.endswith(".nc") \
                    and name.startswith("EMIT_L2B_MIN_"):
                url = href
        if not url:
            continue
        polygon = []
        geometry = ((umm.get("SpatialExtent") or {})
                    .get("HorizontalSpatialDomain") or {}).get("Geometry")
        for shape in (geometry or {}).get("GPolygons") or []:
            for point in (shape.get("Boundary") or {}).get("Points") or []:
                polygon.append((float(point.get("Latitude", 0.0)),
                                float(point.get("Longitude", 0.0))))
            break
        cloud = umm.get("CloudCover")
        out.append({"id": str(umm.get("GranuleUR") or ""),
                    "when": _when(umm),
                    "cloud": float(cloud) if cloud is not None else 0.0,
                    "polygon": polygon[:-1] if polygon
                    and polygon[0] == polygon[-1] else polygon,
                    "url": url, "preview": preview, "version": version})
    return out


def merge(lists):
    """Сцены нескольких версий: у одной съёмки (секунда начала) остаётся
    первая по порядку lists, новые первыми."""
    seen, out = set(), []
    for scenes in lists:
        for scene in scenes:
            key = scene["when"]
            if key in seen:
                continue
            seen.add(key)
            out.append(scene)
    return sorted(out, key=lambda s: s["when"], reverse=True)


def coverage(polygon, ring):
    """Доля участка ring, которую накрывает контур сцены polygon: по
    сетке точек SAMPLES × SAMPLES внутри рамки участка."""
    if len(polygon) < 3 or len(ring) < 3:
        return 0.0
    lats = [p[0] for p in ring]
    lons = [p[1] for p in ring]
    ys = np.linspace(min(lats), max(lats), SAMPLES)
    xs = np.linspace(min(lons), max(lons), SAMPLES)
    grid_y, grid_x = np.meshgrid(ys, xs, indexing="ij")
    grid_y, grid_x = grid_y.ravel(), grid_x.ravel()
    within = inside(grid_y, grid_x, ring)
    if not within.any():
        return 0.0
    covered = inside(grid_y[within], grid_x[within], polygon)
    return float(covered.mean())


def ortho(values, glt_x, glt_y, fill=np.nan):
    """Значения полосы съёмки на сетке широт и долгот по таблице GLT:
    номера столбца и строки с 1, 0 - нет данных, знак не учитывается."""
    gx = np.abs(np.asarray(glt_x, dtype=np.int64))
    gy = np.abs(np.asarray(glt_y, dtype=np.int64))
    values = np.asarray(values)
    good = (gx > 0) & (gy > 0) & (gx <= values.shape[1]) \
        & (gy <= values.shape[0])
    kind = np.float32 if np.issubdtype(values.dtype, np.floating) \
        else values.dtype
    out = np.full(gx.shape, fill, dtype=np.result_type(kind, type(fill)))
    out[good] = values[gy[good] - 1, gx[good] - 1]
    return out


def fit_transform(glt_x, glt_y, lats, lons):
    """Геопреобразование сетки GLT по широтам и долготам полосы, если
    в файле нет атрибута geotransform: наименьшие квадраты по клеткам
    с данными. Итог - (x0, dx, 0, y0, 0, dy) для углов клеток или None."""
    gx = np.abs(np.asarray(glt_x, dtype=np.int64))
    gy = np.abs(np.asarray(glt_y, dtype=np.int64))
    rows, cols = np.nonzero((gx > 0) & (gy > 0))
    if len(rows) < 3:
        return None
    lon = np.asarray(lons)[gy[rows, cols] - 1, gx[rows, cols] - 1]
    lat = np.asarray(lats)[gy[rows, cols] - 1, gx[rows, cols] - 1]
    dx, x0 = np.polyfit(cols + 0.5, lon, 1)
    dy, y0 = np.polyfit(rows + 0.5, lat, 1)
    return (float(x0), float(dx), 0.0, float(y0), 0.0, float(dy))


def names_of(index, group, names, samples=None):
    """Названия минералов групп: {группа: {номер: название}}. Название -
    sample_name, без него name без пути и окончания файла."""
    out = {g: {} for g in GROUPS}
    for n, (number, kind) in enumerate(zip(index, group)):
        text = ""
        if samples is not None and n < len(samples):
            text = str(samples[n] or "").strip()
        if not text and n < len(names):
            text = str(names[n] or "").strip()
            text = text.replace("\\", "/").rsplit("/", 1)[-1]
            text = text.rsplit(".", 1)[0] if "." in text[-5:] else text
        out.setdefault(int(kind), {})[int(number)] = text or str(number)
    return out


def classes(ids, depth, mask=None):
    """Классы участка по номерам минералов ids и глубине полосы depth:
    (номера классов int16, -1 без минерала, номера минералов по убыванию
    площади). Клетка без минерала - номер < 0 или глубина не больше 0
    и не число. Больше MOST минералов - последний класс собирает
    остальные, его номер минерала -1."""
    ids = np.asarray(ids)
    depth = np.asarray(depth, dtype=np.float64)
    good = np.isfinite(depth) & (depth > 0.0) & (ids >= 0)
    if mask is not None:
        good &= mask
    kinds = np.full(ids.shape, -1, dtype=np.int16)
    if not good.any():
        return kinds, []
    found, counts = np.unique(ids[good].astype(np.int64),
                              return_counts=True)
    order = [int(found[n]) for n in np.argsort(-counts, kind="stable")]
    kept = order if len(order) <= MOST else order[:MOST - 1] + [-1]
    lookup = {m: n for n, m in enumerate(kept) if m >= 0}
    rest = len(kept) - 1 if kept[-1] == -1 else None
    kinds[good] = _lookup(ids[good].astype(np.int64), lookup, rest)
    return kinds, kept


def _lookup(flat_ids, lookup, rest):
    top = int(flat_ids.max()) + 1
    table = np.full(top, -1 if rest is None else rest, dtype=np.int16)
    for mineral, kind in lookup.items():
        if mineral < top:
            table[mineral] = kind
    return table[flat_ids]


def color(mineral):
    """Цвет минерала по номеру, «прочие» - серый."""
    if mineral < 0:
        return (160, 160, 160)
    return PALETTE[mineral % len(PALETTE)]


def shares(kinds, count):
    """Доли классов от клеток с минералом: список (номер класса, доля)
    по убыванию."""
    kinds = np.asarray(kinds)
    good = kinds[kinds >= 0]
    if not len(good):
        return []
    counts = np.bincount(good, minlength=count)
    order = np.argsort(-counts, kind="stable")
    return [(int(n), float(counts[n]) / len(good)) for n in order
            if counts[n]]


def area_km2(cells, step=STEP):
    return cells * step * step / 1e6


def fit_ok(transform):
    """Геопреобразование годно: конечные числа и ненулевой шаг."""
    return transform is not None and all(
        math.isfinite(v) for v in transform) and transform[1] != 0.0 \
        and transform[5] != 0.0
