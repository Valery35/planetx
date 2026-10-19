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
Самолёт двух видов (KINDS), как в имитаторе Google Earth Pro, снимок
окна автора от 19 октября 2026 года, - истребитель и винтовой. Прочие
величины вида - в Spec, у самолёта - plane.spec.
Величины - выбор помощника, утверждает автор.
"""
import math

try:  # внутри плагина QGIS
    from .trains import destination
except ImportError:  # headless-тесты
    from trains import destination

G = 9.81
# Скорость поднята по замечанию автора от 19 октября 2026 года -
# «скорость полёта маловата», прежде 140 м/с, 6 м/с² и старт 300 км/ч.
MAX_SPEED = 280.0  # м/с при полной тяге, около 1000 км/ч
THRUST = 12.0  # м/с² при полной тяге
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
START_SPEED = 500.0 / 3.6
STEP_MAX = 0.1  # с, длиннее шаг делится


class Spec:
    """Вид самолёта: наибольшая скорость (м/с), тяга (м/с²), скорость
    сваливания, крен и тангаж (°/с и предел), старт (м/с), длина (м)."""

    def __init__(self, max_speed, thrust, stall, roll_rate, roll_max,
                 pitch_rate, pitch_max, start, length):
        self.max_speed = max_speed
        self.thrust = thrust
        self.drag = thrust / max_speed ** 2
        self.stall = stall
        self.roll_rate = roll_rate
        self.roll_max = roll_max
        self.pitch_rate = pitch_rate
        self.pitch_max = pitch_max
        self.start = start
        self.length = length


FIGHTER, LIGHT = "fighter", "light"
KINDS = {
    # Истребитель: до 2000 км/ч, старт 900 км/ч, крен 90°/с.
    FIGHTER: Spec(555.0, 30.0, 70.0, 90.0, 80.0, 20.0, 35.0, 250.0, 15.0),
    # Винтовой четырёхместный: до 340 км/ч, старт 250 км/ч.
    LIGHT: Spec(95.0, 4.0, 28.0, 45.0, 60.0, 12.0, 25.0, 250.0 / 3.6, 8.0),
}
MIDDLE = Spec(MAX_SPEED, THRUST, STALL, ROLL_RATE, ROLL_MAX, PITCH_RATE,
              PITCH_MAX, START_SPEED, 16.0)


def cruise_throttle(speed, spec=MIDDLE):
    """Тяга ровного полёта на скорости speed."""
    return min(max((speed / spec.max_speed) ** 2, 0.0), 1.0)


class Plane:
    """Состояние самолёта: широта, долгота, высота над уровнем моря (м),
    курс, тангаж, крен (°), скорость (м/с), тяга 0..1, подъём (м/с)."""

    def __init__(self, lat, lon, alt, heading, speed=None, kind=None):
        self.spec = KINDS.get(kind, MIDDLE)
        self.kind = kind
        speed = self.spec.start if speed is None else speed
        self.lat = float(lat)
        self.lon = float(lon)
        self.alt = float(alt)
        self.heading = float(heading) % 360.0
        self.pitch = 0.0
        self.roll = 0.0
        self.speed = float(speed)
        self.throttle = cruise_throttle(speed, self.spec)
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
    spec = plane.spec
    plane.throttle = min(max(plane.throttle
                             + throttle_in * THROTTLE_RATE * dt, 0.0), 1.0)
    if roll_in:
        plane.roll = min(max(plane.roll + roll_in * spec.roll_rate * dt,
                             -spec.roll_max), spec.roll_max)
    else:
        plane.roll = _toward(plane.roll, 0.0, ROLL_RETURN * dt)
    if pitch_in:
        plane.pitch += pitch_in * spec.pitch_rate * dt
    if plane.speed < spec.stall:
        plane.pitch -= STALL_DROP * dt
    plane.pitch = min(max(plane.pitch, -spec.pitch_max), spec.pitch_max)
    pitch = math.radians(plane.pitch)
    accel = spec.thrust * plane.throttle - spec.drag * plane.speed ** 2 \
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


def tape(value, step, half):
    """Деления ленты прибора: [(отметка, отступ от value)] для отметок,
    кратных step, в пределах value ± half."""
    first = math.ceil((value - half) / step)
    last = math.floor((value + half) / step)
    return [(n * step, n * step - value) for n in range(first, last + 1)]


def heading_tape(heading, step, half):
    """Деления ленты курса: отметки 0..359 с переходом через север."""
    return [(mark % 360.0, offset)
            for mark, offset in tape(heading, step, half)]


def ladder(pitch, step=5.0, reach=25.0):
    """Ступени шкалы тангажа у текущего тангажа: [(отметка, угол от оси
    взгляда)], отметки не круче ±90°."""
    return [(mark, mark - pitch) for mark, offset in tape(pitch, step, reach)
            if abs(mark) <= 90.0]


def ladder_offset(angle, focal):
    """Отступ ступени шкалы тангажа на экране вверх от середины в
    пикселях: focal - фокусное расстояние кадра в тех же пикселях."""
    angle = max(min(angle, 89.0), -89.0)
    return focal * math.tan(math.radians(angle))


def readout(plane, ground):
    """Показания для строки на экране: скорость км/ч, высота над уровнем
    моря и над поверхностью м, курс °, подъём м/с, тяга %."""
    return {"speed": plane.speed * 3.6, "alt": plane.alt,
            "height": plane.alt - ground, "heading": plane.heading,
            "climb": plane.climb, "throttle": 100.0 * plane.throttle}
