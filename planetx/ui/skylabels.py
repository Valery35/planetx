# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подписи вида неба: светила, яркие звёзды и созвездия.

Прозрачный слой поверх вида, как органы навигации (ui/navpad.py).
Точки проецирует core.skyview после каждого кадра неба. Подписи
ставятся по старшинству - светила, звёзды по блеску, созвездия по
рангу, - и подпись, которая налезла бы на поставленную, пропускается.
Те же подписи draw кладёт на картинку снимка вида (ui/snapshot.py).
"""
import time

import numpy as np
from qgis.PyQt.QtCore import QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QFontMetricsF, QPainter
from qgis.PyQt.QtWidgets import QWidget

from ..core import skydata
from ..core.skydata import direction
from ..i18n import is_russian, tr
from ..qt_compat import enum

GAP = 6.0  # логических пикселей от точки до подписи
FONT_PIXELS = 12.0  # кегль подписи в логических пикселях
STAR_COLOR = QColor(235, 235, 225, 210)
CONSTELLATION_COLOR = QColor(120, 160, 220, 200)


def body_name(key):
    """Название светила на языке интерфейса."""
    return {"sun": tr("Солнце"), "moon": tr("Луна"),
            "mercury": tr("Меркурий"), "venus": tr("Венера"),
            "mars": tr("Марс"), "jupiter": tr("Юпитер"),
            "saturn": tr("Сатурн"), "uranus": tr("Уран"),
            "neptune": tr("Нептун")}[key]


class SkyLabels(QWidget):
    """Подписи поверх вида view (render/view.py) в режиме неба."""

    def __init__(self, view):
        super().__init__(view)
        self.view = view
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        data = skydata.load()
        key = "ru" if is_russian() else "en"
        # (направление, текст, вид, старшинство - меньше раньше)
        self.fixed = []
        for star in data["stars"]:
            self.fixed.append((direction(star["ra"], star["dec"]),
                               star[key], "star", 10.0 + star["mag"]))
        for entry in data["names"]:
            self.fixed.append((direction(entry["ra"], entry["dec"]),
                               entry[key], "constellation",
                               20.0 + entry["rank"]))
        self.shown = []  # подписи последнего рисования, для проверок
        self.shot_shown = []  # подписи последнего снимка вида
        self.hide()

    def sync(self):
        """Показать слой, если вид в режиме неба, и перерисовать."""
        on = self.view.sky_view is not None
        if on:
            self.setGeometry(0, 0, self.view.width(), self.view.height())
            if not self.isVisible():
                self.show()
            self.update()
        elif self.isVisible():
            self.hide()

    def _items(self):
        moment = self.view.sky_time
        if moment is None:
            moment = time.time()
        items = [(v, body_name(name), "body:" + name, float(i))
                 for i, (name, v, _, _) in enumerate(
                     skydata.bodies(moment))]
        if self.view.show_constellations:
            return items + self.fixed
        return items + [item for item in self.fixed if item[2] == "star"]

    def draw(self, painter, width, height, scale):
        """Подписи на холст width × height пикселей кадра. scale -
        пикселей кадра на логический пиксель, от него кегль и отступы.
        Возвращает поставленные подписи: вид, текст, x, y."""
        sky = self.view.sky_view
        if sky is None:
            return []
        items = sorted(self._items(), key=lambda item: item[3])
        pixels, front = sky.project(np.array([item[0] for item in items]),
                                    width, height)
        font = QFont()
        font.setPixelSize(max(6, int(round(FONT_PIXELS * scale))))
        big = QFont(font)
        big.setBold(True)
        gap = GAP * scale
        painter.setRenderHint(enum(QPainter, "RenderHint",
                                   "TextAntialiasing"))
        taken, shown = [], []
        flags = enum(Qt, "AlignmentFlag", "AlignLeft") \
            | enum(Qt, "AlignmentFlag", "AlignVCenter")
        for (_, text, kind, _), (x, y), ahead in zip(items, pixels, front):
            if not ahead or not (0.0 <= x <= width and 0.0 <= y <= height):
                continue
            body = kind.startswith("body")
            metrics = QFontMetricsF(big if body else font)
            w = metrics.horizontalAdvance(text) if hasattr(
                metrics, "horizontalAdvance") else metrics.width(text)
            h = metrics.height()
            if kind == "constellation":
                rect = QRectF(x - w / 2.0, y - h / 2.0, w, h)
            else:
                rect = QRectF(x + gap, y - h - scale, w, h)
            if any(rect.intersects(other) for other in taken):
                continue
            taken.append(rect)
            if body:
                r, g, b = skydata.BODY_STYLE[kind[5:]][0]
                color = QColor(int(r * 255), int(g * 255), int(b * 255))
            elif kind == "star":
                color = STAR_COLOR
            else:
                color = CONSTELLATION_COLOR
            painter.setFont(big if body else font)
            painter.setPen(color)
            painter.drawText(rect, flags, text)
            shown.append((kind, text, round(x), round(y)))
        return shown

    def paintEvent(self, event):
        cam = self.view.camera
        ratio = self.view.devicePixelRatioF()
        p = QPainter(self)
        try:
            # Проекция - в пикселях кадра, холст виджета - в логических.
            p.scale(1.0 / ratio, 1.0 / ratio)
            self.shown = self.draw(p, cam.width, cam.height, ratio)
        finally:
            p.end()
