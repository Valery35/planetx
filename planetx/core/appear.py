# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проявление картинок слоя по тайлам вида.

Слой карты (тема NASA, карта значений, геологическая карта, наложение
слоёв проекта) рисует на тайле свою картинку или часть картинки предка,
пока своя не пришла (core/overlay.window). Смена части предка на свою
картинку меняет разрешение скачком, а тайл, у которого не было ничего,
появлялся сразу целиком. Просьба автора от 17 октября 2026 года -
«пусть тайлы плавно возникают», «лучше систему создать».

Правило одно для всех слоёв и то же, что у подложки (render/view.py,
_tile_fades). Для тайла вида помнится уровень картинки, которой он был
нарисован в прошлом кадре, - своей или предка. Пришла картинка на d
уровней подробнее - она рисуется со сдвигом уровня мипмапа d + EXTRA,
то есть с разрешением прежней, и за DURATION с становится резкой. Тайл,
у которого не было никакой картинки, проявляется из прозрачности за то
же время. Новый тайл вида (деление родителя) берёт прежний уровень
у ближайшего нарисованного предка. Удаление от камеры, то есть переход
к более грубой картинке, идёт без проявления.

Кривая - половина косинуса: начало держится, конец мягко приходит
к резкой картинке.
"""

import math

DURATION = 0.7  # с, как TILE_FADE подложки
EXTRA = 1.0  # уровней мипмапа сверх разницы, как FADE_EXTRA подложки
LEVELS = 3  # выше скольких уровней искать предка нового тайла
NONE = -1  # уровень «картинки не было»
STILL = (0.0, 0.0)  # проявления нет: сдвиг мипмапа, доля прозрачности


def curve(share):
    """Доля, оставшаяся от начального значения, share - доля времени
    0..1. 1 в начале, 0 в конце."""
    if share >= 1.0:
        return 0.0
    if share <= 0.0:
        return 1.0
    return 0.5 * (1.0 + math.cos(math.pi * share))


class Appear:
    """Проявление картинок одного слоя. step зовётся каждый кадр
    с тайлами вида и уровнями их картинок."""

    def __init__(self, duration=DURATION):
        self.duration = duration
        self.last = {}  # тайл вида - уровень картинки в прошлом кадре
        # тайл вида - (начало, уровень картинки, сдвиг, прозрачность)
        self.states = {}

    def clear(self):
        """Забыть всё: смена источника, дня, тела. Следующий кадр
        рисуется без проявления."""
        self.last = {}
        self.states = {}

    def _before(self, key):
        """Уровень картинки тайла в прошлом кадре: своей строки или
        ближайшего нарисованного предка. None - тайла и предков
        в прошлом кадре не было."""
        if key in self.last:
            return self.last[key]
        z, x, y = key
        for up in range(1, LEVELS + 1):
            if z - up < 0:
                break
            parent = (z - up, x >> up, y >> up)
            if parent in self.last:
                return self.last[parent]
        return None

    def step(self, draw, levels, now, enabled=True):
        """Значения проявления для тайлов draw: список (сдвиг уровня
        мипмапа, доля прозрачности) по одному на тайл. levels - уровень
        картинки каждого тайла или None, если картинки нет. enabled -
        проявление включено, иначе всё сразу резкое (снимок вида,
        запись тура, проверочный режим)."""
        out = []
        last = {}
        states = {}
        for key, level in zip(draw, levels):
            level = NONE if level is None else level
            last[key] = level
            if not enabled or level == NONE:
                out.append(STILL)
                continue
            state = self.states.get(key)
            if state is None or state[1] != level:
                before = self._before(key)
                state = None
                if before is not None and before < level:
                    if before == NONE:
                        state = (now, level, 0.0, 1.0)
                    else:
                        state = (now, level, level - before + EXTRA, 0.0)
            if state is None:
                out.append(STILL)
                continue
            left = curve((now - state[0]) / self.duration)
            if left <= 0.0:
                out.append(STILL)
                continue
            out.append((state[2] * left, state[3] * left))
            states[key] = state
        self.last = last
        self.states = states
        return out

    def busy(self):
        """Идёт ли проявление - вид тогда просит следующий кадр."""
        return bool(self.states)
