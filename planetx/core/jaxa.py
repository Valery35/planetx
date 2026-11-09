# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наборы JAXA Earth по участку: значения по месяцам. Расчёт без Qt.

Слово автора от 9 ноября 2026 года «JAXA в анализ». PlanetX Lite 0.26.0
показывает наборы на глобусе, здесь они - данные окна «Данные JAXA»
подменю «Анализ участка»: ряд по месяцам, растр месяца и карта тренда
в проект QGIS. По правилу «одна функция - один дом» показ остаётся
в Lite, анализ - в модуле.

Каталог STAC - data.earth.jaxa.jp/stac/cog/v1/catalog.json, файлы COG
лежат в хранилище Wasabi. Набор - collection.json с дочерними
каталогами месяцев (./2026-10/catalog.json), в месяце уровни 0 и 1.
Уровень 0 - два полушария с пикселем 0.2°, уровень 1 - четыре полосы
долгот по 90° и два полушария по широте. Окно берёт уровень 1,
читается только то, что под участком. Пиксель уровня 1 у наборов
разный: у SGLI 0.025° (около 2.8 км, файл 3600 x 3600), у аэрозоля
0.05°, у осадков и влажности почвы 0.1°. Значение - число файла (DN),
умноженное на slope и сложенное с offset. Числа empty - нет данных
и коды ошибок. Пересчёт сверен с PlanetX Lite (crates/data/src/jaxa.rs),
шаги - с файлами 9 ноября 2026 года.

