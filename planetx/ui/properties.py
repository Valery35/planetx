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

from ..core.coords import FORMATS
from ..core.places import AS_QGIS, LABEL_LANGUAGES, LOCAL
from ..core.sync import BOTH, GLOBE_TO_MAP, MAP_TO_GLOBE
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
    basemap, relief, scale, language, sync, follow, new_shown, auto,
    coords - формат координат из core.coords.FORMATS.
    """

    auto_changed = pyqtSignal(bool)
    basemap_chosen = pyqtSignal(int)
    scale_changed = pyqtSignal(float)
    language_chosen = pyqtSignal(str)
    sync_chosen = pyqtSignal(str)
    follow_changed = pyqtSignal(bool)
    new_shown_changed = pyqtSignal(bool)
    coords_chosen = pyqtSignal(str)
    sea_changed = pyqtSignal(bool)

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
        self.sea = QCheckBox(tr("Глубины морей и океанов"), self)
        self.sea.setToolTip(tr(
            "С флажком дно морей и океанов лежит на своих глубинах, над "
            "ним полупрозрачная вода, строка состояния показывает "
            "глубину под курсором, профиль высот - глубины и уровень "
            "моря. Без флажка высоты ниже уровня моря считаются нулём, "
            "море ровное. Есть только у Земли."))
        self.sea.toggled.connect(self.sea_changed)
        relief = QGroupBox(tr("Рельеф"), self)
        relief_form = QFormLayout(relief)
        relief_form.addRow(tr("Вертикальный масштаб"), self.scale)
        relief_form.addRow(self.sea)

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

        self.sync = QComboBox(self)
        self.directions = [
            (BOTH, tr("В обе стороны")),
            (MAP_TO_GLOBE, tr("Карта ведёт глобус")),
            (GLOBE_TO_MAP, tr("Глобус ведёт карту"))]
        self.sync.addItems([name for _, name in self.directions])
        self.sync.setToolTip(tr(
            "Кто за кем следует, когда синхронизация включена значком "
            "в углу вида. Карта ведёт глобус - сдвиг и масштаб карты "
            "переносят глобус на тот же участок, наклон и поворот "
            "глобуса остаются. Глобус ведёт карту - после остановки "
            "глобуса карта встаёт в его точку взгляда в своей системе "
            "координат."))
        self.sync.currentIndexChanged.connect(
            lambda index: self.sync_chosen.emit(self.directions[index][0]))
        self.follow = QCheckBox(tr("Слои как на карте QGIS"), self)
        self.follow.setToolTip(tr(
            "С флажком глобус показывает слои проекта, включённые "
            "в дереве слоёв QGIS, и отметка в списке глобуса включает "
            "слой и на карте. Без флажка отметки глобуса свои и карту "
            "не меняют. Флажок хранится в проекте."))
        self.follow.toggled.connect(self.follow_changed)
        self.new_shown = QCheckBox(tr("Новые слои сразу на глобус"), self)
        self.new_shown.setToolTip(tr(
            "С флажком слой, добавленный в проект, например результат "
            "обработки, сразу отмечается на глобусе. Без флажка его "
            "отмечают в списке глобуса."))
        self.new_shown.toggled.connect(self.new_shown_changed)
        canvas = QGroupBox(tr("Карта QGIS"), self)
        canvas_form = QFormLayout(canvas)
        canvas_form.addRow(tr("Синхронизация"), self.sync)
        canvas_form.addRow(self.follow)
        canvas_form.addRow(self.new_shown)

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

        self.coords = QComboBox(self)
        names = {"decimal": tr("Десятичные градусы"),
                 "dms": tr("Градусы, минуты, секунды"),
                 "utm": "UTM", "mgrs": "MGRS"}
        self.coords.addItems([names[fmt] for fmt in FORMATS])
        self.coords.setToolTip(tr(
            "Как записаны координаты в строке состояния и в окне "
            "«Объекты». Поле «Поиск» понимает все четыре формата "
            "независимо от выбора. Выше 84° северной и ниже 80° "
            "южной широты UTM и MGRS заменяются десятичными "
            "градусами."))
        self.coords.currentIndexChanged.connect(
            lambda index: self.coords_chosen.emit(FORMATS[index]))
        coordinates = QGroupBox(tr("Координаты"), self)
        QFormLayout(coordinates).addRow(tr("Формат"), self.coords)

        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        layout = QVBoxLayout(self)
        layout.addWidget(base)
        layout.addWidget(relief)
        layout.addWidget(labels)
        layout.addWidget(canvas)
        layout.addWidget(layers)
        layout.addWidget(coordinates)
        layout.addStretch(1)
        layout.addWidget(buttons)
        self.set_state(state)

    def set_state(self, state):
        """Показать состояние окна. Сигналы при этом не идут."""
        widgets = [self.basemap, self.scale, self.language, self.sync,
                   self.follow, self.new_shown, self.auto, self.coords,
                   self.sea]
        for widget in widgets:
            widget.blockSignals(True)
        self.basemap.setCurrentIndex(state["basemap"])
        codes = [code for code, _ in self.languages]
        self.language.setCurrentIndex(codes.index(state["language"])
                                      if state["language"] in codes else 0)
        ways = [way for way, _ in self.directions]
        self.sync.setCurrentIndex(ways.index(state["sync"])
                                  if state["sync"] in ways else 0)
        self.scale.setValue(state["scale"])
        # Масштаб выключенного рельефа ни на что не влияет.
        self.scale.setEnabled(state["relief"])
        self.auto.setChecked(state["auto"])
        self.follow.setChecked(state["follow"])
        self.new_shown.setChecked(state["new_shown"])
        self.sea.setChecked(state.get("sea", True))
        fmt = state.get("coords", FORMATS[0])
        self.coords.setCurrentIndex(FORMATS.index(fmt)
                                    if fmt in FORMATS else 0)
        for widget in widgets:
            widget.blockSignals(False)
