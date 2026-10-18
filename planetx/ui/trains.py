# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строка «Поезда Финляндии»: живые поезда Digitraffic на глобусе.

Ядро - core/trains.py. Положения просятся раз в POLL секунд, вид
и категория поезда - раз в TYPES_POLL секунд запросом GraphQL. Издалека
поезд - точка цвета категории с подписью, вблизи (полоса вида уже
MODEL_VIEW) - модель вагона, которая едет между обновлениями.
Вблизи (полоса уже RAIL_VIEW) окно берёт рельсы из тайлов векторной
основы уровня 14 у точки взгляда, и поезда едут по ним.
"""
import json
import time

from qgis.PyQt import sip

import numpy as np
from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from .. import journal
from ..core import ellipsoid, models, routing
from ..core import trains as core
from ..core.features import Shape
from ..i18n import tr
from ..net.overlay import fetch_bytes, fetch_json, post_json
from ..render.models import Model as ModelItem
from .legend import train_names

# Полоса вида уже этого - поезда моделями, шире - точками, метры.
MODEL_VIEW = 6000.0
# Полоса вида уже этого - рельсы из векторной основы, метры.
RAIL_VIEW = 8000.0
# Рельсы просятся в этой доле полосы вида от точки взгляда, тайлов
# не больше RAIL_TILES.
RAIL_REACH = 1.0
RAIL_TILES = 64
RAIL_PARALLEL = 4
VIEW_TICK = 1000  # мс между проверками вида
# Модели - у поездов не дальше этого числа полос вида от точки взгляда.
MODEL_REACH = 1.5
POINT_SIZE = 7.0  # точка поезда издалека, логические пиксели
PICK_PIXELS = 10.0
# Величины - выбор помощника, утверждает автор.


def _rgba(color):
    return tuple(int(round(v * 255)) for v in color) + (255,)


class TrainManager(QObject):
    """Поезда окна глобуса."""

    changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.fleet = core.Fleet()
        self.on = False
        self.error = ""
        self.reply = None
        self.types_reply = None
        self.types_at = None
        self.one_replies = {}  # ключ поезда - ответ сведений одного поезда
        self.asked = set()  # поезда, о которых уже спрашивали
        self.poll = QTimer(self)
        self.poll.setInterval(int(core.POLL * 1000))
        self.poll.timeout.connect(self._ask)
        self.view_timer = QTimer(self)
        self.view_timer.setInterval(VIEW_TICK)
        self.view_timer.timeout.connect(self._check_view)
        self.near = False
        self._shapes = []
        self._meshes = {}
        # Рельсы: шаблон адреса тайлов основы, линии по тайлам, ждущие
        # ответы, ключи тайлов вида.
        self.template = None
        self._tilejson = None
        self.rail_lines = {}
        self.rail_replies = {}
        self.rail_queue = []
        self.rail_keys = []
        self._rail_center = None
        self._models_keys = None
        # Часы съёмки ролика: [time.monotonic, секунды UTC] или None -
        # часы компьютера. Кадр с догрузкой тайлов снимается дольше
        # своей доли секунды, по настенным часам поезда прыгали бы.
        self.frozen = None
        self._frozen_at = None

    # Часы съёмки.

    def freeze(self, clock=None):
        """Поезда идут по часам съёмки: положения больше не просятся,
        переходы к новым положениям сняты, время двигают step_clock
        и set_clock."""
        self.poll.stop()
        for train in self.fleet.trains.values():
            train.blend_from = None
        self.frozen = [time.monotonic(),
                       time.time() if clock is None else clock]
        self._frozen_at = tuple(self.frozen)

    def step_clock(self, seconds):
        """Сдвинуть часы съёмки на seconds."""
        if self.frozen is not None:
            self.frozen[0] += seconds
            self.frozen[1] += seconds

    def set_clock(self, seconds):
        """Часы съёмки - seconds от её начала: кадр записи облёта."""
        if self.frozen is not None:
            self.frozen = [self._frozen_at[0] + seconds,
                           self._frozen_at[1] + seconds]

    def unfreeze(self):
        """Снова часы компьютера и опрос службы."""
        self.frozen = None
        if self.on:
            self.poll.start()
            self._ask()

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
            self.poll.stop()
            self.view_timer.stop()
            self.fleet = core.Fleet()
            self.asked = set()
            self.one_replies = {}
            self.types_at = None
            self.rail_lines = {}
            self.rail_queue = []
            self.rail_keys = []
            self._rail_center = None
            self.error = ""
            self._shapes = []
            self._models_keys = None
            self.view.models.set_models([], group="trains")
            self.window._refresh_shapes()
            self.view.update()
        self.changed.emit()

    def close(self):
        """Окно закрывается: таймеры стоят, ждущие запросы сняты. Ответ,
        пришедший после закрытия, окна не трогает - 19 октября 2026 года
        ответ службы после перезагрузки модуля звал удалённое окно."""
        self.on = False
        self.frozen = None
        self.poll.stop()
        self.view_timer.stop()
        replies = [self.reply, self.types_reply, self._tilejson] \
            + list(self.one_replies.values()) \
            + list(self.rail_replies.values())
        self.reply = self.types_reply = self._tilejson = None
        self.one_replies = {}
        self.rail_replies = {}
        for reply in replies:
            if reply is not None and not sip.isdeleted(reply):
                reply.abort()

    def count(self):
        return len(self.fleet.trains)

    # Запросы службы.

    def _ask(self):
        headers = {"Digitraffic-User": core.USER}
        if self.reply is None:
            self.reply = fetch_bytes(core.LATEST_URL, self._latest,
                                     prefer_cache=False, fresh=True,
                                     headers=headers)
        now = time.monotonic()
        if self.types_reply is None and (
                self.types_at is None
                or now - self.types_at >= core.TYPES_POLL):
            self.types_at = now
            self.types_reply = post_json(
                core.GRAPHQL_URL, dict(headers, **{
                    "Content-Type": "application/json"}),
                {"query": core.TYPES_QUERY}, self._types)

    def _latest(self, data, error):
        self.reply = None
        if not self.on:
            return
        if data is None:
            self.error = error
            journal.note("trains: {}".format(error))
            self.changed.emit()
            return
        try:
            samples = core.parse_latest(json.loads(data))
        except ValueError as failure:
            self.error = str(failure)
            self.changed.emit()
            return
        self.error = ""
        self.fleet.update(samples, time.monotonic())
        self._ask_missing()
        self._rebuild()
        self.changed.emit()

    def _ask_missing(self):
        """Вид поездов, которых нет в ответе GraphQL, - по одному,
        не больше TYPES_EACH за опрос, о каждом один раз."""
        if self.types_at is None or self.types_reply is not None:
            return
        missing = [key for key in self.fleet.trains
                   if key not in self.fleet.info and key not in self.asked]
        for key in missing[:core.TYPES_EACH]:
            self.asked.add(key)
            self.one_replies[key] = fetch_json(
                core.train_url(key),
                lambda data, error, key=key: self._one(key, data, error),
                prefer_cache=False)

    def _one(self, key, data, _error):
        self.one_replies.pop(key, None)
        if not self.on:
            return
        found = core.parse_train(data)
        if found:
            self.fleet.info.update(found)
            self._rebuild(force=True)

    def _types(self, data, error):
        self.types_reply = None
        if not self.on:
            return
        found = core.parse_types(data)
        if not found:
            if error:
                journal.note("trains types: {}".format(error))
            return
        # Сведения прибывших поездов, взятые по одному, остаются.
        kept = {key: info for key, info in self.fleet.info.items()
                if key in self.fleet.trains}
        kept.update(found)
        self.fleet.info = kept
        self._rebuild(force=True)

    # Вид: точки издалека, модели вблизи, рельсы.

    def _view(self):
        pose = self.view.navigator.pose
        return pose.lat, pose.lon, self.window._view_width()

    def _check_view(self):
        if not self.on:
            return
        lat, lon, width = self._view()
        near = width < MODEL_VIEW
        if near != self.near:
            self.near = near
            self._rebuild()
        self._update_rails(lat, lon, width)
        if near:
            self._update_models(lat, lon, width)

    def _rebuild(self, force=False):
        """Точки поездов издалека, модели вблизи."""
        if force:
            self._models_keys = None
        lat, lon, width = self._view()
        self.near = width < MODEL_VIEW
        shapes = []
        if not self.near:
            now = time.monotonic()
            for key, plat, plon, _ in self.fleet.positions(now):
                info = self.fleet.info.get(key)
                color = core.category_color(info.category if info else "")
                shapes.append(Shape("point", [(plat, plon)],
                                    name=core.label(key, info),
                                    color=_rgba(color), width=POINT_SIZE))
        self._shapes = shapes
        self._update_models(lat, lon, width)
        self.window._refresh_shapes()
        self.view.update()

    def shapes(self):
        """Точки поездов для своих объектов глобуса."""
        return list(self._shapes) if self.on else []

    def _mesh(self, category, front):
        """Части модели вагона категории: (общие части вида, радиус,
        матрица места). front - головной вагон с лобовым стеклом."""
        found = self._meshes.get((category, front))
        if found is None:
            parts = models.merge(core.train_parts(
                core.category_color(category), front))
            base = models.frame(0.0, 0.0)
            arrays = models.vertices(parts, 0.0, 0.0)
            shared = [(array, None, part.rgba, None)
                      for array, part in zip(arrays, parts)]
            found = (shared, models.radius(parts), base)
            self._meshes[(category, front)] = found
        return found

    def _update_models(self, lat, lon, width):
        """Модели поездов у точки взгляда, группа «trains»."""
        keys = []
        if self.near:
            reach = MODEL_REACH * width
            for key, train in self.fleet.trains.items():
                sample = train.sample
                if core._metres(lat, lon, sample.lat, sample.lon) <= reach:
                    keys.append(key)
        keys.sort()
        if keys == self._models_keys:
            return
        self._models_keys = keys
        items = []
        for key in keys:
            info = self.fleet.info.get(key)
            category = info.category if info else ""
            for car in range(core.cars(category)):
                shared, radius, base = self._mesh(category, car == 0)
                items.append(ModelItem(
                    ("train",) + tuple(key) + (car,), shared,
                    (0.0, 0.0, "clampToGround", 0.0), radius, 1.0, None,
                    base, mover=self._mover(key, base, car), live=True,
                    mesh=("train", category, car == 0)))
        self.view.models.set_models(items, group="trains")
        self.view.update()

    def _mover(self, key, base, car):
        back = car * core.CAR_STEP + core.CAR_LENGTH / 2.0

        def mover(now):
            train = self.fleet.trains.get(key)
            if train is None or not self.near:
                return None
            clock = time.time()
            if self.frozen is not None:
                now, clock = self.frozen
            # Точка модели - середина вагона, голова поезда - точка GPS.
            lat, lon, heading = self.fleet.place(train, now, clock, back)
            if heading != heading:
                heading = 0.0
            return lat, lon, models.moved(base, lat, lon, heading)
        return mover

    # Рельсы.

    def _update_rails(self, lat, lon, width):
        if width >= RAIL_VIEW:
            if self.rail_keys:
                self.rail_keys = []
                self.rail_queue = []
                self._rail_center = None
                self.fleet.set_rails(None)
            return
        if self._rail_center is not None:
            moved = core._metres(lat, lon, *self._rail_center)
            if moved < 0.25 * width:
                return
        self._rail_center = (lat, lon)
        keys = routing.corridor((lat, lon), (lat, lon), RAIL_REACH * width)
        self.rail_keys = keys[:RAIL_TILES]
        self.rail_queue = [k for k in self.rail_keys
                           if k not in self.rail_lines
                           and k not in self.rail_replies]
        self._rail_template()

    def _rail_template(self):
        source = getattr(self.window, "_ofm_source", None)
        if source is not None:
            self.template = source.url
        if self.template is not None:
            self._pump()
            self._set_rails()
            return
        if self._tilejson is None:
            self._tilejson = fetch_json(self.window._vector_choice(),
                                        self._tilejson_done)

    def _tilejson_done(self, data, error):
        self._tilejson = None
        if not self.on:
            return
        tiles = (data or {}).get("tiles") or []
        if not tiles:
            journal.note("trains rails: no tiles {}".format(error))
            return
        self.template = tiles[0]
        self._pump()

    def _pump(self):
        while self.rail_queue and len(self.rail_replies) < RAIL_PARALLEL:
            key = self.rail_queue.pop(0)
            z, x, y = key
            url = self.template.replace("{z}", str(z)).replace(
                "{x}", str(x)).replace("{y}", str(y))
            self.rail_replies[key] = fetch_bytes(
                url, lambda data, error, key=key: self._rail_tile(key, data,
                                                                  error))

    def _rail_tile(self, key, data, _error):
        if self.rail_replies.pop(key, None) is None or not self.on:
            return
        try:
            lines = routing.decode(key, data) if data else []
        except ValueError:
            lines = []
        self.rail_lines[key] = [line.points for line in lines
                                if line.cls == "rail"]
        if len(self.rail_lines) > 4 * RAIL_TILES:
            keep = set(self.rail_keys)
            self.rail_lines = {k: v for k, v in self.rail_lines.items()
                               if k in keep}
        self._pump()
        if not self.rail_replies and not self.rail_queue:
            self._set_rails()

    def _set_rails(self):
        if not self.on:
            return
        lines = [points for key in self.rail_keys
                 for points in self.rail_lines.get(key, ())]
        self.fleet.set_rails(core.Rails(lines) if lines else None)
        self.view.update()

    # Опрос щелчком.

    def identify(self, px, py):
        """Поезда под пикселем кадра: [(название, [(поле, значение)])]."""
        if not self.on or not self.fleet.trains:
            return []
        now, clock = time.monotonic(), time.time()
        keys, points = [], []
        for key, lat, lon, _ in self.fleet.positions(now, clock):
            keys.append(key)
            points.append(ellipsoid.geodetic_to_ecef(
                lat, lon, self.view.label_height(lat, lon)))
        camera = self.view.camera
        pixels, front = camera.project(np.asarray(points, dtype=np.float64))
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        radius = PICK_PIXELS * self.view.devicePixelRatioF()
        if self.near:
            radius *= 3.0
        found = []
        names = train_names()
        for n in np.argsort(gap):
            if gap[n] > radius or not front[n] or len(found) >= 5:
                break
            key = keys[int(n)]
            train = self.fleet.trains[key]
            info = self.fleet.info.get(key)
            values = []
            if info is not None:
                if info.kind:
                    values.append((tr("Вид"), info.kind))
                if info.category:
                    values.append((tr("Категория"),
                                   names.get(info.category, info.category)))
                if info.line:
                    values.append((tr("Линия"), info.line))
                if info.operator:
                    values.append((tr("Оператор"), info.operator.upper()))
            values.append((tr("Номер поезда"), str(key[0])))
            values.append((tr("Скорость"), tr(
                "{value} км/ч",
                value="{:.0f}".format(train.sample.speed * 3.6))))
            values.append((tr("Положение, UTC"), time.strftime(
                "%Y-%m-%d %H:%M:%S", time.gmtime(train.sample.t))))
            values.append((tr("Источник"), core.PAGE))
            found.append((core.label(key, info), values))
        return found

