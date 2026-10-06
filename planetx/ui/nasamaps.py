# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Карты NASA и погода»: витрина карт с превью.

Просьба автора от 7 октября 2026 года - «компактный красивый интерфейс
к картам NASA». Карта - тема NASA GIBS, поле прогноза GFS, пожары FIRMS
или температура суши и моря, включена одна из всех. Превью темы GIBS -
её тайл уровня 1 над Евразией на последний готовый день поверх тайла
подложки, у поля прогноза и пожаров - полоса цветов шкалы. Кнопки
групп сужают витрину, строка поиска ищет по названию. Окно немодальное,
одно на глобус, выбор делает окно глобуса (`GlobeWindow.set_theme`).
"""
import numpy as np
from qgis.PyQt.QtCore import QSize, Qt
from qgis.PyQt.QtGui import QColor, QIcon, QImage, QPainter, QPixmap
from qgis.PyQt.QtWidgets import (QButtonGroup, QDialog, QHBoxLayout, QLabel,
                                 QLineEdit, QListView, QListWidget,
                                 QListWidgetItem, QPushButton, QToolButton,
                                 QVBoxLayout)

from ..core import fires, temperature, themes, weather
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum, enum_int
from .themes import group_names, theme_names

THUMB = 104  # пикселей стороны превью
PARALLEL = 4  # запросов превью сразу
KEY_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
ALL = ""  # кнопка «Все» групп


def map_names():
    """Карта витрины: ключ - (название, подсказка)."""
    names = dict(theme_names())
    names[themes.FIRES] = (tr("Пожары"), tr(
        "Очаги пожаров за последние 24 часа по снимкам VIIRS спутника "
        "NOAA-20, сводка NASA FIRMS. Цвет и размер точки показывают "
        "мощность излучения."))
    names[themes.TEMPERATURE] = (tr("Температура поверхности"), tr(
        "Температура суши днём по MODIS за 8 суток и моря по GHRSST MUR "
        "за сутки, данные NASA GIBS."))
    return names


def ramp_image(colors, base=None):
    """Превью из полосы цветов шкалы поверх картинки подложки."""
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(40, 48, 60))
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    band = THUMB // 4
    count = max(len(colors), 1)
    for n, color in enumerate(colors):
        left = THUMB * n // count
        right = THUMB * (n + 1) // count
        painter.fillRect(left, THUMB - band, right - left, band,
                         QColor(*color[:3]))
    painter.end()
    return image


def tile_image(data, base=None, clear=()):
    """Превью из тайла темы поверх тайла подложки. Цвета clear -
    прозрачные классы темы."""
    image = QImage(THUMB, THUMB, enum(QImage, "Format", "Format_ARGB32"))
    image.fill(QColor(40, 48, 60))
    tile = QImage.fromData(data) if data else QImage()
    painter = QPainter(image)
    if base is not None:
        painter.drawImage(image.rect(), base)
    if not tile.isNull():
        if clear:
            tile = _cleared(tile, clear)
        painter.setOpacity(themes.OPACITY)
        painter.drawImage(image.rect(), tile)
    painter.end()
    return image


def _cleared(tile, clear):
    """Тайл, у которого пиксели цветов clear прозрачны."""
    rgba = enum(QImage, "Format", "Format_RGBA8888")
    tile = tile.convertToFormat(rgba)
    width, height, line = tile.width(), tile.height(), tile.bytesPerLine()
    ptr = tile.constBits()
    ptr.setsize(height * line)
    pixels = np.frombuffer(ptr, np.uint8).reshape(height, line)[
        :, :width * 4].reshape(height, width, 4).copy()
    for color in clear:
        pixels[np.all(pixels[..., :3] == color, axis=-1), 3] = 0
    return QImage(pixels.tobytes(), width, height, width * 4, rgba).copy()


def ramp_of(key):
    """Цвета шкалы карты без тайла: поле прогноза или пожары."""
    if key == themes.FIRES:
        return [color for _, color in fires.FRP_STOPS]
    return weather.legend(weather.BY_KEY[key[len("weather_"):]])["colors"]


def day_text(day):
    """«2026-10-05» в «05.10.2026»."""
    if not day:
        return ""
    year, month, date = day.split("-")
    return "{}.{}.{}".format(date, month, year)


class NasaMaps(QDialog):
    """Витрина карт. window - окно глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.setWindowTitle(tr("Карты NASA и погода"))
        self.resize(700, 580)
        self.names = map_names()
        self.items = {}
        self.thumbs = {}  # ключ - превью QImage
        self.base = None  # тайл подложки под превью
        self._queue = []
        self._replies = {}
        self._group = ALL
        top = QHBoxLayout()
        self.chips = QButtonGroup(self)
        self.chips.setExclusive(True)
        for key, title, tip in [(ALL, tr("Все"), tr("Все карты витрины."))] \
                + list(group_names()):
            chip = QToolButton(self)
            chip.setText(title)
            chip.setToolTip(tip)
            chip.setCheckable(True)
            chip.setChecked(key == ALL)
            chip.setAutoRaise(True)
            chip.clicked.connect(lambda *a, k=key: self._set_group(k))
            self.chips.addButton(chip)
            top.addWidget(chip)
        top.addStretch(1)
        self.search = QLineEdit(self)
        self.search.setPlaceholderText(tr("Найти карту"))
        self.search.setClearButtonEnabled(True)
        self.search.setMinimumWidth(140)
        self.search.setMaximumWidth(180)
        self.search.textChanged.connect(self._filter)
        top.addWidget(self.search)
        self.list = QListWidget(self)
        self.list.setViewMode(enum(QListView, "ViewMode", "IconMode"))
        self.list.setResizeMode(enum(QListView, "ResizeMode", "Adjust"))
        self.list.setMovement(enum(QListView, "Movement", "Static"))
        self.list.setIconSize(QSize(THUMB, THUMB))
        self.list.setGridSize(QSize(THUMB + 44, THUMB + 66))
        self.list.setTextElideMode(enum(Qt, "TextElideMode", "ElideNone"))
        self.list.setWordWrap(True)
        self.list.setSpacing(4)
        self.list.itemClicked.connect(self._clicked)
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        off = QPushButton(tr("Выключить"), self)
        off.setToolTip(tr("Убрать карту с глобуса."))
        off.clicked.connect(lambda *a: self.window.set_theme(""))
        bottom = QHBoxLayout()
        bottom.addWidget(self.note, 1)
        bottom.addWidget(off)
        layout = QVBoxLayout(self)
        layout.addLayout(top)
        layout.addWidget(self.list, 1)
        layout.addLayout(bottom)
        for key, group, kind in themes.gallery_items():
            name, tip = self.names[key]
            item = QListWidgetItem(name, self.list)
            item.setData(KEY_ROLE, key)
            item.setToolTip(tip)
            item.setTextAlignment(enum(Qt, "AlignmentFlag", "AlignHCenter"))
            self.items[key] = (item, group, kind)
            self.thumbs[key] = ramp_image(ramp_of(key)) \
                if kind in ("weather", themes.FIRES) else ramp_image([])
        self._load_base()
        self.refresh()

    # Превью.

    def _load_base(self):
        """Тайл подложки под превью, затем тайлы тем."""
        source = self.window.sources[self.window._basemap]
        url = source.tile_url(*themes.THUMB_TILE)
        self._replies["base"] = fetch_bytes(url, self._base_done)

    def _base_done(self, data, error):
        self._replies.pop("base", None)
        image = QImage.fromData(data) if data else QImage()
        self.base = None if image.isNull() else image
        for key, (item, group, kind) in self.items.items():
            if kind in ("gibs", themes.TEMPERATURE):
                self._queue.append(key)
            else:
                self._set_thumb(key, ramp_image(ramp_of(key), self.base))
        self._pump()

    def _pump(self):
        """Следующие запросы превью, не больше PARALLEL сразу. Теме
        нужен ряд дат - его просит окно глобуса."""
        waiting = []
        while self._queue and len(self._replies) < PARALLEL:
            key = self._queue.pop(0)
            url = self._thumb_url(key)
            if url is None:
                waiting.append(key)
                continue
            self._replies[key] = fetch_bytes(
                url, lambda data, error, k=key: self._thumb_done(k, data))
        self._queue[:0] = waiting

    def _thumb_url(self, key):
        if key == themes.TEMPERATURE:
            z, x, y = themes.THUMB_TILE
            return temperature.url_template(temperature.LAND).replace(
                "{z}", str(z)).replace("{x}", str(x)).replace("{y}", str(y))
        intervals = self.window._theme_domains.get(key)
        if intervals is None:
            theme = themes.BY_KEY[key]
            self.window._theme_fetch(key, "domains", theme.domains_url())
            return None
        day = themes.pick_day(intervals)
        if day is None:
            return None
        return themes.thumb_url(themes.BY_KEY[key], day)

    def _thumb_done(self, key, data):
        self._replies.pop(key, None)
        self._set_thumb(key, tile_image(data, self.base,
                                        themes.CLEAR.get(key, ())))
        self._pump()

    def _set_thumb(self, key, image):
        self.thumbs[key] = image
        self._label(key)

    def _show_icon(self, key, badge):
        """Значок карты: превью с бирочкой дня в левом верхнем углу."""
        image = QImage(self.thumbs.get(key) or ramp_image([]))
        if badge:
            painter = QPainter(image)
            font = painter.font()
            font.setPixelSize(12)
            painter.setFont(font)
            width = painter.fontMetrics().horizontalAdvance(badge) + 8
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(20, 26, 36, 200))
            painter.drawRoundedRect(3, 3, width, 17, 3, 3)
            painter.setPen(QColor(240, 244, 250))
            painter.drawText(7, 16, badge)
            painter.end()
        self.items[key][0].setIcon(QIcon(QPixmap.fromImage(image)))

    def domains_arrived(self, key):
        """Окно глобуса получило ряд дат темы: подпись дня и превью."""
        if key not in self.items:
            return
        self._label(key)
        if key in self._queue:
            self._pump()

    # Выбор и вид.

    def _label(self, key):
        item, group, kind = self.items[key]
        name = self.names[key][0]
        if kind == "gibs":
            intervals = self.window._theme_domains.get(key)
            day = themes.pick_day(intervals) if intervals else None
            sub = day_text(day) if day else ""
        elif kind == "weather":
            sub = tr("прогноз GFS")
        elif kind == themes.FIRES:
            sub = tr("24 часа")
        else:
            sub = tr("суша и море")
        item.setText(name)
        self._show_icon(key, sub)

    def refresh(self):
        """Подписи, выбранная карта и строка внизу."""
        for key in self.items:
            self._label(key)
        current = self.window.gallery_key()
        self.list.blockSignals(True)
        self.list.clearSelection()
        if current in self.items:
            self.items[current][0].setSelected(True)
            self.list.setCurrentItem(self.items[current][0])
        self.list.blockSignals(False)
        if current in self.items:
            self.note.setText(tr("На глобусе: {name}. Повторный щелчок "
                                 "убирает карту.",
                                 name=self.names[current][0]))
        else:
            self.note.setText(tr("Щелчок по карте показывает её на "
                                 "глобусе. День задаёт шкала времени."))

    def _clicked(self, item):
        key = item.data(KEY_ROLE)
        if key == self.window.gallery_key():
            key = ""
        self.window.set_theme(key)

    def _set_group(self, group):
        self._group = group
        self._filter()

    def _filter(self, *args):
        text = self.search.text().strip().lower()
        for key, (item, group, kind) in self.items.items():
            shown = (self._group == ALL or group == self._group) and (
                not text or text in self.names[key][0].lower())
            item.setHidden(not shown)

    def closeEvent(self, event):
        for reply in list(self._replies.values()):
            reply.abort()
        self._replies.clear()
        self._queue = []
        super().closeEvent(event)
