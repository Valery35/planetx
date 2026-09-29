# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно свойств метки из «Моих меток», как «Свойства» Google Earth.

Название, описание, цвет и толщина линии, заливка многоугольника,
подъём над землёй с ползунком «Поверхность земли - Космос», стена
до земли и вид метки, как вкладка «Вид» Google Earth. Вид - точка
взгляда, расстояние, азимут и наклон, по нему идут перелёт к метке
и тур. Окно немодальное, вид глобуса можно крутить, пока оно
открыто. Каждая правка сразу уходит сигналом changed как объект для
предпросмотра. Записывает значения окно глобуса через MyPlaces.update
по кнопке «OK», «Отмена» возвращает прежний вид. Решение автора
от 29 сентября 2026 года.
"""
from qgis.gui import QgsColorButton
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QGroupBox,
                                 QHBoxLayout, QLabel, QLineEdit,
                                 QPlainTextEdit, QPushButton, QSlider,
                                 QVBoxLayout, QWidget)

from ..core import lookat
from ..core.features import MAX_HEIGHT, height_share, share_height
from ..i18n import tr
from ..qt_compat import enum
from .myplaces import DEFAULT_FILL

SLIDER_STEPS = 1000  # делений ползунка высоты


def _rgba(color):
    return (color.red(), color.green(), color.blue(), color.alpha())


def _color_text(rgba):
    return ",".join(str(int(c)) for c in rgba)


class PlaceProperties(QDialog):
    """Свойства метки place (myplaces.Place). changed несёт объект
    core.features.Shape с правками для предпросмотра на глобусе."""

    changed = pyqtSignal(object)

    def __init__(self, place, parent=None, current_view=None):
        super().__init__(parent)
        self.place = place
        # Вид глобуса сейчас, для кнопки «Снимок текущего вида».
        self.current_view = current_view
        shape = place.shape
        self.setModal(False)
        self.setWindowTitle(tr("Свойства: {name}",
                               name=place.name or tr("Без названия")))
        form = QFormLayout()
        self.name = QLineEdit(place.name, self)
        self.name.setToolTip(tr("Название в «Моих метках» и подпись точки "
                                "на глобусе."))
        self.name.textChanged.connect(self._changed)
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
            self.color.colorChanged.connect(self._changed)
            form.addRow(tr("Цвет"), self.color)
            self.width = QDoubleSpinBox(self)
            self.width.setRange(1.0, 10.0)
            self.width.setSingleStep(0.5)
            self.width.setValue(float(shape.width))
            self.width.setToolTip(tr(
                "Толщина линии и контура в пикселях экрана. От масштаба "
                "не зависит."))
            self.width.valueChanged.connect(self._changed)
            form.addRow(tr("Толщина"), self.width)
        if place.kind == "polygon":
            self.fill = QgsColorButton(self)
            self.fill.setAllowOpacity(True)
            self.fill.setColor(QColor(*(shape.fill or DEFAULT_FILL)))
            self.fill.setToolTip(tr(
                "Цвет заливки многоугольника. Прозрачность задаётся "
                "здесь же. Заливкой красится и стена до земли."))
            self.fill.colorChanged.connect(self._changed)
            form.addRow(tr("Заливка"), self.fill)
        self.height = QDoubleSpinBox(self)
        self.height.setRange(0.0, MAX_HEIGHT)
        self.height.setDecimals(1)
        self.height.setSuffix(tr(" м"))
        self.height.setValue(float(shape.height or 0.0))
        self.height.setToolTip(tr(
            "Подъём над рельефом, как «относительно земли» в Google Earth. "
            "Ноль - объект лежит на земле."))
        self.height.valueChanged.connect(self._height_typed)
        form.addRow(tr("Высота над землёй"), self.height)
        self.slider = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.slider.setRange(0, SLIDER_STEPS)
        self.slider.setValue(int(round(
            height_share(self.height.value()) * SLIDER_STEPS)))
        self.slider.setToolTip(tr(
            "Высота ползунком, как в Google Earth. Шкала логарифмическая, "
            "у земли шаг - метры, выше - сотни метров и километры."))
        self.slider.valueChanged.connect(self._height_slid)
        slider_row = QWidget(self)
        row = QHBoxLayout(slider_row)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(QLabel(tr("Поверхность земли"), slider_row))
        row.addWidget(self.slider, 1)
        row.addWidget(QLabel(tr("Космос"), slider_row))
        form.addRow("", slider_row)
        self.extrude = QCheckBox(tr("Выдавить до земли"), self)
        self.extrude.setChecked(bool(shape.extrude))
        self.extrude.setToolTip(tr(
            "Стена от поднятого объекта до земли, у точки - стойка. "
            "Работает при высоте больше нуля."))
        self.extrude.toggled.connect(self._changed)
        form.addRow("", self.extrude)
        self.look = self._view_group(place.view)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.look)
        layout.addWidget(buttons)

    def _view_group(self, view):
        """Раздел «Вид»: точка взгляда, расстояние, азимут, наклон.
        Снятый флажок - у метки нет своего вида."""
        group = QGroupBox(tr("Вид метки"), self)
        group.setCheckable(True)
        group.setChecked(view is not None)
        group.setToolTip(tr(
            "Откуда смотрит камера, когда летит к метке или стоит на ней "
            "в туре, как вид метки в Google Earth. Без своего вида камера "
            "берёт метку в кадр целиком."))
        form = QFormLayout(group)
        view = view or self._default_view()
        self.look_fields = []
        for text, low, high, decimals, suffix, value, tip in (
                (tr("Широта"), -90.0, 90.0, 6, "°", view[0], tr(
                    "Широта точки, на которую смотрит камера. Она может "
                    "не совпадать с меткой.")),
                (tr("Долгота"), -180.0, 180.0, 6, "°", view[1], tr(
                    "Долгота точки, на которую смотрит камера.")),
                (tr("Расстояние"), 1.0, 5.0e7, 0, tr(" м"), view[2], tr(
                    "Расстояние от камеры до точки взгляда, «диапазон» "
                    "Google Earth. Больше - вид шире.")),
                (tr("Азимут"), 0.0, 360.0, 1, "°", view[3], tr(
                    "Куда смотрит камера, «курс» Google Earth. 0 - север "
                    "вверху кадра.")),
                (tr("Наклон"), 0.0, lookat.MAX_TILT, 1, "°", view[4], tr(
                    "Наклон камеры, «угол обзора» Google Earth. 0 - взгляд "
                    "отвесно вниз, больше - к горизонту."))):
            field = QDoubleSpinBox(group)
            field.setRange(low, high)
            field.setDecimals(decimals)
            field.setSuffix(suffix)
            field.setValue(float(value))
            field.setToolTip(tip)
            form.addRow(text, field)
            self.look_fields.append(field)
        row = QWidget(group)
        buttons = QHBoxLayout(row)
        buttons.setContentsMargins(0, 0, 0, 0)
        snap = QPushButton(tr("Снимок текущего вида"), row)
        snap.setToolTip(tr(
            "Взять вид глобуса сейчас: точку взгляда, расстояние, азимут "
            "и наклон."))
        snap.clicked.connect(self._snapshot)
        snap.setEnabled(self.current_view is not None)
        reset = QPushButton(tr("Сброс"), row)
        reset.setToolTip(tr(
            "Вернуть вид, который был у метки при открытии окна."))
        reset.clicked.connect(self._reset_view)
        buttons.addWidget(snap)
        buttons.addWidget(reset)
        buttons.addStretch(1)
        form.addRow("", row)
        return group

    def _default_view(self):
        """Вид без своего вида метки: точка взгляда - метка или
        середина охвата, отвесно."""
        points = self.place.shape.points
        lats = [p[0] for p in points] or [0.0]
        lons = [p[1] for p in points] or [0.0]
        return ((min(lats) + max(lats)) / 2.0, (min(lons) + max(lons)) / 2.0,
                3000.0, 0.0, 0.0)

    def _set_view(self, view):
        for field, value in zip(self.look_fields, view):
            field.setValue(float(value))

    def _snapshot(self):
        view = self.current_view() if self.current_view else None
        if view is not None:
            self._set_view(view)
            self.look.setChecked(True)

    def _reset_view(self):
        view = self.place.view
        self.look.setChecked(view is not None)
        self._set_view(view or self._default_view())

    def view(self):
        """Вид метки из окна, None без своего вида."""
        if not self.look.isChecked():
            return None
        return lookat.make(*(field.value() for field in self.look_fields))

    def _height_typed(self, value):
        self.slider.blockSignals(True)
        self.slider.setValue(int(round(height_share(value) * SLIDER_STEPS)))
        self.slider.blockSignals(False)
        self._changed()

    def _height_slid(self, position):
        height = share_height(position / float(SLIDER_STEPS))
        # Ниже 100 м - метры, выше - десятки метров, чтобы число было
        # круглым.
        height = round(height) if height < 100.0 else round(height, -1)
        self.height.blockSignals(True)
        self.height.setValue(height)
        self.height.blockSignals(False)
        self._changed()

    def _changed(self, *args):
        self.changed.emit(self.preview())

    def preview(self):
        """Объект метки с правками окна, для глобуса."""
        values = {"name": self.name.text().strip(),
                  "height": float(self.height.value()),
                  "extrude": self.extrude.isChecked()}
        if self.color is not None:
            values["color"] = _rgba(self.color.color())
            values["width"] = float(self.width.value())
        if self.fill is not None:
            values["fill"] = _rgba(self.fill.color())
        return self.place.shape._replace(**values)

    def values(self):
        """Поля файла меток для MyPlaces.update."""
        out = {"name": self.name.text().strip(),
               "description": self.description.toPlainText().strip(),
               "height": float(self.height.value()),
               "extrude": int(self.extrude.isChecked()),
               "view": lookat.text(self.view())}
        if self.color is not None:
            out["color"] = _color_text(_rgba(self.color.color()))
            out["width"] = float(self.width.value())
        if self.fill is not None:
            out["fill"] = _color_text(_rgba(self.fill.color()))
        return out
