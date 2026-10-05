# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Спутники по элементам CelesTrak: группы, расчёт и показ.

Расчёт без Qt. Положение - модель SGP4 (core/sgp4.py), поворот TEME
в систему Земли по звёздному времени. SGP4 считается в моменты сетки
шагом SAMPLE модельного времени, между ними положение берётся
кубическим сплайном Эрмита по положениям и скоростям концов. Ошибка
сплайна на шаге 60 с у низкой орбиты - метры, кадр стоит доли
миллисекунды на тысячи спутников.

Правила CelesTrak (celestrak.org/usage-policy.php, 6 октября 2026
года) - группа скачивается не чаще одного обновления, данные
обновляются раз в 2 часа, после ответа с ошибкой запросы прекращаются.
Модуль берёт группу через кэш QGIS и не чаще раза в REFETCH.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
    from . import sgp4
except ImportError:  # headless-тесты
    import ellipsoid
    import sgp4

FEED = "https://celestrak.org/NORAD/elements/gp.php?GROUP={group}&FORMAT=csv"
ATTRIBUTION = ("CelesTrak", "https://celestrak.org")
REFETCH = 2 * 3600.0  # с, не чаще этого группа просится заново
SAMPLE = 60.0  # с модельного времени между расчётами SGP4
OMEGA = 7.292115e-5  # рад/с, вращение Земли
INIT_BUDGET = 150  # спутников за проход цикла событий, около 4 мс
# Дальше этого от эпохи элементов спутник не показывается: точность
# SGP4 падает до километров в сутки, а резонансы геостационарных
# и навигационных спутников интегрируются шагами по 12 часов от эпохи,
# годы назад - тысячи шагов.
MAX_AGE = 30.0  # суток
STALE = 7  # код «элементы старше MAX_AGE» рядом с кодами ошибок SGP4

# Группы CelesTrak строки «Спутники»: ключ запроса и цвет точки.
# Названия и подсказки - в окне (ui), здесь только данные.
GROUPS = (
    ("stations", (255, 255, 255)),
    ("visual", (255, 224, 102)),
    ("gnss", (102, 204, 255)),
    ("weather", (153, 255, 153)),
    ("resource", (255, 170, 102)),
    ("science", (204, 153, 255)),
    ("geo", (255, 102, 153)),
    ("starlink", (170, 170, 170)),
    ("oneweb", (128, 160, 200)),
)
COLORS = dict(GROUPS)
DEFAULT_GROUPS = ("stations",)
# Размер точки в логических пикселях. У больших групп точки мельче.
SIZES = {"stations": 8.0, "starlink": 3.0, "oneweb": 3.0}
SIZE = 5.0


def feed(group):
    """Адрес CSV группы CelesTrak."""
    return FEED.format(group=group)


def jd_now(seconds):
    """Юлианская дата по секундам UTC от 1970 года."""
    return sgp4.unix_jd(seconds)


def to_ecef(r, v, jd):
    """Положение и скорость TEME (км, км/с) в систему Земли, метры
    и м/с. Скорость - относительно вращающейся Земли."""
    p = sgp4.teme_to_ecef(r, jd) * 1000.0
    w = sgp4.teme_to_ecef(v, jd) * 1000.0
    w[..., 0] += OMEGA * p[..., 1]
    w[..., 1] -= OMEGA * p[..., 0]
    return p, w


def hermite(p0, v0, p1, v1, h, s):
    """Кубический сплайн Эрмита между (p0, v0) и (p1, v1), шаг h
    секунд, доля шага s от 0 до 1."""
    s2 = s * s
    s3 = s2 * s
    return ((2 * s3 - 3 * s2 + 1) * p0 + (s3 - 2 * s2 + s) * h * v0
            + (-2 * s3 + 3 * s2) * p1 + (s3 - s2) * h * v1)


def hidden(eye, points):
    """Закрыта ли точка Землёй для глаза eye: отрезок от глаза до точки
    пересекает эллипсоид. points - массив N×3, метры ECEF."""
    a, b = ellipsoid.A, ellipsoid.B
    scale = np.array([1.0 / a, 1.0 / a, 1.0 / b])
    e = np.asarray(eye, dtype=float) * scale
    d = np.asarray(points, dtype=float) * scale - e
    qa = np.einsum("ij,ij->i", d, d)
    qb = 2.0 * (d @ e)
    qc = float(e @ e) - 1.0
    if qc <= 0.0:
        return np.zeros(len(d), dtype=bool)
    disc = qb * qb - 4.0 * qa * qc
    root = np.sqrt(np.maximum(disc, 0.0))
    s = (-qb - root) / (2.0 * qa)
    return (disc > 0.0) & (s > 0.0) & (s < 1.0)


