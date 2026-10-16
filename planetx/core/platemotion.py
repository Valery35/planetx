# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скорости литосферных плит по модели NNR-MORVEL56.

Просьба автора от 16 октября 2026 года после списка геофизики. Плита
вращается вокруг своего полюса с угловой скоростью ω, скорость точки
на её поверхности - ω × r, в системе без суммарного вращения плит
(NNR). Полюса - Table 1 статьи Argus, Gordon, DeMets 2011, плита
точки - растр кодов PB2002 (Bird 2003), файл data/plate_motion.json
собирает tools/build_plate_motion.py.

Стрелки на глобусе - сетка узлов около ARROWS_ACROSS поперёк вида,
длина стрелки пропорциональна скорости, LENGTH_SHARE шага узлов на
REFERENCE мм/год. Величины - выбор помощника, утверждает автор.

Модуль Qt не знает.
"""
import base64
import json
import math
import zlib

import numpy as np

RADIUS = 6371.0e6  # мм, средний радиус Земли
ARROWS_ACROSS = 7
REFERENCE = 50.0  # мм/год
LENGTH_SHARE = 0.45
HEAD_SHARE = 0.3  # доля длины стрелки на её усики
HEAD_ANGLE = 25.0  # градусов между древком и усиком
WINDOW = 1.0  # ширин вида - охват сетки стрелок
MAX_LAT = 80.0
STEPS = (30.0, 20.0, 15.0, 10.0, 5.0, 3.0, 2.0, 1.0, 0.5, 0.25)
ATTRIBUTION = ("Plate motion: NNR-MORVEL56, Argus et al. 2011",
               "https://doi.org/10.1029/2011GC003751")


class Motion:
    """Полюса плит и растр плит."""

    def __init__(self, plates, grid, step):
        self.codes = [p[0] for p in plates]
        self.names = {p[0]: p[1] for p in plates}
        self.poles = {p[0]: (p[2], p[3], p[4]) for p in plates}
        self.grid = grid
        self.step = step

    def plate_at(self, lat, lon):
        """Код плиты в точке или None."""
        rows, cols = self.grid.shape
        r = int(min(max((90.0 - lat) / self.step, 0), rows - 1))
        c = int(((lon + 180.0) % 360.0) / self.step) % cols
        n = int(self.grid[r, c])
        return self.codes[n - 1] if n else None

    def velocity(self, lat, lon):
        """(код, восток, север мм/год) или None вне плит."""
        code = self.plate_at(lat, lon)
        if code is None:
            return None
        east, north = velocity(self.poles[code], lat, lon)
        return code, east, north


def read(text):
    data = json.loads(text)
    step = float(data["step"])
    rows, cols = int(round(180 / step)), int(round(360 / step))
    grid = np.frombuffer(zlib.decompress(base64.b64decode(data["grid"])),
                         dtype=np.uint8).reshape(rows, cols)
    return Motion(data["plates"], grid, step)


def _unit(lat, lon):
    la, lo = math.radians(lat), math.radians(lon)
    return np.array([math.cos(la) * math.cos(lo),
                     math.cos(la) * math.sin(lo), math.sin(la)])


def velocity(pole, lat, lon):
    """Скорость точки (восток, север) мм/год при вращении вокруг полюса
    (широта, долгота, °/млн лет) против часовой стрелки."""
    plat, plon, rate = pole
    omega = _unit(plat, plon) * math.radians(rate) / 1.0e6  # рад/год
    r = _unit(lat, lon) * RADIUS
    v = np.cross(omega, r)
    la, lo = math.radians(lat), math.radians(lon)
    east = np.array([-math.sin(lo), math.cos(lo), 0.0])
    north = np.array([-math.sin(la) * math.cos(lo),
                      -math.sin(la) * math.sin(lo), math.cos(la)])
    return float(v @ east), float(v @ north)


def speed_azimuth(east, north):
    """Скорость мм/год и азимут движения, градусы от севера."""
    return math.hypot(east, north), \
        math.degrees(math.atan2(east, north)) % 360.0


def step_for(width_m):
    """Шаг узлов стрелок, градусы, около ARROWS_ACROSS поперёк вида
    шириной width_m метров."""
    degrees = width_m / 111320.0 / ARROWS_ACROSS
    for step in STEPS:
        if step <= degrees:
            return step
    return STEPS[-1]


def _offset(lat, lon, east_deg, north_deg):
    """Точка в east_deg, north_deg градусах дуги от (lat, lon)."""
    la = lat + north_deg
    lo = lon + east_deg / max(math.cos(math.radians(lat)), 0.05)
    return la, (lo + 180.0) % 360.0 - 180.0


def arrows(motion, lat, lon, width_m):
    """Стрелки скоростей у вида: список (широта, долгота, скорость,
    азимут, ломаные стрелки [[(широта, долгота)]]). Узлы - сетка шага
    step_for в WINDOW ширинах вида, широты до MAX_LAT."""
    step = step_for(width_m)
    # Охват - половина WINDOW ширин вида в каждую сторону, не дальше
    # видимого полушария.
    reach = min(width_m * WINDOW / 2.0 / 111320.0, 90.0)
    lat0 = math.floor(lat / step) * step
    lon0 = math.floor(lon / step) * step
    count = int(reach / step) + 1
    out = []
    for i in range(-count, count + 1):
        la = lat0 + i * step
        if abs(la) > MAX_LAT:
            continue
        # Долготы - в охвате вида, растянутом к полюсам, но не больше
        # одного оборота.
        stretch = 1.0 / max(math.cos(math.radians(la)), 0.2)
        half = min(reach * stretch, 180.0)
        across = int(half / step)
        for j in range(-across, across + 1):
            if half >= 180.0 and j == across:
                continue  # -180° и 180° - одна долгота
            lo = (lon0 + j * step + 180.0) % 360.0 - 180.0
            found = motion.velocity(la, lo)
            if found is None:
                continue
            _, east, north = found
            speed, azimuth = speed_azimuth(east, north)
            if speed < 0.5:
                continue
            length = step * LENGTH_SHARE * speed / REFERENCE
            de, dn = east / speed * length, north / speed * length
            tip = _offset(la, lo, de, dn)
            lines = [[(la, lo), tip]]
            head = length * HEAD_SHARE
            for turn in (HEAD_ANGLE, -HEAD_ANGLE):
                a = math.radians(azimuth + 180.0 + turn)
                lines.append([tip, _offset(tip[0], tip[1],
                                           head * math.sin(a),
                                           head * math.cos(a))])
            out.append((la, lo, speed, azimuth, lines))
    return out
