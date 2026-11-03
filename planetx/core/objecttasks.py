# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Типовые задачи выделения объектов поверх трассировки.

Мысль Василия Швалёва от 3 ноября 2026 года, выбор автора того же дня
(вариант Б): сценарий - настройки трассировки плюс правила названий
классов по спектру источника. На сочетании Sentinel «Сельское хозяйство»
(B11 B8 B2) тёмно-зелёный - хвоя, светло-зелёный - листва и травы,
розовый - открытая почва, рядом с лесом - рубки, без леса - поля.

Правило работает по средним отражениям цвета трассировки в каналах,
поэтому каналы снимка нужно знать: подписи каналов файла «Космоснимков»
(«B11 swir16») или имя файла «S2_20240701_40VDK_agriculture»
(channels). Нужен ближний ИК и красный или SWIR 1,6 мкм. У подложки
глобуса и растра без подписей каналов правил нет.

Пороги отражения - по типичным спектрам USGS Spectral Library и практике
дешифрирования Sentinel-2 и Landsat, выбор помощника, проверяются на
снимках Василия. Хвоя от листвы отделяется не порогом, а внутри снимка:
тёмная по ближнему ИК часть растительности.
"""
import re

import numpy as np

try:  # внутри плагина QGIS
    from . import segments
    from .sentinel import COMPOSITES
except ImportError:  # headless-тесты
    import segments
    from sentinel import COMPOSITES

# Роли каналов: ключи каталога Earth Search и Planetary Computer.
ROLES = {"blue": "blue", "green": "green", "red": "red",
         "nir": "nir", "nir08": "nir", "swir16": "swir1",
         "swir22": "swir2", "coastal": "coastal",
         "rededge1": "re1", "rededge2": "re2", "rededge3": "re3",
         "nir09": "vapour", "lwir": "thermal"}
FILE = re.compile(r"^(S2|L[CEOTM]?\d|LM\d)_(\d{8})_.*_([a-z_]+?)$")

# Пороги отражения - выбор помощника.
WATER_NIR = 0.07  # вода темнее в ближнем ИК
WATER_SWIR = 0.05
VEG_NDVI = 0.35  # растительность по (nir - red) / (nir + red)
VEG_NDMI = 0.05  # по (nir - swir1) / (nir + swir1), если красного нет
SNOW_VIS = 0.35  # снег ярок в видимом и тёмен в SWIR
SNOW_SWIR = 0.15
CONIFER_SHARE = 0.4  # нижняя доля размаха ближнего ИК растительности
CONIFER_SPREAD = 0.05  # размах ниже этого - хвою не отделить
EVERGREEN = 0.75  # ИК меньшей даты к большей у хвои по двум снимкам
WINTER_DARK = 0.25  # видимая яркость хвои на снежном снимке не выше
REFLECTANCE_MAX = 1.5  # значения выше - не отражение
NEAR_FOREST = 0.25  # доля хвои вокруг почвы, с которой это рубка
RIM = 3  # клеток, ширина полосы вокруг куска почвы
THICK = 0.5  # доля внутренних клеток куска хвои, с которой это лес

# Виды цветов.
WATER, CONIFER, BROADLEAF, VEGETATION, SOIL, CLEARING, SNOW, OTHER = (
    "water", "conifer", "broadleaf", "vegetation", "soil", "clearing",
    "snow", "other")

# Сценарии: настройки трассировки и какие виды различаются. Вид, которого
# в списке нет, переходит в замену (MERGE), без замены - «прочее».
SCENARIOS = {
    "forest": {"colors": 8, "smooth": 1, "least": 25,
               "kinds": (CONIFER, BROADLEAF, CLEARING, SOIL, WATER, SNOW),
               "merge": {VEGETATION: BROADLEAF}},
    "fields": {"colors": 8, "smooth": 1, "least": 50,
               "kinds": (VEGETATION, SOIL, CLEARING, WATER, SNOW),
               "merge": {CONIFER: VEGETATION, BROADLEAF: VEGETATION}},
    # Заросшие поля (core/fallow.py): летние виды - основа, вид поля
    # даёт ряд снимков весны и осени.
    "fallow": {"colors": 8, "smooth": 1, "least": 50,
               "kinds": (CONIFER, BROADLEAF, SOIL, WATER, SNOW),
               "merge": {VEGETATION: BROADLEAF}},
    "water": {"colors": 4, "smooth": 1, "least": 25,
              "kinds": (WATER, OTHER),
              "merge": {CONIFER: OTHER, BROADLEAF: OTHER, VEGETATION: OTHER,
                        SOIL: OTHER, CLEARING: OTHER, SNOW: OTHER}},
}
# Цвета вида в слое - выбор помощника.
KIND_COLORS = {WATER: (40, 110, 220), CONIFER: (20, 90, 40),
               BROADLEAF: (110, 190, 80), VEGETATION: (90, 170, 70),
               SOIL: (205, 160, 110), CLEARING: (230, 80, 160),
               SNOW: (235, 240, 250), OTHER: (150, 150, 150)}
# Порядок класса в слое.
KIND_ORDER = (CONIFER, BROADLEAF, VEGETATION, CLEARING, SOIL, WATER, SNOW,
              OTHER)


def channels(descriptions, file_stem):
    """Роли каналов растра по подписям каналов (последнее слово подписи -
    ключ каталога, «B11 swir16») или по имени файла «Космоснимков».
    Итог - список ролей по каналам или None."""
    found = []
    for text in descriptions or ():
        words = re.split(r"[\s,]+", (text or "").strip().lower())
        role = next((ROLES[w] for w in reversed(words) if w in ROLES), None)
        found.append(role)
    if found and any(found):
        return found
    match = FILE.match(re.sub(r"_\d+$", "", file_stem or ""))
    if match and match.group(3) in COMPOSITES:
        return [ROLES[k] for k in COMPOSITES[match.group(3)]]
    return None


def month_of(file_stem):
    """Месяц съёмки по имени файла «Космоснимков», None - не узнать."""
    day = day_of(file_stem)
    return int(day[5:7]) if day else None


def day_of(file_stem):
    """День съёмки «ГГГГ-ММ-ДД» по имени файла «Космоснимков» или None."""
    match = FILE.match(re.sub(r"_\d+$", "", file_stem or ""))
    if not match:
        return None
    raw = match.group(2)
    return "{}-{}-{}".format(raw[:4], raw[4:6], raw[6:])


def role_names(roles):
    """Роли каналов, которые узнало окно, по порядку без повторов."""
    seen = []
    for role in roles or ():
        if role and role not in seen:
            seen.append(role)
    return seen


def usable(roles):
    """Хватает ли каналов для правил: ближний ИК и красный или SWIR."""
    roles = roles or ()
    return "nir" in roles and ("red" in roles or "swir1" in roles)


def _ratio(a, b):
    total = a + b
    return (a - b) / total if total > 1e-6 else 0.0


def color_kinds(centers, roles):
    """Вид каждого цвета трассировки по средним каналов centers (цвета,
    каналы) и ролям каналов: вода, хвоя, листва, почва, снег. Хвоя -
    тёмная по ближнему ИК доля растительности, если размах её ИК больше
    CONIFER_SPREAD, иначе вся растительность - vegetation."""
    centers = np.asarray(centers, dtype=np.float64)
    at = {role: n for n, role in enumerate(roles) if role}
    kinds = []
    for row in centers:
        get = {role: float(row[n]) for role, n in at.items()}
        nir = get["nir"]
        swir = get.get("swir1")
        visible = [get[r] for r in ("blue", "green", "red") if r in get]
        if visible and min(visible) > SNOW_VIS \
                and (swir is None or swir < SNOW_SWIR):
            kinds.append(SNOW)
        elif nir < WATER_NIR and (swir is None or swir < WATER_SWIR):
            kinds.append(WATER)
        elif ("red" in get and _ratio(nir, get["red"]) > VEG_NDVI) or (
                "red" not in get and _ratio(nir, swir) > VEG_NDMI):
            kinds.append(VEGETATION)
        else:
            kinds.append(SOIL)
    veg = [n for n, k in enumerate(kinds) if k == VEGETATION]
    if len(veg) > 1:
        nirs = centers[veg, at["nir"]]
        low, high = float(nirs.min()), float(nirs.max())
        if high - low > CONIFER_SPREAD:
            edge = low + CONIFER_SHARE * (high - low)
            for n, value in zip(veg, nirs):
                kinds[n] = CONIFER if value <= edge else BROADLEAF
    return kinds


def winter(centers, roles, more_roles):
    """Видимая яркость второго снимка по цветам, если на нём лежит снег,
    иначе None. Снег - хотя бы у одного цвета видимые каналы ярче
    SNOW_VIS, а SWIR, если он есть, темнее SNOW_SWIR."""
    more_roles = list(more_roles or ())
    visible = [len(roles) + n for n, r in enumerate(more_roles)
               if r in ("blue", "green", "red")]
    if not visible:
        return None
    centers = np.asarray(centers, dtype=np.float64)
    bright = centers[:, visible].min(axis=1)
    if "swir1" in more_roles:
        swir = centers[:, len(roles) + more_roles.index("swir1")]
        snowy = (bright > SNOW_VIS) & (swir < SNOW_SWIR)
    else:
        snowy = bright > SNOW_VIS
    return bright if snowy.any() else None


def two_dates(kinds, centers, roles, more_roles):
    """Виды цветов по двум снимкам: centers - средние каналов первого
    снимка и за ними второго, roles и more_roles - их роли.

    Второй снимок со снегом (зима - лето, просьба автора от 3 ноября
    2026 года): хвоя - растительность, которая на снегу осталась тёмной
    в видимых каналах (темнее WINTER_DARK) и летом не светлая в ближнем
    ИК (вид первого снимка - хвоя или растительность без разделения).
    Остальная растительность - листва и травы. Голый лиственный лес
    на снегу бывает тёмным от стволов и теней - его отличает яркий летний
    ИК, тёмный луг или болото летом похожи на хвою - их отличает снег.
    Снимок 17 апреля 2026 года у 59.99, 57.43 по одному снегу дал хвои
    90 % участка, вместе с летним ИК - 47 %. У снега ближний ИК высокий,
    поэтому правило ИК на снегу не годится.

    Без снега: растительность, у которой ближний ИК на двух датах почти
    не меняется (меньшее к большему не ниже EVERGREEN), - хвоя, остальная -
    листва и травы, они в другой сезон теряют отражение ИК. Без ближнего
    ИК у второго снимка виды остаются прежними."""
    more_roles = list(more_roles or ())
    veg = (CONIFER, BROADLEAF, VEGETATION)
    snow = winter(centers, roles, more_roles)
    if snow is not None:
        return [(CONIFER if b < WINTER_DARK and k != BROADLEAF
                 else BROADLEAF) if k in veg else k
                for k, b in zip(kinds, snow)]
    if "nir" not in more_roles:
        return list(kinds)
    centers = np.asarray(centers, dtype=np.float64)
    first = centers[:, list(roles).index("nir")]
    second = centers[:, len(roles) + more_roles.index("nir")]
    out = []
    for kind, a, b in zip(kinds, first, second):
        if kind in veg:
            high = max(a, b)
            keep = min(a, b) / high if high > 0 else 0.0
            kind = CONIFER if keep >= EVERGREEN else BROADLEAF
        out.append(kind)
    return out


def scenario_kinds(kinds, scenario):
    """Виды цветов, которые различает сценарий: прочие - в замену."""
    spec = SCENARIOS[scenario]
    out = []
    for kind in kinds:
        kind = spec["merge"].get(kind, kind)
        out.append(kind if kind in spec["kinds"] else OTHER)
    return out


def inner_shares(pieces):
    """Доля внутренних клеток каждого куска: все соседи в сетке - тот же
    кусок, край сетки не в счёт. У кольца в одну-две клетки доля близка
    к нулю."""
    pieces = np.asarray(pieces)
    count = int(pieces.max()) + 1 if pieces.size else 0
    inner = pieces >= 0
    inner[1:] &= pieces[1:] == pieces[:-1]
    inner[:-1] &= pieces[:-1] == pieces[1:]
    inner[:, 1:] &= pieces[:, 1:] == pieces[:, :-1]
    inner[:, :-1] &= pieces[:, :-1] == pieces[:, 1:]
    total = np.bincount(pieces[pieces >= 0], minlength=count)
    found = np.bincount(pieces[inner], minlength=count)
    return found / np.maximum(total, 1)


def ring_shares(pieces, piece_kinds, target, wanted, width):
    """Доля вида target в полосе шириной width клеток вокруг каждого
    куска из wanted: {кусок: доля}. Полоса - клетки участка вне куска
    не дальше width шагов по сторонам клеток. Смешанные пиксели края
    (пересчёт снимка на сетку участка) дают тонкое кольцо другого вида,
    по одной границе кусок его и видел бы."""
    pieces = np.asarray(pieces)
    kind_of = np.array([k == target for k in piece_kinds] + [False])
    rows, cols = pieces.shape
    out = {}
    for n in wanted:
        found = np.nonzero(pieces == n)
        if not len(found[0]):
            continue
        r0 = max(0, found[0].min() - width)
        r1 = min(rows, found[0].max() + width + 1)
        c0 = max(0, found[1].min() - width)
        c1 = min(cols, found[1].max() + width + 1)
        box = pieces[r0:r1, c0:c1]
        mine = box == n
        grown = mine.copy()
        for _ in range(width):
            step = grown.copy()
            step[1:] |= grown[:-1]
            step[:-1] |= grown[1:]
            step[:, 1:] |= grown[:, :-1]
            step[:, :-1] |= grown[:, 1:]
            grown = step
        ring = grown & ~mine & (box >= 0)
        total = int(ring.sum())
        out[n] = float(kind_of[box[ring]].sum()) / total if total else 0.0
    return out


def region_kinds(parts, region_colors, kinds, scenario):
    """Виды областей по сценарию. kinds - виды цветов (color_kinds),
    region_colors[n] - цвет области n. Почва, вокруг которой в полосе RIM
    клеток не меньше NEAR_FOREST хвойного леса, становится рубкой, если
    сценарий различает рубки. Лесом считается только хвоя: светлая
    растительность бывает и посевом, и тогда пашня рядом с посевом стала
    бы рубкой.
    Без отделённой хвои рубок нет."""
    out = [kinds[c] if c >= 0 else OTHER for c in region_colors]
    if CLEARING in SCENARIOS[scenario]["kinds"] and CONIFER in out:
        # Цветов больше, чем видов: вырубка делится на области разных
        # оттенков почвы, и каждая граничит больше с соседней почвой, чем
        # с лесом. Доля границы считается по связному куску одного вида.
        parts = np.asarray(parts)
        codes = {k: n for n, k in enumerate(sorted(set(out)))}
        whole, whole_kinds = segments.dissolve(
            parts, np.array([codes[k] for k in out], dtype=np.int64))
        names = {n: k for k, n in codes.items()}
        piece_kinds = [names[int(c)] for c in whole_kinds]
        # Лес - только хвоя с толщей: смешанные пиксели края поля бывают
        # похожи на хвою и дают тонкое кольцо вокруг поля.
        thick = inner_shares(whole) >= THICK
        piece_kinds = [CONIFER if k == CONIFER and thick[n]
                       else OTHER if k == CONIFER else k
                       for n, k in enumerate(piece_kinds)]
        shares = ring_shares(whole, piece_kinds, CONIFER,
                             [n for n, k in enumerate(piece_kinds)
                              if k == SOIL], RIM)
        flat, first = np.unique(parts.ravel(), return_index=True)
        piece = np.full(len(out), -1, dtype=np.int64)
        keep = flat >= 0
        piece[flat[keep]] = whole.ravel()[first[keep]]
        out = [CLEARING if k == SOIL
               and shares.get(int(piece[n]), 0.0) >= NEAR_FOREST else k
               for n, k in enumerate(out)]
    return scenario_kinds(out, scenario)


# Линейные объекты по видам: группа - виды областей, из которых линии.
LINE_GROUPS = (("roads", (SOIL, CLEARING)), ("water", (WATER,)),
               ("belts", (BROADLEAF, VEGETATION)))
LINE_COLORS = {"roads": (255, 255, 255), "water": (120, 220, 255),
               "belts": (255, 225, 60)}


def line_masks(parts, region_list):
    """Маски видов для линий: {группа: маска клеток}. region_list[n] -
    вид области n (region_kinds)."""
    parts = np.asarray(parts)
    kinds = np.array(list(region_list) + [OTHER], dtype=object)
    cell = kinds[np.where(parts >= 0, parts, len(region_list))]
    return {group: np.isin(cell, list(members))
            for group, members in LINE_GROUPS}


def classes_of(region_list, scenario):
    """Классы слоя: виды областей по порядку KIND_ORDER, которые
    встретились. Итог - (виды классов, номер класса каждой области)."""
    used = [k for k in KIND_ORDER if k in set(region_list)]
    index = {k: n for n, k in enumerate(used)}
    return used, np.array([index[k] for k in region_list], dtype=np.int64)
