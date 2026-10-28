# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Левая панель окна глобуса: поиск, два раздела, строка состояния.

Разделы сворачиваются «аккордеоном», щелчком по заголовку. Свёрнутый
раздел оставляет только заголовок, его место занимают открытые.
Решение автора от 29 сентября 2026 года.

- «Метки» - папка «Мои метки», как в Google Earth. Она есть и пустая,
  двойной щелчок по метке переносит к ней. Строки выделяются по
  несколько, с Ctrl и Shift.
- «Проект QGIS» - слои текущего проекта со своим меню и строкой «Земля
  над гридами». Отметка слоя проекта включает его на глобусе и не
  меняет видимость на карте. Прозрачность слоя проекта - свойство
  самого слоя QGIS, решение автора от 28 сентября 2026 года. Отдельный
  раздел - решение автора от 17 октября 2026 года.
- «Слои» - одним списком данные глобуса: включённые слои каталога,
  группы векторной основы, основа и рельеф. Кнопка «Добавить данные»
  ставит на место списка каталог. Решение автора от 12 октября
  2026 года.

Панель только показывает и сообщает сигналами, решает окно.
"""
import html
import os

from qgis.core import (QgsApplication, QgsPointCloudLayer, QgsProject,
                       QgsRasterLayer, QgsSettings, QgsVectorLayer,
                       QgsWkbTypes)
from qgis.PyQt.QtCore import (QEvent, QItemSelectionModel, QRect, Qt,
                              QTimer, pyqtSignal)
from qgis.PyQt.QtGui import QCursor, QFont, QIcon, QKeySequence, QPalette
from qgis.PyQt.QtWidgets import (QAbstractItemView,
                                 QHBoxLayout, QLabel,
                                 QLineEdit,
                                 QListWidget, QMenu, QPushButton,
                                 QSizePolicy, QSlider, QSplitter,
                                 QStyle,
                                 QStyledItemDelegate, QStyleOptionButton,
                                 QStyleOptionViewItem,
                                 QToolButton, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout, QWidget,
                                 QWidgetAction)

from ..core import geoid, icons, lookat
from ..core import pointcloud as cloud_core
from ..core.placetree import is_folder
from ..i18n import tr
from ..net.overlay import (AIRPORTS, BORDERS, PARKS, PEAKS, PLACES,
                           RAILWAYS, RIVERS, ROAD_REFS, ROADS, WATER,
                           WATER_NAMES)
from ..qt_compat import QAction, enum, enum_int
from .placeprops import icon_image
from .pointcloud import class_names
from .spinner import BusySpinner

# Роль данных строки: номер слоя QGIS, у строки «Глобус» - None.
LAYER_ROLE = enum_int(enum(Qt, "ItemDataRole", "UserRole"))
CHECKABLE = enum(Qt, "ItemFlag", "ItemIsUserCheckable")
CHECKED = enum(Qt, "CheckState", "Checked")
UNCHECKED = enum(Qt, "CheckState", "Unchecked")
TRISTATE = enum(Qt, "ItemFlag", "ItemIsAutoTristate")
RELIEF = "relief"  # строка рельефа в панели «Слои»
# Знак стороны шторки перед названием слоя проекта, core/sides.py.
SIDE_MARKS = {"left": "◧", "right": "◨"}
# Строки раздела «Слои» под рельефом: сетка, звёзды, облака.
GRID, STARS, CLOUDS = "grid", "stars", "clouds"
TEMPERATURE = "temperature"
BUILDINGS = "buildings"
CONTOURS = "contours"
INFRA = "infra_osm"
CABLES = "cables"
SUN = "sun"
SLOPE, ASPECT = "slope", "aspect"
QUAKES = "quakes"
FIRES = "fires"
CUTAWAY = "cutaway"
PALEO = "paleo"
PLATES = "plates"
SATELLITES = "satellites"
EXTRAS = (GRID, STARS, CLOUDS, TEMPERATURE, BUILDINGS, SUN, SLOPE, ASPECT,
          QUAKES, FIRES, PLATES, CUTAWAY, PALEO, SATELLITES)
# Роль данных строки «Моих меток»: ключ метки «вид:номер».
PLACE_ROLE = LAYER_ROLE + 1
# Роль строки записанного тура: у неё своё меню.
TOUR_ROLE = PLACE_ROLE + 1
# Строка внутри папки-переключателя: рисуется переключателем, как
# в Google Earth, а не флажком.
RADIO_ROLE = TOUR_ROLE + 1
# Строка самой папки-переключателя.
RADIO_FOLDER_ROLE = RADIO_ROLE + 1
# Строка слоя проекта в списке «Слоёв»: номер слоя QGIS.
LAYER_ID_ROLE = RADIO_FOLDER_ROLE + 1
# Строка включённого слоя каталога: ключ строки «На глобусе».
ACTIVE_ROLE = LAYER_ID_ROLE + 1
# У строки меню справа: True - «⋯», MENU_ROW - «▾», строка-выбор,
# щелчок по ней открывает меню.
MORE_ROLE = ACTIVE_ROLE + 1
MENU_ROW = "menu"
ADD_SOURCE = -1  # пункт «Добавить источник тайлов…» меню основы
MORE_WIDTH = 22  # пикселей, место «⋯» у правого края строки
FOUND_HEIGHT = 160  # пикселей, наибольшая высота списка найденных мест
# Клавиши строки поиска и списка подсказок под ней.
KEY_PRESS = enum(QEvent, "Type", "KeyPress")
KEY_DOWN = enum(Qt, "Key", "Key_Down")
KEY_UP = enum(Qt, "Key", "Key_Up")
KEY_ESCAPE = enum(Qt, "Key", "Key_Escape")
KEY_CHOOSE = (enum(Qt, "Key", "Key_Return"), enum(Qt, "Key", "Key_Enter"))
FOCUS_OUT = enum(QEvent, "Type", "FocusOut")
# Уход фокуса, после которого подсказки остаются - меню строки и смена
# окна системы.
FOCUS_KEEP = (enum(Qt, "FocusReason", "PopupFocusReason"),
              enum(Qt, "FocusReason", "ActiveWindowFocusReason"))
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
            "Границы стран и областей, реки и водоёмы, подписи на "
            "глобусе."), (
            (BORDERS, tr("Границы"), tr(
                "Границы стран ярко-жёлтые, границы областей тонкие "
                "белые. Морские границы не рисуются.")),
            (PLACES, tr("Населённые пункты"), tr(
                "Названия стран, областей, городов, посёлков и деревень. "
                "При приближении появляются всё более мелкие пункты.")),
            (WATER_NAMES, tr("Названия водоёмов"), tr(
                "Названия морей, озёр и водохранилищ, голубым курсивом.")),
            (RIVERS, tr("Реки"), tr(
                "Узкие реки синими линиями. Появляются примерно с 600 м "
                "на пиксель.")),
            (WATER, tr("Водоёмы"), tr(
                "Берега озёр, водохранилищ и широких рек обведены синей "
                "линией. Водохранилища в данных разрезаны на куски, "
                "и контур проходит и по разрезам.")),
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
        (tr("Природа"), tr("Вершины и охраняемые территории."), (
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
               "polygon": "/mIconPolygonLayer.svg",
               # Наложения: на поверхности, фото, на экране.
               "ground": "/mIconRaster.svg",
               "photo": "/mLayoutItemPicture.svg",
               "screen": "/mActionAddImage.svg",
               # 3D-модель.
               "model": "/mLayoutItem3DMap.svg"}
VIEW_ICON = "/mIconCamera.svg"  # метка «Сохранить вид» с ракурсом


def place_icon(place):
    """Значок метки: сохранённый вид, точка, линия или многоугольник.
    Вид, поставленный метке «Снимком вида», значок не меняет."""
    if getattr(place, "tour", None):
        return QgsApplication.getThemeIcon(
            "/mTemporalNavigationMovie.svg")
    if place.kind == "point" and place.shape.icon != icons.DEFAULT:
        return icon_image(place.shape.icon, place.shape.color)
    name = VIEW_ICON if lookat.is_view_mark(
        place.kind, place.shape.points, place.view) \
        else PLACE_ICONS.get(place.kind, PLACE_ICONS["point"])
    return QgsApplication.getThemeIcon(name)


def layer_kind(layer):
    """Тип слоя словами, как в списке 3D-сцены Isoliner3D."""
    if isinstance(layer, QgsRasterLayer):
        return tr("растр")
    if isinstance(layer, QgsPointCloudLayer):
        return tr("облако точек")
    if isinstance(layer, QgsVectorLayer):
        # Номер Qgis.GeometryType: 0 точки, 1 линии, 2 полигоны.
        kinds = {0: tr("точки"), 1: tr("линии"), 2: tr("полигоны")}
        return kinds.get(enum_int(layer.geometryType()), tr("таблица"))
    return tr("слой")


def hint_text(item):
    """Строка подсказки поиска (core.searchbar.Suggestion): название
    и приписка вида - метка, звезда, созвездие или прежний запрос."""
    if item.kind == "place":
        return tr("{name} - метка", name=item.text)
    if item.kind == "star":
        return tr("{name} - звезда", name=item.text)
    if item.kind == "constellation":
        return tr("{name} - созвездие", name=item.text)
    if item.kind == "action":
        return tr("{name} - {what}", name=item.text, what=item.note)
    if item.kind == "manual":
        return tr("{name} - раздел руководства", name=item.text)
    return tr("{name} - прежний запрос", name=item.text)


class RadioDelegate(QStyledItemDelegate):
    """Строки папки-переключателя и сама такая папка - кружки
    переключателей вместо флажков, как в Google Earth. Щелчок по кружку
    работает как по флажку: окно оставляет включённой одну строку
    папки. Кружок папки с точкой, когда в ней что-то показано."""

    def paint(self, painter, option, index):
        if not (index.data(RADIO_ROLE) or index.data(RADIO_FOLDER_ROLE)):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = opt.widget
        style = widget.style() if widget is not None else None
        if style is None:
            super().paint(painter, option, index)
            return
        rect = style.subElementRect(
            enum(QStyle, "SubElement", "SE_ItemViewItemCheckIndicator"),
            opt, widget)
        on = opt.checkState != UNCHECKED
        # Фон строки целиком, потом строка без флажка правее кружка:
        # значок и текст остаются на своих местах.
        style.drawPrimitive(enum(QStyle, "PrimitiveElement",
                                 "PE_PanelItemViewItem"), opt, painter,
                            widget)
        opt.features &= ~enum(QStyleOptionViewItem, "ViewItemFeature",
                              "HasCheckIndicator")
        opt.rect.setLeft(rect.right() + 1)
        style.drawControl(enum(QStyle, "ControlElement", "CE_ItemViewItem"),
                          opt, painter, widget)
        button = QStyleOptionButton()
        button.rect = rect
        # Недоступная строка, например тема на Марсе, - серый кружок.
        enabled = enum(QStyle, "StateFlag", "State_Enabled")
        button.state = (opt.state & enabled) | (
            enum(QStyle, "StateFlag", "State_On") if on
            else enum(QStyle, "StateFlag", "State_Off"))
        style.drawPrimitive(enum(QStyle, "PrimitiveElement",
                                 "PE_IndicatorRadioButton"),
                            button, painter, widget)


class LayerDelegate(RadioDelegate):
    """Строки списка «Слоёв»: у строки с меню справа «⋯». Текст
    строки обрезается до него."""

    def paint(self, painter, option, index):
        if not index.data(MORE_ROLE):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        right = opt.rect.right()
        opt.rect.setRight(right - MORE_WIDTH)
        super().paint(painter, opt, index)
        painter.save()
        painter.setPen(option.palette.color(enum(QPalette, "ColorRole",
                                                 "Text")))
        mark = "▾" if index.data(MORE_ROLE) == MENU_ROW else "⋯"
        painter.drawText(QRect(right - MORE_WIDTH, option.rect.top(),
                               MORE_WIDTH, option.rect.height()),
                         enum(Qt, "AlignmentFlag", "AlignCenter"), mark)
        painter.restore()


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
        # Прочие корни списка с метками - «Временные метки».
        self.extra_groups = []
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
        for group in [self.group] + self.extra_groups:
            if group is not None:
                look(group)
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
    # Выбрана подсказка строки поиска, core.searchbar.Suggestion.
    suggestion_chosen = pyqtSignal(object)
    # Ссылка «Разговор» под ответом помощника.
    assistant_requested = pyqtSignal()
    # Кнопка «создать метки по описанию» и ссылка «Отменить» под ответом.
    make_requested = pyqtSignal(str)
    undo_requested = pyqtSignal()
    # Ссылка «Остановить» под счётом меток, идущих потоком.
    stop_requested = pyqtSignal()
    accept_requested = pyqtSignal()
    # Ссылка строки маршрута под строкой поиска: «car», «foot», «clear».
    route_link = pyqtSignal(str)
    layer_toggled = pyqtSignal(str, bool)
    fly_to_layer = pyqtSignal(object)
    # Непрозрачность слоя 0-1 из меню слоя, свойства слоя QGIS.
    opacity_changed = pyqtSignal(str, float)
    layer_properties = pyqtSignal(object)
    # Трек точечного слоя: открыть окно настроек трека.
    track_requested = pyqtSignal(object)
    # Растр проекта включён или выключен рельефом глобуса.
    inset_toggled = pyqtSignal(str, bool)
    # Растр проекта - батиметрия водоёма: номер слоя (окно уровня воды).
    bathymetry_requested = pyqtSignal(str)
    map_year_requested = pyqtSignal(str)
    # Сторона шторки слоя: номер слоя, left, right или "" - обе.
    swipe_side_requested = pyqtSignal(str, str)
    side_swipe_toggled = pyqtSignal(bool)  # кнопка «Шторка слоёв»
    sounding_requested = pyqtSignal(str)
    volume_requested = pyqtSignal(str)
    # Растр - поверхность по отметкам, пункт меню слоя.
    grid_toggled = pyqtSignal(str, bool)
    # Векторный слой с Z - объёмом по отметкам, пункт меню слоя.
    zlayer_toggled = pyqtSignal(str, bool)
    # Слой с Z - истинные отметки и без рельефа.
    ztrue_toggled = pyqtSignal(str, bool)
    # Облако точек: номер слоя, настройки core.pointcloud.style.
    pointcloud_style = pyqtSignal(str, object)
    # Растр - изолинии в проект QGIS, пункт меню слоя.
    contours_requested = pyqtSignal(object)
    # Векторный слой - выдавливание по полю, пункт меню слоя.
    extrude_requested = pyqtSignal(object)
    # Слой проекта в «Мои метки» папкой, ui/layer_places.py.
    places_requested = pyqtSignal(object)
    # Непрозрачность земли над подземной моделью, от 0 до 1.
    ground_alpha = pyqtSignal(float)
    # Кнопка строки «Земля над гридами» - окно «Подземный режим».
    subsurface_requested = pyqtSignal()
    # Группы векторной основы, включённые в панели «Слои», множество.
    geo_changed = pyqtSignal(object)
    # Строка витрины карт NASA и погоды: открыть витрину.
    gallery_requested = pyqtSignal()
    # Подложка выбрана в группе «Основа» - номер источника.
    basemap_chosen = pyqtSignal(int)
    add_source_requested = pyqtSignal()
    # «Ещё подосновы…» меню «Основа» - категория «Подоснова» каталога.
    bases_requested = pyqtSignal()
    relief_toggled = pyqtSignal(bool)
    # Меню строки «Рельеф»: модель высот суши, глубины морей,
    # окно «Источники данных».
    relief_model_chosen = pyqtSignal(str)
    sea_toggled = pyqtSignal(bool)
    sea_model_chosen = pyqtSignal(str)
    sources_requested = pyqtSignal()
    # Строка сетки, звёзд или облаков: ключ из EXTRAS и флажок.
    extra_toggled = pyqtSignal(str, bool)
    # Раздел «На глобусе»: флажок строки (слой выключен, строка
    # остаётся), убрать строку, непрозрачность 0..1, слой в проект QGIS.
    # Ключ - ключ строки витрины или «map» - карта витрины.
    active_toggled = pyqtSignal(str, bool)
    active_off = pyqtSignal(str)
    active_opacity = pyqtSignal(str, float)
    active_export = pyqtSignal(str)
    # Вертикальный масштаб режима «Геоид» из меню «⋯» его строки.
    geoid_scale_changed = pyqtSignal(float)
    # Пункт «Растягивать кору» меню строки «Разрез Земли».
    cutaway_stretch_changed = pyqtSignal(bool)
    # Пункт «Тени» меню строки «Солнце» - тени в кадре.
    sun_shadows_changed = pyqtSignal(bool)
    # Пункт «Томография мантии» того же меню.
    cutaway_tomo_changed = pyqtSignal(bool)
    # Пункт «Кора CRUST1.0 в проект QGIS…» того же меню.
    crust_export = pyqtSignal()
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
    # Выделение «Моих меток» сменилось: ключи выделенных строк.
    places_selected = pyqtSignal(object)
    # Ползунок непрозрачности выделенного сдвинут: значение 0..1.
    opacity_moved = pyqtSignal(float)
    # Папка раскрыта или свёрнута.
    folder_expanded = pyqtSignal(str, bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.place = QLineEdit(self)
        # Пример в пустой строке: место или тема. Решение автора от
        # 5 октября 2026 года - кнопки помощника у строки нет, параметры
        # помощника - в окне «Свойства вида».
        self.place.setPlaceholderText(tr("Путешествия Колумба"))
        self.place.setClearButtonEnabled(True)
        self.place.setToolTip(tr(
            "Место, координаты, тема или действие. Название места или "
            "координаты, например Пермь или 58.0105, 56.2294, дают "
            "перелёт. Слой, карта или окно модуля, например «течения», "
            "«линейка» или «снимки», находятся по названию и включаются "
            "из подсказки. Тема становится метками с датами, вопрос "
            "словами уходит помощнику. Ctrl+K из любого места окна ставит "
            "курсор в эту строку."))
        self.place.returnPressed.connect(self._enter)
        self.place.textChanged.connect(self._search_text)
        self.place.textEdited.connect(self._text_edited)
        go = QPushButton(tr("Поиск"), self)
        go.setToolTip(tr(
            "Найти то, что введено в строке. Место - перелёт к нему, "
            "несколько найденных мест - список ниже. Тема без места на "
            "карте - метки по ней от помощника, если в окне «Свойства "
            "вида» настроен помощник."))
        go.clicked.connect(self._enter)
        shortcut = QAction(self.place)
        shortcut.setShortcut(QKeySequence("Ctrl+Return"))
        shortcut.setShortcutContext(
            enum(Qt, "ShortcutContext", "WidgetShortcut"))
        shortcut.triggered.connect(self._make)
        self.place.addAction(shortcut)
        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.addWidget(self.place, 1)
        top.addWidget(go, 0)
        # Значок ожидания: ответ модели помощника или службы поиска мест
        # ещё не пришёл. Виден только во время ожидания.
        self.busy = BusySpinner(self)
        top.addWidget(self.busy, 0)
        # Подсказки при вводе: метки, небо, прежние запросы. Их даёт
        # окно функцией suggest_source(текст) -> список Suggestion
        # (core/searchbar.py). Список встроен в панель и виден, пока
        # в нём есть строки. QCompleter не годится: Enter при открытом
        # списке срабатывал бы дважды.
        self.suggest_source = None
        self._hints = []
        self.hints = QListWidget(self)
        self.hints.setVisible(False)
        self.hints.setMaximumHeight(FOUND_HEIGHT)
        self.hints.itemClicked.connect(
            lambda item: self._choose_hint(self.hints.row(item)))
        # «Вниз» из строки - в список, «вверх» с первой строки - обратно,
        # Enter выбирает подсказку, Escape прячет список.
        self.place.installEventFilter(self)
        self.hints.installEventFilter(self)
        # Найденные места. Список виден, пока в нём есть строки.
        self.found = QListWidget(self)
        self.found.setVisible(False)
        self.found.setMaximumHeight(FOUND_HEIGHT)
        self.found.itemClicked.connect(
            lambda item: self.place_chosen.emit(self.found.row(item)))
        self.found.itemActivated.connect(
            lambda item: self.place_chosen.emit(self.found.row(item)))
        # Ответ помощника на просьбу из строки поиска. Виден, пока
        # в нём есть текст.
        self.answer = QLabel(self)
        self.answer.setWordWrap(True)
        self.answer.setVisible(False)
        self.answer.setTextInteractionFlags(
            enum(Qt, "TextInteractionFlag", "TextBrowserInteraction"))
        self.answer.linkActivated.connect(self._answer_link)

        self.list = PlaceTree(self)
        self.list.setItemDelegate(RadioDelegate(self.list))
        # Кнопка тура под списком, как в Google Earth: активна у пути
        # и у папки «Мои метки».
        self.tour_button = QToolButton(self)
        self.tour_button.setText("▶\ufe0f")
        self.tour_button.setEnabled(False)
        self.tour_button.clicked.connect(self._tour_clicked)
        self.list.currentItemChanged.connect(self._tour_state)
        # Ползунок непрозрачности выделенного под списком, как под
        # «Местами» Google Earth Pro. Просьба автора от 10 октября
        # 2026 года.
        self.opacity = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.opacity.setRange(0, 100)
        self.opacity.setValue(100)
        self.opacity.setEnabled(False)
        self.opacity.setToolTip(tr(
            "Непрозрачность выделенных меток, путей, многоугольников, "
            "картинок и содержимого папок. Влево - прозрачнее. Значение "
            "сохраняется в «Моих метках» и в KML."))
        self.opacity.valueChanged.connect(self._opacity_moved)
        self._opacity_quiet = False
        self.list.itemSelectionChanged.connect(
            lambda: self.places_selected.emit(self.list.selected_keys()))
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
        # «Временные метки», как в Google Earth, - папка файла меток
        # с ключом temp_key, в списке своим корнем под «Моими метками».
        # Окно ставит ключ до set_places.
        self.temp_key = None
        self.temp_item = None
        # Флажок папки меняет все метки, каждая шлёт itemChanged. Метки
        # переписываются в файл после того, как Qt обойдёт все строки,
        # иначе список перестраивался бы посреди обхода.
        self._place_states = {}
        self._place_timer = QTimer(self)
        self._place_timer.setSingleShot(True)
        self._place_timer.timeout.connect(self._emit_places)
        # Раздел «Слои» - одним списком всё, что на глобусе: включённые
        # слои каталога, группы векторной основы, слои проекта группой,
        # основа и рельеф. Решение автора от 12 октября 2026 года - «На
        # глобусе тоже не очень, давай покомпактней», каталог выезжает
        # в панели, проект - группой. Строка в одну линию, без виджетов,
        # меню строки - «⋯» справа и правая кнопка.
        self.geo = QTreeWidget(self)
        self.geo.setHeaderHidden(True)
        # Темы и подложки - одна из всех, такие строки рисуются кружками.
        self.geo.setItemDelegate(LayerDelegate(self.geo))
        self.geo.setContextMenuPolicy(
            enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.geo.customContextMenuRequested.connect(self._geo_menu)
        self.geo.itemDoubleClicked.connect(self._geo_double_clicked)
        # Щелчок по группе меняет все её строки, каждая шлёт itemChanged.
        # Изменения собираются за один проход цикла событий. Сигнал
        # подключается после того, как строки построены.
        self._geo_timer = QTimer(self)
        self._geo_timer.setSingleShot(True)
        self._geo_timer.timeout.connect(self._emit_geo)
        self._layer_states = {}
        self._layer_timer = QTimer(self)
        self._layer_timer.setSingleShot(True)
        self._layer_timer.timeout.connect(self._emit_layers)
        self.geo_items = {}
        # Последнее сообщённое окну состояние панели «Слои».
        self._relief = False
        self._groups = set()
        self._basemap = 0
        self.geo.itemClicked.connect(self._geo_clicked)
        # Включённые слои каталога - строки в начале списка, set_active.
        self.active_rows = {}
        self._active_shape = None
        self._active_values = {}  # ключ - (непрозрачность, в проект)
        # Масштаб геоида для ползунка меню «⋯», ставит окно глобуса.
        self.geoid_scale = geoid.SCALE
        # Пункты «Растягивать кору» и «Томография мантии», ставит окно
        # глобуса.
        self.cutaway_stretch = True
        # Пункт «Тени» строки «Солнце», ставит окно глобуса.
        self.sun_shadows = True
        self.cutaway_tomo = False
        # Группы векторной основы. Группа видна, пока в ней что-то
        # включено, и после снятия флажков - до «Убрать с глобуса».
        self.vector_groups = []
        self._vector_seen = set()
        for title, tip, rows in geo_tree():
            group = QTreeWidgetItem(self.geo, [title])
            group.setToolTip(0, tip)
            group.setData(0, MORE_ROLE, True)
            group.setFlags(group.flags() | CHECKABLE | TRISTATE)
            for key, text, row_tip in rows:
                item = QTreeWidgetItem(group, [text])
                item.setData(0, LAYER_ROLE, key)
                item.setToolTip(0, row_tip)
                item.setFlags(item.flags() | CHECKABLE)
                item.setCheckState(0, UNCHECKED)
                self.geo_items[key] = item
            self.vector_groups.append(group)
        # Сетка, здания, горизонтали, ЛЭП и кабели включает каталог,
        # в списке они - строки включённого. Скрытые строки здесь
        # держат их флажки для set_extras и extra_toggled.
        self.extra_items = {}
        self._extras = {}
        for key in (GRID, BUILDINGS, CONTOURS, INFRA, CABLES):
            item = QTreeWidgetItem(self.geo, [key])
            item.setData(0, LAYER_ROLE, key)
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, UNCHECKED)
            item.setHidden(True)
            self.extra_items[key] = item
        # Слои проекта - свой раздел «Проект QGIS» со своим списком, отметка
        # включает слой на глобусе и не меняет видимость на карте QGIS. С
        # 12 октября 2026 года они были группой списка «Слоёв», решение
        # автора от 17 октября 2026 года - вернуть разделом: у слоёв
        # проекта свои свойства и своё меню, раздел «богаче».
        self.project_tree = QTreeWidget(self)
        self.project_tree.setHeaderHidden(True)
        self.project_tree.setRootIsDecorated(False)
        self.project_tree.setItemDelegate(LayerDelegate(self.project_tree))
        self.project_tree.setContextMenuPolicy(
            enum(Qt, "ContextMenuPolicy", "CustomContextMenu"))
        self.project_tree.customContextMenuRequested.connect(
            lambda point: self._geo_menu(point, self.project_tree))
        self.project_tree.itemDoubleClicked.connect(self._geo_double_clicked)
        self.project_tree.itemClicked.connect(
            lambda item, column: self._geo_clicked(item, column,
                                                   self.project_tree))
        self.project_tree.itemChanged.connect(self._geo_changed)
        self.project_group = self.project_tree.invisibleRootItem()
        # Земля над подземной моделью: ползунок непрозрачности, виден,
        # пока модель есть. Просьба автора от 8 октября 2026 года -
        # прозрачность и невидимость поверхности над гридами.
        ground = QWidget(self)
        self.ground_row = ground
        row = QHBoxLayout(ground)
        row.setContentsMargins(0, 0, 4, 0)
        row.addWidget(QLabel(tr("Земля над гридами"), ground))
        self.ground_slider = QSlider(enum(Qt, "Orientation", "Horizontal"),
                                     ground)
        self.ground_slider.setRange(0, 100)
        self.ground_slider.setToolTip(tr(
            "Непрозрачность земли над подземной моделью - гридами "
            "по отметкам, кровлями, скважинами. Вправо земля "
            "непрозрачна, влево прозрачнее, у левого края её не видно. "
            "Вне контура данных земля не меняется."))
        self.ground_slider.valueChanged.connect(
            lambda value: self.ground_alpha.emit(value / 100.0))
        row.addWidget(self.ground_slider, 1)
        under = QToolButton(ground)
        under.setText("…")
        under.setAutoRaise(True)
        under.setToolTip(tr(
            "Окно «Подземный режим» - вырез блока, камера под землёй "
            "и шаблон данных."))
        under.clicked.connect(
            lambda _=False: self.subsurface_requested.emit())
        row.addWidget(under)
        ground.setVisible(False)
        # Шторка слоёв проекта: стороны - подменю «Шторка» меню слоя,
        # кнопка включает и снимает шторку, видна, пока стороны есть.
        self.swipe_sides = {}
        self.swipe_button = QToolButton(self)
        self.swipe_button.setText(tr("⇆ Шторка слоёв"))
        self.swipe_button.setCheckable(True)
        self.swipe_button.setAutoRaise(True)
        self.swipe_button.setToolTip(tr(
            "Сравнение слоёв шторкой. Слои «Слева» видны левее шторки, "
            "«Справа» - правее, прочие - на обеих сторонах. Сторона "
            "слоя - подменю «Шторка» меню слоя, шторка тянется мышью."))
        self.swipe_button.toggled.connect(self.side_swipe_toggled.emit)
        self.swipe_button.setVisible(False)
        # Основа и рельеф - строки наверху списка, как прочие, у обеих
        # меню выбора «▾». Просьба автора от 12 октября 2026 года - «два
        # нижних слоя вверх», «выбор Esri не кнопкой, как все пункты, но
        # с выпадающим списком», «рельеф тоже выпадающим списком».
        self.base_item = QTreeWidgetItem([tr("Основа")])
        self.base_item.setData(0, MORE_ROLE, MENU_ROW)
        self.base_item.setToolTip(0, tr(
            "Снимки или карта на поверхности. Щелчок по строке - выбор "
            "подложки и свой источник тайлов. Esri World Imagery - пример "
            "подложки, условия её использования задаёт Esri."))
        self.base_item.setIcon(0, QgsApplication.getThemeIcon(
            "/mIconRaster.svg"))
        self.base_item.setFlags(enum(Qt, "ItemFlag", "ItemIsEnabled"))
        self.geo.insertTopLevelItem(0, self.base_item)
        self._basemap_names = []
        self._own_basemap = None
        relief = QTreeWidgetItem([tr("Рельеф")])
        relief.setData(0, LAYER_ROLE, RELIEF)
        relief.setData(0, MORE_ROLE, MENU_ROW)
        relief.setToolTip(0, tr(
            "Высоты поднимают поверхность и дают отмывку склонов. Флажок "
            "включает рельеф, щелчок по названию - выбор высот суши "
            "и глубины морей. Высоты Земли - Mapzen Terrain Tiles, "
            "Марса - MOLA, Луны - LOLA. Вертикальный масштаб - "
            "в свойствах вида."))
        relief.setFlags(relief.flags() | CHECKABLE)
        relief.setCheckState(0, UNCHECKED)
        self.geo.insertTopLevelItem(1, relief)
        self.geo_items[RELIEF] = relief
        # Выбор рельефа: (ключ, название в меню, коротко в строке),
        # выбранный ключ, глубины морей. Их даёт окно, set_relief_menu.
        self._relief_models = []
        self._relief_model = ""
        self._sea = True
        # Строки включённого встают под основой и рельефом.
        self._active_at = 2
        self._theme = ""
        self.geo.itemChanged.connect(self._geo_changed)
        # Растры проекта - рельеф глобуса, отметки меню слоя.
        self.inset_ids = set()
        # Растры проекта - поверхности по отметкам под землёй.
        self.grid_ids = set()
        self.zlayer_ids = set()  # векторные слои объёмом по отметкам Z
        self.ztrue_ids = set()  # из них - с истинными отметками Z
        # Облака точек: настройки и встреченные классы по номеру слоя.
        self.pointcloud_styles = {}
        self.pointcloud_classes = {}
        # Папка - сетевая ссылка KML: её меню получает «Загрузить заново».
        self.is_link = lambda key: False
        # Кнопка каталога над списком, каталог - отдельным окном.
        self.add_data = QPushButton(tr("Добавить данные"), self)
        self.add_data.setIcon(QIcon(os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "maps.svg")))
        self.add_data.setToolTip(tr(
            "Каталог карт и слоёв - карты NASA, прогноз погоды, пожары, "
            "небо, недра, инфраструктура, анализ рельефа и строки "
            "векторной основы. Каталог открывается отдельным окном, "
            "его можно держать открытым рядом с глобусом."))
        self.add_data.clicked.connect(
            lambda _=False: self.gallery_requested.emit())
        page = QWidget(self)
        page_layout = QVBoxLayout(page)
        page_layout.setContentsMargins(0, 0, 0, 0)
        page_layout.setSpacing(2)
        page_layout.addWidget(self.add_data)
        page_layout.addWidget(self.geo, 1)
        upper = QWidget(self)
        upper_layout = QVBoxLayout(upper)
        upper_layout.setContentsMargins(0, 0, 0, 0)
        upper_layout.setSpacing(2)
        upper_layout.addWidget(self.list, 1)
        tour_row = QHBoxLayout()
        tour_row.addWidget(self.opacity, 1)
        tour_row.addWidget(self.tour_button)
        upper_layout.addLayout(tour_row)
        project = QWidget(self)
        project_layout = QVBoxLayout(project)
        project_layout.setContentsMargins(0, 0, 0, 0)
        project_layout.setSpacing(2)
        project_layout.addWidget(self.project_tree, 1)
        project_layout.addWidget(self.swipe_button)
        project_layout.addWidget(ground)
        self.sections = [
            Section("places", tr("Метки"), upper, tr(
                "Свернуть или развернуть «Мои метки»."), self),
            Section("project", tr("Проект QGIS"), project, tr(
                "Слои текущего проекта QGIS в порядке карты. Отметка "
                "показывает слой на глобусе, видимость на карте QGIS не "
                "меняется. Меню слоя - «⋯» справа или правая кнопка."),
                self),
            Section("base", tr("Слои"), page, tr(
                "Свернуть или развернуть слои на глобусе."), self)]
        split = QSplitter(enum(Qt, "Orientation", "Vertical"), self)
        split.setChildrenCollapsible(False)
        for n, section in enumerate(self.sections):
            split.addWidget(section)
            split.setStretchFactor(n, (3, 2, 4)[n])
        self.split = split

        self.status = QLabel(self)
        self.status.setWordWrap(True)
        # Ширину строки задаёт панель, а не текст: длинное слово без
        # пробелов, например адрес в ошибке сети, раздвигало панель на
        # весь экран, 11 октября 2026 года.
        self.status.setSizePolicy(
            enum(QSizePolicy, "Policy", "Ignored"),
            enum(QSizePolicy, "Policy", "Preferred"))
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
        layout.addWidget(self.hints)
        layout.addWidget(self.found)
        layout.addWidget(self.answer)
        layout.addWidget(split, 1)
        layout.addWidget(self.status, 0)
        self.set_layers([], set())
        self._tour_state()

    def _search_text(self, text):
        """Пустое поле поиска закрывает списки и снимает метку."""
        if not text.strip():
            self.hide_hints()
            self.set_found([])
            self.set_answer("")
            self.search_cleared.emit()

    def _enter(self, checked=False):
        """Enter в строке поиска и кнопка «Поиск»: подсказки прячутся,
        запрос уходит окну."""
        self.hide_hints()
        self.fly_text.emit(self.place.text())

    def _make(self, checked=False):
        """Кнопка помощника, Ctrl+Enter и ссылка под ответом: метки
        по описанию в строке."""
        self.hide_hints()
        self.make_requested.emit(self.place.text())

    # Подсказки строки поиска.

    def _text_edited(self, text):
        """Правка строки пользователем обновляет подсказки. Текст,
        поставленный программой, сюда не приходит."""
        if text.strip():
            self.show_hints(text)
        else:
            self.hide_hints()

    def show_hints(self, text):
        """Подсказки к тексту от поставщика suggest_source. Пустой
        текст - прежние запросы."""
        source = self.suggest_source
        self.set_hints(source(text) if source is not None else [])

    def set_hints(self, items):
        """Строки подсказок, список Suggestion. Пустой список прячет
        их. Высота - по строкам, не больше FOUND_HEIGHT."""
        self._hints = list(items)
        self.hints.clear()
        self.hints.addItems([hint_text(item) for item in self._hints])
        for row, item in enumerate(self._hints):
            if item.kind == "manual" and item.note:
                # Абзац раздела, где больше всего слов запроса.
                self.hints.item(row).setToolTip(item.note)
        if self._hints:
            row = self.hints.sizeHintForRow(0)
            height = row * len(self._hints) + 2 * self.hints.frameWidth()
            self.hints.setFixedHeight(
                min(height, FOUND_HEIGHT) if row > 0 else FOUND_HEIGHT)
        self.hints.setVisible(bool(self._hints))

    def hide_hints(self):
        """Список подсказок пуст и спрятан."""
        self.set_hints([])

    def set_busy(self, on, tip=""):
        """Значок ожидания у строки поиска, tip - что именно ждётся."""
        self.busy.set_busy(on, tip)

    def _choose_hint(self, row):
        """Подсказка выбрана щелчком или Enter: список прячется, выбор
        уходит окну."""
        if not 0 <= row < len(self._hints):
            return
        item = self._hints[row]
        if self.hints.hasFocus():
            self.place.setFocus()
        self.hide_hints()
        self.suggestion_chosen.emit(item)

    def eventFilter(self, watched, event):
        """Клавиши строки поиска и списка подсказок."""
        if event.type() == KEY_PRESS and (
                watched is self.place or watched is self.hints) \
                and self._hint_key(watched, event.key()):
            return True
        if event.type() == FOCUS_OUT and (
                watched is self.place or watched is self.hints) \
                and event.reason() not in FOCUS_KEEP:
            # Фокус ещё не на новом виджете, проверка - после события.
            QTimer.singleShot(0, self._focus_left)
        return super().eventFilter(watched, event)

    def _focus_left(self):
        """Фокус ушёл из строки поиска и списка подсказок, например
        щелчком по глобусу, - подсказки прячутся."""
        if self._hints and not (self.place.hasFocus()
                                or self.hints.hasFocus()):
            self.hide_hints()

    def _hint_key(self, watched, key):
        """Клавиша строки поиска или списка подсказок. Истина - клавиша
        обработана здесь и дальше не идёт."""
        if key == KEY_ESCAPE:
            if not self._hints:
                return False
            self.hide_hints()
            self.place.setFocus()
            return True
        if watched is self.place:
            if key != KEY_DOWN:
                return False
            # В пустой строке «вниз» показывает прежние запросы.
            if not self._hints:
                self.show_hints(self.place.text())
            if self._hints:
                self.hints.setFocus()
                self.hints.setCurrentRow(0)
            return True
        row = self.hints.currentRow()
        if key == KEY_UP and row <= 0:
            self.hints.setCurrentRow(-1)
            self.place.setFocus()
            return True
        if key in KEY_CHOOSE:
            self._choose_hint(row)
            return True
        return False

    def _answer_link(self, link):
        if link == "undo":
            self.undo_requested.emit()
        elif link == "stop":
            self.stop_requested.emit()
        elif link == "make":
            self._make()
        elif link == "accept":
            self.accept_requested.emit()
        elif link.startswith("route:"):
            self.route_link.emit(link[len("route:"):])
        else:
            self.assistant_requested.emit()

    def set_ground(self, shown, alpha=1.0):
        """Строка «Земля над гридами»: видна ли и непрозрачность."""
        self.ground_row.setVisible(bool(shown))
        if shown:
            self.ground_slider.blockSignals(True)
            self.ground_slider.setValue(int(round(float(alpha) * 100)))
            self.ground_slider.blockSignals(False)

    def set_answer(self, text, undo=False, make="", stop=False,
                   accept=False, links=(), talk=True):
        """Ответ помощника под строкой поиска со ссылкой на разговор.
        Пустой текст прячет его. undo - ещё ссылка «Отменить» для
        только что созданных меток. make - тема строки: ссылка «Создать
        метки по теме» после поиска по названию. accept - ссылка
        «Записать в «Мои метки»» для документа, который предложила
        модель. links - свои ссылки (адрес, текст), talk=False - без
        ссылки на разговор, это строка маршрута."""
        if not text:
            self.answer.clear()
            self.answer.setVisible(False)
            return
        body = html.escape(text).replace("\n", "<br>")
        if accept:
            body += ' <a href="accept">{}</a>'.format(
                html.escape(tr("Записать в «Мои метки»")))
        if make:
            body += ' <a href="make">{}</a>'.format(html.escape(tr(
                "Создать метки по теме «{topic}»", topic=make)))
        if undo:
            body += ' <a href="undo">{}</a>'.format(
                html.escape(tr("Отменить")))
        if stop:
            # Метки идут потоком: остановка оставляет пришедшие целиком.
            body += ' <a href="stop">{}</a>'.format(
                html.escape(tr("Остановить")))
        for href, label in links:
            body += ' <a href="{}">{}</a>'.format(html.escape(href),
                                                 html.escape(label))
        if talk:
            body += ' <a href="assistant">{}</a>'.format(
                html.escape(tr("Разговор…")))
        self.answer.setText(body)
        self.answer.setVisible(True)

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
        self._vector_rows()

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

    def set_earth(self, earth, relief=False):
        """Земля или другое тело. У Марса и Луны векторная основа,
        облака, температура, здания, солнце и слои проекта недоступны,
        флажки остаются как были. Рельеф доступен, если у тела есть
        высоты, relief."""
        for key, item in self.geo_items.items():
            off = not earth and not (key == "relief" and relief)
            item.setDisabled(off)
            parent = item.parent()
            if parent is not None:
                parent.setDisabled(off)
        self.extra_items[BUILDINGS].setDisabled(not earth)
        self.extra_items[INFRA].setDisabled(not earth)
        self.extra_items[CABLES].setDisabled(not earth)
        self.project_tree.setDisabled(not earth)

    def set_active(self, rows):
        """Включённые слои каталога - строки в начале списка «Слоёв»:
        (ключ, название, непрозрачность 0..1 или None, можно ли
        в проект, включён ли). Выключенный флажком слой остаётся
        строкой, замечание автора от 11 октября 2026 года - иначе его
        приходилось искать в каталоге заново. Строка в одну линию,
        непрозрачность и выгрузка - в меню «⋯», решение автора от
        12 октября 2026 года. Сигналы при этом не идут."""
        shape = [(key, title) for key, title, _, _, _ in rows]
        self.geo.blockSignals(True)
        if shape != self._active_shape:
            self._active_shape = shape
            for item in self.active_rows.values():
                index = self.geo.indexOfTopLevelItem(item)
                if index >= 0:
                    self.geo.takeTopLevelItem(index)
            self.active_rows = {}
            for n, (key, title, _, _, _) in enumerate(rows):
                item = QTreeWidgetItem([title])
                item.setData(0, ACTIVE_ROLE, key)
                item.setData(0, MORE_ROLE, True)
                item.setToolTip(0, tr(
                    "{name}. Флажок выключает слой, строка остаётся. Меню "
                    "«⋯» - непрозрачность, в проект QGIS, убрать с "
                    "глобуса.", name=title))
                item.setFlags((item.flags() | CHECKABLE) & ~DRAG & ~DROP)
                self.geo.insertTopLevelItem(self._active_at + n, item)
                self.active_rows[key] = item
        for key, _, opacity, export, on in rows:
            self.active_rows[key].setCheckState(0, CHECKED if on
                                                else UNCHECKED)
            self._active_values[key] = (opacity, export)
        self.geo.blockSignals(False)

    def active_checked(self, key):
        """Флажок строки key включённого: стоит ли он."""
        item = self.active_rows.get(key)
        return item is not None and item.checkState(0) == CHECKED

    def set_active_checked(self, key, on):
        """Флажок строки key, как щелчок мышью: сигнал идёт."""
        self.active_rows[key].setCheckState(0, CHECKED if on else UNCHECKED)

    def _active_menu(self, key, pos):
        """Меню «⋯» включённого слоя: непрозрачность, в проект QGIS,
        убрать с глобуса."""
        opacity, export = self._active_values.get(key, (None, False))
        menu = QMenu(self)
        if opacity is not None:
            def moved(value, key=key):
                old = self._active_values.get(key, (None, False))
                self._active_values[key] = (value, old[1])
                self.active_opacity.emit(key, value)
            menu.addAction(self._slider_action(
                menu, tr("Непрозрачность"), opacity, moved, tr(
                    "Непрозрачность слоя. Вправо слой непрозрачен, влево "
                    "прозрачнее.")))
        if key == "geoid":
            menu.addAction(self._geoid_scale_action(menu))
        if key == "sun":
            shadows = menu.addAction(tr("Тени"))
            shadows.setCheckable(True)
            shadows.setChecked(self.sun_shadows)
            shadows.setToolTip(tr(
                "Тени рельефа, зданий и 3D-моделей вблизи камеры, в радиусе "
                "до 5 км от точки взгляда. Без флажка - свет солнца без "
                "теней, кадр рисуется быстрее."))
            menu.setToolTipsVisible(True)

            def shadows_toggled(on):
                self.sun_shadows = bool(on)
                self.sun_shadows_changed.emit(self.sun_shadows)
            shadows.toggled.connect(shadows_toggled)
        if key == "cutaway":
            stretch = menu.addAction(tr("Растягивать кору"))
            stretch.setCheckable(True)
            stretch.setChecked(self.cutaway_stretch)
            stretch.setToolTip(tr(
                "Растягивает глубины до 400 км тем сильнее, чем дальше "
                "камера, и издалека видны кора и верхняя мантия. Без "
                "флажка все глубины в настоящем масштабе."))
            menu.setToolTipsVisible(True)

            def toggled(on):
                self.cutaway_stretch = bool(on)
                self.cutaway_stretch_changed.emit(self.cutaway_stretch)
            stretch.toggled.connect(toggled)
            tomo = menu.addAction(tr("Томография мантии"))
            tomo.setCheckable(True)
            tomo.setChecked(self.cutaway_tomo)
            tomo.setToolTip(tr(
                "Раскрашивает мантию на гранях по отклонению скорости "
                "сейсмических волн от модели PREM - модель SEISGLOB2. "
                "Красная мантия медленнее и горячее, синяя быстрее "
                "и холоднее. Первое включение скачивает около 28 МБ."))

            def tomo_toggled(on):
                self.cutaway_tomo = bool(on)
                self.cutaway_tomo_changed.emit(self.cutaway_tomo)
            tomo.toggled.connect(tomo_toggled)
            crust_item = menu.addAction(tr("Кора CRUST1.0 в проект QGIS…"))
            crust_item.setToolTip(tr(
                "Отметки кровель трёх слоёв осадков, трёх слоёв коры и Мохо "
                "по модели CRUST1.0 в рамке вида - растры GeoTIFF в метрах "
                "с шагом 1°, группой в проект QGIS."))
            crust_item.triggered.connect(
                lambda _=False: QTimer.singleShot(
                    0, self.crust_export.emit))
        if export:
            menu.addAction(tr("В проект QGIS…")).triggered.connect(
                lambda _=False: self.active_export.emit(key))
        menu.addAction(tr("Убрать с глобуса")).triggered.connect(
            lambda _=False: QTimer.singleShot(
                0, lambda: self.active_off.emit(key)))
        menu.exec(pos)

    def _slider_action(self, menu, title, value, moved, tip):
        """Строка меню с ползунком 0..100 % и числом. moved получает
        долю 0..1."""
        row = QWidget(menu)
        box = QHBoxLayout(row)
        box.setContentsMargins(8, 2, 8, 2)
        slider = QSlider(enum(Qt, "Orientation", "Horizontal"), row)
        slider.setRange(0, 100)
        slider.setValue(int(round(float(value) * 100)))
        slider.setMinimumWidth(120)
        label = QLabel(tr("{value} %", value=slider.value()), row)
        row.setToolTip(tip)

        def changed(percent):
            label.setText(tr("{value} %", value=percent))
            moved(percent / 100.0)
        slider.valueChanged.connect(changed)
        box.addWidget(QLabel(title, row))
        box.addWidget(slider, 1)
        box.addWidget(label)
        action = QWidgetAction(menu)
        action.setDefaultWidget(row)
        return action

    def _geoid_scale_action(self, menu):
        """Строка меню с ползунком масштаба геоида по ступеням
        geoid.SCALES. Глобус меняет масштаб сразу при движении."""
        row = QWidget(menu)
        box = QHBoxLayout(row)
        box.setContentsMargins(8, 2, 8, 2)
        slider = QSlider(enum(Qt, "Orientation", "Horizontal"), row)
        slider.setRange(0, len(geoid.SCALES) - 1)
        slider.setPageStep(1)
        slider.setValue(geoid.scale_step(self.geoid_scale))
        slider.setMinimumWidth(120)
        label = QLabel(geoid.scale_text(self.geoid_scale), row)
        row.setToolTip(tr(
            "Во сколько раз растянуты высоты геоида над эллипсоидом. "
            "Вправо горбы и впадины глубже, влево Земля круглее. Разрез "
            "Земли следует за поверхностью."))

        def changed(step):
            self.geoid_scale = geoid.SCALES[step]
            label.setText(geoid.scale_text(self.geoid_scale))
            self.geoid_scale_changed.emit(self.geoid_scale)
        slider.valueChanged.connect(changed)
        box.addWidget(QLabel(tr("Масштаб"), row))
        box.addWidget(slider, 1)
        box.addWidget(label)
        action = QWidgetAction(menu)
        action.setDefaultWidget(row)
        return action

    def _vector_menu(self, group, pos):
        """Меню «⋯» группы векторной основы: убрать с глобуса."""
        menu = QMenu(self)
        menu.addAction(tr("Убрать с глобуса")).triggered.connect(
            lambda _=False: self._vector_off(group))
        menu.exec(pos)

    def _vector_off(self, group):
        """Группа векторной основы выключена и ушла из списка."""
        self._vector_seen.discard(id(group))
        self.geo.blockSignals(True)
        for i in range(group.childCount()):
            group.child(i).setCheckState(0, UNCHECKED)
        self.geo.blockSignals(False)
        self._emit_geo()
        self._vector_rows()

    def _vector_rows(self):
        """Группа векторной основы видна, пока в ней что-то включено,
        и после снятия флажков - до «Убрать с глобуса»."""
        for group in self.vector_groups:
            on = any(group.child(i).checkState(0) == CHECKED
                     for i in range(group.childCount()))
            if on:
                self._vector_seen.add(id(group))
            group.setHidden(id(group) not in self._vector_seen)

    def section(self, name):
        """Раздел панели по имени: «places» или «base»."""
        return next(s for s in self.sections if s.name == name)

    def set_theme(self, key, name=""):
        """Карта каталога key на глобусе, "" - ни одной, name - её
        название. Сигналы не идут."""
        self._theme = key or ""
        self._extras[FIRES] = self._theme == FIRES
        self._extras[TEMPERATURE] = self._theme == TEMPERATURE

    def _geo_changed(self, item):
        key = item.data(0, ACTIVE_ROLE)
        if key:
            # Сигнал - после прохода цикла событий: Qt ещё в обработчике
            # флажка, а окно перестроит строки.
            on = item.checkState(0) == CHECKED
            QTimer.singleShot(0, lambda: self.active_toggled.emit(key, on))
            return
        layer_id = item.data(0, LAYER_ID_ROLE)
        if layer_id:
            self._layer_states[layer_id] = item.checkState(0) == CHECKED
            self._layer_timer.start(0)
            return
        if item.data(0, LAYER_ROLE):
            self._geo_timer.start(0)

    def _emit_layers(self):
        states, self._layer_states = self._layer_states, {}
        for layer_id, on in states.items():
            self.layer_toggled.emit(layer_id, on)

    def _geo_clicked(self, item, column, tree=None):
        # Строка могла исчезнуть между нажатием и отпусканием кнопки,
        # тогда Qt присылает щелчок без строки.
        if item is None or not item.data(0, MORE_ROLE):
            return
        tree = tree or self.geo
        rect = tree.visualItemRect(item)
        pos = tree.viewport().mapFromGlobal(QCursor.pos())
        if item.data(0, MORE_ROLE) == MENU_ROW:
            # Строка-выбор: меню по щелчку на названии, флажок рельефа
            # остаётся флажком.
            box = self.geo.style().pixelMetric(enum(
                QStyle, "PixelMetric", "PM_IndicatorWidth"))
            check = bool(item.flags() & CHECKABLE)
            if not check or pos.x() > rect.left() + box + 4:
                self._row_menu(item, self.geo.viewport().mapToGlobal(
                    rect.bottomLeft()))
            return
        if pos.x() >= rect.right() - MORE_WIDTH:
            self._row_menu(item, QCursor.pos())

    def _geo_menu(self, point, tree=None):
        tree = tree or self.geo
        item = tree.itemAt(point)
        if item is not None:
            self._row_menu(item, tree.viewport().mapToGlobal(point))

    def _row_menu(self, item, pos):
        """Меню строки списка «Слоёв» - своё у каждого вида строки."""
        key = item.data(0, ACTIVE_ROLE)
        if key:
            self._active_menu(key, pos)
            return
        layer_id = item.data(0, LAYER_ID_ROLE)
        if layer_id:
            layer = QgsProject.instance().mapLayer(layer_id)
            if layer is not None:
                self._layer_menu_at(layer, pos)
            return
        if item in self.vector_groups:
            self._vector_menu(item, pos)
        elif item is self.base_item:
            self._basemap_menu(pos)
        elif item is self.geo_items[RELIEF]:
            self._relief_menu(pos)

    def _geo_double_clicked(self, item, column=0):
        """Двойной щелчок по слою проекта - перелёт к нему."""
        layer = QgsProject.instance().mapLayer(
            item.data(0, LAYER_ID_ROLE) or "")
        if layer is not None:
            self.fly_to_layer.emit(layer)

    def _basemap_menu(self, pos):
        """Меню строки «Основа»: подложки, отмечена выбранная, и свой
        источник тайлов."""
        if self._own_basemap is not None:
            return
        self.basemap_menu().exec(pos)

    def basemap_menu(self):
        """Меню строки «Основа»: подложки в списке глобуса, «Ещё
        подосновы…» и свой источник тайлов. Отдельно от показа - его
        проверяет шаг.

        До 27 октября 2026 года здесь было подменю «Готовые источники»
        с тем же списком, что категория «Подоснова» каталога. Решение
        автора - выбор один, в каталоге с превью, меню ведёт туда."""
        menu = QMenu(self)
        for i, name in enumerate(self._basemap_names):
            action = menu.addAction(name)
            action.setCheckable(True)
            action.setChecked(i == self._basemap)
            action.triggered.connect(
                lambda _=False, i=i: self._basemap_activated(i))
        menu.addSeparator()
        menu.addAction(tr("Ещё подосновы…")).triggered.connect(
            lambda _=False: self.bases_requested.emit())
        menu.addAction(tr("Добавить источник тайлов…")).triggered.connect(
            lambda _=False: self._basemap_activated(ADD_SOURCE))
        return menu

    def basemap_names(self):
        """Названия подложек меню строки «Основа»."""
        return list(self._basemap_names)

    def _basemap_activated(self, index):
        """Подложка выбрана в меню строки «Основа». ADD_SOURCE - свой
        источник тайлов, выбор тогда не меняется."""
        if index == ADD_SOURCE:
            self.add_source_requested.emit()
            return
        self._pick_basemap(index)

    def _pick_basemap(self, index):
        changed = index != self._basemap
        self._mark_basemap(index)
        if changed:
            self.basemap_chosen.emit(index)

    def _mark_basemap(self, index):
        self._basemap = index
        names = self._basemap_names
        name = self._own_basemap or (
            names[index] if 0 <= index < len(names) else "")
        self.base_item.setText(0, tr("Основа · {name}", name=name)
                               if name else tr("Основа"))

    def set_basemaps(self, names, index, own=None):
        """Строка «Основа»: названия источников и выбранный. own -
        название снимков другого тела, тогда выбора нет."""
        self._basemap_names = list(names) if own is None else []
        self._own_basemap = own
        self.base_item.setData(0, MORE_ROLE,
                               MENU_ROW if own is None else None)
        self._mark_basemap(0 if own is not None else index)

    def set_relief_menu(self, models, model, sea, seas=(), sea_model=""):
        """Меню строки «Рельеф»: models - (ключ, название, коротко),
        model - выбранный ключ, sea - глубины морей, seas - (ключ,
        название) источников глубин, sea_model - выбранный. Пустой
        models - меню нет, это другое тело."""
        self._relief_models = list(models)
        self._relief_model = model
        self._sea = bool(sea)
        self._sea_models = list(seas)
        self._sea_model = sea_model
        item = self.geo_items[RELIEF]
        item.setData(0, MORE_ROLE, MENU_ROW if models else None)
        short = next((s for k, _, s in models if k == model), "")
        self.geo.blockSignals(True)
        item.setText(0, tr("Рельеф · {name}", name=short) if short
                     else tr("Рельеф"))
        self.geo.blockSignals(False)

    def _relief_menu(self, pos):
        """Меню строки «Рельеф»: высоты суши, глубины морей, источники."""
        if not self._relief_models:
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        for key, title, _ in self._relief_models:
            action = menu.addAction(title)
            action.setCheckable(True)
            action.setChecked(key == self._relief_model)
            action.triggered.connect(
                lambda _=False, key=key: self.relief_model_chosen.emit(key))
        menu.addSeparator()
        sea = menu.addAction(tr("Глубины морей и океанов"))
        sea.setCheckable(True)
        sea.setChecked(self._sea)
        sea.setToolTip(tr(
            "Дно морей и океанов ниже нуля и вода над ним. Без флажка "
            "поверхность моря ровная, на уровне нуля."))
        sea.toggled.connect(self.sea_toggled.emit)
        for key, title in getattr(self, "_sea_models", ()):
            action = menu.addAction("    " + title)
            action.setCheckable(True)
            action.setChecked(key == self._sea_model)
            action.setEnabled(self._sea)
            action.triggered.connect(
                lambda _=False, key=key: self.sea_model_chosen.emit(key))
        menu.addSeparator()
        menu.addAction(tr("Источники данных…")).triggered.connect(
            lambda _=False: self.sources_requested.emit())
        menu.exec(pos)

    def set_places(self, tree):
        """Строки «Моих меток» по дереву MyPlaces.tree(): метки Place
        и пары (Folder, дети). Сигналы при этом не идут. Папка temp_key
        встаёт своим корнем «Временные метки»."""
        temp = next((node for node in tree if isinstance(node, tuple)
                     and node[0].key == self.temp_key), None)
        tree = [node for node in tree if node is not temp]
        kids = temp[1] if temp is not None else []
        self.list.blockSignals(True)
        group = self.places_group
        holder = self._temp_holder(temp[0] if temp is not None else None)
        # Те же строки, сменились только флажки - строки не строятся
        # заново: на 8 тысячах точек перестройка шла 0.35 с на каждый
        # флажок, 20 октября 2026 года.
        signature = (self._signature(tree), self._signature(kids))
        if (tree or kids) \
                and signature == getattr(self, "_places_signature", None) \
                and group.childCount() == len(tree) \
                and (holder is None or holder.childCount() == len(kids)):
            self._update_checks(group, tree)
            if holder is not None:
                self._update_checks(holder, kids)
                self._temp_check(holder, temp[0], kids)
            self.list.blockSignals(False)
            self._tour_state()
            return
        self._places_signature = signature
        # Выделение и текущая строка переживают перестройку списка: её
        # зовёт любая запись «Моих меток», в том числе ползунок
        # непрозрачности выделенного.
        chosen = set(self.list.selected_keys())
        current = self.list.currentItem()
        current = current.data(0, PLACE_ROLE) if current is not None \
            else None
        group.takeChildren()
        self._fill(group, tree)
        if not tree:
            # Пустая папка отмечена, новая метка сразу видна.
            group.setCheckState(0, CHECKED)
        group.setExpanded(True)
        if holder is not None:
            holder.takeChildren()
            self._fill(holder, kids)
            self._temp_check(holder, temp[0], kids)
            holder.setExpanded(True)
        if chosen or current:
            self._reselect(group, chosen, current)
            if holder is not None:
                self._reselect(holder, chosen, current)
        self.list.blockSignals(False)
        self._tour_state()

    def _temp_holder(self, folder):
        """Строка «Временные метки» для папки folder, None - строки нет."""
        item = self.temp_item
        if folder is None:
            if item is not None:
                self.list.takeTopLevelItem(
                    self.list.indexOfTopLevelItem(item))
                self.list.extra_groups = []
                self.temp_item = None
            return None
        if item is None:
            item = QTreeWidgetItem(self.list, [tr("Временные метки")])
            font = QFont(item.font(0))
            font.setBold(True)
            item.setFont(0, font)
            item.setIcon(0, QgsApplication.getThemeIcon(
                "/mActionHistory.svg"))
            item.setToolTip(0, tr(
                "Новые метки, пути и измерения ложатся сюда, пока строка "
                "выделена. При закрытии окна глобуса содержимое можно "
                "перенести в «Мои метки» или удалить. Метку, которую "
                "надо сохранить сразу, перетащите в «Мои метки»."))
            item.setFlags((item.flags() | CHECKABLE | TRISTATE) & ~DRAG)
            self.temp_item = item
            self.list.extra_groups = [item]
        item.setData(0, PLACE_ROLE, folder.key)
        return item

    @staticmethod
    def _temp_check(item, folder, kids):
        """Флажок пустых «Временных меток» - флажок папки."""
        if not kids:
            item.setCheckState(0, CHECKED if folder.visible else UNCHECKED)

    def select_temporary(self):
        """Сделать «Временные метки» текущей строкой: новые метки
        ложатся туда."""
        if self.temp_item is not None:
            self.list.setCurrentItem(self.temp_item)

    def _signature(self, nodes):
        """Всё, кроме флажков, из чего _fill строит строки."""
        out = []
        for node in nodes:
            if isinstance(node, tuple):
                folder, kids = node
                out.append((folder.key, folder.name, bool(folder.radio),
                            bool(folder.expandable), folder.description,
                            bool(folder.expanded), self.is_link(folder.key),
                            self._signature(kids)))
                continue
            shape = node.shape
            out.append((node.key, node.name, node.measure,
                        bool(getattr(node, "tour", None)), node.kind,
                        shape.icon, tuple(shape.color or ()),
                        lookat.is_view_mark(node.kind, shape.points,
                                            node.view)))
        return out

    def _update_checks(self, parent, nodes):
        """Флажки строк по дереву той же формы, что у _fill."""
        for i, node in enumerate(nodes):
            item = parent.child(i)
            if isinstance(node, tuple):
                folder, kids = node
                radio = bool(folder.radio and folder.expandable and kids)
                if folder.expandable:
                    self._update_checks(item, kids)
                else:
                    kids = []
                if radio:
                    lit = any(getattr(k[0] if isinstance(k, tuple) else k,
                                      "visible", False) for k in kids)
                    state = CHECKED if lit else UNCHECKED
                elif not kids:
                    state = CHECKED if folder.visible else UNCHECKED
                else:
                    continue
            else:
                state = CHECKED if node.visible else UNCHECKED
            if item.checkState(0) != state:
                item.setCheckState(0, state)

    def _reselect(self, parent, chosen, current):
        for i in range(parent.childCount()):
            child = parent.child(i)
            key = child.data(0, PLACE_ROLE)
            if key == current:
                self.list.setCurrentItem(
                    child, 0, enum(QItemSelectionModel, "SelectionFlag",
                                   "NoUpdate"))
            if key in chosen:
                child.setSelected(True)
            self._reselect(child, chosen, current)

    def _fill(self, parent, nodes):
        folder_icon = QgsApplication.getThemeIcon("/mIconFolder.svg")
        # Сетевая ссылка - значок шара сетевых слоёв QGIS, а не папка.
        # Замечание автора от 20 октября 2026 года.
        link_icon = QgsApplication.getThemeIcon("/mIconWms.svg")
        for node in nodes:
            if isinstance(node, tuple):
                folder, kids = node
                item = QTreeWidgetItem(parent, [folder.name
                                                or tr("Без названия")])
                item.setData(0, PLACE_ROLE, folder.key)
                item.setData(0, RADIO_ROLE, self._radio_parent(parent))
                item.setData(0, RADIO_FOLDER_ROLE, bool(folder.radio))
                item.setIcon(0, link_icon if self.is_link(folder.key)
                             else folder_icon)
                # Флажок папки-переключателя не трёхпозиционный: он
                # отмечен, пока виден ребёнок, и сам детям не передаётся.
                # Снятый гасит всех (core/placetree.radio_states).
                radio = bool(folder.radio and folder.expandable and kids)
                flags = item.flags() | CHECKABLE
                if not radio:
                    flags |= TRISTATE
                item.setFlags(flags)
                if folder.description:
                    item.setToolTip(0, folder.description)
                if folder.expandable:
                    self._fill(item, kids)
                else:
                    # Папка без раскрытия: строки детей не показываются,
                    # их видимость следует флажку самой папки.
                    kids = []
                if radio:
                    lit = any(getattr(k[0] if isinstance(k, tuple) else k,
                                      "visible", False) for k in kids)
                    item.setCheckState(0, CHECKED if lit else UNCHECKED)
                elif not kids:
                    item.setCheckState(0, CHECKED if folder.visible
                                       else UNCHECKED)
                item.setExpanded(folder.expanded)
                continue
            item = QTreeWidgetItem(parent, [node.name or tr("Без названия")])
            item.setData(0, PLACE_ROLE, node.key)
            item.setData(0, RADIO_ROLE, self._radio_parent(parent))
            item.setData(0, TOUR_ROLE, bool(getattr(node, "tour",
                                                    None)))
            item.setIcon(0, place_icon(node))
            if node.measure:
                item.setToolTip(0, node.measure)
            item.setFlags((item.flags() | CHECKABLE) & ~DROP)
            item.setCheckState(0, CHECKED if node.visible else UNCHECKED)

    @staticmethod
    def _radio_parent(parent):
        """Лежит ли строка в папке-переключателе."""
        return bool(parent.data(0, RADIO_FOLDER_ROLE))

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
        if found[0] is None and self.temp_item is not None:
            if self.temp_item.data(0, PLACE_ROLE) == key:
                found[0] = self.temp_item
            else:
                look(self.temp_item)
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
        её метки, ключ пути - путь, None - нечего.

        У выделенной метки тур идёт по её папке. Раньше кнопка у метки
        была серой, и тур по трём меткам Луны не запускался, пока
        не выделена папка, 1 октября 2026 года.
        """
        if item is self.places_group:
            return ""
        key = item.data(0, PLACE_ROLE) if item is not None else None
        if key and (is_folder(key) or key.startswith("line:")):
            return key
        if key:
            parent = item.parent()
            if parent is None or parent is self.places_group:
                return ""
            return self._tour_key(parent)
        return None

    def set_opacity(self, value):
        """Ползунок непрозрачности: value 0..1 или None - выделено
        нечего менять. Сигнал opacity_moved при этом не идёт."""
        self._opacity_quiet = True
        self.opacity.setEnabled(value is not None)
        self.opacity.setValue(int(round(100 * (1.0 if value is None
                                               else value))))
        self._opacity_quiet = False

    def _opacity_moved(self, value):
        if not self._opacity_quiet:
            self.opacity_moved.emit(value / 100.0)

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
        self._vector_rows()
        for key, item in self.extra_items.items():
            on = item.checkState(0) == CHECKED
            if on != self._extras.get(key):
                self._extras[key] = on
                self.extra_toggled.emit(key, on)

    def _layer_text(self, layer):
        """Строка слоя проекта: название и тип. Роль на глобусе (рельеф,
        грид) в строке не пишется - решение автора от 12 октября
        2026 года, «не надо ролей, идея неудачная». Сторона шторки -
        знак перед названием."""
        text = tr("{name} · {kind}", name=layer.name(),
                  kind=layer_kind(layer))
        mark = SIDE_MARKS.get(self.swipe_sides.get(layer.id()))
        return mark + " " + text if mark else text

    def set_side_swipe(self, on, any_side):
        """Кнопка «Шторка слоёв» - нажата, видна, пока у слоёв есть
        стороны."""
        self.swipe_button.blockSignals(True)
        self.swipe_button.setChecked(bool(on))
        self.swipe_button.blockSignals(False)
        self.swipe_button.setVisible(bool(any_side))

    def _side_menu(self, menu, layer):
        """Подменю «Шторка» меню слоя проекта."""
        sub = menu.addMenu(tr("Шторка"))
        sub.setToolTipsVisible(True)
        current = self.swipe_sides.get(layer.id(), "")
        for side, text, tip in (
                ("left", tr("Слева"), tr(
                    "Слой виден только левее шторки. Правее - слои "
                    "«Справа» и общие.")),
                ("right", tr("Справа"), tr(
                    "Слой виден только правее шторки.")),
                ("", tr("На обеих сторонах"), tr(
                    "Слой виден по обе стороны шторки."))):
            action = sub.addAction(text)
            action.setCheckable(True)
            action.setChecked(current == side)
            action.setToolTip(tip)
            action.triggered.connect(
                lambda _=False, s=side: self.swipe_side_requested.emit(
                    layer.id(), s))

    def project_rows(self):
        """Строки слоёв проекта раздела «Проект QGIS»."""
        group = self.project_group
        return [group.child(i) for i in range(group.childCount())]

    def set_layers(self, layers, shown):
        """Слои проекта - список раздела «Проект QGIS». shown -
        номера отмеченных.

        Сигналы при этом не идут. При тех же слоях меняются только
        флажки: список перестраивается и из обработчика щелчка по
        флажку, а строка, которую Qt ещё меняет, удаляться не должна.
        """
        rows = self.project_rows()
        texts = [self._layer_text(layer) for layer in layers]
        self.project_tree.blockSignals(True)
        if [r.data(0, LAYER_ID_ROLE) for r in rows] == \
                [layer.id() for layer in layers] and \
                [r.text(0) for r in rows] == texts:
            for row in rows:
                state = CHECKED if row.data(0, LAYER_ID_ROLE) in shown \
                    else UNCHECKED
                if row.checkState(0) != state:
                    row.setCheckState(0, state)
            self.project_tree.blockSignals(False)
            return
        self.project_group.takeChildren()
        for layer, text in zip(layers, texts):
            item = QTreeWidgetItem(self.project_group, [text])
            item.setData(0, LAYER_ID_ROLE, layer.id())
            item.setData(0, MORE_ROLE, True)
            item.setToolTip(0, tr(
                "Отметка показывает слой на глобусе, видимость на карте "
                "QGIS не меняется. Двойной щелчок переносит к слою, меню "
                "«⋯» - перелёт, прозрачность, роль на глобусе и "
                "свойства."))
            item.setFlags((item.flags() | CHECKABLE) & ~DRAG & ~DROP)
            item.setCheckState(0, CHECKED if layer.id() in shown
                               else UNCHECKED)
        self.project_tree.blockSignals(False)

    # События списка.

    def _changed(self, item):
        key = item.data(0, PLACE_ROLE)
        if key:
            self._place_states[key] = item.checkState(0) == CHECKED
            self._place_timer.start(0)

    def _double_clicked(self, item, column=0):
        # У папки перелёт к её виду, если вид задан, как у Google Earth.
        key = item.data(0, PLACE_ROLE)
        if key:
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
        if item is self.temp_item:
            # «Временные метки»: перенести в «Мои метки» или очистить,
            # сама строка не удаляется и не переименовывается.
            self._add_menu(menu, key)
            for entry in (("paste", tr("Вставить")), None,
                          ("temp_save", tr("Сохранить в «Мои метки»")),
                          ("temp_clear", tr("Очистить «Временные метки»…")),
                          None,
                          ("export_kml", tr("Сохранить как KML…")),
                          ("tour", tr("Запустить тур"))):
                if entry is None:
                    menu.addSeparator()
                    continue
                menu.addAction(entry[1]).triggered.connect(
                    lambda _=False, a=entry[0]: self.place_action.emit(
                        a, key))
            menu.exec(self.list.viewport().mapToGlobal(point))
            return
        if is_folder(key):
            # Порядок меню папки Google Earth, 2 октября 2026 года,
            # сверху «Подлететь», как у метки.
            menu.addAction(tr("Подлететь")).triggered.connect(
                lambda: self.place_action.emit("fly", key))
            self._add_menu(menu, key)
            actions = [None,
                       ("cut", tr("Вырезать")),
                       ("copy", tr("Копировать")),
                       ("paste", tr("Вставить")),
                       ("remove", tr("Удалить")),
                       None,
                       None,
                       ("import_kml", tr("Открыть KML или KMZ…")),
                       ("export_kml", tr("Сохранить как KML…")),
                       ("ground_project",
                        tr("Картинки на поверхности в проект QGIS…")),
                       None,
                       ("snapshot", tr("Снимок вида папки")),
                       ("sort", tr("Сортировать от А до Я")),
                       None,
                       ("tour", tr("Запустить тур")),
                       ("properties", tr("Свойства…"))]
            if self.is_link(key):
                actions[0:0] = [("reload_link", tr("Загрузить заново"))]
        elif key:
            actions = [("fly", tr("Подлететь"))]
            if item.data(0, TOUR_ROLE):
                actions.append(("tour", tr("Запустить тур")))
            elif key.startswith("line:"):
                actions.append(("tour", tr("Тур по пути")))
                actions.append(("profile", tr("Профиль высот")))
                actions.append(("section", tr("Разрез вниз…")))
                actions.append(("model_section", tr("Разрез модели…")))
                actions.append(("model_wall", tr("Стенка разреза модели")))
            elif key.startswith("polygon:"):
                actions.append(("model_cut", tr("Вырез модели")))
            elif key.startswith("ground:"):
                actions.append(("ground_project",
                                tr("Картинку в проект QGIS…")))
            if key.split(":")[0] in ("line", "polygon"):
                # Участок по контуру метки. У точки - меню на глобусе.
                actions.append(("sentinel", tr("Космоснимки…")))
                actions.append(("catchment", tr("Водосбор метки")))
                actions.append(("flow_lines", tr("Линии стока от метки…")))
            actions += [("snapshot", tr("Снимок вида метки")),
                        ("properties", tr("Свойства…")),
                        ("new_folder_after", tr("Новая папка")),
                        ("cut", tr("Вырезать")),
                        ("copy", tr("Копировать")),
                        ("paste", tr("Вставить")),
                        ("remove", tr("Удалить"))]
        if key:
            for entry in actions:
                if entry is None:
                    menu.addSeparator()
                    continue
                action, text = entry
                menu.addAction(text).triggered.connect(
                    lambda _=False, a=action: self.place_action.emit(a, key))
        elif item is self.places_group:
            self._add_menu(menu, "")
            menu.addSeparator()
            menu.addAction(tr("Запустить тур")).triggered.connect(
                lambda: self.place_action.emit("tour", ""))
            menu.addAction(tr("Сортировать от А до Я")).triggered.connect(
                lambda: self.place_action.emit("sort", ""))
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
            menu.addSeparator()
            menu.addAction(tr("Очистить «Мои метки»…")).triggered.connect(
                lambda: self.place_action.emit("clear", ""))
        menu.exec(self.list.viewport().mapToGlobal(point))

    def _add_menu(self, menu, key):
        """Подменю «Добавить» папки: папка, метка, путь, многоугольник,
        тур, записанный с экрана, и наложения картинок. Новое ложится
        в папку key."""
        sub = menu.addMenu(tr("Добавить"))
        for action, text in (("new_folder", tr("Папку")),
                             ("draw_point", tr("Метку")),
                             ("draw_line", tr("Путь")),
                             ("draw_polygon", tr("Многоугольник")),
                             ("record_tour", tr("Записанный тур")),
                             ("add_ground", tr("Картинку на поверхности")),
                             ("add_photo", tr("Фото")),
                             ("add_screen", tr("Картинку на экране")),
                             ("add_model", tr("3D-модель…")),
                             ("add_link", tr("Сетевую ссылку…"))):
            sub.addAction(text).triggered.connect(
                lambda _=False, a=action: self.place_action.emit(a, key))

    def _copy_selected(self):
        """Ctrl+C: выделенные строки, без выделения - текущая, корень
        «Мои метки» - все метки."""
        chosen = [key for key in self.list.selected_keys()
                  if key != self.temp_key]
        if chosen:
            self.places_action.emit("copy", chosen)
            return
        item = self.list.currentItem()
        if item is self.places_group:
            self.place_action.emit("copy", "")
        elif item is not None and item.data(0, PLACE_ROLE):
            self.place_action.emit("copy", item.data(0, PLACE_ROLE))

    def _layer_menu(self, point):
        """Меню строки слоя проекта под точкой списка раздела."""
        self._geo_menu(point, self.project_tree)

    def _cloud_menu(self, menu, layer_id):
        """Пункты облака точек: цвет, размер точки, классы."""
        style = cloud_core.style(self.pointcloud_styles.get(layer_id))

        def emit(**change):
            self.pointcloud_style.emit(layer_id, dict(style, **change))
        colors = menu.addMenu(tr("Цвет точек"))
        colors.setToolTipsVisible(True)
        for mode, text, tip in (
                ("rgb", tr("Цвет съёмки"), tr(
                    "Цвет RGB из файла облака. Если цвета в файле нет, "
                    "точки окрашиваются по классу.")),
                ("class", tr("По классу"), tr(
                    "Классы ASPRS - земля, растительность, здания, вода "
                    "и другие. Подписи - в шкале в углу вида.")),
                ("height", tr("По высоте"), tr(
                    "От синего внизу облака к красному вверху.")),
                ("intensity", tr("По интенсивности"), tr(
                    "Сила отражённого сигнала лидара оттенками серого."))):
            action = colors.addAction(text)
            action.setCheckable(True)
            action.setChecked(style["mode"] == mode)
            action.setToolTip(tip)
            action.triggered.connect(lambda _=False, m=mode: emit(mode=m))
        sizes = menu.addMenu(tr("Размер точек"))
        for size in cloud_core.SIZES:
            action = sizes.addAction(tr("{value} пикс.", value="{:g}".format(
                size)))
            action.setCheckable(True)
            action.setChecked(abs(style["size"] - size) < 0.01)
            action.triggered.connect(lambda _=False, v=size: emit(size=v))
        seen = sorted(self.pointcloud_classes.get(layer_id, ()))
        chosen = style["classes"]
        classes = menu.addMenu(tr("Классы точек"))
        classes.setToolTipsVisible(True)
        every = classes.addAction(tr("Все классы"))
        every.setCheckable(True)
        every.setChecked(chosen is None)
        every.triggered.connect(lambda: emit(classes=None))
        ground = classes.addAction(tr("Только земля"))
        ground.setToolTip(tr("Класс 2 - точки поверхности земли."))
        ground.triggered.connect(lambda: emit(classes=[2]))
        if seen:
            classes.addSeparator()
        names = class_names()
        for code in seen:
            action = classes.addAction(names.get(code, tr(
                "Класс {code}", code=code)))
            action.setCheckable(True)
            action.setChecked(chosen is None or code in chosen)

            def toggle(on, code=code):
                kept = set(seen if chosen is None else chosen)
                if on:
                    kept.add(code)
                else:
                    kept.discard(code)
                emit(classes=None if kept >= set(seen) else sorted(kept))
            action.toggled.connect(toggle)

    def _layer_menu_at(self, layer, pos):
        """Меню слоя проекта: перелёт, прозрачность, трек, рельеф
        глобуса у растра, свойства."""
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        menu.addAction(tr("Подлететь")).triggered.connect(
            lambda: self.fly_to_layer.emit(layer))
        menu.addAction(self._opacity_action(menu, layer))
        if isinstance(layer, QgsPointCloudLayer):
            self._cloud_menu(menu, layer.id())
        else:
            self._side_menu(menu, layer)
        if isinstance(layer, QgsVectorLayer) \
                and enum_int(layer.geometryType()) == 0:
            menu.addAction(tr("Трек…")).triggered.connect(
                lambda: self.track_requested.emit(layer))
            sounding = menu.addAction(tr("Батиметрия по промерам…"))
            sounding.setToolTip(tr(
                "Точки слоя - промеры глубин эхолотом. Из них строится "
                "растр глубин, он ложится в рельеф глобуса дном водоёма, "
                "над ним - вода на уровне водоёма."))
            sounding.triggered.connect(
                lambda: self.sounding_requested.emit(layer.id()))
        if isinstance(layer, QgsVectorLayer) \
                and enum_int(layer.geometryType()) in (0, 1, 2):
            raise_ = menu.addAction(tr("Выдавливание…"))
            raise_.setToolTip(tr(
                "Объекты слоя поднимаются над рельефом на высоту из "
                "числового поля: многоугольник - призмой, точка - "
                "столбиком, линия - стенкой. Цвет - стиль слоя."))
            raise_.triggered.connect(
                lambda: self.extrude_requested.emit(layer))
            to_places = menu.addAction(tr("В «Мои метки»…"))
            to_places.setToolTip(tr(
                "Объекты слоя ложатся в «Мои метки» папкой с именем слоя - "
                "выделенные, иначе все. Цвета - стиль слоя, название - "
                "подпись слоя, атрибуты - поля объекта, время - временные "
                "свойства слоя. Папку можно сохранить в KML."))
            to_places.triggered.connect(
                lambda: self.places_requested.emit(layer))
        if isinstance(layer, QgsVectorLayer) \
                and enum_int(layer.geometryType()) in (1, 2) \
                and QgsWkbTypes.hasZ(layer.wkbType()):
            solid = menu.addAction(tr("Объёмом по отметкам Z"))
            solid.setCheckable(True)
            solid.setChecked(layer.id() in self.zlayer_ids)
            solid.setToolTip(tr(
                "Вершины слоя стоят на своих отметках Z - многоугольники "
                "плоскостями, линии трубками, под землёй или над ней, "
                "например вертикальный забор разреза. Цвет - поле color "
                "или стиль слоя QGIS. Ползунок «Земля над гридами» "
                "делает землю над ними прозрачной."))
            solid.toggled.connect(
                lambda on: self.zlayer_toggled.emit(layer.id(), on))
            true_z = menu.addAction(tr("Истинные отметки Z"))
            true_z.setCheckable(True)
            true_z.setEnabled(layer.id() in self.zlayer_ids)
            true_z.setChecked(layer.id() in self.ztrue_ids)
            true_z.setToolTip(tr(
                "При выключенном рельефе вершины стоят на своих отметках "
                "над уровнем моря, например горизонтали поднимаются над "
                "плоской Землёй. Без флажка отметка считается от "
                "поверхности, как глубина скважин и пластов. С рельефом "
                "флажок ничего не меняет."))
            true_z.toggled.connect(
                lambda on: self.ztrue_toggled.emit(layer.id(), on))
        if isinstance(layer, QgsRasterLayer):
            year = menu.addAction(tr("Год карты…"))
            year.setToolTip(tr(
                "Год исторической карты - растра или тайлов. Карты одной "
                "группы слоёв сменяют друг друга на шкале времени - видна "
                "последняя карта не позже момента шкалы. Шаги ◂ ▸ шкалы "
                "идут по годам карт."))
            year.triggered.connect(
                lambda: self.map_year_requested.emit(layer.id()))
        if isinstance(layer, QgsRasterLayer) \
                and layer.providerType() == "gdal":
            relief = menu.addAction(tr("Рельеф глобуса"))
            relief.setCheckable(True)
            relief.setChecked(layer.id() in self.inset_ids)
            relief.setToolTip(tr(
                "Высоты растра заменяют рельеф глобуса в его охвате. "
                "На полосе вдоль края высоты плавно переходят к общему "
                "рельефу. Внутри охвата рельеф подробнее, до пикселя "
                "растра."))
            relief.toggled.connect(
                lambda on: self.inset_toggled.emit(layer.id(), on))
            volume = menu.addAction(tr("Выемка и насыпь…"))
            volume.setToolTip(tr(
                "Растр - новая съёмка рельефа, например карьера с "
                "отвалами. Разность с прежней съёмкой даёт объёмы выемки "
                "и насыпи и растр разности в проекте."))
            volume.triggered.connect(
                lambda: self.volume_requested.emit(layer.id()))
            lake = menu.addAction(tr("Батиметрия водоёма…"))
            lake.setToolTip(tr(
                "Растр глубин или отметок дна озера, моря или водохранилища "
                "ложится в рельеф глобуса, над ним - полупрозрачная вода "
                "на уровне водоёма. В окне задаются, что в растре, "
                "и уровень воды."))
            lake.triggered.connect(
                lambda: self.bathymetry_requested.emit(layer.id()))
            grid = menu.addAction(tr("Поверхность по отметкам"))
            grid.setCheckable(True)
            grid.setChecked(layer.id() in self.grid_ids)
            grid.setToolTip(tr(
                "Значения растра - абсолютные отметки, растр ложится "
                "поверхностью на свою высоту, под землёй или над ней. "
                "Цвет - стиль слоя QGIS. Флажок слоя показывает "
                "и скрывает поверхность, ползунок «Земля над гридами» "
                "раздела «Слои» делает землю над ней прозрачной."))
            grid.toggled.connect(
                lambda on: self.grid_toggled.emit(layer.id(), on))
            lines = menu.addAction(tr("Изолинии в проект QGIS…"))
            lines.setToolTip(tr(
                "Изолинии значений растра с тем же шагом, что на гриде "
                "глобуса, - около 12 линий на размах значений. Линии "
                "ложатся слоем GeoPackage в группу «PlanetX - "
                "горизонтали», каждая пятая толще и подписана."))
            lines.triggered.connect(
                lambda: self.contours_requested.emit(layer))
        menu.addAction(tr("Свойства слоя…")).triggered.connect(
            lambda: self.layer_properties.emit(layer))
        menu.exec(pos)