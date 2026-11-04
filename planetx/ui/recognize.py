# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Распознавание» подменю «Анализ участка», первая ступень - классы
по точкам.

Решение автора от 4 ноября 2026 года - распознавание растёт ступенями
«точки - области - задания», простая первая, загрузка снимков понятная.
Снимки окно подбирает и загружает само по «Построить», когда участок,
классы и точки уже заданы - слово автора того же дня «загрузка, когда
максимально сформулированы условия». Таблица «Снимки» - лето и март -
апрель со снегом, без снега классы по летнему. Поиск сцен Sentinel-2
участка и загрузка сочетания «Сельское хозяйство» по участку - как
у «Выделения объектов» (ui/s2finder.py), снимок, который уже есть
в проекте и накрывает участок, берётся без загрузки. Классы по точкам -
окно «Классификация» (ui/aefclass.py) без выбора источника: каналы
летнего снимка и снимка со снегом - признаки клетки.

Вторая ступень - образцы областями, слово автора того же дня «делай
вторую ступень, по областям». Переключатель «Образцы» - точки или
области. В областях щелчок по глобусу начинает контур выбранного класса
(ClassSample, как контур образца «Похожих областей»), щелчок по первой
вершине замыкает его, щелчок внутри готового контура убирает. Образцы
класса - клетки внутри контура (ui/aefclass.py, RING_CELLS).

Третья ступень - задачи, слово автора того же дня «давай дальше по
распознаванию, третью ступень», выбор - список «Задача». Задача («Леса
и рубки», «Поля», «Вода») сама заводит свои классы и считает их
правилами «Выделения объектов» по тем же снимкам лета и снега
(core.objecttasks.cell_kinds), образцы не нужны. Образец точкой или
областью поправляет класс: «Построить» берёт до TASK_SAMPLES клеток
каждого класса правил образцами, добавляет образцы пользователя
и считает классы ближайшими образцами. Заросших полей в списке нет -
им нужен ряд снимков весны и осени за 4 года.

