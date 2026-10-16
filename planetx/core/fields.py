# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты значений геофизики - тайлы значений и раскраска.

Магнитные аномалии EMAG2v3 (core/emag.py) были первой такой картой.
Возраст океанического дна, аномалии силы тяжести и тепловой поток -
просьба автора от 16 октября 2026 года - ложатся тем же путём: сетку
источника режет tools/build_field.py в planetx-terrain/<папка> тайлами
Web Mercator уровней 0-max_level в записи Terrarium. Код
R * 256 + G + B / 256 - 32768 - значение, умноженное на scale, «нет
данных» - (0, 0, 0). Модуль раскрашивает тайл в рабочем потоке (rgba),
значение под щелчком берёт из тайла (value_at).

У шейдера тайла свободных текстурных блоков больше нет, все карты
значений делят блок 15 слоя вида «emag». На глобусе одна такая карта,
включение другой снимает прежнюю.

Модуль Qt не знает.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import emag
except ImportError:  # headless-тесты
    import emag

TERRAIN = "https://raw.githubusercontent.com/Valery35/planetx-terrain/main/"
EMPTY = -32768.0
SIZE = 256

Field = namedtuple("Field", "key folder max_level scale stops ticks unit "
                            "digits attribution opacity")
Field.__doc__ = """Карта значений: key - ключ строки «Слоёв», folder -
папка planetx-terrain, max_level - глубший уровень тайлов, scale - код
на единицу значения, stops - раскраска (значение, (r, g, b)), ticks -
подписи шкалы, unit - единица, digits - знаков после запятой в окне
«Объекты», attribution - (подпись, адрес), opacity - непрозрачность."""

# Раскраски и пределы - выбор помощника, утверждает автор.
FIELDS = {
    "emag": Field("emag", "emag", emag.MAX_LEVEL, 1.0, emag.STOPS,
                  (-250, -120, 0, 120, 250), "nT", 0, emag.ATTRIBUTION,
                  emag.OPACITY),
    # Возраст океанической коры, Seton и соавторы 2020, EarthByte, сетка
    # 6' (0.1°), шкала GeeK2007, млн лет, CC BY 4.0. Молодое дно у
    # хребтов красное, древнее - синее и фиолетовое, как на картах
    # авторов.
    "seafloor_age": Field(
        "seafloor_age", "seafloor_age", 5, 10.0,
        ((0.0, (230, 40, 40)), (20.0, (245, 150, 40)),
         (40.0, (245, 230, 70)), (70.0, (110, 200, 90)),
         (110.0, (60, 170, 200)), (160.0, (60, 90, 200)),
         (200.0, (120, 60, 180)), (280.0, (80, 30, 110))),
        (0, 50, 100, 150, 200, 250), "Ma", 1,
        ("Seafloor age: Seton et al. 2020, EarthByte, CC BY 4.0",
         "https://www.earthbyte.org/a-global-dataset-of-present-day-"
         "oceanic-crustal-age-and-seafloor-spreading-parameters/"), 0.8),
    # Тепловой поток, сетка кригинга базы IHFC 2024 (Petrunin и
    # соавторы 2026), 0.5°, мВт/м², CC BY 4.0.
    "heatflow": Field(
        "heatflow", "heatflow", 3, 10.0,
        ((0.0, (40, 50, 140)), (40.0, (60, 120, 210)),
         (60.0, (130, 200, 220)), (80.0, (245, 235, 160)),
         (100.0, (245, 170, 70)), (150.0, (220, 70, 40)),
         (250.0, (130, 20, 30))),
        (0, 50, 100, 150, 200, 250), "mW/m2", 0,
        ("Heat flow: IHFC Global Heat Flow Database 2024, Petrunin et al. "
         "2026, CC BY 4.0", "https://doi.org/10.5880/gfz.khag.2026.004"),
        0.75),
    # Аномалия силы тяжести в свободном воздухе по модели XGM2019e
    # (Zingerle и соавторы 2020, ICGEM, CC BY 4.0), синтез до степени
    # 719 (tools/build_gravity.py), сетка 0.25°, мГал.
    "gravity": Field(
        "gravity", "gravity", 5, 10.0,
        ((-200.0, (30, 40, 130)), (-80.0, (60, 120, 210)),
         (-20.0, (170, 210, 235)), (0.0, (245, 245, 240)),
         (20.0, (245, 210, 150)), (80.0, (230, 120, 60)),
         (200.0, (150, 30, 30))),
        (-200, -100, 0, 100, 200), "mGal", 0,
        ("Gravity: XGM2019e, Zingerle et al. 2020, ICGEM, CC BY 4.0",
         "https://doi.org/10.5880/ICGEM.2019.007"), 0.75),
    # Аномалия Буге - та же аномалия минус простая поправка Буге плюс
    # поправка на рельеф вокруг по рельефу ETOPO 2022
    # (tools/build_bouguer.py), сетка 0.25°, мГал.
    # Под горами до -500, над океаном до +450, пределы шкалы шире.
    "bouguer": Field(
        "bouguer", "bouguer", 5, 10.0,
        ((-400.0, (30, 40, 130)), (-200.0, (60, 120, 210)),
         (-60.0, (170, 210, 235)), (0.0, (245, 245, 240)),
         (60.0, (245, 210, 150)), (200.0, (230, 120, 60)),
         (400.0, (150, 30, 30))),
        (-400, -200, 0, 200, 400), "mGal", 0,
        ("Bouguer anomaly: XGM2019e, Zingerle et al. 2020, ICGEM, "
         "CC BY 4.0; relief: ETOPO 2022, NOAA NCEI",
         "https://doi.org/10.5880/ICGEM.2019.007"), 0.75),
}
# Порядок строк каталога.
KEYS = ("emag", "gravity", "bouguer", "seafloor_age", "heatflow")


