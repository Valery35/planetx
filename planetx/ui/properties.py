# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свойства вида: немодальное окно с настройками глобуса.

Устройство взято из 3D-сцены Isoliner3D. Подложка, векторная основа
и рельеф хранятся в настройках QGIS, флажок слоёв проекта - в проекте.
"""
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QDoubleSpinBox,
                                 QFormLayout, QGroupBox, QVBoxLayout)

from ..i18n import tr
from ..net.overlay import BORDERS, RIVERS, ROADS
from ..qt_compat import enum

# Пределы и шаг вертикального масштаба рельефа.
SCALE_RANGE = (0.5, 10.0)
SCALE_STEP = 0.5


class PropertiesDialog(QDialog):
    """Окно свойств. Сигналы несут новые значения.

    state - словарь с ключами basemap, groups, relief, scale, auto.
    """

    auto_changed = pyqtSignal(bool)
    basemap_chosen = pyqtSignal(int)
    group_toggled = pyqtSignal(str, bool)
    relief_toggled = pyqtSignal(bool)
    scale_changed = pyqtSignal(float)

    def __init__(self, sources, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Свойства вида"))
        self.setModal(False)

        self.basemap = QComboBox(self)
        self.basemap.addItems(sources)
        self.basemap.setToolTip(tr(
            "Источник картинки на глобусе. В списке OpenStreetMap "
            "и подключения XYZ Tiles из обозревателя QGIS, кроме "
            "подключений рельефа. Новое подключение появляется здесь "
            "при следующем открытии окна."))
        self.basemap.currentIndexChanged.connect(self.basemap_chosen)
        base = QGroupBox(tr("Подложка"), self)
        QVBoxLayout(base).addWidget(self.basemap)

        self.groups = {}
        lines = QGroupBox(tr("Векторная основа"), self)
        lines.setToolTip(tr(
            "Линии по векторным тайлам OpenFreeMap поверх подложки. "
            "Линии ложатся на рельеф, подписей нет."))
        box = QVBoxLayout(lines)
        for group, text, tip in (
                (BORDERS, tr("Границы"), tr(
                    "Границы стран и регионов. Морские границы "
                    "не рисуются.")),
                (RIVERS, tr("Реки"), tr(
                    "Реки появляются с уровня тайлов 8, это около "
                    "600 м на пиксель.")),
                (ROADS, tr("Дороги"), tr(
                    "Магистрали и главные дороги видны с уровня 6, "
                    "остальные дороги с уровня 12. Над городом "
                    "дороги закрывают подложку густой сеткой."))):
            check = QCheckBox(text, self)
            check.setToolTip(tip)
            check.toggled.connect(
                lambda on, group=group: self.group_toggled.emit(group, on))
            box.addWidget(check)
            self.groups[group] = check

        self.relief = QCheckBox(tr("Показывать рельеф"), self)
        self.relief.setToolTip(tr(
            "Высоты Mapzen Terrain Tiles поднимают поверхность и дают "
            "отмывку склонов. Без рельефа Земля гладкая, высоты "
            "не загружаются."))
        self.relief.toggled.connect(self._relief_toggled)
        self.scale = QDoubleSpinBox(self)
        self.scale.setRange(*SCALE_RANGE)
        self.scale.setSingleStep(SCALE_STEP)
        self.scale.setDecimals(1)
        self.scale.setKeyboardTracking(False)
        self.scale.setToolTip(tr(
            "Множитель высот рельефа. Больше 1 - горы и долины "
            "выразительнее, равнинный рельеф становится заметен. "
            "Камера остаётся над поднятой поверхностью. После смены "
            "глобус пересобирает поверхность за несколько секунд."))
        self.scale.valueChanged.connect(self.scale_changed)
        relief = QGroupBox(tr("Рельеф"), self)
        form = QFormLayout(relief)
        form.addRow(self.relief)
        form.addRow(tr("Вертикальный масштаб"), self.scale)

        self.auto = QCheckBox(tr("Обновлять автоматически"), self)
        self.auto.setToolTip(tr(
            "Слои проекта на глобусе обычно обновляются кнопкой «Обновить "
            "слои». С этим флажком глобус перерисовывает их сам после "
            "каждой правки данных, стиля, порядка или видимости слоёв. "
            "Удобно на лёгких данных, на тяжёлых глобус будет часто "
            "перерисовывать наложение."))
        self.auto.toggled.connect(self.auto_changed)
        layers = QGroupBox(tr("Слои проекта"), self)
        QVBoxLayout(layers).addWidget(self.auto)

        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(base)
        layout.addWidget(lines)
        layout.addWidget(relief)
        layout.addWidget(layers)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self.set_state(state)

    def _relief_toggled(self, on):
        self.scale.setEnabled(on)
        self.relief_toggled.emit(on)

    def set_state(self, state):
        """Показать состояние окна. Сигналы при этом не идут."""
        widgets = [self.basemap, self.relief, self.scale, self.auto] \
            + list(self.groups.values())
        for widget in widgets:
            widget.blockSignals(True)
        self.basemap.setCurrentIndex(state["basemap"])
        for group, check in self.groups.items():
            check.setChecked(group in state["groups"])
        self.relief.setChecked(state["relief"])
        self.scale.setValue(state["scale"])
        self.scale.setEnabled(state["relief"])
        self.auto.setChecked(state["auto"])
        for widget in widgets:
            widget.blockSignals(False)
