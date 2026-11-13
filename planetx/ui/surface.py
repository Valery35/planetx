# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Уклон, экспозиция и горизонтали по высотам тела - строки реестра
каталога (core/rows.py) и исполнитель. Слои вида «slope» и «contours»
считает рабочий поток (core/slope.py, core/contours.py). Шкала уклона
(window.slope_legend) общая с окном «Уклон и экспозиция» участка
(ui/relief.py), выгрузка горизонталей (window.contour_export) - с меню
растра, они остаются окну.
"""
import math

from qgis.PyQt.QtCore import QObject

from ..core import ellipsoid, slope
from ..core import sources as datasources
from ..core.contours import (LEVEL as CONTOUR_LEVEL,
                             SOURCE_LEVEL as CONTOUR_SOURCE,
                             is_imagery as contour_is_imagery,
                             view_step as contour_view_step)
from ..core.rows import Row
from ..core.terrain import MAX_LEVEL as TERRAIN_MAX
from ..i18n import tr

# Уклон и экспозиция - один слой вида, включена одна из двух строк.
MODES = ("slope", "aspect")
CONTOURS = "contours"


class SurfaceTool(QObject):
    """Слои уклона или экспозиции и горизонталей по строкам и телу."""

    def __init__(self, window):
        from .legend import ContourLegend
        super().__init__(window)
        self.window = window
        # Горизонтали: сечение, крестик и выгрузка в проект.
        self.legend = ContourLegend(window.view)
        self.legend.hide()
        self.legend.closer = lambda: window.set_extra(CONTOURS, False)
        window.legend_panel.add(self.legend)
        window.contour_legend = self.legend
        self.palette = "map"  # жёлтые линии на снимке, коричневые на карте

    shown_key = None

    def turn(self, key, on):
        self.surface_changed()
        return True

    def source(self):
        """Тайлы высот тела: (источник, пол высот, врезки) или None."""
        return self.window._surface_source()

    def surface_changed(self):
        """Слой уклона или экспозиции по строкам и телу. Тайлы высот
        берутся через кэш QGIS, слой считается из них в рабочем потоке
        (core/slope.py)."""
        from .globe.base import slope_prepare
        window = self.window
        view = window.view
        mode = next((k for k in MODES if window.extras.get(k)), None)
        found = self.source()
        self.set_contours(found)
        # Тот же слой вида занимает квадрат окна «Уклон и экспозиция»
        # (ui/relief.py): включённая строка его снимает, без строки он
        # возвращается.
        local = getattr(window, "relief", None)
        if mode is not None and local is not None:
            local.clear(quiet=True)
        if mode is None or found is None or view.sky_view is not None:
            window._set_gibs("slope", False)
            window.slope_legend.hide()
            if local is not None:
                local.show()
            return
        source, floor, insets = found
        view.gibs["slope"].max_level = source.max_level
        encoding = window._terrain_choice()[1] if window.planet.earth \
            else "terrarium"
        window._set_gibs("slope", True, (source, slope_prepare(
            mode, floor, ellipsoid.A, insets, encoding)), cache=True)
        window.slope_legend.set_mode(mode)
        window.slope_legend.show()
        window._place_attribution()

    def set_contours(self, found):
        """Слой горизонталей по строке и телу, независимо от уклона.
        found - источник высот тела, как у уклона."""
        from .contours import ContourSource, digit_glyphs
        from .globe.base import BODY_CONTOUR_DEEPER, contours_prepare
        from .inset import DeepSource
        window = self.window
        view = window.view
        planet = window.planet
        if not window.extras.get(CONTOURS) or found is None \
                or view.sky_view is not None:
            window._set_gibs("contours", False)
            self.legend.hide()
            return
        self.palette = self.palette_for(window.source)
        self.legend.export = \
            window.contour_export.view_contours if planet.earth else None
        self.legend.show()
        self.view_changed()
        source, floor, insets = found
        levels = None
        if planet.earth:
            # Глубже уровня съёмки - по предку (ContourSource, upsample),
            # в открытом море - по уровню глубин. Свой источник высот
            # бывает подробнее, у него - уровень 15.
            land = CONTOUR_SOURCE if source.url == datasources.TERRAIN_URL \
                else TERRAIN_MAX
            source = ContourSource(source.url, view.store, land)
            levels = source.level_of
            deepest = CONTOUR_LEVEL
        else:
            # У тел высоты только до уровня тела (5). Глубже тайл
            # горизонталей - предок, сглаженный и пересчитанный
            # кубически, как на Земле глубже уровня съёмки. Иначе вблизи
            # линии растягивались вместе с тайлом уровня 5. Просьба
            # автора от 11 октября 2026 года.
            top = source.max_level
            source = DeepSource(source.name, source.url, top,
                                source.attribution, missing=source.missing)

            def levels(key, top=top):
                return min(key[0], top)
            deepest = min(CONTOUR_LEVEL, top + BODY_CONTOUR_DEEPER)
        view.gibs["contours"].max_level = deepest
        encoding = window._terrain_choice()[1] if planet.earth \
            else "terrarium"
        window._set_gibs("contours", True, (source, contours_prepare(
            floor, ellipsoid.A, insets, encoding, digit_glyphs(), levels,
            self.palette, view.store, sea=planet.earth)), cache=True)

    def palette_for(self, source):
        """Цвета горизонталей по подложке: imagery - снимок, map -
        карта (core.contours.is_imagery)."""
        imagery = contour_is_imagery(source.name, source.url,
                                     builtin_body=not self.window.planet.earth)
        return "imagery" if imagery else "map"

    def basemap_changed(self, source):
        """Подложка сменилась со снимка на карту или обратно."""
        if self.window.extras.get(CONTOURS) \
                and self.palette_for(source) != self.palette:
            self.set_contours(self.source())

    def view_changed(self):
        """Сечение горизонталей в середине вида на шкале."""
        if self.legend.isHidden():
            return
        view = self.window.view
        pose = view.navigator.pose
        camera = view.camera
        self.legend.set_step(contour_view_step(
            pose.distance, pose.lat, math.radians(camera.fov_y),
            view.height() * view.devicePixelRatioF(),
            ellipsoid.A, view.gibs["contours"].max_level), self.palette)

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row("slope", "terrain", lambda: (tr("Уклон"), tr(
        "Уклон поверхности по высотам рельефа, классами от "
        "ровного до круче 35°. Шкала стоит в левом нижнем "
        "углу вида. Есть у Земли, Марса и Луны.")), SurfaceTool,
        source="Terrarium",
        colors=tuple(color for _, color in slope.SLOPE_STOPS),
        words=("крутизна", "уклон", "slope"), fades=("slope",),
        view_map="slope", earth=False, relief=True),
    Row("aspect", "terrain", lambda: (tr("Экспозиция"), tr(
        "Куда обращён склон - цвет стороны света, ровное "
        "место серое. Включается вместо уклона.")), SurfaceTool,
        source="Terrarium",
        colors=tuple(color for _, color in slope.ASPECT_STOPS),
        words=("экспозиция", "стороны света", "aspect"), fades=("slope",),
        view_map="slope", earth=False, relief=True, after="slope"),
    Row(CONTOURS, "map", lambda: (tr("Горизонтали"), tr(
        "Линии равных высот рельефа, как на топографической карте. "
        "Сечение подбирается по масштабу вида - от сотен метров "
        "издалека до 5-10 м вблизи, каждая пятая горизонталь "
        "утолщённая и подписана отметкой. Ниже "
        "уровня моря - синие изобаты. Строятся по высотам глобуса "
        "и по своему рельефу растром проекта.")), SurfaceTool,
        source="Terrarium", colors=((150, 100, 60), (250, 220, 60)),
        words=("изолинии", "горизонтали", "изобаты", "contours"),
        fades=("contours",), earth=False, relief=True, after="grid"),
)
