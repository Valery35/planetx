# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Темы NASA GIBS, шторка дней, солнце, сетка, горизонтали, слои GIBS и рельеф
вида.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import math
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import QTimer

from ... import journal
from ...core import (basemap, ellipsoid, events, stars, sun, graticule,
                     themes, wayback, sources as datasources)
from ...core.geocode import link_zoom
from ...core.sync import ground_size
from ...core.features import Shape
from ...core.contours import (LEVEL as CONTOUR_LEVEL,
                              SOURCE_LEVEL as CONTOUR_SOURCE,
                              is_imagery as contour_is_imagery,
                              view_step as contour_view_step)
from ...core.terrain import MAX_LEVEL as TERRAIN_MAX
from ...core.places import Place as MarkPlace
from ...i18n import tr
from ...net.loader import TileLoader
from ...net.overlay import fetch_bytes, fetch_json
from .. import guide as guide_ui
from .. import style
from ..identify import Group
from ..sidepanel import save_width, saved_width
from ..themes import theme_names
from ..project import set_visible_on_map, write_shown
from ..inset import DeepSource, DemSource, terrain_prepare
from ..contours import ContourSource, digit_glyphs
from ..properties import SCALE_RANGE
from ..nasamaps import NasaMaps, map_names
from ..overture import OvertureTiles, release_url
from .base import (BODY_CONTOUR_DEEPER, CIRCLE_COLOR,
                   GRID_COLOR, GRID_WIDTH, RELIEF_KEY, SCALE_KEY, SUN_PERIOD,
                   SURFACE_EXTRAS, THEME_KEY, TILE_SIZE, WAYBACK_PAUSE,
                   buildings_decoder,
                   contours_prepare, gibs_source, prepare_theme, slope_prepare)


