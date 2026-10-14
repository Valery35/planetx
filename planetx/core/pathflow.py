# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поток по пути: короткие штрихи бегут от первой точки к последней.

Просьба автора от 15 октября 2026 года - показ логистики. Дуги над
землёй с бегущей головой похожи на траектории на военных картах, поэтому
путь лежит на земле, а по нему ровно бегут штрихи цвета линии, без голов
и вспышек. Шаг штрихов - доля ширины видимой полосы, так поток выглядит
одинаково на любом расстоянии камеры. Скорость одна для всех путей.

Модуль Qt не знает.
"""
import math

import numpy as np

try:  # внутри плагина QGIS
    from . import ellipsoid
except ImportError:  # headless-тесты
    import ellipsoid

STEP = 0.25  # градусов дуги, наибольший отрезок сгущённого пути
MAX_POINTS = 4000  # точек сгущённого пути, не больше
# Шаг штрихов - доля ширины видимой полосы, длина штриха - доля шага,
# скорость - шагов в секунду. Выбор помощника, утверждает автор.
SPACING_SHARE = 0.06
DASH_SHARE = 0.4
SPEED = 0.6
PARTS = 4  # отрезков в штрихе, чтобы он шёл по изгибу пути
DASH_LIMIT = 3000  # штрихов на все пути вида, не больше
LIGHTEN = 0.55  # доля белого в цвете штриха поверх цвета линии


def _unit(lats, lons):
    la, lo = np.radians(lats), np.radians(lons)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                     np.sin(la)], axis=-1)


def _latlon(units):
    units = units / np.linalg.norm(units, axis=-1, keepdims=True)
    lats = np.degrees(np.arcsin(np.clip(units[..., 2], -1.0, 1.0)))
    lons = np.degrees(np.arctan2(units[..., 1], units[..., 0]))
    return lats, lons


class Path:
    """Сгущённый путь: единичные векторы точек по дугам большого круга
    и пройденное расстояние до каждой точки в метрах."""

    def __init__(self, points):
        pts = [(float(a), float(b)) for a, b in points]
        if len(pts) < 2:
            raise ValueError("a flow path needs two points")
        ends = _unit(np.array([p[0] for p in pts]),
                     np.array([p[1] for p in pts]))
        angles = np.arccos(np.clip(np.einsum(
            "ij,ij->i", ends[:-1], ends[1:]), -1.0, 1.0))
        counts = np.maximum(1, np.ceil(np.degrees(angles) / STEP)).astype(int)
        total = int(counts.sum())
        if total > MAX_POINTS:
            counts = np.maximum(1, (counts * MAX_POINTS // total))
        units = [ends[:1]]
        for a, b, angle, n in zip(ends[:-1], ends[1:], angles, counts):
            t = np.arange(1, n + 1) / float(n)
            if angle < 1e-12:
                part = np.repeat(b[None, :], n, axis=0)
            else:
                s = math.sin(angle)
                part = (np.sin((1.0 - t) * angle)[:, None] * a
                        + np.sin(t * angle)[:, None] * b) / s
            units.append(part)
        self.units = np.vstack(units)
        steps = np.arccos(np.clip(np.einsum(
            "ij,ij->i", self.units[:-1], self.units[1:]), -1.0, 1.0))
        # Радиус тела читается при вызове: set_body меняет его.
        radius = (2.0 * ellipsoid.A + ellipsoid.B) / 3.0
        self.cum = np.concatenate([[0.0], np.cumsum(steps)]) * radius
        self.length = float(self.cum[-1])

    def at(self, distances):
        """Широты и долготы точек на расстояниях distances от начала."""
        d = np.clip(np.asarray(distances, dtype=np.float64), 0.0,
                    self.length)
        i = np.clip(np.searchsorted(self.cum, d, side="right") - 1, 0,
                    len(self.cum) - 2)
        span = self.cum[i + 1] - self.cum[i]
        share = np.where(span > 0.0, (d - self.cum[i]) / np.where(
            span > 0.0, span, 1.0), 0.0)
        units = self.units[i] + (self.units[i + 1] - self.units[i]) \
            * share[..., None]
        return _latlon(units)


def spacing_for(width):
    """Шаг штрихов в метрах для ширины видимой полосы width, м."""
    return max(float(width), 1.0) * SPACING_SHARE


def dash_ranges(length, spacing, phase):
    """Начала и концы штрихов (n, 2) в метрах вдоль пути длиной length.
    phase - доля шага 0..1, сдвиг от времени. Штрих у конца пути
    обрезается концом."""
    dash = spacing * DASH_SHARE
    first = (phase % 1.0) * spacing - spacing
    starts = first + np.arange(int(math.ceil((length - first) / spacing))
                               + 1) * spacing
    ends = starts + dash
    keep = (ends > 0.0) & (starts < length)
    return np.stack([np.clip(starts[keep], 0.0, length),
                     np.clip(ends[keep], 0.0, length)], axis=-1)


def dashes(path, spacing, phase, parts=PARTS, near=None):
    """Точки штрихов пути: широты и долготы (n, parts + 1).

    near - (широта, долгота, угол в градусах): только штрихи, середина
    которых ближе этого угла к точке. Вблизи путь в тысячи километров
    дал бы десятки тысяч штрихов, видны из них единицы."""
    ranges = dash_ranges(path.length, spacing, phase)
    if near is not None and len(ranges):
        lat, lon, angle = near
        middle = path.at(ranges.mean(axis=1))
        cos = _unit(middle[0], middle[1]) @ _unit(lat, lon)
        ranges = ranges[cos >= math.cos(math.radians(min(angle, 180.0)))]
    if not len(ranges):
        return np.zeros((0, parts + 1)), np.zeros((0, parts + 1))
    t = np.linspace(0.0, 1.0, parts + 1)
    d = ranges[:, :1] + (ranges[:, 1:] - ranges[:, :1]) * t[None, :]
    return path.at(d)


def phase_at(seconds):
    """Сдвиг штрихов на момент seconds, доля шага."""
    return (float(seconds) * SPEED) % 1.0


def dash_color(color):
    """Цвет штриха RGBA 0-1: цвет линии, высветленный долей LIGHTEN,
    непрозрачность - как у линии."""
    r, g, b, a = (c / 255.0 for c in color)
    mix = [c + (1.0 - c) * LIGHTEN for c in (r, g, b)]
    return (mix[0], mix[1], mix[2], max(a, 0.6))