def url(field, base=TERRAIN):
    """Шаблон адреса тайлов карты."""
    return base + field.folder + "/{z}/{x}/{y}.png"


def encode(values, scale=1.0):
    """Значения (NaN - нет данных) в RGB uint8 записи Terrarium с
    множителем scale."""
    values = np.asarray(values, dtype=np.float64)
    code = np.clip(np.round(values * scale) + 32768.0, 1.0, 65535.0)
    code = np.where(np.isnan(values), 0.0, code).astype(np.int64)
    rgb = np.zeros(values.shape + (3,), np.uint8)
    rgb[..., 0] = code >> 8
    rgb[..., 1] = code & 255
    return rgb


def decode(rgb, scale=1.0):
    """RGB (строки, столбцы, 3+) в значения, NaN - нет данных."""
    rgb = np.asarray(rgb)
    code = rgb[..., 0].astype(np.float32) * 256.0 \
        + rgb[..., 1].astype(np.float32) \
        + rgb[..., 2].astype(np.float32) / 256.0 + EMPTY
    empty = code <= EMPTY + 0.5
    values = code / np.float32(scale)
    values[empty] = np.nan
    return values


def colors(field, values):
    """Значения в RGBA uint8 с премноженной альфой, пусто - прозрачно."""
    values = np.asarray(values, dtype=np.float64)
    at = np.array([s for s, _ in field.stops])
    out = np.zeros(values.shape + (4,), np.uint8)
    clean = np.nan_to_num(values, nan=float(at[0]))
    for k in range(3):
        channel = np.interp(clean, at, [c[k] for _, c in field.stops])
        out[..., k] = np.round(channel * field.opacity).astype(np.uint8)
    out[..., 3] = int(round(255 * field.opacity))
    out[np.isnan(values)] = 0
    return out


def rgba(field, tile_rgba):
    """Тайл записи Terrarium (RGBA загрузчика) в раскраску."""
    return colors(field, decode(tile_rgba, field.scale))


def pixel_of(lat, lon, z):
    """Тайл (x, y) уровня z и пиксель (столбец, строка) точки."""
    lat = max(min(lat, 85.0511), -85.0511)
    world = SIZE * 2 ** z
    gx = (lon + 180.0) / 360.0 * world
    gy = (1.0 - math.log(math.tan(math.radians(lat))
                         + 1.0 / math.cos(math.radians(lat))) / math.pi) \
        / 2.0 * world
    gx = min(max(gx, 0.0), world - 1e-6)
    gy = min(max(gy, 0.0), world - 1e-6)
    return ((int(gx // SIZE), int(gy // SIZE)),
            (int(gx % SIZE), int(gy % SIZE)))


def value_at(field, tile_rgb, column, row):
    """Значение пикселя тайла или None."""
    value = float(decode(np.asarray(tile_rgb)[row:row + 1,
                                              column:column + 1],
                         field.scale)[0, 0])
    return None if math.isnan(value) else value
