# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Минералы по спектру: спектр пикселя снимка сравнивается с эталонами
спектральной библиотеки USGS Spectral Library Version 7.

Просьба автора от 2 ноября 2026 года. Библиотека - data/spectra.json
(tools/build_spectra.py), у каждого эталона значения, пересчитанные
USGS на каналы ASTER, Landsat 8 и Sentinel-2. Каналы растра узнаются по
длине волны из подписи канала: «B3N 0.82 um» файлов ASTER модуля, имена
каналов «red», «swir16» файлов Sentinel-2 и Landsat модуля, число
с единицей нм или мкм. Канал сопоставляется с ближайшим каналом датчика
не дальше TOLERANCE доли длины волны, тепловые каналы не участвуют.

Мера - угол между спектрами (Spectral Angle Mapper, Kruse и др. 1993):
arccos(a·b / |a||b|). Угол не зависит от общей яркости, поэтому склон
в тени и на солнце даёт один ответ. Клетка получает эталон с наименьшим
углом, если он не больше порога, иначе остаётся без класса.

Модуль только на NumPy, переносится в PlanetX Lite без изменений.
"""
import json
import math
import re

import numpy as np

TOLERANCE = 0.06  # доля длины волны, в которой каналы считаются одним
MIN_BANDS = 3  # совпавших каналов не меньше
CHUNK = 256 * 1024  # клеток за шаг расчёта
LIMIT = 6.0  # градусов, порог угла по умолчанию
# Длины волн, мкм, по именам каналов файлов модуля (core/sentinel.py).
KEYS = {"coastal": 0.443, "blue": 0.49, "green": 0.56, "red": 0.665,
        "rededge1": 0.705, "rededge2": 0.74, "rededge3": 0.783,
        "nir": 0.842, "nir08": 0.865, "nir09": 0.945, "swir16": 1.61,
        "swir22": 2.19}
NUMBER = re.compile(r"(\d+(?:[.,]\d+)?)\s*(nm|um|µm|мкм|нм)", re.IGNORECASE)
WORD = re.compile(r"[a-z]+\d*", re.IGNORECASE)
GROUPS = ("minerals", "soils", "vegetation", "coatings", "artificial",
          "liquids")


class Library:
    """Эталоны: sensors - {ключ: {"name", "um"}}, spectra - список
    словарей id, name, group, instrument, kind и значений по датчикам."""

    def __init__(self, data):
        self.sensors = data["sensors"]
        self.spectra = data["spectra"]
        self.source = data.get("source", "")
        self.by_id = {s["id"]: s for s in self.spectra}

    def values(self, sensor, ids):
        """Эталоны ids на каналах датчика: float64 (эталоны, каналы),
        у кого значений этого датчика нет - пропускаются. Итог - (ids,
        массив)."""
        kept = [i for i in ids if sensor in self.by_id.get(i, {})]
        if not kept:
            return [], np.zeros((0, len(self.sensors[sensor]["um"])))
        return kept, np.array([self.by_id[i][sensor] for i in kept],
                              dtype=np.float64)


def load(path):
    with open(path, encoding="utf-8") as fh:
        return Library(json.load(fh))


def wavelength(label):
    """Длина волны канала, мкм, по подписи или None. Тепловой канал
    (подпись с «, K» или длина больше 5 мкм) - None."""
    if not label:
        return None
    text = str(label)
    if text.rstrip().endswith(", K"):
        return None
    found = NUMBER.search(text)
    if found:
        value = float(found.group(1).replace(",", "."))
        unit = found.group(2).lower()
        if unit in ("nm", "нм"):
            value /= 1000.0
        return value if 0.3 < value < 5.0 else None
    for word in WORD.findall(text):
        if word.lower() in KEYS:
            return KEYS[word.lower()]
    return None


# Номера каналов датчиков в порядке библиотеки: подписи «B8A», «Band 3N».
NUMBERS = {"aster": ("1", "2", "3N", "4", "5", "6", "7", "8", "9"),
           "landsat8": ("1", "2", "3", "4", "5", "6", "7"),
           "sentinel2": ("1", "2", "3", "4", "5", "6", "7", "8", "8A", "9",
                         "10", "11", "12")}
BAND_NUMBER = re.compile(r"\bB(?:AND)?[ _]?0*(\d+[AN]?)\b", re.IGNORECASE)


def match(library, waves, sensor=None):
    """Датчик библиотеки и пары (номер канала растра, номер канала
    датчика) по длинам волн waves каналов растра (None - неизвестна).
    sensor - датчик явно, без него - тот, у кого совпало больше каналов,
    при равенстве - у кого количество каналов ближе к растру (Landsat
    и Sentinel-2 делят многие длины волн), потом - у кого каналы ближе.
    Итог - (датчик, пары) или (None, [])."""
    known = sum(1 for wave in waves if wave is not None)
    best, best_score = (None, []), None
    keys = [sensor] if sensor else list(library.sensors)
    for key in keys:
        um = library.sensors[key]["um"]
        pairs, used, miss = [], set(), 0.0
        for n, wave in enumerate(waves):
            if wave is None:
                continue
            near = min(range(len(um)), key=lambda j: abs(um[j] - wave))
            gap = abs(um[near] - wave) / wave
            if gap <= TOLERANCE and near not in used:
                pairs.append((n, near))
                used.add(near)
                miss += gap
        score = (len(pairs), -abs(len(um) - known), -miss)
        if best_score is None or score > best_score:
            best, best_score = (key, pairs), score
    if len(best[1]) < MIN_BANDS:
        return None, []
    return best


def by_names(sensor, labels):
    """Пары каналов по номерам в подписях «B4», «B8A», «Band 3N» для
    датчика sensor, иначе по порядку каналов."""
    numbers = NUMBERS[sensor]
    pairs, used = [], set()
    for n, label in enumerate(labels):
        found = BAND_NUMBER.search(str(label or ""))
        if found and found.group(1).upper() in numbers:
            j = numbers.index(found.group(1).upper())
            if j not in used:
                pairs.append((n, j))
                used.add(j)
    if len(pairs) >= MIN_BANDS:
        return pairs
    size = min(len(labels), len(numbers))
    return [(n, n) for n in range(size)]


def pairs_for(library, labels, sensor=None):
    """Датчик и пары каналов растра с подписями labels: сначала по длинам
    волн, у явного датчика без длин волн - по номерам в подписях или по
    порядку. Итог - (датчик, пары), (None, []) - не узнан."""
    waves = [wavelength(label) for label in labels]
    found = match(library, waves, sensor)
    if found[0] is not None or sensor is None:
        return found
    return sensor, by_names(sensor, labels)


def angles(cube, refs):
    """Углы, градусы, между спектрами cube (каналы, клетки) и эталонами
    refs (эталоны, каналы): float32 (эталоны, клетки), NaN у клетки
    без данных или с нулевым спектром."""
    cube = np.asarray(cube, dtype=np.float64)
    refs = np.asarray(refs, dtype=np.float64)
    norm = np.sqrt((cube * cube).sum(axis=0))
    ref_norm = np.sqrt((refs * refs).sum(axis=1))
    with np.errstate(invalid="ignore", divide="ignore"):
        cos = (refs @ cube) / (ref_norm[:, None] * norm[None, :])
    out = np.degrees(np.arccos(np.clip(cos, -1.0, 1.0)))
    bad = ~np.isfinite(norm) | (norm <= 0.0)
    out[:, bad] = np.nan
    return out.astype(np.float32)


def classify(grid, refs, limit=LIMIT, progress=None):
    """Эталон каждой клетки сетки grid (каналы, строки, столбцы):
    (номера int16, -1 без класса, угол до него float32, NaN без данных).
    limit - наибольший угол, градусы. progress(сделано, всего) - перед
    шагом."""
    bands, rows, cols = grid.shape
    flat = grid.reshape(bands, -1)
    kinds = np.full(flat.shape[1], -1, dtype=np.int16)
    best = np.full(flat.shape[1], np.nan, dtype=np.float32)
    if not len(refs):
        return kinds.reshape(rows, cols), best.reshape(rows, cols)
    for start in range(0, flat.shape[1], CHUNK):
        if progress is not None:
            progress(start, flat.shape[1])
        part = angles(flat[:, start:start + CHUNK], refs)
        good = np.isfinite(part).all(axis=0)
        low = np.argmin(np.where(np.isfinite(part), part, np.inf), axis=0)
        low_angle = part[low, np.arange(part.shape[1])]
        ok = good & (low_angle <= limit)
        piece = kinds[start:start + CHUNK]
        piece[ok] = low[ok]
        best[start:start + CHUNK] = np.where(good, low_angle, np.nan)
    return kinds.reshape(rows, cols), best.reshape(rows, cols)


def nearest(spectrum, refs, count=5):
    """Ближайшие к спектру (каналы,) эталоны: [(номер, угол)] по углу."""
    found = angles(np.asarray(spectrum, dtype=np.float64)[:, None],
                   refs)[:, 0]
    order = [int(n) for n in np.argsort(found) if math.isfinite(found[n])]
    return [(n, float(found[n])) for n in order[:count]]


def scaled(ref, spectrum):
    """Эталон ref в масштабе спектра: наименьшие квадраты одним множителем,
    так на графике видна форма, а не яркость."""
    ref = np.asarray(ref, dtype=np.float64)
    spectrum = np.asarray(spectrum, dtype=np.float64)
    good = np.isfinite(spectrum)
    denom = float((ref[good] * ref[good]).sum())
    if denom <= 0.0:
        return ref
    return ref * float((ref[good] * spectrum[good]).sum()) / denom


def search(library, text, group=None):
    """Эталоны по словам названия и группе: все слова должны быть
    в названии, образце или приборе."""
    words = [w for w in str(text).lower().split() if w]
    out = []
    for item in library.spectra:
        if group and item["group"] != group:
            continue
        haystack = (item["name"] + " " + item["instrument"]).lower()
        if all(w in haystack for w in words):
            out.append(item)
    return out
