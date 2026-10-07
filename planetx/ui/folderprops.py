# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Свойства папки» по образцу окна папки Google Earth.

Просьба автора от 2 октября 2026 года, «посмотри свойства папки в GE,
наверное, стоит поближе сделать». Название, флажки «Разрешить
раскрывать папку» и «Показать содержание как группу переключателей»,
вкладки «Описание» и «Вид». Вид папки - те же пять чисел, что у вида
метки (core/lookat.py), по нему летит перелёт к папке. Окно модальное,
правки идут в файл по «OK».
"""
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox,
                                 QDoubleSpinBox, QFormLayout, QGroupBox,
                                 QHBoxLayout, QLineEdit, QPlainTextEdit,
                                 QPushButton, QTabWidget, QVBoxLayout,
                                 QWidget)

from ..core import lookat, region
from ..i18n import tr
from ..qt_compat import enum
from . import regionfield


class FolderDialog(QDialog):
    """Свойства папки «Моих меток». current_view - функция без
    аргументов, вид глобуса сейчас, или None."""

    def __init__(self, folder, current_view=None, parent=None,
                 points=()):
        super().__init__(parent)
        self.folder = folder
        # Точки меток папки - рамка Region поля «Скрывать дальше».
        self.points = list(points)
        self.current_view = current_view
        self.setWindowTitle(tr("Свойства папки"))
        self.setMinimumWidth(460)

        self.name = QLineEdit(folder.name, self)
        self.expandable = QCheckBox(tr("Разрешить раскрывать папку"), self)
        self.expandable.setChecked(folder.expandable)
        self.expandable.setToolTip(tr(
            "Без флажка папка в списке не раскрывается, её метки "
            "показывает и скрывает флажок самой папки."))
        self.radio = QCheckBox(
            tr("Показать содержание как группу переключателей"), self)
        self.radio.setChecked(folder.radio)
        self.radio.setToolTip(tr(
            "На глобусе видна только одна метка или папка из этой папки. "
            "Флажок одной строки снимает флажки остальных."))
        self.expandable.toggled.connect(self.radio.setEnabled)
        self.radio.setEnabled(folder.expandable)

        self.description = QPlainTextEdit(folder.description, self)
        self.description.setToolTip(tr(
            "Описание папки. Оно хранится в «Моих метках» и в KML."))
        tabs = QTabWidget(self)
        tabs.addTab(self.description, tr("Описание"))
        tabs.addTab(self._view_tab(folder.view), tr("Вид"))

        form = QFormLayout()
        form.addRow(tr("Название"), self.name)
        checks = QVBoxLayout()
        checks.addWidget(self.expandable)
        indent = QHBoxLayout()
        indent.addSpacing(20)
        indent.addWidget(self.radio)
        checks.addLayout(indent)
        form.addRow("", checks)
        self.far = regionfield.make(self, folder.region)
        form.addRow(tr("Скрывать дальше"), self.far)
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Ok")
            | enum(QDialogButtonBox, "StandardButton", "Cancel"), self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(tabs, 1)
        layout.addWidget(buttons)

    def _view_tab(self, view):
        page = QWidget(self)
        self.look = QGroupBox(tr("Вид папки"), page)
        self.look.setCheckable(True)
        self.look.setChecked(view is not None)
        self.look.setToolTip(tr(
            "Откуда смотрит камера, когда летит к папке. Вид задаётся "
            "вручную числами или снимком текущего вида. Без своего вида "
            "перелёт берёт в кадр все метки папки."))
        form = QFormLayout(self.look)
        view = view or (0.0, 0.0, 1.0e7, 0.0, 0.0)
        self.look_fields = []
        for text, low, high, decimals, suffix, value, tip in (
                (tr("Широта"), -90.0, 90.0, 6, "°", view[0], tr(
                    "Широта точки, на которую смотрит камера.")),
                (tr("Долгота"), -180.0, 180.0, 6, "°", view[1], tr(
                    "Долгота точки, на которую смотрит камера.")),
                (tr("Расстояние"), 1.0, 5.0e7, 0, tr(" м"), view[2], tr(
                    "Расстояние от камеры до точки взгляда. "
                    "Больше - вид шире.")),
                (tr("Азимут"), 0.0, 360.0, 1, "°", view[3], tr(
                    "Куда смотрит камера. 0 - север "
                    "вверху кадра.")),
                (tr("Наклон"), 0.0, lookat.MAX_TILT, 1, "°", view[4], tr(
                    "Наклон камеры. 0 - взгляд "
                    "отвесно вниз, больше - к горизонту."))):
            field = QDoubleSpinBox(self.look)
            field.setRange(low, high)
            field.setDecimals(decimals)
            field.setSuffix(suffix)
            field.setValue(float(value))
            field.setToolTip(tip)
            form.addRow(text, field)
            self.look_fields.append(field)
        row = QHBoxLayout()
        snap = QPushButton(tr("Снимок текущего вида"), page)
        snap.setToolTip(tr(
            "Взять вид глобуса сейчас: точку взгляда, расстояние, азимут "
            "и наклон."))
        snap.clicked.connect(self._snapshot)
        snap.setEnabled(self.current_view is not None)
        reset = QPushButton(tr("Сброс"), page)
        reset.setToolTip(tr(
            "Вернуть вид, который был у папки при открытии окна."))
        reset.clicked.connect(self._reset_view)
        row.addStretch(1)
        row.addWidget(snap)
        row.addWidget(reset)
        layout = QVBoxLayout(page)
        layout.addWidget(self.look)
        layout.addStretch(1)
        layout.addLayout(row)
        return page

    def _set_view(self, view):
        for field, value in zip(self.look_fields, view):
            field.setValue(float(value))

    def _snapshot(self):
        view = self.current_view() if self.current_view else None
        if view is not None:
            self._set_view(view)
            self.look.setChecked(True)

    def _reset_view(self):
        view = self.folder.view
        self.look.setChecked(view is not None)
        if view is not None:
            self._set_view(view)

    def values(self):
        """Поля файла меток для MyPlaces.update."""
        view = lookat.make(*(f.value() for f in self.look_fields)) \
            if self.look.isChecked() else None
        return {"name": self.name.text().strip(),
                "description": self.description.toPlainText().strip(),
                "view": lookat.text(view),
                "region": region.text(regionfield.value(
                    self.far, self.points, self.folder.region)),
                "expandable": int(self.expandable.isChecked()),
                "radio": int(self.radio.isChecked()
                             and self.expandable.isChecked())}
