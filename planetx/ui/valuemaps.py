# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Карты значений геофизики (core/fields.py) - магнитные аномалии, возраст
дна, тепловой поток, сила тяжести, аномалия Буге. Тайлы planetx-terrain,
раскраска в рабочем потоке, слой вида «emag», на глобусе одна карта.
Строки реестра каталога (core/rows.py) и исполнитель.
"""
from functools import partial

from qgis.PyQt.QtCore import QObject
from qgis.PyQt.QtGui import QImage

from ..core import basemap, fields
from ..core.rows import Row
from ..i18n import tr
from ..net.overlay import fetch_bytes

LAYER = "emag"


def field_texts():
    """Карта значений: ключ - (группа окна «Объекты», строка, единица,
    строки пояснений)."""
    return {
        "emag": (tr("Магнитная аномалия"), tr("Аномалия поля"), tr("нТл"),
                 [(tr("Высота сетки"), tr("4 км над эллипсоидом")),
                  (tr("Набор"), "EMAG2v3, NOAA NCEI")]),
        "seafloor_age": (tr("Океаническое дно"), tr("Возраст коры"),
                         tr("млн лет"),
                         [(tr("Набор"), "Seton et al. 2020, EarthByte")]),
        "gravity": (tr("Сила тяжести"), tr("Аномалия в свободном воздухе"),
                    tr("мГал"),
                    [(tr("Набор"), "XGM2019e, Zingerle et al. 2020")]),
        "bouguer": (tr("Сила тяжести"), tr("Аномалия Буге"), tr("мГал"),
                    [(tr("Набор"), "XGM2019e, ETOPO 2022"),
                     (tr("Плотность породы"), "2670 кг/м³")]),
        "heatflow": (tr("Тепловой поток"), tr("Поток тепла"),
                     tr("мВт/м²"),
                     [(tr("Набор"), "IHFC 2024, Petrunin et al. 2026")]),
    }


class FieldMapTool(QObject):
    """Показанная карта значений и значение под щелчком."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.shown = None
        self.value = None  # (ключ, точка, значение или None, ошибка)
        self.reply = None

    @property
    def shown_key(self):
        return self.shown

    def turn(self, key, on):
        from .globe.base import prepare_field
        window = self.window
        field = fields.FIELDS[key]
        if not on and self.shown != key:
            return False
        on = on and window.planet.earth
        self.drop()
        made = None
        if on:
            window.view.gibs[LAYER].max_level = field.max_level
            source = basemap.Source(key, window.field_urls[key],
                                    field.max_level, field.attribution,
                                    builtin=True)
            made = (source, partial(prepare_field, key))
        self.shown = key if on else None
        window._set_gibs(LAYER, on, made=made, cache=True)
        window.field_legend.set_field(field)
        window.field_legend.setVisible(on)
        return True

    def ask(self, lat, lon):
        """Значение карты под щелчком: тайл глубшего уровня из кэша или
        сети, пиксель точки."""
        self.drop()
        key = self.shown
        if key is None or not self.window.planet.earth:
            return
        field = fields.FIELDS[key]
        (x, y), (column, row) = fields.pixel_of(lat, lon, field.max_level)
        url = self.window.field_urls[key].format(
            z=field.max_level, x=x, y=y)
        point = (lat, lon)
        self.value = (key, point, None, "")
        self.reply = fetch_bytes(
            url, lambda data, error: self._arrived(
                key, point, column, row, data, error))

    def drop(self):
        reply, self.reply = self.reply, None
        self.value = None
        if reply is not None:
            reply.abort()

    def _arrived(self, key, point, column, row, data, error):
        state = self.value
        if state is None or state[:2] != (key, point):
            return
        self.reply = None
        value = None
        if data is not None:
            image = QImage.fromData(data)
            if not image.isNull():
                color = image.pixelColor(column, row)
                value = fields.value_at(fields.FIELDS[key], [[(
                    color.red(), color.green(), color.blue())]], 0, 0)
            error = "" if not image.isNull() else tr("тайл не прочитан")
        self.value = (key, point, value, "" if value is not None
                      else error or tr("нет данных"))
        self.window._refresh_identified()

    def identify(self, lat, lon, tolerance=0.0):
        """Группа карты значений окна «Объекты»."""
        from .identify import Group
        state = self.value
        if state is None:
            return []
        key, _, value, error = state
        group, title, unit, notes = field_texts()[key]
        if value is None and not error:
            values = [(tr("Значение"), tr("загрузка…"))]
        elif value is None:
            values = [(tr("Значение"), error)]
        else:
            digits = fields.FIELDS[key].digits
            sign = "+" if fields.FIELDS[key].stops[0][0] < 0 else ""
            number = "{:" + sign + "." + str(digits) + "f}"
            values = [(tr("Значение"), "{} {}".format(
                number.format(value), unit))] + notes
        return [(Group(group), [(title, values, None)])]

    def credit(self):
        return fields.FIELDS[self.shown].attribution if self.shown else None

    def close(self):
        self.drop()


