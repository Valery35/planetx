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
from qgis.core import QgsApplication
from qgis.gui import QgsColorButton
from qgis.PyQt.QtCore import (QDateTime, QPointF, QRectF, Qt,
                              pyqtSignal)
from qgis.PyQt.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateTimeEdit,
                                 QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QGroupBox,
                                 QHBoxLayout, QLabel, QLineEdit,
                                 QPlainTextEdit, QPushButton, QSlider,
                                 QVBoxLayout, QWidget)

from ..core import icons, lookat, when
from ..core.features import MAX_HEIGHT, height_share, share_height
from ..i18n import tr
from ..qt_compat import enum
from ..render.labels import svg_file
from .myplaces import DEFAULT_FILL

SLIDER_STEPS = 1000  # делений ползунка высоты


def _rgba(color):
    return (color.red(), color.green(), color.blue(), color.alpha())


def _color_text(rgba):
    return ",".join(str(int(c)) for c in rgba)


def icon_names():
    """Названия значков core.icons для списка."""
    return {"dot": tr("Кружок"), "pushpin": tr("Кнопка"), "flag": tr("Флаг"),
            "info": tr("Справка"), "camera": tr("Фотоаппарат"),
            "house": tr("Дом"), "peak": tr("Вершина"), "tree": tr("Лес"),
            "water": tr("Вода"), "survey": tr("Геодезический пункт"),
            "quarry": tr("Карьер"), "hiker": tr("Пеший маршрут"),
            "camp": tr("Лагерь"), "car": tr("Автомобиль"),
            "bus": tr("Автобус"), "rail": tr("Железная дорога"),
            "tram": tr("Трамвай"), "airport": tr("Аэропорт"),
            "ship": tr("Судно"), "fuel": tr("Заправка"),
            "parking": tr("Стоянка"), "hospital": tr("Больница"),
            "pharmacy": tr("Аптека"), "school": tr("Школа"),
            "church": tr("Храм"), "museum": tr("Музей"),
            "hotel": tr("Гостиница"), "food": tr("Ресторан"),
            "cafe": tr("Кафе"), "shop": tr("Магазин"),
            "police": tr("Полиция"), "fire": tr("Пожарная часть"),
            "post": tr("Почта"), "ski": tr("Горные лыжи"),
            "swim": tr("Купание")}


def icon_image(icon, color, size=20):
    """QIcon значка icon цвета color для списков."""
    pixmap = QPixmap(size, size)
    pixmap.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pixmap)
    painter.setRenderHint(enum(QPainter, "RenderHint", "Antialiasing"))
    path = svg_file(icons.svg(icon)) if icon != icons.DEFAULT else None
    image = None
    if path is not None:
        image, _ = QgsApplication.svgCache().svgAsImage(
            path, size - 2.0, QColor(*color), QColor(40, 30, 0, 230), 1.0,
            1.0)
    if image is not None and not image.isNull():
        painter.drawImage(QPointF((size - image.width()) / 2.0,
                                  (size - image.height()) / 2.0), image)
    else:
        painter.setPen(QPen(QColor(60, 40, 0, 230), 1.2))
        painter.setBrush(QColor(*color))
        painter.drawEllipse(QRectF(size * 0.25, size * 0.25, size * 0.5,
                                   size * 0.5))
    painter.end()
    return QIcon(pixmap)


NONE, MOMENT, SPAN = 0, 1, 2
UTC = "yyyy-MM-ddTHH:mm:ssZ"


