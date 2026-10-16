# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разрез Земли: вырезанный сектор и оболочки на его гранях. Без Qt.

Третий пункт списка «непрерывной вертикали», 2 октября 2026 года.
Из глобуса вынимается сектор - четверть полушария, 90° по долготе
от экватора до полюса. Его три грани - четверть экваториального
круга и две четверти меридиональных кругов - раскрашены оболочками
Земли по радиусам модели PREM (Dziewonski, Anderson, 1981, Physics
of the Earth and Planetary Interiors 25, 297-356).

Радиусы PREM даны для шара 6371 км. Край грани лежит на эллипсоиде,
поэтому радиус границы оболочки - доля радиуса эллипсоида в том же
направлении. Так грань сходится с поверхностью без щели, а сжатие
Земли, 21 км, ложится на все оболочки поровну. Глубины не
растягиваются масштабом рельефа: на масштабе всей Земли масштаб
рельефа исказил бы радиусы ядра.

Поверхность в секторе отбрасывает шейдер тайла по нормали вершины
(render/shaders.py, u_wedge), см. Wedge.uniform.

С моделью коры CRUST1.0 (core/crust.py) кора на гранях - её слои
по ячейкам 1°: вода, лёд, осадки, верхняя, средняя и нижняя кора.
Верхняя мантия тогда начинается от Мохо этой точки. Отметка слоя
в км переходит в радиус так же, как граница оболочки: доля
(PREM_RADIUS + отметка) / PREM_RADIUS радиуса эллипсоида. Точка грани
ищется в модели по направлению из центра, разница геоцентрической
и геодезической широты, до 0.19°, меньше ячейки.
"""
import math
from collections import namedtuple

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid, tomography
    from .slabs import band
    from .subsurface import Part, merge
except ImportError:  # headless-тесты
    import ellipsoid
    import tomography
    from slabs import band
    from subsurface import Part, merge

PREM_RADIUS = 6371.0  # км, радиус шара модели
# Оболочки: название, радиус нижней и верхней границы в км по PREM,
# цвет. Границы - Мохо 24.4 км, 400 и 670 км, ядро 2891 км, внутреннее
# ядро 5149.5 км глубины. Цвета - выбор помощника, утверждает автор.
SHELLS = (
    ("inner_core", 0.0, 1221.5, (255, 240, 170)),
    ("outer_core", 1221.5, 3480.0, (245, 195, 70)),
    ("lower_mantle", 3480.0, 5701.0, (225, 135, 55)),
    ("transition_zone", 5701.0, 5971.0, (205, 100, 45)),
    ("upper_mantle", 5971.0, 6346.6, (180, 75, 40)),
    ("crust", 6346.6, PREM_RADIUS, (120, 95, 75)),
)
HALF = 45.0  # половина ширины сектора по долготе, градусы
ARC_STEP = 1.5  # шаг дуги грани, градусы
CRUST_STEP = 0.5  # шаг дуги с моделью коры: две точки на ячейку
# Слои CRUST1.0 - цвет. Выбор помощника, утверждает автор.
CRUST_COLORS = {
    "water": (40, 95, 170),
    "ice": (225, 235, 245),
    "sediments_upper": (235, 210, 145),
    "sediments_middle": (215, 185, 120),
    "sediments_lower": (195, 160, 100),
    "crust_upper": (170, 150, 135),
    "crust_middle": (145, 125, 115),
    "crust_lower": (120, 100, 95),
}
# Слои океанической коры (core.crust.Crust.oceanic) - свой цвет,
# у CRUST_COLORS остаётся континентальная. Выбор помощника, утверждает
# автор.
OCEAN_COLORS = {
    "crust_upper": (95, 115, 110),
    "crust_middle": (75, 95, 92),
    "crust_lower": (60, 78, 78),
}
# Выделение коры издалека, решение автора от 2 октября 2026 года.
# Глубины до STRETCH_DEPTH растягиваются функцией stretch: у поверхности
# в gain раз, на STRETCH_DEPTH - без растяжения, ниже всё настоящее.
# gain растёт с расстоянием до точки взгляда ступенями GAIN_STEPS, одна
# единица на GAIN_DISTANCE метров. Величины - выбор помощника,
# утверждает автор.
STRETCH_DEPTH = 400.0  # км, граница верхней мантии и переходной зоны
GAIN_STEPS = (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0)
GAIN_DISTANCE = 2.0e6
# Плита Slab2 на гранях (core/slabs.py) - цвет, выбор помощника.
SLAB_COLOR = (55, 85, 125)
# Шаг дуги полосы плиты - шаг сетки файлов зон Slab2 (tools/build_slabs.py).
# Ячейка полосы нужна с плитой на обоих концах, крупный шаг съедал бы
# край зоны и узкие зоны целиком.
SLAB_STEP = 0.1

# Сектор двигается за угловые точки, просьба автора от 2 октября 2026
# года. Ширина по долготе и по широте - не меньше MIN_SPAN, по долготе
# не больше MAX_SPAN.
MIN_SPAN = 5.0
MAX_SPAN = 180.0

Wedge = namedtuple("Wedge", "west east south north")
Wedge.__doc__ = """Сектор: западная и восточная долгота, южная и северная
широта, градусы. Восток отсчитывается от запада к востоку, через линию
перемены дат тоже. Широта 0 - плоскость экватора, широта ±90 - полюс,
прочие широты - конус к центру Земли."""


def make_wedge(west, east, south, north):
    """Сектор с границами в допустимых пределах: долготы от -180 до 180,
    ширина по долготе MIN_SPAN-MAX_SPAN, широты по порядку и не уже
    MIN_SPAN."""
    west = (float(west) + 180.0) % 360.0 - 180.0
    span = min(max((float(east) - west) % 360.0, MIN_SPAN), MAX_SPAN)
    east = (west + span + 180.0) % 360.0 - 180.0
    south = min(max(float(south), -90.0), 90.0 - MIN_SPAN)
    north = min(max(float(north), south + MIN_SPAN), 90.0)
    return Wedge(west, east, south, north)


def span(wedge):
    """Ширина сектора по долготе, градусы."""
    return (wedge.east - wedge.west) % 360.0 or 360.0


def middle(wedge):
    """Средняя долгота сектора."""
    return (wedge.west + span(wedge) / 2.0 + 180.0) % 360.0 - 180.0


def wedge_at(lat, lon, half=HALF):
    """Сектор под точкой взгляда: её долгота посередине, от экватора до
    полюса её полушария."""
    if lat >= 0.0:
        return make_wedge(lon - half, lon + half, 0.0, 90.0)
    return make_wedge(lon - half, lon + half, -90.0, 0.0)


def uniform(wedge):
    """Числа для шейдера тайла: направление средней долготы (x, y),
    косинус половины ширины, синусы южной и северной широты."""
    lon = math.radians(middle(wedge))
    return (math.cos(lon), math.sin(lon),
            math.cos(math.radians(span(wedge) / 2.0)),
            math.sin(math.radians(wedge.south)),
            math.sin(math.radians(wedge.north)))


def inside(wedge, lats, lons):
    """Признак «точка в вынутом секторе» для широт и долгот."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    off = (lons - wedge.west) % 360.0
    return (lats > wedge.south) & (lats < wedge.north) & \
        (off <= span(wedge))