def height(points):
    """Высота точек над эллипсоидом, метры."""
    return ellipsoid.ecef_to_geodetic(np.asarray(points, dtype=float))[2]


class Swarm:
    """Спутники выбранных групп: элементы, начальные величины,
    положения на момент."""

    def __init__(self):
        self.groups = {}  # группа -> sgp4.Orbits
        self._merge()

    def set_group(self, group, elements):
        """Элементы группы core.sgp4.Elements. Одинаковые номера NORAD
        из разных групп показываются один раз - у первой группы."""
        self.groups[group] = sgp4.Orbits(elements)
        self._merge()

    def drop_group(self, group):
        if self.groups.pop(group, None) is not None:
            self._merge()

    def keep(self, groups):
        """Оставить только группы groups."""
        for group in list(self.groups):
            if group not in groups:
                del self.groups[group]
        self._merge()

    def _merge(self):
        """Общие массивы всех групп: какой спутник откуда и его поля."""
        self.names = []
        self.numbers = np.zeros(0, dtype=np.int64)
        self.group_of = []
        self.f = None
        self.cache = None
        self._samples = {}
        self.colors = np.zeros((0, 4), dtype=np.float32)
        self.sizes = np.zeros(0, dtype=np.float32)

    def ready(self):
        return all(orb.ready for orb in self.groups.values())

    def init_some(self, budget=INIT_BUDGET):
        """Начальные величины следующих спутников, не больше budget
        за вызов. Возвращает True, когда посчитаны все."""
        for orb in self.groups.values():
            if not orb.ready:
                orb.init_some(budget)
                return False
        if self.f is None:
            self._build()
        return True

    def _build(self):
        seen = set()
        parts = []
        names, groups, numbers, colors, sizes = [], [], [], [], []
        for group, orb in self.groups.items():
            e = orb.elements
            take = [i for i, n in enumerate(e.number) if int(n) not in seen]
            seen.update(int(e.number[i]) for i in take)
            if not take:
                continue
            idx = np.array(take)
            parts.append({k: v[idx] for k, v in orb.f.items()})
            names += [e.name[i] for i in take]
            numbers.append(e.number[idx])
            groups += [group] * len(take)
            rgb = COLORS.get(group, (255, 255, 255))
            colors.append(np.tile(np.array(rgb + (255,)) / 255.0,
                                  (len(take), 1)))
            sizes.append(np.full(len(take), SIZES.get(group, SIZE)))
        self.names = names
        self.group_of = groups
        if parts:
            self.f = {k: np.concatenate([p[k] for p in parts])
                      for k in parts[0]}
            self.numbers = np.concatenate(numbers)
            self.colors = np.vstack(colors).astype(np.float32)
            self.sizes = np.concatenate(sizes).astype(np.float32)
        else:
            self.f = {k: np.zeros(0) for k in sgp4.FIELDS}
        self.cache = sgp4.Cache(self.f)
        self._samples = {}

    def __len__(self):
        return len(self.names)

    def _sample(self, step):
        """Положения и скорости в системе Земли в момент шага step сетки
        SAMPLE, словарь запоминает два последних шага."""
        if step in self._samples:
            return self._samples[step]
        seconds = step * SAMPLE
        jd = jd_now(seconds)
        tsince, stale = _since(self.f, jd)
        r, v, error = sgp4.propagate(self.f, tsince, self.cache)
        error = np.where(stale, STALE, error)
        p, w = to_ecef(r, v, jd)
        if len(self._samples) >= 2:
            for old in sorted(self._samples, key=lambda k: abs(k - step))[1:]:
                del self._samples[old]
        self._samples[step] = (p, w, error)
        return self._samples[step]

    def positions(self, seconds):
        """Положения спутников, метры ECEF, на момент seconds UTC от
        1970 года и признак годного положения. Пока начальные величины
        не посчитаны, спутников нет."""
        if self.f is None or not len(self):
            return np.zeros((0, 3)), np.zeros(0, dtype=bool)
        step = math.floor(seconds / SAMPLE)
        p0, v0, e0 = self._sample(step)
        p1, v1, e1 = self._sample(step + 1)
        s = seconds / SAMPLE - step
        points = hermite(p0, v0, p1, v1, SAMPLE, s)
        ok = (e0 == 0) & (e1 == 0) & np.isfinite(points).all(axis=1)
        return points, ok

    def index_of(self, number):
        """Номер спутника по номеру NORAD или None."""
        if self.f is None:
            return None
        found = np.flatnonzero(self.numbers == number)
        return int(found[0]) if found.size else None

    def motion(self, index, seconds):
        """Положение (метры ECEF) и скорость относительно Земли
        спутника index на момент seconds или None."""
        jd = jd_now(seconds)
        f = {k: v[index:index + 1] for k, v in self.f.items()}
        tsince, stale = _since(f, jd)
        r, v, error = sgp4.propagate(f, tsince)
        if stale[0] or error[0]:
            return None
        p, w = to_ecef(r, v, jd)
        return p[0], w[0]

    def info(self, index, seconds):
        """Название, номер NORAD, группа, высота км и скорость км/с
        спутника index на момент seconds."""
        jd = jd_now(seconds)
        f = {k: v[index:index + 1] for k, v in self.f.items()}
        tsince, stale = _since(f, jd)
        r, v, error = sgp4.propagate(f, tsince)
        p, _ = to_ecef(r, v, jd)
        return {"name": self.names[index],
                "number": int(self.numbers[index]),
                "group": self.group_of[index],
                "height": float(height(p)[0]) / 1000.0,
                "speed": float(np.linalg.norm(v[0])),
                "age": float(jd - sgp4.JD_EPOCH0 - f["epoch"][0]),
                "error": STALE if stale[0] else int(error[0])}