class TimeField(QWidget):
    """Время метки или вида, как TimeStamp и TimeSpan KML: нет, момент
    или промежуток. Дата и время - местные, в файл уходят UTC. Строки
    из файла, которые не правили, остаются как были, в том числе
    неполные даты «2026-09»."""

    changed = pyqtSignal()

    def __init__(self, time, parent=None):
        super().__init__(parent)
        self.original = time
        self.mode = QComboBox(self)
        self.mode.addItems([tr("Нет"), tr("Момент"), tr("Промежуток")])
        self.begin = QDateTimeEdit(self)
        self.end = QDateTimeEdit(self)
        for edit in (self.begin, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd HH:mm")
            edit.dateTimeChanged.connect(self._edited)
        self.dash = QLabel("-", self)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.mode)
        row.addWidget(self.begin, 1)
        row.addWidget(self.dash)
        row.addWidget(self.end, 1)
        self.touched = False
        self._fill(time)
        self.mode.currentIndexChanged.connect(self._mode_changed)

    def _fill(self, time):
        now = QDateTime.currentDateTime()
        begin = when.parse(time[0]) if time else None
        end = when.parse(time[1]) if time else None
        for edit, value in ((self.begin, begin), (self.end, end)):
            edit.blockSignals(True)
            edit.setDateTime(QDateTime.fromSecsSinceEpoch(int(value))
                             if value is not None else now)
            edit.blockSignals(False)
        mode = NONE if not time else MOMENT if time[0] == time[1] else SPAN
        self.mode.blockSignals(True)
        self.mode.setCurrentIndex(mode)
        self.mode.blockSignals(False)
        self._show()

    def _show(self):
        mode = self.mode.currentIndex()
        self.begin.setEnabled(mode != NONE)
        self.end.setVisible(mode == SPAN)
        self.dash.setVisible(mode == SPAN)

    def _mode_changed(self, *args):
        self.touched = True
        self._show()
        self.changed.emit()

    def _edited(self, *args):
        self.touched = True
        self.changed.emit()

    def set_value(self, time):
        self.original = time
        self.touched = False
        self._fill(time)

    def value(self):
        """Пара строк core.when или None."""
        if not self.touched:
            return self.original
        mode = self.mode.currentIndex()
        if mode == NONE:
            return None
        begin = self.begin.dateTime().toUTC().toString(UTC)
        if mode == MOMENT:
            return (begin, begin)
        return (begin, self.end.dateTime().toUTC().toString(UTC))


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
        self.color = self.width = self.fill = self.icon = None
        if place.kind == "point":
            self.color = QgsColorButton(self)
            self.color.setAllowOpacity(True)
            self.color.setColor(QColor(*shape.color))
            self.color.setToolTip(tr(
                "Цвет значка метки, как цвет значка в Google Earth."))
            self.color.colorChanged.connect(self._color_changed)
            self.icon = QComboBox(self)
            names = icon_names()
            for icon in icons.IDS:
                self.icon.addItem(icon_image(icon, shape.color),
                                  names[icon], icon)
            self.icon.setCurrentIndex(icons.IDS.index(
                icons.normal(shape.icon)))
            self.icon.setToolTip(tr(
                "Значок точки на глобусе и в списке. В KML он уходит "
                "стандартным значком Google Earth той же темы."))
            self.icon.currentIndexChanged.connect(self._changed)
            form.addRow(tr("Значок"), self.icon)
            form.addRow(tr("Цвет"), self.color)
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
        self.time = TimeField(place.time, self)
        self.time.setToolTip(tr(
            "Собственное время метки, как TimeStamp и TimeSpan "
            "в Google Earth. Метка со временем видна, пока её время "
            "попадает в промежуток шкалы времени внизу вида. Метка "
            "без времени видна всегда."))
        form.addRow(tr("Время"), self.time)
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
        self.view_time = TimeField(self.place.view_time, group)
        self.view_time.setToolTip(tr(
            "Дата и время вида, как в Google Earth. Перелёт к метке "
            "и тур ставят шкалу времени на это время."))
        form.addRow(tr("Дата/время"), self.view_time)
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

    def _color_changed(self, *args):
        """Цвет точки: значки списка перекрашиваются."""
        rgba = _rgba(self.color.color())
        for n, icon in enumerate(icons.IDS):
            self.icon.setItemIcon(n, icon_image(icon, rgba))
        self._changed()

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
        if self.width is not None:
            values["width"] = float(self.width.value())
        if self.fill is not None:
            values["fill"] = _rgba(self.fill.color())
        if self.icon is not None:
            values["icon"] = self.icon.currentData()
        return self.place.shape._replace(**values)

    def values(self):
        """Поля файла меток для MyPlaces.update."""
        out = {"name": self.name.text().strip(),
               "description": self.description.toPlainText().strip(),
               "height": float(self.height.value()),
               "extrude": int(self.extrude.isChecked()),
               "view": lookat.text(self.view()),
               "time": when.pack(self.time.value()),
               "view_time": when.pack(self.view_time.value()
                                     if self.look.isChecked() else None)}
        if self.color is not None:
            out["color"] = _color_text(_rgba(self.color.color()))
        if self.width is not None:
            out["width"] = float(self.width.value())
        if self.icon is not None:
            out["icon"] = self.icon.currentData()
        if self.fill is not None:
            out["fill"] = _color_text(_rgba(self.fill.color()))
        return out