class ThemesMixin:
    """Часть окна глобуса GlobeWindow."""

    # Темы NASA GIBS.

    def set_theme(self, key):
        """Тема NASA GIBS из групп раздела «Слои», "" - выключить.
        Включена одна тема, выбор помнят настройки QGIS. Выбранная тема
        открывает шкалу времени на последний день ряда, когда он придёт.
        Новая тема при открытой шкале берёт её момент."""
        # Пожары - в том же выборе: пожары или одна тема. Просьба
        # автора от 5 октября 2026 года.
        # Температура суши и моря - тоже карта витрины, просьба автора
        # от 7 октября 2026 года.
        chosen = key
        journal.note("set_theme {}".format(chosen or "-"))
        key = key if key in themes.BY_KEY else ""
        self._theme_open_time = bool(key) and key != self.theme_key \
            and not self.timebar.shown()
        self.theme_key = key
        for extra in themes.EXCLUSIVE:
            if bool(self.extras.get(extra)) != (chosen == extra):
                self.set_extra(extra, chosen == extra)
        QgsSettings().setValue(THEME_KEY, key)
        self._mark_gallery()
        self._show_theme()

    def load_gibs(self, done=None):
        """Весь каталог GIBS: слои из GetCapabilities WMTS темами
        (core.themes.register), done() - когда список пришёл. Список
        просится один раз за окно, ответ помнит кэш QGIS."""
        if getattr(self, "gibs_layers", None) is not None:
            if done is not None:
                done()
            return
        if not hasattr(self, "_gibs_waiting"):
            self._gibs_waiting = []
        if done is not None:
            self._gibs_waiting.append(done)
        if getattr(self, "_gibs_reply", None) is None:
            self._gibs_reply = fetch_bytes(themes.CAPABILITIES,
                                           self._gibs_done)

    def _gibs_done(self, data, error):
        self._gibs_reply = None
        if not data:
            self.message = (tr("Каталог NASA GIBS не загрузился: {error}",
                               error=error), time.monotonic())
            self._show_state()
            self._gibs_waiting = []
            return
        self.gibs_layers = themes.parse_capabilities(data)
        themes.register(self.gibs_layers)
        journal.note("gibs catalog {} layers".format(len(self.gibs_layers)))
        waiting, self._gibs_waiting = self._gibs_waiting, []
        for done in waiting:
            done()

    def gallery_key(self):
        """Карта витрины на глобусе: пожары, температура, тема или ""."""
        for extra in themes.EXCLUSIVE:
            if getattr(self, "extras", {}).get(extra):
                return extra
        return getattr(self, "theme_key", "")

    def _mark_gallery(self):
        """Строка витрины в «Слоях» и сама витрина - по выбранной карте."""
        if getattr(self, "panel", None) is None:
            return
        key = self.gallery_key()
        self.panel.set_theme(key, map_names()[key][0] if key else "")
        self._update_active()
        gallery = getattr(self, "gallery", None)
        if gallery is not None and gallery.isVisible():
            gallery.refresh()

    def export_key(self, key):
        """Строка «На глобусе», которой выгружается карта или слой key
        каталога, None - не выгружается или не на глобусе."""
        for row, _, _, export, on in self._active_rows():
            if export and on and (row == key or (
                    row == "map" and key == self.theme_key)):
                return row
        return None

    def _side_changed(self):
        """Окно в панели свойств появилось или ушло: место панели
        берётся у вида или отдаётся ему."""
        # Пустая панель свойств скрыта: без этого разделитель оставлял
        # ей ширину её заголовка с крестиком, снимок автора от 17 октября
        # 2026 года.
        self.side.setVisible(self.side.dialog is not None)
        sizes = self.splitter.sizes()
        if len(sizes) < 3:
            return
        want = saved_width() if self.side.dialog is not None else 0
        if (sizes[2] > 0) == (want > 0):
            return
        view = max(sizes[1] + sizes[2] - want, 100)
        self.splitter.setSizes([sizes[0], view, want])

    def _side_moved(self, pos, index):
        """Разделитель панели свойств сдвинут - ширина помнится."""
        sizes = self.splitter.sizes()
        if len(sizes) >= 3 and self.side.dialog is not None:
            save_width(sizes[2])

    def start_guide(self):
        """Знакомство с модулем с первой остановки. Прежнее закрывается."""
        if not self.isVisible():
            return
        if self.guide is not None:
            self.guide.finish()
        self.guide = guide_ui.Guide(self)
        self.guide.start()

    def open_gallery(self):
        """Каталог «Добавить данные» - немодальное окно поверх глобуса,
        одно на глобус. Панель и список «Слоёв» остаются как были."""
        if getattr(self, "gallery", None) is None:
            self.gallery = NasaMaps(self, self)
            self.gallery.setObjectName("planetxCatalog")
            self.gallery.setStyleSheet(style.window_style())
        if not self.gallery.isVisible():
            self.gallery.place()
        self.gallery.show()
        self.gallery.raise_()
        self.gallery.activateWindow()
        self.gallery.resume()
        self._mark_gallery()
        self.gallery.refresh()
        return self.gallery

    def close_gallery(self):
        """Закрыть окно каталога."""
        gallery = getattr(self, "gallery", None)
        if gallery is not None and gallery.isVisible():
            gallery.close()

    def _theme_on(self):
        return bool(self.theme_key) and self.planet.earth \
            and self.view.sky_view is None

    def _show_theme(self):
        """Тема на глобус или с глобуса. Ряд дат и шкала слоя
        просятся при первом показе темы, ответы помнятся."""
        self._time_mode()
        if not self._theme_on() or self.theme_key != themes.WAYBACK:
            self._wayback_stop()
        if not self._theme_on() or self.theme_key != "weather_wind":
            self.flow.set_wind(None)
        if not self._theme_on() or not themes.is_weather(self.theme_key):
            self.weather.hide()
            self._value_field = None
            self._update_values()
        if not self._theme_on() or themes.is_weather(self.theme_key):
            self.set_compare(False)
        if not self._theme_on():
            self._theme_shown = None
            self.theme_day = None
            self._set_gibs("theme", False)
            self.theme_legend.hide()
            self._place_attribution()
            return
        if themes.is_weather(self.theme_key):
            # Поле прогноза GFS: ряд и картинки даёт ui/weather.py.
            self._theme_shown = None
            self.weather.show(self.theme_key, self.theme_moment())
            self._update_timebar()
            return
        theme = themes.BY_KEY[self.theme_key]
        if theme.key == themes.EVENTS and not self._event_ready():
            # Снимки событий: ряд дат даёт выбранное событие.
            self._set_gibs("theme", False)
            self.theme_legend.hide()
            self.open_events()
            return
        if theme.key not in self._theme_domains \
                and isinstance(theme, themes.LayerTheme):
            # Слой каталога GIBS: ряд дат - из ответа GetCapabilities.
            self._theme_domains[theme.key] = theme.series(time.time())
        if theme.key not in self._theme_domains and theme.domains_url():
            self._theme_fetch(theme.key, "domains", theme.domains_url())
        if theme.colormap and theme.key not in self._theme_scales:
            self._theme_fetch(theme.key, "scale", theme.colormap_url())
        self._update_timebar()
        self._apply_theme()
        if theme.key == themes.WAYBACK:
            self._wayback_view()

    def _theme_fetch(self, key, kind, url):
        if (key, kind) in self._theme_replies:
            return
        self._theme_replies[(key, kind)] = fetch_bytes(
            url, lambda data, error, key=key, kind=kind:
            self._theme_done(key, kind, data, error))

    def _theme_done(self, key, kind, data, error):
        self._theme_replies.pop((key, kind), None)
        if kind == "domains":
            if data is None:
                self.message = (tr("Ряд дат темы не загрузился: {error}",
                                   error=error), time.monotonic())
                self._show_state()
                return
            if key == themes.WAYBACK:
                self._wayback_config(data)
            else:
                self._theme_domains[key] = themes.ready_intervals(
                    themes.parse_domains(data), time.time())
            self._update_timebar()
            if getattr(self, "gallery", None) is not None:
                self.gallery.domains_arrived(key)
        else:
            self._theme_scales[key] = themes.parse_colormap(data) \
                if data else None
        if key == self.theme_key:
            self._apply_theme()

    def _time_mode(self):
        """Одно время вида: покрытию нужен момент, событиям - промежуток.
        Без событий шкала - один бегунок, при теме у шкалы шаги по ряду
        темы. Решение автора от 5 октября 2026 года."""
        theme = getattr(self, "theme_key", "") and self._theme_on()
        events = any(p.visible and p.time for p in self.myplaces.places) \
            or bool(self.extras.get("quakes")
                    and self.view.quakes.events) \
            or bool(self.extras.get("fires")
                    and self.view.fires.fires is not None) \
            or bool(self._data_marks)
        maps = bool(self._map_moments())
        # Часам и историческим картам, как и покрытию, нужен момент.
        point = (bool(theme) or self._clock_on() or maps) and not events
        if self.timebar.track.point != point:
            self.timebar.set_point(point)
        self.timebar.set_stepper(self._theme_step if theme
                                 else self._map_step if maps else None)
        self.timebar.ready = self._theme_ready if theme else None
        self.timebar.set_compare(
            bool(theme) and not themes.is_weather(self.theme_key)
            or maps and not theme,
            getattr(self, "_compare_at", None) is not None
            or getattr(self, "_map_compare_at", None) is not None)
        if (theme or not maps) \
                and getattr(self, "_map_compare_at", None) is not None:
            # Тема включена поверх исторических карт - шторка карт снимается.
            self._map_compare_off()

    def _theme_step(self, moment, delta):
        """Момент соседнего дня ряда темы для шага шкалы или None.
        У поля прогноза - соседний час."""
        if themes.is_weather(self.theme_key):
            return self.weather.step(moment, delta)
        intervals = self._theme_domains.get(self.theme_key)
        if not intervals:
            return None
        days = themes.days(intervals)
        day = themes.pick_day(intervals, moment)
        if day not in days:
            return None
        index = days.index(day) + delta
        if not 0 <= index < len(days):
            return None
        return themes.moment(days[index])

    def _theme_ready(self):
        """Показан ли день темы: все картинки кадра пришли. Показ дней
        подряд ждёт этого."""
        if themes.is_weather(self.theme_key):
            return self.weather.ready()
        return all(not layer.missing and not layer.pending
                   for name, layer in self.view.gibs.items()
                   if name in ("theme", "compare") and layer.shown)

    def theme_moment(self):
        """Момент дня темы: правый бегунок открытой шкалы времени, без
        неё - None, последний день ряда."""
        if self.timebar.shown():
            hi = self.timebar.range()[1]
            if math.isfinite(hi):
                return hi
        return None

    def _apply_theme(self):
        """День темы по шкале времени, слой вида и шкала в углу. Смена
        дня той же темы держит прежние картинки до замены."""
        if not self._theme_on():
            return
        if themes.is_weather(self.theme_key):
            self.weather.set_moment(self.theme_moment())
            return
        theme = themes.BY_KEY[self.theme_key]
        intervals = self._theme_domains.get(theme.key)
        if intervals is None:
            return
        found = themes.span(intervals)
        if getattr(self, "_theme_open_time", False) and found:
            # Выбранная тема: шкала открывается на последнем дне ряда.
            self._theme_open_time = False
            if self.timebar.known:
                if not self.timebar.shown():
                    self.timebar.open_bar()
                    self.toolbar.set_time_shown(True)
                lo, hi = self.timebar.range()
                self.timebar.set_range(lo if lo < found[1] else found[1],
                                       found[1])
                self._time_range = self.timebar.range()
                self._refresh_shapes()
        day = themes.pick_day(intervals, self.theme_moment())
        if day is None:
            self.message = (tr("У темы нет дат в ряду."), time.monotonic())
            self._show_state()
            return
        self.theme_day = day
        name = theme_names()[theme.key][0] if theme.key != themes.EVENTS \
            else self.event_title() or theme_names()[theme.key][0]
        scale = self._theme_scales.get(theme.key)
        units = scale["units"] if scale else ""
        title = tr("{name}, {units} · {day}", name=name, units=units,
                   day=day) if units else tr("{name} · {day}", name=name,
                                             day=day)
        self.theme_legend.set_theme(title, scale)
        self.theme_legend.show()
        self._place_attribution()
        self._apply_compare(theme, intervals, day)
        if (theme.key, day) == self._theme_shown:
            return
        keep = self._theme_shown is not None \
            and self._theme_shown[0] == theme.key
        self._theme_shown = (theme.key, day)
        self.view.crossfade(self._theme_ready)
        if theme.key == themes.EVENTS:
            self._event_layer("theme", day, keep)
            return
        source = basemap.Source(theme.name, theme.url(day), theme.level,
                                theme.attribution, builtin=True,
                                missing=(404,))
        self.view.gibs["theme"].max_level = theme.level
        self._set_gibs("theme", True, (source, prepare_theme(theme.key)),
                       keep=keep)

    def set_compare(self, on):
        """Шторка сравнения двух дней темы NASA. Левая часть по
        умолчанию - тот же день год назад (themes.compare_day), правая -
        день шкалы времени. Поле прогноза GFS шторки не получает. Без
        темы при исторических картах - шторка карт двух лет."""
        if not (getattr(self, "theme_key", "") and self._theme_on()):
            if self._compare_at is not None \
                    or "compare" in getattr(self, "gibs_loaders", {}):
                # Шторка темы осталась от снятой темы.
                self._compare_at = None
                self._compare_shown = None
                self.view.swipe = None
                self.swipe_bar.set_shown(False)
                self._set_gibs("compare", False)
                on = False
            if on and self._map_moments():
                self._map_compare_start()
            else:
                self._map_compare_off()
            self.timebar.set_compare(self.timebar.compare.isVisibleTo(
                self.timebar), self._map_compare_at is not None)
            return
        intervals = self._theme_domains.get(self.theme_key) \
            if on and self._theme_on() \
            and not themes.is_weather(self.theme_key) else None
        if on and intervals:
            before = events.pre_day(self._event_items) \
                if self.theme_key == themes.EVENTS \
                and self._event_ready() else None
            if self._compare_at is None:
                # У снимков события слева - снимки до события.
                self._compare_at = themes.moment(before or themes.compare_day(
                    intervals, self.theme_moment()))
            self.view.swipe = self.swipe_bar.share
            self.swipe_bar.set_shown(True)
            self._apply_theme()
        elif self._compare_at is not None \
                or "compare" in getattr(self, "gibs_loaders", {}):
            self._compare_at = None
            self._compare_shown = None
            self.view.swipe = None
            self.swipe_bar.set_shown(False)
            self._set_gibs("compare", False)
        self.timebar.set_compare(self.timebar.compare.isVisibleTo(
            self.timebar), self._compare_at is not None)

    def _apply_compare(self, theme, intervals, day):
        """День левой части шторки и её слой вида."""
        if self._compare_at is None:
            return
        left = themes.pick_day(intervals, self._compare_at)
        self.swipe_bar.set_days(left, day)
        if (theme.key, left) == self._compare_shown:
            return
        keep = self._compare_shown is not None \
            and self._compare_shown[0] == theme.key
        self._compare_shown = (theme.key, left)
        if theme.key == themes.EVENTS:
            self._event_layer("compare", left, keep)
            return
        source = basemap.Source(theme.name, theme.url(left), theme.level,
                                theme.attribution, builtin=True,
                                missing=(404,))
        self.view.gibs["compare"].max_level = theme.level
        self._set_gibs("compare", True, (source, prepare_theme(theme.key)),
                       keep=keep)

    def _compare_step(self, delta):
        """Шаг дня левой части шторки по ряду темы."""
        if self._map_compare_at is not None:
            self._map_compare_step(delta)
            return
        intervals = self._theme_domains.get(self.theme_key)
        if self._compare_at is None or not intervals:
            return
        day = themes.step_day(
            intervals, themes.pick_day(intervals, self._compare_at), delta)
        if day is not None:
            self._compare_at = themes.moment(day)
            self._apply_theme()

    def _swipe_moved(self, share):
        self.view.swipe = share
        self.view.update()

    # Архив снимков Esri Wayback (core/wayback.py): выпуски - ряд дат
    # темы, шаги шкалы - выпуски, где снимок в середине вида менялся.

    def _wayback_config(self, data):
        """Список выпусков пришёл. Ряд дат - все выпуски, пока цепочка
        изменений в середине вида не готова."""
        try:
            releases = wayback.parse_config(bytes(data))
        except (ValueError, UnicodeDecodeError) as problem:
            journal.note("wayback config: {}".format(problem))
            releases = []
        self._wayback_releases = releases
        themes.BY_KEY[themes.WAYBACK].releases = wayback.by_day(releases)
        self._wayback_tile = None
        self._theme_domains[themes.WAYBACK] = wayback.intervals(releases)
        self._wayback_view()

    def _wayback_view(self):
        """Вид сдвинулся: изменения ищутся заново, когда тайл поиска
        в середине вида сменился и вид постоял WAYBACK_PAUSE."""
        if getattr(self, "theme_key", "") != themes.WAYBACK \
                or not self._theme_on() \
                or not getattr(self, "_wayback_releases", None):
            return
        if getattr(self, "_wayback_timer", None) is None:
            self._wayback_timer = QTimer(self)
            self._wayback_timer.setSingleShot(True)
            self._wayback_timer.timeout.connect(self._wayback_search)
        if self._wayback_target() != getattr(self, "_wayback_tile", None):
            self._wayback_timer.start(WAYBACK_PAUSE)

    def _wayback_target(self):
        """Тайл поиска (z, x, y) под точкой взгляда."""
        pose = self.view.navigator.pose
        width, _ = ground_size(pose.distance, self.view.camera.fov_y,
                               self.view.camera.aspect)
        z = wayback.search_level(width)
        return (z,) + wayback.tile_of(pose.lat, pose.lon, z)

    def _wayback_search(self):
        """Цепочка изменений: новейший выпуск, выпуск его тайла, выпуск
        старше него и так далее, запрос на изменение."""
        if getattr(self, "theme_key", "") != themes.WAYBACK \
                or not self._theme_on():
            return
        target = self._wayback_target()
        if target == getattr(self, "_wayback_tile", None):
            return
        self._wayback_abort()
        self._wayback_tile = target
        self._wayback_chain = []
        self._wayback_send(self._wayback_releases[-1])

    def _wayback_send(self, release):
        target = self._wayback_tile
        self._wayback_reply = fetch_bytes(
            wayback.tilemap_url(release.number, *target),
            lambda data, error, target=target, number=release.number:
            self._wayback_arrived(target, number, data, error))

    def _wayback_arrived(self, target, number, data, error):
        if target != getattr(self, "_wayback_tile", None) \
                or getattr(self, "_wayback_reply", None) is None:
            return  # ответ снятого или прежнего поиска
        self._wayback_reply = None
        effective = None
        if data is not None:
            try:
                effective = wayback.parse_tilemap(bytes(data), number)
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
                data = None
        if data is None:
            # Без ответа ряд остаётся всеми выпусками.
            journal.note("wayback tilemap {}: {}".format(number, error))
            self._wayback_done(None)
            return
        if effective is not None:
            self._wayback_chain.append(effective)
            older = wayback.changes_next(self._wayback_releases, effective)
            if older is not None:
                self._wayback_send(older)
                return
        self._wayback_done(self._wayback_chain)

    def _wayback_done(self, chain):
        """Ряд дат темы - выпуски с изменениями, без них - все."""
        numbers = set(chain or ())
        found = [r for r in self._wayback_releases if r.number in numbers] \
            or self._wayback_releases
        self._theme_domains[themes.WAYBACK] = wayback.intervals(found)
        self._update_timebar()
        self._apply_theme()

    def _wayback_abort(self):
        reply = getattr(self, "_wayback_reply", None)
        self._wayback_reply = None
        if reply is not None:
            reply.abort()

    def _wayback_stop(self):
        """Тема снята: поиск изменений снимается."""
        timer = getattr(self, "_wayback_timer", None)
        if timer is not None:
            timer.stop()
        self._wayback_abort()
        self._wayback_tile = None

    def wayback_changes(self):
        """Даты выпусков в ряду темы Wayback - для шагов проверки."""
        return themes.days(self._theme_domains.get(themes.WAYBACK) or [])

    def _ask_wayback(self, lat, lon):
        """Сведения о снимке выпуска под щелчком: дата съёмки, источник,
        разрешение."""
        self._wayback_meta = None
        reply = getattr(self, "_wayback_meta_reply", None)
        self._wayback_meta_reply = None
        if reply is not None:
            reply.abort()
        if getattr(self, "theme_key", "") != themes.WAYBACK \
                or not self._theme_on() or not self.theme_day:
            return
        release = themes.BY_KEY[themes.WAYBACK].release(self.theme_day)
        pose = self.view.navigator.pose
        width, _ = ground_size(pose.distance, self.view.camera.fov_y,
                               self.view.camera.aspect)
        url = wayback.metadata_url(release, lat, lon,
                                   min(link_zoom(lat, width),
                                       wayback.MAX_LEVEL))
        if url is None:
            return
        point = (lat, lon)
        self._wayback_meta = (point, release, None, "")
        self._wayback_meta_reply = fetch_bytes(
            url, lambda data, error: self._wayback_meta_arrived(
                point, release, data, error))

    def _wayback_meta_arrived(self, point, release, data, error):
        state = getattr(self, "_wayback_meta", None)
        if state is None or state[0] != point:
            return
        self._wayback_meta_reply = None
        info = None
        if data is not None:
            try:
                info = wayback.parse_metadata(bytes(data)) or {}
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        self._wayback_meta = (point, release, info, error or "")
        self._refresh_identified()

    def _identify_wayback(self):
        """Группа «Архив снимков Esri Wayback» окна «Объекты»."""
        state = getattr(self, "_wayback_meta", None)
        if state is None:
            return []
        _, release, info, error = state
        title = tr("Выпуск {day}", day=release.day.isoformat())
        if info is None and not error:
            values = [(tr("Сведения"), tr("Запрос к Esri…"))]
        elif info is None:
            values = [(tr("Ошибка"), error)]
        elif not info:
            values = [(tr("Сведения"), tr("Нет сведений о снимке"))]
        else:
            values = []
            for label, key in ((tr("Дата съёмки"), "date"),
                               (tr("Источник"), "provider"),
                               (tr("Съёмочная система"), "sensor")):
                if info[key]:
                    values.append((label, info[key]))
            for label, key in ((tr("Разрешение, м"), "resolution"),
                               (tr("Точность, м"), "accuracy")):
                if info[key] is not None:
                    values.append((label, "{:g}".format(info[key])))
        return [(Group(tr("Архив снимков Esri Wayback")),
                 [(title, values, None)])]

    def sun_time(self):
        """Момент для солнца, секунды UTC: конец промежутка открытой
        шкалы времени, иначе часы компьютера."""
        if self.timebar.shown():
            hi = self.timebar.range()[1]
            if math.isfinite(hi):
                return hi
        return sun.now()

    def _update_sun(self):
        """Направление на солнце в вид. Пока строка «Солнце» включена
        и шкала закрыта, солнце идёт по часам раз в SUN_PERIOD."""
        # Шкала времени бывает раньше строк раздела «Слои».
        on = getattr(self, "extras", {}).get("sun", False) \
            and self.planet.earth
        self.view.sun = sun.direction(self.sun_time()) if on else None
        # Огни городов - вместе с солнцем, загрузчик - при смене.
        if on != getattr(self, "_lights_on", False):
            self._lights_on = on
            self._set_gibs("lights", on, cache=True)
        timer = getattr(self, "sun_timer", None)
        if timer is None:
            timer = self.sun_timer = QTimer(self)
            timer.setInterval(SUN_PERIOD)
            timer.timeout.connect(self._update_sun)
        if on and not self.timebar.shown():
            timer.start()
        else:
            timer.stop()
        self.view.update()

    def _overture_on(self):
        """Здания - из архива Overture Maps (окно «Источники данных»)."""
        return QgsSettings().value(datasources.BUILDINGS_KEY, "") \
            == datasources.OVERTURE

    def _set_buildings(self, on):
        """3D-здания: загрузчик тайлов векторной основы, архива Overture
        Maps или никакого. Адрес тайлов основы даёт TileJSON, адрес
        архива - каталог STAC Overture, до их прихода здания ждут."""
        old = self.buildings_loader
        if old is not None:
            old.abort()
            old.deleteLater()
        self.buildings_loader = None
        overture = on and self._overture_on()
        if overture:
            url = getattr(self, "_overture_url", None)
            if url is not None:
                self.buildings_loader = OvertureTiles(url, parent=self)
                self.buildings_loader.loaded.connect(
                    lambda key, found, extra: self.view.add_buildings(
                        key, found))
            elif getattr(self, "_overture_reply", None) is None:
                self._overture_reply = fetch_json(
                    datasources.OVERTURE_STAC, self._overture_catalog,
                    prefer_cache=False)
        elif on and self._ofm_source is not None:
            self.buildings_loader = TileLoader(self._ofm_source, parent=self,
                                               decode=buildings_decoder)
            self.buildings_loader.loaded.connect(
                lambda key, found, extra: self.view.add_buildings(key, found))
        elif on and self._tilejson is None:
            self._tilejson = fetch_json(self._vector_choice(),
                                        self._tilejson_done)
        self.view.set_buildings(on, self.buildings_loader,
                                "overture" if overture else "vector")
        self._show_attribution()

    def _overture_catalog(self, data, error):
        """Пришёл каталог STAC Overture: адрес архива последнего выпуска.
        Без ответа - выпуск по умолчанию."""
        self._overture_reply = None
        if error:
            journal.note("overture catalog: {}".format(error))
        self._overture_url = release_url(data)
        if self.extras.get("buildings") and self.buildings_loader is None:
            self._set_buildings(True)

    def _update_layer_labels(self, force=False):
        """Подписи слоёв проекта, которые сейчас на глобусе. Слои
        читаются заново, только когда вид сдвинулся на долю окна."""
        pose = self.view.navigator.pose
        width = 2.0 * pose.distance * math.tan(
            math.radians(self.view.camera.fov_y) / 2.0)
        # Слои проекта - земные, на другом теле подписей нет.
        layers = (self._applied_layers or []) if self.planet.earth else []
        self.layer_labels.time_range = self._layer_range()
        self.layer_labels.update(layers, pose.lat,
                                 pose.lon, width, force)

    def _show_layer_labels(self):
        self.view.layer_marks = self.layer_labels.marks
        self.view.update()

    def _update_grid(self):
        """Сетка на глобусе. Строится заново, только когда меняется
        шаг или точка взгляда уходит на шаг, а не каждый кадр."""
        if not self.extras.get("grid"):
            if self.grid_shapes or self.view.grid_marks:
                self.grid_shapes = []
                self.view.grid_marks = []
                self._grid_key = None
                self._refresh_shapes()
            return
        pose = self.view.navigator.pose
        width = 2.0 * pose.distance * math.tan(
            math.radians(self.view.camera.fov_y) / 2.0)
        key = graticule.key(pose.lat, pose.lon, width)
        if key == self._grid_key:
            return
        self._grid_key = key
        step, found = graticule.lines(pose.lat, pose.lon, width)
        self.grid_shapes = [Shape("line", points, color=GRID_COLOR,
                                  width=GRID_WIDTH)
                            for _, _, points in found]
        self.grid_shapes += [
            Shape("line", points, color=CIRCLE_COLOR, width=GRID_WIDTH)
            for _, _, points in graticule.circles(pose.lat, pose.lon,
                                                  width)]
        marks = []
        for n, (lat, lon, kind, value) in enumerate(
                graticule.labels(pose.lat, pose.lon, width)):
            marks.append(MarkPlace(-100000 - n, self._grid_text(
                kind, value, step), "grid", 1, lat,
                graticule.normal_lon(lon)))
        names = self._circle_names()
        for n, (lat, lon, name) in enumerate(
                graticule.circle_labels(pose.lat, pose.lon, width)):
            marks.append(MarkPlace(-200000 - n, names[name], "circle", 1,
                                   lat, graticule.normal_lon(lon)))
        self.view.grid_marks = marks
        self._refresh_shapes()

    @staticmethod
    def _circle_names():
        return {"equator": tr("Экватор"),
                "cancer": tr("Тропик Рака"),
                "capricorn": tr("Тропик Козерога"),
                "arctic": tr("Северный полярный круг"),
                "antarctic": tr("Южный полярный круг")}

    def _grid_text(self, kind, value, step):
        """Подпись линии сетки с полушарием."""
        angle = graticule.angle_text(value, step)
        if kind == "lat":
            if abs(value) < 1e-9:
                return angle
            return tr("{angle} с. ш.", angle=angle) if value > 0 \
                else tr("{angle} ю. ш.", angle=angle)
        value = graticule.normal_lon(value)
        if abs(value) < 1e-9 or abs(abs(value) - 180.0) < 1e-9:
            return graticule.angle_text(abs(value), step)
        return tr("{angle} в. д.", angle=angle) if value > 0 \
            else tr("{angle} з. д.", angle=angle)

    def _load_sky(self):
        """Картинка неба с Млечным путём, один раз за окно. Запрос идёт
        тем же загрузчиком, что и тайлы, картинка раскодируется в его
        потоке. Второй раз она берётся из кэша QGIS."""
        if self.sky_loader is not None:
            return
        source = basemap.Source("NASA SVS", stars.SKY_URL, 0,
                                builtin=True)
        self.sky_loader = TileLoader(source, parent=self)
        self.sky_loader.loaded.connect(
            lambda key, rgba, extra: self.view.set_sky_image(rgba))
        self.sky_loader.want((0, 0, 0), 1.0)

    def _surface_source(self):
        """Тайлы высот тела для уклона: (источник, пол высот) или None,
        если высот у тела нет."""
        if self.planet.earth:
            return basemap.Source("Terrarium", self._terrain_choice()[0],
                                  TERRAIN_MAX, builtin=True), \
                self._earth_floor(), self._height_entries()
        if self.planet.terrain is None:
            return None
        name, url, level, _ = self.planet.terrain
        return basemap.Source(name, url, level, builtin=True), None, ()

    def _set_surface(self):
        """Слой уклона или экспозиции по строкам раздела «Слои» и телу.
        Тайлы высот берутся через кэш QGIS, слой считается из них
        в рабочем потоке (core/slope.py)."""
        mode = next((k for k in SURFACE_EXTRAS if self.extras.get(k)),
                    None)
        found = self._surface_source()
        self._set_contours(found)
        # Тот же слой вида занимает квадрат окна «Уклон и экспозиция»
        # (ui/relief.py): включённая строка его снимает, без строки он
        # возвращается.
        local = getattr(self, "relief", None)
        if mode is not None and local is not None:
            local.clear(quiet=True)
        if mode is None or found is None or self.view.sky_view is not None:
            self._set_gibs("slope", False)
            self.slope_legend.hide()
            if local is not None:
                local.show()
            return
        source, floor, insets = found
        self.view.gibs["slope"].max_level = source.max_level
        encoding = self._terrain_choice()[1] if self.planet.earth \
            else "terrarium"
        self._set_gibs("slope", True, (source, slope_prepare(
            mode, floor, ellipsoid.A, insets, encoding)), cache=True)
        self.slope_legend.set_mode(mode)
        self.slope_legend.show()
        self._place_attribution()

    def _set_contours(self, found):
        """Слой горизонталей по строке «Горизонтали» и телу, независимо
        от уклона. found - источник высот тела, как у уклона."""
        if not self.extras.get("contours") or found is None \
                or self.view.sky_view is not None:
            self._set_gibs("contours", False)
            self.contour_legend.hide()
            return
        # Жёлтые линии на снимке, коричневые на карте.
        self._contour_palette = self._palette_for(self.source)
        self.contour_legend.export = \
            self.contour_export.view_contours if self.planet.earth else None
        self.contour_legend.show()
        self._update_contour_legend()
        source, floor, insets = found
        levels = None
        if self.planet.earth:
            # Глубже уровня съёмки - по предку (ContourSource, upsample),
            # в открытом море - по уровню глубин. Свой источник высот
            # бывает подробнее, у него - уровень 15.
            land = CONTOUR_SOURCE if source.url == datasources.TERRAIN_URL \
                else TERRAIN_MAX
            source = ContourSource(source.url, self.view.store, land)
            levels = source.level_of
            deepest = CONTOUR_LEVEL
        else:
            # У тел высоты только до уровня тела (5). Глубже тайл
            # горизонталей - предок, сглаженный и пересчитанный
            # кубически, как на Земле глубже уровня съёмки. Иначе вблизи
            # линии растягивались вместе с тайлом уровня 5. Просьба
            # автора от 11 октября 2026 года.
            top = source.max_level
            source = DeepSource(source.name, source.url, top,
                                source.attribution, missing=source.missing)

            def levels(key, top=top):
                return min(key[0], top)
            deepest = min(CONTOUR_LEVEL, top + BODY_CONTOUR_DEEPER)
        self.view.gibs["contours"].max_level = deepest
        encoding = self._terrain_choice()[1] if self.planet.earth \
            else "terrarium"
        self._set_gibs("contours", True, (source, contours_prepare(
            floor, ellipsoid.A, insets, encoding, digit_glyphs(), levels,
            self._contour_palette, self.view.store,
            sea=self.planet.earth)), cache=True)

    def _palette_for(self, source):
        """Цвета горизонталей по подложке: imagery - снимок, map -
        карта (core.contours.is_imagery)."""
        imagery = contour_is_imagery(source.name, source.url,
                                     builtin_body=not self.planet.earth)
        return "imagery" if imagery else "map"

    def _update_contour_legend(self):
        """Сечение горизонталей в середине вида на шкале."""
        if self.contour_legend.isHidden():
            return
        pose = self.view.navigator.pose
        camera = self.view.camera
        self.contour_legend.set_step(contour_view_step(
            pose.distance, pose.lat, math.radians(camera.fov_y),
            self.view.height() * self.view.devicePixelRatioF(),
            ellipsoid.A, self.view.gibs["contours"].max_level),
            self._contour_palette)

    def _set_gibs(self, name, on, made=None, cache=False, keep=False):
        """Слой NASA GIBS вида - облака, море или суша: новый загрузчик
        или никакого. Ответы GIBS запрещают кэш, поэтому мимо него.
        made - (источник, подготовка) своего слоя, как у уклона."""
        old = self.gibs_loaders.pop(name, None)
        if old is not None:
            old.abort()
            old.deleteLater()
        loader = None
        if on:
            source, prepare = made or gibs_source(name)
            loader = TileLoader(source, parent=self, prepare=prepare,
                                size=TILE_SIZE, cache=cache)
            loader.loaded.connect(
                lambda key, rgba, levels, name=name:
                self.view.add_gibs(name, key, levels))
            self.gibs_loaders[name] = loader
        self.view.set_gibs(name, on, loader, keep=keep)
        self._show_attribution()

    def set_relief(self, on):
        """Включить или выключить рельеф, сразу, флажком панели «Слои»."""
        self._relief = bool(on)
        QgsSettings().setValue(RELIEF_KEY, self._relief)
        self.panel.set_geo(self._groups, self._relief)
        self.view.set_relief(self._relief_target())
        self._update_water()
        self.subsurface.relief_changed()
        self._place_quakes()
        self._place_fires()
        self._place_deposits()
        if self._relief and self.terrain_loader is not None:
            self.terrain_loader.want((0, 0, 0), 1.0)
        self._sync_properties()
        self._show_attribution()
        self._mark_dirty(self._pending())

    def set_relief_scale(self, scale):
        """Вертикальный масштаб рельефа."""
        self._scale = min(max(float(scale), SCALE_RANGE[0]), SCALE_RANGE[1])
        QgsSettings().setValue(SCALE_KEY, self._scale)
        self._changed()

    def set_layer_shown(self, layer_id, on):
        """Отметка слоя проекта в списке глобуса.

        В режиме «как на карте QGIS» отметка включает и выключает слой
        в дереве слоёв QGIS, глобус следует за деревом.
        """
        if self.follow:
            set_visible_on_map(layer_id, on)
            return
        if on:
            self._shown.add(layer_id)
        else:
            self._shown.discard(layer_id)
        write_shown(self._shown)
        self._changed()

    def _relief_target(self):
        """Масштаб рельефа. У тела без высот рельефа нет. В палеогеографии
        рельеф выключен: нынешние горы на берегах прошлого лишние, решение
        автора от 4 октября 2026 года. Настройка рельефа не меняется."""
        if not self.planet.earth and self.planet.terrain is None:
            return 0.0
        if getattr(self, "extras", {}).get("paleo") and self._paleo_on():
            return 0.0
        if self._geoid_on():
            return self.geoid_scale()
        return self._scale if self._relief else 0.0

    def _start_terrain(self, source, floor):
        """Загрузчик высот источника source или никакого (None).
        floor - нижний предел высот, core.terrain.decode."""
        old = self.terrain_loader
        if old is not None:
            old.abort()
            old.deleteLater()
        self.terrain_errors.clear()
        self.terrain_loader = None
        if source is not None:
            # Высоты Земли - с врезками своего рельефа и тайлами глубже
            # уровня 15 внутри их рамок (ui/inset.py).
            earth = isinstance(source, DeepSource)
            insets = self._height_entries() if earth else ()
            encoding = self._terrain_choice()[1] if earth else "terrarium"
            self.view.store.deep = [entry.box() for entry in insets
                                    if not isinstance(entry, DemSource)]
            self.terrain_loader = TileLoader(
                source, parent=self,
                prepare=terrain_prepare(insets, floor, encoding))
            self.terrain_loader.loaded.connect(self._heights)
            self.terrain_loader.failed.connect(
                self.terrain_errors.__setitem__)
            if self._relief or self._geoid_on():
                self.terrain_loader.want((0, 0, 0), 1.0)
        self.view.terrain_loader = self.terrain_loader
