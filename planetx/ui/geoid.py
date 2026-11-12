# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Геоид EGM2008 (core/geoid.py): пока строка включена, высоты Земли -
тайлы геоида planetx-terrain, растянутые ползунком меню «⋯» строки,
воды и дымки поверхности нет. Строка реестра каталога (core/rows.py)
и исполнитель. Окно спрашивает его крючками heights_replaced,
relief_scale, terrain_source, surface_look и replace_site.
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject

from ..core import basemap, geoid
from ..core.rows import Row
from ..i18n import tr
from .identify import Group

KEY = "geoid"
SCALE_KEY = "PlanetX/geoid_scale"  # масштаб режима «Геоид»


class GeoidTool(QObject):
    """Режим «измятого глобуса»."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        # Шаги проверки подменяют адрес на локальную копию хранилища.
        self.url = geoid.TILE_URL

    shown_key = None

    def on(self):
        window = self.window
        return bool(getattr(window, "extras", {}).get(KEY)) \
            and getattr(window, "planet", None) is not None \
            and window.planet.earth

    def turn(self, key, on):
        """Высоты Земли - тайлы геоида с масштабом, вода не рисуется -
        половина геоида ниже нуля. Выключение возвращает рельеф,
        масштаб и глубины морей."""
        window = self.window
        self.surface_look()
        window._body_terrain(window.planet)
        window.view.reset_heights()
        window.view.set_relief(window._relief_target())
        window._update_water()
        window._place_rows()
        window._mark_gallery()
        window._show_attribution()
        window.view.update()
        return True

    def scale(self):
        """Масштаб режима - настройка ползунка меню «⋯» строки, по
        умолчанию geoid.SCALE."""
        value = QgsSettings().value(SCALE_KEY, geoid.SCALE, type=float)
        return min(geoid.SCALES[-1], max(geoid.SCALES[0], float(value)))

    def set_scale(self, scale):
        """Ползунок масштаба: высоты растягиваются заново сразу, разрез
        Земли следует за поверхностью."""
        window = self.window
        QgsSettings().setValue(SCALE_KEY, float(scale))
        window.panel.geoid_scale = self.scale()
        if self.on():
            window.view.set_relief(window._relief_target())
            window.view.update()

    def heights_replaced(self):
        """Высоты Земли - не рельеф и не дно: воды и глубин морей нет."""
        return self.on()

    def relief_scale(self):
        return self.scale() if self.on() else None

    def terrain_source(self):
        """Источник высот Земли в режиме и его последний уровень."""
        if not self.on():
            return None
        return basemap.Source("EGM2008", self.url, geoid.MAX_LEVEL,
                              builtin=True), geoid.MAX_LEVEL

    def surface_look(self):
        """Вода и дымка поверхности - их нет в режиме. Половина геоида
        ниже нуля, а поверхность опущена на сотни километров, воздух над
        ней заливал впадины белым."""
        window = self.window
        on = self.on()
        window.view.sea_floor = window.sea_depths and window.planet.earth \
            and not on
        window.view.surface_air = not on
        # Разрез Земли тянется к «измятой» поверхности.
        window.view.wedge_lift = on

    def replace_site(self, height):
        """Группа «Геоид» окна «Объекты» вместо «Места» или None: высота
        под щелчком - высота геоида, кора к ней не относится."""
        if not self.on():
            return None
        if height is None:
            return []
        return [(Group(tr("Геоид")), [(tr("Геоид EGM2008"), [
            (tr("Высота геоида"), tr("{value} м", value="{:+.1f}".format(
                height))),
            (tr("Над"), tr("эллипсоидом WGS84"))], None)])]

    def credits(self):
        return [geoid.ATTRIBUTION] if self.on() else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "geophysics", lambda: (tr("Геоид"), tr(
        "Форма уровенной поверхности Земли - геоида - по модели "
        "EGM2008 NGA. Пока строка включена, высоты глобуса - высоты "
        "геоида над эллипсоидом, от -107 до +86 м, растянутые "
        "в 10 000 раз, и Земля выглядит «измятой». Горбы - там, где "
        "сила тяжести больше, например у Новой Гвинеи, впадины - "
        "где меньше, самая глубокая - в Индийском океане. Рельеф "
        "и вода на это время убраны, выключение строки их "
        "возвращает.")), GeoidTool,
        source="EGM2008, NGA",
        colors=((60, 90, 170), (120, 170, 120), (200, 150, 80)),
        words=("геоид", "картошка", "потсдамская картошка", "egm2008",
               "фигура земли", "geoid"),
        after="cutaway"),
)