def corners(wedge):
    """Угловые точки сектора на поверхности: (широта, долгота) в порядке
    юго-запад, юго-восток, северо-запад, северо-восток. У полюса две
    точки совпадают."""
    return [(wedge.south, wedge.west), (wedge.south, wedge.east),
            (wedge.north, wedge.west), (wedge.north, wedge.east)]


def move_corner(wedge, index, lat, lon):
    """Сектор, у которого угол index (как в corners) встал в точку."""
    west, east, south, north = wedge
    if index in (0, 2):
        west = lon
    else:
        east = lon
    if index in (0, 1):
        south = lat
    else:
        north = lat
    if (east - west) % 360.0 > MAX_SPAN:
        # Угол перетащили за противоположную сторону - сектор
        # не выворачивается, ширина остаётся наименьшей.
        if index in (0, 2):
            west = east - MIN_SPAN
        else:
            east = west + MIN_SPAN
    return make_wedge(west, east, min(south, north), max(south, north))


def boundary(directions, lift=None):
    """Радиус края грани по единичным направлениям из центра (n, 3):
    эллипсоид или, с lift, поверхность над ним.

    lift(lats, lons) - высота поверхности на экране в метрах по
    геодезическим широтам и долготам точек, например геоид в его
    масштабе. Замечание пользователя от 14 октября 2026 года - разрез
    не стыковался с «измятым» геоидом. Все оболочки растягиваются
    в ту же долю, край грани ложится на поверхность."""
    d = np.asarray(directions, dtype=np.float64)
    a, b = ellipsoid.A, ellipsoid.B
    radius = 1.0 / np.sqrt((d[:, 0] ** 2 + d[:, 1] ** 2) / a ** 2
                           + d[:, 2] ** 2 / b ** 2)
    if lift is None:
        return radius
    lats, lons = _latlon(d)
    # Широта направления из центра - геоцентрическая, высоты лежат по
    # геодезической.
    geodetic = np.degrees(np.arctan2(np.tan(np.radians(lats)),
                                     (b / a) ** 2))
    heights = np.asarray(lift(geodetic, lons), dtype=np.float64)
    # Точка без высоты (NaN) ставится на эллипсоид: вершина с NaN
    # выпала бы из грани.
    heights = np.nan_to_num(heights, nan=0.0, posinf=0.0, neginf=0.0)
    return np.maximum(radius + heights, radius * 0.5)


