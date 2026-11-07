# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты картинками (core/tilemaps.py) - литология GLiM, покрытие земель
ESA WorldCover, воды JRC, почвы SoilGrids. Тот же слой вида «emag», на
глобусе одна карта. Строки реестра каталога (core/rows.py) и исполнитель.
"""
from functools import partial

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtGui import QImage

from ..core import basemap, fields, tilemaps
from ..core.rows import Row
from ..i18n import tr
from ..net.overlay import fetch_bytes

LAYER = "emag"


class TileMapTool(QObject):
    """Показанная карта картинками и значение под щелчком."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.shown = None  # ключ показанной карты
        self.value = None  # (ключ, точка, значение, ошибка)
        self.reply = None

    @property
    def shown_key(self):
        return self.shown

    def turn(self, key, on):
        """Тайлы службы или planetx-terrain, цвет «нет данных» прозрачен,
        шкала. Ложь - слой вида занят другой картой."""
        from .globe.base import prepare_tilemap
        window = self.window
        tmap = tilemaps.MAPS[key]
        if not on and self.shown != key:
            return False
        on = on and window.planet.earth
        self.drop()
        made = None
        if on:
            window.view.gibs[LAYER].max_level = tmap.max_level
            if tmap.coarse:
                source = basemap.SplitSource(
                    key, window.tilemap_urls[key], window.tilemap_coarse[key],
                    tmap.split, tmap.max_level, tmap.attribution,
                    builtin=True)
            else:
                kind = basemap.WmsSource if tmap.wms else basemap.Source
                source = kind(key, window.tilemap_urls[key], tmap.max_level,
                              tmap.attribution, builtin=True)
            made = (source, partial(prepare_tilemap, key))
        self.shown = key if on else None
        window._set_gibs(LAYER, on, made=made, cache=True)
        ramp = on and tmap.stops is not None
        if ramp:
            window.field_legend.set_field(tmap)
        window.field_legend.setVisible(ramp)
        if on and tmap.classes:
            window.class_legend.set_map(tmap)
        window.class_legend.setVisible(bool(on and tmap.classes))
        return True

    def ask(self, lat, lon):
        """Значение карты под щелчком: запрос GetFeatureInfo службы или
        пиксель тайла глубшего уровня из кэша или сети."""
        self.drop()
        key = self.shown
        if key is None or not self.window.planet.earth:
            return
        tmap = tilemaps.MAPS[key]
        point = (lat, lon)
        self.value = (key, point, None, "")
        url = tilemaps.query_url(tmap, lat, lon)
        if url is not None:
            self.reply = fetch_bytes(
                url, lambda data, error: self._arrived(
                    key, point, None, data, error))
            return
        (x, y), pixel = fields.pixel_of(lat, lon, tmap.max_level)
        url = self.window.tilemap_urls[key].format(
            z=tmap.max_level, x=x, y=y)
        self.reply = fetch_bytes(
            url, lambda data, error: self._arrived(
                key, point, pixel, data, error))

    def drop(self):
        reply, self.reply = self.reply, None
        self.value = None
        if reply is not None:
            reply.abort()

    def _arrived(self, key, point, pixel, data, error):
        state = self.value
        if state is None or state[:2] != (key, point):
            return
        self.reply = None
        tmap = tilemaps.MAPS[key]
        value = None
        if data is not None and pixel is None:
            value = tilemaps.parse_query(tmap, bytes(data))
            error = ""
        elif data is not None:
            image = QImage.fromData(data)
            if image.isNull():
                error = tr("тайл не прочитан")
            else:
                color = image.pixelColor(*pixel)
                value = tilemaps.value_of(tmap, (
                    color.red(), color.green(), color.blue(),
                    color.alpha()))
                error = ""
        elif error and "404" in str(error):
            error = ""  # тайла нет - на месте пусто
        self.value = (key, point, value,
                      "" if value is not None else error or tr("нет данных"))
        self.window._refresh_identified()

    def identify(self, lat, lon, tolerance=0.0):
        """Группа карты картинками окна «Объекты»."""
        from .identify import Group
        from .legend import class_names, class_titles, field_titles
        state = self.value
        if state is None:
            return []
        key, _, value, error = state
        tmap = tilemaps.MAPS[key]
        title = (class_titles() if tmap.classes else field_titles()).get(
            key, key)
        if value is None and not error:
            values = [(tr("Значение"), tr("загрузка…"))]
        elif value is None:
            values = [(tr("Значение"), error)]
        elif tmap.classes:
            values = [(tr("Класс"), class_names().get(value, value))]
        else:
            number = "{:." + str(tmap.digits) + "f}"
            values = [(tr("Значение"), "{} {}".format(
                number.format(value), tmap.unit).strip())]
        group = {"glim": tr("Литология"), "water_occurrence": tr("Вода"),
                 "worldcover": tr("Покрытие земель"),
                 "water_transitions": tr("Вода")}.get(key, tr("Почва"))
        return [(Group(group), [(title, values, None)])]

    def credit(self):
        return tilemaps.MAPS[self.shown].attribution if self.shown else None

    def close(self):
        self.drop()


# Строки каталога (core/rows.py, ui/registry.py). after - строка, за
# которой стоит строка в каталоге.
SOIL = "SoilGrids, ISRIC"
GSW = "JRC Global Surface Water"
SOIL_COLORS = ((242, 218, 193), (180, 123, 65), (118, 70, 21))