def _row(key, names, after, source, colors, words):
    return Row(key, "geophysics", names, FieldMapTool, source=source,
               colors=colors, words=words, fades=(LAYER,), view_map=LAYER,
               after=after)


ROWS = (
    _row("emag", lambda: (tr("Магнитные аномалии"), tr(
        "Аномалии магнитного поля Земли по сетке EMAG2v3 NOAA NCEI - "
        "отклонение поля от нормального на высоте 4 км над "
        "эллипсоидом, шаг около 4 км. Красные - поле сильнее, "
        "синие - слабее. Аномалии выдают строение коры - хребты "
        "и полосы океанского дна, древние щиты, рудные районы. "
        "Пустые места - там съёмки нет. Щелчок в режиме «Определить "
        "объекты» показывает значение в нТл.")), "magdecl",
        "EMAG2v3, NOAA NCEI",
        ((40, 60, 150), (245, 245, 235), (160, 30, 35)),
        ("магнитные аномалии", "магнитка", "аэромагнитка",
         "магниторазведка", "emag", "magnetic anomaly")),
    _row("gravity", lambda: (tr("Аномалии силы тяжести"), tr(
        "Аномалия силы тяжести в свободном воздухе по модели XGM2019e "
        "до степени 719, шаг около 28 км. Красные - сила тяжести "
        "больше нормальной, синие - меньше. Над глубоководными "
        "желобами провалы до -300 мГал, над вулканическими островами "
        "и горами - подъём. Щелчок в режиме «Определить объекты» "
        "показывает аномалию в мГал.")), "emag", "XGM2019e, ICGEM",
        ((30, 40, 130), (245, 245, 240), (150, 30, 30)),
        ("сила тяжести", "гравитация", "гравиметрия",
         "аномалии силы тяжести", "xgm2019e", "gravity", "free-air")),
    _row("bouguer", lambda: (tr("Аномалии Буге"), tr(
        "Аномалия силы тяжести за вычетом притяжения рельефа - "
        "поправка Буге по рельефу ETOPO 2022 с плотностью породы "
        "2670 кг/м³, вода и лёд своей плотностью, и поправка на "
        "рельеф вокруг в круге 167 км. Аномалия показывает плотность "
        "недр без влияния гор и глубин океана. Под горами она "
        "отрицательная, это толстая лёгкая кора, над океаном "
        "положительная. Щелчок в режиме «Определить объекты» "
        "показывает аномалию в мГал.")), "gravity", "XGM2019e, ETOPO 2022",
        ((60, 120, 210), (245, 245, 240), (230, 120, 60)),
        ("буге", "аномалия буге", "аномалии буге", "bouguer")),
    _row("seafloor_age", lambda: (tr("Возраст океанического дна"), tr(
        "Возраст океанической коры по сетке Seton и соавторов 2020 "
        "года, шаг 0.1°. Молодое дно у срединных хребтов красное, "
        "древнее у окраин океанов - синее и фиолетовое. Суша и "
        "континентальная кора не закрашены. На глобусе одна карта "
        "значений - возраст дна, магнитные аномалии, сила тяжести "
        "или тепловой поток. Щелчок в режиме «Определить объекты» "
        "показывает возраст в млн лет.")), "geoid", "Seton et al. 2020",
        ((230, 40, 40), (245, 230, 70), (60, 90, 200)),
        ("возраст дна", "возраст океанического дна", "возраст коры",
         "спрединг", "seafloor age", "ocean age")),
    _row("heatflow", lambda: (tr("Тепловой поток"), tr(
        "Поток тепла из недр через поверхность Земли по сетке 0.5°, "
        "построенной по 91 тысяче измерений базы IHFC 2024. Синие - "
        "холодные древние щиты, красные - рифты, хребты и вулканические "
        "области. Вдали от измерений сетка сглажена. Щелчок в режиме "
        "«Определить объекты» показывает поток в мВт/м².")),
        "seafloor_age", "IHFC 2024",
        ((40, 50, 140), (245, 235, 160), (220, 70, 40)),
        ("тепловой поток", "геотермия", "теплопоток", "heat flow",
         "geothermal")),
)