def gain_for(distance):
    """Растяжение коры для расстояния до точки взгляда, ступенью
    GAIN_STEPS: наибольшая ступень не больше distance / GAIN_DISTANCE."""
    raw = float(distance) / GAIN_DISTANCE
    return max([g for g in GAIN_STEPS if g <= raw] or [GAIN_STEPS[0]])


def stretch(depth, gain):
    """Глубина на экране для настоящей глубины depth, км. До
    STRETCH_DEPTH - STRETCH_DEPTH·(1 - (1 - x)^gain), x = depth /
    STRETCH_DEPTH: наклон у поверхности gain, на границе 1. Выше
    поверхности (depth < 0) и глубже границы - без изменения."""
    depth = np.asarray(depth, dtype=np.float64)
    if gain == 1.0:
        return depth
    x = np.clip(depth / STRETCH_DEPTH, 0.0, 1.0)
    shown = STRETCH_DEPTH * (1.0 - (1.0 - x) ** gain)
    return np.where((depth > 0.0) & (depth < STRETCH_DEPTH), shown, depth)


def _share(elevation, gain):
    """Доля радиуса для отметки в км (вверх положительно)."""
    elevation = np.asarray(elevation, dtype=np.float64)
    return (PREM_RADIUS - stretch(-elevation, gain)) / PREM_RADIUS


def _band(edge, normal, low, high, color, whole=False):
    """Полоса грани между долями радиуса low и high (по точке дуги или
    одно число). Ячейка нулевой толщины на обоих концах пропускается.
    whole - ячейка нужна с толщиной на обоих концах. Так у плиты: точка
    без плиты стоит на поверхности, и ячейка от конца плиты к ней шла
    клином от глубины до поверхности. color - один цвет или цвет
    на точку дуги (n, 3)."""
    n = len(edge)
    low = np.broadcast_to(np.asarray(low, dtype=np.float64), (n,))
    high = np.broadcast_to(np.asarray(high, dtype=np.float64), (n,))
    i = np.arange(n - 1)
    keep = ((high[i] > low[i]) & (high[i + 1] > low[i + 1]) if whole
            else (high[i] > low[i]) | (high[i + 1] > low[i + 1]))
    i = i[keep]
    if not len(i):
        return None
    positions = np.vstack([edge * low[:, None], edge * high[:, None]])
    tris = np.concatenate([np.stack([i, i + 1, n + i], -1),
                           np.stack([i + 1, n + i + 1, n + i], -1)])
    rgb = np.broadcast_to(np.asarray(color, dtype=np.uint8), (n, 3))
    rgba = np.empty((2 * n, 4), dtype=np.uint8)
    rgba[:, :3] = np.vstack([rgb, rgb])
    rgba[:, 3] = 255
    return Part(positions, np.tile(normal, (2 * n, 1)), rgba,
                tris.astype(np.uint32))


MANTLE = ("upper_mantle", "transition_zone", "lower_mantle")


