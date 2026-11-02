# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Общий слой вида окон анализа участка.

Слой вида «viewshed» делят видимость из точки, классификация, похожие
области, минералы по спектру, минералы EMIT и земляные работы. У слоя
один хозяин: инструмент, который показывает результат, занимает слой
(SiteLayer.claim), прежний хозяин снимает свой результат сам (drop).
Так новый инструмент не правит прежние. Решение автора от 2 ноября
2026 года - «стандартизируй инструменты анализа по максимуму».

SiteTool - общая основа показа результата инструмента на этом слое:
картинки тайлов, глубина, непрозрачность, снятие и очистка.
"""
import math

LAYER = "viewshed"  # слой вида, общий у окон анализа участка


def result_level(result):
    """Глубина тайлов слоя вида по шагу сетки результата."""
    lat = (result["box"][1] + result["box"][3]) / 2.0
    pixel = 2 * math.pi * 6378137.0 * math.cos(math.radians(lat)) / 256
    return max(1, min(18, int(math.ceil(math.log2(pixel
                                                  / result["step"])))))


class SiteLayer:
    """Хозяин общего слоя вида у окна глобуса."""

    def __init__(self):
        self.owner = None

    def claim(self, owner):
        """owner показывает свой результат: прежний хозяин снимает свой,
        слой вида при этом не выключается."""
        old, self.owner = self.owner, owner
        if old is not None and old is not owner:
            old.drop()

    def release(self, owner):
        if self.owner is owner:
            self.owner = None


class SiteTool:
    """Основа показа результата инструмента на общем слое вида.
    Наследник держит window и tiles, задаёт forget - что снимается
    вместе с картинками (результат, кнопка OK)."""

    window = None
    tiles = None

    def put_tiles(self, tiles, level, opacity=None, keep=False):
        """Картинки тайлов tiles на общем слое: занять слой, глубина
        level, непрозрачность opacity (None - как есть). keep - новые
        картинки ложатся поверх прежних без мигания."""
        window = self.window
        view = window.view
        window.site_layer.claim(self)
        old = self.tiles
        self.tiles = None
        if old is not None:
            old.abort()
            old.deleteLater()
        tiles.loaded.connect(lambda key, rgba, levels:
                             view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        layer = view.gibs[LAYER]
        layer.max_level = level
        layer.empty.clear()
        view.set_gibs(LAYER, True, tiles, keep=keep)
        layer.fade = 0.0 if opacity is None else 1.0 - opacity
        view.update()

    def set_opacity(self, value):
        """Непрозрачность результата - доля прозрачности слоя вида, без
        пересборки картинок тайлов."""
        if self.tiles is None:
            return
        self.window.view.gibs[LAYER].fade = 1.0 - value
        self.window.view.update()

    def _drop_tiles(self):
        if self.tiles is not None:
            # Прозрачность слоя у видимости своя.
            self.window.view.gibs[LAYER].fade = 0.0
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def forget(self):
        """Что снимается вместе с картинками, у наследника."""

    def drop(self):
        """Слой вида занимает другой инструмент: результат снимается без
        выключения слоя."""
        self._drop_tiles()
        self.forget()

    def clear(self):
        """Результат снимается, свой слой выключается."""
        shown = self.tiles is not None
        self.drop()
        self.window.site_layer.release(self)
        if shown:
            self.window.view.set_gibs(LAYER, False)


class ViewshedOwner:
    """Видимость из точки как хозяин общего слоя: её картинки держит
    окно глобуса (globe/tools.py)."""

    def __init__(self, window):
        self.window = window

    def drop(self):
        self.window._drop_viewshed()
