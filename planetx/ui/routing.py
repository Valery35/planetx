# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Маршрут по дорогам векторной основы: точки, загрузка, расчёт.

Расчёт - core/routing.py. Начало и конец ставит меню правой кнопки
на глобусе, пункты «Проложить маршрут отсюда» и «Проложить маршрут
сюда». Тайлы коридора
просятся через кэш QGIS не больше PARALLEL сразу, тот же адрес, что
у векторной основы, - OpenFreeMap или своя основа в схеме OpenMapTiles.
Граф и путь считаются генераторами частями в главном потоке, шаг -
проход цикла событий. С флажком «через сервис» окна «Источники данных»
маршрут сначала просится у сервиса OSRM, не чаще раза в секунду, по
тайлам - только если сервис не ответил и точки не дальше MAX_DISTANCE.
Готовый путь ложится в «Мои метки», окно летит к нему, строка под
поиском показывает длину и время и пересчитывает путь другим способом.
"""
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer, QUrl, pyqtSignal
from qgis.PyQt.QtGui import QDesktopServices

from ..core import routing, sources
from ..core.features import Shape
from ..i18n import tr
from ..net.overlay import fetch_bytes, fetch_json

MODE_KEY = "PlanetX/route_mode"
PARALLEL = 4  # запросов тайлов сразу
ROUTE_COLOR = (0, 120, 255, 255)
ROUTE_WIDTH = 4.0


def mode_names():
    return {"car": tr("на машине"), "bike": tr("на велосипеде"),
            "foot": tr("пешком")}


def mode_links():
    return {"car": tr("На машине"), "bike": tr("На велосипеде"),
            "foot": tr("Пешком")}


def service_on():
    """Строить ли маршрут через сервис, флажок окна «Источники
    данных», по умолчанию да."""
    return QgsSettings().value(sources.ROUTER_ON_KEY, True, type=bool)


def service_template():
    return sources.router(QgsSettings().value(sources.ROUTER_KEY, ""))


def duration_text(seconds):
    """Время в пути: минуты, с часа - часы и минуты."""
    minutes = int(round(seconds / 60.0))
    if minutes < 60:
        return tr("{value} мин", value=str(max(minutes, 1)))
    return tr("{hours} ч {minutes} мин", hours=str(minutes // 60),
              minutes=str(minutes % 60))


class RouteManager(QObject):
    """Маршруты окна глобуса."""

    # Маршрут готов: ключ метки в «Моих метках».
    finished = pyqtSignal(str)

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.origin = None  # (широта, долгота, название)
        self.target = None
        value = QgsSettings().value(MODE_KEY, "car")
        self.mode = value if value in routing.MODES else "car"
        self.lines = {}  # ключ тайла - линии дорог
        self.replies = {}
        self.queue = []
        self.half = 0.0
        self.widened = 0
        self._steps = None
        self._stage = ""
        self._counted = 0
        self.template = None
        self._tilejson = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._advance)
        self.last = None  # последний маршрут, core.routing.Route
        self.via = ""  # кто построил: "service" или "tiles"
        self.service_reply = None
        self._service_at = -routing.SERVICE_GAP  # время прошлого запроса
        self.service_timer = QTimer(self)
        self.service_timer.setSingleShot(True)
        self.service_timer.timeout.connect(self._ask_service)
        self._service_error = ""

    # Точки.

    def set_origin(self, lat, lon, name=""):
        self.origin = (lat, lon, name)
        self._show(tr("Начало маршрута поставлено. Конец - пункт "
                      "«Проложить маршрут сюда» меню на глобусе."))
        self._maybe_start()

    def set_target(self, lat, lon, name=""):
        self.target = (lat, lon, name)
        if self.origin is None:
            self._show(tr("Конец маршрута поставлен. Начало - пункт "
                          "«Проложить маршрут отсюда» меню на глобусе."))
        self._maybe_start()

    def set_mode(self, mode):
        if mode not in routing.MODES:
            return
        self.mode = mode
        QgsSettings().setValue(MODE_KEY, mode)
        self._maybe_start()

    def clear(self):
        self.abort()
        self.origin = self.target = None
        self.window.panel.set_answer("")

    def busy(self):
        return bool(self.replies or self.queue or self._steps
                    or self.service_reply is not None
                    or self.service_timer.isActive())

    # Расчёт.

    def _maybe_start(self):
        if self.origin is None or self.target is None:
            return
        self.abort()
        self._service_error = ""
        if service_on():
            self._show(tr("Маршрут: запрос к сервису…"), links=False)
            wait = routing.SERVICE_GAP - (time.monotonic()
                                          - self._service_at)
            self.service_timer.start(int(max(wait, 0.0) * 1000))
            return
        self._tiles()

    def _ask_service(self):
        """Один запрос маршрута к сервису OSRM."""
        if self.origin is None or self.target is None:
            return
        self._service_at = time.monotonic()
        url = routing.service_url(service_template(), self.mode,
                                  self.origin[:2], self.target[:2])
        self.service_reply = fetch_json(
            url, self._service_done, prefer_cache=False)

    def _service_done(self, data, error):
        if self.service_reply is None:
            return
        self.service_reply = None
        try:
            route = routing.parse_service(data) if data is not None \
                else None
        except ValueError as problem:
            route, error = None, str(problem)
        if route is not None:
            self.via = "service"
            self._done(route)
            return
        self._service_error = error or "no data"
        self._tiles()

    def _tiles(self):
        """Маршрут по тайлам дорог векторной основы."""
        a, b = self.origin[:2], self.target[:2]
        distance = float(routing._metres(a[0], a[1], b[0], b[1]))
        if distance > routing.MAX_DISTANCE and self._service_error:
            self._show(tr(
                "Маршрут не построен: сервис ответил «{error}», а по "
                "дорогам векторной основы маршрут строится до {limit} км "
                "по прямой.", error=self._service_error,
                limit="{:.0f}".format(routing.MAX_DISTANCE / 1000.0)))
            return
        if distance > routing.MAX_DISTANCE:
            self._show(tr(
                "Точки дальше {limit} км по прямой. Без сервиса маршрут "
                "строится по дорогам района, для дальних поездок он не "
                "подходит. Сервис маршрутов включает окно «Источники "
                "данных».",
                limit="{:.0f}".format(routing.MAX_DISTANCE / 1000.0)),
                links=False)
            return
        self.half = max(routing.CORRIDOR_MIN,
                        routing.CORRIDOR_SHARE * distance)
        self.widened = 0
        if self.template is None:
            self._ask_tilejson()
            return
        self._fetch_corridor()

    def _ask_tilejson(self):
        source = getattr(self.window, "_ofm_source", None)
        if source is not None:
            self.template = source.url
            self._fetch_corridor()
            return
        if self._tilejson is None:
            self._show(tr("Маршрут: адрес дорог векторной основы…"))
            self._tilejson = fetch_json(self.window._vector_choice(),
                                        self._tilejson_done)

    def _tilejson_done(self, data, error):
        self._tilejson = None
        tiles = (data or {}).get("tiles") or []
        if not tiles:
            self._show(tr("Маршрут не построен: нет адреса тайлов "
                          "векторной основы. {error}", error=error or ""),
                       links=False)
            return
        self.template = tiles[0]
        if self.origin is not None and self.target is not None:
            self._fetch_corridor()

    def _fetch_corridor(self):
        keys = routing.corridor(self.origin[:2], self.target[:2], self.half)
        if len(keys) > routing.MAX_TILES:
            self._show(tr("Маршрут не построен: коридор между точками - "
                          "{count} тайлов дорог, предел {limit}.",
                          count=str(len(keys)),
                          limit=str(routing.MAX_TILES)), links=False)
            return
        self.keys = keys
        self.queue = [k for k in keys if k not in self.lines]
        self._pump()
        if not self.replies:
            self._compute()

    def _pump(self):
        while self.queue and len(self.replies) < PARALLEL:
            key = self.queue.pop(0)
            z, x, y = key
            url = self.template.replace("{z}", str(z)).replace(
                "{x}", str(x)).replace("{y}", str(y))
            self.replies[key] = fetch_bytes(
                url, lambda data, error, key=key: self._tile(key, data,
                                                               error))
        self._count_pending()
        done = len(self.keys) - len(self.queue) - len(self.replies)
        if self.replies:
            self._show(tr("Маршрут: тайлы дорог {done} из {total}",
                          done=str(done), total=str(len(self.keys))),
                       links=False)

    def _tile(self, key, data, error):
        if self.replies.pop(key, None) is None:
            return
        try:
            self.lines[key] = routing.decode(key, data) if data else []
        except ValueError:
            self.lines[key] = []
        self._pump()
        if not self.replies and not self.queue:
            self._compute()

    def _count_pending(self):
        """Ждущие тайлы - в счётчик загрузки вида."""
        view = self.window.view
        count = len(self.replies)
        view.data_pending = max(0, view.data_pending + count - self._counted)
        self._counted = count

    def _compute(self):
        lines = [ln for k in self.keys for ln in self.lines.get(k, ())]
        self._stage = "graph"
        self._steps = routing.build_steps(lines, self.mode)
        self._show(tr("Маршрут: расчёт…"), links=False)
        self.timer.start(0)

    def _advance(self):
        """Шаг генератора расчёта, не больше нескольких миллисекунд
        Python за проход цикла событий."""
        if self._steps is None:
            return
        try:
            value = next(self._steps)
        except StopIteration:
            self._steps = None
            return
        if value is None:
            self.timer.start(0)
            return
        if self._stage == "graph":
            self.graph = value
            self._stage = "route"
            self._steps = routing.route_steps(value, self.origin[:2],
                                              self.target[:2], self.mode)
            self.timer.start(0)
            return
        self._steps = None
        self.via = "tiles"
        self._done(value)

    def _done(self, route):
        if not isinstance(route, routing.Route):
            if self.widened < routing.WIDEN:
                # Пути в коридоре нет: шире вдвое.
                self.widened += 1
                self.half *= 2.0
                self._fetch_corridor()
                return
            self._show(tr("Маршрут не найден: точки не связаны дорогами "
                          "векторной основы или дальше {reach} м от них.",
                          reach="{:.0f}".format(routing.REACH)))
            return
        self.last = route
        name = self.window.new_name(tr("Маршрут"))
        text = self._summary(route)
        shape = Shape("line", route.points, ROUTE_COLOR, ROUTE_WIDTH,
                      name=name)
        key = self.window.myplaces.add(
            shape, measure=text,
            folder=self.window.panel.current_folder(),
            body=self.window.body_key())
        self._show(tr("{name}: {summary}", name=name, summary=text))
        self.finished.emit(key or "")

    def _summary(self, route):
        a = self.origin[2] or tr("точка")
        b = self.target[2] or tr("точка")
        text = tr("{a} - {b}, {km} км, {time} {mode}", a=a, b=b,
                  km="{:.1f}".format(route.length / 1000.0),
                  time=duration_text(route.seconds),
                  mode=mode_names()[self.mode])
        if self.via == "service":
            text += ". " + tr("Сервис OSRM, данные © OpenStreetMap")
        elif self._service_error:
            text += ". " + tr("Сервис не ответил ({error}), маршрут по "
                              "тайлам дорог", error=self._service_error)
        return text

    def abort(self):
        self.timer.stop()
        self.service_timer.stop()
        reply, self.service_reply = self.service_reply, None
        if reply is not None:
            reply.abort()
        self._steps = None
        self.queue = []
        replies, self.replies = self.replies, {}
        self._count_pending()
        for reply in replies.values():
            reply.abort()

    def close(self):
        self.abort()

    # Строка под поиском.

    def _show(self, text, links=True):
        options = []
        if links and self.origin is not None and self.target is not None:
            for mode, title in mode_links().items():
                if mode != self.mode:
                    options.append(("route:" + mode, title))
            if self.via == "service":
                options.append(("route:fix", tr("Ошибка на карте")))
        if self.origin is not None or self.target is not None:
            options.append(("route:clear", tr("Сбросить")))
        self.window.panel.set_answer(text, links=options, talk=False)

    def link(self, name):
        if name == "clear":
            self.clear()
        elif name == "fix":
            QDesktopServices.openUrl(QUrl(routing.FIX_MAP))
        elif name in routing.MODES:
            self.set_mode(name)

