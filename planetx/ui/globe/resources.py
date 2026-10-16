# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Недра и энергетика: горные разработки, ЛЭП, электростанции, плиты, кабели,
место под щелчком, координаты под курсором.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import os
import zipfile
import time

import numpy as np
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QTimer

from ... import journal
from ...core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ...core.measure import surface_level
from ...core.flight import Flight
from ...core.navigation import ground_under
from ...core.skyview import ra_dec_text
from ...core import (infra, mining, cables as cables_core,
                     plants as plants_core, platemotion, plates, slabs,
                     volcanoes as volcanoes_core)
from ...core.features import Shape
from ..overpass import brief_error
from ...core.places import Place as MarkPlace
from ...i18n import tr
from ...net.gdalnet import executor
from ...net.overlay import fetch_bytes, plate_layer, cable_layer
from ...render.view import OBJECT_BUDGET, start_keys
from ..identify import Group, point_text
from ..deposits import parse_plants
from ..legend import fuel_names
from .base import (CURSOR_PERIOD, DATA_DIR, DEPOSIT_POLL, IDENTIFY_PIXELS,
                   MESSAGE_TIME, MOTION_COLOR, MOTION_WIDTH, distance_text)


class ResourcesMixin:
    """Часть окна глобуса GlobeWindow."""

    # Горные разработки и шахты OSM.

    def _deposit_legend_on(self):
        """Шкала месторождений нужна месторождениям USGS и шахтам OSM."""
        return bool(self.planet.earth and self.view.sky_view is None
                    and (self.extras.get("deposits")
                         or self.extras.get("osm_mines")))

    def _close_deposit_legend(self):
        """Крестик шкалы убирает месторождения и шахты OSM."""
        self.set_extra("deposits", False)
        self.set_extra("osm_mines", False)

    def _mining_path(self):
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, mining.POLYGONS_FILE)

    def _set_mining(self, on):
        """Контуры горных разработок строкой витрины. Первое включение
        скачивает GeoPackage в профиль, дальше файл читается без сети."""
        self._mark_gallery()
        if not on:
            if self._mining_reply is not None:
                self._mining_reply.abort()
                self._mining_reply = None
            self._update_overlay(keep=True)
            self._show_attribution()
            return
        if self.mining_layer is None:
            path = self._mining_path()
            if os.path.exists(path):
                self._open_mining(path)
            elif self._mining_reply is None:
                self._mining_reply = fetch_bytes(
                    mining.POLYGONS_URL, self._mining_arrived)
                self.view.data_pending += 1
                self.message = (tr("Загрузка контуров горных разработок, "
                                   "около 25 МБ…"), time.monotonic())
                self._show_state()
                return
        self._update_overlay(keep=True)
        self._show_attribution()

    def _mining_arrived(self, data, error):
        if self._mining_reply is not None:
            self.view.data_pending = max(0, self.view.data_pending - 1)
        self._mining_reply = None
        if data is None:
            journal.note("mining polygons: {}".format(brief_error(error)))
            self.message = (tr("Контуры горных разработок не загрузились, "
                               "проверьте сеть и включите строку снова."),
                            time.monotonic())
            self._show_state()
            return
        path = self._mining_path()
        try:
            with open(path + ".part", "wb") as stream:
                stream.write(data)
            os.replace(path + ".part", path)
        except OSError as error:
            self.message = (tr("Контуры горных разработок не записаны: "
                               "{error}", error=str(error)), time.monotonic())
            self._show_state()
            return
        self._open_mining(path)
        if self.extras.get("mining"):
            self._update_overlay(keep=True)
            self._show_attribution()

    def _open_mining(self, path):
        """Слой QGIS контуров из файла профиля со своим стилем."""
        from qgis.core import QgsFillSymbol, QgsVectorLayer
        from ..nasamaps import MINING_FILL, MINING_LINE
        layer = QgsVectorLayer(path, "Mining areas", "ogr")
        if not layer.isValid():
            self.message = (tr("Файл контуров горных разработок не "
                               "читается: {path}", path=path),
                            time.monotonic())
            self._show_state()
            return
        symbol = QgsFillSymbol.createSimple({
            "color": "{},{},{},{}".format(*MINING_FILL),
            "outline_color": "{},{},{},{}".format(*MINING_LINE),
            "outline_width": "0.35"})
        layer.renderer().setSymbol(symbol)
        self.mining_layer = layer

    def _set_osm_mines(self, on):
        """Шахты и карьеры OSM строкой витрины: тайлы вокруг вида."""
        self._mark_gallery()
        self.deposit_legend.setVisible(self._deposit_legend_on())
        if not on:
            self.osm_mines_tiles.stop()
        self._place_osm_mines()
        if on:
            self._want_overpass()

    def _overpass_view_changed(self):
        if self.planet.earth and (self.extras.get("osm_mines")
                                  or self.extras.get("infra_osm")):
            self._osm_timer.start()

    def _want_overpass(self):
        """Недостающие тайлы у точки взгляда - загрузчикам Overpass
        включённых строк."""
        if not self.planet.earth:
            return
        pose = self.view.navigator.pose
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        altitude = float(ecef_to_geodetic(eye)[2])
        if self.extras.get("osm_mines"):
            self.osm_mines_tiles.want(pose.lat, pose.lon, altitude)
        if self.extras.get("infra_osm"):
            self.infra_tiles.want(pose.lat, pose.lon, altitude)

    def _overpass_failed(self):
        """Отказ сервера Overpass: пользователю - короткая фраза,
        подробности уже в журнале работы."""
        self.message = (tr("Сервер OpenStreetMap не ответил, запрос "
                           "повторится сам."), time.monotonic())
        self._show_state()

    def _place_osm_mines(self):
        on = self.extras.get("osm_mines", False) and self.planet.earth
        items = self.osm_mines_tiles.all_items()
        self.view.osm_mines.set_deposits(
            mining.to_deposits(items) if on and items else None,
            self.view.store.scale, self._surface_ground)
        self._show_attribution()
        self.view.update()

    # ЛЭП и трубопроводы OSM.

    def _set_infra(self, on):
        """ЛЭП, подстанции и трубопроводы OSM строкой витрины."""
        self._mark_gallery()
        self.infra_legend.setVisible(on and self.planet.earth)
        if not on:
            self.infra_tiles.stop()
            self._update_overlay(keep=True)
            self._show_attribution()
            return
        self._place_infra()
        self._want_overpass()

    def _place_infra(self):
        """Слои QGIS в памяти по всем пришедшим объектам: линии - ЛЭП
        и трубопроводы, точки - подстанции. Стиль - по классу."""
        from ..infra import infra_layers
        items = infra.unique(self.infra_tiles.all_items())
        self.infra_lines, self.infra_points = infra_layers(items)
        if self.extras.get("infra_osm") and self.planet.earth:
            self._update_overlay(keep=True)
        self._show_attribution()

    def _identify_infra(self, lat, lon, tolerance):
        """Линия или подстанция OSM у точки щелчка."""
        if not (self.extras.get("infra_osm") and self.planet.earth
                and self.infra_lines is not None):
            return []
        from ..infra import nearest_infra
        found = nearest_infra(self.infra_lines, self.infra_points, lat, lon,
                              tolerance)
        if found is None:
            return []
        title, values = found
        return [(Group(tr("ЛЭП, кабели и трубопроводы OSM")),
                 [(title or tr("Без названия"), values, None)])]

    # Вулканы GVP (core/volcanoes.py).

    def _volcanoes_path(self):
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "volcanoes.npz")

    def _set_volcanoes(self, on):
        """Вулканы голоцена строкой каталога. Первое включение скачивает
        список GVP около 2 МБ, итог - файл профиля."""
        self._mark_gallery()
        self.volcano_legend.setVisible(on and self.planet.earth)
        if not on:
            if self._volcano_reply is not None:
                reply, self._volcano_reply = self._volcano_reply, None
                reply.abort()
            self._place_volcanoes()
            return
        if self.volcano_data is None:
            path = self._volcanoes_path()
            if os.path.exists(path):
                try:
                    self.volcano_data = volcanoes_core.load(path)
                except (OSError, ValueError, KeyError) as error:
                    journal.note("volcanoes file: {}".format(error))
        if self.volcano_data is not None:
            self._place_volcanoes()
            return
        if self._volcano_reply is not None:
            return
        self._volcano_reply = fetch_bytes(volcanoes_core.URL,
                                          self._volcanoes_arrived)
        self.view.data_pending += 1
        self.message = (tr("Загрузка списка вулканов GVP, около 2 МБ…"),
                        time.monotonic())
        self._show_state()

    def _volcanoes_arrived(self, data, error):
        self.view.data_pending = max(0, self.view.data_pending - 1)
        if self._volcano_reply is None:
            return  # снят выключением строки
        self._volcano_reply = None
        found = None
        if data is not None:
            try:
                # Около 1200 строк - разбор в главном потоке, десятки мс.
                found = volcanoes_core.parse(bytes(data))
                volcanoes_core.save(found, self._volcanoes_path())
            except (OSError, ValueError, KeyError) as problem:
                error = str(problem)
                found = None
        if found is None:
            journal.note("volcanoes: {}".format(brief_error(error or "")))
            self.message = (tr("Список вулканов не загрузился, проверьте "
                               "сеть и включите строку снова."),
                            time.monotonic())
            self._show_state()
            return
        self.volcano_data = found
        self.message = (tr("Вулканов {count}.", count=len(found)),
                        time.monotonic())
        self._show_state()
        self._place_volcanoes()

    def _place_volcanoes(self):
        on = self.extras.get("volcanoes", False) and self.planet.earth
        self.view.volcanoes.set_volcanoes(
            self.volcano_data if on else None, self.view.store.scale,
            self._surface_ground)
        self._show_attribution()
        self.view.update()

    def _identify_volcanoes(self, px, py):
        """Вулканы у точки щелчка на экране, не больше 10."""
        layer = self.view.volcanoes
        data = layer.data
        if data is None:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        seen = layer.visible(eye)
        if not len(seen):
            return []
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        pixels, front = self.view.camera.project(layer.focus[seen])
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        near = np.nonzero(front & (gap <= radius))[0]
        near = near[np.argsort(gap[near])][:10]
        features = []
        for n in near:
            record = int(layer.order[seen[n]])
            number, name, kind, country, setting, evidence = \
                (data.text(record) + [""] * 6)[:6]
            values = []
            if kind:
                values.append((tr("Тип"), kind))
            year = float(data.last[record])
            if np.isfinite(year):
                year = int(year)
                values.append((tr("Последнее извержение"), str(year)
                               if year > 0 else tr("{year} до н. э.",
                                                   year=-year)))
            else:
                values.append((tr("Последнее извержение"),
                               tr("дата неизвестна")))
            height = float(data.elevation[record])
            if np.isfinite(height):
                values.append((tr("Высота"), tr("{value} м",
                                                value="{:.0f}".format(
                                                    height))))
            if country:
                values.append((tr("Страна"), country))
            if setting:
                values.append((tr("Обстановка"), setting))
            if evidence:
                values.append((tr("Достоверность"), evidence))
            values.append((tr("Набор"), "Global Volcanism Program"))
            if number:
                values.append((tr("Источник"),
                               volcanoes_core.PAGE.format(number)))
            features.append((name, values, None))
        return [(Group(tr("Вулканы")), features)] if features else []

    # Электростанции WRI.

    def _plants_path(self):
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "power_plants.npz")

    def _set_plants(self, on):
        """Электростанции WRI строкой витрины. Первое включение скачивает
        архив около 4 МБ, разбор - в рабочем потоке, итог - файл
        профиля."""
        self._mark_gallery()
        self.plant_legend.setVisible(on and self.planet.earth)
        if not on:
            if self._plant_reply is not None:
                reply, self._plant_reply = self._plant_reply, None
                reply.abort()
            self._place_plants()
            return
        if self.plant_data is None:
            path = self._plants_path()
            if os.path.exists(path):
                try:
                    self.plant_data = plants_core.load(path)
                except (OSError, ValueError, KeyError) as error:
                    journal.note("plants file: {}".format(error))
        if self.plant_data is not None:
            self._place_plants()
            return
        if self._plant_reply is not None or self._plant_job is not None:
            return
        self._plant_reply = fetch_bytes(plants_core.URL, self._plants_arrived)
        self.view.data_pending += 1
        self.message = (tr("Загрузка электростанций WRI, около 4 МБ…"),
                        time.monotonic())
        self._show_state()

    def _plants_arrived(self, data, error):
        self.view.data_pending = max(0, self.view.data_pending - 1)
        if self._plant_reply is None:
            return  # снят выключением строки
        self._plant_reply = None
        if data is None:
            journal.note("plants: {}".format(brief_error(error)))
            self.message = (tr("Электростанции не загрузились, проверьте "
                               "сеть и включите строку снова."),
                            time.monotonic())
            self._show_state()
            return
        self._plant_job = executor("deposits", 1).submit(
            parse_plants, bytes(data), self._plants_path())
        self.view.data_pending += 1
        QTimer.singleShot(DEPOSIT_POLL, self._plants_poll)

    def _plants_poll(self):
        job = self._plant_job
        if job is None:
            return
        if not job.done():
            QTimer.singleShot(DEPOSIT_POLL, self._plants_poll)
            return
        self._plant_job = None
        self.view.data_pending = max(0, self.view.data_pending - 1)
        try:
            self.plant_data = job.result()
        except (OSError, ValueError, KeyError, StopIteration,
                zipfile.BadZipFile) as error:
            journal.note("plants parse: {}".format(error))
            self.message = (tr("Электростанции не разобраны."),
                            time.monotonic())
            self._show_state()
            return
        self.message = (tr("Электростанций {count}.",
                           count=len(self.plant_data)), time.monotonic())
        self._show_state()
        self._place_plants()

    def _place_plants(self):
        on = self.extras.get("plants", False) and self.planet.earth
        self.view.plants.set_plants(self.plant_data if on else None,
                                    self.view.store.scale,
                                    self._surface_ground)
        self._show_attribution()
        self.view.update()

    def _identify_plants(self, px, py):
        """Электростанции у точки щелчка на экране, не больше 10."""
        layer = self.view.plants
        data = layer.data
        if data is None:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        seen = layer.visible(eye)
        if not len(seen):
            return []
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        pixels, front = self.view.camera.project(layer.focus[seen])
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        near = np.nonzero(front & (gap <= radius))[0]
        near = near[np.argsort(gap[near])][:10]
        fuels = fuel_names()
        keys = [f[0] for f in plants_core.FUELS]
        features = []
        for n in near:
            record = int(layer.order[seen[n]])
            name, country, fuel, year, owner, url = \
                (data.text(record) + [""] * 6)[:6]
            values = [(tr("Мощность"), tr("{value} МВт", value="{:g}".format(
                round(float(data.capacity[record]), 1)))),
                      (tr("Топливо"), "{} ({})".format(
                          fuels[keys[int(data.fuel[record])]], fuel))]
            if year:
                values.append((tr("Год ввода"), year))
            if owner:
                values.append((tr("Владелец"), owner))
            if country:
                values.append((tr("Страна"), country))
            values.append((tr("Набор"), "WRI Global Power Plant Database"))
            if url:
                values.append((tr("Источник"), url))
            features.append((name, values, None))
        return [(Group(tr("Электростанции")), features)] if features else []

    def _plate_names(self):
        """Подписи групп и классов границ плит на языке интерфейса."""
        return ({"divergent": tr("Раздвиг плит"),
                 "transform": tr("Сдвиг плит"),
                 "convergent": tr("Схождение плит")},
                {"OSR": tr("Океанический спрединговый хребет"),
                 "CRB": tr("Континентальный рифт"),
                 "OTF": tr("Океанический трансформный разлом"),
                 "CTF": tr("Континентальный трансформный разлом"),
                 "SUB": tr("Зона субдукции"),
                 "OCB": tr("Океаническая граница схождения"),
                 "CCB": tr("Континентальная коллизия")})

    def _set_plates(self, on):
        """Строка «Границы плит»: линии границ в наложении, названия
        плит надписями глобуса. Файл data/plates.json читается при
        первом включении."""
        if on and self.plates_data is None:
            try:
                with open(os.path.join(DATA_DIR, "plates.json"),
                          encoding="utf-8") as fh:
                    self.plates_data = plates.Plates.from_text(fh.read())
            except (OSError, ValueError) as error:
                self.message = (tr("Границы плит не прочитаны: {error}",
                                   error=str(error)), time.monotonic())
                self._show_state()
                return
        if on and self.plate_layer is None:
            self.plate_layer = plate_layer(self.plates_data,
                                           self._plate_names()[0])
        self.view.plate_marks = [
            MarkPlace(-300000 - n, p.name, "plate", 1, p.lat, p.lon)
            for n, p in enumerate(self.plates_data.plates)] \
            if on and self.plates_data is not None else []
        self._update_overlay(keep=True)
        self._show_attribution()
        self.view.update()

    # Скорости плит NNR-MORVEL56 (core/platemotion.py).

    def _motion_on(self):
        # Зовётся и при создании окна, до чтения строк «Слоёв».
        return bool(getattr(self, "extras", {}).get("platemotion")) \
            and self.planet.earth and self.view.sky_view is None

    def _set_platemotion(self, on):
        """Строка «Скорости плит»: стрелки у вида и подписи мм/год.
        Файл data/plate_motion.json читается при первом включении."""
        if on and self.plate_motion is None:
            try:
                with open(os.path.join(DATA_DIR, "plate_motion.json"),
                          encoding="utf-8") as fh:
                    self.plate_motion = platemotion.read(fh.read())
            except (OSError, ValueError, KeyError) as error:
                self.message = (tr("Скорости плит не прочитаны: {error}",
                                   error=str(error)), time.monotonic())
                self._show_state()
                return
        self._motion_key = None
        self._update_plate_arrows()
        self._show_attribution()
        self._mark_gallery()

    def _update_plate_arrows(self):
        """Стрелки строятся заново, когда меняется шаг узлов или вид
        уходит на шаг, как сетка координат."""
        if not self._motion_on() or self.plate_motion is None:
            if self.motion_shapes or self._motion_marks:
                self.motion_shapes = []
                self._motion_marks = []
                self._motion_key = None
                self._set_geo_marks()
                self._refresh_shapes()
            return
        pose = self.view.navigator.pose
        width = self._view_width()
        step = platemotion.step_for(width)
        key = (step, round(pose.lat / step), round(pose.lon / step))
        if key == self._motion_key:
            return
        self._motion_key = key
        shapes = []
        marks = []
        for n, (lat, lon, speed, _, lines) in enumerate(
                platemotion.arrows(self.plate_motion, pose.lat, pose.lon,
                                   width)):
            for line in lines:
                shapes.append(Shape("line", line, color=MOTION_COLOR,
                                    width=MOTION_WIDTH))
            marks.append(MarkPlace(-700000 - n, "{:.0f}".format(speed),
                                   "grid", 1, lat, lon))
        self.motion_shapes = shapes
        self._motion_marks = marks
        self._set_geo_marks()
        self._refresh_shapes()

    def _motion_rows(self, lat, lon):
        """Строки скорости плиты для окна «Объекты» или []."""
        if not self._motion_on() or self.plate_motion is None:
            return []
        found = self.plate_motion.velocity(lat, lon)
        if found is None:
            return []
        code, east, north = found
        speed, azimuth = platemotion.speed_azimuth(east, north)
        return [(tr("Плита"), "{} ({})".format(
                    self.plate_motion.names[code], code)),
                (tr("Скорость плиты"), tr("{value} мм/год",
                                          value="{:.1f}".format(speed))),
                (tr("Направление"), "{:.0f}°".format(azimuth))]

    def _set_currents(self, on):
        """Строка «Течения» витрины: струйки течений и шкала."""
        self._mark_gallery()
        self.flow.moment = self.theme_moment()
        self.flow.set_currents(on and self.planet.earth)
        self.current_legend.setVisible(on and self.planet.earth)
        self._update_timebar()
        self._show_attribution()

    def _flow_changed(self):
        if self.flow.error:
            self.message = (self.flow.error, time.monotonic())
        elif self.flow.currents_day:
            self.message = (tr("Течения на {day}.",
                               day=self.flow.currents_day),
                            time.monotonic())
        self._show_state()
        self._show_attribution()

    def _cable_names(self):
        return {"telecom": tr("Линия связи"),
                "power": tr("Силовой кабель")}

    def _set_cables(self, on):
        """Строка «Подводные кабели» группы «Карта»: линии в наложении.
        Файл data/cables.json читается при первом включении."""
        if on and self.cables_data is None:
            try:
                with open(os.path.join(DATA_DIR, "cables.json"),
                          encoding="utf-8") as fh:
                    self.cables_data = cables_core.Cables.from_text(
                        fh.read())
            except (OSError, ValueError) as error:
                journal.note("cables: {}".format(error))
                self.message = (tr("Подводные кабели не прочитаны."),
                                time.monotonic())
                self._show_state()
                return
        if on and self.cable_layer is None:
            self.cable_layer = cable_layer(self.cables_data,
                                           self._cable_names())
        self._update_overlay(keep=True)
        self._show_attribution()
        self.view.update()

    def _identify_cables(self, lat, lon, tolerance):
        """Подводный кабель у точки щелчка, когда строка включена."""
        if not (self.planet.earth and self.extras.get("cables")
                and self.cables_data is not None):
            return []
        found = cables_core.nearest(self.cables_data, lat, lon, tolerance)
        if found is None:
            return []
        values = [(tr("Вид"), self._cable_names()[found.kind])]
        if found.operator:
            values.append((tr("Владелец"), found.operator))
        kv = infra.kilovolts(found.voltage)
        if kv is not None:
            values.append((tr("Напряжение"), tr(
                "{value} кВ", value="{:g}".format(kv))))
        values.append((tr("Объект OSM"), "https://www.openstreetmap.org/"
                       + found.osm))
        return [(Group(tr("Подводные кабели")), [
            (found.name or tr("Без названия"), values, None)])]

    def _identify_plates(self, lat, lon, tolerance):
        """Граница плит у точки щелчка, когда строка включена."""
        if not (self.planet.earth and self.extras.get("plates")
                and self.plates_data is not None):
            return []
        found = plates.nearest(self.plates_data, lat, lon, tolerance)
        if found is None:
            return []
        groups, classes = self._plate_names()
        values = [(tr("Тип"), classes.get(found.code, found.code)),
                  (tr("Плиты"), found.pair),
                  (tr("Скорость"), tr("{value} мм/год",
                                      value="{:.0f}".format(found.speed)))]
        return [(Group(tr("Граница плит")), [
            (groups[plates.group(found.code)], values, None)])]

    def _identify_site(self, lat, lon, height):
        """Место под щелчком: высота или глубина, кора CRUST1.0, плита
        Slab2. Кора и зона плиты просятся, если их нет, окно обновится
        по их приходу."""
        if not self.planet.earth:
            return []
        if self._geoid_on():
            # В режиме геоида высота под щелчком - высота геоида, не
            # рельеф и не дно, кора к ней не относится.
            if height is None:
                return []
            return [(Group(tr("Геоид")), [(tr("Геоид EGM2008"), [
                (tr("Высота геоида"), tr("{value} м", value="{:+.1f}"
                                         .format(height))),
                (tr("Над"), tr("эллипсоидом WGS84"))], None)])]
        values = []
        address = self._address_value(lat, lon)
        if address is not None:
            values.append((tr("Адрес"), address))
        if height is not None:
            kind, value = surface_level(height)
            values.append((tr("Глубина") if kind == "depth"
                           else tr("Высота"), tr("{value} м",
                                                 value=str(value))))
        self._want_crust()
        if self.crust is not None:
            bounds = self.crust.at([lat], [lon])[0].astype(float)
            sediments = float(bounds[2] - bounds[5])
            values.append((tr("Мохо"), tr("{value} км", value="{:.1f}".format(
                -bounds[-1]))))
            values.append((tr("Толщина коры"), tr("{value} км", value=(
                "{:.1f}".format(bounds[1] - bounds[-1])))))
            oceanic = self.crust.oceanic([lat], [lon])
            if oceanic is not None:
                values.append((tr("Тип коры"), tr("океаническая")
                               if oceanic[0] else tr("континентальная")))
            if sediments > 0.0:
                # Не «Осадки»: эта строка перевода - осадки погоды,
                # английский каталог показывал их как Sediments.
                values.append((tr("Осадочный чехол"), tr("{value} км", value=(
                    "{:.1f}".format(sediments)))))
        elif self._crust_reply is not None:
            values.append((tr("Кора"), tr("загружается")))
        codes = slabs.touched(self._read_slab_index(), [lat], [lon])
        self._request_slabs(codes)
        zones = [self.slab_zones[c] for c in codes if c in self.slab_zones]
        top, bottom = slabs.band(zones, [lat], [lon])
        if np.isfinite(top[0]):
            values.append((tr("Плита Slab2"), tr(
                "{top}-{bottom} км", top="{:.0f}".format(top[0]),
                bottom="{:.0f}".format(bottom[0]))))
        elif any(c in self._slab_replies for c in codes):
            values.append((tr("Плита Slab2"), tr("загружается")))
        values += self._motion_rows(lat, lon)
        return [(Group(tr("Место")), [(tr("Под точкой"), values, None)])] \
            if values else []

    def _ground(self, px, py):
        """Широта и долгота точки рельефа под пикселем или None."""
        view = self.view
        point = ground_under(view.camera, px, py,
                             view.navigator.pose.terrain)
        if point is None:
            return None
        lat, lon, _ = (float(v) for v in ecef_to_geodetic(point))
        return lat, lon

    def _surface(self, px, py):
        """Точка 3D-линейки под пикселем: широта, долгота и настоящая
        высота над эллипсоидом, на крыше или стене здания, если луч
        встречает его раньше рельефа. None - мимо Земли.

        Рельеф на экране поднят в store.scale раз. Высота точки над
        рельефом при этом настоящая, здания не растягиваются, поэтому
        настоящая высота - нарисованная минус подъём рельефа."""
        view = self.view
        point = view.surface_hit(px, py)
        if point is None:
            return None
        lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
        scale = view.store.scale
        if scale and scale != 1.0:
            drawn = float(view.store.heights_at(np.array([lat]),
                                                np.array([lon]))[0])
            h -= drawn - drawn / scale
        return lat, lon, h

    def drawn_points(self, ruler, rubber=False):
        """Точки 3D-линейки в ECEF так, как они нарисованы: при подъёме
        рельефа высота рельефа под точкой поднята в store.scale раз."""
        xyz = ruler.space_points(rubber)
        scale = self.view.store.scale
        if not len(xyz) or not scale or scale == 1.0:
            return xyz
        lat, lon, h = ecef_to_geodetic(xyz)
        drawn = np.asarray(self.view.store.heights_at(lat, lon))
        return geodetic_to_ecef(lat, lon, h + drawn - drawn / scale)

    def fly_view(self, lat, lon, distance):
        """Перелёт с прежними азимутом и наклоном, для синхронизации."""
        pose = self.view.navigator.pose
        self._fly_to(lat, lon, distance, pose.heading, pose.tilt,
                     focus=False)

    def _fly_to(self, lat, lon, distance, heading=0.0, tilt=0.0,
                focus=True):
        """Перелёт, по умолчанию в конце взгляд отвесный, север вверху."""
        navigator = self.view.navigator
        flight = Flight(navigator.pose, lat, lon, distance, heading, tilt,
                        fov_y=self.view.camera.fov_y)
        navigator.start_flight(flight, time.monotonic())
        if focus:
            self.view.setFocus()
        self.view.update()

    def _show_state(self):
        keys = start_keys()
        done = sum(1 for key in keys if self.view.has(key))
        text, shown = self.message
        if text and time.monotonic() - shown < MESSAGE_TIME:
            self.status.setText(text)
            return
        sky = self.view.sky_view
        if sky is not None:
            # Небо тайлов не грузит, загрузка глобуса стоит без ошибки.
            text = tr("Звёздное небо, поле зрения {fov}°",
                      fov=int(round(sky.fov)))
            if self._cursor_text:
                text += "\n" + self._cursor_text
            self.status.setText(text)
            return
        if self.errors:
            text = tr("Подложка не загрузилась: {error}",
                      error=next(iter(self.errors.values())))
        elif self.overlay_error:
            text = tr("Векторная основа не загрузилась: {error}",
                      error=self.overlay_error)
        elif self.dirty:
            text = tr("Настройки или слои изменились. Глобус покажет их "
                      "после кнопки «Обновить».")
        elif done < len(keys):
            text = tr("Загрузка подложки: {done} из {total}",
                      done=done, total=len(keys))
        elif self.view.error:
            text = tr("Контекст OpenGL 3.3 недоступен: {version}",
                      version=self.view.error)
        else:
            text = tr("Обзор с высоты {height}",
                      height=distance_text(self.view.altitude()))
            text += self._load_text()
            if self._cursor_text:
                text += "\n" + self._cursor_text
            self.status.setText(text)
            return
        # Вставшая загрузка и тяжёлые метки видны и рядом с ошибкой или
        # подсказкой «Обновить».
        self.status.setText(text + self._load_text())

    def _load_text(self):
        """Хвост первой строки: загрузка, вставшая загрузка, объём меток.

        Деградация видна, а не прячется в размытой картинке, решение
        автора от 28 сентября 2026 года (шаг 14).
        """
        view = self.view
        parts = []
        if view.load_stalled:
            parts.append(tr("загрузка стоит {seconds} с",
                            seconds=int(view.load_stalled)))
        elif view.load_missing:
            parts.append(tr("загрузка {count}", count=view.load_missing))
        vertices = view.object_vertices()
        if vertices > OBJECT_BUDGET:
            parts.append(tr("метки тяжёлые, {count} тыс. вершин",
                            count=vertices // 1000))
        return "".join(" · " + part for part in parts)

    # Координаты под курсором.

    def _hovered(self, px, py):
        """Курсор сдвинулся. Точка считается не чаще раза в CURSOR_PERIOD."""
        self._hover = None if px < 0 else (px, py)
        if self._hover is None:
            self._cursor_text = ""
            self._show_state()
        elif not self._cursor_timer.isActive():
            self._cursor_timer.start(CURSOR_PERIOD)

    def _update_cursor(self):
        """Широта, долгота и высота рельефа под курсором."""
        text = ""
        view = self.view
        if self._hover is not None and view.sky_view is not None:
            cam = view.camera
            text = ra_dec_text(view.sky_view.direction_at(
                *self._hover, cam.width, cam.height))
        elif self._hover is not None:
            point = ground_under(view.camera, *self._hover,
                                 view.navigator.pose.terrain)
            if point is not None:
                lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
                if self._ruler_open() and self.ruler.spatial():
                    found = self._surface(*self._hover)
                    if found is not None:
                        self.ruler.set_cursor(found[:2], found[2])
                elif self._ruler_open():
                    self.ruler.set_cursor((lat, lon))
                elif self._place_open():
                    self.drawer.set_cursor((lat, lon))
                scale = view.store.scale
                text = point_text(lat, lon, h / scale if scale else None,
                                  digits=5, fmt=self.coords)
        if text != self._cursor_text:
            self._cursor_text = text
            self._show_state()
