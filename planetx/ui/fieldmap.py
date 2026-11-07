# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Строки «Поля» раздела «Слои»: границы полей Fields of the World.

Тайлы MVT читаются из архива PMTiles частями файла (core/pmtiles.py,
net/ranges.py), многоугольники рисует QPainter в картинку тайла слоя вида
«emag», на глобусе одна карта этого слоя. Разобранные тайлы помнятся для
опроса щелчком. Заливка, толщина линии и картинка 512 - выбор помощника,
утверждает автор.
"""
import threading
from collections import OrderedDict

import numpy as np
from qgis.PyQt.QtCore import QObject, QPointF, Qt
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QPainterPath, QPen

from ..core import fieldmap, pmtiles, watermask
from ..core.mipmap import mip_chain
from ..core.places import DecodeError
from ..core.rows import Row
from ..i18n import tr
from ..net import ranges
from ..qt_compat import enum
from .threadtiles import ThreadTiles

LAYER = "emag"  # слой вида, общий с картами значений
WORKERS = 4  # рабочих потоков: тайл - одна-две части файла
IN_FLIGHT = 8  # тайлов в работе сразу
SIDE = 512  # пикселей на сторону картинки тайла
FILL_ALPHA = 110
LINE_WIDTH = 1.6  # пикселей картинки
TILES_KEPT = 64  # разобранных тайлов для опроса щелчком


def paint(found):
    """Картинка RGBA uint8 полей тайла."""
    image = QImage(SIDE, SIDE, enum(QImage, "Format", "Format_RGBA8888"))
    image.fill(0)
    painter = QPainter(image)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    for field in found:
        path = QPainterPath()
        path.setFillRule(enum(Qt, "FillRule", "OddEvenFill"))
        for ring in field.rings:
            points = (ring * SIDE).tolist()
            path.moveTo(*points[0])
            for x, y in points[1:]:
                path.lineTo(QPointF(x, y))
            path.closeSubpath()
        r, g, b = fieldmap.color(field.score)
        painter.setBrush(QColor(r, g, b, FILL_ALPHA))
        painter.setPen(QPen(QColor(r, g, b), LINE_WIDTH))
        painter.drawPath(path)
    painter.end()
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    rows = np.frombuffer(ptr, dtype=np.uint8).reshape(
        image.height(), image.bytesPerLine())
    return rows[:, :SIDE * 4].reshape(SIDE, SIDE, 4).copy()


class FieldTiles(ThreadTiles):
    """Картинки тайлов полей: загрузчик слоя вида (ui/threadtiles.py),
    сигнал loaded (ключ, картинка, уровни мипмапов), пустой тайл - (None,
    None), вид тогда берёт предка."""

    def __init__(self, year, parent=None):
        super().__init__(WORKERS, IN_FLIGHT, "fields", parent)
        self.year = year
        self.archive = None
        self.lock = threading.Lock()
        self.found = OrderedDict()

    def _open(self):
        url = fieldmap.URLS[self.year]
        with self.lock:
            if self.archive is None:
                self.archive = pmtiles.Archive(
                    lambda start, length: ranges.fetch(url, start, length))
            return self.archive

    def work(self, key):
        z, x, y = key
        data = self._open().tile(z, x, y)  # отказ сети - OSError
        if data is None:
            return None, None
        try:
            found = fieldmap.decode(data, fieldmap.LAYERS[self.year])
        except (DecodeError, ValueError, IndexError) as error:
            raise pmtiles.PmtilesError(str(error)) from error
        with self.lock:
            self.found[key] = found
            while len(self.found) > TILES_KEPT:
                self.found.popitem(last=False)
        if not found:
            return None, None
        rgba = paint(found)
        return rgba, mip_chain(rgba)

    def under(self, lat, lon):
        """Оценка поля в точке по разобранным тайлам или None."""
        for level in range(fieldmap.MAX_LEVEL, fieldmap.MIN_LEVEL - 1, -1):
            key, x, y = watermask.tile_of(lat, lon, level)
            with self.lock:
                found = self.found.get(key)
            if found is None:
                continue
            for field in found:
                if watermask.inside(field.rings, [x], [y])[0]:
                    return field.score
            return None
        return None


class _Scale:
    """Шкала оценки для FieldLegend."""
    key = "fields"
    stops = fieldmap.STOPS
    ticks = (70, 80, 90, 100)


class FieldTool(QObject):
    """Строки «Поля» у окна глобуса: показанный год или None.
    Исполнитель строк реестра (core/rows.py)."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.year = None
        self.tiles = None

    @property
    def key(self):
        return fieldmap.KEYS.get(self.year)

    shown_key = key

    def turn(self, key, on):
        """Строка реестра: год строки на слое вида или снять его. Ложь -
        слой вида занят другой картой, снимать нечего."""
        if on:
            year = next(y for y, k in fieldmap.KEYS.items() if k == key)
            self.set_year(year if self.window.planet.earth else None)
        elif self.key == key:
            self.set_year(None)
        else:
            return False
        return True

    def identify(self, lat, lon, tolerance=0.0):
        """Группа окна «Объекты»: оценка поля под щелчком."""
        from .identify import Group
        score = self.under(lat, lon)
        if score is None:
            return []
        values = [(tr("Оценка модели"), tr("{score} из 100",
                                           score=int(score + 0.5))),
                  (tr("Что это"), tr("Оценка модели по снимкам Sentinel-2, "
                                     "не кадастровый участок."))]
        title = tr("Поле {year} года", year=self.year)
        return [(Group(tr("Границы полей")), [(title, values, None)])]

    def credit(self):
        if self.year:
            return fieldmap.ATTRIBUTION, fieldmap.TERMS
        return None

    def set_year(self, year):
        """Показать поля года на слое «emag» или снять их, year None."""
        window = self.window
        view = window.view
        self._drop_tiles()
        self.year = year
        layer = view.gibs[LAYER]
        if year is None:
            layer.min_level = 0
            if window.gibs_loaders.get(LAYER) is None:
                view.set_gibs(LAYER, False)
            window.field_legend.setVisible(False)
            return
        old = window.gibs_loaders.pop(LAYER, None)
        if old is not None:
            old.abort()
            old.deleteLater()
        tiles = FieldTiles(year, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        window.gibs_loaders[LAYER] = tiles
        layer.max_level = fieldmap.MAX_LEVEL
        layer.min_level = fieldmap.MIN_LEVEL
        layer.empty.clear()
        view.set_gibs(LAYER, True, tiles)
        legend = window.field_legend
        legend.set_field(_Scale)
        legend.title = tr("Оценка границ полей {year}", year=year)
        legend.show()

    def under(self, lat, lon):
        return None if self.tiles is None else self.tiles.under(lat, lon)

    def _drop_tiles(self):
        if self.tiles is not None:
            if self.window.gibs_loaders.get(LAYER) is self.tiles:
                self.window.gibs_loaders.pop(LAYER)
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def close(self):
        self._drop_tiles()


# Строки каталога (core/rows.py, ui/registry.py).
COLORS = ((254, 195, 121), (243, 250, 187), (51, 160, 44))
SOURCE = "Fields of the World"
ROWS = (
    Row("ftw_2025", "life", lambda: (tr("Границы полей 2025"), tr(
        "Границы сельскохозяйственных полей мира за 2025 год - оценка "
        "модели по снимкам Sentinel-2, а не кадастр. Цвет - оценка "
        "модели от оранжевого к зелёному, поля с оценкой ниже 69 "
        "не показаны. Поля видны вблизи, с высоты около 70 км и "
        "ниже. Щелчок в режиме «Определить объекты» показывает "
        "оценку.")), FieldTool, source=SOURCE, colors=COLORS,
        words=("границы полей", "поля", "пашня 2025", "fields of the world",
               "field boundaries"), fades=(LAYER,), view_map=LAYER,
        after="worldcover"),
    Row("ftw_2024", "life", lambda: (tr("Границы полей 2024"), tr(
        "Границы сельскохозяйственных полей мира за 2024 год, тот же "
        "набор и та же оценка модели, что у строки за 2025 год. Поля "
        "видны вблизи, с высоты около 70 км и ниже.")), FieldTool,
        source=SOURCE, colors=COLORS,
        words=("границы полей 2024", "поля 2024", "пашня 2024",
               "field boundaries 2024"), fades=(LAYER,), view_map=LAYER,
        after="ftw_2025"),
)
