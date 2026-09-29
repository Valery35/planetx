# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Левая панель окна глобуса: поиск, три раздела, строка состояния.

Разделы сворачиваются «аккордеоном», щелчком по заголовку. Свёрнутый
раздел оставляет только заголовок, его место занимают открытые.
Решение автора от 29 сентября 2026 года.

- «Метки» - папка «Мои метки», как в Google Earth. Она есть и пустая,
  двойной щелчок по метке переносит к ней. Строки выделяются по
  несколько, с Ctrl и Shift.
- «Слои проекта» - слои проекта в порядке карты QGIS с типом слоя.
  Отметка слоя включает его на глобусе и не меняет видимость на карте.
  У слоя в меню «Подлететь», прозрачность и свойства слоя. Прозрачность -
  свойство самого слоя QGIS, решение автора от 28 сентября 2026 года.
- «Слои» - векторная основа по группам и рельеф, как панель «Слои»
  Google Earth. Свойства вида открывает значок на панели значков вида.

Панель только показывает и сообщает сигналами, решает окно.
"""
from qgis.core import (QgsApplication, QgsProject, QgsRasterLayer,
                       QgsSettings, QgsVectorLayer)
from qgis.PyQt.QtCore import Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFont, QKeySequence
from qgis.PyQt.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                                 QLineEdit,
                                 QListWidget, QMenu, QPushButton,
                                 QSizePolicy, QSlider, QSplitter,
                                 QToolButton, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout, QWidget,
                                 QWidgetAction)

from ..core import lookat
from ..core.placetree import is_folder
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
# Строки раздела «Слои» под рельефом: сетка, звёзды, облака.
GRID, STARS, CLOUDS = "grid", "stars", "clouds"
TEMPERATURE = "temperature"
BUILDINGS = "buildings"
EXTRAS = (GRID, STARS, CLOUDS, TEMPERATURE, BUILDINGS)
# Роль данных строки «Моих меток»: ключ метки «вид:номер».
PLACE_ROLE = LAYER_ROLE + 1
FOUND_HEIGHT = 160  # пикселей, наибольшая высота списка найденных мест
DRAG = enum(Qt, "ItemFlag", "ItemIsDragEnabled")
DROP = enum(Qt, "ItemFlag", "ItemIsDropEnabled")
OPEN_KEY = "PlanetX/panel_open/"  # + имя раздела: раскрыт ли он
WIDGET_MAX = 16777215  # QWIDGETSIZE_MAX, высота без предела


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


# Значки строк «Моих меток» по виду объекта, из темы QGIS.
PLACE_ICONS = {"point": "/mIconPointLayer.svg", "line": "/mIconLineLayer.svg",
               "polygon": "/mIconPolygonLayer.svg"}
VIEW_ICON = "/mIconCamera.svg"  # метка «Сохранить вид» с ракурсом


def place_icon(place):
    """Значок метки: сохранённый вид, точка, линия или многоугольник.
    Вид, поставленный метке «Снимком вида», значок не меняет."""
    name = VIEW_ICON if lookat.is_view_mark(
        place.kind, place.shape.points, place.view) \
        else PLACE_ICONS.get(place.kind, PLACE_ICONS["point"])
    return QgsApplication.getThemeIcon(name)


def layer_kind(layer):
    """Тип слоя словами, как в списке 3D-сцены Isoliner3D."""
    if isinstance(layer, QgsRasterLayer):
        return tr("растр")
    if isinstance(layer, QgsVectorLayer):
        # Номер Qgis.GeometryType: 0 точки, 1 линии, 2 полигоны.
        kinds = {0: tr("точки"), 1: tr("линии"), 2: tr("полигоны")}
        return kinds.get(enum_int(layer.geometryType()), tr("таблица"))
    return tr("слой")


class Section(QWidget):
    """Раздел панели «аккордеоном»: заголовок сворачивает содержимое.

    Свёрнутый раздел не выше своего заголовка, разделитель отдаёт
    освободившееся место открытым разделам. Раскрыт ли раздел, помнят
    настройки QGIS.
    """

    def __init__(self, name, title, body, tip, parent=None):
        super().__init__(parent)
        self.name = name
        self.body = body
        self.header = QToolButton(self)
        self.header.setText(title)
        self.header.setToolTip(tip)
        self.header.setCheckable(True)
        self.header.setAutoRaise(True)
        self.header.setToolButtonStyle(enum(Qt, "ToolButtonStyle",
                                            "ToolButtonTextBesideIcon"))
        self.header.setSizePolicy(
            enum(QSizePolicy, "Policy", "Expanding"),
            enum(QSizePolicy, "Policy", "Fixed"))
        font = QFont(self.header.font())
        font.setBold(True)
        self.header.setFont(font)
        self.row = QHBoxLayout()
        self.row.setContentsMargins(0, 0, 0, 0)
        self.row.addWidget(self.header, 1)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addLayout(self.row)
        layout.addWidget(body, 1)
        opened = QgsSettings().value(OPEN_KEY + name, True, type=bool)
        self.header.setChecked(opened)
        self._apply(opened)
        self.header.toggled.connect(self._apply)

    def add_button(self, button):
        """Кнопка справа на заголовке."""
        self.row.addWidget(button)

    def is_open(self):
        return self.header.isChecked()

    def set_open(self, on):
        self.header.setChecked(bool(on))

    def _apply(self, on):
        on = bool(on)
        self.header.setArrowType(enum(Qt, "ArrowType",
                                      "DownArrow" if on else "RightArrow"))
        self.body.setVisible(on)
        self.setMaximumHeight(WIDGET_MAX if on
                              else self.header.sizeHint().height())
        QgsSettings().setValue(OPEN_KEY + self.name, on)


class PlaceTree(QTreeWidget):
    """Верхний список. Метки и папки перетаскиваются мышью внутри
    «Моих меток» и между папками, как в Google Earth. По порядку списка
    идёт тур.

    Сам Qt строки не переносит. Сигнал place_moved сообщает ключ метки
    или папки, ключ папки назначения ("" - корень «Мои метки») и строку
    в ней, перед которой встать. Список строится заново из файла меток.
    """

    place_moved = pyqtSignal(str, str, int)
    # Несколько выбранных строк перетащены: ключи, папка, строка.
    places_moved = pyqtSignal(object, str, int)
    # Клавиша Del над выбранными строками.
    delete_pressed = pyqtSignal()
    # Ctrl+C и Ctrl+V над списком меток.
    copy_pressed = pyqtSignal()
    paste_pressed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.group = None
        # Несколько строк выделяются с Ctrl и Shift, как в проводнике.
        self.setSelectionMode(enum(QAbstractItemView, "SelectionMode",
                                   "ExtendedSelection"))
        self.setDragDropMode(enum(QAbstractItemView, "DragDropMode",
                                  "InternalMove"))
        self.setDropIndicatorShown(True)
        root = self.invisibleRootItem()
        root.setFlags(root.flags() & ~DROP)

    def _is_holder(self, item):
        """Корень «Мои метки» или папка: сюда можно положить."""
        return item is not None and (
            item is self.group or is_folder(item.data(0, PLACE_ROLE)))

    def _key(self, item):
        return "" if item is self.group else item.data(0, PLACE_ROLE)

    def selected_keys(self):
        """Ключи выделенных меток и папок в порядке списка."""
        chosen = set(id(item) for item in self.selectedItems())
        out = []

        def look(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if id(child) in chosen and child.data(0, PLACE_ROLE):
                    out.append(child.data(0, PLACE_ROLE))
                look(child)
        if self.group is not None:
            look(self.group)
        return out

    def keyPressEvent(self, event):
        if event.key() == enum(Qt, "Key", "Key_Delete") \
                and self.selected_keys():
            self.delete_pressed.emit()
            return
        if event.matches(enum(QKeySequence, "StandardKey", "Copy")):
            self.copy_pressed.emit()
            return
        if event.matches(enum(QKeySequence, "StandardKey", "Paste")):
            self.paste_pressed.emit()
            return
        super().keyPressEvent(event)

    def dropEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") \
            else event.pos()
        target = self.itemAt(pos)
        moved = self.currentItem()
        where = self.dropIndicatorPosition()
        above = enum(QAbstractItemView, "DropIndicatorPosition",
                     "AboveItem")
        on = enum(QAbstractItemView, "DropIndicatorPosition", "OnItem")
        holder, index = None, None
        if self._is_holder(target) and where == on:
            holder, index = target, target.childCount()
        elif target is not None and self._is_holder(target.parent()):
            holder = target.parent()
            index = holder.indexOfChild(target) \
                + (0 if where == above else 1)
        event.setDropAction(enum(Qt, "DropAction", "IgnoreAction"))
        event.accept()
        key = moved.data(0, PLACE_ROLE) if moved is not None else None
        chosen = self.selected_keys()
        if key and holder is not None and key in chosen \
                and len(chosen) > 1:
            self.places_moved.emit(chosen, self._key(holder), index)
        elif key and holder is not None:
            self.place_moved.emit(key, self._key(holder), index)


class LayerPanel(QWidget):

    fly_text = pyqtSignal(str)
    # Номер строки в списке найденных мест.
    place_chosen = pyqtSignal(int)
    search_cleared = pyqtSignal()
    layer_toggled = pyqtSignal(str, bool)
    fly_to_layer = pyqtSignal(object)
    # Непрозрачность слоя 0-1 из меню слоя, свойства слоя QGIS.
    opacity_changed = pyqtSignal(str, float)
    layer_properties = pyqtSignal(object)
    # Трек точечного слоя: открыть окно настроек трека.
    track_requested = pyqtSignal(object)
    # Группы векторной основы, включённые в панели «Слои», множество.
    geo_changed = pyqtSignal(object)
    relief_toggled = pyqtSignal(bool)
    # Строка сетки, звёзд или облаков: ключ из EXTRAS и флажок.
    extra_toggled = pyqtSignal(str, bool)
    # «Мои метки»: флажки меток и папок {ключ: включена}, действие над
    # меткой или папкой и ключ.
    places_toggled = pyqtSignal(object)
    place_action = pyqtSignal(str, str)
    # Метка или папка перетащена: ключ, папка назначения ("" - корень)
    # и строка в ней, перед которой она встаёт.
    place_moved = pyqtSignal(str, str, int)
    places_moved = pyqtSignal(object, str, int)
    # Действие над несколькими выбранными строками и их ключи.
    places_action = pyqtSignal(str, object)
    # Папка раскрыта или свёрнута.
    folder_expanded = pyqtSignal(str, bool)

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

        self.list = PlaceTree(self)
        # Кнопка тура под списком, как в Google Earth: активна у пути
        # и у папки «Мои метки».
        self.tour_button = QToolButton(self)
        self.tour_button.setText("▶")
        self.tour_button.setEnabled(False)
        self.tour_button.clicked.connect(self._tour_clicked)
        self.list.currentItemChanged.connect(self._tour_state)
        self.list.setHeaderHidden(True)
        self.list.place_moved.connect(self.place_moved)
        self.list.places_moved.connect(self.places_moved)
        self.list.copy_pressed.connect(self._copy_selected)
        self.list.paste_pressed.connect(
            lambda: self.place_action.emit("paste",
                                           self.current_folder() or ""))
        self.list.delete_pressed.connect(
            lambda: self.places_action.emit("remove",
                                            self.list.selected_keys()))
        self.list.setContextMenuPolicy(
            enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.itemDoubleClicked.connect(self._double_clicked)
        self.list.itemChanged.connect(self._changed)
        self.list.itemExpanded.connect(lambda item: self._expanded(item, 1))
        self.list.itemCollapsed.connect(lambda item: self._expanded(item, 0))
        # «Мои метки» - корень раздела «Метки», как в Google Earth.
        self.places_group = QTreeWidgetItem(self.list, [tr("Мои метки")])
        bold = QFont(self.places_group.font(0))
        bold.setBold(True)
        # Корень списка меток отличается от папок значком и шрифтом.
        self.places_group.setIcon(
            0, QgsApplication.getThemeIcon("/mIconFavorites.svg"))
        self.places_group.setFont(0, bold)
        self.places_group.setToolTip(0, tr(
            "Сохранённые метки, виды, пути, многоугольники и измерения. "
            "Они хранятся в общем файле профиля QGIS и видны в любом "
            "проекте. Двойной щелчок по метке переносит к ней. Метки "
            "и папки перетаскиваются мышью. Меню по правой кнопке - тур, "
            "новая папка, перелёт, переименование, удаление, слои меток "
            "в проекте. Несколько строк выделяются с Ctrl и Shift, "
            "выделенное удаляется клавишей Del."))
        self.places_group.setFlags((self.places_group.flags() | CHECKABLE
                                    | TRISTATE) & ~DRAG)
        self.list.group = self.places_group
        self.places_group.setCheckState(0, CHECKED)
        self.places_group.setExpanded(True)
        # Флажок папки меняет все метки, каждая шлёт itemChanged. Метки
        # переписываются в файл после того, как Qt обойдёт все строки,
        # иначе список перестраивался бы посреди обхода.
        self._place_states = {}
        self._place_timer = QTimer(self)
        self._place_timer.setSingleShot(True)
        self._place_timer.timeout.connect(self._emit_places)
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
        self.extra_items = {}
        self._extras = {}
        for key, text, tip in (
                (GRID, tr("Координатная сетка"), tr(
                    "Параллели и меридианы с подписями градусов, как "
                    "сетка Google Earth. Шаг сетки меняется с высотой "
                    "камеры.")),
                (STARS, tr("Звёзды"), tr(
                    "Звёзды каталога ярких звёзд Йельского университета "
                    "и Млечный путь по карте неба NASA. Картинка неба "
                    "скачивается при первом показе. Звёзды видны "
                    "из космоса и гаснут, когда камера опускается "
                    "в атмосферу.")),
                (CLOUDS, tr("Облака"), tr(
                    "Облака по снимкам VIIRS из NASA GIBS за последние "
                    "полные сутки. Они лежат полупрозрачной пеленой "
                    "поверх снимка. Снег и лёд тоже белые и остаются "
                    "видны.")),
                (TEMPERATURE, tr("Температура"), tr(
                    "Температура поверхности по данным NASA GIBS: суша "
                    "днём за 8 дней по MODIS, море за сутки по GHRSST "
                    "MUR. Под облаками на суше бывают пропуски. Шкала "
                    "в градусах стоит в левом нижнем углу вида.")),
                (BUILDINGS, tr("3D-здания"), tr(
                    "Объёмные здания из OpenStreetMap по векторным "
                    "тайлам OpenFreeMap. Они видны, когда камера ближе "
                    "6 км к земле. Высота взята из OSM, иначе из "
                    "этажности. Здание без этих сведений получает "
                    "высоту 5 м."))):
            item = QTreeWidgetItem(self.geo, [text])
            item.setData(0, LAYER_ROLE, key)
            item.setToolTip(0, tip)
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, UNCHECKED)
            self.extra_items[key] = item
        self.geo.itemChanged.connect(self._geo_changed)
        # Слои проекта - свой список, отдельно от меток.
        self.layers = QTreeWidget(self)
        self.layers.setHeaderHidden(True)
        self.layers.setRootIsDecorated(False)
        self.layers.setContextMenuPolicy(
            enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.layers.customContextMenuRequested.connect(self._layer_menu)
        self.layers.itemChanged.connect(self._changed)
        # Двойной щелчок по слою - перелёт к нему, как «Подлететь» в меню.
        self.layers.itemDoubleClicked.connect(self._layer_double_clicked)
        upper = QWidget(self)
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(2)
        upper_layout.addWidget(self.list, 1)
        tour_row = QHBoxLayout()
        tour_row.addStretch(1)
        tour_row.addWidget(self.tour_button)
        upper_layout.addLayout(tour_row)
        self.sections = [
            Section("places", tr("Метки"), upper, tr(
                "Свернуть или развернуть «Мои метки»."), self),
            Section("project", tr("Слои проекта"), self.layers, tr(
                "Свернуть или развернуть слои проекта QGIS."), self),
            Section("base", tr("Слои"), self.geo, tr(
                "Свернуть или развернуть векторную основу и рельеф."),
                self)]
        split = QSplitter(enum(Qt, "Orientation", "Vertical"), self)
        split.setChildrenCollapsible(False)
        for n, section in enumerate(self.sections):
            split.addWidget(section)
            split.setStretchFactor(n, (3, 2, 2)[n])
        self.split = split

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
        self._tour_state()

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

    def set_extras(self, states):
        """Флажки сетки, звёзд и облаков {ключ: включён}. Сигналы
        при этом не идут."""
        self.geo.blockSignals(True)
        for key, on in states.items():
            if key in self.extra_items:
                self.extra_items[key].setCheckState(
                    0, CHECKED if on else UNCHECKED)
                self._extras[key] = bool(on)
        self.geo.blockSignals(False)

    def _geo_changed(self, item):
        if item.data(0, LAYER_ROLE):
            self._geo_timer.start(0)

    def set_places(self, tree):
        """Строки «Моих меток» по дереву MyPlaces.tree(): метки Place
        и пары (Folder, дети). Сигналы при этом не идут."""
        self.list.blockSignals(True)
        group = self.places_group
        group.takeChildren()
        self._fill(group, tree)
        if not tree:
            # Пустая папка отмечена, новая метка сразу видна.
            group.setCheckState(0, CHECKED)
        group.setExpanded(True)
        self.list.blockSignals(False)
        self._tour_state()

    def _fill(self, parent, nodes):
        folder_icon = QgsApplication.getThemeIcon("/mIconFolder.svg")
        for node in nodes:
            if isinstance(node, tuple):
                folder, kids = node
                item = QTreeWidgetItem(parent, [folder.name
                                                or tr("Без названия")])
                item.setData(0, PLACE_ROLE, folder.key)
                item.setIcon(0, folder_icon)
                item.setFlags(item.flags() | CHECKABLE | TRISTATE)
                self._fill(item, kids)
                if not kids:
                    item.setCheckState(0, CHECKED if folder.visible
                                       else UNCHECKED)
                item.setExpanded(folder.expanded)
                continue
            item = QTreeWidgetItem(parent, [node.name or tr("Без названия")])
            item.setData(0, PLACE_ROLE, node.key)
            item.setIcon(0, place_icon(node))
            if node.measure:
                item.setToolTip(0, node.measure)
            item.setFlags((item.flags() | CHECKABLE) & ~DROP)
            item.setCheckState(0, CHECKED if node.visible else UNCHECKED)

    def select_place(self, key):
        """Сделать строку метки или папки текущей и показать её."""
        found = [None]

        def look(parent):
            for i in range(parent.childCount()):
                child = parent.child(i)
                if child.data(0, PLACE_ROLE) == key:
                    found[0] = child
                    return
                look(child)
        look(self.places_group)
        if found[0] is not None:
            self.list.setCurrentItem(found[0])
            self.list.scrollToItem(found[0])

    def current_folder(self):
        """Папка для новой метки: выбранная папка или папка выбранной
        метки, None - корень «Мои метки»."""
        item = self.list.currentItem()
        while item is not None and item is not self.places_group:
            key = item.data(0, PLACE_ROLE)
            if is_folder(key):
                return key
            item = item.parent()
        return None

    def _expanded(self, item, on):
        key = item.data(0, PLACE_ROLE)
        if is_folder(key):
            self.folder_expanded.emit(key, bool(on))

    def _tour_key(self, item):
        """Что облетит кнопка тура: "" - все «Мои метки», ключ папки -
        её метки, ключ пути - путь, None - нечего."""
        if item is self.places_group:
            return ""
        key = item.data(0, PLACE_ROLE) if item is not None else None
        if key and (is_folder(key) or key.startswith("line:")):
            return key
        return None

    def _tour_state(self, *args):
        key = self._tour_key(self.list.currentItem())
        self.tour_button.setEnabled(key is not None)
        self.tour_button.setToolTip(
            tr("Тур по отмеченным «Моим меткам»") if key == ""
            else tr("Тур по отмеченным меткам папки") if is_folder(key)
            else tr("Тур вдоль выбранного пути") if key
            else tr("Тур: выберите папку «Мои метки» или путь в ней"))

    def _tour_clicked(self):
        key = self._tour_key(self.list.currentItem())
        if key is not None:
            self.place_action.emit("tour", key)

    def _emit_places(self):
        states, self._place_states = self._place_states, {}
        if states:
            self.places_toggled.emit(states)

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
        for key, item in self.extra_items.items():
            on = item.checkState(0) == CHECKED
            if on != self._extras.get(key):
                self._extras[key] = on
                self.extra_toggled.emit(key, on)

    def set_layers(self, layers, shown):
        """Слои проекта под «Глобусом» и «Моими метками». shown - номера
        отмеченных.

        Сигналы при этом не идут.
        """
        self.layers.blockSignals(True)
        self.layers.clear()
        for layer in layers:
            item = QTreeWidgetItem(self.layers, [tr(
                "{name} · {kind}", name=layer.name(),
                kind=layer_kind(layer))])
            item.setData(0, LAYER_ROLE, layer.id())
            item.setToolTip(0, tr(
                "Отметка показывает слой на глобусе, видимость на карте "
                "QGIS не меняется. Двойной щелчок переносит к слою, меню "
                "по правой кнопке - перелёт, прозрачность и свойства."))
            item.setFlags((item.flags() | CHECKABLE) & ~DRAG & ~DROP)
            item.setCheckState(0, CHECKED if layer.id() in shown
                               else UNCHECKED)
        self.layers.blockSignals(False)

    # События списка.

    def _changed(self, item):
        key = item.data(0, PLACE_ROLE)
        if key:
            self._place_states[key] = item.checkState(0) == CHECKED
            self._place_timer.start(0)
            return
        layer_id = item.data(0, LAYER_ROLE)
        if layer_id:
            self.layer_toggled.emit(layer_id,
                                    item.checkState(0) == CHECKED)

    def _double_clicked(self, item, column=0):
        key = item.data(0, PLACE_ROLE)
        if key and not is_folder(key):
            self.place_action.emit("fly", key)

    def _opacity_action(self, menu, layer):
        """Строка меню с ползунком прозрачности слоя."""
        row = QWidget(menu)
        box = QHBoxLayout(row)
        box.setContentsMargins(8, 2, 8, 2)
        slider = QSlider(enum(Qt, "Orientation", "Horizontal"), row)
        slider.setRange(0, 100)
        slider.setValue(int(round((1.0 - layer.opacity()) * 100)))
        slider.setMinimumWidth(120)
        value = QLabel(row)
        row.setToolTip(tr(
            "Прозрачность слоя QGIS. Она меняется и на карте, сквозь "
            "прозрачный слой видна подложка и слои под ним."))

        def moved(percent):
            value.setText(tr("{value} %", value=percent))
            self.opacity_changed.emit(layer.id(), 1.0 - percent / 100.0)
        value.setText(tr("{value} %", value=slider.value()))
        slider.valueChanged.connect(moved)
        box.addWidget(QLabel(tr("Прозрачность"), row))
        box.addWidget(slider, 1)
        box.addWidget(value)
        action = QWidgetAction(menu)
        action.setDefaultWidget(row)
        return action

    def _menu(self, point):
        item = self.list.itemAt(point)
        menu = QMenu(self)
        if item is None:
            # Пустое место под списком: папка в конец «Моих меток».
            menu.addAction(tr("Новая папка")).triggered.connect(
                lambda: self.place_action.emit("new_folder", ""))
            menu.addAction(tr("Открыть KML или KMZ…")).triggered.connect(
                lambda: self.place_action.emit("import_kml", ""))
            menu.addAction(tr("Вставить")).triggered.connect(
                lambda: self.place_action.emit("paste", ""))
            menu.exec(self.list.viewport().mapToGlobal(point))
            return
        key = item.data(0, PLACE_ROLE)
        chosen = self.list.selected_keys()
        if key in chosen and len(chosen) > 1:
            # Несколько строк: общее для всех.
            for action, text in (
                    ("copy", tr("Копировать")),
                    ("show", tr("Показать выбранное")),
                    ("hide", tr("Скрыть выбранное")),
                    ("remove", tr("Удалить выбранное ({count})",
                                  count=len(chosen)))):
                menu.addAction(text).triggered.connect(
                    lambda _=False, a=action: self.places_action.emit(
                        a, chosen))
            menu.exec(self.list.viewport().mapToGlobal(point))
            return
        if is_folder(key):
            actions = [("tour", tr("Запустить тур")),
                       ("new_folder", tr("Новая папка")),
                       ("import_kml", tr("Открыть KML или KMZ…")),
                       ("export_kml", tr("Сохранить как KML…")),
                       ("copy", tr("Копировать")),
                       ("paste", tr("Вставить")),
                       ("rename", tr("Переименовать…")),
                       ("remove", tr("Удалить"))]
        elif key:
            actions = [("fly", tr("Подлететь"))]
            if key.startswith("line:"):
                actions.append(("tour", tr("Тур по пути")))
            actions += [("snapshot", tr("Снимок вида метки")),
                        ("properties", tr("Свойства…")),
                        ("new_folder_after", tr("Новая папка")),
                        ("copy", tr("Копировать")),
                        ("paste", tr("Вставить")),
                        ("rename", tr("Переименовать…")),
                        ("remove", tr("Удалить"))]
        if key:
            for action, text in actions:
                menu.addAction(text).triggered.connect(
                    lambda _=False, a=action: self.place_action.emit(a, key))
        elif item is self.places_group:
            menu.addAction(tr("Запустить тур")).triggered.connect(
                lambda: self.place_action.emit("tour", ""))
            menu.addAction(tr("Новая папка")).triggered.connect(
                lambda: self.place_action.emit("new_folder", ""))
            menu.addAction(tr("Открыть KML или KMZ…")).triggered.connect(
                lambda: self.place_action.emit("import_kml", ""))
            menu.addAction(tr("Сохранить как KML…")).triggered.connect(
                lambda: self.place_action.emit("export_kml", ""))
            menu.addAction(tr("Копировать")).triggered.connect(
                lambda: self.place_action.emit("copy", ""))
            menu.addAction(tr("Вставить")).triggered.connect(
                lambda: self.place_action.emit("paste", ""))
            menu.addAction(tr("Добавить слои меток в проект")).triggered \
                .connect(lambda: self.place_action.emit("project", ""))
        menu.exec(self.list.viewport().mapToGlobal(point))

    def _copy_selected(self):
        """Ctrl+C: выделенные строки, без выделения - текущая, корень
        «Мои метки» - все метки."""
        chosen = self.list.selected_keys()
        if chosen:
            self.places_action.emit("copy", chosen)
            return
        item = self.list.currentItem()
        if item is self.places_group:
            self.place_action.emit("copy", "")
        elif item is not None and item.data(0, PLACE_ROLE):
            self.place_action.emit("copy", item.data(0, PLACE_ROLE))

    def _layer_double_clicked(self, item, column=0):
        layer = QgsProject.instance().mapLayer(item.data(0, LAYER_ROLE))
        if layer is not None:
            self.fly_to_layer.emit(layer)

    def _layer_menu(self, point):
        """Меню слоя проекта: перелёт, прозрачность, трек, свойства."""
        item = self.layers.itemAt(point)
        layer_id = item.data(0, LAYER_ROLE) if item is not None else None
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id \
            else None
        if layer is None:
            return
        menu = QMenu(self)
        menu.addAction(tr("Подлететь")).triggered.connect(
            lambda: self.fly_to_layer.emit(layer))
        menu.addAction(self._opacity_action(menu, layer))
        if isinstance(layer, QgsVectorLayer) \
                and enum_int(layer.geometryType()) == 0:
            menu.addAction(tr("Трек…")).triggered.connect(
                lambda: self.track_requested.emit(layer))
        menu.addAction(tr("Свойства слоя…")).triggered.connect(
            lambda: self.layer_properties.emit(layer))
        menu.exec(self.layers.viewport().mapToGlobal(point))