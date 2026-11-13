# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""3D-здания (core/buildings.py, render/buildings.py) - из тайлов
векторной основы или архива Overture Maps (ui/overture.py), источник
выбирает окно «Источники данных». Строка реестра (core/rows.py)
и исполнитель. Адрес тайлов основы - TileJSON окна (window._ofm_source),
он приходит позже, тогда окно зовёт vector_ready.
"""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import sources as datasources
from ..core.rows import Row
from ..i18n import tr

KEY = "buildings"


class BuildingsTool(QObject):
    """Загрузчик тайлов зданий: основы, Overture или никакого."""

    shown_key = None

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.loader = None
        self.overture_url = None  # архив Overture по каталогу STAC
        self.reply = None

    @staticmethod
    def overture_on():
        """Здания - из архива Overture Maps (окно «Источники данных»)."""
        return QgsSettings().value(datasources.BUILDINGS_KEY, "") \
            == datasources.OVERTURE

    def turn(self, key, on):
        self.set(on)
        return True

    def drop(self):
        if self.loader is not None:
            self.loader.abort()
            self.loader.deleteLater()
        self.loader = None

    def set(self, on):
        """Загрузчик зданий заново. Адрес тайлов основы даёт TileJSON,
        адрес архива - каталог STAC Overture, до их прихода здания
        ждут."""
        from ..net.loader import TileLoader
        from ..net.overlay import fetch_json
        from .globe.base import buildings_decoder
        from .overture import OvertureTiles
        window = self.window
        view = window.view
        self.drop()
        overture = on and self.overture_on()
        if overture:
            if self.overture_url is not None:
                self.loader = OvertureTiles(self.overture_url,
                                            parent=window)
                self.loader.loaded.connect(
                    lambda key, found, extra: view.add_buildings(key, found))
            elif self.reply is None:
                self.reply = fetch_json(datasources.OVERTURE_STAC,
                                        self._catalog, prefer_cache=False)
        elif on and window._ofm_source is not None:
            self.loader = TileLoader(window._ofm_source, parent=window,
                                     decode=buildings_decoder)
            self.loader.loaded.connect(
                lambda key, found, extra: view.add_buildings(key, found))
        elif on and window._tilejson is None:
            window._tilejson = fetch_json(window._vector_choice(),
                                          window._tilejson_done)
        view.set_buildings(on, self.loader,
                           "overture" if overture else "vector")
        window._show_attribution()

    def _catalog(self, data, error):
        """Пришёл каталог STAC Overture: адрес архива последнего выпуска.
        Без ответа - выпуск по умолчанию."""
        from .overture import release_url
        self.reply = None
        if error:
            journal.note("overture catalog: {}".format(error))
        self.overture_url = release_url(data)
        self.vector_ready()

    def vector_ready(self):
        """Пришёл адрес тайлов: включённые здания без загрузчика
        начинают грузиться."""
        if self.window.extras.get(KEY) and self.loader is None:
            self.set(True)

    def vector_changed(self):
        """Окно «Источники данных» сменило векторную основу: загрузчик
        снимается до прихода нового TileJSON."""
        self.drop()

    def credits(self):
        if self.loader is None or not self.window.planet.earth \
                or not self.overture_on():
            return []
        return [datasources.OVERTURE_CREDIT]

    def vector_credit(self):
        """Подпись основы нужна и зданиям из неё без строк основы."""
        return self.loader is not None and not self.overture_on() \
            or None

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        if self.loader is not None:
            self.loader.abort()


ROWS = (
    Row(KEY, "map", lambda: (tr("3D-здания"), tr(
        "Объёмные здания из OpenStreetMap по векторным тайлам "
        "OpenFreeMap. Они видны, когда камера ближе 6 км к земле. "
        "Высота взята из OSM, иначе из этажности. Здание без этих "
        "сведений получает высоту 5 м.")), BuildingsTool,
        source="OpenFreeMap", colors=((200, 190, 175), (150, 140, 130)),
        words=("здания", "дома", "3d", "buildings"), before="grid"),
)
