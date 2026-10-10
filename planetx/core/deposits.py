# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Месторождения полезных ископаемых USGS. Расчёт без Qt.

Просьба автора от 10 октября 2026 года - «месторождения полезных
ископаемых, такие точки в USGS были», выбор того же дня - строка
витрины, оба набора:

- MRDS, Mineral Resources Data System - 304 632 записи месторождений,
  рудников, проявлений, из них 266 599 в США, 1 394 в России. Файл
  mrds-csv.zip (23 МБ), не обновляется с 2011 года, в архиве 2022 год.
- Major mineral deposits of the world, USGS Open-File Report 2005-1294 -
  3 168 крупных месторождений мира, из них 300 в России.

Оба файла скачиваются при первом включении строки, разбор - в рабочем
потоке (parse_mrds, parse_major), итог - компактный файл в профиле QGIS
(save, load), дальше сеть не нужна. Цвет точки - группа первого
полезного ископаемого (group_of), размер - крупное месторождение
мира или стадия освоения MRDS. Тексты для опроса лежат одной строкой
с разделителями, запись достаётся по смещению (Deposits.text).
"""
import csv
import io
import math
import zipfile

import numpy as np

MRDS_URL = "https://mrdata.usgs.gov/mrds/mrds-csv.zip"
MAJOR_URL = ("https://mrdata.usgs.gov/major-deposits/"
             "ofr20051294-csv.zip")
ATTRIBUTION = ("Deposits: USGS MRDS, USGS OFR 2005-1294",
               "https://mrdata.usgs.gov/")
MRDS_PAGE = "https://mrdata.usgs.gov/mrds/show-mrds.php?dep_id={}"

# Группы полезных ископаемых: ключ, слова в названии, цвет. Порядок -
# порядок проверки. Состав и цвета - выбор помощника, утверждает автор.
GROUPS = (
    ("precious", ("gold", "silver", "platinum", "palladium", "pge",
                  "rhodium", "iridium", "osmium", "ruthenium"),
     (240, 200, 40)),
    ("base", ("copper", "lead", "zinc", "nickel", "cobalt", "molybdenum",
              "tin", "tungsten", "mercury", "antimony", "bismuth",
              "cadmium", "arsenic"), (230, 110, 40)),
    ("iron", ("iron", "manganese", "chromium", "chromite", "vanadium",
              "titanium"), (170, 60, 60)),
    ("rare", ("lithium", "rare earth", "ree", "niobium", "tantalum",
              "beryllium", "zirconium", "cesium", "gallium", "germanium",
              "indium", "tellurium", "graphite", "aluminum", "bauxite",
              "scandium", "yttrium", "rubidium", "hafnium"),
     (170, 90, 220)),
    ("energy", ("coal", "uranium", "thorium", "lignite", "oil", "gas",
                "peat", "anthracite", "geothermal", "helium"),
     (60, 200, 90)),
    ("gems", ("diamond", "gem", "emerald", "sapphire", "ruby", "opal",
              "turquoise", "garnet", "jade", "amber"), (60, 200, 230)),
    ("industrial", ("sand", "gravel", "stone", "clay", "limestone",
                    "gypsum", "salt", "potash", "phosphate", "barite",
                    "fluor", "feldspar", "mica", "talc", "kaolin",
                    "perlite", "pumice", "diatomite", "sulfur", "boron",
                    "borate", "dolomite", "marble", "granite", "silica",
                    "zeolite", "vermiculite", "asbestos", "magnesite",
                    "magnesium", "bentonite", "cement", "lime", "quartz",
                    "sodium", "potassium", "iodine", "bromine", "nitrate",
                    "slate", "shale", "pegmatite", "wollastonite",
                    "kyanite", "andalusite", "olivine", "strontium",
                    "celestite", "calcium", "trona", "halite",
                    "volcanic", "corundum", "emery", "fuller", "pigment",
                    "aggregate", "montmorillonite", "abrasive", "phosphor",
                    "asphalt", "soda", "sylvite", "pyrophyllite",
                    "nepheline", "staurolite"),
     (175, 175, 175)),
)
OTHER = len(GROUPS)
OTHER_COLOR = (235, 235, 235)
# Стадия освоения MRDS - код и размер точки, логических пикселей.
STATUSES = ("Producer", "Past Producer", "Plant", "Prospect", "Occurrence",
            "Unknown")
STATUS_SIZES = (4.5, 4.0, 4.0, 3.0, 2.5, 2.5)
MAJOR_SIZE = 7.0
SEPARATOR = "\x1f"  # поля записи
END = "\x1e"  # конец записи


def group_of(commodities):
    """Номер группы по строке полезных ископаемых (первое найденное
    слово по порядку GROUPS), иначе OTHER."""
    text = (commodities or "").lower()
    first = text.split(",")[0].strip() if text else ""
    for probe in (first, text):
        if not probe:
            continue
        for n, (_, words, _) in enumerate(GROUPS):
            if any(word in probe for word in words):
                return n
    return OTHER


def colors(groups):
    """Цвета точек (n, 3) uint8 по номерам групп."""
    table = np.array([g[2] for g in GROUPS] + [OTHER_COLOR], dtype=np.uint8)
    return table[np.asarray(groups, dtype=np.int64)]


def sizes(major, status):
    """Размер точки: крупное месторождение мира или стадия MRDS."""
    by_status = np.array(STATUS_SIZES, dtype=np.float32)
    out = by_status[np.asarray(status, dtype=np.int64)]
    return np.where(np.asarray(major, dtype=bool), MAJOR_SIZE, out)


class Deposits:
    """Месторождения массивами: lat, lon, group, status (код STATUSES),
    major (крупное месторождение мира), text - строка записей, offsets -
    начала записей в ней (на одну больше записей)."""

    __slots__ = ("lat", "lon", "group", "status", "major", "blob",
                 "offsets")

    def __init__(self, lat=(), lon=(), group=(), status=(), major=(),
                 blob="", offsets=(0,)):
        self.lat = np.asarray(lat, dtype=np.float64)
        self.lon = np.asarray(lon, dtype=np.float64)
        self.group = np.asarray(group, dtype=np.uint8)
        self.status = np.asarray(status, dtype=np.uint8)
        self.major = np.asarray(major, dtype=bool)
        self.blob = blob
        self.offsets = np.asarray(offsets, dtype=np.int64)

    def __len__(self):
        return len(self.lat)

    def text(self, n):
        """Поля записи n: название, страна, полезные ископаемые, тип,
        стадия или модель, номер записи MRDS (пусто у крупных)."""
        part = self.blob[self.offsets[n]:self.offsets[n + 1]]
        return part.rstrip(END).split(SEPARATOR)


def _number(cell):
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


class _Builder:
    def __init__(self):
        self.lat, self.lon, self.group = [], [], []
        self.status, self.major, self.parts = [], [], []

    def add(self, lat, lon, commodities, major, status, fields):
        if lat is None or lon is None or not (-90.0 <= lat <= 90.0) \
                or not (-180.0 <= lon <= 180.0):
            return
        self.lat.append(lat)
        self.lon.append(lon)
        self.group.append(group_of(commodities))
        self.status.append(status)
        self.major.append(major)
        self.parts.append(SEPARATOR.join(
            str(f or "").replace(SEPARATOR, " ").replace(END, " ")
            for f in fields) + END)

    def result(self):
        lengths = [len(p) for p in self.parts]
        offsets = np.concatenate([[0], np.cumsum(lengths)]) if lengths \
            else np.zeros(1)
        return Deposits(self.lat, self.lon, self.group, self.status,
                        self.major, "".join(self.parts), offsets)


def _rows(data, name):
    """Строки CSV файла name архива ZIP data."""
    archive = zipfile.ZipFile(io.BytesIO(data))
    member = next(m for m in archive.namelist()
                  if m.lower().endswith(name))
    text = archive.read(member).decode("utf-8", "replace")
    return csv.DictReader(io.StringIO(text))


def parse(mrds, major):
    """Оба набора в одни массивы: сначала крупные месторождения мира,
    потом MRDS. mrds, major - байты архивов или None."""
    out = _Builder()
    if major:
        for row in _rows(major, "deposit.csv"):
            out.add(_number(row.get("latitude")),
                    _number(row.get("longitude")), row.get("commodity"),
                    True, len(STATUSES) - 1,
                    (row.get("dep_name"), row.get("country"),
                     row.get("commodity"), row.get("dep_type"),
                     row.get("model_name") or row.get("type_detail"), ""))
    if mrds:
        index = {name.lower(): n for n, name in enumerate(STATUSES)}
        for row in _rows(mrds, "mrds.csv"):
            commodities = ", ".join(c for c in (row.get("commod1"),
                                                row.get("commod2"),
                                                row.get("commod3")) if c)
            status = index.get((row.get("dev_stat") or "").lower(),
                               len(STATUSES) - 1)
            out.add(_number(row.get("latitude")),
                    _number(row.get("longitude")), commodities, False,
                    status, (row.get("site_name"), row.get("country"),
                             commodities, row.get("dep_type"),
                             row.get("dev_stat"), row.get("dep_id")))
    return out.result()


def save(deposits, path):
    """Массивы в файл NPZ без объектов Python."""
    np.savez_compressed(
        path, lat=deposits.lat.astype(np.float32),
        lon=deposits.lon.astype(np.float32), group=deposits.group,
        status=deposits.status, major=deposits.major,
        offsets=deposits.offsets,
        blob=np.frombuffer(deposits.blob.encode("utf-8"), dtype=np.uint8))


def load(path):
    """Месторождения из файла save. Смещения - в символах строки."""
    with np.load(path, allow_pickle=False) as data:
        blob = data["blob"].tobytes().decode("utf-8")
        return Deposits(data["lat"].astype(np.float64),
                        data["lon"].astype(np.float64), data["group"],
                        data["status"], data["major"], blob,
                        data["offsets"])
