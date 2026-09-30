# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подписи вида неба: светила, яркие звёзды и созвездия.

Прозрачный слой поверх вида, как органы навигации (ui/navpad.py).
Точки проецирует core.skyview после каждого кадра неба. Подписи
ставятся по старшинству - светила, звёзды по блеску, созвездия по
рангу, - и подпись, которая налезла бы на поставленную, пропускается.
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
        russian = is_russian()
        key = "ru" if russian else "en"
        # (направление, текст, вид, старшинство - меньше раньше)
        self.fixed = []
        for star in data["stars"]:
            self.fixed.append((direction(star["ra"], star["dec"]),
                               star[key], "star", 10.0 + star["mag"]))
        for entry in data["names"]:
            self.fixed.append((direction(entry["ra"], entry["dec"]),
                               entry[key], "constellation",
                               20.0 + entry["rank"]))
        self.font = QFont()
        self.font.setPointSizeF(9.0)
        self.big = QFont(self.font)
        self.big.setBold(True)
        self.shown = []  # подписи последнего рисования, для проверок
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

    def paintEvent(self, event):
        sky = self.view.sky_view
        self.shown = []
        if sky is None:
            return
        cam = self.view.camera
        ratio = self.view.devicePixelRatioF()
        items = sorted(self._items(), key=lambda item: item[3])
        dirs = np.array([item[0] for item in items])
        pixels, front = sky.project(dirs, cam.width, cam.height)
        p = QPainter(self)
        p.setRenderHint(enum(QPainter, "RenderHint", "TextAntialiasing"))
        taken = []
        width, height = self.width(), self.height()
        for (v, text, kind, _), (x, y), ahead in zip(items, pixels, front):
            if not ahead:
                continue
            x, y = x / ratio, y / ratio
            if not (0.0 <= x <= width and 0.0 <= y <= height):
                continue
            font = self.big if kind.startswith("body") else self.font
            metrics = QFontMetricsF(font)
            w = metrics.horizontalAdvance(text) if hasattr(
                metrics, "horizontalAdvance") else metrics.width(text)
            h = metrics.height()
            if kind == "constellation":
                rect = QRectF(x - w / 2.0, y - h / 2.0, w, h)
            else:
                rect = QRectF(x + GAP, y - h - 1.0, w, h)
            if any(rect.intersects(other) for other in taken):
                continue
            taken.append(rect)
            if kind.startswith("body"):
                r, g, b = skydata.BODY_STYLE[kind[5:]][0]
                color = QColor(int(r * 255), int(g * 255), int(b * 255))
            elif kind == "star":
                color = STAR_COLOR
            else:
                color = CONSTELLATION_COLOR
            p.setFont(font)
            p.setPen(color)
            p.drawText(rect, enum(Qt, "AlignmentFlag", "AlignLeft")
                       | enum(Qt, "AlignmentFlag", "AlignVCenter"), text)
            self.shown.append((kind, text, round(x), round(y)))
        p.end()
