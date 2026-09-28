# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно свойств метки из «Моих меток», как «Свойства» Google Earth.

Название, описание, цвет и толщина линии, заливка многоугольника,
подъём над землёй и стена до земли. Окно только собирает значения,
записывает их окно глобуса через MyPlaces.update.
"""
from qgis.gui import QgsColorButton
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QLineEdit,
                                 QPlainTextEdit, QVBoxLayout)

from ..i18n import tr
from ..qt_compat import enum
from .myplaces import DEFAULT_FILL

MAX_HEIGHT = 100000.0  # метров подъёма, не больше


def _rgba(color):
    return (color.red(), color.green(), color.blue(), color.alpha())


def _color_text(rgba):
    return ",".join(str(int(c)) for c in rgba)


class PlaceProperties(QDialog):
    """Свойства метки place (myplaces.Place)."""

    def __init__(self, place, parent=None):
        super().__init__(parent)
        self.place = place
        shape = place.shape
        self.setWindowTitle(tr("Свойства: {name}",
                               name=place.name or tr("Без названия")))
        form = QFormLayout()
        self.name = QLineEdit(place.name, self)
        self.name.setToolTip(tr("Название в «Моих метках» и подпись точки "
                                "на глобусе."))
        form.addRow(tr("Название"), self.name)
        self.description = QPlainTextEdit(place.description, self)
        self.description.setToolTip(tr(
            "Описание метки. Оно сохраняется в файле меток и уходит "
            "в KML."))
        self.description.setMaximumHeight(90)
        form.addRow(tr("Описание"), self.description)
        self.color = self.width = self.fill = None
        if place.kind != "point":
            self.color = QgsColorButton(self)
            self.color.setAllowOpacity(True)
            self.color.setColor(QColor(*shape.color))
            self.color.setToolTip(tr("Цвет линии или контура."))
            form.addRow(tr("Цвет"), self.color)
            self.width = QDoubleSpinBox(self)
            self.width.setRange(1.0, 10.0)
            self.width.setSingleStep(0.5)
            self.width.setValue(float(shape.width))
            self.width.setToolTip(tr(
                "Толщина линии и контура в пикселях экрана. От масштаба "
                "не зависит."))
            form.addRow(tr("Толщина"), self.width)
        if place.kind == "polygon":
            self.fill = QgsColorButton(self)
            self.fill.setAllowOpacity(True)
            self.fill.setColor(QColor(*(shape.fill or DEFAULT_FILL)))
            self.fill.setToolTip(tr(
                "Цвет заливки многоугольника. Прозрачность задаётся "
                "здесь же. Заливкой красится и стена до земли."))
            form.addRow(tr("Заливка"), self.fill)
        self.height = QDoubleSpinBox(self)
        self.height.setRange(0.0, MAX_HEIGHT)
        self.height.setDecimals(1)
        self.height.setSuffix(tr(" м"))
        self.height.setValue(float(shape.height or 0.0))
        self.height.setToolTip(tr(
            "Подъём над рельефом, как «относительно земли» в Google Earth. "
            "Ноль - объект лежит на земле."))
        form.addRow(tr("Высота над землёй"), self.height)
        self.extrude = QCheckBox(tr("Выдавить до земли"), self)
        self.extrude.setChecked(bool(shape.extrude))
        self.extrude.setToolTip(tr(
            "Стена от поднятого объекта до земли, у точки - стойка. "
            "Работает при высоте больше нуля."))
        form.addRow("", self.extrude)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def values(self):
        """Поля файла меток для MyPlaces.update."""
        out = {"name": self.name.text().strip(),
               "description": self.description.toPlainText().strip(),
               "height": float(self.height.value()),
               "extrude": int(self.extrude.isChecked())}
        if self.color is not None:
            out["color"] = _color_text(_rgba(self.color.color()))
            out["width"] = float(self.width.value())
        if self.fill is not None:
            out["fill"] = _color_text(_rgba(self.fill.color()))
        return out
