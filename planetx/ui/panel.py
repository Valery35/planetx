# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Левая панель окна глобуса: координаты, список, строка состояния.

Устройство взято из 3D-сцены Isoliner3D. Список плоский. Первая строка
«Глобус», двойной щелчок по ней открывает свойства вида. Дальше все
слои проекта в порядке карты QGIS с типом слоя. Отметка слоя включает
его на глобусе и не меняет видимость на карте. У слоя в меню
«Подлететь».

Внизу панель «Слои», как в Google Earth: векторная основа по группам,
которые сворачиваются, и рельеф. Флажки в ней срабатывают сразу.

Панель только показывает и сообщает сигналами, решает окно.
"""
from qgis.core import QgsProject, QgsRasterLayer, QgsVectorLayer
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFont
from qgis.PyQt.QtWidgets import (QHBoxLayout, QLabel, QLineEdit,
                                 QListWidget, QListWidgetItem, QMenu,
                                 QPushButton, QSplitter, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout, QWidget)

from ..i18n import tr
from ..net.overlay import (AIRPORTS, BORDERS, PARKS, PEAKS, PLACES,
                           RAILWAYS, RIVERS, ROAD_REFS, ROADS, WATER,
                           WATER_NAMES)
from ..qt_compat import enum, enum_int

# Роль данных строки: номер слоя QGIS, у строки «Глобус» - None.
LAYER_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
CHECKABLE = enum(Qt, "ItemFlag", "ItemIsUserCheckable")
CHECKED = enum(Qt, "CheckState", "Checked")
UNCHECKED = enum(Qt, "CheckState", "Unchecked")
TRISTATE = enum(Qt, "ItemFlag", "ItemIsAutoTristate")
RELIEF = "relief"  # строка рельефа в панели «Слои»
FOUND_HEIGHT = 160  # пикселей, наибольшая высота списка найденных мест


def geo_tree():
    """Группы панели «Слои»: название, подсказка, строки группы.

    Строка - группа векторной основы, её название и подсказка.
    """
    return (
        (tr("Границы и названия"), tr(
            "Границы стран и областей и подписи на глобусе."), (
            (BORDERS, tr("Границы"), tr(
                "Границы стран ярко-жёлтые, границы областей тонкие "
                "белые. Морские границы не рисуются.")),
            (PLACES, tr("Населённые пункты"), tr(
                "Названия стран, областей, городов, посёлков и деревень. "
                "При приближении появляются всё более мелкие пункты.")),
            (WATER_NAMES, tr("Названия водоёмов"), tr(
                "Названия морей, озёр и водохранилищ, голубым курсивом.")),
        )),
        (tr("Транспорт"), tr("Дороги, их номера, железные дороги "
                             "и аэропорты."), (
            (ROADS, tr("Дороги"), tr(
                "Магистрали жёлтые, главные дороги светло-жёлтые, "
                "остальные тонкие белые. Над городом дороги закрывают "
                "подложку густой сеткой.")),
            (ROAD_REFS, tr("Номера дорог"), tr(
                "Таблички с номерами магистралей и главных дорог. "
                "Европейские маршруты на зелёной табличке. "
                "Подписываются с высоты ниже 1000 км.")),
            (RAILWAYS, tr("Железные дороги"), tr(
                "Светлая линия с тёмным пунктиром. При отдалении "
                "пропадают вместе с магистралями. Станционные "
                "и подъездные пути не рисуются.")),
            (AIRPORTS, tr("Аэропорты"), tr(
                "Названия аэропортов с квадратным значком, при "
                "приближении взлётные полосы. Подписываются с высоты "
                "ниже 1000 км.")),
        )),
        (tr("Природа"), tr("Реки, вершины и охраняемые территории."), (
            (RIVERS, tr("Реки"), tr(
                "Узкие реки синими линиями. Появляются примерно с 600 м "
                "на пиксель.")),
            (WATER, tr("Водоёмы"), tr(
                "Берега озёр, водохранилищ и широких рек обведены синей "
                "линией. Водохранилища в данных разрезаны на куски, "
                "и контур проходит и по разрезам.")),
            (PEAKS, tr("Вершины"), tr(
                "Вершины и вулканы с высотой в метрах, треугольный "
                "значок. Подписываются с высоты ниже 400 км.")),
            (PARKS, tr("Заповедники и нацпарки"), tr(
                "Заповедники, национальные парки и заказники, зелёный "
                "контур и название. Названия видны ниже 3000 км, "
                "контур вместе с магистралями.")),
        )),
    )


def layer_kind(layer):
    """Тип слоя словами, как в списке 3D-сцены Isoliner3D."""
    if isinstance(layer, QgsRasterLayer):
        return tr("растр")
    if isinstance(layer, QgsVectorLayer):
        # Номер Qgis.GeometryType: 0 точки, 1 линии, 2 полигоны.
        kinds = {0: tr("точки"), 1: tr("линии"), 2: tr("полигоны")}
        return kinds.get(enum_int(layer.geometryType()), tr("таблица"))
    return tr("слой")


class LayerPanel(QWidget):

    fly_text = pyqtSignal(str)
    # Номер строки в списке найденных мест.
    place_chosen = pyqtSignal(int)
    search_cleared = pyqtSignal()
    properties_requested = pyqtSignal()
    layer_toggled = pyqtSignal(str, bool)
    fly_to_layer = pyqtSignal(object)
    # Группы векторной основы, включённые в панели «Слои», множество.
    geo_changed = pyqtSignal(object)
    relief_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.place = QLineEdit(self)
        self.place.setPlaceholderText(tr("Поиск"))
        self.place.setClearButtonEnabled(True)
        self.place.setToolTip(tr(
            "Название места или координаты в градусах, например Пермь "
            "или 58.0105, 56.2294. Enter запускает поиск или перелёт. "
            "Несколько найденных мест показываются списком ниже, "
            "перелёт начинается щелчком по строке. Перелёт прерывается "
            "мышью."))
        self.place.returnPressed.connect(
            lambda: self.fly_text.emit(self.place.text()))
        self.place.textChanged.connect(self._search_text)
        go = QPushButton(tr("Поиск"), self)
        go.clicked.connect(lambda: self.fly_text.emit(self.place.text()))
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.place, 1)
        top.addWidget(go, 0)
        # Найденные места. Список виден, пока в нём есть строки.
        self.found = QListWidget(self)
        self.found.setVisible(False)
        self.found.setMaximumHeight(FOUND_HEIGHT)
        self.found.itemClicked.connect(
            lambda item: self.place_chosen.emit(self.found.row(item)))
        self.found.itemActivated.connect(
            lambda item: self.place_chosen.emit(self.found.row(item)))

        self.list = QListWidget(self)
        self.list.setContextMenuPolicy(
            enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(self._double_clicked)
        self.list.itemChanged.connect(self._changed)

        self.geo = QTreeWidget(self)
        self.geo.setHeaderHidden(True)
        # Щелчок по группе меняет все её строки, каждая шлёт itemChanged.
        # Изменения собираются за один проход цикла событий. Сигнал
        # подключается после того, как строки построены.
        self._geo_timer = QTimer(self)
        self._geo_timer.setSingleShot(True)
        self._geo_timer.timeout.connect(self._emit_geo)
        self.geo_items = {}
        # Последнее сообщённое окну состояние панели «Слои».
        self._relief = False
        self._groups = set()
        for title, tip, rows in geo_tree():
            group = QTreeWidgetItem(self.geo, [title])
            group.setToolTip(0, tip)
            group.setFlags(group.flags() | CHECKABLE | TRISTATE)
            for key, text, row_tip in rows:
                item = QTreeWidgetItem(group, [text])
                item.setData(0, LAYER_ROLE, key)
                item.setToolTip(0, row_tip)
                item.setFlags(item.flags() | CHECKABLE)
                item.setCheckState(0, UNCHECKED)
                self.geo_items[key] = item
        relief = QTreeWidgetItem(self.geo, [tr("Рельеф")])
        relief.setData(0, LAYER_ROLE, RELIEF)
        relief.setToolTip(0, tr(
            "Высоты Mapzen Terrain Tiles поднимают поверхность и дают "
            "отмывку склонов. Без рельефа Земля гладкая, высоты "
            "не загружаются. Вертикальный масштаб - в свойствах вида."))
        relief.setFlags(relief.flags() | CHECKABLE)
        relief.setCheckState(0, UNCHECKED)
        self.geo_items[RELIEF] = relief
        self.geo.itemChanged.connect(self._geo_changed)
        heading = QLabel(tr("Слои"), self)
        bold = QFont(heading.font())
        bold.setBold(True)
        heading.setFont(bold)
        lower = QWidget(self)
        lower_layout = QVBoxLayout(lower)
        lower_layout.setContentsMargins(0, 4, 0, 0)
        lower_layout.addWidget(heading)
        lower_layout.addWidget(self.geo, 1)
        split = QSplitter(enum(Qt, "Orientation", "Vertical"), self)
        split.addWidget(self.list)
        split.addWidget(lower)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        # Высота на две строки: камера и точка под курсором. Когда точки
        # нет, строка не сжимается и панель над ней не прыгает.
        self.status.setMinimumHeight(
            2 * self.status.fontMetrics().lineSpacing() + 2)
        self.status.setAlignment(enum(Qt, "AlignmentFlag", "AlignTop"))
        self.status.setTextInteractionFlags(
            enum(Qt, "TextInteractionFlag", "TextSelectableByMouse"))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addLayout(top)
        layout.addWidget(self.found)
        layout.addWidget(split, 1)
        layout.addWidget(self.status, 0)
        self.set_layers([], set())

    def _search_text(self, text):
        """Пустое поле поиска закрывает список и снимает метку."""
        if not text.strip():
            self.set_found([])
            self.search_cleared.emit()

    def set_found(self, texts):
        """Строки найденных мест. Пустой список прячет его."""
        self.found.clear()
        self.found.addItems(list(texts))
        self.found.setVisible(bool(texts))
        if texts:
            self.found.setCurrentRow(0)

    def set_geo(self, groups, relief):
        """Флажки панели «Слои». Сигналы при этом не идут."""
        self.geo.blockSignals(True)
        for key, item in self.geo_items.items():
            on = relief if key == RELIEF else key in groups
            item.setCheckState(0, CHECKED if on else UNCHECKED)
        self.geo.blockSignals(False)
        self._relief = relief
        self._groups = set(groups)

    def _geo_changed(self, item):
        if item.data(0, LAYER_ROLE):
            self._geo_timer.start(0)

    def _emit_geo(self):
        groups = {key for key, item in self.geo_items.items()
                  if key != RELIEF and item.checkState(0) == CHECKED}
        relief = self.geo_items[RELIEF].checkState(0) == CHECKED
        if relief != self._relief:
            self._relief = relief
            self.relief_toggled.emit(relief)
        if groups != self._groups:
            self._groups = groups
            self.geo_changed.emit(groups)

    def set_layers(self, layers, shown):
        """Строка «Глобус» и слои проекта. shown - номера отмеченных.

        Сигналы при этом не идут.
        """
        self.list.blockSignals(True)
        self.list.clear()
        head = QListWidgetItem(tr("Глобус"))
        head.setData(LAYER_ROLE, None)
        bold = QFont(head.font())
        bold.setBold(True)
        head.setFont(bold)
        head.setToolTip(tr("Свойства вида: двойной щелчок"))
        self.list.addItem(head)
        for layer in layers:
            item = QListWidgetItem(tr("{name} · {kind}", name=layer.name(),
                                      kind=layer_kind(layer)))
            item.setData(LAYER_ROLE, layer.id())
            item.setToolTip(tr(
                "Отметка показывает слой на глобусе, видимость на карте "
                "QGIS не меняется. Меню по правой кнопке - перелёт "
                "к слою."))
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(CHECKED if layer.id() in shown
                               else UNCHECKED)
            self.list.addItem(item)
        self.list.blockSignals(False)

    # События списка.

    def _changed(self, item):
        layer_id = item.data(LAYER_ROLE)
        if layer_id:
            self.layer_toggled.emit(layer_id,
                                    item.checkState() == CHECKED)

    def _double_clicked(self, item):
        if not item.data(LAYER_ROLE):
            self.properties_requested.emit()

    def _menu(self, point):
        item = self.list.itemAt(point)
        if item is None:
            return
        menu = QMenu(self)
        layer_id = item.data(LAYER_ROLE)
        if layer_id:
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer is None:
                return
            menu.addAction(tr("Подлететь")).triggered.connect(
                lambda _=False, layer=layer: self.fly_to_layer.emit(layer))
        else:
            menu.addAction(tr("Свойства вида…")).triggered.connect(
                self.properties_requested)
        menu.exec(self.list.viewport().mapToGlobal(point))
