# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Геоид EGM2008 - «измятый глобус».

Высота геоида над эллипсоидом WGS84 по модели EGM2008 (NGA, 2008),
сетка 5' из набора GeographicLib egm2008-5.pgm. Тайлы уровней
0-MAX_LEVEL в записи Terrarium (метры) режет tools/build_geoid.py
в planetx-terrain/geoid. В режиме геоида высоты Земли берутся из этих
тайлов вместо рельефа и растягиваются в SCALE раз - горбы и впадины
геоида от -107 до +86 м становятся видны с орбиты.

Модуль Qt не знает.
"""
import numpy as np

MAX_LEVEL = 4
TILE_URL = ("https://raw.githubusercontent.com/Valery35/planetx-terrain/"
            "main/geoid/{z}/{x}/{y}.png")
ATTRIBUTION = ("EGM2008, NGA", "https://earth-info.nga.mil/")
# Вертикальный масштаб режима: 100 м геоида - 1000 км на экране. Выбор
# помощника, утверждает автор.
SCALE = 10000.0
# Ступени ползунка масштаба меню «⋯» строки «Геоид», просьба
# пользователя от 14 октября 2026 года. Ступени - выбор помощника.
SCALES = (1000.0, 2000.0, 3000.0, 5000.0, 7000.0, 10000.0, 15000.0,
          20000.0)


def scale_step(scale):
    """Номер ступени SCALES, ближайшей к масштабу scale."""
    return min(range(len(SCALES)), key=lambda i: abs(SCALES[i] - scale))


def scale_text(scale):
    """Масштаб для подписи - «×10 000»."""
    return "×{:,}".format(int(round(scale))).replace(",", " ")


def encode(heights):
    """Метры (NaN - нет данных) в RGB uint8 записи Terrarium:
    высота = R * 256 + G + B / 256 - 32768."""
    heights = np.asarray(heights, dtype=np.float64)
    code = np.clip(np.nan_to_num(heights, nan=0.0) + 32768.0, 0.0,
                   65535.996)
    whole = np.floor(code)
    rgb = np.zeros(heights.shape + (3,), np.uint8)
    rgb[..., 0] = (whole // 256).astype(np.uint8)
    rgb[..., 1] = (whole % 256).astype(np.uint8)
    rgb[..., 2] = np.minimum(np.round((code - whole) * 256.0),
                             255).astype(np.uint8)
    return rgb


def read_pgm(data):
    """Сетка GeographicLib PGM (P5, 16 бит) в метры: строки с севера от
    90°, столбцы с востока от 0°, шаг. Смещение и шкала - из
    комментариев # Offset и # Scale."""
    offset = scale = None
    pos = 0
    fields = []
    while len(fields) < 4:
        end = data.index(b"\n", pos)
        line = data[pos:end].decode("ascii").strip()
        pos = end + 1
        if line.startswith("#"):
            parts = line[1:].split()
            if parts[:1] == ["Offset"]:
                offset = float(parts[1])
            elif parts[:1] == ["Scale"]:
                scale = float(parts[1])
            continue
        fields += line.split()
    if fields[0] != "P5" or offset is None or scale is None:
        raise ValueError("not a GeographicLib geoid PGM")
    width, height = int(fields[1]), int(fields[2])
    raw = np.frombuffer(data, dtype=">u2", count=width * height,
                        offset=pos).reshape(height, width)
    return offset + scale * raw.astype(np.float64), 360.0 / width
