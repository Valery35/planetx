# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки чрезвычайных событий Vantor и Planet: список событий, снимки
события, тайлы темы и окно «Снимки событий».

Ядро - core/events.py. Каталоги STAC приходят менеджером сети модуля
в главном потоке, части снимков COG - тоже им, через мост net/ranges.py
из рабочих потоков. Тайл темы собирается в рабочем потоке: тайлы
снимка раскодирует читатель TIFF в Qt, LZW и JPEG на Python шли бы
секундами. QImage в рабочем потоке допустим.
"""
import json
import threading
from collections import OrderedDict

from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout,
                                 QHeaderView, QLabel, QPushButton,
                                 QTextBrowser, QTreeWidget, QTreeWidgetItem,
                                 QVBoxLayout)

from .. import journal
from ..core import cog, events
from ..core.mipmap import mip_chain
from ..i18n import tr
from ..net import ranges
from ..net.overlay import fetch_bytes
from ..qt_compat import enum
from .overlays import image_rgba
from .threadtiles import ThreadTiles

PARALLEL = 6  # документов каталога в работе сразу
MAX_DOCS = 1500  # документов одного события не больше
WORKERS = 8  # рабочих потоков тайлов: поток больше ждёт сеть, чем считает
IN_FLIGHT = 16  # тайлов в работе сразу
COGS_KEPT = 96  # открытых снимков в памяти
TILE_SIDE = 4096  # наибольшая сторона тайла снимка для раскодирования

_COGS = OrderedDict()  # адрес: core.cog.Cog или None - не читается
_COGS_LOCK = threading.Lock()
_OPENING = {}  # адрес: замок открытия, заголовок читается один раз


def decode(blob):
    """Тайл снимка - маленький TIFF (core.cog.tiff_bytes) - в RGBA."""
    return image_rgba(blob, side=TILE_SIDE)


def open_cog(href):
    """Снимок COG по адресу: из памяти или открыть. None - файл не
    разбирается. Ошибки сети идут вызывающему, снимок откроется
    в следующий раз."""
    with _COGS_LOCK:
        if href in _COGS:
            _COGS.move_to_end(href)
            return _COGS[href]
        lock = _OPENING.setdefault(href, threading.Lock())
    with lock:
        with _COGS_LOCK:
            if href in _COGS:
                return _COGS[href]
        try:
            found = cog.Cog(lambda start, length: ranges.fetch(
                href, start, length))
        except (cog.CogError, ranges.Missing) as error:
            # Файла нет или он не разбирается - снимок пропускается.
            journal.note("event image {}: {}".format(href, error))
            found = None
        with _COGS_LOCK:
            _COGS[href] = found
            _OPENING.pop(href, None)
            while len(_COGS) > COGS_KEPT:
                _COGS.popitem(last=False)
        return found


class EventCatalog(QObject):
    """Список событий обоих каталогов. Сигнал changed - пришло событие
    или ошибка."""

    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.events = {}  # ключ: core.events.Event
        self.errors = []
        self.replies = {}
        self.loaded = False

    def load(self):
        """Корневые каталоги и документы событий, один раз за сеанс."""
        if self.loaded or self.replies:
            return
        self.errors = []
        for source, url in events.ROOTS.items():
            self._get(url, lambda doc, s=source, u=url:
                      self._root(s, u, doc), prefer_cache=False)

    def busy(self):
        return bool(self.replies)

    def ordered(self):
        """События новые первыми."""
        return sorted(self.events.values(),
                      key=lambda e: (e.day, e.title), reverse=True)

    def _get(self, url, done, prefer_cache=True):
        def arrived(data, error):
            self.replies.pop(url, None)
            doc = None
            if data is not None:
                try:
                    doc = json.loads(data.decode("utf-8"))
                except ValueError as problem:
                    error = str(problem)
            if doc is None:
                self.errors.append(error or "?")
                journal.note("events catalog {}: {}".format(url, error))
            else:
                done(doc)
            if not self.replies:
                self.loaded = True
            self.changed.emit()
        self.replies[url] = fetch_bytes(url, arrived,
                                        prefer_cache=prefer_cache)

    def _root(self, source, url, doc):
        for href, title in events.parse_events(doc, url):
            self._get(href, lambda d, h=href, t=title, s=source:
                      self._event(s, h, t, d))

    def _event(self, source, url, title, doc):
        event = events.parse_event(doc, url, source)
        if event is None:
            return
        if title and event.title == event.key.split("/", 1)[1].replace(
                "-", " ").replace("_", " "):
            event.title = title
        self.events[event.key] = event

    def abort(self):
        replies, self.replies = self.replies, {}
        for reply in replies.values():
            reply.abort()


class EventItems(QObject):
    """Снимки одного события обходом его каталогов. Сигналы progress -
    документов пришло, done - список core.events.Item и текст ошибки."""

    progress = pyqtSignal(int)
    done = pyqtSignal(object, str)

    def __init__(self, event, parent=None):
        super().__init__(parent)
        self.target = event
        self.queue = [(event.url, events.phase_of(event.url), 0)]
        self.seen = {event.url}
        self.replies = {}
        self.items = []
        self.count = 0
        self.error = ""
        self.stopped = False

    def start(self):
        self._pump()

    def _pump(self):
        while self.queue and len(self.replies) < PARALLEL \
                and self.count + len(self.replies) < MAX_DOCS:
            url, phase, depth = self.queue.pop(0)
            self.replies[url] = fetch_bytes(
                url, lambda data, error, u=url, p=phase, d=depth:
                self._arrived(u, p, d, data, error))
        if not self.replies and not self.stopped:
            self.stopped = True
            self.done.emit(self.items, self.error)

    def _arrived(self, url, phase, depth, data, error):
        if self.replies.pop(url, None) is None or self.stopped:
            return
        self.count += 1
        doc = None
        if data is not None:
            try:
                doc = json.loads(data.decode("utf-8"))
            except ValueError as problem:
                error = str(problem)
        if doc is None:
            self.error = error or "?"
        elif doc.get("type") == "Feature":
            item = events.parse_item(doc, url, self.target.source, phase)
            if item is not None:
                self.items.append(item)
        elif depth < events.MAX_DEPTH:
            for _, href in events.children(doc, url):
                if href not in self.seen:
                    self.seen.add(href)
                    self.queue.append((href, events.phase_of(href) or phase,
                                       depth + 1))
        self.progress.emit(self.count)
        self._pump()

    def abort(self):
        self.stopped = True
        self.queue = []
        replies, self.replies = self.replies, {}
        for reply in replies.values():
            reply.abort()


class EventTiles(ThreadTiles):
    """Картинки тайлов темы из снимков события на день: загрузчик слоя
    вида (ui/threadtiles.py), сигнал loaded (ключ, картинка, уровни
    мипмапов)."""

    def __init__(self, items, day, parent=None):
        super().__init__(WORKERS, IN_FLIGHT, "event", parent)
        self.items = events.shown(items, day)
        self.day = day
        decode(cog.tiff_bytes(_WARM, [b"\0" * 4]))

    def work(self, key):
        rgba = events.paint(self.items, *key, open_cog, decode)
        return rgba, mip_chain(rgba)

class _Warm:
    """Тайл 1 × 1 RGBA без сжатия: первая расшифровка в главном потоке
    подгружает модуль TIFF Qt до рабочих потоков."""
    tile_w = tile_h = 1
    samples = 4
    compression = 1
    predictor = 1
    planar = 1
    keep = {338: (2,)}


_WARM = _Warm()


def event_text(event, count=None):
    """Описание события для окна: название, день, источник, описание."""
    lines = ["<b>{}</b>".format(_escape(event.title))]
    lines.append(_escape(" · ".join(part for part in (
        event.day, events.NAMES.get(event.source, "")) if part)))
    if count is not None:
        lines.append(tr("Снимков: {count}", count=count))
    if event.description:
        lines.append(_escape(event.description))
    return "<br>".join(lines)


def _escape(text):
    return (str(text).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;"))


class EventsDialog(QDialog):
    """Окно «Снимки событий»: список событий Vantor и Planet, описание
    выбранного, «Показать на глобусе» и «Убрать с глобуса». Сигналы
    chosen - core.events.Event, cleared."""

    chosen = pyqtSignal(object)
    cleared = pyqtSignal()

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self.catalog = catalog
        self.setWindowTitle(tr("Снимки событий"))
        layout = QVBoxLayout(self)
        intro = QLabel(tr(
            "Снимки землетрясений, наводнений, пожаров и ураганов из "
            "открытых каталогов Vantor и Planet. Шкала времени выбирает "
            "день снимков, шторка сравнивает снимки до и после события. "
            "Лицензия снимков CC BY-NC 4.0 - только некоммерческое "
            "использование."))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels([tr("Событие"), tr("Дата"),
                                   tr("Источник")])
        self.tree.setRootIsDecorated(False)
        header = self.tree.header()
        header.setSectionResizeMode(0, enum(QHeaderView, "ResizeMode",
                                            "Stretch"))
        header.setStretchLastSection(False)
        self.tree.itemSelectionChanged.connect(self._describe)
        self.tree.itemDoubleClicked.connect(lambda *_: self._show())
        layout.addWidget(self.tree, 2)
        self.details = QTextBrowser()
        self.details.setOpenExternalLinks(True)
        layout.addWidget(self.details, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.show_button = QPushButton(tr("Показать на глобусе"))
        self.show_button.clicked.connect(self._show)
        self.clear_button = QPushButton(tr("Убрать с глобуса"))
        self.clear_button.clicked.connect(self.cleared.emit)
        row.addWidget(self.show_button)
        row.addWidget(self.clear_button)
        row.addStretch(1)
        buttons = QDialogButtonBox(enum(QDialogButtonBox, "StandardButton",
                                        "Close"))
        buttons.rejected.connect(self.close)
        row.addWidget(buttons)
        layout.addLayout(row)
        self.resize(640, 560)
        catalog.changed.connect(self.refresh)
        self.counts = {}
        self.refresh()

    def refresh(self):
        current = self.current()
        keep = current.key if current is not None else None
        self.tree.clear()
        for event in self.catalog.ordered():
            item = QTreeWidgetItem([event.title, event.day,
                                    events.NAMES.get(event.source, "")])
            item.setData(0, enum(Qt, "ItemDataRole", "UserRole"), event.key)
            item.setToolTip(0, event.title)
            self.tree.addTopLevelItem(item)
            if event.key == keep:
                self.tree.setCurrentItem(item)
        if self.catalog.busy():
            self.set_status(tr("Загрузка списка событий…"))
        elif not self.catalog.events:
            self.set_status(tr("Список событий не загрузился: {error}",
                               error="; ".join(self.catalog.errors[:2])))
        elif not self.status.text():
            self.set_status(tr("Событий: {count}",
                               count=len(self.catalog.events)))
        self._describe()

    def current(self):
        item = self.tree.currentItem()
        if item is None:
            return None
        return self.catalog.events.get(
            item.data(0, enum(Qt, "ItemDataRole", "UserRole")))

    def select(self, key):
        for n in range(self.tree.topLevelItemCount()):
            item = self.tree.topLevelItem(n)
            if item.data(0, enum(Qt, "ItemDataRole", "UserRole")) == key:
                self.tree.setCurrentItem(item)
                return

    def set_status(self, text):
        self.status.setText(text)

    def set_count(self, key, count):
        self.counts[key] = count
        self._describe()

    def _describe(self):
        event = self.current()
        self.show_button.setEnabled(event is not None)
        if event is None:
            self.details.setHtml("")
            return
        self.details.setHtml(event_text(event, self.counts.get(event.key)))

    def _show(self):
        event = self.current()
        if event is not None:
            self.chosen.emit(event)
