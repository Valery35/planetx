# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Геологическая карта Macrostrat (core/geology.py) - тот же слой вида
«emag», что у карт значений, на глобусе одна такая карта. Строка реестра
каталога (core/rows.py) и исполнитель.
"""
from qgis.PyQt.QtCore import QObject

from ..core import basemap, geology
from ..core.geocode import link_zoom
from ..core.rows import Row
from ..core.sync import ground_size
from ..i18n import tr
from ..net.overlay import fetch_bytes

KEY = "geology"
LAYER = "emag"


class GeologyTool(QObject):
    """Карта на глобусе - строка «Слоёв», порода под щелчком."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.value = None  # (точка, подразделения или None, ошибка)
        self.reply = None

    @property
    def shown_key(self):
        window = self.window
        on = bool(getattr(window, "extras", {}).get(KEY)) \
            and getattr(window, "planet", None) is not None \
            and window.planet.earth
        return KEY if on else None

    def turn(self, key, on):
        """Тайлы Macrostrat, щелчок даёт породу. Ложь - слой вида занят
        другой картой."""
        from .globe.base import prepare_geology
        window = self.window
        if not on and window._row_map_shown() not in (None, KEY):
            self.drop()
            return False
        on = on and window.planet.earth
        self.drop()
        made = None
        if on:
            window.view.gibs[LAYER].max_level = geology.MAX_LEVEL
            source = basemap.Source("Macrostrat", geology.TILES,
                                    geology.MAX_LEVEL, geology.ATTRIBUTION,
                                    builtin=True)
            made = (source, prepare_geology)
        window._set_gibs(LAYER, on, made=made, cache=True)
        window.field_legend.setVisible(False)
        return True

    def ask(self, lat, lon):
        """Порода под щелчком: запрос map_query Macrostrat на уровне
        карты вида."""
        self.drop()
        if self.shown_key is None:
            return
        view = self.window.view
        width, _ = ground_size(view.navigator.pose.distance,
                               view.camera.fov_y, view.camera.aspect)
        self.value = ((lat, lon), None, "")
        self._send(lat, lon, link_zoom(lat, width))

    def _send(self, lat, lon, z):
        point = (lat, lon)
        self.reply = fetch_bytes(
            geology.query_url(lat, lon, z),
            lambda data, error: self._arrived(point, z, data, error))

    def drop(self):
        reply, self.reply = self.reply, None
        self.value = None
        if reply is not None:
            reply.abort()

    def _arrived(self, point, z, data, error):
        state = self.value
        if state is None or state[0] != point:
            return  # ответ снятого или прежнего запроса
        self.reply = None
        units = None
        if data is not None:
            try:
                units = geology.parse_query(bytes(data))
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        if units == [] and geology.coarser(z) is not None:
            # Глубже карты места ответ пуст - та же точка мельче.
            self._send(point[0], point[1], geology.coarser(z))
            return
        self.value = (point, units, error or "")
        self.window._refresh_identified()

    def identify(self, lat, lon):
        """Группа «Геология» окна «Объекты»."""
        from .identify import Group
        state = self.value
        if state is None:
            return []
        (lat, lon), units, error = state
        if units is None and not error:
            features = [(tr("Запрос к Macrostrat…"), [], None)]
        elif units is None:
            features = [(tr("Macrostrat не ответил"),
                         [(tr("Ошибка"), error)], None)]
        elif not units:
            features = [(tr("Карта в точке пуста"), [], None)]
        else:
            features = []
            for unit in units:
                names, ages = geology.age_text(unit)
                values = []
                if names:
                    values.append((tr("Возраст"), names))
                if ages:
                    values.append((tr("Возраст, млн лет"), ages))
                for label, key in ((tr("Литология"), "lith"),
                                   (tr("Свита"), "strat_name"),
                                   (tr("Описание"), "descrip"),
                                   (tr("Примечание"), "comments")):
                    if unit[key]:
                        values.append((label, unit[key]))
                source = ", ".join(v for v in (
                    unit["source"], unit["authors"], unit["year"]) if v)
                if source:
                    values.append((tr("Карта"), source))
                if unit["url"]:
                    values.append((tr("Ссылка на карту"), unit["url"]))
                values.append((tr("Страница Macrostrat"),
                               geology.page_url(lat, lon)))
                features.append((unit["name"] or unit["lith"]
                                 or tr("Без названия"), values, None))
        return [(Group(tr("Геология")), features)]

    def credit(self):
        return geology.ATTRIBUTION if self.shown_key else None

    def close(self):
        self.drop()


ROWS = (
    Row(KEY, "geology", lambda: (tr("Геологическая карта"), tr(
        "Геологическая карта мира Macrostrat, сведённая из карт разного "
        "масштаба. Цвет показывает возраст пород. В России и Европе "
        "самая подробная карта - 1:5 000 000, в США карты намного "
        "подробнее. Щелчок в режиме «Определить объекты» показывает "
        "подразделение, литологию, возраст в млн лет и карту-источник. "
        "На глобусе одна такая карта - геологическая или карта "
        "значений геофизики.")), GeologyTool, source="Macrostrat",
        colors=((251, 167, 148), (128, 197, 101), (191, 128, 196)),
        words=("геология", "геологическая карта", "стратиграфия",
               "возраст пород", "macrostrat", "geology", "geologic map"),
        fades=(LAYER,), view_map=LAYER, after="satellites"),
)