ORBIT_POINTS = 180  # точек на виток орбиты и на след
# Орбита и след пересчитываются, когда момент сдвинулся на столько
# секунд: за 30 с низкий спутник проходит 230 км, полоса витка - сотни.
ORBIT_REFRESH = 30.0


def path(f, index, seconds):
    """Виток орбиты и след спутника index на момент seconds.

    Орбита - положения на один период вперёд в инерциальной системе,
    повёрнутые в систему Земли на сам момент. Так виток замкнут
    и стоит на звёздах, Земля под ним поворачивается. След - точки
    под спутником от половины периода назад до половины вперёд с учётом
    вращения Земли. Возвращает (широты, долготы, высоты орбиты в метрах,
    широты, долготы следа) или None, если спутник не считается."""
    one = {k: v[index:index + 1] for k, v in f.items()}
    period = 2.0 * math.pi / float(one["no"][0])  # минут
    n = ORBIT_POINTS
    jd = jd_now(seconds)
    many = {k: np.repeat(v, n + 1) for k, v in one.items()}

    steps = np.linspace(0.0, period, n + 1) / 1440.0
    tsince, stale = _since(many, jd + steps)
    r, v, error = sgp4.propagate(many, tsince)
    if stale.any() or error.any():
        return None
    ring = sgp4.teme_to_ecef(r, jd) * 1000.0
    lat, lon, h = ellipsoid.ecef_to_geodetic(ring)

    steps = np.linspace(-0.5 * period, 0.5 * period, n + 1) / 1440.0
    tsince, stale = _since(many, jd + steps)
    r, v, error = sgp4.propagate(many, tsince)
    good = ~stale & (error == 0)
    # Каждая точка следа - своим поворотом Земли.
    g = sgp4.gstime(jd + steps)
    c, s = np.cos(g), np.sin(g)
    under = np.stack([c * r[:, 0] + s * r[:, 1], -s * r[:, 0] + c * r[:, 1],
                      r[:, 2]], axis=1) * 1000.0
    tlat, tlon, _ = ellipsoid.ecef_to_geodetic(under[good])
    return lat, lon, h, tlat, tlon


def heading(point, velocity):
    """Азимут движения точки над Землёй, градусы от севера."""
    lat, lon, _ = ellipsoid.ecef_to_geodetic(point)
    la, lo = math.radians(float(lat)), math.radians(float(lon))
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo),
                      -math.sin(la) * math.sin(lo), math.cos(la)])
    return math.degrees(math.atan2(float(velocity @ east),
                                   float(velocity @ north))) % 360.0


def _since(f, jd):
    """Минуты от эпохи каждого спутника до jd, не дальше MAX_AGE суток,
    и признак «дальше»."""
    tsince = (jd - sgp4.JD_EPOCH0 - f["epoch"]) * 1440.0
    limit = MAX_AGE * 1440.0
    stale = np.abs(tsince) > limit
    return np.clip(tsince, -limit, limit), stale
