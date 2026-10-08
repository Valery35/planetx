# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слои NASA GIBS в видеокарте: картинки тайлов и окна в них.

Облака и температура суши и моря лежат своими текстурами шейдера
тайла, с премноженной альфой, см. LAYERS. Тайл глубже предельного
уровня слоя берёт часть картинки предка. Пока картинка тайла
не пришла, берётся часть ближайшего готового предка, как у наложения
(core/overlay.py). Загрузчик создаёт окно глобуса, здесь он только
зовётся.
"""
import time

from ..core import clouds, sun, temperature, terrain
from ..core.clouds import source_key
from ..core.overlay import window
from . import gpu

MAX_IMAGES = 300  # картинок слоя в видеокарте
UPLOADS = 1  # картинок слоя за кадр
# Набор нужных тайлов уходит загрузчику не чаще, при перелёте он меняется
# каждый кадр.
ASK_PERIOD = 0.3
# Слои снизу вверх: имя, предельный уровень, текстурный блок, имена
# переменных шейдера. Наложение слоёв проекта - блок 1, между морем
# и облаками, см. shaders.TILE_FRAGMENT.
# Уклон и экспозиция (core/slope.py) - блок 5, по тайлам высот, его
# предельный уровень - уровень высот тела, окно ставит его при смене тела.
LAYERS = (("sea", temperature.MAX_LEVEL, 3, "u_sea", "u_sea_uv"),
          ("land", temperature.MAX_LEVEL, 4, "u_land", "u_land_uv"),
          ("slope", terrain.MAX_LEVEL, 5, "u_slope", "u_slope_uv"),
          # Видимость из точки (core/viewshed.py) - блок 6, уровень
          # ставит окно по шагу расчёта.
          ("viewshed", terrain.MAX_LEVEL, 6, "u_viewshed", "u_viewshed_uv"),
          # Инсоляция (core/insolation.py) - блок 7, так же.
          ("insolation", terrain.MAX_LEVEL, 7, "u_insolation",
           "u_insolation_uv"),
          # Маска выреза блока подземного режима (ui/subsurface.py) -
          # блок 8. В шейдере не смешивается, а отбрасывает поверхность.
          ("cut", 16, 8, "u_cut", "u_cut_uv"),
          # Тема NASA GIBS (core/themes.py) - блок 9, одна тема за раз,
          # уровень ставит окно по слою темы.
          ("theme", 9, 9, "u_theme", "u_theme_uv"),
          # Огни городов (core/sun.py) - блок 10, видны на ночной стороне
          # при включённом солнце, поверх снимка и под облаками.
          ("lights", sun.LIGHTS_LEVEL, 10, "u_lights", "u_lights_uv"),
          # Та же тема на другой день - левая часть шторки сравнения
          # (ui/swipe.py), блок 11, рисуется вместо темы левее шторки.
          ("compare", 9, 11, "u_compare", "u_compare_uv"),
          # Горизонтали рельефа (core/contours.py) - блок 12, по тайлам
          # высот, как уклон, поверх тем и под слоями проекта.
          ("contours", terrain.MAX_LEVEL, 12, "u_contours",
           "u_contours_uv"),
          ("clouds", clouds.MAX_LEVEL, 2, "u_clouds", "u_clouds_uv"))


class GibsLayer:
    """Картинки одного слоя по тайлам источника."""

    def __init__(self, max_level):
        self.max_level = max_level
        self.shown = False
        self.dropping = False  # освободить картинки в следующем кадре
        self.loader = None
        self.textures = {}
        # Картинки прежнего загрузчика: рисуются, пока новый не прислал
        # замену, но просятся у него заново (GlobeView.set_gibs, keep).
        self.stale = set()
        self.used = {}
        self.pending = {}
        self.wanted = frozenset()
        self.asked_at = 0.0
        # Набор сменился, а просьба отложена на ASK_PERIOD. Вид тогда
        # заказывает кадр, иначе без новых кадров она бы не ушла.
        self.unasked = False
        self.missing = 0  # тайлов кадра без своей картинки

    def add(self, key, levels):
        """Пришла картинка тайла, уровни мипмапов."""
        self.pending[key] = levels

    def upload(self, pool, frame, count=UPLOADS):
        """Картинки в видеокарту, не больше count за кадр."""
        for key in sorted(self.pending, key=lambda k: k[0])[:count]:
            levels = self.pending.pop(key)
            self.stale.discard(key)
            if key in self.textures:
                pool.release(self.textures.pop(key))
            self.textures[key] = pool.acquire(levels)
            self.used[key] = frame

    def items(self, draw, clear, frame):
        """Пары (текстура, окно) для тайлов draw. Заодно просит
        недостающие картинки у загрузчика."""
        out = []
        wanted = {}
        ready = self.textures.__contains__
        for key in draw:
            own = source_key(key, self.max_level)
            found = window(key, ready, max_depth=key[0])
            if found is None:
                out.append((clear, gpu.NO_OVERLAY))
            else:
                out.append((self.textures[found[0]], found[1]))
                self.used[found[0]] = frame
            if found is None or found[0] != own or own in self.stale:
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
        if len(self.textures) <= MAX_IMAGES:
            return
        spare = sorted((self.used.get(k, 0), k) for k in self.textures
                       if self.used.get(k, 0) < frame)
        for _, key in spare[:len(self.textures) - int(MAX_IMAGES * 0.9)]:
            pool.release(self.textures.pop(key))
            self.used.pop(key, None)

    def drop(self, pool):
        """Все картинки обратно в запас, например при смене даты."""
        for texture in self.textures.values():
            pool.release(texture)
        self.textures.clear()
        self.stale.clear()
        self.used.clear()
        self.pending.clear()
        self.wanted = frozenset()
        self.unasked = False
        self.dropping = False
