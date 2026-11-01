# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Снимки OpenAerialMap»: снимки с дронов и самолётов в рамке вида.

Поиск и разбор ответа - core/oam.py. Рамки снимков на глобусе - тот же
слой в памяти, что у карт Рамсея. Выбранный снимок ложится слоем тайлов
проекта, файл не скачивается (GlobeWindow.add_oam_image).
"""
import json

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (QDialog, QHBoxLayout, QLabel, QLineEdit,
                                 QPushButton, QTreeWidget, QTreeWidgetItem,
                                 QVBoxLayout)

from .. import journal
from ..core import oam, rumsey as rumsey_core
from ..i18n import tr
from ..net.overlay import fetch_bytes
from ..qt_compat import enum

PREVIEW = 220  # пикселей на сторону картинки снимка


def gsd_text(gsd):
    if gsd <= 0.0:
        return ""
    if gsd < 1.0:
        return tr("{value} см", value="{:.1f}".format(gsd * 100.0))
    return tr("{value} м", value="{:.1f}".format(gsd))


def size_text(size):
    if size >= 1e9:
        return tr("{value} ГБ", value="{:.1f}".format(size / 1e9))
    return tr("{value} МБ", value="{:.0f}".format(size / 1e6))


class OamDialog(QDialog):
    """Список снимков в рамке вида, новые первыми, и слой в проект."""

    def __init__(self, window):
        super().__init__(window)
        self.globe = window
        self.setWindowTitle(tr("Снимки OpenAerialMap"))
        self.images = []
        self.box = None
        self.page = 0
        self.found = 0
        self.reply = None
        self.picture_reply = None
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(tr("Название или поставщик"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._fill)
        self.list = QTreeWidget(self)
        self.list.setHeaderLabels([tr("Дата"), tr("Снимок"), tr("Пиксель"),
                                   tr("Файл"), tr("Лицензия")])
        self.list.setRootIsDecorated(False)
        for column, width in enumerate((85, 250, 65, 70, 100)):
            self.list.setColumnWidth(column, width)
        self.list.itemDoubleClicked.connect(lambda *a: self._add())
        self.list.currentItemChanged.connect(lambda *a: self._selected_now())
        self.picture = QLabel(self)
        self.picture.setFixedSize(PREVIEW, PREVIEW)
        self.picture.setAlignment(enum(Qt, "AlignmentFlag", "AlignCenter"))
        search = QPushButton(tr("Искать в виде"), self)
        search.setToolTip(tr("Снимки в нынешней рамке вида глобуса, новые "
                             "первыми."))
        search.clicked.connect(self.search_view)
        self.more = QPushButton(tr("Ещё"), self)
        self.more.setToolTip(tr("Следующие снимки той же рамки, более "
                                "старые."))
        self.more.clicked.connect(self._next_page)
        self.add_button = QPushButton(tr("В проект QGIS"), self)
        self.add_button.setToolTip(tr(
            "Снимок ложится слоем тайлов в проект и отмечается на "
            "глобусе. Файл не скачивается."))
        self.add_button.clicked.connect(self._add)
        fly = QPushButton(tr("Показать на глобусе"), self)
        fly.setToolTip(tr("Перелёт к рамке выбранного снимка."))
        fly.clicked.connect(self._fly)
        note = QLabel(tr(
            "Снимки загружены участниками Open Imagery Network. У каждого "
            "снимка своя лицензия, она показана в списке и записывается "
            "в права слоя. Снимки с NC - только для некоммерческого "
            "использования."), self)
        note.setWordWrap(True)
        middle = QHBoxLayout()
        middle.addWidget(self.list, 1)
        middle.addWidget(self.picture)
        buttons = QHBoxLayout()
        for button in (search, self.more, self.add_button, fly):
            buttons.addWidget(button)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.filter)
        layout.addLayout(middle, 1)
        layout.addLayout(buttons)
        layout.addWidget(note)
        self.resize(860, 500)

    def show_view(self, box):
        """Новый поиск в рамке box."""
        self.box = box
        self.images = []
        self.found = 0
        self.page = 0
        self.list.clear()
        self._ask()

    def search_view(self):
        self.show_view(self.globe.oam_box())

    def _next_page(self):
        if self.box is not None and len(self.images) < self.found:
            self._ask()

    def _ask(self):
        self._drop_reply()
        self.status.setText(tr("Поиск снимков…"))
        self.reply = fetch_bytes(oam.search_url(self.box, self.page + 1),
                                 self._arrived, prefer_cache=False)

    def _drop_reply(self):
        reply, self.reply = self.reply, None
        if reply is not None:
            reply.abort()

    def _arrived(self, data, error):
        if self.reply is None:
            return  # запрос снят
        self.reply = None
        try:
            if data is None:
                raise ValueError(error)
            images, found = oam.parse(json.loads(data.decode("utf-8")))
        except (ValueError, AttributeError, TypeError) as failure:
            journal.note("oam search: {}".format(failure))
            self.status.setText(tr("Служба OpenAerialMap не ответила."))
            return
        self.page += 1
        self.images += images
        self.found = found
        self._fill()

    def _fill(self, *args):
        current = self._current()
        self.list.blockSignals(True)
        self.list.clear()
        text = self.filter.text().strip().lower()
        role = enum(Qt, "ItemDataRole", "UserRole")
        shown = []
        for n, image in enumerate(self.images):
            if text and text not in "{} {}".format(
                    image.title, image.provider).lower():
                continue
            item = QTreeWidgetItem(self.list, [
                image.day, image.title, gsd_text(image.gsd),
                size_text(image.size), image.license])
            item.setData(0, role, n)
            item.setToolTip(1, "{} - {}".format(image.title, image.provider))
            shown.append(item)
            if current is image:
                self.list.setCurrentItem(item)
        self.list.blockSignals(False)
        self.more.setEnabled(len(self.images) < self.found)
        if not self.found:
            self.status.setText(tr(
                "В рамке вида снимков нет. Снимки покрывают мир неравномерно, "
                "отдалите вид и нажмите «Искать в виде»."))
        else:
            self.status.setText(tr(
                "Снимков в рамке вида: {found}, в списке {count}.",
                found=self.found, count=len(shown)))
        self._show_footprints()

    def _current(self):
        item = self.list.currentItem()
        if item is None:
            return None
        return self.images[item.data(
            0, enum(Qt, "ItemDataRole", "UserRole"))]

    def _selected_now(self):
        self._show_footprints()
        self._show_picture()

    def _show_footprints(self):
        if not self.isVisible():
            return
        current = self._current()
        role = enum(Qt, "ItemDataRole", "UserRole")
        boxes = [self.images[self.list.topLevelItem(n).data(0, role)].box
                 for n in range(self.list.topLevelItemCount())]
        self.globe.set_rumsey_footprints(
            boxes, None if current is None else current.box)

    def _show_picture(self):
        reply, self.picture_reply = self.picture_reply, None
        if reply is not None:
            reply.abort()
        self.picture.clear()
        image = self._current()
        if image is None or not image.thumbnail:
            return
        self.picture_reply = fetch_bytes(
            image.thumbnail, lambda data, error: self._picture(image, data))

    def _picture(self, image, data):
        if self.picture_reply is None or self._current() is not image:
            return
        self.picture_reply = None
        pixmap = QPixmap()
        if data and pixmap.loadFromData(data):
            self.picture.setPixmap(pixmap.scaled(
                PREVIEW, PREVIEW,
                enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
                enum(Qt, "TransformationMode", "SmoothTransformation")))

    def _fly(self):
        image = self._current()
        if image is None:
            return
        west, south, east, north = image.box
        self.globe.view.fly_pose((south + north) / 2.0, (west + east) / 2.0,
                                 rumsey_core.fly_distance(image.box), 0.0,
                                 0.0)

    def _add(self):
        image = self._current()
        if image is None:
            return
        if self.globe.add_oam_image(image) is None:
            self.status.setText(tr("Снимок не открылся: {title}.",
                                   title=image.title))
            return
        self.status.setText(tr("Снимок в проекте: {title}.",
                               title=image.title))
        self._fly()

    def closeEvent(self, event):
        self._drop_reply()
        reply, self.picture_reply = self.picture_reply, None
        if reply is not None:
            reply.abort()
        self.globe.set_rumsey_footprints([], None)
        super().closeEvent(event)
