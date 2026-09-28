# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Новая метка, путь или многоугольник в «Мои метки», как в Google Earth.

Точки ставит тот же механизм, что у линейки (ui/measure.py): щелчок
по глобусу добавляет точку, перетаскивание двигает Землю, за курсором
тянется резинка. Окно задаёт название, цвет и толщину.
"""
from qgis.gui import QgsColorButton
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
                                 QFormLayout, QLabel, QLineEdit, QPushButton,
                                 QTabBar, QVBoxLayout)

from ..i18n import tr
from ..qt_compat import enum
from .myplaces import DEFAULT_COLOR, DEFAULT_FILL, DEFAULT_WIDTH

MODES = ("point", "path", "polygon")


def _rgba(color):
    return (color.red(), color.green(), color.blue(), color.alpha())


class PlaceDialog(QDialog):
    """Окно «Новая метка». Сигнал save_requested - кнопка «Сохранить»."""

    save_requested = pyqtSignal()
    style_changed = pyqtSignal()

    def __init__(self, ruler, namer=None, parent=None):
        super().__init__(parent)
        self.ruler = ruler
        # namer(вид) - название новой метки с номером, как «Моя метка 3».
        self.namer = namer
        self.auto_name = ""
        self.setWindowTitle(tr("Новая метка"))
        self.setModal(False)
        self.tabs = QTabBar(self)
        for title in (tr("Метка"), tr("Путь"), tr("Многоугольник")):
            self.tabs.addTab(title)
        self.tabs.currentChanged.connect(self._mode)
        self.hint = QLabel(self)
        self.hint.setWordWrap(True)
        self.name = QLineEdit(self)
        self.name.setPlaceholderText(tr("Без названия"))
        self.name.setToolTip(tr(
            "Название в «Моих метках» и подпись точки на глобусе."))
        self.color = QgsColorButton(self)
        self.color.setAllowOpacity(True)
        self.color.setToolTip(tr(
            "Цвет линии и контура. Заливка многоугольника того же цвета, "
            "полупрозрачная."))
        self.color.colorChanged.connect(self.style_changed)
        self.width = QDoubleSpinBox(self)
        self.width.setRange(1.0, 10.0)
        self.width.setSingleStep(0.5)
        self.width.setValue(DEFAULT_WIDTH)
        self.width.setToolTip(tr(
            "Толщина линии и контура в пикселях экрана. От масштаба "
            "не зависит."))
        self.width.valueChanged.connect(self.style_changed)
        form = QFormLayout()
        form.addRow(tr("Название"), self.name)
        form.addRow(tr("Цвет"), self.color)
        form.addRow(tr("Толщина"), self.width)
        self.save = QPushButton(tr("Сохранить"), self)
        self.save.setToolTip(tr("Записать объект в «Мои метки»."))
        clear = QPushButton(tr("Очистить"), self)
        clear.setToolTip(tr("Убрать поставленные точки."))
        buttons = QDialogButtonBox(self)
        role = enum(QDialogButtonBox, "ButtonRole", "ActionRole")
        buttons.addButton(self.save, role)
        buttons.addButton(clear, role)
        self.save.clicked.connect(self.save_requested)
        clear.clicked.connect(self.ruler.clear)
        layout = QVBoxLayout(self)
        layout.addWidget(self.tabs)
        layout.addWidget(self.hint)
        layout.addLayout(form)
        layout.addWidget(buttons)
        self.ruler.changed.connect(self._update)
        self._mode(0)

    def _mode(self, index):
        mode = MODES[index]
        default = DEFAULT_COLOR["line" if mode == "path" else mode]
        self.color.setColor(QColor(*default))
        self.ruler.set_mode(mode)
        self.reset_name()

    def reset_name(self):
        """Название с номером для нового объекта. Своё название,
        введённое вручную, сменой вида не затирается."""
        if self.namer is None:
            return
        text = self.name.text().strip()
        if text and text != self.auto_name:
            return
        self.auto_name = self.namer(MODES[self.tabs.currentIndex()])
        self.name.setText(self.auto_name)

    def _update(self):
        hints = {
            "point": tr("Щелчок по глобусу ставит метку. Новый щелчок "
                        "переносит её."),
            "path": tr("Щелчками по глобусу отметьте точки пути."),
            "polygon": tr("Щелчками по глобусу отметьте вершины "
                          "многоугольника.")}
        self.hint.setText(hints[self.ruler.mode])
        self.save.setEnabled(self.ruler.shape(rubber=False) is not None)

    def style(self):
        """Цвет, толщина и заливка для фигуры."""
        color = _rgba(self.color.color())
        fill = (color[0], color[1], color[2], DEFAULT_FILL[3])
        return {"color": color, "width": self.width.value(), "fill": fill}

    def shape(self, rubber=True):
        return self.ruler.shape(rubber=rubber, name=self.name.text().strip(),
                                **self.style())
