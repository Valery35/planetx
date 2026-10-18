# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Живые объекты без рельсов - суда и самолёты. Просьба автора от
19 октября 2026 года - «делай суда Digitraffic и самолёты adsb.lol».

Расчёт без Qt. Объект - последнее положение со временем, скоростью,
курсом, высотой и скоростью подъёма. Между положениями объект идёт
своим курсом со своей скоростью не дольше extrapolate секунд, новое
положение принимает переходом BLEND секунд, как поезд core.trains.
"""
import math
import time

try:  # внутри плагина QGIS
    from .trains import BLEND, _blend, _metres, destination
except ImportError:  # headless-тесты
    from trains import BLEND, _blend, _metres, destination

KNOT = 1852.0 / 3600.0  # м/с в узле
FOOT = 0.3048


class Sample:
    """Положение объекта: ключ, время (секунды UTC), точка, скорость м/с,
    курс по земле, азимут корпуса (NaN - нет), высота м (NaN - на
    поверхности), подъём м/с, крен."""

    def __init__(self, key, t, lat, lon, speed=0.0, course=math.nan,
                 heading=math.nan, alt=math.nan, climb=0.0, roll=0.0):
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
            lat, lon = destination(lat, lon, course,
                                   sample.speed * elapsed)
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

    def positions(self, now, clock=None):
        """[(ключ, широта, долгота, азимут, высота)] на момент."""
        clock = time.time() if clock is None else clock
        return [(key,) + self.place(item, now, clock)
                for key, item in self.items.items()]


def near(lat, lon, other_lat, other_lon, reach):
    """Ближе ли точка reach метров."""
    return _metres(lat, lon, other_lat, other_lon) <= reach
