# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Заросшие поля по ряду весенних и осенних снимков.

Мысль Василия Швалёва от 3 ноября 2026 года - пары «осень - весна»
и «весна - весна разных лет», заросшее поле - то, что несколько сезонов
не обрабатывалось. Слово автора того же дня «делай осень-весну
и заросшие поля», выбор - ряд за 4 года.

Пашня весной до всходов и осенью после уборки и зяби - голая почва,
у залежи по весне старая трава и кустарник. Поэтому у каждого поля
летнего снимка (область трассировки) по снимкам весны и осени за годы
видно, в каком году на нём последний раз была голая почва. Голая клетка -
NDVI ниже BARE_NDVI. Прогон 3 ноября 2026 года у Шадейки (57.43, 56.80)
по снимкам Sentinel-2 мая и сентября - октября 2023-2026 годов: пашня
весной 0.10-0.25, сухая ветошь залежи 0.35-0.5, всходы и травы выше 0.6,
порог 0.3 отделил пашню от ветоши на всех восьми снимках. Деревья
на летнем снимке - NDMI (B8 - B11) / (B8 + B11) выше WOODY_NDMI: лес
у Шадейки 0.3-0.45, луга и посевы августа 0.1-0.3, но 31 июля 2026 года
у посевов и лугов 0.32-0.38. Поэтому деревья берутся по ряду сезонов
(season_woody), летний NDMI - запасной путь. Пороги - выбор помощника,
утверждает автор.

