# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Плавающая панель значков в левом верхнем углу вида.

Устройство взято из 3D-сцены Isoliner3D. Сюда идут действия над видом:
скрытие боковой панели, как в Google Earth, обновление, синхронизация
с картой, определение объектов, линейка,
новая метка, сохранение вида в «Мои метки», снимок вида в файл
и в макет, сцена, свойства вида и окно «О модуле».
"""
import os

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QSize, pyqtSignal
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QFrame, QHBoxLayout, QMenu, QToolButton

from ..core.planets import MENU
from ..i18n import tr
from ..qt_compat import QActionGroup, enum

ROOT = os.path.dirname(os.path.dirname(__file__))


def body_names():
    """Названия тел меню «Тело» на языке интерфейса по ключам."""
    return {"mercury": tr("Меркурий"), "venus": tr("Венера"),
            "earth": tr("Земля"), "moon": tr("Луна"), "mars": tr("Марс"),
            "jupiter": tr("Юпитер"), "io": tr("Ио"),
            "europa": tr("Европа"), "ganymede": tr("Ганимед"),
            "callisto": tr("Каллисто"), "mimas": tr("Мимас"),
            "enceladus": tr("Энцелад"), "tethys": tr("Тефия"),
            "dione": tr("Диона"), "rhea": tr("Рея"), "titan": tr("Титан"),
            "iapetus": tr("Япет"), "triton": tr("Тритон"),
            "ceres": tr("Церера"), "vesta": tr("Веста"),
            "pluto": tr("Плутон"), "charon": tr("Харон")}
ICON_SIZE = QSize(20, 20)
STYLE = ("QFrame#planetxToolbar { background: rgba(250, 250, 250, 225); "
         "border: 1px solid rgba(0, 0, 0, 60); border-radius: 4px; }")
DIRTY_STYLE = "QToolButton { background: #ff9f1c; border-radius: 3px; }"


class ViewToolbar(QFrame):
    """Панель значков. Сигналы - по одному на кнопку."""

    sidebar_clicked = pyqtSignal()
    refresh_clicked = pyqtSignal()
    about_clicked = pyqtSignal()
    properties_clicked = pyqtSignal()
    sync_toggled = pyqtSignal(bool)
    save_view_requested = pyqtSignal()
    record_toggled = pyqtSignal(bool)
    time_toggled = pyqtSignal(bool)
    body_chosen = pyqtSignal(str)
    constellations_toggled = pyqtSignal(bool)
    identify_toggled = pyqtSignal(bool)
    ruler_clicked = pyqtSignal()
    place_clicked = pyqtSignal()
    snapshot_clicked = pyqtSignal()
    scene_save_requested = pyqtSignal()
    scene_open_requested = pyqtSignal()
    demo_requested = pyqtSignal(str)
    layout_clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("planetxToolbar")
        self.setStyleSheet(STYLE)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self.sidebar = self._button(
            QIcon(os.path.join(ROOT, "sidebar.svg")),
            tr("Скрыть боковую панель"), self.sidebar_clicked)
        self.refresh = self._button(
            QgsApplication.getThemeIcon("/mActionRefresh.svg"),
            tr("Обновить глобус"), self.refresh_clicked)
        self.sync = self._button(
            QIcon(os.path.join(ROOT, "sync.svg")),
            tr("Синхронизация с окном карты QGIS. Направление - "
               "в свойствах вида."), self.sync_toggled, checkable=True)
        self.identify = self._button(
            QgsApplication.getThemeIcon("/mActionIdentify.svg"),
            tr("Определить объекты. Щелчок по глобусу показывает "
               "координаты и высоту точки и объекты слоёв проекта, "
               "отмеченных на глобусе."), self.identify_toggled,
            checkable=True)
        self.ruler_button = self._button(
            QgsApplication.getThemeIcon("/mActionMeasure.svg"),
            tr("Линейка. Длина, периметр и площадь на эллипсоиде, "
               "сохранение измерения в «Мои метки»."), self.ruler_clicked)
        self.place_button = self._button(
            QgsApplication.getThemeIcon("/mActionAddMarker.svg"),
            tr("Новая метка, путь или многоугольник в «Мои метки»."),
            self.place_clicked)
        self.save_button = self._button(
            QgsApplication.getThemeIcon("/mActionNewBookmark.svg"),
            tr("Сохранить вид. Точка взгляда становится меткой в «Моих "
               "метках», перелёт к ней возвращает высоту, азимут "
               "и наклон."), self.save_view_requested)
        self.record = self._button(
            QgsApplication.getThemeIcon("/mActionRecord.svg"),
            tr("Записать тур с экрана. Двигайте камеру "
               "мышью, клавишами или перелётами, повторный щелчок "
               "останавливает запись. Тур ложится в «Мои метки»."),
            self.record_toggled, checkable=True)
        # Шкала времени меток. Кнопка доступна, когда у видимых меток
        # есть время, окно зовёт set_time_available.
        self.time = self._button(
            QgsApplication.getThemeIcon("/propertyicons/temporal.svg"),
            tr("Шкала времени меток. Пока шкала открыта, метки вне её "
               "промежутка скрыты. Закрытая шкала показывает все метки."),
            self.time_toggled, checkable=True)
        self.time.setEnabled(False)
        self._button(
            QgsApplication.getThemeIcon("/mActionSaveMapAsImage.svg"),
            tr("Снимок вида в файл PNG или JPEG, в том числе больше окна."),
            self.snapshot_clicked)
        self._button(
            QgsApplication.getThemeIcon("/mActionNewLayout.svg"),
            tr("Вид в макет QGIS неизменной картинкой, вставленной "
               "в проект."), self.layout_clicked)
        # Сцена: вид целиком в файл и из файла.
        scene = QToolButton(self)
        scene.setIcon(QgsApplication.getThemeIcon("/mActionFileSave.svg"))
        scene.setIconSize(ICON_SIZE)
        scene.setAutoRaise(True)
        scene.setToolTip(tr(
            "Сцена - камера, время, слои на глобусе, настройки вида "
            "и выбранная папка «Моих меток» с её туром. Сохраняется "
            "в файл и открывается на другом компьютере."))
        scene.setPopupMode(enum(QToolButton, "ToolButtonPopupMode",
                                "InstantPopup"))
        menu = QMenu(scene)
        menu.addAction(tr("Сохранить сцену…")).triggered.connect(
            self.scene_save_requested)
        menu.addAction(tr("Открыть сцену…")).triggered.connect(
            self.scene_open_requested)
        scene.setMenu(menu)
        self.layout().addWidget(scene)
        self.scene = scene
        # Демо: готовые сцены по телам, значок - академическая шапочка.
        demo = QToolButton(self)
        demo.setIcon(QIcon(os.path.join(ROOT, "demo.svg")))
        demo.setIconSize(ICON_SIZE)
        demo.setAutoRaise(True)
        demo.setToolTip(tr(
            "Демо: подготовленные сцены с метками и турами на Земле, Марсе, "
            "Луне и небе. Метки ложатся новой папкой в «Мои метки», "
            "кнопка ▶ под списком проводит тур."))
        demo.setPopupMode(enum(QToolButton, "ToolButtonPopupMode",
                               "InstantPopup"))
        menu = QMenu(demo)
        for section, items in (
                (tr("Земля"), (("perm", tr("Пермь")),
                               ("bocachica", tr("Бока-Чика, Starbase")))),
                (tr("Марс"), (("mars", tr("Места посадок марсоходов")),)),
                (tr("Луна"), (("moon",
                               tr("«Аполлоны» и «Луноходы»")),)),
                (tr("Небо"), (("sky", tr("Созвездия и яркие объекты")),))):
            menu.addSection(section)
            for key, title in items:
                menu.addAction(title).triggered.connect(
                    lambda checked=False, k=key: self.demo_requested.emit(k))
        demo.setMenu(menu)
        self.layout().addWidget(demo)
        self.demo = demo
        # Тело глобуса: Земля, Марс, Луна, и вид звёздного неба.
        body = QToolButton(self)
        body.setIcon(QIcon(os.path.join(ROOT, "planet.svg")))
        body.setIconSize(ICON_SIZE)
        body.setAutoRaise(True)
        body.setToolTip(tr(
            "Тело глобуса - планета, спутник, карликовая планета или "
            "звёздное небо. У каждого тела свои снимки, у Марса и Луны ещё "
            "и рельеф. Земные слои, поиск и здания на других телах "
            "выключены. Небо показывает созвездия, звёзды и планеты из "
            "центра небесной сферы."))
        body.setPopupMode(enum(QToolButton, "ToolButtonPopupMode",
                               "InstantPopup"))
        menu = QMenu(body)
        group = QActionGroup(menu)
        self.body_actions = {}
        names = body_names()
        sections = {"jupiter": tr("Юпитер и его спутники"),
                    "saturn": tr("Спутники Сатурна"),
                    "neptune": tr("Спутник Нептуна"),
                    "dwarf": tr("Карликовые планеты и астероиды")}
        items = []
        for section, keys in MENU:
            items.append((None, sections.get(section, "")))
            items += [(key, names[key]) for key in keys]
        items += [(None, ""), ("sky", tr("Небо"))]
        for key, title in items:
            if key is None:
                if title:
                    menu.addSection(title)
                elif menu.actions():
                    menu.addSeparator()
                continue
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setActionGroup(group)
            action.triggered.connect(
                lambda checked, k=key: self.body_chosen.emit(k))
            self.body_actions[key] = action
        self.body_actions["earth"].setChecked(True)
        # Линии и названия созвездий неба, вне группы тел.
        lines = menu.addAction(tr("Созвездия"))
        lines.setCheckable(True)
        lines.setChecked(True)
        lines.setToolTip(tr("Линии фигур и названия созвездий на небе. "
                            "Без них остаются звёзды, их имена "
                            "и светила."))
        lines.toggled.connect(self.constellations_toggled)
        self.constellations = lines
        body.setMenu(menu)
        self.layout().addWidget(body)
        self.body = body
        self.properties = self._button(
            QgsApplication.getThemeIcon("/mActionOptions.svg"),
            tr("Свойства вида: подложка, масштаб рельефа, язык подписей, "
               "связь с картой, обновление, формат координат."),
            self.properties_clicked)
        self._button(QIcon(os.path.join(ROOT, "about.svg")),
                     tr("О модуле"), self.about_clicked)
        self.adjustSize()

    def _button(self, icon, tip, signal, checkable=False):
        button = QToolButton(self)
        button.setIcon(icon)
        button.setIconSize(ICON_SIZE)
        button.setAutoRaise(True)
        button.setToolTip(tip)
        if checkable:
            button.setCheckable(True)
            button.toggled.connect(signal)
        else:
            button.clicked.connect(signal)
        self.layout().addWidget(button)
        return button

    def set_body(self, key):
        """Отметка тела в меню без сигнала."""
        action = self.body_actions.get(key)
        if action is not None:
            action.setChecked(True)

    def set_time_available(self, available):
        """Кнопка шкалы доступна, когда у видимых меток есть время.
        Без таких меток шкала закрывается."""
        self.time.setEnabled(available)
        if not available:
            self.time.setChecked(False)

    def set_time_shown(self, shown):
        """Отметка кнопки по шкале, открытой окном, без сигнала."""
        self.time.blockSignals(True)
        self.time.setChecked(shown)
        self.time.blockSignals(False)

    def set_sidebar(self, shown):
        """Подсказка значка боковой панели по её состоянию."""
        self.sidebar.setToolTip(tr("Скрыть боковую панель") if shown
                                else tr("Показать боковую панель"))

    def set_dirty(self, dirty):
        """Кнопка «Обновить» горит, пока глобус не показывает выбранное."""
        self.refresh.setStyleSheet(DIRTY_STYLE if dirty else "")
        self.refresh.setToolTip(tr(
            "Обновить глобус: настройки или слои изменились") if dirty
            else tr("Обновить глобус"))
