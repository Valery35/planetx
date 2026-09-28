# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Экранные органы навигации в духе Google Earth: расчёт без Qt.

Органы стоят в правом верхнем углу вида - кольцо компаса с джойстиком
взгляда внутри, джойстик сдвига и ползунок высоты с кнопками плюс
и минус. Здесь лежат углы кольца, отклонение джойстика, связь
положения ползунка с расстоянием и шаги движения за время dt.
Отрисовка и мышь - в ui/navpad.py.

Скорости - умолчания помощника, их назначает автор. Решение автора
от 29 сентября 2026 года - органы как в Google Earth.
"""
import math

LOOK_RATE = 30.0  # градусов в секунду при полном отклонении джойстика
MOVE_RATE = 0.5  # ширин видимой полосы в секунду при полном отклонении
ZOOM_RATE = math.log(2.0)  # плюс и минус - вдвое за секунду
NEAR = 100.0  # метров, расстояние у верхнего края ползунка
FAR = 2.0e7  # метров, у нижнего края
# Показ органов: у угла вида, как в Google Earth, или всё время.
# Решение автора от 29 сентября 2026 года, «никогда» не нужно.
MODES = ("auto", "always")


def ring_angle(x, y):
    """Угол точки (x, y) от центра кольца, по часовой стрелке от верха,
    в градусах. Ось y экрана направлена вниз."""
    return math.degrees(math.atan2(x, -y)) % 360.0


def angle_delta(a0, a1):
    """Кратчайший поворот от a0 к a1, от -180 до 180 градусов."""
    return (a1 - a0 + 180.0) % 360.0 - 180.0


def north_angle(heading):
    """Угол буквы N на кольце: север сдвигается против поворота вида."""
    return (-heading) % 360.0


def ring_turn(a0, a1):
    """Поворот вида, когда кольцо тянут от угла a0 к углу a1. Кольцо
    идёт за курсором вместе с севером, азимут вида меняется обратно."""
    return -angle_delta(a0, a1)


def stick(x, y, radius):
    """Отклонение джойстика от -1 до 1 по осям, длина не больше 1."""
    sx, sy = x / radius, y / radius
    length = math.hypot(sx, sy)
    if length > 1.0:
        sx, sy = sx / length, sy / length
    return sx, sy


def look_step(sx, sy, dt):
    """Поворот взгляда (азимут, наклон) за dt. Вверх - взгляд выше."""
    return sx * LOOK_RATE * dt, -sy * LOOK_RATE * dt


def move_step(sx, sy, dt, width):
    """Сдвиг (вперёд, вправо) в метрах за dt. width - ширина видимой
    полосы, скорость от неё, поэтому сдвиг одинаков на экране."""
    step = MOVE_RATE * width * dt
    return -sy * step, sx * step


def zoom_factor(direction, dt):
    """Множитель расстояния за dt. direction 1 - ближе, -1 - дальше."""
    return math.exp(-direction * ZOOM_RATE * dt)


def slider_share(distance, near=NEAR, far=FAR):
    """Место бегунка от 0 (верх, близко) до 1 (низ, далеко), шкала
    логарифмическая, как высота в Google Earth."""
    distance = min(max(distance, near), far)
    return math.log(distance / near) / math.log(far / near)


def slider_distance(share, near=NEAR, far=FAR):
    """Расстояние по месту бегунка."""
    share = min(max(share, 0.0), 1.0)
    return near * (far / near) ** share
