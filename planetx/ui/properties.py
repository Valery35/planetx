# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Свойства вида: немодальное окно с настройками глобуса.

Устройство взято из 3D-сцены Isoliner3D. Подложка, вертикальный
масштаб рельефа и язык подписей хранятся в настройках QGIS, флажок
автообновления - в проекте. Векторная основа и флажок рельефа живут
в панели «Слои» окна глобуса, как в Google Earth.
"""
from qgis.PyQt.QtCore import pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QDoubleSpinBox,
                                 QFormLayout, QGroupBox, QVBoxLayout)

from ..core.places import AS_QGIS, LABEL_LANGUAGES, LOCAL
from ..i18n import tr
from ..qt_compat import enum

# Пределы и шаг вертикального масштаба рельефа.
SCALE_RANGE = (0.5, 10.0)
SCALE_STEP = 0.5


def language_names():
    """Названия языков подписей по кодам LABEL_LANGUAGES."""
    return {
        "ru": tr("русский"), "en": tr("английский"),
        "de": tr("немецкий"), "fr": tr("французский"),
        "es": tr("испанский"), "it": tr("итальянский"),
        "pt": tr("португальский"), "pl": tr("польский"),
        "uk": tr("украинский"), "kk": tr("казахский"),
        "tr": tr("турецкий"), "ar": tr("арабский"),
        "zh": tr("китайский"), "ja": tr("японский"),
        "ko": tr("корейский"),
    }


def language_choices():
    """Строки списка языков подписей: код и название."""
    names = language_names()
    return ([(AS_QGIS, tr("Как в QGIS")), (LOCAL, tr("Местные названия"))]
            + [(code, names[code]) for code in LABEL_LANGUAGES])


class PropertiesDialog(QDialog):
    """Окно свойств. Сигналы несут новые значения.

    sources - подложки из core/basemap.py. state - словарь с ключами
    basemap, relief, scale, language, auto.
    """

    auto_changed = pyqtSignal(bool)
    basemap_chosen = pyqtSignal(int)
    scale_changed = pyqtSignal(float)
    language_chosen = pyqtSignal(str)

    def __init__(self, sources, state, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Свойства вида"))
        self.setModal(False)

        self.basemap = QComboBox(self)
        self.basemap.addItems([
            tr("{name} - пример", name=source.name) if source.example
            else source.name for source in sources])
        self.basemap.setToolTip(tr(
            "Источник картинки на глобусе. Esri World Imagery - пример "
            "подложки, условия её использования задаёт Esri. В списке "
            "также OpenStreetMap и подключения XYZ Tiles из обозревателя "
            "QGIS, кроме подключений рельефа. Новое подключение "
            "появляется здесь при следующем открытии окна."))
        self.basemap.currentIndexChanged.connect(self.basemap_chosen)
        base = QGroupBox(tr("Подложка"), self)
        QVBoxLayout(base).addWidget(self.basemap)

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
        QFormLayout(relief).addRow(tr("Вертикальный масштаб"), self.scale)

        self.language = QComboBox(self)
        self.languages = language_choices()
        self.language.addItems([name for _, name in self.languages])
        self.language.setToolTip(tr(
            "Язык названий пунктов, водоёмов, вершин и других подписей "
            "глобуса. «Как в QGIS» берёт язык интерфейса QGIS. Если "
            "названия на выбранном языке нет, ставится название "
            "латиницей или местное. Подписи меняются сразу."))
        self.language.currentIndexChanged.connect(
            lambda index: self.language_chosen.emit(
                self.languages[index][0]))
        labels = QGroupBox(tr("Подписи"), self)
        QFormLayout(labels).addRow(tr("Язык"), self.language)

        self.auto = QCheckBox(tr("Обновлять автоматически"), self)
        self.auto.setToolTip(tr(
            "Без флажка глобус показывает новую подложку, масштаб "
            "рельефа и слои проекта после кнопки «Обновить». С флажком "
            "он обновляется сам после каждой смены настроек и каждой "
            "правки данных, стиля и порядка слоёв. На тяжёлых слоях это "
            "частая перерисовка."))
        self.auto.toggled.connect(self.auto_changed)
        layers = QGroupBox(tr("Обновление"), self)
        QVBoxLayout(layers).addWidget(self.auto)

        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(base)
        layout.addWidget(relief)
        layout.addWidget(labels)
        layout.addWidget(layers)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self.set_state(state)

    def set_state(self, state):
        """Показать состояние окна. Сигналы при этом не идут."""
        widgets = [self.basemap, self.scale, self.language, self.auto]
        for widget in widgets:
            widget.blockSignals(True)
        self.basemap.setCurrentIndex(state["basemap"])
        codes = [code for code, _ in self.languages]
        self.language.setCurrentIndex(codes.index(state["language"])
                                      if state["language"] in codes else 0)
        self.scale.setValue(state["scale"])
        # Масштаб выключенного рельефа ни на что не влияет.
        self.scale.setEnabled(state["relief"])
        self.auto.setChecked(state["auto"])
        for widget in widgets:
            widget.blockSignals(False)
