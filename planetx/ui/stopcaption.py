# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Подпись остановки тура крупно на кадре: название и описание.

Просьба автора от 15 октября 2026 года - показ туром для презентации.
Плашка стоит внизу по центру кадра над подписью источников. Её рисует
одна функция draw_caption - и слой поверх вида, и запись тура в кадр,
поэтому подпись есть и в видео. Когда подпись видна, решает
core.tour.Tour.caption_at.
"""
from qgis.PyQt.QtCore import QEvent, QRectF, Qt
from qgis.PyQt.QtGui import QColor, QFont, QPainter, QTextDocument
from qgis.PyQt.QtWidgets import QWidget

from ..qt_compat import enum, enum_int

KEY = "PlanetX/tour_captions"  # показывать ли подписи остановок
# Размеры в логических пикселях окна, доля ширины кадра, отступ снизу
# над подписью источников, наибольшая длина описания. Выбор помощника,
# утверждает автор.
TITLE_SIZE = 28
TEXT_SIZE = 17
WIDTH_SHARE = 0.6
MIN_WIDTH = 360
PAD = 14
BOTTOM = 44
TEXT_LIMIT = 400
BACK = (15, 25, 40, 175)


def plain(text):
    """Описание без разметки HTML, длиннее TEXT_LIMIT - с многоточием."""
    if not text:
        return ""
    doc = QTextDocument()
    doc.setHtml(text)
    out = " ".join(doc.toPlainText().split())
    if len(out) > TEXT_LIMIT:
        out = out[:TEXT_LIMIT].rsplit(" ", 1)[0] + "…"
    return out


def draw_caption(painter, width, height, ratio, title, text, alpha):
    """Плашка подписи на кадре width x height пикселей. ratio - пикселей
    кадра на логический пиксель окна, alpha - непрозрачность 0..1."""
    if alpha <= 0.0 or not (title or text):
        return
    painter.save()
    try:
        painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
        painter.setRenderHint(enum(QPainter, "RenderHint",
                                   "TextAntialiasing"))
        pad = PAD * ratio
        box_width = min(width - 2.0 * pad,
                        max(MIN_WIDTH * ratio, width * WIDTH_SHARE))
        inner = box_width - 2.0 * pad
        wrap = enum_int(enum(Qt, "AlignmentFlag", "AlignHCenter")) \
            | enum_int(enum(Qt, "TextFlag", "TextWordWrap"))
        title_font = QFont(painter.font())
        title_font.setPixelSize(max(8, int(round(TITLE_SIZE * ratio))))
        title_font.setBold(True)
        text_font = QFont(painter.font())
        text_font.setPixelSize(max(6, int(round(TEXT_SIZE * ratio))))
        room = QRectF(0.0, 0.0, inner, height)
        painter.setFont(title_font)
        title_box = painter.boundingRect(room, wrap, title) if title \
            else QRectF()
        painter.setFont(text_font)
        text_box = painter.boundingRect(room, wrap, text) if text \
            else QRectF()
        gap = 0.4 * pad if title and text else 0.0
        box_height = title_box.height() + gap + text_box.height() + 2 * pad
        left = (width - box_width) / 2.0
        top = height - BOTTOM * ratio - box_height
        painter.setPen(enum(Qt, "PenStyle", "NoPen"))
        r, g, b, a = BACK
        painter.setBrush(QColor(r, g, b, int(round(a * alpha))))
        painter.drawRoundedRect(QRectF(left, top, box_width, box_height),
                                6.0 * ratio, 6.0 * ratio)
        y = top + pad
        if title:
            painter.setFont(title_font)
            painter.setPen(QColor(255, 255, 255, int(round(255 * alpha))))
            painter.drawText(QRectF(left + pad, y, inner, title_box.height()),
                             wrap, title)
            y += title_box.height() + gap
        if text:
            painter.setFont(text_font)
            painter.setPen(QColor(225, 232, 240, int(round(255 * alpha))))
            painter.drawText(QRectF(left + pad, y, inner, text_box.height()),
                             wrap, text)
    finally:
        painter.restore()


class StopCaption(QWidget):
    """Слой поверх вида с подписью остановки, мышь проходит сквозь."""

    def __init__(self, view):
        super().__init__(view)
        self.setAttribute(enum(Qt, "WidgetAttribute",
                               "WA_TransparentForMouseEvents"))
        self.title = ""
        self.text = ""
        self.alpha = 0.0
        self.resize(view.size())
        view.installEventFilter(self)
        self.hide()

    def set_caption(self, title, text, alpha):
        """Новая подпись или её непрозрачность, 0 прячет слой."""
        state = (title, text, round(alpha, 3))
        if state == (self.title, self.text, round(self.alpha, 3)):
            # Картинки на экране поднимаются при каждой сборке, подпись
            # остановки остаётся над ними.
            if self.isVisible():
                self.raise_()
            return
        self.title, self.text, self.alpha = title, text, alpha
        visible = alpha > 0.0 and bool(title or text)
        self.setVisible(visible)
        if visible:
            self.raise_()
            self.update()

    def eventFilter(self, watched, event):
        if event.type() == enum(QEvent, "Type", "Resize"):
            self.resize(watched.size())
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        try:
            draw_caption(painter, self.width(), self.height(), 1.0,
                         self.title, self.text, self.alpha)
        finally:
            painter.end()
