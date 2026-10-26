# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки чрезвычайных событий Vantor и Planet темой архива снимков.

Часть окна глобуса GlobeWindow (ui/window.py). Ядро - core/events.py,
загрузка и окно - ui/events.py. Снимки события - тема EVENTS: ряд дат -
дни снимков, правый бегунок шкалы - день «после», шторка темы - день
«до» (последний день снимков до события), как у тем NASA и Wayback.
"""
import math
import time

from ...core import events, themes
from ...core.flight import fit_view
from ...core.sync import ground_size, view_box
from ...i18n import tr
from ..events import EventCatalog, EventItems, EventTiles, EventsDialog
from ..export import add_raster

# «В проект QGIS…»: снимков дня в рамке вида не больше. Каждый
# открывается QGIS по сети, это секунда на снимок. Выбор помощника.
EXPORT_MAX = 12


class DisastersMixin:
    """Часть окна глобуса GlobeWindow."""

    def open_events(self):
        """Окно «Снимки событий», одно на глобус. Список событий
        загружается при первом открытии."""
        if getattr(self, "events_dialog", None) is None:
            self.event_catalog = EventCatalog(self)
            self.events_dialog = EventsDialog(self.event_catalog, self)
            self.events_dialog.chosen.connect(self.show_event)
            self.events_dialog.cleared.connect(self.clear_event)
        self.event_catalog.load()
        self.events_dialog.show()
        self.events_dialog.raise_()
        self.events_dialog.activateWindow()
        event = getattr(self, "_event", None)
        if event is not None:
            self.events_dialog.select(event.key)
        return self.events_dialog

    def show_event(self, event):
        """Снимки события на глобус: обход его каталогов, перелёт, тема,
        шкала на последнем дне снимков, шторка до и после."""
        self._event_stop()
        self._event = event
        self._event_items = None
        self._event_state(tr("Загрузка снимков события «{title}»…",
                             title=event.title))
        if event.box is not None:
            self._fly_event(event.box)
        crawl = EventItems(event, self)
        crawl.progress.connect(lambda count: self._event_state(tr(
            "Загрузка снимков события: документов каталога {count}",
            count=count)))
        crawl.done.connect(self._event_items_done)
        self._event_crawl = crawl
        crawl.start()

    def _event_items_done(self, items, error):
        self._event_crawl = None
        event = getattr(self, "_event", None)
        if event is None:
            return
        if not items:
            self._event_state(tr(
                "У события нет снимков, которые глобус может показать. "
                "{error}", error=error).strip())
            return
        self._event_items = items
        theme = themes.BY_KEY[themes.EVENTS]
        theme.level = events.max_level(items)
        theme.name = events.NAMES.get(event.source, theme.name)
        theme.attribution = events.CREDITS.get(event.source,
                                               theme.attribution)
        self._theme_domains[themes.EVENTS] = events.intervals(items)
        if getattr(self, "events_dialog", None) is not None:
            self.events_dialog.set_count(event.key, len(items))
        self._event_state(tr(
            "Снимков: {count}, дней съёмки: {days}. Шкала времени выбирает "
            "день, шторка сравнивает снимки до и после.",
            count=len(items),
            days=len(self._theme_domains[themes.EVENTS])))
        if event.box is None:
            self._fly_event(events.box_of(items))
        # Шторка прежнего события снимается: у нового снимков «до» может
        # не быть. Шкала встаёт на последний день снимков события.
        self.set_compare(False)
        self._theme_shown = None
        self._compare_shown = None
        self._compare_at = None
        if self.theme_key != themes.EVENTS:
            self.set_theme(themes.EVENTS)
        self._theme_open_time = True
        self._show_theme()
        before = events.pre_day(items)
        if before is not None and before < events.post_day(items):
            self._compare_at = themes.moment(before)
            self.set_compare(True)

    def clear_event(self):
        """Снимки события с глобуса."""
        self._event_stop()
        self._event = None
        self._event_items = None
        self._theme_domains.pop(themes.EVENTS, None)
        if self.theme_key == themes.EVENTS:
            self.set_theme("")
        self._event_state("")

    def _event_stop(self):
        crawl = getattr(self, "_event_crawl", None)
        self._event_crawl = None
        if crawl is not None:
            crawl.abort()
            crawl.deleteLater()

    def _event_state(self, text):
        dialog = getattr(self, "events_dialog", None)
        if dialog is not None:
            dialog.set_status(text)
        if text:
            self.message = (text, time.monotonic())
            self._show_state()

    def _fly_event(self, box):
        camera = self.view.camera
        lat, lon, distance = fit_view(*box, camera.fov_y, camera.aspect)
        if all(math.isfinite(v) for v in (lat, lon, distance)):
            self._fly_to(lat, lon, distance)

    def _event_ready(self):
        """Снимки события пришли, тему можно показать."""
        return bool(getattr(self, "_event_items", None))

    def _event_layer(self, name, day, keep):
        """Слой вида name («theme» или «compare») - снимки события на
        день day. Прежние картинки видны, пока их не заменят новые."""
        if not self._event_ready():
            return
        tiles = EventTiles(self._event_items, day, parent=self)
        tiles.loaded.connect(
            lambda key, rgba, levels, name=name:
            self.view.add_gibs(name, key, levels))
        old = self.gibs_loaders.pop(name, None)
        if old is not None:
            old.abort()
            old.deleteLater()
        self.gibs_loaders[name] = tiles
        self.view.gibs[name].max_level = themes.BY_KEY[themes.EVENTS].level
        self.view.set_gibs(name, True, tiles, keep=keep)
        self._show_attribution()

    def event_title(self):
        """Название показанного события или None."""
        event = getattr(self, "_event", None)
        return event.title if event is not None else None

    def _export_events(self):
        """«В проект QGIS…» темы снимков событий: снимки дня в рамке вида
        растрами по сети, файлы не пишутся. Количество слоёв или None."""
        items = getattr(self, "_event_items", None)
        if not items or not self.theme_day:
            return None
        pose = self.view.navigator.pose
        width, height = ground_size(pose.distance, self.view.camera.fov_y,
                                    self.view.camera.aspect)
        box = view_box(pose.lat, pose.lon, width, height)
        found = [item for item in events.shown(items, self.theme_day)
                 if events.touches(item.box, box)][:EXPORT_MAX]
        count = 0
        for item in reversed(found):
            title = "{} {} {}".format(item.day, item.platform, item.ident)
            rights = events.CREDITS.get(item.source, ("",))[0]
            if add_raster("/vsicurl/" + item.href, title.strip(),
                          rights=rights,
                          group=tr("PlanetX - снимки событий"),
                          copy=True) is not None:
                count += 1
        return count or None
