# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строки «Суда Балтики» и «Самолёты»: живые объекты без рельсов.

Ядро - core/movers.py, core/vessels.py, core/aircraft.py. LiveManager -
общее устройство: опрос службы раз в poll секунд, издалека - точки
цвета группы с подписью у вида (не больше MAX_POINTS ближайших), вблизи
(полоса уже model_view) - модели, которые идут своим курсом между
обновлениями. Самолёт в воздухе стоит на своей высоте, судно и борт на
земле - на поверхности под собой, над водой - на уровне воды. Запись
облёта ведёт объекты по своим часам (freeze, set_clock), как поезда.
"""
import json
import time

import numpy as np
from qgis.PyQt import sip
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from .. import journal
from ..core import aircraft, ellipsoid, models, movers, vessels
from ..core.features import Shape
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..render.models import Model as ModelItem

VIEW_TICK = 1000  # мс между проверками вида
MAX_POINTS = 600  # точек издалека не больше, ближайших к точке взгляда
POINT_REACH = 3.0  # точки - не дальше стольких полос вида
MODEL_REACH = 1.5  # модели - не дальше стольких полос вида
POINT_SIZE = 7.0
PICK_PIXELS = 10.0
HEADERS = {"Digitraffic-User": "PlanetX"}


def _rgba(color):
    return tuple(int(round(v * 255)) for v in color) + (255,)


class LiveManager(QObject):
    """Общее устройство строки живых объектов. Наследник задаёт службу,
    разбор, группы, размеры, модель и поля опроса."""

    changed = pyqtSignal()
    poll_seconds = 10.0
    model_view = 10000.0
    extrapolate = 60.0
    stale = 900.0
    info_seconds = 600.0

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.fleet = movers.Movers(self.extrapolate, self.stale)
        self.on = False
        self.error = ""
        self.reply = None
        self.info_reply = None
        self.info_at = None
        self.near = False
        self.frozen = None
        self._frozen_at = None
        self._shapes = []
        self._meshes = {}
        self._models_keys = None
        self._points_at = None
        self.poll = QTimer(self)
        self.poll.setInterval(int(self.poll_seconds * 1000))
        self.poll.timeout.connect(self._ask)
        self.view_timer = QTimer(self)
        self.view_timer.setInterval(VIEW_TICK)
        self.view_timer.timeout.connect(self._check_view)

    # Наследнику.

    def url(self):
        raise NotImplementedError

    def parse(self, data):
        """(список movers.Sample, {ключ: сведения} или None)."""
        raise NotImplementedError

    def info_url(self):
        return None

    def parse_info(self, data):
        return {}

    def group_of(self, key):
        raise NotImplementedError

    def color(self, group):
        raise NotImplementedError

    def size(self, key):
        """(ширина, длина, высота) модели, м."""
        raise NotImplementedError

    def unit_parts(self, color):
        raise NotImplementedError

    def label(self, key):
        raise NotImplementedError

    def values(self, key, item):
        """Поля окна «Объекты»: [(поле, значение)]."""
        raise NotImplementedError

    def keep(self):
        """Ответ - только часть мира: прежние объекты вне ответа
        остаются до устаревания."""
        return False

    # Включение.

    def set_on(self, on):
        on = bool(on)
        if on == self.on:
            return
        self.on = on
        if on:
            self.poll.start()
            self.view_timer.start()
            self._ask()
        else:
            self._stop()
            self.fleet = movers.Movers(self.extrapolate, self.stale)
            self.info_at = None
            self.error = ""
            self._shapes = []
            self._models_keys = None
            self.view.models.set_models([], group=self.group_name())
            self.window._refresh_shapes()
            self.view.update()
        self.changed.emit()

    def group_name(self):
        return type(self).__name__

    def _stop(self):
        self.poll.stop()
        self.view_timer.stop()
        replies = [self.reply, self.info_reply]
        self.reply = self.info_reply = None
        for reply in replies:
            if reply is not None and not sip.isdeleted(reply):
                reply.abort()

    def close(self):
        """Окно закрывается: таймеры стоят, ждущие запросы сняты, ответ
        после закрытия окна не трогает."""
        self.on = False
        self.frozen = None
        self._stop()

    def count(self):
        return len(self.fleet)

    # Часы записи облёта.

    def freeze(self, clock=None):
        self.poll.stop()
        for item in self.fleet.items.values():
            item.blend_from = None
        self.frozen = [time.monotonic(),
                       time.time() if clock is None else clock]
        self._frozen_at = tuple(self.frozen)

    def step_clock(self, seconds):
        if self.frozen is not None:
            self.frozen[0] += seconds
            self.frozen[1] += seconds

    def set_clock(self, seconds):
        if self.frozen is not None:
            self.frozen = [self._frozen_at[0] + seconds,
                           self._frozen_at[1] + seconds]

    def unfreeze(self):
        self.frozen = None
        if self.on:
            self.poll.start()
            self._ask()

    def _clock(self, now=None):
        if self.frozen is not None:
            return self.frozen[0], self.frozen[1]
        return (time.monotonic() if now is None else now), time.time()

    # Запросы.

    def _ask(self):
        if not self.on:
            return
        if self.reply is None:
            url = self.url()
            if url:
                self.reply = fetch_bytes(url, self._done, prefer_cache=False,
                                         fresh=True, headers=HEADERS)
        info = self.info_url()
        if info and self.info_reply is None and (
                self.info_at is None
                or time.monotonic() - self.info_at >= self.info_seconds):
            self.info_at = time.monotonic()
            self.info_reply = fetch_bytes(info, self._info_done,
                                          prefer_cache=False, fresh=True,
                                          headers=HEADERS)

    def _done(self, data, error):
        self.reply = None
        if not self.on:
            return
        if data is None:
            self.error = error
            journal.note("{}: {}".format(self.group_name(), error))
            self.changed.emit()
            return
        try:
            samples, info = self.parse(json.loads(data))
        except ValueError as failure:
            self.error = str(failure)
            self.changed.emit()
            return
        self.error = ""
        if info:
            self.fleet.info.update(info)
        self.fleet.update(samples, time.monotonic(), keep=self.keep())
        self._rebuild()
        self.changed.emit()

    def _info_done(self, data, error):
        self.info_reply = None
        if not self.on or data is None:
            if error and self.on:
                journal.note("{} info: {}".format(self.group_name(), error))
            return
        try:
            found = self.parse_info(json.loads(data))
        except ValueError:
            return
        if found:
            self.fleet.info.update(found)
            self._rebuild(force=True)

    # Вид.

    def _view(self):
        pose = self.view.navigator.pose
        return pose.lat, pose.lon, self.window._view_width()

    def _check_view(self):
        if not self.on:
            return
        lat, lon, width = self._view()
        near = width < self.model_view
        moved = self._points_at is None or not movers.near(
            lat, lon, self._points_at[0], self._points_at[1],
            0.3 * width) or abs(width - self._points_at[2]) > 0.3 * width
        if near != self.near or moved:
            self._rebuild()
        elif near:
            self._update_models(lat, lon, width)

    def _ground(self, lat, lon):
        """Высота поверхности над уровнем моря под точкой: над водой -
        уровень воды."""
        scale = self.view.store.scale
        return self.view.label_height(lat, lon) / scale if scale else 0.0

    def _rebuild(self, force=False):
        if force:
            self._models_keys = None
        lat, lon, width = self._view()
        self._points_at = (lat, lon, width)
        self.near = width < self.model_view
        shapes = []
        if not self.near:
            now, clock = self._clock()
            found = []
            reach = POINT_REACH * width
            for key, plat, plon, _, alt in self.fleet.positions(now, clock):
                gap = movers._metres(lat, lon, plat, plon)
                if gap <= reach:
                    found.append((gap, key, plat, plon, alt))
            found.sort(key=lambda row: row[0])
            for _, key, plat, plon, alt in found[:MAX_POINTS]:
                color = _rgba(self.color(self.group_of(key)))
                if alt == alt:
                    shapes.append(Shape("point", [(plat, plon)],
                                        name=self.label(key), color=color,
                                        width=POINT_SIZE, alts=[alt]))
                else:
                    shapes.append(Shape("point", [(plat, plon)],
                                        name=self.label(key), color=color,
                                        width=POINT_SIZE))
        self._shapes = shapes
        self._update_models(lat, lon, width)
        self.window._refresh_shapes()
        self.view.update()

    def shapes(self):
        return list(self._shapes) if self.on else []

    def _mesh(self, group):
        found = self._meshes.get(group)
        if found is None:
            parts = models.merge(self.unit_parts(self.color(group)))
            base = models.frame(0.0, 0.0)
            arrays = models.vertices(parts, 0.0, 0.0)
            found = ([(array, None, part.rgba, None)
                      for array, part in zip(arrays, parts)], base)
            self._meshes[group] = found
        return found

    def _update_models(self, lat, lon, width):
        keys = []
        if self.near:
            reach = MODEL_REACH * width
            for key, item in self.fleet.items.items():
                sample = item.sample
                if movers.near(lat, lon, sample.lat, sample.lon, reach):
                    keys.append(key)
        keys.sort(key=str)
        if keys == self._models_keys:
            return
        self._models_keys = keys
        items = []
        for key in keys:
            group = self.group_of(key)
            shared, base = self._mesh(group)
            size = self.size(key)
            items.append(ModelItem(
                (self.group_name(), key), shared,
                (0.0, 0.0, "absolute", 0.0), 0.6 * max(size), 1.0, None,
                base, mover=self._mover(key, base, size), live=True,
                mesh=(self.group_name(), group)))
        self.view.models.set_models(items, group=self.group_name())
        self.view.update()

    def _mover(self, key, base, size):
        def mover(now):
            item = self.fleet.items.get(key)
            if item is None or not self.near or not self.on:
                return None
            now, clock = self._clock(now)
            lat, lon, heading, alt = self.fleet.place(item, now, clock)
            if heading != heading:
                heading = 0.0
            if alt != alt:
                alt = self._ground(lat, lon)
            roll = getattr(item.sample, "roll", 0.0)
            return lat, lon, models.moved(base, lat, lon, heading, 0.0,
                                          roll, size), alt
        return mover

    # Опрос щелчком.

    def identify(self, px, py):
        """Объекты под пикселем кадра: [(название, [(поле, значение)])]."""
        if not self.on or not len(self.fleet):
            return []
        now, clock = self._clock()
        keys, points = [], []
        for key, lat, lon, _, alt in self.fleet.positions(now, clock):
            keys.append(key)
            height = alt * self.view.store.scale if alt == alt \
                else self.view.label_height(lat, lon)
            points.append(ellipsoid.geodetic_to_ecef(lat, lon, height))
        pixels, front = self.view.camera.project(
            np.asarray(points, dtype=np.float64))
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        radius = PICK_PIXELS * self.view.devicePixelRatioF() \
            * (3.0 if self.near else 1.0)
        found = []
        for n in np.argsort(gap):
            if gap[n] > radius or not front[n] or len(found) >= 5:
                break
            key = keys[int(n)]
            found.append((self.label(key),
                          self.values(key, self.fleet.items[key])))
        return found


def _when(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(t))


class VesselManager(LiveManager):
    """Суда Балтики по AIS Digitraffic."""

    poll_seconds = vessels.POLL
    model_view = 20000.0
    extrapolate = vessels.EXTRAPOLATE
    stale = vessels.STALE
    info_seconds = vessels.INFO_POLL

    def group_name(self):
        return "vessels"

    def url(self):
        return vessels.LOCATIONS_URL

    def parse(self, data):
        return vessels.parse_locations(data), None

    def info_url(self):
        return vessels.VESSELS_URL

    def parse_info(self, data):
        return vessels.parse_vessels(data)

    def group_of(self, key):
        info = self.fleet.info.get(key)
        return info.group if info is not None else "other"

    def color(self, group):
        return vessels.group_color(group)

    def size(self, key):
        return vessels.ship_size(self.fleet.info.get(key))

    def unit_parts(self, color):
        return vessels.unit_ship_parts(color)

    def label(self, key):
        return vessels.label(key, self.fleet.info.get(key))

    def values(self, key, item):
        from .legend import vessel_names
        info = self.fleet.info.get(key)
        sample = item.sample
        out = []
        if info is not None:
            out.append((tr("Тип"), vessel_names().get(info.group, "")))
            if info.call:
                out.append((tr("Позывной"), info.call))
            if info.imo:
                out.append((tr("IMO"), str(info.imo)))
            if info.destination:
                out.append((tr("Назначение"), info.destination))
            if info.length:
                out.append((tr("Размеры"), tr(
                    "{length} × {width} м", length="{:.0f}".format(
                        info.length), width="{:.0f}".format(info.width))))
        out.append((tr("MMSI"), str(key)))
        out.append((tr("Скорость"), tr(
            "{value} уз", value="{:.1f}".format(sample.speed
                                               / movers.KNOT))))
        if sample.course == sample.course:
            out.append((tr("Курс"), "{:.0f}°".format(sample.course)))
        out.append((tr("Положение, UTC"), _when(sample.t)))
        return out


class AircraftManager(LiveManager):
    """Самолёты по ADS-B adsb.lol в круге у точки взгляда."""

    poll_seconds = aircraft.POLL
    model_view = 15000.0
    extrapolate = aircraft.EXTRAPOLATE
    stale = aircraft.STALE

    def group_name(self):
        return "aircraft"

    def url(self):
        lat, lon, width = self._view()
        return aircraft.point_url(lat, lon, max(2.0 * width, 20000.0))

    def keep(self):
        return True

    def parse(self, data):
        return aircraft.parse(data)

    def group_of(self, key):
        info = self.fleet.info.get(key)
        return info.group if info is not None else "other"

    def color(self, group):
        return aircraft.group_color(group)

    def size(self, key):
        info = self.fleet.info.get(key)
        return aircraft.plane_size(info.category if info else "")

    def unit_parts(self, color):
        return aircraft.unit_plane_parts(color)

    def label(self, key):
        return aircraft.label(key, self.fleet.info.get(key))

    def values(self, key, item):
        from .legend import aircraft_names
        info = self.fleet.info.get(key)
        sample = item.sample
        out = []
        if info is not None:
            if info.kind:
                out.append((tr("Тип"), info.kind))
            if info.reg:
                out.append((tr("Бортовой номер"), info.reg))
            out.append((tr("Категория"),
                        aircraft_names().get(info.group, "")))
        out.append((tr("Код ICAO"), key.upper()))
        if sample.alt == sample.alt:
            out.append((tr("Высота"), tr(
                "{metres} м ({feet} футов)",
                metres="{:.0f}".format(sample.alt),
                feet="{:.0f}".format(sample.alt / movers.FOOT))))
        else:
            out.append((tr("Высота"), tr("на земле")))
        out.append((tr("Скорость"), tr(
            "{value} км/ч", value="{:.0f}".format(sample.speed * 3.6))))
        if sample.course == sample.course:
            out.append((tr("Курс"), "{:.0f}°".format(sample.course)))
        out.append((tr("Положение, UTC"), _when(sample.t)))
        return out

