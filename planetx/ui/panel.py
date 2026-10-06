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
import html

from qgis.core import (QgsApplication, QgsProject, QgsRasterLayer,
                       QgsSettings, QgsVectorLayer)
from qgis.PyQt.QtCore import QEvent, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QFont, QKeySequence
from qgis.PyQt.QtWidgets import (QAbstractItemView, QHBoxLayout, QLabel,
                                 QLineEdit,
                                 QListWidget, QMenu, QPushButton,
                                 QSizePolicy, QSlider, QSplitter, QStyle,
                                 QStyledItemDelegate, QStyleOptionButton,
                                 QStyleOptionViewItem,
                                 QToolButton, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout, QWidget,
                                 QWidgetAction)

from ..core import icons, lookat, themes
from ..core.placetree import is_folder
from ..i18n import tr
from ..net.overlay import (AIRPORTS, BORDERS, PARKS, PEAKS, PLACES,
                           RAILWAYS, RIVERS, ROAD_REFS, ROADS, WATER,
                           WATER_NAMES)
from ..qt_compat import QAction, enum, enum_int
from .placeprops import icon_image
from .satellites import group_names as satellite_group_names
from .spinner import BusySpinner
from .themes import group_names, theme_names

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
# Строки группы «Основа»: номер источника или ADD_SOURCE.
BASEMAP_ROLE = TOUR_ROLE + 1
ADD_SOURCE = -1
# Строка внутри папки-переключателя: рисуется переключателем, как
# в Google Earth, а не флажком.
RADIO_ROLE = BASEMAP_ROLE + 1
# Строка самой папки-переключателя.
RADIO_FOLDER_ROLE = RADIO_ROLE + 1
THEME_ROLE = RADIO_FOLDER_ROLE + 1  # ключ темы NASA GIBS
THEME_GROUP_ROLE = THEME_ROLE + 1  # ключ группы тем NASA GIBS
SAT_GROUP_ROLE = THEME_GROUP_ROLE + 1  # ключ группы спутников CelesTrak
FOUND_HEIGHT = 160  # пикселей, наибольшая высота списка найденных мест
# Клавиши строки поиска и списка подсказок под ней.
KEY_PRESS = enum(QEvent, "Type", "KeyPress")
KEY_DOWN = enum(Qt, "Key", "Key_Down")
KEY_UP = enum(Qt, "Key", "Key_Up")
KEY_ESCAPE = enum(Qt, "Key", "Key_Escape")
KEY_CHOOSE = (enum(Qt, "Key", "Key_Return"), enum(Qt, "Key", "Key_Enter"))
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
               "polygon": "/mIconPolygonLayer.svg",
               # Наложения: на поверхности, фото, на экране.
               "ground": "/mIconRaster.svg",
               "photo": "/mLayoutItemPicture.svg",
               "screen": "/mActionAddImage.svg"}
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
    return tr("{name} - прежний запрос", name=item.text)


