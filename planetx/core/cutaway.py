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
    from . import ellipsoid
    from .slabs import band
    from .subsurface import Part, merge
except ImportError:  # headless-тесты
    import ellipsoid
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

Wedge = namedtuple("Wedge", "lon sign half")
Wedge.__doc__ = """Сектор: средняя долгота, полушарие (1 - северное,
-1 - южное), половина ширины по долготе в градусах."""


def wedge_at(lat, lon, half=HALF):
    """Сектор под точкой взгляда: её долгота посередине, её
    полушарие."""
    return Wedge(float(lon), 1.0 if lat >= 0.0 else -1.0, float(half))


def uniform(wedge):
    """Четыре числа для шейдера тайла: направление средней долготы
    (x, y), косинус половины ширины, полушарие."""
    lon = math.radians(wedge.lon)
    return (math.cos(lon), math.sin(lon), math.cos(math.radians(wedge.half)),
            wedge.sign)


def inside(wedge, lats, lons):
    """Признак «точка в вынутом секторе» для широт и долгот."""
    lats = np.asarray(lats, dtype=np.float64)
    lons = np.asarray(lons, dtype=np.float64)
    off = (lons - wedge.lon + 180.0) % 360.0 - 180.0
    return (wedge.sign * lats > 0.0) & (np.abs(off) <= wedge.half)


def boundary(directions):
    """Радиус эллипсоида по единичным направлениям из центра (n, 3)."""
    d = np.asarray(directions, dtype=np.float64)
    a, b = ellipsoid.A, ellipsoid.B
    return 1.0 / np.sqrt((d[:, 0] ** 2 + d[:, 1] ** 2) / a ** 2
                         + d[:, 2] ** 2 / b ** 2)


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


def _band(edge, normal, low, high, color):
    """Полоса грани между долями радиуса low и high (по точке дуги или
    одно число). Ячейка нулевой толщины на обоих концах пропускается."""
    n = len(edge)
    low = np.broadcast_to(np.asarray(low, dtype=np.float64), (n,))
    high = np.broadcast_to(np.asarray(high, dtype=np.float64), (n,))
    i = np.arange(n - 1)
    keep = (high[i] > low[i]) | (high[i + 1] > low[i + 1])
    i = i[keep]
    if not len(i):
        return None
    positions = np.vstack([edge * low[:, None], edge * high[:, None]])
    tris = np.concatenate([np.stack([i, i + 1, n + i], -1),
                           np.stack([i + 1, n + i + 1, n + i], -1)])
    rgba = np.tile(np.array(tuple(color) + (255,), dtype=np.uint8),
                   (2 * n, 1))
    return Part(positions, np.tile(normal, (2 * n, 1)), rgba,
                tris.astype(np.uint32))


def _face(directions, normal, shells, crust=None, gain=1.0):
    """Грань - полосы оболочек по дуге единичных направлений (n, 3).
    С моделью коры кора - слои CRUST1.0, мантия - до Мохо точки.
    gain - растяжение коры, см. stretch."""
    edge = boundary(directions)[:, None] * directions

    def radius(r):
        return _share(r - PREM_RADIUS, gain)

    if crust is None:
        return [_band(edge, normal, radius(low), radius(high), color)
                for _, low, high, color in shells]
    lats, lons = _latlon(directions)
    bounds = crust.at(lats, lons).astype(np.float64)
    share = _share(bounds, gain)
    moho = share[:, -1]
    parts = []
    for key, low, high, color in shells:
        if key == "crust":
            continue
        top = moho if key == "upper_mantle" else radius(high)
        parts.append(_band(edge, normal, radius(low), top, color))
    for k, key in enumerate(crust_layers()):
        parts.append(_band(edge, normal, share[:, k + 1], share[:, k],
                           CRUST_COLORS[key]))
    return parts


def crust_layers():
    """Ключи слоёв коры сверху вниз, как в core.crust.LAYERS."""
    return tuple(CRUST_COLORS)


def faces(wedge, shells=SHELLS, step=None, crust=None, gain=1.0):
    """Сетка трёх граней сектора для видеокарты, core.subsurface.Mesh.

    Экваториальная грань - дуга по долготе на экваторе, меридиональные
    - дуги от экватора до полюса на крайних долготах. crust - модель
    core.crust.Crust или None, тогда кора - оболочка PREM. gain -
    растяжение коры, см. stretch."""
    if step is None:
        step = ARC_STEP if crust is None else CRUST_STEP
    parts = []
    for directions, normal in arcs(wedge, step):
        parts += _face(directions, normal, shells, crust, gain)
    return merge(parts, key="cutaway")


def arcs(wedge, step=CRUST_STEP):
    """Дуги граней: единичные направления (n, 3) и нормаль грани.
    Экваториальная - по долготе на экваторе, меридиональные - от
    экватора до полюса на крайних долготах."""
    count = max(2, int(math.ceil(2.0 * wedge.half / step)) + 1)
    lons = np.radians(np.linspace(wedge.lon - wedge.half,
                                  wedge.lon + wedge.half, count))
    out = [(np.stack([np.cos(lons), np.sin(lons), np.zeros(count)], -1),
            np.array([0.0, 0.0, 1.0]))]
    count = max(2, int(math.ceil(90.0 / step)) + 1)
    lats = np.radians(np.linspace(0.0, 90.0 * wedge.sign, count))
    for lon in (wedge.lon - wedge.half, wedge.lon + wedge.half):
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


def slab_bands(wedge, zones, gain=1.0, step=CRUST_STEP):
    """Полосы плит Slab2 на гранях, core.subsurface.Mesh или None.
    zones - зоны core.slabs.Slab, которых касается разрез. Глубины - с тем
    же растяжением, что у коры."""
    parts = []
    for directions, normal in arcs(wedge, step):
        lats, lons = _latlon(directions)
        top, bottom = band(zones, lats, lons)
        none = ~np.isfinite(top)
        high = np.where(none, 1.0, _share(-np.nan_to_num(top), gain))
        low = np.where(none, 1.0, _share(-np.nan_to_num(bottom), gain))
        edge = boundary(directions)[:, None] * directions
        parts.append(_band(edge, normal, low, high, SLAB_COLOR))
    return merge(parts, key="slabs")


def label_points(wedge, shells=SHELLS):
    """Места подписей оболочек: широта, долгота и высота над
    эллипсоидом середины оболочки на экваториальной грани, по средней
    долготе. Высота отрицательная - точка внутри Земли."""
    out = []
    for name, low, high, _ in shells:
        mid = (low + high) / 2.0 / PREM_RADIUS
        out.append((name, 0.0, wedge.lon, (mid - 1.0) * ellipsoid.A))
    return out