Источник «Цвета снимка» - слово автора от 4 ноября 2026 года
«объединяй, делай источник «Цвета снимка»» на просьбу Василия Швалёва
объединить окно с «Трассировкой». Летний снимок раскладывается на цвета,
как у трассировки (core.tracing.ranked_colors), образцы не нужны, цвета -
строки классов по убыванию доли участка. Строки с одинаковым названием
сливаются, образец точкой или областью поправляет цвет, как у задачи.
"""
import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QObject, Qt, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QAbstractItemView, QButtonGroup, QComboBox,
                                 QHBoxLayout, QHeaderView, QMenu,
                                 QRadioButton, QSpinBox, QTableWidget,
                                 QTableWidgetItem, QWidget)

from ..core import aef, rasterclass, tracing
from ..core import objecttasks as ot
from ..core.features import Shape
from ..i18n import tr
from ..qt_compat import enum
from . import s2finder
from .aef import stop_point
from .aefclass import AUTO, ClassDialog, ClassTool, read_raster
from .area import Area
from .results import add_vector, result_path, write_vector
from .objecttasks import (WHOLE_COVER, cover_share, kind_color, kind_name,
                          layer_roles, scenario_names, suitable_rasters)
from .s2finder import SceneFinder
from .tracing import raster_roles

SETTINGS = "PlanetX/recognize/"
SIDE_MOST = 20.0  # км, наибольшая сторона участка - загрузка по участку
CHOICES = 12  # дат в меню строки
TASKS = ("forest", "fields", "water")  # задачи списка «Задача»
COLORS_TASK = "colors"  # строка «Цвета снимка» списка «Задача»
TASK_SAMPLES = 60  # клеток класса правил образцами, если есть свои
# Строки таблицы: ключ, месяцы по порядку предпочтения. Снег - март
# и апрель, как у второго снимка «Выделения объектов».
ROWS = (("summer", s2finder.SUMMER), ("snow", (3, 4)))


def row_name(key):
    return {"summer": tr("Лето"), "snow": tr("Март - апрель, снег")}[key]


def day_text(day):
    """«2025-07-21» - «21.07.2025»."""
    return "{}.{}.{}".format(day[8:10], day[5:7], day[:4]) if day else ""


def colors_codes(rows):
    """Номера цветов снимка у строк классов «Цветов снимка» [[номера]]:
    строка с тем же названием, что у строки выше, отдаёт свой цвет ей -
    так цвета сливаются. Свой класс без цвета - пустой список."""
    out = [[] for _ in rows]
    first = {}
    for n, row in enumerate(rows):
        rank = getattr(row, "rank", None)
        if rank is None:
            continue
        name = row.name.text().strip()
        target = first.setdefault(name, n) if name else n
        out[target].append(rank)
    return out


class ShotTable(QTableWidget):
    """Снимки участка строками: что нужно, дата, облачность над участком,
    состояние. Сигнал picked(ключ, глобальная точка) - щелчок по строке."""

    picked = pyqtSignal(str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.keys = []
        self.layers = {}  # {ключ: номер слоя}
        self.clouds = {}  # {ключ: облачность над участком, %}
        self.states = {}  # {ключ: текст состояния}
        self.setColumnCount(3)
        self.setHorizontalHeaderLabels([tr("Снимок"), tr("Дата"),
                                        tr("Состояние")])
        header = self.horizontalHeader()
        header.setSectionResizeMode(enum(QHeaderView, "ResizeMode",
                                         "ResizeToContents"))
        header.setSectionResizeMode(2, enum(QHeaderView, "ResizeMode",
                                            "Stretch"))
        self.verticalHeader().setVisible(False)
        self.setEditTriggers(enum(QAbstractItemView, "EditTrigger",
                                  "NoEditTriggers"))
        self.setSelectionMode(enum(QAbstractItemView, "SelectionMode",
                                   "NoSelection"))
        self.setToolTip(tr(
            "Снимки Sentinel-2 участка подбираются и загружаются сами по "
            "«Построить»: самый чистый над участком за три года. Снимок "
            "проекта, который накрывает участок, берётся без загрузки. "
            "Щелчок по строке - другие даты, снимок из проекта или «Без "
            "снимка»."))
        self.cellClicked.connect(self._clicked)

    def set_keys(self, keys):
        self.keys = list(keys)
        self.setRowCount(len(self.keys))
        self.refresh()
        height = self.horizontalHeader().sizeHint().height() \
            + 2 * self.frameWidth()
        for row in range(self.rowCount()):
            height += self.rowHeight(row)
        self.setFixedHeight(height)

    def layer(self, key):
        return QgsProject.instance().mapLayer(self.layers.get(key) or "")

    def set_layer(self, key, layer, cloud=None):
        if layer is None:
            self.layers.pop(key, None)
            self.clouds.pop(key, None)
        else:
            self.layers[key] = layer.id()
            if cloud is None:
                self.clouds.pop(key, None)
            else:
                self.clouds[key] = cloud
        self.states.pop(key, None)
        self.refresh()

    def set_state(self, key, text):
        self.states[key] = text
        self.refresh()

    def missing(self):
        return [key for key in self.keys if self.layer(key) is None]

    def refresh(self):
        for row, key in enumerate(self.keys):
            layer = self.layer(key)
            day = layer_roles(layer)[1] if layer is not None else ""
            cloud = self.clouds.get(key)
            state = self.states.get(key) or (
                tr("готов") if layer is not None
                else tr("подберётся по «Построить»"))
            date = day_text(day) or ("✓" if layer is not None else "-")
            if cloud is not None:
                date += tr(", облака {cloud} %", cloud="{:.0f}".format(cloud))
            cells = (row_name(key), date, state)
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                if layer is not None:
                    item.setToolTip(layer.name())
                self.setItem(row, column, item)

    def _clicked(self, row, column):
        rect = self.visualItemRect(self.item(row, column))
        self.picked.emit(self.keys[row],
                         self.viewport().mapToGlobal(rect.bottomLeft()))


class ShotPicker(QObject):
    """Подбор снимков в таблицу: один поиск на все строки, лучший снимок
    в каждую пустую строку, загрузка по очереди. Сигналы status, changed -
    снимок строки сменился, done - подбор закончен."""

    status = pyqtSignal(str)
    changed = pyqtSignal()
    done = pyqtSignal()

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.choices = {}  # {ключ: [(сцена, облачность, данные)]}
        self.queue = []
        self.loading = None  # (ключ, облачность) того, что грузится
        self.ring = None
        self.searched = None  # участок последнего поиска
        self.finder = SceneFinder(self)
        self.finder.status.connect(self.status.emit)
        self.finder.found.connect(self._found)
        self.finder.loaded.connect(self._loaded)
        self.finder.failed.connect(self._failed)
        table.picked.connect(self._menu)

    def busy(self):
        return self.finder.busy() or bool(self.queue) \
            or self.loading is not None

    def stop(self):
        self.finder.stop()
        self.queue = []
        if self.loading is not None:
            self.table.states.pop(self.loading[0], None)
        self.loading = None
        self.table.refresh()

    def fit(self, ring):
        """Снимки таблицы для участка ring: строки без снимка или со
        снимком, который участок не накрывает, берут снимок проекта или
        ищутся. Поиск - один раз на участок. True - снимки уже есть,
        иначе подбор начат, конец - сигнал done."""
        ring = list(ring)
        for key in self.table.keys:
            layer = self.table.layer(key)
            if layer is not None and not _covers(layer, ring):
                self.table.set_layer(key, None)
        self._take_project(ring)
        missing = self.table.missing()
        if not missing:
            self.changed.emit()
            return True
        if self.busy() and self.ring == ring:
            return False
        self.stop()
        self.ring = ring
        if self.searched == ring and self.choices:
            self._fill()
            return False
        months = sorted({m for key, ms in ROWS for m in ms
                         if key in missing})
        for key in missing:
            self.table.set_state(key, tr("поиск…"))
        self.finder.search(ring, months, shown=10000)
        return False

    def _take_project(self, ring):
        """Снимок проекта с подписями каналов, днём нужного месяца в имени
        файла и участком внутри - в пустую строку без загрузки."""
        for key, months in ROWS:
            if key not in self.table.keys or self.table.layer(key):
                continue
            for layer in suitable_rasters():
                day = layer_roles(layer)[1]
                if day and int(day[5:7]) in months \
                        and layer.id() not in self.table.layers.values() \
                        and _covers(layer, ring):
                    self.table.set_layer(key, layer)
                    break

    def _found(self, found):
        self.searched = list(self.ring)
        self.choices = {}
        for key, months in ROWS:
            self.choices[key] = s2finder.order(
                [p for p in found if int(p[0].when[5:7]) in months],
                months)[:CHOICES]
        self._fill()

    def _fill(self):
        self.queue = []
        for key in self.table.missing():
            options = self.choices.get(key) or []
            if options:
                self.queue.append((key, options[0]))
            else:
                self.table.set_state(key, tr("чистого снимка нет")
                                     if key == "summer"
                                     else tr("нет, классы по летнему"))
        self._next()

    def _next(self):
        if not self.queue:
            self.loading = None
            self._report()
            return
        key, (scene, cloud, _) = self.queue.pop(0)
        self.loading = (key, cloud)
        self.table.set_state(key, tr("загрузка…"))
        self.status.emit(tr("Загрузка снимка «{row}» {day}…",
                            row=row_name(key), day=day_text(scene.when[:10])))
        self.finder.load(scene, self.ring)

    def _loaded(self, layer):
        if self.loading is not None:
            key, cloud = self.loading
            self.table.set_layer(key, layer, cloud)
            self.changed.emit()
        self._next()

    def _failed(self):
        if self.loading is not None:
            self.table.set_state(self.loading[0], tr("не загрузился"))
        self._next()

    def _report(self):
        if "summer" in self.table.missing():
            self.status.emit(tr(
                "Летнего снимка участка нет: у сцен Sentinel-2 за три года "
                "облачность над участком больше 5 %. Щелчок по строке "
                "«Лето» - снимок из проекта."))
        self.changed.emit()
        self.done.emit()

    def _menu(self, key, where):
        """Меню строки: другие даты, снимок из проекта, «Без снимка»."""
        if self.busy():
            return
        menu = QMenu(self.table)
        for option in self.choices.get(key, []):
            scene, cloud, _ = option
            action = menu.addAction(tr(
                "{day} - облачность над участком {cloud} %",
                day=day_text(scene.when[:10]),
                cloud="{:.0f}".format(cloud)))
            action.triggered.connect(
                lambda _=False, o=option: self._take(key, o))
        own = menu.addMenu(tr("Снимок из проекта"))
        for layer in suitable_rasters(key == "summer"):
            action = own.addAction(layer.name())
            action.triggered.connect(
                lambda _=False, l=layer: self._own(key, l))
        own.setEnabled(not own.isEmpty())
        menu.addSeparator()
        menu.addAction(tr("Без снимка")).triggered.connect(
            lambda: self._own(key, None))
        menu.popup(where)

    def _take(self, key, option):
        self.queue = [(key, option)]
        self._next()

    def _own(self, key, layer):
        self.table.set_layer(key, layer)
        self.changed.emit()


def _covers(layer, ring):
    share = cover_share(layer, ring)
    return share is None or share >= WHOLE_COVER


class ClassSample(Area):
    """Контур образца класса: вершины рисуются, как у участка, замкнутый
    контур уходит строке класса row. Участка окон анализа не трогает."""

    shared = False

    def __init__(self, window, dialog, site):
        super().__init__(window, dialog, 1.0, SIDE_MOST)
        self.site = site
        self.row = None
        self.widget.hide()

    def start(self, row):
        self.row = row
        self.ring = []
        self.drawing = True
        self.begin()

    def edited(self):
        if self.closed():
            row, ring = self.row, list(self.ring)
            self.ring = []
            if row is not None:
                row.set_rings(row.rings + [ring])
            self.changed.emit()
            self.site.begin()
        self.window._refresh_shapes()
        self.window.handles.sync()

    def stop(self):
        self.ring = []
        self.drawing = False

    def shapes(self):
        if not self.visible() or len(self.ring) < 2 or self.row is None:
            return []
        return [Shape("line", list(self.ring), color=self.row.rgb() + (255,),
                      width=2.0)]


class RecognizeDialog(ClassDialog):
    """Окно «Распознавание»: участок, снимки, классы по точкам. Слово
    автора от 4 ноября 2026 года - «пользователя ни разу не грузим лишним,
    максимально просто и компактно». Источник, год, пиксель, деление на
    объекты и непрозрачность окна «Классификация» спрятаны: источник -
    летний снимок таблицы, пиксель - «Авто», снимок со снегом берётся,
    если он нашёлся."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Распознавание"))
        self.wanted_pixel = AUTO
        self.shots = ShotTable(self)
        self.shots.set_keys([key for key, _ in ROWS])
        self.picker = ShotPicker(self.shots, self)
        self.picker.status.connect(self.status.setText)
        self.picker.changed.connect(self._source)
        form = self.layout().itemAt(0).layout()
        for widget in (self.place, self.source, self.year, self.level,
                       self.volume, self.split, self.split_scale,
                       self.split_weight, self.split_least, self.split_join,
                       self.alpha):
            widget.setVisible(False)
            label = form.labelForField(widget)
            if label is not None:
                label.setVisible(False)
        self.from_trace.setVisible(False)
        form.insertRow(1, tr("Снимки"), self.shots)
        self.by_points = QRadioButton(tr("Точки"), self)
        self.by_points.setToolTip(tr(
            "Щелчок по глобусу ставит точку выбранного класса. Нужно три "
            "точки на класс."))
        self.by_areas = QRadioButton(tr("Области"), self)
        self.by_areas.setToolTip(tr(
            "Щелчок по глобусу начинает контур выбранного класса, щелчок по "
            "первой вершине его замыкает. Образцы класса - клетки внутри "
            "контура, одного контура на класс хватает. Щелчок внутри "
            "контура убирает его."))
        modes = QButtonGroup(self)
        modes.addButton(self.by_points)
        modes.addButton(self.by_areas)
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(self.by_points)
        row.addWidget(self.by_areas)
        row.addStretch(1)
        form.insertRow(3, tr("Образцы"), holder)
        self.task = QComboBox(self)
        tip_role = enum(Qt, "ItemDataRole", "ToolTipRole")
        self.task.addItem(tr("Свои образцы"), "")
        self.task.setItemData(0, tr(
            "Классы и образцы задаются вручную, нужно хотя бы два класса."),
            tip_role)
        self.task.addItem(tr("Цвета снимка"), COLORS_TASK)
        self.task.setItemData(1, tr(
            "Летний снимок раскладывается на цвета, как в окне "
            "«Трассировка», образцы не нужны. Название цвета можно "
            "переписать, цвета с одинаковым названием сливаются."),
            tip_role)
        for key, name, tip in scenario_names():
            if key in TASKS:
                self.task.addItem(name, key)
                self.task.setItemData(self.task.count() - 1, tip, tip_role)
        self.task.setToolTip(tr(
            "Задача сама заводит классы и считает их правилами по снимкам "
            "лета и снега, образцы не нужны. Образец точкой или областью "
            "поправляет свой класс, «Построить» считает заново с ним."))
        form.insertRow(3, tr("Задача"), self.task)
        self.color_count = QSpinBox(self)
        self.color_count.setRange(2, 16)
        self.color_count.setValue(int(QgsSettings().value(
            SETTINGS + "colors", tracing.COLORS)))
        self.color_count.setToolTip(tr(
            "На сколько цветов раскладывается снимок. Больше цветов - "
            "подробнее классы, их проще слить одинаковыми названиями."))
        form.insertRow(4, tr("Цветов"), self.color_count)
        self.color_count.valueChanged.connect(lambda _: self._task())
        wanted = QgsSettings().value(SETTINGS + "task", "") or ""
        self.task.setCurrentIndex(max(0, self.task.findData(wanted)))
        self.task.currentIndexChanged.connect(lambda _: self._task())
        areas = QgsSettings().value(SETTINGS + "areas", False) \
            in (True, "true")
        (self.by_areas if areas else self.by_points).setChecked(True)
        self.by_areas.toggled.connect(lambda _: self._mode())
        self.sample = ClassSample(window, self, self.area)
        self.sample.changed.connect(self.changed)
        self._mode()
        if self.task_key():
            self._task()

    def task_key(self):
        """Ключ задачи, пусто - свои образцы."""
        return self.task.currentData() or ""

    def _task(self):
        """Классы задачи вместо прежних, у своих образцов - снова два
        пустых класса."""
        key = self.task_key()
        QgsSettings().setValue(SETTINGS + "task", key)
        QgsSettings().setValue(SETTINGS + "colors",
                               self.color_count.value())
        form = self.layout().itemAt(0).layout()
        self.color_count.setVisible(key == COLORS_TASK)
        label = form.labelForField(self.color_count)
        if label is not None:
            label.setVisible(key == COLORS_TASK)
        for row in list(self.rows):
            self._remove(row)
        if key == COLORS_TASK:
            for n in range(self.color_count.value()):
                row = self.add_class(tr("Цвет {n}", n=n + 1))
                row.rank = n
        elif key:
            for kind in ot.task_kinds(key):
                row = self.add_class(kind_name(kind))
                row.kind = kind
                row.color = QColor(*kind_color(kind))
                row._paint()
        else:
            for _ in range(2):
                self.add_class()
        if self.rows:
            self.rows[0].pick.setChecked(True)
        self._mode()
        self.changed.emit()

    def areas_mode(self):
        return self.by_areas.isChecked()

    def _mode(self):
        on = self.areas_mode()
        QgsSettings().setValue(SETTINGS + "areas", on)
        if self.task_key() == COLORS_TASK:
            self.hint.setText(tr(
                "«Построить» раскладывает летний снимок на цвета. Цвета "
                "с одинаковым названием сливаются. Если цвет лёг неверно, "
                "поставьте его образец - {how} - и нажмите «Построить».",
                how=tr("контур") if on else tr("точку")))
        elif self.task_key():
            self.hint.setText(tr(
                "Классы задачи считаются правилами по снимкам, образцы не "
                "нужны. Если класс лёг неверно, поставьте его образец - "
                "{how} - и нажмите «Построить».",
                how=tr("контур") if on else tr("точку")))
        else:
            self._own_hint(on)
        if not on and self.sample.drawing:
            self.sample.stop()
            self.area.begin()

    def _own_hint(self, on):
        self.hint.setText(tr(
            "Обведите на глобусе образец выбранного класса - щелчками по "
            "вершинам, щелчок по первой замыкает контур. Нужно хотя бы два "
            "класса, у каждого контур или три точки.") if on else tr(
            "Щёлкните по глобусу, чтобы поставить точку выбранного "
            "класса. Нужно хотя бы два класса по три точки."))

    def raster_id(self):
        layer = self.shots.layer("summer")
        return layer.id() if layer is not None else ""

    def raster(self):
        return self.shots.layer("summer")

    def snow(self):
        return self.shots.layer("snow")

    def split_params(self):
        return None

    def _source(self):
        super()._source()
        self.level.setCurrentIndex(max(0, self.level.findData(AUTO)))
        self.area.set_most(SIDE_MOST)

    def _remember(self):
        """Настройки окна «Классификация» это окно не меняет."""

    def _split_changed(self):
        """Деления на объекты у окна нет."""

    def showEvent(self, event):
        super().showEvent(event)
        self.area.set_most(SIDE_MOST)


