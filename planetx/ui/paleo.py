# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Ползунок возраста палеогеографии: возрасты карт набора, период,
показ."""
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QLabel, QSlider, \
    QToolButton

from ..core import paleo
from ..i18n import tr
from ..qt_compat import enum

STYLE = ("QFrame#planetxPaleo { background: rgba(250, 250, 250, 230); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
PLAY_PERIOD = 900  # мс на шаг возраста при показе
SLIDER_WIDTH = 260


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
        self.slider.setRange(0, len(paleo.AGES) - 1)
        # Прошлое слева, настоящее справа, как на шкале времени.
        self.slider.setInvertedAppearance(True)
        self.slider.setFixedWidth(SLIDER_WIDTH)
        self.slider.setToolTip(tr(
            "Возраст в миллионах лет назад. Карта рельефа и глубин на "
            "этот возраст - PaleoDEM PALEOMAP, Scotese и Wright 2018."))
        self.slider.valueChanged.connect(self._moved)
        layout.addWidget(self.slider)
        self.play = QToolButton(self)
        self.play.setText("▶\ufe0f")
        self.play.setAutoRaise(True)
        self.play.setToolTip(tr(
            "Показ от выбранного возраста к настоящему по всем картам "
            "набора."))
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
        return paleo.AGES[self.slider.value()]

    def set_age(self, age):
        self.slider.setValue(paleo.AGES.index(paleo.nearest(age)))

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
