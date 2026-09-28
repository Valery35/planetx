# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака в видеокарте: картинки тайлов и окна в них для тайлов кадра.

Облака лежат третьей текстурой шейдера тайла, поверх подложки
и наложения, с премноженной альфой. Тайл глубже уровня
core.clouds.MAX_LEVEL берёт часть картинки предка. Пока картинка
тайла не пришла, берётся часть ближайшего готового предка, как
у наложения (core/overlay.py). Загрузчик создаёт окно глобуса,
здесь он только зовётся.
"""
import time

from ..core import clouds
from ..core.overlay import window
from . import gpu

MAX_CLOUDS = 300  # картинок облаков в видеокарте
UPLOADS = 1  # картинок облаков за кадр
# Набор нужных тайлов уходит загрузчику не чаще, при перелёте он меняется
# каждый кадр.
ASK_PERIOD = 0.3


class Clouds:
    """Картинки облаков по тайлам снимка."""

    def __init__(self):
        self.loader = None
        self.textures = {}
        self.used = {}
        self.pending = {}
        self.wanted = frozenset()
        self.asked_at = 0.0
        # Набор сменился, а просьба отложена на ASK_PERIOD. Вид тогда
        # заказывает кадр, иначе без новых кадров она бы не ушла.
        self.unasked = False
        self.missing = 0  # тайлов кадра без своей картинки облаков

    def add(self, key, levels):
        """Пришла картинка облаков, уровни мипмапов."""
        self.pending[key] = levels

    def upload(self, pool, frame, count=UPLOADS):
        """Картинки в видеокарту, не больше count за кадр."""
        for key in sorted(self.pending, key=lambda k: k[0])[:count]:
            levels = self.pending.pop(key)
            if key in self.textures:
                pool.release(self.textures.pop(key))
            self.textures[key] = pool.acquire(levels)
            self.used[key] = frame

    def items(self, draw, clear, frame):
        """Пары (текстура облаков, окно) для тайлов draw. Заодно просит
        недостающие картинки у загрузчика."""
        out = []
        wanted = {}
        ready = self.textures.__contains__
        for key in draw:
            own = clouds.source_key(key)
            found = window(key, ready, max_depth=key[0])
            if found is None:
                out.append((clear, gpu.NO_OVERLAY))
            else:
                out.append((self.textures[found[0]], found[1]))
                self.used[found[0]] = frame
            if found is None or found[0] != own:
                wanted[own] = -own[0]
        self.missing = len(wanted)
        keys = frozenset(wanted)
        now = time.monotonic()
        self.unasked = self.loader is not None and keys != self.wanted
        if self.unasked and now - self.asked_at > ASK_PERIOD:
            self.loader.want_many(wanted.items())
            self.loader.retain(wanted)
            self.wanted = keys
            self.asked_at = now
            self.unasked = False
        return out

    def evict(self, pool, frame):
        """Лишние картинки обратно в запас, самые давние первыми."""
        if len(self.textures) <= MAX_CLOUDS:
            return
        spare = sorted((self.used.get(k, 0), k) for k in self.textures
                       if self.used.get(k, 0) < frame)
        for _, key in spare[:len(self.textures) - int(MAX_CLOUDS * 0.9)]:
            pool.release(self.textures.pop(key))
            self.used.pop(key, None)

    def drop(self, pool):
        """Все картинки обратно в запас, например при смене даты."""
        for texture in self.textures.values():
            pool.release(texture)
        self.textures.clear()
        self.used.clear()
        self.pending.clear()
        self.wanted = frozenset()
        self.unasked = False