def theme_group(key):
    """Группа темы key или пожаров, "" - без группы."""
    if key == FIRES:
        return "fire"
    theme = themes.BY_KEY.get(key)
    return theme.group if theme is not None else ""


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
    # Группы векторной основы, включённые в панели «Слои», множество.
    geo_changed = pyqtSignal(object)
    # Подложка выбрана в группе «Основа» - номер источника.
    basemap_chosen = pyqtSignal(int)
    add_source_requested = pyqtSignal()
    relief_toggled = pyqtSignal(bool)
    # Строка сетки, звёзд или облаков: ключ из EXTRAS и флажок.
    extra_toggled = pyqtSignal(str, bool)
    # Отмеченные группы спутников, множество ключей CelesTrak.
    satellite_groups_changed = pyqtSignal(object)
    # Тема NASA GIBS: ключ core.themes, "" - тема выключена.
    theme_chosen = pyqtSignal(str)
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
        # Пример в пустой строке: место или тема. Решение автора от
        # 5 октября 2026 года - кнопки помощника у строки нет, параметры
        # помощника - в окне «Свойства вида».
        self.place.setPlaceholderText(tr("Путешествия Колумба"))
        self.place.setClearButtonEnabled(True)
        self.place.setToolTip(tr(
            "Место, координаты или тема. Название места или координаты, "
            "например Пермь или 58.0105, 56.2294, дают перелёт. Тема, "
            "например «путешествия Колумба», становится метками с датами "
            "в «Моих метках». Вопрос словами уходит помощнику. Ctrl+Enter "
            "сразу создаёт метки по теме."))
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
        # Темы NASA - одна из всех, строки рисуются кружками
        # переключателей. Просьба автора от 5 октября 2026 года.
        self.geo.setItemDelegate(RadioDelegate(self.geo))
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
        self._basemap = 0
        # Подложка - первая группа раздела, одна отмеченная строка
        # и «Добавить источник тайлов…». Просьба автора от 1 октября
        # 2026 года.
        self.base_group = QTreeWidgetItem(self.geo, [tr("Основа")])
        self.base_group.setToolTip(0, tr(
            "Снимки или карта на поверхности. Esri World Imagery - пример "
            "подложки, условия её использования задаёт Esri. Свой источник "
            "добавляет строка «Добавить источник тайлов…»."))
        self.geo.itemClicked.connect(self._geo_clicked)
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
        # Рельеф стоит сразу под группой «Основа», просьба автора
        # от 3 октября 2026 года.
        relief = QTreeWidgetItem(self.geo, self.base_group)
        relief.setText(0, tr("Рельеф"))
        relief.setData(0, LAYER_ROLE, RELIEF)
        relief.setToolTip(0, tr(
            "Высоты поднимают поверхность и дают отмывку склонов. "
            "Высоты Земли - Mapzen Terrain Tiles, Марса - MOLA, Луны - "
            "LOLA. Без рельефа шар гладкий, высоты не загружаются. "
            "Вертикальный масштаб - в свойствах вида."))
        relief.setFlags(relief.flags() | CHECKABLE)
        relief.setCheckState(0, UNCHECKED)
        self.geo_items[RELIEF] = relief
        self.extra_items = {}
        self._extras = {}
        for key, text, tip in (
                (GRID, tr("Координатная сетка"), tr(
                    "Параллели и меридианы с подписями градусов, экватор, "
                    "тропики и полярные круги. Шаг сетки меняется с высотой "
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
                    "высоту 5 м.")),
                (SUN, tr("Солнце"), tr(
                    "Свет рельефа, зданий и воздуха по положению солнца. "
                    "Ночная сторона Земли тёмная. Время солнца - конец "
                    "промежутка открытой шкалы времени, без неё - часы "
                    "компьютера. Без флажка свет падает с северо-запада, "
                    "как на карте рельефа.")),
                (QUAKES, tr("Землетрясения"), tr(
                    "Землетрясения магнитудой от 4.5 за последние 30 "
                    "суток по сводке USGS. Кружок стоит в очаге на его "
                    "глубине, линия ведёт к эпицентру на поверхности. "
                    "Цвет показывает глубину очага, размер - магнитуду. "
                    "Сводка загружается при включении строки.")),
                (FIRES, tr("Пожары"), tr(
                    "Очаги пожаров за последние 24 часа по снимкам VIIRS "
                    "спутника NOAA-20, сводка NASA FIRMS. Точка стоит на "
                    "месте очага, цвет и размер показывают мощность "
                    "излучения. Сводка загружается при включении строки, "
                    "около 6 МБ.")),
                (PLATES, tr("Границы плит"), tr(
                    "Границы литосферных плит по модели PB2002. Красные - "
                    "раздвиг плит на хребтах и рифтах, зелёные - сдвиг "
                    "по трансформным разломам, синие - схождение "
                    "в зонах субдукции и коллизии. Названия плит стоят "
                    "надписями. Тип границы и скорость плит показывает "
                    "окно «Объекты».")),
                (CUTAWAY, tr("Разрез Земли"), tr(
                    "Вынимает из Земли сектор под точкой взгляда - "
                    "четверть полушария шириной 90° по долготе. На его "
                    "гранях видны кора, мантия и ядро по радиусам "
                    "модели PREM. Где грань проходит через зону "
                    "субдукции, на ней видна погружающаяся плита. "
                    "Углы сектора тянутся мышью. Сектор ставится заново "
                    "при каждом включении строки.")),
                (PALEO, tr("Палеогеография"), tr(
                    "Рельеф суши и глубины моря в прошлом, до 540 млн "
                    "лет назад, по картам PaleoDEM PALEOMAP. Возраст "
                    "задаёт ползунок в левом нижнем углу вида. Снимок, "
                    "границы и подписи на это время убраны.")),
                (SLOPE, tr("Уклон"), tr(
                    "Уклон поверхности по высотам рельефа, классами от "
                    "ровного до круче 35°. Шкала стоит в левом нижнем "
                    "углу вида. Есть у Земли, Марса и Луны.")),
                (ASPECT, tr("Экспозиция"), tr(
                    "Куда обращён склон - цвет стороны света, ровное "
                    "место серое. Включается вместо уклона.")),
                (SATELLITES, tr("Спутники"), tr(
                    "Искусственные спутники по орбитальным элементам "
                    "CelesTrak, положение по модели SGP4. Время - правый "
                    "бегунок шкалы времени, без шкалы - часы компьютера. "
                    "Группы выбираются флажками ниже. Элементы группы "
                    "обновляются не чаще раза в 2 часа."))):
            item = QTreeWidgetItem(self.geo, [text])
            item.setData(0, LAYER_ROLE, key)
            item.setToolTip(0, tip)
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, UNCHECKED)
            self.extra_items[key] = item
        # Группы спутников - строки под «Спутниками», отмечаются любые.
        self.sat_items = {}
        for key, text, tip in satellite_group_names():
            item = QTreeWidgetItem(self.extra_items[SATELLITES], [text])
            item.setData(0, SAT_GROUP_ROLE, key)
            item.setToolTip(0, tip)
            item.setFlags(item.flags() | CHECKABLE)
            item.setCheckState(0, UNCHECKED)
            self.sat_items[key] = item
        # Темы NASA GIBS - группы строк, отмечена одна тема из всех.
        # Просьба автора от 5 октября 2026 года.
        # Флажок группы отмечен, когда включена её тема. Снятый флажок
        # выключает тему, поставленный - включает прежнюю тему группы.
        # Замечание автора того же дня - «как отключить все слои из воды
        # или огня».
        self.theme_items = {}
        self.theme_groups = []
        self._theme = ""
        self._group_last = {}
        names = theme_names()
        for group_key, title, tip in group_names():
            group = QTreeWidgetItem(self.geo, [title])
            group.setToolTip(0, tip)
            group.setData(0, THEME_GROUP_ROLE, group_key)
            group.setFlags(group.flags() | CHECKABLE)
            group.setCheckState(0, UNCHECKED)
            self.theme_groups.append(group)
            for theme in themes.THEMES:
                if theme.group != group_key:
                    continue
                text, row_tip = names[theme.key]
                item = QTreeWidgetItem(group, [text])
                item.setData(0, THEME_ROLE, theme.key)
                item.setData(0, RADIO_ROLE, True)
                item.setToolTip(0, row_tip)
                item.setFlags(item.flags() | CHECKABLE)
                item.setCheckState(0, UNCHECKED)
                self.theme_items[theme.key] = item
            if group_key == "fire":
                # Пожары - первой строкой «Планеты огня», переключателем
                # в общем выборе тем: пожары или одна тема. Просьбы
                # автора от 5 октября 2026 года.
                fires = self.extra_items[FIRES]
                self.geo.takeTopLevelItem(
                    self.geo.indexOfTopLevelItem(fires))
                group.insertChild(0, fires)
                fires.setData(0, THEME_ROLE, FIRES)
                fires.setData(0, RADIO_ROLE, True)
                self.theme_items[FIRES] = fires
        self.geo.itemChanged.connect(self._geo_changed)
        # Слои проекта - свой список, отдельно от меток.
        # Растры проекта - рельеф глобуса, отметки меню слоя.
        self.inset_ids = set()
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
        return super().eventFilter(watched, event)

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
        for key in (CLOUDS, TEMPERATURE, BUILDINGS, SUN, QUAKES, FIRES,
                    PLATES, CUTAWAY, PALEO, SATELLITES):
            self.extra_items[key].setDisabled(not earth)
        for group in self.theme_groups:
            group.setDisabled(not earth)
        # Уклон и экспозиция - там, где есть высоты.
        for key in (SLOPE, ASPECT):
            self.extra_items[key].setDisabled(not (earth or relief))
        self.layers.setEnabled(earth)

    def set_theme(self, key):
        """Отметить тему key, "" - ни одной, FIRES - пожары. Сигналы
        не идут."""
        self._theme = key or ""
        current = theme_group(self._theme)
        if current:
            self._group_last[current] = self._theme
        self.geo.blockSignals(True)
        for name, item in self.theme_items.items():
            item.setCheckState(0, CHECKED if name == self._theme
                               else UNCHECKED)
        self._extras[FIRES] = self._theme == FIRES
        for group in self.theme_groups:
            on = bool(current) \
                and group.data(0, THEME_GROUP_ROLE) == current
            group.setCheckState(0, CHECKED if on else UNCHECKED)
        self.geo.blockSignals(False)

    def _theme_changed(self, item):
        key = item.data(0, THEME_ROLE)
        if item.checkState(0) == CHECKED:
            chosen = key
        elif key == self._theme:
            chosen = ""
        else:
            return
        # Отмечена одна тема: прежняя отметка снимается.
        self.set_theme(chosen)
        self.theme_chosen.emit(chosen)

    def _theme_group_changed(self, item):
        """Флажок группы тем: снят - тема группы выключена, поставлен -
        включена прежняя тема группы, без неё - первая."""
        group = item.data(0, THEME_GROUP_ROLE)
        if item.checkState(0) == CHECKED:
            chosen = self._group_last.get(group) or next(
                t.key for t in themes.THEMES if t.group == group)
        else:
            if theme_group(self._theme) != group:
                self.set_theme(self._theme)
                return
            chosen = ""
        self.set_theme(chosen)
        self.theme_chosen.emit(chosen)

    def set_satellite_groups(self, groups):
        """Отметить группы спутников. Сигналы при этом не идут."""
        self.geo.blockSignals(True)
        for key, item in self.sat_items.items():
            item.setCheckState(0, CHECKED if key in groups else UNCHECKED)
        self.geo.blockSignals(False)

    def _geo_changed(self, item):
        if item.data(0, SAT_GROUP_ROLE):
            self.satellite_groups_changed.emit(
                {key for key, row in self.sat_items.items()
                 if row.checkState(0) == CHECKED})
            return
        if item.data(0, THEME_ROLE):
            self._theme_changed(item)
            return
        if item.data(0, THEME_GROUP_ROLE):
            self._theme_group_changed(item)
            return
        index = item.data(0, BASEMAP_ROLE)
        if index is not None and index != ADD_SOURCE:
            if item.checkState(0) == CHECKED:
                self._pick_basemap(index)
            else:
                # Подложка без отметки не остаётся, отметка возвращается.
                self._pick_basemap(self._basemap)
            return
        if item.data(0, LAYER_ROLE):
            self._geo_timer.start(0)

    def _geo_clicked(self, item, column):
        # Строка могла исчезнуть между нажатием и отпусканием кнопки,
        # тогда Qt присылает щелчок без строки.
        if item is None:
            return
        index = item.data(0, BASEMAP_ROLE)
        if index == ADD_SOURCE:
            self.add_source_requested.emit()
        elif index is not None and index != self._basemap:
            self._pick_basemap(index)

    def _pick_basemap(self, index):
        changed = index != self._basemap
        self._mark_basemap(index)
        if changed:
            self.basemap_chosen.emit(index)

    def _mark_basemap(self, index):
        self._basemap = index
        self.geo.blockSignals(True)
        for i in range(self.base_group.childCount()):
            child = self.base_group.child(i)
            value = child.data(0, BASEMAP_ROLE)
            if value != ADD_SOURCE:
                child.setCheckState(0, CHECKED if value == index
                                    else UNCHECKED)
        self.geo.blockSignals(False)

    def _basemap_names(self):
        """Названия источников в строках группы «Основа»."""
        group = self.base_group
        names = []
        for i in range(group.childCount()):
            child = group.child(i)
            value = child.data(0, BASEMAP_ROLE)
            if value is None:
                return None
            if value != ADD_SOURCE:
                names.append(child.text(0))
        return names

    def set_basemaps(self, names, index, own=None):
        """Строки группы «Основа»: названия источников и выбранный.
        own - название снимков другого тела, тогда группа показывает
        только его и выбор недоступен."""
        group = self.base_group
        if own is None and self._basemap_names() == list(names):
            # Те же источники - меняется только отметка. Строки
            # не пересоздаются, иначе щелчок по флажку, который сам
            # выбрал подложку, приходит в _geo_clicked без строки.
            self._mark_basemap(index)
            return
        self.geo.blockSignals(True)
        group.takeChildren()
        self._basemap = index
        if own is not None:
            item = QTreeWidgetItem(group, [own])
            item.setDisabled(True)
        else:
            for i, name in enumerate(names):
                item = QTreeWidgetItem(group, [name])
                item.setData(0, BASEMAP_ROLE, i)
                item.setFlags(item.flags() | CHECKABLE)
                item.setCheckState(0, CHECKED if i == index else UNCHECKED)
            add = QTreeWidgetItem(group, [tr("Добавить источник тайлов…")])
            add.setData(0, BASEMAP_ROLE, ADD_SOURCE)
            add.setToolTip(0, tr(
                "Свой источник тайлов по адресу. Окно разбирает адрес, "
                "показывает пробную мозаику и находит самый подробный "
                "уровень."))
            font = add.font(0)
            font.setItalic(True)
            add.setFont(0, font)
        group.setExpanded(True)
        self.geo.blockSignals(False)

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
                item.setData(0, RADIO_ROLE, self._radio_parent(parent))
                item.setData(0, RADIO_FOLDER_ROLE, bool(folder.radio))
                item.setIcon(0, folder_icon)
                item.setFlags(item.flags() | CHECKABLE | TRISTATE)
                if folder.description:
                    item.setToolTip(0, folder.description)
                if folder.expandable:
                    self._fill(item, kids)
                else:
                    # Папка без раскрытия: строки детей не показываются,
                    # их видимость следует флажку самой папки.
                    kids = []
                if not kids:
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
            elif key.startswith("point:"):
                actions.append(("viewshed", tr("Видимость отсюда…")))
                actions.append(("insolation", tr("Инсоляция…")))
            elif key.startswith("ground:"):
                actions.append(("ground_project",
                                tr("Картинку в проект QGIS…")))
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
                             ("add_screen", tr("Картинку на экране"))):
            sub.addAction(text).triggered.connect(
                lambda _=False, a=action: self.place_action.emit(a, key))

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
        """Меню слоя проекта: перелёт, прозрачность, трек, рельеф
        глобуса у растра, свойства."""
        item = self.layers.itemAt(point)
        layer_id = item.data(0, LAYER_ROLE) if item is not None else None
        layer = QgsProject.instance().mapLayer(layer_id) if layer_id \
            else None
        if layer is None:
            return
        menu = QMenu(self)
        menu.setToolTipsVisible(True)
        menu.addAction(tr("Подлететь")).triggered.connect(
            lambda: self.fly_to_layer.emit(layer))
        menu.addAction(self._opacity_action(menu, layer))
        if isinstance(layer, QgsVectorLayer) \
                and enum_int(layer.geometryType()) == 0:
            menu.addAction(tr("Трек…")).triggered.connect(
                lambda: self.track_requested.emit(layer))
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
        menu.addAction(tr("Свойства слоя…")).triggered.connect(
            lambda: self.layer_properties.emit(layer))
        menu.exec(self.layers.viewport().mapToGlobal(point))