# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Недра и энергетика: горные разработки, ЛЭП, электростанции, плиты, кабели,
место под щелчком, координаты под курсором.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import time

import numpy as np

from ...core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ...core.measure import surface_level
from ...core.flight import Flight
from ...core.navigation import ground_under
from ...core.skyview import ra_dec_text
from ...core import slabs
from ...i18n import tr
from ...render.view import OBJECT_BUDGET, start_keys
from ..identify import Group, point_text
from .base import CURSOR_PERIOD, MESSAGE_TIME, distance_text


class ResourcesMixin:
    """Часть окна глобуса GlobeWindow."""

    # Объекты OpenStreetMap по тайлам Overpass (ui/overpass.py).

    def _overpass_view_changed(self):
        if self.planet.earth and (self.extras.get("osm_mines")
                                  or self.extras.get("infra_osm")):
            self._osm_timer.start()

    def _place_rows(self):
        """Точки строк реестра - заново по нынешнему масштабу рельефа."""
        for tool in self.row_tools.values():
            if hasattr(tool, "relief_changed"):
                tool.relief_changed()

    def _want_overpass(self):
        """Недостающие тайлы у точки взгляда - загрузчикам Overpass
        включённых строк."""
        if not self.planet.earth:
            return
        pose = self.view.navigator.pose
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        altitude = float(ecef_to_geodetic(eye)[2])
        for tool in self.row_tools.values():
            if hasattr(tool, "want"):
                tool.want(pose.lat, pose.lon, altitude)

    def _overpass_failed(self):
        """Отказ сервера Overpass: пользователю - короткая фраза,
        подробности уже в журнале работы."""
        self.message = (tr("Сервер OpenStreetMap не ответил, запрос "
                           "повторится сам."), time.monotonic())
        self._show_state()

    def _flow_changed(self):
        if self.flow.error:
            self.message = (self.flow.error, time.monotonic())
        elif self.flow.currents_day:
            self.message = (tr("Течения на {day}.",
                               day=self.flow.currents_day),
                            time.monotonic())
        self._show_state()
        self._show_attribution()

    def _identify_site(self, lat, lon, height):
        """Место под щелчком: высота или глубина, кора CRUST1.0, плита
        Slab2. Кора и зона плиты просятся, если их нет, окно обновится
        по их приходу."""
        if not self.planet.earth:
            return []
        # Строка реестра со своими высотами (геоид) даёт свою группу:
        # высота под щелчком - не рельеф и не дно, кора к ней не относится.
        replaced = self._row_hook("replace_site", height)
        if replaced is not None:
            return replaced
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
        for tool in self.row_tools.values():
            if hasattr(tool, "place_values"):
                values += tool.place_values(lat, lon)
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
