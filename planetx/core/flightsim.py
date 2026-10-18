# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Режим полёта: свой самолёт с клавиатуры, как имитатор полёта Google
Earth Pro. Просьба автора от 19 октября 2026 года - «в GE был режим
полёта», «да, делай».

Расчёт без Qt. Самолёт - точка, высота над уровнем моря, курс, тангаж,
крен, скорость и тяга. Модель простая, без аэродинамики:
- крен меняется клавишами со скоростью ROLL_RATE, без клавиш выходит
  к нулю со скоростью ROLL_RETURN, не больше ROLL_MAX;
- поворот - координированный, угловая скорость g · tg(крен) / скорость;
- тангаж меняется клавишами со скоростью PITCH_RATE и держится без
  клавиш, не больше PITCH_MAX;
- скорость растёт от тяги (THRUST при полной), падает от сопротивления
  (наибольшая скорость при полной тяге - MAX_SPEED) и от подъёма
  g · sin(тангаж);
- ниже STALL нос опускается сам со скоростью STALL_DROP;
- касание поверхности кончает полёт.
Величины - выбор помощника, утверждает автор.
"""
import math

try:  # внутри плагина QGIS
    from .trains import destination
except ImportError:  # headless-тесты
    from trains import destination

G = 9.81
MAX_SPEED = 140.0  # м/с при полной тяге, около 500 км/ч
THRUST = 6.0  # м/с² при полной тяге
DRAG = THRUST / MAX_SPEED ** 2
STALL = 28.0  # м/с, около 100 км/ч
STALL_DROP = 15.0  # °/с
ROLL_RATE = 45.0  # °/с
ROLL_RETURN = 20.0  # °/с
ROLL_MAX = 60.0
PITCH_RATE = 12.0  # °/с
PITCH_MAX = 25.0
THROTTLE_RATE = 0.4  # доля в секунду
START_HEIGHT = 1000.0  # м над поверхностью
START_SPEED = 300.0 / 3.6
STEP_MAX = 0.1  # с, длиннее шаг делится


def cruise_throttle(speed):
    """Тяга ровного полёта на скорости speed."""
    return min(max((speed / MAX_SPEED) ** 2, 0.0), 1.0)


class Plane:
    """Состояние самолёта: широта, долгота, высота над уровнем моря (м),
    курс, тангаж, крен (°), скорость (м/с), тяга 0..1, подъём (м/с)."""

    def __init__(self, lat, lon, alt, heading, speed=START_SPEED):
        self.lat = float(lat)
        self.lon = float(lon)
        self.alt = float(alt)
        self.heading = float(heading) % 360.0
        self.pitch = 0.0
        self.roll = 0.0
        self.speed = float(speed)
        self.throttle = cruise_throttle(speed)
        self.climb = 0.0
        self.crashed = False


def _toward(value, target, rate):
    if value < target:
        return min(value + rate, target)
    return max(value - rate, target)


def step(plane, dt, pitch_in=0, roll_in=0, throttle_in=0, ground=0.0):
    """Шаг полёта на dt секунд. pitch_in - +1 нос вверх, -1 вниз;
    roll_in - +1 крен вправо, -1 влево; throttle_in - +1 больше тяги,
    -1 меньше. ground - высота поверхности под самолётом над уровнем
    моря. Касание поверхности ставит crashed."""
    if plane.crashed:
        return plane
    left = max(float(dt), 0.0)
    while left > 1e-9:
        part = min(left, STEP_MAX)
        left -= part
        _step(plane, part, pitch_in, roll_in, throttle_in, ground)
        if plane.crashed:
            break
    return plane


def _step(plane, dt, pitch_in, roll_in, throttle_in, ground):
    plane.throttle = min(max(plane.throttle
                             + throttle_in * THROTTLE_RATE * dt, 0.0), 1.0)
    if roll_in:
        plane.roll = min(max(plane.roll + roll_in * ROLL_RATE * dt,
                             -ROLL_MAX), ROLL_MAX)
    else:
        plane.roll = _toward(plane.roll, 0.0, ROLL_RETURN * dt)
    if pitch_in:
        plane.pitch += pitch_in * PITCH_RATE * dt
    if plane.speed < STALL:
        plane.pitch -= STALL_DROP * dt
    plane.pitch = min(max(plane.pitch, -PITCH_MAX), PITCH_MAX)
    pitch = math.radians(plane.pitch)
    accel = THRUST * plane.throttle - DRAG * plane.speed ** 2 \
        - G * math.sin(pitch)
    plane.speed = max(plane.speed + accel * dt, 0.0)
    speed = max(plane.speed, 1.0)
    turn = math.degrees(G * math.tan(math.radians(plane.roll)) / speed)
    plane.heading = (plane.heading + turn * dt) % 360.0
    plane.climb = plane.speed * math.sin(pitch)
    plane.alt += plane.climb * dt
    run = plane.speed * math.cos(pitch) * dt
    if run > 0.0:
        plane.lat, plane.lon = destination(plane.lat, plane.lon,
                                           plane.heading, run)
    if plane.alt <= ground:
        plane.alt = ground
        plane.crashed = True


def readout(plane, ground):
    """Показания для строки на экране: скорость км/ч, высота над уровнем
    моря и над поверхностью м, курс °, подъём м/с, тяга %."""
    return {"speed": plane.speed * 3.6, "alt": plane.alt,
            "height": plane.alt - ground, "heading": plane.heading,
            "climb": plane.climb, "throttle": 100.0 * plane.throttle}
