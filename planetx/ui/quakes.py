# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Землетрясения: сводка USGS за 30 суток (core/quakes.py) и каталог
ISC-GEM с 1904 года (core/iscgem.py). Очаги рисует вид (render.quakes,
поля вида quakes и history), шкала глубины общая. Строки реестра
каталога (core/rows.py) и исполнитель.
"""
import datetime
import math
import os
import time

import numpy as np
from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import iscgem, quakes as quakes_core, when
from ..core.rows import Row
from ..i18n import tr
from .overpass import brief_error

QUAKES, HISTORY = "quakes", "iscgem"
# Очагов у щелчка в окне «Объекты» не больше: каталог ISC-GEM даёт
# десятки событий в одной точке. Выбор помощника.
PICK_MOST = 20


def _stamp(seconds):
    if seconds is None or not math.isfinite(seconds):
        return ""
    # fromtimestamp на Windows не берёт время до 1970 года.
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    return (epoch + datetime.timedelta(seconds=seconds)).strftime(
        "%Y-%m-%d %H:%M")


class QuakeTool(QObject):
    """Сводка USGS и каталог ISC-GEM, их загрузка и очаги на виде."""

    shown_key = None
    # Выгрузка точек «В проект QGIS…» берёт только промежуток шкалы.
    point_window = True

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.events = []  # сводка USGS
        self.reply = None
        self.error = ""
        self.history = None  # каталог ISC-GEM
        self.history_reply = None
        self.parts = []
        self.queue = []
        self.quiet = False

    @property
    def legend(self):
        return self.window.quake_legend

    def sync_legend(self):
        """Шкала глубины очагов - при очагах на Земле."""
        window = self.window
        on = (window.extras.get(QUAKES, False)
              or window.extras.get(HISTORY, False)) \
            and window.planet.earth and window.view.sky_view is None
        self.legend.setVisible(on)
        window._place_attribution()

    def turn(self, key, on):
        if key == QUAKES:
            self._turn_quakes(on)
        else:
            self._turn_history(on)
        return True

    # Сводка USGS.

    def _turn_quakes(self, on):
        """Сводка USGS загружается при каждом включении, кэш QGIS отдаёт
        её только по заголовкам сервера."""
        window = self.window
        self.sync_legend()
        if not on:
            if self.reply is not None:
                self.reply.abort()
            self.reply = None
            window.view.quakes.set_events([], 0.0, None)
            window._update_timebar()
            window.view.update()
            return
        self.fetch_feed()

    def fetch_feed(self):
        """Сводка землетрясений USGS, если её запроса ещё нет."""
        from ..net.overlay import fetch_json
        if self.reply is None:
            self.reply = fetch_json(quakes_core.FEED, self._feed_done,
                                    prefer_cache=False)

    def _feed_done(self, data, error):
        self.reply = None
        self.error = error
        if data is not None:
            self.events = quakes_core.parse(data)
        self.place()
        self.window._refresh_section()

    # Каталог ISC-GEM.

    @staticmethod
    def _history_path():
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, iscgem.FILE)

    def _turn_history(self, on):
        """Первое включение собирает каталог запросами ComCat по
        промежуткам лет, около 74 тысяч событий, итог - файл профиля.
        Файл старше iscgem.REFETCH_DAYS собирается заново."""
        window = self.window
        self.sync_legend()
        if not on:
            if self.history_reply is not None:
                reply, self.history_reply = self.history_reply, None
                reply.abort()
                window.view.data_pending = max(
                    0, window.view.data_pending - 1)
            self.place()
            return
        path = self._history_path()
        if self.history is None and os.path.exists(path):
            try:
                self.history = iscgem.load(path)
            except (OSError, ValueError, KeyError) as error:
                journal.note("iscgem file: {}".format(error))
            age = (time.time() - os.path.getmtime(path)) / 86400.0
            if age > iscgem.REFETCH_DAYS and self.history_reply is None:
                self._history_fetch(quiet=True)
        if self.history is not None:
            self.place()
            return
        if self.history_reply is None:
            self._history_fetch()

    def _history_fetch(self, quiet=False):
        self.parts = []
        self.queue = iscgem.periods(time.gmtime().tm_year)
        self.quiet = quiet
        self.window.view.data_pending += 1
        self._history_next()

    def _history_next(self):
        from ..net.overlay import fetch_bytes
        window = self.window
        start, end = self.queue[0]
        if not self.quiet:
            window.message = (tr("Загрузка землетрясений ISC-GEM, {year}…",
                                 year=start[:4]), time.monotonic())
            window._show_state()
        self.history_reply = fetch_bytes(iscgem.query_url(start, end),
                                         self._history_arrived)

    def _history_arrived(self, data, error):
        window = self.window
        if self.history_reply is None:
            return  # снят выключением строки
        self.history_reply = None
        if data is None:
            window.view.data_pending = max(0, window.view.data_pending - 1)
            journal.note("iscgem: {}".format(brief_error(error or "")))
            if not self.quiet:
                window.message = (tr("Каталог ISC-GEM не загрузился, "
                                     "проверьте сеть и включите строку "
                                     "снова."), time.monotonic())
                window._show_state()
            return
        self.parts.extend(iscgem.parse(bytes(data)))
        self.queue.pop(0)
        if self.queue:
            self._history_next()
            return
        window.view.data_pending = max(0, window.view.data_pending - 1)
        found = self.parts
        self.parts = []
        try:
            iscgem.save(found, self._history_path())
        except OSError as problem:
            journal.note("iscgem save: {}".format(problem))
        self.history = found
        if not self.quiet:
            window.message = (tr("Исторических землетрясений {count}.",
                                 count=len(found)), time.monotonic())
            window._show_state()
        self.place()

    # Очаги на виде.

    def place(self):
        """События на глобус по нынешнему масштабу рельефа. Эпицентр
        стоит на рельефе из хранилища высот, грубом вдали от вида. При
        разрезе Земли очаги растягиваются по глубине, как кора."""
        window = self.window
        view = window.view
        earth = window.planet.earth
        depth = window._depth_map()
        on = window.extras.get(QUAKES, False) and earth
        view.quakes.set_events(self.events if on else [], view.store.scale,
                               window._surface_ground, depth)
        on = window.extras.get(HISTORY, False) and earth
        view.history.set_events((self.history or []) if on else [],
                                view.store.scale, window._surface_ground,
                                depth)
        window._update_timebar()
        self.time_changed()
        window._show_attribution()
        view.update()

    def relief_changed(self):
        self.place()

    def wedge_changed(self):
        """Растяжение коры разреза сменилось: очаги заново."""
        view = self.window.view
        if view.quakes.events or view.history.events:
            self.place()

    def time_changed(self):
        span = getattr(self.window, "_time_range", None)
        self.window.view.quakes.window = span
        self.window.view.history.window = span

    def time_marks(self):
        """Охват шкалы времени: первое и последнее событие обоих слоёв.
        У каталога ISC-GEM событий десятки тысяч - по массиву времён."""
        view = self.window.view
        times = []
        span = quakes_core.span(view.quakes.events)
        if span is not None:
            times += [when.stamp(when.text(t)) for t in span]
        history = view.history.times
        history = history[~np.isnan(history)]
        if len(history):
            times += [when.stamp(when.text(float(t)))
                      for t in (history.min(), history.max())]
        return times

    def time_events(self):
        """События сводки на шкале - шкале нужен промежуток."""
        return bool(self.window.extras.get(QUAKES)
                    and self.window.view.quakes.events)

    def credits(self):
        view = self.window.view
        parts = []
        if view.quakes.events:
            parts.append(quakes_core.ATTRIBUTION)
        if view.history.events:
            parts.append(iscgem.ATTRIBUTION)
        return parts

    def identify(self, lat, lon, tolerance=0.0):
        return []  # очаги опрашиваются по пикселю, pick

    def pick(self, px, py):
        """Очаги у точки щелчка на экране - сводка USGS и каталог
        ISC-GEM, по группе на слой."""
        view = self.window.view
        out = []
        for layer, title in ((view.quakes, tr("Землетрясения")),
                             (view.history,
                              tr("Исторические землетрясения"))):
            out += self._near(layer, title, px, py)
        return out

    def _near(self, layer, title, px, py):
        """Очаги слоя layer у точки щелчка, не больше PICK_MOST
        ближайших."""
        from .globe.base import IDENTIFY_PIXELS
        from .identify import Group
        if not layer.events:
            return []
        view = self.window.view
        eye = np.asarray(view.camera.eye, dtype=np.float64)
        shown = quakes_core.facing(eye, layer.epicenter, layer.lats,
                                   layer.lons) \
            & quakes_core.in_window(layer.times, layer.window)
        radius = IDENTIFY_PIXELS * view.devicePixelRatioF() * 2.0
        best = np.full(len(layer.events), np.inf)
        for points in (layer.focus, layer.epicenter):
            pixels, front = view.camera.project(points)
            gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
            best = np.minimum(best, np.where(front, gap, np.inf))
        found = np.nonzero((best <= radius) & shown)[0]
        found = found[np.argsort(best[found])][:PICK_MOST]
        features = []
        for n in found:
            q = layer.events[int(n)]
            values = [(tr("Магнитуда"), "{:.1f}".format(q.mag)),
                      (tr("Глубина очага"), tr("{value} км", value=(
                          "{:.0f}".format(q.depth))))]
            if q.time is not None:
                values.append((tr("Время, UTC"), when.text(q.time)))
            if q.url:
                values.append((tr("Страница USGS"), q.url))
            features.append((q.place or "M {:.1f}".format(q.mag), values,
                             None))
        return [(Group(title), features)] if features else []

    @staticmethod
    def point_rows(layer, index):
        """Поля и значения очагов index для «В проект QGIS…»."""
        fields = [("place", "str"), ("mag", "real"),
                  ("depth_km", "real"), ("time", "str"), ("url", "str")]
        rows = [(q.place, q.mag, q.depth, _stamp(q.time), q.url)
                for q in (layer.events[n] for n in index)]
        return fields, rows

    def credit(self):
        return None

    def close(self):
        for name in ("reply", "history_reply"):
            reply = getattr(self, name)
            if reply is not None:
                setattr(self, name, None)
                reply.abort()


ROWS = (
    Row(QUAKES, "seismic", lambda: (tr("Землетрясения"), tr(
        "Землетрясения магнитудой от 4.5 за последние 30 "
        "суток по сводке USGS. Кружок стоит в эпицентре "
        "на поверхности. На своей глубине очаг виден в вынутом "
        "секторе строки «Разрез Земли». "
        "Цвет показывает глубину очага, размер - магнитуду. "
        "Сводка загружается при включении строки.")), QuakeTool,
        source="USGS",
        words=("землетрясения", "сейсмика", "очаги", "earthquakes"),
        after="paleo", points="quakes"),
    Row(HISTORY, "seismic", lambda: (tr("Исторические землетрясения"), tr(
        "Сильные землетрясения мира с 1904 по 2024 год по каталогу "
        "ISC-GEM - около 74 тысяч событий магнитудой от 5, места, "
        "глубины и магнитуды пересчитаны одним способом. "
        "Кружок стоит в эпицентре, на своей глубине - в вынутом "
        "секторе разреза Земли, цвет показывает "
        "глубину, размер - магнитуду. Промежуток шкалы времени "
        "отбирает события. Щелчок по кружку показывает место, дату, "
        "магнитуду и страницу события USGS. Первое включение "
        "скачивает каталог по частям, около 13 МБ.")), QuakeTool,
        source="ISC-GEM",
        words=("исторические землетрясения", "землетрясения с 1900",
               "старые землетрясения", "каталог землетрясений", "isc-gem",
               "iscgem", "historical earthquakes"),
        after=QUAKES, points="history"),
)
