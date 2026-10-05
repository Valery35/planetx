# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Новый источник тайлов».

Просьба автора от 1 октября 2026 года - окно ввода параметров тайлов,
«хорошо, когда умное». Окно принимает адрес в любом виде, который
разбирает core/tilesource.py, и само:

- приводит его к шаблону и показывает шаблон;
- предлагает название по имени сервера;
- собирает мозаику уровня 1 из четырёх тайлов, по ней видно, что
  сервер отвечает и что ряды идут в нужную сторону, флажок TMS
  переворачивает ряды;
- ищет наибольший уровень, на котором сервер отдаёт тайл в точке
  взгляда глобуса.

Источник сохраняется подключением XYZ Tiles QGIS, поэтому он виден
и в обозревателе QGIS. Подпись источника лежит в поле
planetx-attribution того же подключения.
"""
from qgis.core import QgsNetworkAccessManager, QgsSettings
from qgis.PyQt.QtCore import QTimer, QUrl
from qgis.PyQt.QtGui import QImage, QPainter, QPixmap
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QFormLayout, QHBoxLayout, QLabel, QLayout,
                                 QLineEdit, QSpinBox, QVBoxLayout)

from ..core import tilesource
from ..core.basemap import MAX_LEVEL, attribution_for, tile_url
from ..core.placeholder import PLACEHOLDER_SHARE
from ..core.tiling import lonlat_to_tile
from ..i18n import tr
from ..net.loader import MARK, REDIRECT, SAFE_REDIRECT, install_user_agent
from ..qt_compat import enum

XYZ_PREFIX = "connections/xyz/items/"
ATTRIBUTION_FIELD = "planetx-attribution"
PREVIEW = 256  # пикселей на сторону мозаики предпросмотра
PROBE_LEVELS = (19, 18, 17, 16, 15, 14, 12, 10, 8)
GRID = 24  # точек на сторону при проверке тайла на заглушку
NO_ERROR = enum(QNetworkReply, "NetworkError", "NoError")
STATUS = enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute")


def save_connection(name, url, max_level, attribution):
    """Записать подключение XYZ Tiles QGIS."""
    settings = QgsSettings()
    base = XYZ_PREFIX + name + "/"
    settings.setValue(base + "url", url)
    settings.setValue(base + "zmin", 0)
    settings.setValue(base + "zmax", int(max_level))
    if attribution:
        settings.setValue(base + ATTRIBUTION_FIELD, attribution)


def looks_placeholder(image):
    """Заглушка «нет данных»: серые пиксели почти по всей картинке,
    как у Esri World Imagery глубже снятых уровней (core/placeholder)."""
    # Как core.placeholder.is_placeholder: один точный серый цвет.
    w, h = image.width(), image.height()
    counts = {}
    for i in range(GRID):
        for j in range(GRID):
            c = image.pixelColor(int((i + 0.5) * w / GRID),
                                 int((j + 0.5) * h / GRID))
            if c.red() == c.green() == c.blue():
                counts[c.red()] = counts.get(c.red(), 0) + 1
    return max(counts.values(), default=0) >= \
        PLACEHOLDER_SHARE * GRID * GRID


def taken_names():
    names = set()
    for key in QgsSettings().allKeys():
        if key.startswith(XYZ_PREFIX):
            names.add(key[len(XYZ_PREFIX):].rpartition("/")[0])
    return names


def remove_connection(name):
    """Удалить подключение XYZ Tiles QGIS с названием name."""
    QgsSettings().remove(XYZ_PREFIX + name)


class TileSourceDialog(QDialog):
    """Новый источник тайлов или правка готового. point - (широта,
    долгота) точки взгляда глобуса, в ней ищется наибольший уровень.
    edit - core.basemap.Source подключения XYZ для правки или None."""

    def __init__(self, parent=None, point=(0.0, 0.0), edit=None):
        super().__init__(parent)
        self.edit = edit
        self.setWindowTitle(tr("Источник тайлов") if edit is not None
                            else tr("Новый источник тайлов"))
        self.point = point
        self.replies = []
        self.template = None
        self.name_edited = False
        self.credit_edited = False
        install_user_agent()
        self.setMinimumWidth(620)

        self.address = QLineEdit(self)
        self.address.setPlaceholderText(
            "https://…/{z}/{x}/{y}.png")
        self.address.setToolTip(tr(
            "Адрес тайлов в любом виде - шаблон с {z}, {x}, {y}, адрес "
            "одного тайла из браузера или адрес с z, x, y в параметрах "
            "запроса. Окно само приводит его к шаблону."))
        self.parsed = QLabel(self)
        self.parsed.setWordWrap(True)
        self.name = QLineEdit(self)
        self.name.setToolTip(tr(
            "Название источника в списке подложек и в обозревателе QGIS. "
            "Предлагается по имени сервера."))
        self.name.textEdited.connect(self._name_edited)
        self.tms = QCheckBox(tr("Ряды снизу вверх (TMS)"), self)
        self.tms.setToolTip(tr(
            "У части серверов ряды тайлов считаются от южного края. Если "
            "в мозаике ниже север внизу, отметьте флажок."))
        self.level = QSpinBox(self)
        self.level.setRange(1, MAX_LEVEL)
        self.level.setValue(18)
        self.level.setToolTip(tr(
            "Самый подробный уровень тайлов сервера. Окно находит его само "
            "по точке взгляда глобуса. Глубже этого уровня глобус "
            "увеличивает последний тайл."))
        self.credit = QLineEdit(self)
        self.credit.textEdited.connect(self._credit_edited)
        self.credit.setToolTip(tr(
            "Подпись источника в углу вида и на снимках. Условия "
            "использования тайлов задаёт их владелец."))
        self.preview = QLabel(self)
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setStyleSheet("background: #20242c;")
        self.status = QLabel(self)
        self.status.setWordWrap(True)

        form = QFormLayout()
        form.addRow(tr("Адрес"), self.address)
        form.addRow("", self.parsed)
        form.addRow(tr("Название"), self.name)
        form.addRow("", self.tms)
        form.addRow(tr("Уровни до"), self.level)
        form.addRow(tr("Подпись"), self.credit)
        self.buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(self.preview)
        row.addStretch(1)
        layout = QVBoxLayout(self)
        # Окно растёт под переносимый текст шаблона и строки состояния,
        # иначе строка состояния налезала на мозаику.
        layout.setSizeConstraint(enum(QLayout, "SizeConstraint",
                                      "SetMinimumSize"))
        layout.addLayout(form)
        layout.addLayout(row)
        layout.addWidget(self.status)
        layout.addWidget(self.buttons)

        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(600)
        self.timer.timeout.connect(self._check)
        self.address.textChanged.connect(lambda _: self.timer.start())
        self.tms.toggled.connect(lambda _: self._check())
        self._update()
        if edit is not None:
            # Правка: поля готового подключения, название и подпись
            # уже заданы пользователем.
            self.name.setText(edit.name)
            self.name_edited = True
            self.credit.setText(edit.attribution[0]
                                if edit.attribution[0] != edit.name else "")
            self.credit_edited = True
            self.address.setText(edit.url)
            self.level.setValue(edit.max_level)

    # Разбор адреса.

    def _credit_edited(self, _):
        self.credit_edited = True

    def _name_edited(self, _):
        self.name_edited = True
        self._update()

    def _check(self):
        self._abort()
        try:
            url = tilesource.template(self.address.text())
        except tilesource.ParseError:
            self.template = None
            self.parsed.setText(tr(
                "Адрес не разобран. Нужен шаблон с {z}, {x}, {y} или адрес "
                "одного тайла."))
            self.preview.clear()
            self.status.clear()
            self._update()
            return
        if self.tms.isChecked():
            url = tilesource.flip_rows(url)
        self.template = url
        self.parsed.setText(tr("Шаблон - {url}", url=url))
        self.adjustSize()
        if not self.name_edited:
            self.name.setText(tilesource.name_for(url))
        if not self.credit_edited:
            # Подпись известного сервера, например Esri, ставится сама.
            text, _ = attribution_for("", url)
            self.credit.setText(text)
        self._update()
        self._load_preview(url)

    def _update(self):
        ok = self.template is not None and bool(self.name.text().strip())
        button = self.buttons.button(
            enum(QDialogButtonBox, "StandardButton", "Ok"))
        button.setEnabled(ok)

    # Сеть: мозаика предпросмотра и поиск уровня.

    def _get(self, url, done):
        request = QNetworkRequest(QUrl(url))
        request.setAttribute(MARK, True)
        request.setAttribute(REDIRECT, SAFE_REDIRECT)
        reply = QgsNetworkAccessManager.instance().get(request)
        self.replies.append(reply)
        reply.finished.connect(lambda reply=reply: done(reply))

    def _abort(self):
        for reply in self.replies:
            reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()
        self.replies = []

    def _load_preview(self, url):
        self.canvas = QImage(PREVIEW, PREVIEW,
                             enum(QImage, "Format", "Format_RGB32"))
        self.canvas.fill(0x20242C)
        self.got = 0
        self.failed = []
        keys = tilesource.preview_keys(1)
        self.status.setText(tr("Загрузка мозаики…"))
        half = PREVIEW // 2
        for z, x, y in keys:
            self._get(tile_url(url, z, x, y),
                      lambda reply, x=x, y=y: self._tile(reply, x, y, half))
        self.best = 0
        for z in PROBE_LEVELS:
            tx, ty = lonlat_to_tile(self.point[0], self.point[1], z)
            self._get(tile_url(url, z, tx, ty),
                      lambda reply, z=z: self._probe(reply, z))

    def _image(self, reply):
        """Картинка ответа или текст ошибки."""
        if reply.error() != NO_ERROR:
            code = reply.attribute(STATUS)
            return None, str(code) if code else reply.errorString()
        image = QImage()
        if not image.loadFromData(bytes(reply.readAll())):
            return None, tr("не картинка")
        return image, ""

    def _tile(self, reply, x, y, half):
        if reply in self.replies:
            self.replies.remove(reply)
        reply.deleteLater()
        image, error = self._image(reply)
        if image is None:
            self.failed.append(error)
        else:
            self.got += 1
            painter = QPainter(self.canvas)
            painter.drawImage(x * half, y * half,
                              image.scaled(half, half))
            painter.end()
            self.preview.setPixmap(QPixmap.fromImage(self.canvas))
        self._status()

    def _probe(self, reply, z):
        if reply in self.replies:
            self.replies.remove(reply)
        reply.deleteLater()
        image, _ = self._image(reply)
        if image is not None and looks_placeholder(image):
            image = None
        if image is not None and z > self.best:
            self.best = z
            self.level.setValue(z)
        self._status()

    def _status(self):
        text = tr("Тайлов мозаики пришло {n} из 4.", n=self.got)
        if self.failed:
            text += " " + tr("Ответы с ошибкой - {errors}.",
                             errors=", ".join(sorted(set(self.failed))))
        if self.best:
            text += " " + tr("В точке взгляда есть уровень {z}.",
                             z=self.best)
        self.status.setText(text)
        self.adjustSize()

    # Итог.

    def accept(self):
        self._abort()
        name = self.name.text().strip()
        old = self.edit.name if self.edit is not None else None
        if name != old and name in taken_names():
            name = "%s (PlanetX)" % name
        if old is not None and name != old:
            remove_connection(old)
        save_connection(name, self.template, self.level.value(),
                        self.credit.text().strip())
        self.saved_name = name
        super().accept()

    def reject(self):
        self._abort()
        super().reject()
