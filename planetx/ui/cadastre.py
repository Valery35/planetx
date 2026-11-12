# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Кадастр Росреестра (core/cadastre.py): участки НСПД тайлами WMS
на слое вида «cadastre», сведения об участке под щелчком в окне
«Объекты» и его контур на глобусе. Строка реестра каталога
(core/rows.py) и исполнитель.
"""
from qgis.PyQt.QtCore import QObject

from ..core import cadastre
from ..core.features import Shape
from ..core.rows import Row
from ..i18n import tr
from ..net.overlay import fetch_bytes
from .identify import Group

KEY = "cadastre"
# Подсветка участка под щелчком, как выделение на карте НСПД. Цвета -
# выбор помощника, утверждает автор.
PARCEL_COLOR = (200, 0, 200, 255)
PARCEL_FILL = (230, 120, 230, 90)


def parcel_labels():
    """Подписи полей сведений об участке, ключи - core.cadastre.FIELDS."""
    return {
        "cad_num": tr("Кадастровый номер"),
        "readable_address": tr("Адрес"),
        "specified_area": tr("Площадь уточнённая"),
        "declared_area": tr("Площадь декларированная"),
        "land_record_category_type": tr("Категория земель"),
        "permitted_use_established_by_document":
            tr("Вид разрешённого использования"),
        "ownership_type": tr("Форма собственности"),
        "right_type": tr("Вид права"),
        "cost_value": tr("Кадастровая стоимость"),
        "cost_index": tr("Удельная кадастровая стоимость"),
        "cost_determination_date": tr("Дата определения стоимости"),
        "cost_application_date": tr("Дата применения стоимости"),
        "land_record_reg_date": tr("Дата постановки на учёт"),
        "status": tr("Статус"),
        "quarter_cad_number": tr("Кадастровый квартал")}


class CadastreTool(QObject):
    """Слой участков и один запрос сведений на щелчок."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.reply = None
        # (точка, участки или None, ошибка) последнего щелчка или None.
        self.parcels = None
        self.outlines = []

    shown_key = None

    def on(self):
        window = self.window
        return bool(getattr(window, "extras", {}).get(KEY)) \
            and window.planet.earth

    def turn(self, key, on):
        window = self.window
        window._set_gibs("cadastre", on and window.planet.earth, cache=True)
        if not on:
            self.drop()
        return True

    def ask(self, lat, lon):
        """Запрос сведений об участках под щелчком, когда показан
        кадастр. Один запрос на щелчок, прежний снимается."""
        self.drop()
        if not self.on():
            return
        point = (lat, lon)
        self.parcels = (point, None, "")
        self.reply = fetch_bytes(
            cadastre.info_url(lat, lon),
            lambda data, error: self.arrived(point, data, error),
            fresh=True, headers={"Referer": cadastre.REFERER})

    def drop(self):
        """Снять запрос, сведения и подсветку участков."""
        reply, self.reply = self.reply, None
        self.parcels = None
        if reply is not None:
            reply.abort()
        if self.outlines:
            self.outlines = []
            self.window._refresh_shapes()

    def arrived(self, point, data, error):
        if self.parcels is None or self.parcels[0] != point:
            return  # ответ снятого или прежнего запроса
        self.reply = None
        parcels = None
        if data is not None:
            try:
                parcels = cadastre.parse_info(data)
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        self.parcels = (point, parcels, error or "")
        self.outlines = [
            Shape("polygon", ring, color=PARCEL_COLOR, width=3.0,
                  fill=PARCEL_FILL)
            for parcel in parcels or () for ring in parcel["rings"]]
        self.window._refresh_shapes()
        self.window._refresh_identified()

    def shapes(self):
        return list(self.outlines)

    def identify(self, lat, lon, tolerance=0.0):
        """Группа «Кадастр Росреестра» окна «Объекты» по последнему
        щелчку."""
        if self.parcels is None:
            return []
        (lat, lon), parcels, error = self.parcels
        if parcels is None and not error:
            features = [(tr("Запрос к НСПД…"), [], None)]
        elif parcels is None:
            features = [(tr("НСПД не ответила"), [(tr("Ошибка"), error)],
                         None)]
        elif not parcels:
            features = [(tr("Участков под точкой нет"), [], None)]
        else:
            link = cadastre.map_link(lat, lon)
            labels = parcel_labels()
            features = [(tr("Земельный участок {number}",
                            number=p["number"]),
                         [(labels.get(key, key), value)
                          for key, value in p["values"]]
                         + [(tr("Карта НСПД"), link)], None)
                        for p in parcels]
        return [(Group(tr("Кадастр Росреестра")), features)]

    def credits(self):
        return [cadastre.ATTRIBUTION] \
            if "cadastre" in self.window.gibs_loaders else []

    def credit(self):
        return None

    def close(self):
        reply, self.reply = self.reply, None
        self.parcels = None
        if reply is not None:
            reply.abort()


ROWS = (
    Row(KEY, "map", lambda: (tr("Кадастр Росреестра"), tr(
        "Земельные участки из Национальной системы пространственных "
        "данных Росреестра поверх снимка, только по России. Видны "
        "вблизи, с высоты около 10 км и ниже. Служба отвечает "
        "медленно и отказывает на частые запросы, поэтому участки "
        "приходят по одному тайлу.")), CadastreTool,
        source="Rosreestr NSPD",
        colors=((230, 90, 80), (250, 225, 220)),
        words=("кадастр", "росреестр", "нспд", "участки",
               "земельные участки", "пкк", "cadastre", "parcels"),
        fades=("cadastre",)),
)