Многолетние травы на сенокосе за годы ряда тоже ни разу не голые -
они выходят залежью, это ограничение способа.
"""
import numpy as np

try:  # внутри плагина QGIS
    from . import objecttasks as ot
except ImportError:  # headless-тесты
    import objecttasks as ot

YEARS = 4  # лет ряда, выбор автора от 3 ноября 2026 года
SPRING = (5, 4)  # месяцы весны по порядку предпочтения
AUTUMN = (9, 10)
BARE_NDVI = 0.3  # голая почва межсезонного снимка
BARE_SHARE = 0.25  # доля голых клеток поля, с которой поле обрабатывалось
KNOWN_SHARE = 0.5  # доля клеток поля с данными, чтобы снимок считался
ALWAYS_BARE = 0.8  # голое на такой доле снимков - не поле, застройка
WOODY_SWIR = 0.09  # дерево - медиана SWIR снимков сезонов ниже
WOODY_NDMI = 0.3  # дерево на летнем снимке, если у сезонов нет SWIR
WOODY_SHARE = 0.25  # доля деревьев залежи, с которой она зарастает
FOREST_SHARE = 0.7  # доля деревьев, с которой область - лес
RECENT = 2  # лет без обработки, которые ещё «недавно»

# Виды полей.
TILLED, FALLOW_NEW, FALLOW_OLD, OVERGROWN, FOREST = (
    "tilled", "fallow_new", "fallow_old", "overgrown", "forest")
KINDS = (TILLED, FALLOW_NEW, FALLOW_OLD, OVERGROWN, FOREST)
# Цвета видов: от бурой пашни к тёмному лесу - выбор помощника.
COLORS = {TILLED: (190, 135, 80), FALLOW_NEW: (240, 200, 70),
          FALLOW_OLD: (175, 205, 95), OVERGROWN: (95, 150, 60),
          FOREST: (25, 90, 45)}
# Летние виды, из которых бывают поля.
FIELD_SOURCES = (ot.CONIFER, ot.BROADLEAF, ot.VEGETATION, ot.SOIL,
                 ot.CLEARING, ot.OTHER)


def _band(bands, roles, role):
    roles = list(roles)
    return np.asarray(bands[roles.index(role)], dtype=np.float64) \
        if role in roles else None


def bare_cells(bands, roles):
    """Голые клетки межсезонного снимка: 1 - голая почва, 0 - растения,
    NaN - нет данных, вода или снег. Нужны красный и ближний ИК."""
    red, nir = _band(bands, roles, "red"), _band(bands, roles, "nir")
    if red is None or nir is None:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        ndvi = (nir - red) / (nir + red)
    out = (ndvi < BARE_NDVI).astype(np.float64)
    unknown = ~np.isfinite(ndvi) | (nir < ot.WATER_NIR)
    swir = _band(bands, roles, "swir1")
    if swir is None:
        swir = _band(bands, roles, "swir2")
    snow = red > ot.SNOW_VIS
    if swir is not None:
        snow &= swir < ot.SNOW_SWIR
    out[unknown | snow] = np.nan
    return out


def season_woody(scenes):
    """Деревья по ряду снимков весны и осени: медиана SWIR 2,2 мкм (без
    него - 1,6 мкм) по снимкам ниже WOODY_SWIR. scenes - [(каналы, роли)],
    снег и нет данных - не в счёт. None - ни у одного снимка нет SWIR.

    Лес тёмный в SWIR круглый год от теней полога и воды в листве,
    трава и сухая ветошь залежи весной и осенью светлые. Прогон у Шадейки
    3 ноября 2026 года, 8 снимков 2023-2026 годов: хвойный и смешанный лес
    0.03-0.08, луга и залежь 0.10-0.20, пашня 0.15-0.30. Летний NDMI на
    снимке 31 июля 2026 года этого не делил - у пышных посевов и лугов он
    0.32-0.38, как у леса."""
    rows = []
    for bands, roles in scenes:
        swir = _band(bands, roles, "swir2")
        if swir is None:
            swir = _band(bands, roles, "swir1")
        bare = bare_cells(bands, roles)
        if swir is None or bare is None:
            continue
        rows.append(np.where(np.isfinite(bare), swir, np.nan))
    if not rows:
        return None
    stack = np.stack(rows)
    known = np.isfinite(stack).any(axis=0)
    # nanmedian клетки без единого значения дала бы предупреждение.
    stack[:, ~known] = 0.0
    median = np.nanmedian(stack, axis=0)
    median[~known] = np.nan
    out = (median < WOODY_SWIR).astype(np.float64)
    out[~np.isfinite(median)] = np.nan
    return out


def woody_cells(bands, roles):
    """Деревья летнего снимка по NDMI, None - нет ближнего ИК и SWIR.
    Запасной путь, если у снимков сезонов нет SWIR."""
    nir, swir = _band(bands, roles, "nir"), _band(bands, roles, "swir1")
    if nir is None or swir is None:
        return None
    with np.errstate(invalid="ignore", divide="ignore"):
        ndmi = (nir - swir) / (nir + swir)
    return ndmi > WOODY_NDMI


def _per_region(parts, values, count):
    """Сумма values и количество клеток с данными по областям."""
    parts = np.asarray(parts)
    good = (parts >= 0) & np.isfinite(values)
    total = np.bincount(parts[good], weights=values[good], minlength=count)
    known = np.bincount(parts[good], minlength=count)
    return total[:count], known[:count]


def tilled_years(parts, scenes, count):
    """По областям: {год: обрабатывалось ли} и количество голых и
    учтённых снимков. scenes - [(год, голые клетки bare_cells)].
    Снимок учтён у области, если данные есть на KNOWN_SHARE её клеток."""
    parts = np.asarray(parts)
    cells = np.bincount(parts[parts >= 0], minlength=count)[:count]
    years = [dict() for _ in range(count)]
    bare = np.zeros(count, dtype=np.int64)
    seen = np.zeros(count, dtype=np.int64)
    for year, values in scenes:
        total, known = _per_region(parts, values, count)
        enough = known >= KNOWN_SHARE * np.maximum(cells, 1)
        tilled = enough & (total >= BARE_SHARE * np.maximum(known, 1))
        for n in np.nonzero(enough)[0]:
            years[n][year] = years[n].get(year, False) or bool(tilled[n])
        seen += enough
        bare += tilled
    return years, bare, seen


def woody_shares(parts, woody, count):
    if woody is None:
        return None
    total, known = _per_region(parts, np.asarray(woody, dtype=np.float64),
                               count)
    return total / np.maximum(known, 1)


def field_kinds(summer, years, bare, seen, woody, newest):
    """Виды областей. summer - виды по летнему снимку (region_kinds),
    years - tilled_years, woody - доли деревьев или None, newest - самый
    новый год ряда. Итог - (виды, последний год голой почвы или 0)."""
    kinds, last = [], []
    for n, kind in enumerate(summer):
        tilled = sorted(y for y, t in years[n].items() if t)
        last.append(tilled[-1] if tilled else 0)
        tree = woody[n] if woody is not None else (
            1.0 if kind == ot.CONIFER else 0.0)
        if kind not in FIELD_SOURCES or not years[n]:
            kinds.append(kind)
        elif kind == ot.SOIL and seen[n] >= 3 \
                and bare[n] >= ALWAYS_BARE * seen[n]:
            # Голое и летом, и почти на всех снимках сезонов - застройка,
            # дороги, карьер. Пашня летом под посевом.
            kinds.append(ot.SOIL)
        elif tilled:
            age = newest - tilled[-1]
            kinds.append(TILLED if age <= 0 else FALLOW_NEW if age <= RECENT
                         else OVERGROWN if tree >= WOODY_SHARE
                         else FALLOW_OLD)
        else:
            kinds.append(FOREST if tree >= FOREST_SHARE
                         else OVERGROWN if tree >= WOODY_SHARE
                         else FALLOW_OLD)
    return kinds, last


# Классы заросших полей окна «Распознавание» по порядку слоя.
ROWS = KINDS + (ot.CONIFER, ot.BROADLEAF, ot.VEGETATION, ot.CLEARING,
                ot.SOIL, ot.WATER, ot.SNOW, ot.OTHER)


def field_cells(grid, roles, good, seasons):
    """Заросшие поля окна «Распознавание»: grid - каналы летнего снимка
    (roles), за ними снимки весны и осени seasons [(год, роли, каналов)].
    Области - по летнему снимку (objecttasks.summer_regions), вид поля -
    по годам голой почвы. Итог - (номер класса ROWS у клетки, -1 вне
    good, области клеток, летние виды областей, учтённых снимков)."""
    first = len(roles)
    out = np.full(good.shape, -1, dtype=np.int64)
    found = ot.summer_regions(grid[:first], roles, None, good, "fallow")
    if found is None:
        return out, None, [], 0
    parts, summer = found
    count = len(summer)
    scenes, stacks, at = [], [], first
    for year, season_roles, bands in seasons:
        block = grid[at:at + bands]
        at += bands
        stacks.append((block, season_roles))
        cells = bare_cells(block, season_roles)
        if cells is not None and np.isfinite(cells).any():
            scenes.append((year, cells))
    trees = season_woody(stacks)
    if trees is None:
        trees = woody_cells(grid[:first], roles)
    woody = woody_shares(parts, trees, count)
    years, bare, seen = tilled_years(parts, scenes, count)
    newest = max((y for y, _ in scenes), default=0)
    kinds, _ = field_kinds(summer, years, bare, seen, woody, newest)
    codes = np.array([ROWS.index(k) for k in kinds] + [-1], dtype=np.int64)
    out[:] = codes[np.where(parts >= 0, parts, count)]
    out[~good] = -1
    return out, parts, summer, len(scenes)


# Лучший день сезона: конец мая - пашня ещё голая, залежь уже зелёная,
# начало октября - урожай убран, зябь вспахана, снега ещё нет. Прогон
# у Шадейки 3 ноября 2026 года: снимок 1 сентября 2026 года застал поля
# под неубранным хлебом, пашни вышло 3 % участка.
BEST_DAY = {"spring": 145, "autumn": 274}  # день года
CLOUD_STEP = 2.0  # облачность в процентах, которая не различается


def _day_of_year(when):
    month, day = int(when[5:7]), int(when[8:10])
    return (0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334)[
        month - 1] + day


def pick(found, seasons=(("spring", SPRING), ("autumn", AUTUMN))):
    """Лучший снимок на год и сезон: found - [(сцена, облачность,
    данные)], итог {(год, сезон): [(сцена, облачность, данные), ...]} -
    лучший первым: меньше облаков (с шагом CLOUD_STEP), ближе к BEST_DAY
    сезона."""
    out = {}
    for scene, cloud, valid in found:
        month = int(scene.when[5:7])
        for name, months in seasons:
            if month in months:
                out.setdefault((int(scene.when[:4]), name), []).append(
                    (scene, cloud, valid))
    for (_, name), rows in out.items():
        best = BEST_DAY.get(name, 0)
        rows.sort(key=lambda r: (int(r[1] // CLOUD_STEP),
                                 abs(_day_of_year(r[0].when) - best),
                                 r[0].when))
    return out