def _row(key, group, names, after, source, colors, words):
    return Row(key, group, names, TileMapTool, source=source,
               colors=colors, words=words, fades=(LAYER,), view_map=LAYER,
               after=after)


ROWS = (
    _row("glim", "geology", lambda: (tr("Литология"), tr(
        "Литологическая карта мира GLiM - породы на поверхности "
        "16 классами: рыхлые отложения, осадочные, вулканические, "
        "плутонические и метаморфические породы, лёд. Карта сведена "
        "из 92 региональных карт, масштаб около 1:3 750 000. "
        "Щелчок в режиме «Определить объекты» показывает класс "
        "пород. На глобусе одна такая карта - литологическая, "
        "геологическая, почвенная, водная или карта значений "
        "геофизики.")), "geology", "GLiM, Hartmann & Moosdorf 2012",
        ((238, 228, 150), (110, 180, 225), (232, 80, 72), (140, 170, 100)),
        ("литология", "литологическая карта", "породы", "типы пород",
         "glim", "lithology", "rock types")),
    _row("worldcover", "life", lambda: (tr("Покрытие земель"), tr(
        "Карта покрытия земель ESA WorldCover за 2021 год по снимкам "
        "Sentinel-1 и Sentinel-2 с пикселем 10 м - лес, кустарник, "
        "луга, пашня, застройка, голые земли, снег и лёд, вода, "
        "болота, мангры, мхи и лишайники. Щелчок в режиме "
        "«Определить объекты» показывает класс.")), "currents",
        "ESA WorldCover 2021",
        ((0, 100, 0), (240, 150, 255), (250, 0, 0), (0, 100, 200)),
        ("покрытие земель", "растительность", "лес", "пашня",
         "застройка", "землепользование", "worldcover", "land cover")),
    _row("water_occurrence", "water", lambda: (tr("Повторяемость воды"), tr(
        "Как часто место было покрыто водой с 1984 по 2021 год по "
        "снимкам Landsat - доля наблюдений с водой, Global Surface "
        "Water JRC. Синие - вода всегда, красные - вода бывает "
        "редко. Пиксель 30 м. Щелчок в режиме «Определить "
        "объекты» показывает повторяемость в процентах.")), "ftw_2024",
        GSW, ((255, 120, 120), (130, 60, 200), (0, 0, 255)),
        ("повторяемость воды", "поверхностные воды", "вода landsat", "jrc",
         "surface water", "water occurrence")),
    _row("water_transitions", "water", lambda: (tr("Изменения воды"), tr(
        "Что стало с водой с 1984 по 2021 год по снимкам Landsat - "
        "постоянная и сезонная вода, новая и исчезнувшая, переходы "
        "между ними, Global Surface Water JRC. Видны новые "
        "водохранилища, обмелевшие озёра и блуждающие русла. Щелчок "
        "в режиме «Определить объекты» показывает класс.")),
        "water_occurrence", GSW,
        ((0, 0, 221), (34, 177, 76), (209, 45, 62), (153, 217, 234)),
        ("изменения воды", "исчезнувшие озёра", "новые водохранилища",
         "обмеление", "water change", "water transitions")),
    _row("soil_clay", "soil", lambda: (tr("Глина в почве"), tr(
        "Доля глинистых частиц в слое почвы 0-5 см по SoilGrids "
        "ISRIC - модель по 240 тысячам почвенных разрезов, сетка "
        "250 м. Щелчок в режиме «Определить объекты» запрашивает "
        "значение у SoilGrids.")), "water_transitions", SOIL, SOIL_COLORS,
        ("глина", "почвы", "почва", "гранулометрия", "soilgrids", "clay",
         "soil")),
    _row("soil_sand", "soil", lambda: (tr("Песок в почве"), tr(
        "Доля песчаных частиц в слое почвы 0-5 см по SoilGrids "
        "ISRIC, сетка 250 м. Щелчок в режиме «Определить объекты» "
        "запрашивает значение у SoilGrids.")), "soil_clay", SOIL,
        SOIL_COLORS, ("песок", "песчаные почвы", "sand")),
    _row("soil_soc", "soil", lambda: (tr("Органический углерод почвы"), tr(
        "Содержание органического углерода в слое почвы 0-5 см по "
        "SoilGrids ISRIC, г/кг, сетка 250 м. Больше всего его "
        "в торфяниках тундры и тайги. Щелчок в режиме «Определить "
        "объекты» запрашивает значение у SoilGrids.")), "soil_sand", SOIL,
        ((251, 249, 249), (187, 163, 156), (118, 70, 57)),
        ("органический углерод", "гумус", "углерод почвы", "soil carbon",
         "soc")),
    _row("soil_ph", "soil", lambda: (tr("Кислотность почвы"), tr(
        "Кислотность почвы pH в водной вытяжке, слой 0-5 см, по "
        "SoilGrids ISRIC, сетка 250 м. Жёлтые - кислые почвы, "
        "зелёные - нейтральные, бирюзовые - щелочные. Щелчок "
        "в режиме «Определить объекты» запрашивает значение "
        "у SoilGrids.")), "soil_soc", SOIL,
        ((241, 238, 45), (66, 181, 50), (15, 204, 217)),
        ("кислотность", "ph", "кислые почвы", "soil ph", "acidity")),
)