class RecognizeTool(ClassTool):
    """Распознавание участка по точкам у окна глобуса."""

    dialog_class = RecognizeDialog
    shapes_attr = "recognize_shapes"

    def __init__(self, window):
        super().__init__(window)
        self.pending = False  # «Построить» ждёт подбора снимков
        self.found_rgb = None  # цвета снимка последнего «Построить»

    def tool_title(self):
        return tr("Распознавание")

    def _want_index(self):
        """Указатель AlphaEarth окну не нужен."""

    def too_few_text(self):
        if self.dialog.task_key():
            return tr("У задачи нужно хотя бы два класса.")
        return tr("Нужно хотя бы два класса, у каждого контур или три "
                  "точки.")

    def used_rows(self):
        """У задачи - все её классы: образцы не обязательны."""
        if not self.dialog.task_key():
            return super().used_rows()
        rows = list(self.dialog.rows)
        return rows if len(rows) >= aef.MIN_CLASSES else None

    def build(self):
        """«Построить»: сначала условия - участок, классы и образцы, потом
        подбор и загрузка снимков, потом классы."""
        dialog = self.dialog
        if dialog is None or dialog.point is None or self.job is not None:
            return
        if dialog.picker.busy():
            dialog.status.setText(tr("Снимки ещё загружаются."))
            return
        if self.used_rows() is None:
            dialog.status.setText(self.too_few_text())
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        if not dialog.picker.fit(dialog.area.ring):
            if not self.pending:
                self.pending = True
                dialog.picker.done.connect(self._shots_done)
            return
        if dialog.raster() is None:
            dialog.status.setText(tr(
                "Нет летнего снимка. Щелчок по строке «Лето» - другая дата "
                "или снимок из проекта."))
            return
        task = dialog.task_key()
        if task and task != COLORS_TASK \
                and not ot.usable(raster_roles(dialog.raster())[0]):
            dialog.status.setText(tr(
                "У летнего снимка не узнать ближний ИК и красный или SWIR - "
                "правилам задачи нужен снимок окна «Космоснимки»."))
            return
        super().build()
        if task == COLORS_TASK and self.job is not None:
            self.settings = [tr("цвета снимка, цветов {n}",
                                n=dialog.color_count.value())] \
                + list(self.settings)
        elif task and self.job is not None:
            self.settings = [tr("задача «{task}»",
                                task=dialog.task.currentText())] \
                + list(self.settings)

    def rules_job(self):
        """Классы задачи правилами, с образцами - ближайшими образцами:
        до TASK_SAMPLES клеток каждого класса правил плюс образцы
        пользователя. Без задачи - None."""
        dialog = self.dialog
        scenario = dialog.task_key()
        if not scenario:
            return None
        roles = raster_roles(dialog.raster())[0]
        snow = dialog.snow()
        snow_roles = raster_roles(snow)[0] if snow is not None else None
        rows = self.used_rows()
        colors = scenario == COLORS_TASK
        if colors:
            codes = colors_codes(rows)
        else:
            codes = [[ot.KIND_ORDER.index(row.kind)]
                     if getattr(row, "kind", None) else [] for row in rows]
        count = dialog.color_count.value()
        first = len(roles) or None
        self.found_rgb = None

        def run(grid, inside, samples, labels):
            top = first or grid.shape[0]
            good = inside & np.isfinite(grid[:top]).all(axis=0)
            if colors:
                cells, centers = tracing.ranked_colors(grid[:top], good,
                                                       count)
                self.found_rgb = tracing.display_colors(centers)
            else:
                more = snow_roles if grid.shape[0] > top else None
                cells = ot.cell_kinds(grid, roles, more, good, scenario)
            stop_point(self)
            out = np.full(cells.shape, -1, dtype=np.int64)
            for n, code in enumerate(codes):
                if code:
                    out[np.isin(cells, code)] = n
            if not samples:
                return out
            samples, labels = list(samples), list(labels)
            flat = grid.reshape(grid.shape[0], -1)
            usable = rasterclass.usable(grid).ravel()
            for n in range(len(codes)):
                place = np.flatnonzero((out.ravel() == n) & usable)
                if not len(place):
                    continue
                take = place[np.linspace(
                    0, len(place) - 1, min(TASK_SAMPLES, len(place)))
                    .astype(np.int64)]
                for cell in take:
                    samples.append(flat[:, cell])
                    labels.append(n)
            if len(set(labels)) < aef.MIN_CLASSES:
                return out
            classes, _ = rasterclass.classify(
                grid, np.stack(samples, axis=1), labels, inside,
                progress=lambda done, total: stop_point(self))
            return classes

        return run

    def _built(self, out, key, box, year, colors, names, *rest, **more):
        """Цвета снимка - строкам классов: цвет строки - цвет снимка
        под её номером."""
        found, self.found_rgb = self.found_rgb, None
        if found and self.dialog.task_key() == COLORS_TASK:
            colors = list(colors)
            for n, row in enumerate(self.dialog.rows):
                rank = getattr(row, "rank", None)
                if rank is not None and rank < len(found) \
                        and n < len(colors):
                    row.color = QColor(*found[rank])
                    row._paint()
                    colors[n] = tuple(found[rank])
        super()._built(out, key, box, year, colors, names, *rest, **more)

    def _shots_done(self):
        """Снимки подобраны - «Построить» идёт дальше сам."""
        dialog = self.dialog
        if not self.pending or dialog is None:
            return
        self.pending = False
        dialog.picker.done.disconnect(self._shots_done)
        if dialog.isVisible() and dialog.raster() is not None:
            self.build()

    def more_bands(self, box, side):
        """Каналы снимка со снегом на сетке летнего."""
        dialog = self.dialog
        layer = dialog.snow()
        if layer is None:
            return None
        roles, _ = raster_roles(layer)
        if not layer.crs().isValid():
            return None
        path, wkt = layer.source().split("|")[0], layer.crs().toWkt()

        def add(index, found):
            x0, y0, step, grid = found
            other = read_raster(path, wkt, index, box, side, step)
            if isinstance(other, str) \
                    or other[3].shape[1:] != grid.shape[1:] \
                    or not np.isfinite(other[3]).any():
                # Снимок со снегом не лёг - классы по летнему.
                return found
            return x0, y0, step, np.concatenate((grid, other[3]))

        return (layer.id(), path, len(roles or ())), add

    # --- образцы областями ----------------------------------------------

    def ring_under(self, lat, lon):
        """Контур образца с точкой внутри: (строка класса, номер) или
        None, последний нарисованный - первым."""
        for row in reversed(self.dialog.rows):
            for n in range(len(row.rings) - 1, -1, -1):
                if aef.ring_inside([lat], [lon], row.rings[n])[0]:
                    return row, n
        return None

    def point_under(self, px, py):
        """Точка класса у курсора или, в областях, контур под курсором -
        подсказка участка меняется по тому, что убирает щелчок."""
        dialog = self.dialog
        found = super().point_under(px, py)
        if found is not None:
            dialog.area.point_hint = tr("Убрать точку")
            return found
        if not dialog.areas_mode():
            return None
        ground = self.window._ground(px, py)
        hit = self.ring_under(*ground) if ground is not None else None
        if hit is not None:
            dialog.area.point_hint = tr("Убрать область")
        return hit

    def click(self, px, py, lat, lon):
        dialog = self.dialog
        if not dialog.areas_mode() \
                or super().point_under(px, py) is not None:
            super().click(px, py, lat, lon)
            return
        hit = self.ring_under(lat, lon)
        if hit is not None:
            row, n = hit
            row.set_rings(row.rings[:n] + row.rings[n + 1:])
            self._update_shapes()
            return
        row = dialog.active()
        if row is None:
            return
        dialog.sample.start(row)
        dialog.sample.add(lat, lon)

    def _update_shapes(self):
        super()._update_shapes()
        dialog = self.dialog
        if dialog is None or not dialog.isVisible():
            return
        for row in dialog.rows:
            for ring in row.rings:
                self.shapes.append(Shape(
                    "polygon", list(ring), color=row.rgb() + (255,),
                    fill=row.rgb() + (70,), width=2.0))
        setattr(self.window, self.shapes_attr, self.shapes)
        self.window._refresh_shapes()

    def export(self, path=None):
        """Классы, как у «Классификации», рядом - контуры образцов слоем
        многоугольников с классом и названием."""
        done = super().export(path)
        if done and self.result is not None:
            self._export_rings()
        return done

    def _export_rings(self):
        rows = self.dialog.rows
        items = [(ring, {"class": n, "name": row.name.text()})
                 for n, row in enumerate(rows, 1) for ring in row.rings]
        if not items:
            return None
        path = result_path("class_areas", ".gpkg")
        if not write_vector(path, "areas", "polygon", items,
                            [("class", "int"), ("name", "str")]):
            return None
        group = self.session.group_for(self.result["ring"])
        return add_vector(
            self.window, path, "areas", tr("Образцы классов"), group,
            rows[0].rgb(), width=0.6, fill=(255, 255, 255, 0),
            classes=("class", [(n, row.rgb(), row.name.text())
                               for n, row in enumerate(rows, 1)
                               if row.rings]))

    def _closed(self, code=0):
        if self.pending:
            self.pending = False
            self.dialog.picker.done.disconnect(self._shots_done)
        self.dialog.picker.stop()
        self.dialog.sample.stop()
        super()._closed(code)

    def close(self):
        if self.dialog is not None:
            self.dialog.picker.stop()
        super().close()


__all__ = ["RecognizeTool"]