def _mantle(edge, directions, normal, top, tomo, gain):
    """Мантия по томографии: сетка от top (доля радиуса по точкам -
    Мохо) до ядра, ряды на глубинах модели, цвет вершины - dVs."""
    lats, lons = _latlon(directions)
    depths = tomography.rows(tomo)
    n = len(edge)
    shares = [np.asarray(top, dtype=np.float64)]
    rgb = [tomography.colors(tomography.sample(tomo, lats, lons,
                                               depths[0]))]
    for depth in depths:
        share = np.minimum(np.full(n, _share(-depth, gain)), shares[0])
        shares.append(share)
        rgb.append(tomography.colors(tomography.sample(tomo, lats, lons,
                                                       depth)))
    count = len(shares)
    positions = np.vstack([edge * s[:, None] for s in shares])
    colors = np.empty((count * n, 4), np.uint8)
    colors[:, :3] = np.vstack(rgb)
    colors[:, 3] = 255
    i = np.arange(n - 1)
    tris = []
    for r in range(count - 1):
        a, b = r * n + i, (r + 1) * n + i
        tris += [np.stack([a, a + 1, b], -1), np.stack([a + 1, b + 1, b], -1)]
    return Part(positions, np.tile(normal, (count * n, 1)), colors,
                np.concatenate(tris).astype(np.uint32))


def _face(directions, normal, shells, crust=None, gain=1.0, lift=None,
          tomo=None):
    """Грань - полосы оболочек по дуге единичных направлений (n, 3).
    С моделью коры кора - слои CRUST1.0, мантия - до Мохо точки.
    gain - растяжение коры, см. stretch. lift - см. boundary. tomo -
    модель core.tomography.Tomo: мантия раскрашена по ней."""
    edge = boundary(directions, lift)[:, None] * directions

    def radius(r):
        return _share(r - PREM_RADIUS, gain)

    if crust is None:
        parts = [_band(edge, normal, radius(low), radius(high), color)
                 for key, low, high, color in shells
                 if tomo is None or key not in MANTLE]
        if tomo is not None:
            crust_low = [low for key, low, _, _ in SHELLS
                         if key == "crust"][0]
            parts.append(_mantle(edge, directions, normal,
                                 np.full(len(edge), radius(crust_low)),
                                 tomo, gain))
        return parts
    lats, lons = _latlon(directions)
    bounds = crust.at(lats, lons).astype(np.float64)
    share = _share(bounds, gain)
    moho = share[:, -1]
    parts = []
    for key, low, high, color in shells:
        if key == "crust" or tomo is not None and key in MANTLE:
            continue
        top = moho if key == "upper_mantle" else radius(high)
        parts.append(_band(edge, normal, radius(low), top, color))
    if tomo is not None:
        parts.append(_mantle(edge, directions, normal, moho, tomo, gain))
    oceanic = crust.oceanic(lats, lons)
    for k, key in enumerate(crust_layers()):
        parts.append(_band(edge, normal, share[:, k + 1], share[:, k],
                           layer_colors(key, oceanic)))
    return parts


def crust_layers():
    """Ключи слоёв коры сверху вниз, как в core.crust.LAYERS."""
    return tuple(CRUST_COLORS)


def layer_colors(key, oceanic):
    """Цвет слоя коры key: один цвет или цвет на точку (n, 3), если
    слой бывает океаническим и oceanic - массив bool по точкам."""
    if oceanic is None or key not in OCEAN_COLORS:
        return CRUST_COLORS[key]
    oceanic = np.asarray(oceanic, dtype=bool)
    return np.where(oceanic[:, None], np.array(OCEAN_COLORS[key]),
                    np.array(CRUST_COLORS[key])).astype(np.uint8)


def split_types(top, bottom, oceanic):
    """Слой коры по точкам линии на континентальную и океаническую
    части: (океаническая ли, верх, низ) с NaN вне своей части. Края
    океанической части расширены на точку, так между частями нет ни
    щели, ни перекрытия: отрезок на стыке берёт океаническая."""
    top = np.asarray(top, dtype=np.float64)
    bottom = np.asarray(bottom, dtype=np.float64)
    if oceanic is None:
        return [(False, top, bottom)]
    ocean = np.asarray(oceanic, dtype=bool)
    wide = ocean.copy()
    wide[1:] |= ocean[:-1]
    wide[:-1] |= ocean[1:]
    out = []
    for kind, mask in ((False, ~ocean), (True, wide)):
        if mask.any():
            out.append((kind, np.where(mask, top, np.nan),
                        np.where(mask, bottom, np.nan)))
    return out


