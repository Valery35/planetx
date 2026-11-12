# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Звёзды с Млечным путём и атмосфера - строки группы «Небо и свет»,
есть у всех тел. Строки реестра каталога (core/rows.py) и исполнитель.
"""
from qgis.PyQt.QtCore import QObject

from ..core import basemap, stars
from ..core.rows import Row
from ..i18n import tr


class SkyTool(QObject):
    """Звёзды (render/stars.py, картинка неба NASA SVS) и атмосфера."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.loader = None  # картинка неба, один раз за окно

    shown_key = None

    def turn(self, key, on):
        view = self.window.view
        if key == "stars":
            view.set_stars(on)
            if on:
                self.load_sky()
        else:
            # Небо, гало и дымка над поверхностью, просьба автора от
            # 14 октября 2026 года. Без воздуха фон - чёрный космос.
            view.atmosphere = on
            view.update()
        return True

    def load_sky(self):
        """Картинка неба с Млечным путём, один раз за окно. Запрос идёт
        тем же загрузчиком, что и тайлы, картинка раскодируется в его
        потоке. Второй раз она берётся из кэша QGIS."""
        from ..net.loader import TileLoader
        if self.loader is not None:
            return
        view = self.window.view
        source = basemap.Source("NASA SVS", stars.SKY_URL, 0, builtin=True)
        self.loader = TileLoader(source, parent=self.window)
        self.loader.loaded.connect(
            lambda key, rgba, extra: view.set_sky_image(rgba))
        self.loader.want((0, 0, 0), 1.0)

    @staticmethod
    def thumb(key, tile, base):
        """Превью каталога: звёзды Ориона, у атмосферы - цвета строки."""
        if key != "stars":
            return None
        from .nasamaps import stars_image
        return stars_image()

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        if self.loader is not None:
            self.loader.abort()


ROWS = (
    Row("stars", "sky", lambda: (tr("Звёзды"), tr(
        "Звёзды каталога ярких звёзд Йельского университета "
        "и Млечный путь по карте неба NASA. Картинка неба "
        "скачивается при первом показе. Звёзды видны "
        "из космоса и гаснут, когда камера опускается "
        "в атмосферу.")), SkyTool, source="Yale BSC, NASA SVS",
        words=("звёзды", "небо", "млечный путь", "stars", "milky way"),
        default=True, earth=False, before="sun"),
    Row("air", "sky", lambda: (tr("Атмосфера"), tr(
        "Голубое свечение воздуха вокруг планеты, небо над "
        "горизонтом и дымка над далёкой поверхностью. Без флажка "
        "фон вида - чёрный космос, поверхность видна без дымки. "
        "У тел без воздуха строка ничего не меняет.")), SkyTool,
        colors=((10, 15, 40), (90, 150, 230), (200, 225, 250)),
        words=("атмосфера", "воздух", "дымка", "гало", "atmosphere",
               "haze", "air"),
        default=True, earth=False, after="stars"),
)
