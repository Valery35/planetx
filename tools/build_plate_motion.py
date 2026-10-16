# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скорости плит NNR-MORVEL56 и растр плит в data/plate_motion.json.

    python-qgis.bat tools/build_plate_motion.py ПАПКА

ПАПКА - GeoJSON PB2002_plates.json из github.com/fraxen/tectonicplates
(Hugo Ahlenius, Nordpil, по модели Peter Bird 2003, Open Data Commons
Attribution 1.0), тот же, что у tools/build_plates.py.

Полюса вращения - Table 1 статьи Argus, Gordon, DeMets 2011, G³,
doi:10.1029/2011GC003751 («This paper is not subject to U.S.
copyright»): 25 плит MORVEL и 31 плита Bird 2003 в системе без
суммарного вращения (NNR). Плита точки - растр кодов PB2002 шагом
STEP градусов, GDAL Rasterize. Плиты MORVEL Capricorn, Lwandle,
Macquarie и Sur в PB2002 - части соседних плит, точке достаётся полюс
плиты PB2002.
"""
import json
import os
import sys

import numpy as np
from osgeo import gdal, ogr

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "planetx", "core"))
import platemotion  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
    __file__))), "planetx", "data", "plate_motion.json")
STEP = 0.25
# Код PB2002 - (широта, долгота полюса, °/млн лет) NNR-MORVEL56.
POLES = {
    "AM": (63.17, -122.82, 0.297), "AN": (65.42, -118.11, 0.250),
    "AR": (48.88, -8.49, 0.559), "AU": (33.86, 37.94, 0.632),
    "CA": (35.20, -92.62, 0.286), "CO": (26.93, -124.31, 1.198),
    "EU": (48.85, -106.50, 0.223), "IN": (50.37, -3.29, 0.544),
    "JF": (-38.31, 60.04, 0.951), "NZ": (46.23, -101.06, 0.696),
    "NA": (-4.85, -80.64, 0.209), "AF": (47.68, -68.44, 0.292),
    "PA": (-63.58, 114.70, 0.651), "PS": (-46.02, -31.36, 0.910),
    "RI": (20.25, -107.29, 4.536), "SW": (-29.94, -36.87, 1.362),
    "SC": (22.52, -106.15, 0.146), "SO": (49.95, -84.52, 0.339),
    "SA": (-22.62, -112.83, 0.109), "SU": (50.06, -95.02, 0.337),
    "YA": (63.03, -116.62, 0.334),
    "AS": (19.43, 122.87, 0.124), "AP": (-6.58, -83.98, 0.488),
    "AT": (40.11, 26.66, 1.210), "BR": (-63.74, 142.06, 0.490),
    "BS": (-1.49, 121.64, 2.475), "BH": (-40.00, 100.50, 0.799),
    "BU": (-6.13, -78.10, 2.229), "CL": (-72.78, 72.05, 0.607),
    "CR": (-20.40, 170.53, 3.923), "EA": (24.97, 67.53, 11.334),
    "FT": (-16.33, 178.07, 5.101), "GP": (2.53, 81.18, 5.487),
    "JZ": (34.25, 70.74, 22.368), "KE": (39.99, 6.46, 2.347),
    "MN": (-3.67, 150.27, 51.569), "MO": (14.25, 92.67, 0.774),
    "MA": (11.05, 137.84, 1.306), "MS": (2.15, -56.09, 3.566),
    "NH": (0.57, -6.60, 2.469), "NI": (-3.29, -174.49, 3.314),
    "ND": (17.73, -122.68, 0.116), "NB": (-45.04, 127.64, 0.856),
    "OK": (30.30, -92.28, 0.229), "ON": (36.12, 137.92, 2.539),
    "PM": (31.35, -113.90, 0.317), "SL": (50.71, -143.47, 0.268),
    "SS": (-2.87, 130.62, 1.703), "SB": (6.88, -31.89, 8.111),
    "TI": (-4.44, 113.50, 1.864), "TO": (25.87, 4.48, 8.942),
    "WL": (0.10, 128.52, 1.744),
}


def main(folder):
    gdal.UseExceptions()
    ogr.UseExceptions()
    path = os.path.join(folder, "PB2002_plates.json")
    with open(path, encoding="utf-8") as fh:
        features = json.load(fh)["features"]
    codes = [f["properties"]["Code"] for f in features]
    names = {f["properties"]["Code"]: f["properties"]["PlateName"]
             for f in features}
    missing = [c for c in codes if c not in POLES]
    assert not missing, missing
    cols, rows = int(360 / STEP), int(180 / STEP)
    raster = gdal.GetDriverByName("MEM").Create("", cols, rows, 1,
                                                gdal.GDT_Byte)
    raster.SetGeoTransform((-180.0, STEP, 0.0, 90.0, 0.0, -STEP))
    source = ogr.Open(path)
    layer = source.GetLayer(0)
    # Номер плиты в растре - номер кода в списке плюс 1, 0 - пусто.
    for n, code in enumerate(codes):
        layer.SetAttributeFilter("Code = '{}'".format(code))
        gdal.RasterizeLayer(raster, [1], layer, burn_values=[n + 1])
    grid = raster.GetRasterBand(1).ReadAsArray().astype(np.uint8)
    # Пустые клетки на стыках - номер ближайшей соседней клетки.
    for _ in range(4):
        empty = grid == 0
        if not empty.any():
            break
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0)):
            shifted = np.roll(np.roll(grid, dr, axis=0), dc, axis=1)
            fill = empty & (shifted > 0) & (grid == 0)
            grid[fill] = shifted[fill]
    data = {
        "source": "NNR-MORVEL56: Argus, Gordon, DeMets 2011; plates: "
                  "Bird 2003, PB2002, Hugo Ahlenius, Nordpil",
        "step": STEP,
        "plates": [[c, names[c]] + list(POLES[c]) for c in codes],
        "runs": platemotion.runs(grid),
    }
    with open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, separators=(",", ":"))
    print(OUT, os.path.getsize(OUT), "plates", len(codes),
          "empty cells", int((grid == 0).sum()))


if __name__ == "__main__":
    main(sys.argv[1])
