# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Батиметрия водоёма»: что в растре и уровень воды.

Пункт «Батиметрия водоёма…» меню растра в «Слоях проекта». Растр
становится врезкой своего рельефа, глубины - отметками дна, над ним -
вода на уровне водоёма (core/bathymetry.py).
"""
from qgis.PyQt.QtWidgets import (QDialog, QDialogButtonBox, QDoubleSpinBox,
                                 QFormLayout, QLabel, QPushButton,
                                 QRadioButton, QVBoxLayout)

from ..i18n import tr
from ..qt_compat import enum

REMOVE = 2  # итог окна: батиметрию убрать


class BathymetryDialog(QDialog):
    """Окно настроек батиметрии растра name. setting - прежние (вид,
    уровень) или None, level - уровень по умолчанию."""

    def __init__(self, name, setting, level, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Батиметрия водоёма"))
        kind, level = setting if setting is not None else ("depth", level)
        about = QLabel(tr(
            "Растр «{name}» ложится в рельеф глобуса дном водоёма, над ним "
            "рисуется вода на уровне водоёма. Уровень по умолчанию - "
            "высота рельефа в середине растра, у озера это обычно "
            "поверхность воды.", name=name), self)
        about.setWordWrap(True)
        self.depth = QRadioButton(tr("Значения - глубины"), self)
        self.depth.setToolTip(tr(
            "Глубина под поверхностью воды, со знаком плюс или минус. "
            "Отметка дна - уровень воды минус глубина."))
        self.bed = QRadioButton(tr("Значения - отметки дна"), self)
        self.bed.setToolTip(tr(
            "Высота дна над уровнем моря, как у рельефа. Уровень воды "
            "нужен только для поверхности воды."))
        (self.depth if kind == "depth" else self.bed).setChecked(True)
        self.level = QDoubleSpinBox(self)
        self.level.setRange(-500.0, 9000.0)
        self.level.setDecimals(2)
        self.level.setSuffix(tr(" м"))
        self.level.setValue(float(level))
        self.level.setToolTip(tr(
            "Высота поверхности воды над уровнем моря. Вода рисуется на "
            "этой высоте над всеми точками, где дно ниже."))
        form = QFormLayout()
        form.addRow(self.depth)
        form.addRow(self.bed)
        form.addRow(tr("Уровень воды"), self.level)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        remove = QPushButton(tr("Убрать батиметрию"), self)
        remove.setToolTip(tr("Растр перестаёт быть рельефом глобуса, "
                             "вода над ним не рисуется."))
        remove.setEnabled(setting is not None)
        remove.clicked.connect(lambda _=False: self.done(REMOVE))
        buttons.addButton(remove, enum(QDialogButtonBox, "ButtonRole",
                                       "DestructiveRole"))
        layout = QVBoxLayout(self)
        layout.addWidget(about)
        layout.addLayout(form)
        layout.addWidget(buttons)

    def setting(self):
        """Выбранные (вид, уровень)."""
        return ("depth" if self.depth.isChecked() else "bed",
                float(self.level.value()))
