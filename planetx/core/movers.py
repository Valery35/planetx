# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Живые объекты без рельсов - суда и самолёты. Просьба автора от
19 октября 2026 года - «делай суда Digitraffic и самолёты adsb.lol».

Расчёт без Qt. Объект - последнее положение со временем, скоростью,
курсом, высотой и скоростью подъёма. Между положениями объект идёт
своим курсом со своей скоростью не дольше extrapolate секунд, новое
положение принимает переходом BLEND секунд, как поезд core.trains.

Объект с известной скоростью поворота (track_rate ADS-B или разность
курсов двух положений) идёт по дуге, а не по прямой. Тангаж модели
самолёта - по подъёму и скорости, крен без данных - координированный,
по скорости поворота (attitude). Просьба автора от 19 октября
2026 года - «кинематику доделывай».
"""
import math
import time

try:  # внутри плагина QGIS
    from .tour import bearing
    from .trains import BLEND, _blend, _metres, destination
except ImportError:  # headless-тесты
    from tour import bearing
    from trains import BLEND, _blend, _metres, destination

KNOT = 1852.0 / 3600.0  # м/с в узле
FOOT = 0.3048
G = 9.81
TURN_MAX = 6.0  # °/с, скорость поворота по двум положениям не больше
TURN_GAP = 60.0  # с, положения дальше друг от друга поворот не дают
ROLL_MAX = 45.0  # крен по скорости поворота не больше


class Sample:
    """Положение объекта: ключ, время (секунды UTC), точка, скорость м/с,
    курс по земле, азимут корпуса (NaN - нет), высота м (NaN - на
    поверхности), подъём м/с, крен (NaN - нет), скорость поворота °/с
    (NaN - нет)."""

    def __init__(self, key, t, lat, lon, speed=0.0, course=math.nan,
                 heading=math.nan, alt=math.nan, climb=0.0, roll=0.0,
                 turn=math.nan):
        self.key = key
        self.t = t
        self.lat = lat
        self.lon = lon
        self.speed = speed
        self.course = course
        self.heading = heading
        self.alt = alt
        self.climb = climb
        self.roll = roll
        self.turn = turn


class Mover:
    """Объект: последнее положение и переход к нему."""

    def __init__(self, sample):
        self.sample = sample
        self.blend_from = None
        self.blend_at = 0.0


class Movers:
    """Объекты на глобусе: положения, точка, азимут и высота на момент.

    extrapolate - ход по своей скорости после положения не дольше, с,
    stale - положение старше этого не показывается, с."""

    def __init__(self, extrapolate=60.0, stale=900.0):
        self.extrapolate = extrapolate
        self.stale = stale
        self.items = {}
        self.info = {}

    def __len__(self):
        return len(self.items)

    def update(self, samples, now, clock=None, keep=False):
        """Новые положения. keep - ответ только части мира (рамка вида):
        объекты вне ответа остаются, пока не устареют."""
        clock = time.time() if clock is None else clock
        seen = set()
        for sample in samples:
            if clock - sample.t > self.stale:
                continue
            seen.add(sample.key)
            item = self.items.get(sample.key)
            if item is None:
                self.items[sample.key] = Mover(sample)
                continue
            if sample.t <= item.sample.t:
                continue
            if sample.turn != sample.turn:
                sample.turn = turn_between(item.sample, sample)
            shown = self.place(item, now, clock)
            item.sample = sample
            item.blend_from = shown
            item.blend_at = now
        for key in list(self.items):
            old = clock - self.items[key].sample.t > self.stale
            if old or (key not in seen and not keep):
                del self.items[key]

    def _ahead(self, sample, clock):
        elapsed = min(max(clock - sample.t, 0.0), self.extrapolate)
        heading = sample.heading if sample.heading == sample.heading \
            else sample.course
        lat, lon = sample.lat, sample.lon
        course = sample.course
        if course == course and sample.speed > 0.0 and elapsed > 0.0:
            turn = sample.turn if sample.turn == sample.turn else 0.0
            bearing, run = arc(course, sample.speed, turn, elapsed)
            lat, lon = destination(lat, lon, bearing, run)
            if heading == heading:
                heading = (heading + turn * elapsed) % 360.0
        alt = sample.alt
        if alt == alt:
            alt = max(alt + sample.climb * elapsed, 0.0)
        return lat, lon, heading, alt

    def place(self, item, now, clock):
        """(широта, долгота, азимут, высота) объекта на экране."""
        lat, lon, heading, alt = self._ahead(item.sample, clock)
        if item.blend_from is not None:
            k = (now - item.blend_at) / BLEND
            if k >= 1.0:
                item.blend_from = None
            else:
                a = item.blend_from
                k = max(k, 0.0)
                lat, lon, heading = _blend(a[:3], (lat, lon, heading), k)
                if a[3] == a[3] and alt == alt:
                    alt = a[3] + k * (alt - a[3])
        return lat, lon, heading, alt

    def attitude(self, item, clock):
        """(тангаж, крен) модели в градусах: тангаж - по подъёму
        и скорости, крен - данный или по скорости поворота."""
        sample = item.sample
        pitch = 0.0
        if sample.alt == sample.alt and sample.speed > 1.0:
            pitch = math.degrees(math.atan2(sample.climb, sample.speed))
        roll = sample.roll
        if roll != roll:
            turn = sample.turn if sample.turn == sample.turn else 0.0
            roll = bank(turn, sample.speed)
            if sample.alt != sample.alt:
                roll = 0.0
        return pitch, roll

    def positions(self, now, clock=None):
        """[(ключ, широта, долгота, азимут, высота)] на момент."""
        clock = time.time() if clock is None else clock
        return [(key,) + self.place(item, now, clock)
                for key, item in self.items.items()]


def arc(course, speed, turn, seconds):
    """(азимут хорды, длина хорды) пути с постоянной скоростью speed м/с
    и поворотом turn °/с за seconds секунд от курса course."""
    run = speed * seconds
    swing = math.radians(turn * seconds)
    if abs(swing) < 1e-6:
        return course, run
    chord = 2.0 * run / swing * math.sin(swing / 2.0)
    return (course + math.degrees(swing) / 2.0) % 360.0, abs(chord)


def turn_between(old, new):
    """Скорость поворота °/с по курсам двух положений или NaN."""
    gap = new.t - old.t
    if not (0.0 < gap <= TURN_GAP) or old.course != old.course \
            or new.course != new.course or new.speed <= 0.0:
        return math.nan
    delta = (new.course - old.course + 180.0) % 360.0 - 180.0
    return min(max(delta / gap, -TURN_MAX), TURN_MAX)


def bank(turn, speed):
    """Координированный крен по скорости поворота °/с и скорости м/с."""
    roll = math.degrees(math.atan(math.radians(turn) * speed / G))
    return min(max(roll, -ROLL_MAX), ROLL_MAX)


CHASE_MIN = 50.0  # м, камера следом не ближе к объекту


def chase(lat, lon, heading, height, reach, tilt):
    """Поза камеры следом за объектом на высоте height над поверхностью:
    (широта и долгота точки взгляда, азимут взгляда, расстояние до неё).
    Камера в reach метрах позади объекта по курсу heading, наклон tilt
    от отвеса. Объект лежит на луче взгляда: точка взгляда - продолжение
    луча через объект до поверхности, впереди на height · tan(tilt).
    Азимут берётся в самой точке взгляда - курс по дуге большого круга
    там другой, и объект уходил бы вбок."""
    height = max(float(height), 0.0) if height == height else 0.0
    tilt = min(max(float(tilt), 0.0), 85.0)
    reach = max(float(reach), CHASE_MIN)
    ahead = height * math.tan(math.radians(tilt))
    if ahead < 1.0:
        return lat, lon, heading, reach
    look_lat, look_lon = destination(lat, lon, heading, ahead)
    look = (bearing(look_lat, look_lon, lat, lon) + 180.0) % 360.0
    return look_lat, look_lon, look, \
        reach + height / math.cos(math.radians(tilt))


CHASE_PASSES = 3


def chase_on(lat, lon, heading, alt, ground, reach, tilt):
    """chase для объекта на высоте alt (как у ground, высоты на экране)
    над неровной поверхностью ground(lat, lon): высота берётся над
    рельефом в точке взгляда, а не под объектом. Над впадиной Марса
    рельеф в 3.7 км впереди выше на 44 м, при 150 м до самолёта он
    уходил на 16° вниз от середины кадра."""
    look_lat, look_lon = lat, lon
    out = None
    for _ in range(CHASE_PASSES):
        height = alt - ground(look_lat, look_lon)
        if height != height:
            height = 0.0
        out = chase(lat, lon, heading, height, reach, tilt)
        look_lat, look_lon = out[0], out[1]
    return out


def near(lat, lon, other_lat, other_lon, reach):
    """Ближе ли точка reach метров."""
    return _metres(lat, lon, other_lat, other_lon) <= reach