def faces(wedge, shells=SHELLS, step=None, crust=None, gain=1.0,
          lift=None, tomo=None):
    """Сетка трёх граней сектора для видеокарты, core.subsurface.Mesh.

    Экваториальная грань - дуга по долготе на экваторе, меридиональные
    - дуги от экватора до полюса на крайних долготах. crust - модель
    core.crust.Crust или None, тогда кора - оболочка PREM. gain -
    растяжение коры, см. stretch. lift - высота поверхности, к которой
    тянется край граней, см. boundary. tomo - томография мантии,
    core.tomography.Tomo, или None - мантия оболочками PREM."""
    if step is None:
        step = ARC_STEP if crust is None and lift is None \
            and tomo is None else CRUST_STEP
    parts = []
    for directions, normal in arcs(wedge, step):
        parts += _face(directions, normal, shells, crust, gain, lift, tomo)
    return merge(parts, key="cutaway")


def arcs(wedge, step=CRUST_STEP):
    """Дуги граней: единичные направления (n, 3) и нормаль грани.
    Широтные - по долготе на южной и северной широте, если она не
    полюс: на экваторе это плоскость, на прочих широтах конус к центру.
    Меридиональные - от южной до северной широты на крайних долготах."""
    width = span(wedge)
    count = max(2, int(math.ceil(width / step)) + 1)
    lons = np.radians(wedge.west + np.linspace(0.0, width, count))
    out = []
    for lat in (wedge.south, wedge.north):
        if abs(lat) >= 90.0:
            continue
        phi = math.radians(lat)
        directions = np.stack([math.cos(phi) * np.cos(lons),
                               math.cos(phi) * np.sin(lons),
                               np.full(count, math.sin(phi))], -1)
        # Нормаль конуса - на север в середине дуги: свет одной грани
        # один.
        lam = math.radians(middle(wedge))
        normal = np.array([-math.sin(phi) * math.cos(lam),
                           -math.sin(phi) * math.sin(lam), math.cos(phi)])
        out.append((directions, normal))
    count = max(2, int(math.ceil((wedge.north - wedge.south) / step)) + 1)
    lats = np.radians(np.linspace(wedge.south, wedge.north, count))
    for lon in (wedge.west, wedge.east):
        lam = math.radians(lon)
        out.append((np.stack([np.cos(lats) * math.cos(lam),
                              np.cos(lats) * math.sin(lam), np.sin(lats)],
                             -1),
                    np.array([-math.sin(lam), math.cos(lam), 0.0])))
    return out


def _latlon(directions):
    """Широты и долготы точек дуги по направлению из центра."""
    lats = np.degrees(np.arcsin(np.clip(directions[:, 2], -1.0, 1.0)))
    lons = np.degrees(np.arctan2(directions[:, 1], directions[:, 0]))
    return lats, lons


def arc_points(wedge, step=CRUST_STEP):
    """Широты и долготы всех точек дуг граней: по ним ищутся зоны
    плит, которых касается разрез."""
    pairs = [_latlon(d) for d, _ in arcs(wedge, step)]
    return (np.concatenate([p[0] for p in pairs]),
            np.concatenate([p[1] for p in pairs]))


def slab_bands(wedge, zones, gain=1.0, step=SLAB_STEP, lift=None):
    """Полосы плит Slab2 на гранях, core.subsurface.Mesh или None.
    zones - зоны core.slabs.Slab, которых касается разрез. Глубины - с тем
    же растяжением, что у коры, край - как у граней (lift)."""
    parts = []
    for directions, normal in arcs(wedge, step):
        lats, lons = _latlon(directions)
        top, bottom = band(zones, lats, lons)
        none = ~np.isfinite(top)
        high = np.where(none, 1.0, _share(-np.nan_to_num(top), gain))
        low = np.where(none, 1.0, _share(-np.nan_to_num(bottom), gain))
        edge = boundary(directions, lift)[:, None] * directions
        parts.append(_band(edge, normal, low, high, SLAB_COLOR, whole=True))
    return merge(parts, key="slabs")


def label_points(wedge, shells=SHELLS):
    """Места подписей оболочек: широта, долгота и высота над
    эллипсоидом середины оболочки на экваториальной грани, по средней
    долготе. Высота отрицательная - точка внутри Земли."""
    out = []
    for name, low, high, _ in shells:
        mid = (low + high) / 2.0 / PREM_RADIUS
        out.append((name, max(wedge.south, 0.0) if wedge.north > 0.0
                    else wedge.north, middle(wedge),
                    (mid - 1.0) * ellipsoid.A))
    return out
