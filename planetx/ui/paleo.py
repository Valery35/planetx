# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Ползунок возраста палеогеографии: млн лет назад, период, показ."""
import numpy as np
from qgis.PyQt.QtCore import QPointF, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor, QImage, QPainter, QPolygonF
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, \
    QToolButton

from ..core import paleo
from ..i18n import tr
from ..qt_compat import enum

STYLE = ("QFrame#planetxPaleo { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
PLAY_PERIOD = 900  # мс на шаг возраста при показе
SLIDER_WIDTH = 260


def land_mask(rings, width=paleo.MASK_WIDTH):
    """Маска суши для вида: массив (h, w, 4) uint8, картинка всей
    Земли, север вверху, долгота -180 слева. Суша белая."""
    height = width // 2
    image = QImage(width, height,
                   enum(QImage, "Format", "Format_RGBA8888"))
    image.fill(QColor(0, 0, 0, 255))
    painter = QPainter(image)
    try:
        painter.setRenderHint(enum(QPainter, "RenderHint",
                                   "Antialiasing"))
        white = QColor(255, 255, 255)
        painter.setPen(white)
        painter.setBrush(white)
        for ring in rings:
            points = paleo.unwrapped(ring)
            # Копии со сдвигом на 360° закрывают оба края картинки.
            for shift in (-360.0, 0.0, 360.0):
                painter.drawPolygon(QPolygonF([
                    QPointF((lon + shift + 180.0) / 360.0 * width,
                            (90.0 - lat) / 180.0 * height)
                    for lat, lon in points]))
    finally:
        painter.end()
    bits = image.constBits()
    bits.setsize(width * height * 4)
    return np.frombuffer(bits, dtype=np.uint8).reshape(
        height, width, 4).copy()


def mask_from_png(data):
    """Маска суши для вида из готового PNG planetx-terrain: массив
    (h, w) uint8, суша 255, или None, если картинка не читается. Одна
    яркость вместо RGBA - маска 8192 × 4096 занимает 32 МБ, а не 128."""
    image = QImage.fromData(data, "PNG")
    if image.isNull():
        return None
    image = image.convertToFormat(enum(QImage, "Format",
                                       "Format_Grayscale8"))
    width, height, line = image.width(), image.height(), \
        image.bytesPerLine()
    bits = image.constBits()
    bits.setsize(line * height)
    return np.frombuffer(bits, dtype=np.uint8).reshape(
        height, line)[:, :width].copy()


def period_names():
    return {"quaternary": tr("Четвертичный период"), "neogene": tr("Неоген"),
            "paleogene": tr("Палеоген"), "cretaceous": tr("Мел"),
            "jurassic": tr("Юра"), "triassic": tr("Триас"),
            "permian": tr("Пермский период"), "carboniferous": tr("Карбон"),
            "devonian": tr("Девон"), "silurian": tr("Силур"),
            "ordovician": tr("Ордовик"), "cambrian": tr("Кембрий"),
            "precambrian": tr("Докембрий")}


class PaleoBar(QFrame):
    """Панель возраста. Сигнал age_changed - возраст в млн лет."""

    age_changed = pyqtSignal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("planetxPaleo")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 3, 6, 3)
        layout.setSpacing(6)
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setRange(0, paleo.MAX_AGE // paleo.STEP)
        # Прошлое слева, настоящее справа, как на шкале времени.
        self.slider.setInvertedAppearance(True)
        self.slider.setFixedWidth(SLIDER_WIDTH)
        self.slider.setToolTip(tr(
            "Возраст в миллионах лет назад. Суша на этот возраст "
            "собрана по модели Merdith 2021 из веб-службы GPlates."))
        self.slider.valueChanged.connect(self._moved)
        layout.addWidget(self.slider)
        self.play = QToolButton(self)
        self.play.setText("▶\ufe0f")
        self.play.setAutoRaise(True)
        self.play.setToolTip(tr(
            "Показ от выбранного возраста к настоящему, шаг 5 млн лет."))
        self.play.clicked.connect(self.toggle)
        layout.addWidget(self.play)
        self.label = QLabel(self)
        layout.addWidget(self.label)
        # Возраст уходит сигналом, когда ползунок остановился.
        self.settle = QTimer(self)
        self.settle.setSingleShot(True)
        self.settle.setInterval(250)
        self.settle.timeout.connect(self._emit)
        self.timer = QTimer(self)
        self.timer.setInterval(PLAY_PERIOD)
        self.timer.timeout.connect(self._step)
        # ready() - показан ли нынешний возраст. Показ ждёт его, иначе
        # шаги обгоняют ответы службы и глобус стоит. Ставит окно.
        self.ready = None
        self._show()
        self.hide()

    def age(self):
        return self.slider.value() * paleo.STEP

    def set_age(self, age):
        self.slider.setValue(int(age) // paleo.STEP)

    def _show(self):
        age = self.age()
        name = period_names()[paleo.period(age)]
        self.label.setText(tr("{age} млн лет назад, {period}", age=age,
                              period=name) if age else tr("Настоящее"))
        self.adjustSize()

    def _moved(self, *args):
        self._show()
        self.settle.start()

    def _emit(self):
        self.age_changed.emit(self.age())

    def toggle(self):
        if self.timer.isActive():
            self.stop()
        elif self.slider.value() > 0:
            self.timer.start()
            self.play.setText("⏸")

    def stop(self):
        self.timer.stop()
        self.play.setText("▶\ufe0f")

    def _step(self):
        if self.ready is not None and not self.ready():
            return
        value = self.slider.value()
        if value <= 0:
            self.stop()
            return
        self.slider.setValue(value - 1)
        # Возраст уходит сразу, без ожидания остановки ползунка.
        self.settle.stop()
        self._emit()