Условия данных - earth.jaxa.jp/en/data/policy/, подпись CREDIT.
"""
import datetime
import json
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import series
except ImportError:  # headless-тесты
    import series

ROOT = "https://s3.ap-northeast-1.wasabisys.com/je-pds/cog/v1/"
CREDIT = "JAXA Earth"
CREDIT_URL = "https://data.earth.jaxa.jp/"
LEVEL = 1  # уровень набора: квадраты 90°
QUAD = 90.0  # сторона квадрата уровня, градусы
HEAD = 16384  # байт начала файла: заголовок и каталоги

Set = namedtuple("Set", "key id band units slope offset empty stops step")
Set.__doc__ = """Набор: key - ключ окна, id - номер набора STAC, band -
канал в имени файла, units - единица, slope и offset - пересчёт числа
файла, empty - числа без значения, stops - раскраска растра в проекте
[(значение, (R, G, B))], step - пиксель файла уровня 1, градусы."""

# Наборы и раскраски - как строки PlanetX Lite 0.26.0.
SETS = (
    Set("lst",
        "JAXA.G-Portal_GCOM-C.SGLI_standard.L3-LST.daytime.v3_global_monthly",
        "LST", "°C", 0.02, -273.15, (65535.0,),
        ((-30.0, (60, 0, 130)), (-15.0, (40, 60, 220)),
         (0.0, (230, 240, 250)), (15.0, (120, 210, 90)),
         (30.0, (250, 210, 50)), (45.0, (240, 110, 30)),
         (60.0, (150, 10, 30))), 0.025),
    Set("sst",
        "JAXA.G-Portal_GCOM-C.SGLI_standard.L3-SST.daytime.v3_global_monthly",
        "SST", "°C", 0.0012, -10.0, (65535.0,),
        ((-2.0, (50, 0, 110)), (6.0, (40, 90, 220)), (12.0, (70, 200, 220)),
         (18.0, (240, 230, 80)), (24.0, (245, 150, 40)),
         (28.0, (220, 50, 30)), (32.0, (130, 0, 30))), 0.025),
    Set("ndvi",
        "JAXA.G-Portal_GCOM-C.SGLI_standard.L3-NDVI.daytime.v3_global_monthly",
        "NDVI", "", 0.0001, -1.0, (65535.0,),
        ((-0.1, (140, 110, 80)), (0.1, (210, 190, 140)),
         (0.3, (200, 220, 110)), (0.5, (110, 180, 60)),
         (0.7, (40, 130, 40)), (0.9, (0, 70, 20))), 0.025),
    Set("chla",
        "JAXA.G-Portal_GCOM-C.SGLI_standard.L3-CHLA.daytime.v3_global_monthly",
        "CHLA", "мг/м³", 0.0016, 0.0, (65535.0,),
        ((0.03, (40, 20, 120)), (0.1, (30, 80, 200)), (0.3, (40, 170, 210)),
         (1.0, (80, 200, 120)), (3.0, (220, 220, 60)),
         (10.0, (230, 120, 30)), (30.0, (170, 20, 20))), 0.025),
    Set("precip", "JAXA.EORC_GSMaP_standard.Gauge.00Z-23Z.v6_monthly",
        "PRECIP", "мм/ч", 1.0, 0.0, (-999.9, -4.0, -8.0, -99.0),
        ((0.0, (255, 255, 255)), (0.1, (100, 170, 250)),
         (0.25, (40, 110, 230)), (0.5, (60, 40, 200)),
         (1.0, (170, 40, 190)), (2.0, (230, 30, 110))), 0.1),
    Set("smc",
        "JAXA.G-Portal_GCOM-W.AMSR2_standard.L3-SMC.daytime.v3_global_monthly",
        "SMC", "%", 0.1, 0.0,
        (-32768.0, -32761.0, -32762.0, -32763.0, -32764.0, -32765.0,
         -32766.0, -32767.0),
        ((0.0, (170, 110, 50)), (10.0, (220, 190, 110)),
         (20.0, (180, 220, 140)), (30.0, (70, 180, 170)),
         (45.0, (30, 100, 200)), (60.0, (20, 30, 140))), 0.1),
    Set("aod", "JAXA.JASMES_Terra.MODIS-Aqua.MODIS_taua.v811_global_monthly",
        "T500", "", 0.001, 0.0, (65535.0,),
        ((0.0, (255, 255, 210)), (0.1, (250, 230, 140)),
         (0.25, (240, 170, 60)), (0.5, (210, 90, 30)),
         (1.0, (140, 30, 30)), (2.0, (70, 0, 40))), 0.05),
)
BY_KEY = {s.key: s for s in SETS}

Month = namedtuple("Month", "date day point values")
Month.__doc__ = """Месяц ряда: date - «ГГГГ-ММ», day - сутки середины
месяца от 1970-01-01, point - сводка участка (series.Point) или None,
values - сетка значений участка (NaN вне участка и без данных)."""


def collection_url(dataset):
    """Адрес описания набора с месяцами."""
    return "{}{}/collection.json".format(ROOT, dataset.id)


def parse_dates(text):
    """Месяцы набора из collection.json по возрастанию: дочерние каталоги
    вида ./2026-10/catalog.json. Ответ считается враждебным."""
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return []
    links = value.get("links") if isinstance(value, dict) else None
    out = set()
    for link in links if isinstance(links, list) else ():
        if not isinstance(link, dict) or link.get("rel") != "child":
            continue
        href = link.get("href")
        if not isinstance(href, str) or not href.startswith("./") \
                or not href.endswith("/catalog.json"):
            continue
        date = href[2:-len("/catalog.json")]
        if month_day(date) is not None:
            out.add(date)
    return sorted(out)


def month_day(date):
    """Сутки от 1970-01-01 середины месяца «ГГГГ-ММ», None - не месяц."""
    if len(date) != 7 or date[4] != "-":
        return None
    try:
        year, month = int(date[:4]), int(date[5:])
        first = datetime.date(year, month, 1)
    except ValueError:
        return None
    return (first - series.EPOCH).days + 14.5


def between(dates, first, last):
    """Месяцы dates от first до last включительно («ГГГГ-ММ»)."""
    return [d for d in dates if first <= d <= last]


def _lon(value):
    value = int(round(value))
    return "{}{:03d}.00".format("W" if value < 0 else "E", abs(value))


def _lat(value):
    value = int(round(value))
    return "{}{:02d}.00".format("S" if value < 0 else "N", abs(value))


def quad_url(dataset, date, west, south):
    """Адрес файла квадрата уровня 1 с юго-западным углом west, south."""
    east, north = west + QUAD, south + QUAD
    return "{root}{id}/{date}/{level}/{w}-{e}/{w}-{s}-{e}-{n}-{band}.tiff" \
        .format(root=ROOT, id=dataset.id, date=date, level=LEVEL,
                w=_lon(west), e=_lon(east), s=_lat(south), n=_lat(north),
                band=dataset.band)


def quads(box):
    """Углы (запад, юг) квадратов, которые задевает рамка box (запад, юг,
    восток, север). Рамка через линию перемены дат - две части."""
    west, south, east, north = box
    if east < west:
        return quads((west, south, 180.0, north)) \
            + quads((-180.0, south, east, north))
    out = []
    for lon in range(-180, 180, int(QUAD)):
        if lon + QUAD <= west or lon >= east:
            continue
        for lat in (-90, 0):
            if lat + QUAD <= south or lat >= north:
                continue
            out.append((float(lon), float(lat)))
    return out


Grid = namedtuple("Grid", "west north rows cols step")
Grid.__doc__ = """Сетка участка по пикселям уровня: west, north - центр
левого верхнего пикселя, градусы, rows, cols - размер, step - шаг."""


def grid_for(box, step):
    """Сетка пикселей шага step, которые задевает рамка box. Узел -
    середина пикселя, края пикселей на кратных step от -180 и 90."""
    west, south, east, north = box
    c0 = int(math.floor((west + 180.0) / step + 1e-9))
    c1 = int(math.ceil((east + 180.0) / step - 1e-9))
    r0 = int(math.floor((90.0 - north) / step + 1e-9))
    r1 = int(math.ceil((90.0 - south) / step - 1e-9))
    cols, rows = max(c1 - c0, 1), max(r1 - r0, 1)
    return Grid(-180.0 + (c0 + 0.5) * step, 90.0 - (r0 + 0.5) * step,
                rows, cols, step)


def nodes(grid):
    """Широты и долготы узлов сетки массивами (rows, cols)."""
    lats = grid.north - np.arange(grid.rows) * grid.step
    lons = grid.west + np.arange(grid.cols) * grid.step
    return np.meshgrid(lats, lons, indexing="ij")


def to_values(dataset, dn):
    """Значения набора из чисел файла, NaN - нет данных."""
    dn = np.asarray(dn, dtype=np.float64)
    bad = ~np.isfinite(dn)
    for empty in dataset.empty:
        bad |= np.abs(dn - empty) < 1e-3
    out = dn * dataset.slope + dataset.offset
    out[bad] = np.nan
    return out


def read_grid(dataset, grid, block):
    """Сетка чисел файла участка: block(запад, юг, c0, r0, c1, r1) -
    пиксели c0..c1, r0..r1 файла квадрата (float, NaN - нет тайла) или
    None - файла нет. Возвращает значения набора (rows, cols)."""
    step = grid.step
    out = np.full((grid.rows, grid.cols), np.nan)
    # Номера пикселей сетки в мировой нумерации от -180 и 90.
    gc0 = int(round((grid.west + 180.0) / step - 0.5))
    gr0 = int(round((90.0 - grid.north) / step - 0.5))
    side = int(round(QUAD / step))
    west = -180.0 + gc0 * step
    east = west + grid.cols * step
    north = 90.0 - gr0 * step
    south = north - grid.rows * step
    for qw, qs in quads((west, south, east, north)):
        qc0 = int(round((qw + 180.0) / step))
        qr0 = int(round((90.0 - qs - QUAD) / step))
        c0, c1 = max(gc0, qc0), min(gc0 + grid.cols, qc0 + side) - 1
        r0, r1 = max(gr0, qr0), min(gr0 + grid.rows, qr0 + side) - 1
        if c1 < c0 or r1 < r0:
            continue
        part = block(qw, qs, c0 - qc0, r0 - qr0, c1 - qc0, r1 - qr0)
        if part is None:
            continue
        out[r0 - gr0:r1 - gr0 + 1, c0 - gc0:c1 - gc0 + 1] = \
            to_values(dataset, part)
    return out


def step_fits(dataset, transform):
    """Пиксель файла (геопреобразование COG) - шаг набора, начало -
    угол квадрата. Иначе файл не той сетки и не читается."""
    dx, dy = transform[1], transform[5]
    return abs(dx - dataset.step) < dataset.step * 1e-6 \
        and abs(dy + dataset.step) < dataset.step * 1e-6


def area_mask(grid, inside):
    """Пиксели участка: inside(широты, долготы) - маска многоугольника.
    Участок меньше пикселя берёт пиксель своей середины."""
    lats, lons = nodes(grid)
    mask = np.asarray(inside(lats, lons), dtype=bool)
    if not mask.any():
        mask[grid.rows // 2, grid.cols // 2] = True
    return mask


def month_of(dataset, date, grid, mask, block):
    """Месяц ряда: значения участка и сводка по ним."""
    values = read_grid(dataset, grid, block)
    values[~mask] = np.nan
    point = series.point(values, mask, np.ones(mask.shape, dtype=bool))
    return Month(date, month_day(date), point, values)


def same_month(months, date):
    """Месяцы ряда с тем же месяцем года, что у date: ряд одного сезона
    для тренда между годами."""
    return [m for m in months if m.date[5:] == date[5:]]


def csv_text(dataset, months, title):
    """Ряд таблицей CSV: месяц, медиана, процентили, доля участка со
    значением."""
    rows = [(m.date, dataset.band, m.point) for m in months]
    return series.csv_text(rows, title).replace(
        "date,scene,", "month,band,", 1).replace(
        "clear_percent", "valid_percent", 1)
