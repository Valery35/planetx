# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Собирает planetx/data/spectra.json из спектральной библиотеки USGS
Spectral Library Version 7 (Kokaly и др., 2017, doi 10.5066/F7RR1WDJ,
общественное достояние США).

Берутся архивы спектров, пересчитанных USGS на каналы спутников:
ASCIIdata_splib07b_rsASTER, rsLandsat8 и rsSentinel2 со страницы
sciencebase.gov/catalog/item/586e8c88e4b0f5ce109fccae. Папки
распакованных архивов передаются аргументами:

    python build_spectra.py <папка rsASTER> <папка rsLandsat8>
                            <папка rsSentinel2>

Главы: минералы, почвы и смеси, растения, покрытия, искусственные
материалы, жидкости. Органические соединения не берутся. Спектр
со значением «нет данных» хоть в одном канале датчика у этого датчика
пропускается. Значения - отражение в долях единицы, 4 знака.
"""
import glob
import json
import os
import re
import sys

SENSORS = (("aster", "S07ASTER", "ASTER"),
           ("landsat8", "S07LSAT8", "Landsat 8"),
           ("sentinel2", "S07SNTL2", "Sentinel-2"))
CHAPTERS = {"M": "minerals", "S": "soils", "V": "vegetation",
            "C": "coatings", "A": "artificial", "L": "liquids"}
WAVES = re.compile(r"Wavelengths_\w+_\((\d+)_bands\)_microns\.txt$")
HEADER = re.compile(r"Record=(\d+):\s*(.*)$")
OUT = os.path.join(os.path.dirname(__file__), "..", "planetx", "data",
                   "spectra.json")


def read(path):
    """Заголовок и значения файла библиотеки."""
    with open(path, encoding="latin-1") as fh:
        lines = fh.read().split("\n")
    head = HEADER.search(lines[0])
    values = [float(x) for x in lines[1:] if x.strip()]
    return (head.group(2).strip() if head else ""), values


def parse_title(title):
    """«Kaolinite CM3  BECKa AREF» - (название, образец, прибор, вид)."""
    parts = title.split()
    if len(parts) >= 3 and parts[-1].isupper() and len(parts[-1]) == 4:
        kind, instrument = parts[-1], parts[-2]
        rest = parts[:-2]
    else:
        kind, instrument, rest = "", "", parts
    name = " ".join(rest).replace("_", " ")
    return name, instrument, kind


def wavelengths(folder):
    for path in glob.glob(os.path.join(folder, "**", "*.txt"),
                          recursive=True):
        if WAVES.search(os.path.basename(path)):
            return [round(v, 4) for v in read(path)[1]]
    raise SystemExit("нет файла длин волн в " + folder)


def main(folders):
    sensors = {}
    spectra = {}
    for (key, prefix, title), folder in zip(SENSORS, folders):
        sensors[key] = {"name": title, "um": wavelengths(folder)}
        for path in glob.glob(os.path.join(folder, "**", prefix + "_*.txt"),
                              recursive=True):
            chapter = os.path.basename(os.path.dirname(path))
            letter = chapter[len("Chapter"):len("Chapter") + 1] \
                if chapter.startswith("Chapter") else ""
            if letter not in CHAPTERS:
                continue
            head, values = read(path)
            if len(values) != len(sensors[key]["um"]):
                continue
            if any(v < -1.0 or v > 10.0 for v in values):
                continue  # «нет данных» -1.23e34
            name, instrument, kind = parse_title(head)
            ident = os.path.basename(path)[len(prefix) + 1:-4]
            entry = spectra.setdefault(ident, {
                "id": ident, "name": name, "group": CHAPTERS[letter],
                "instrument": instrument, "kind": kind})
            entry[key] = [round(v, 4) for v in values]
    rows = sorted((e for e in spectra.values()
                   if any(k in e for k, _, _ in SENSORS)),
                  key=lambda e: (e["group"], e["name"].lower(), e["id"]))
    # Имя файла без пробелов сканер каталога QGIS (detect-secrets)
    # принимает за ключ, поэтому номер эталона - порядковый.
    for n, row in enumerate(rows):
        row["id"] = n
    data = {"source": "USGS Spectral Library Version 7, Kokaly et al. "
                      "2017, doi:10.5066/F7RR1WDJ, public domain",
            "sensors": sensors, "spectra": rows}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(len(rows), "спектров,", os.path.getsize(OUT) // 1024, "КБ")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        raise SystemExit(__doc__)
    main(sys.argv[1:])
