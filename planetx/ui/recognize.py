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

Одно окно вместо шести - замечание автора от 4 ноября 2026 года «на вид
6 функций сильно дублируют друг друга», выбор того же дня - все четыре
окна («Классификация», «Выделение объектов», «Трассировка», «Похожие
области») задачами этого окна, старые пункты меню убраны, по OK всегда
растр классов и сглаженные многоугольники. Источник - снимки Sentinel-2,
которые окно подбирает само, растр проекта, подложка глобуса или
эмбеддинги AlphaEarth. Задачи - свои образцы, цвета снимка, похожие на
образец (контур образца, ползунок похожести, core/similar.py), леса
и рубки, поля, вода, заросшие поля (таблица весны и осени за 4 года,
core.fallow.field_cells). Линейные объекты - осевые линии узких частей
у задач с правилами (core/linear.py). Многоугольники - сглаживание
трассировки по классам клеток (core.tracing.class_shapes), с делением
на объекты - сами объекты.
"""
import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import (QAbstractItemView, QButtonGroup, QCheckBox,
                                 QComboBox, QFormLayout, QHBoxLayout,
                                 QHeaderView, QLabel,
                                 QMenu, QPushButton, QRadioButton, QSlider,
                                 QSpinBox, QTableWidget, QTableWidgetItem,
                                 QWidget)

from ..core import aef, fallow, linear, rasterclass, segments, similar, \
    tracing
from ..core import objecttasks as ot
from ..core.features import Shape
from ..i18n import tr
from ..qt_compat import enum
from . import s2finder
from .aef import stop_point
from .aefclass import (BASEMAP, CLASS_SIDE, RASTER_SIDE, ClassDialog,
                       ClassTool, SourceBox, add_classes, class_abstract,
                       fill_pixels, project_rasters, read_raster, set_credit,
                       write_classes, write_objects)
from .area import Area
from .results import (add_vector, result_path, set_abstract, show_layer,
                      titled, write_vector)
from .objecttasks import (WHOLE_COVER, cover_share, kind_color, kind_name,
                          layer_roles, line_name, scenario_names,
                          suitable_rasters, write_lines)
from .s2finder import SceneFinder
from .seasons import SeasonPicker, SeasonTable
from .similar import FOUND_COLOR
from .tracing import _stroke_as_fill, raster_roles, write_traced

SETTINGS = "PlanetX/recognize/"
SIDE_MOST = 20.0  # км, наибольшая сторона участка - загрузка по участку
CHOICES = 12  # дат в меню строки
TASKS = ("forest", "fields", "water")  # задачи с правилами по видам
COLORS_TASK = "colors"  # строка «Цвета снимка» списка «Задача»
SIMILAR_TASK = "similar"  # «Похожие на образец»
FALLOW_TASK = "fallow"  # «Заросшие поля»
LINE_TASKS = TASKS + (FALLOW_TASK,)  # задачи с линейными объектами
SHOTS = "@shots"  # источник «Снимки Sentinel-2 участка»
REST_COLOR = (150, 150, 150)  # класс «Остальное» похожих областей
SIMILAR_LIMIT = 70  # %, похожесть по умолчанию - как у прежнего окна
REPICK_PAUSE = 150  # мс, новая выборка после паузы ползунка
# Классы заросших полей: виды полей и летние виды без снега.
FALLOW_KINDS = fallow.KINDS + tuple(ot.task_kinds(FALLOW_TASK))
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


class RecognizeSource(SourceBox):
    """Список «Источник» окна «Распознавание»: снимки Sentinel-2 участка,
    подложка глобуса, растры проекта и эмбеддинги AlphaEarth."""

    def refill(self):
        chosen = self.currentData()
        self.blockSignals(True)
        self.clear()
        self.addItem(tr("Снимки Sentinel-2 участка"), SHOTS)
        self.addItem(tr("Подложка глобуса"), BASEMAP)
        for layer in project_rasters():
            self.addItem(layer.name(), layer.id())
        self.addItem(tr("Эмбеддинги AlphaEarth"), "")
        found = self.findData(chosen) if chosen is not None else 0
        self.setCurrentIndex(max(0, found))
        self.blockSignals(False)
        if chosen is not None and self.currentData() != chosen:
            self.currentIndexChanged.emit(self.currentIndex())


class RecognizeDialog(ClassDialog):
    """Окно «Распознавание»: участок, источник, задача, классы. Слово
    автора от 4 ноября 2026 года - «пользователя ни разу не грузим лишним,
    максимально просто и компактно». На виду - участок, источник, снимки
    (если они нужны), задача и её поле, образцы и классы. Пиксель,
    наименьшая область, деление на объекты и непрозрачность - под
    флажком «Дополнительно»."""

    source_class = RecognizeSource

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Распознавание"))
        settings = QgsSettings()
        self.source.setToolTip(tr(
            "Откуда берутся признаки клетки. Снимки Sentinel-2 участка "
            "окно подбирает и загружает само по «Построить» - летний "
            "и мартовский со снегом. У растра проекта каждый канал - "
            "признак. Подложка - картинка текущей подложки под участком. "
            "Эмбеддинги AlphaEarth загружаются из сети на выбранный год."))
        self.shots = ShotTable(self)
        self.shots.set_keys([key for key, _ in ROWS])
        self.picker = ShotPicker(self.shots, self)
        self.picker.status.connect(self.status.setText)
        self.picker.changed.connect(self._source)
        self.task = QComboBox(self)
        self._fill_tasks()
        self.color_count = QSpinBox(self)
        self.color_count.setRange(2, 16)
        self.color_count.setValue(int(settings.value(
            SETTINGS + "colors", tracing.COLORS)))
        self.color_count.setToolTip(tr(
            "На сколько цветов раскладывается снимок. Больше цветов - "
            "подробнее классы, их проще слить одинаковыми названиями."))
        self.limit = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.limit.setRange(1, 100)
        self.limit.setValue(int(settings.value(SETTINGS + "similar",
                                               SIMILAR_LIMIT)))
        self.limit.setToolTip(tr(
            "Насколько объект участка должен быть похож на образец по цвету "
            "и рисунку. Ниже - находится больше, в том числе непохожее."))
        self.limit_text = QLabel(self)
        self.limit_row = _row(self, self.limit, self.limit_text)
        self.seasons = SeasonTable(self)
        self.season_count = QLabel(self)
        self.pick_seasons = QPushButton(tr("Подобрать снимки"), self)
        self.pick_seasons.setToolTip(tr(
            "Ищет снимки Sentinel-2 участка весны и осени за 4 года, в "
            "каждую пустую клетку берёт самый чистый и загружает его. "
            "«Построить» делает это само, если снимков нет."))
        self.season_row = _row(self, self.season_count, self.pick_seasons)
        self.season_picker = SeasonPicker(self.seasons, self)
        self.season_picker.status.connect(self.status.setText)
        self.season_picker.done.connect(self._season_count)
        self.pick_seasons.clicked.connect(self._pick_seasons)
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
        self.modes_row = _row(self, self.by_points, self.by_areas,
                              stretch=False)
        self.lines = QCheckBox(tr("Линейные объекты"), self)
        self.lines.setChecked(_flag(settings.value(SETTINGS + "lines")))
        self.lines.setToolTip(tr(
            "Дороги и просеки, реки и каналы, лесополосы - осевыми линиями "
            "отдельным слоем. Линия - узкая часть почвы, воды или "
            "растительности, связный кусок линии не короче 200 м."))
        self.line_width = QSpinBox(self)
        self.line_width.setRange(5, 500)
        self.line_width.setSuffix(tr(" м"))
        self.line_width.setValue(int(settings.value(SETTINGS + "line_width",
                                                    linear.WIDTH)))
        self.line_width.setToolTip(tr(
            "Объект уже этого - линия. Ширина не меньше двух пикселей "
            "сетки, иначе линия рвётся."))
        self.least = QSpinBox(self)
        self.least.setRange(1, 100000)
        self.least.setValue(int(settings.value(SETTINGS + "least",
                                               tracing.LEAST)))
        self.least.setToolTip(tr(
            "Многоугольник меньше этого количества клеток сливается с "
            "соседом по самой длинной общей границе. Растр классов не "
            "меняется."))
        self.more = QCheckBox(tr("Дополнительно"), self)
        self.more.setChecked(_flag(settings.value(SETTINGS + "more")))
        self.more.setToolTip(tr(
            "Тонкие настройки: пиксель, наименьшая область многоугольников, "
            "деление на объекты, ширина линий, непрозрачность."))
        self.from_trace.setVisible(False)
        self._arrange()
        wanted = settings.value(SETTINGS + "task", "") or ""
        self.task.setCurrentIndex(max(0, self.task.findData(wanted)))
        source = settings.value(SETTINGS + "source", SHOTS)
        if source in (SHOTS, BASEMAP, ""):
            self.source.setCurrentIndex(max(0, self.source.findData(source)))
        areas = _flag(settings.value(SETTINGS + "areas"))
        (self.by_areas if areas else self.by_points).setChecked(True)
        self.sample = ClassSample(window, self, self.area)
        self.sample.changed.connect(self.changed)
        self.color_count.valueChanged.connect(lambda _: self._task())
        self.task.currentIndexChanged.connect(lambda _: self._task())
        self.by_areas.toggled.connect(lambda _: self._mode())
        self.limit.valueChanged.connect(lambda _: self._limit())
        self.lines.toggled.connect(lambda _: self._options())
        self.line_width.valueChanged.connect(lambda _: self._options())
        self.least.valueChanged.connect(lambda _: self._options())
        self.more.toggled.connect(lambda _: self._options())
        self.split.toggled.connect(lambda _: self._options())
        self._limit()
        self._task()
        self._source()

    def _fill_tasks(self):
        tip_role = enum(Qt, "ItemDataRole", "ToolTipRole")
        items = [("", tr("Свои образцы"), tr(
            "Классы и образцы задаются вручную, нужно хотя бы два класса.")),
            (COLORS_TASK, tr("Цвета снимка"), tr(
                "Снимок раскладывается на цвета, образцы не нужны. Название "
                "цвета можно переписать, цвета с одинаковым названием "
                "сливаются.")),
            (SIMILAR_TASK, tr("Похожие на образец"), tr(
                "Обведите образец на глобусе, окно найдёт на участке "
                "объекты, похожие на него по цвету и рисунку."))]
        items += [(k, n, t) for k, n, t in scenario_names()
                  if k in LINE_TASKS]
        for key, name, tip in items:
            self.task.addItem(name, key)
            self.task.setItemData(self.task.count() - 1, tip, tip_role)
        self.task.setToolTip(tr(
            "Что распознать. Задачи с правилами (леса, поля, вода, заросшие "
            "поля) сами заводят классы и считают их по снимку, образцы не "
            "нужны, образец точкой или областью поправляет свой класс."))

    def _arrange(self):
        """Строки окна в своём порядке: формы окна «Классификация» и
        полей этого окна."""
        form = self.layout().itemAt(0).layout()
        self.form = form
        while form.rowCount():
            row = form.takeRow(0)
            label = row.labelItem.widget() if row.labelItem else None
            if label is not None:
                label.setParent(None)
                label.deleteLater()
        # Тонкие настройки - своим блоком: скрытые строки формы в Qt 5
        # оставляют промежутки.
        self.more_box = QWidget(self)
        inner = QFormLayout(self.more_box)
        inner.setContentsMargins(0, 0, 0, 0)
        self.more_form = inner
        for text, widget in ((tr("Пиксель"), self.level),
                             ("", self.volume),
                             (tr("Наименьшая область, клеток"), self.least),
                             (tr("Ширина линий до"), self.line_width),
                             ("", self.split),
                             (tr("Масштаб объектов"), self.split_scale),
                             (tr("Доля текстуры"), self.split_weight),
                             (tr("Наименьший объект, клеток"),
                              self.split_least),
                             ("", self.split_join),
                             (tr("Непрозрачность"), self.alpha)):
            inner.addRow(text, widget)
        rows = ((tr("Участок"), self.area.widget),
                (tr("Источник"), self.source),
                (tr("Снимки"), self.shots),
                (tr("Год"), self.year),
                (tr("Задача"), self.task),
                (tr("Цветов"), self.color_count),
                (tr("Похожесть"), self.limit_row),
                (tr("Весна и осень"), self.season_row),
                ("", self.seasons),
                (tr("Образцы"), self.modes_row),
                ("", self.lines),
                ("", self.more))
        for text, widget in rows:
            form.addRow(text, widget)
        form.addRow(self.more_box)
        self.place.setVisible(False)

    def _show_row(self, widget, on):
        """Строка формы видна или нет. В Qt 6 - setRowVisible, без
        промежутка от скрытой строки."""
        for form in (self.form, self.more_form):
            if form.indexOf(widget) < 0:
                continue
            if hasattr(form, "setRowVisible"):
                form.setRowVisible(widget, on)
            else:
                widget.setVisible(on)
                label = form.labelForField(widget)
                if label is not None:
                    label.setVisible(on)

    def source_key(self):
        """SHOTS, BASEMAP, номер слоя растра или пусто - AlphaEarth."""
        key = self.source.currentData()
        return "" if key is None else key

    def task_key(self):
        """Ключ задачи, пусто - свои образцы."""
        return self.task.currentData() or ""

    def allowed(self, task):
        """Годится ли задача для источника: правилам нужны каналы
        снимка - ближний ИК и красный или SWIR."""
        if task not in LINE_TASKS:
            return True
        key = self.source_key()
        if key == SHOTS:
            return True
        layer = QgsProject.instance().mapLayer(key) \
            if key not in ("", BASEMAP) else None
        return layer is not None and ot.usable(layer_roles(layer)[0])

    def _source(self):
        key = self.source_key()
        shots, alpha = key == SHOTS, key == ""
        self._show_row(self.shots, shots)
        self._show_row(self.year, alpha)
        self.year.setEnabled(alpha)
        self.area.set_most(SIDE_MOST if shots else CLASS_SIDE if alpha
                           else RASTER_SIDE)
        fill_pixels(self.level, not alpha, self.wanted_pixel)
        model = self.task.model()
        for n in range(self.task.count()):
            model.item(n).setEnabled(self.allowed(self.task.itemData(n)))
        if not self.allowed(self.task_key()):
            self.task.setCurrentIndex(0)
        if key in (SHOTS, BASEMAP, ""):
            QgsSettings().setValue(SETTINGS + "source", key)
        self.volume_changed()
        self._options()
        self.source_changed.emit()

    def volume_changed(self):
        if self.point is not None and self.source_key() == SHOTS \
                and self.raster() is None:
            self.volume.setText(tr("Пиксель - по летнему снимку, 10 м."))
            return
        super().volume_changed()

    def _task(self):
        """Классы задачи вместо прежних, у своих образцов - снова два
        пустых класса."""
        key = self.task_key()
        settings = QgsSettings()
        settings.setValue(SETTINGS + "task", key)
        settings.setValue(SETTINGS + "colors", self.color_count.value())
        for row in list(self.rows):
            self._remove(row)
        if key == COLORS_TASK:
            for n in range(self.color_count.value()):
                row = self.add_class(tr("Цвет {n}", n=n + 1))
                row.rank = n
        elif key == SIMILAR_TASK:
            row = self.add_class(tr("Похоже на образец"))
            row.color = QColor(*FOUND_COLOR)
            row._paint()
            row = self.add_class(tr("Остальное"))
            row.color = QColor(*REST_COLOR)
            row._paint()
            # Остальное не закрывает местность, флажок «Видно» его покажет.
            row.visible.setChecked(False)
        elif key:
            kinds = FALLOW_KINDS if key == FALLOW_TASK \
                else ot.task_kinds(key)
            for kind in kinds:
                row = self.add_class(kind_name(kind))
                row.kind = kind
                row.color = QColor(*kind_color(kind))
                row._paint()
        else:
            for _ in range(2):
                self.add_class()
        if self.rows:
            self.rows[0].pick.setChecked(True)
        self.shots.set_keys(["summer"] if key == FALLOW_TASK
                            else [k for k, _ in ROWS])
        if key == FALLOW_TASK:
            self._take_seasons()
        self._options()
        self._mode()
        self.changed.emit()

    def _options(self):
        """Видимость строк по задаче, источнику и «Дополнительно»."""
        task = self.task_key()
        more = self.more.isChecked()
        self._show_row(self.color_count, task == COLORS_TASK)
        self._show_row(self.limit_row, task == SIMILAR_TASK)
        self._show_row(self.season_row, task == FALLOW_TASK)
        self._show_row(self.seasons, task == FALLOW_TASK)
        self._show_row(self.modes_row, task != SIMILAR_TASK)
        self._show_row(self.lines, task in LINE_TASKS)
        self.add_button.setVisible(task != SIMILAR_TASK)
        self.more_box.setVisible(more)
        self._show_row(self.line_width, task in LINE_TASKS
                       and self.lines.isChecked())
        own = not task
        self._show_row(self.split, own)
        for box in (self.split_scale, self.split_weight, self.split_least,
                    self.split_join):
            self._show_row(box, own and self.split.isChecked())
        settings = QgsSettings()
        settings.setValue(SETTINGS + "more", more)
        settings.setValue(SETTINGS + "lines", self.lines.isChecked())
        settings.setValue(SETTINGS + "line_width", self.line_width.value())
        settings.setValue(SETTINGS + "least", self.least.value())

    def _limit(self):
        self.limit_text.setText("{} %".format(self.limit.value()))
        QgsSettings().setValue(SETTINGS + "similar", self.limit.value())

    def least_cells(self):
        return self.least.value()

    def areas_mode(self):
        return self.task_key() == SIMILAR_TASK or self.by_areas.isChecked()

    def _mode(self):
        on = self.areas_mode()
        if self.task_key() != SIMILAR_TASK:
            QgsSettings().setValue(SETTINGS + "areas",
                                   self.by_areas.isChecked())
        how = tr("контур") if on else tr("точку")
        task = self.task_key()
        if task == COLORS_TASK:
            self.hint.setText(tr(
                "«Построить» раскладывает снимок на цвета. Цвета "
                "с одинаковым названием сливаются. Если цвет лёг неверно, "
                "поставьте его образец - {how} - и нажмите «Построить».",
                how=how))
        elif task == SIMILAR_TASK:
            self.hint.setText(tr(
                "Обведите на глобусе образец - щелчками по вершинам, щелчок "
                "по первой замыкает контур, щелчок внутри контура убирает "
                "его. Образцов может быть несколько."))
        elif task == FALLOW_TASK:
            self.hint.setText(tr(
                "Границы полей - по летнему снимку, вид поля - по снимкам "
                "весны и осени за 4 года. «Построить» подберёт снимки "
                "сам."))
        elif task:
            self.hint.setText(tr(
                "Классы задачи считаются правилами по снимкам, образцы не "
                "нужны. Если класс лёг неверно, поставьте его образец - "
                "{how} - и нажмите «Построить».", how=how))
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
        key = self.source_key()
        if key == SHOTS:
            layer = self.shots.layer("summer")
            return layer.id() if layer is not None else ""
        return key

    def raster(self):
        if self.source_key() == SHOTS:
            return self.shots.layer("summer")
        return super().raster()

    def snow(self):
        if self.source_key() != SHOTS or self.task_key() == FALLOW_TASK:
            return None
        return self.shots.layer("snow")

    def split_params(self):
        if self.task_key():
            return None
        return super().split_params()

    # --- весна и осень --------------------------------------------------

    def _take_seasons(self):
        """Клетки таблицы сезонов берут снимки проекта с красным и ближним
        ИК - то, что уже загружено, заново не грузится."""
        layers = []
        summer = self.raster_id()
        for layer in suitable_rasters(False):
            roles, day = layer_roles(layer)
            if "red" in roles and layer.id() != summer:
                layers.append((layer, day))
        self.seasons.take_project(layers)
        self._season_count()

    def _season_count(self):
        self.season_count.setText(tr(
            "Снимков {count} из {total}", count=len(self.seasons.chosen()),
            total=len(self.seasons.keys())))

    def _pick_seasons(self):
        problem = self.area.check()
        if problem:
            self.status.setText(problem)
            return
        if self.season_picker.busy():
            return
        self._take_seasons()
        self.season_picker.search(self.area.ring)

    def season_layers(self):
        """[(год, сезон, слой)] таблицы сезонов, кроме летнего снимка."""
        summer = self.raster_id()
        return [row for row in self.seasons.chosen()
                if row[2].id() != summer]

    def stop_pickers(self):
        self.picker.stop()
        self.season_picker.finder.stop()
        self.season_picker.queue = []
        self.seasons.loading = None
        self.seasons.refresh()

    def showEvent(self, event):
        super().showEvent(event)
        self._source()
        if self.task_key() == FALLOW_TASK:
            self._take_seasons()


def _row(parent, first, *more, stretch=True):
    """Виджеты строкой: первый растягивается, без stretch - все слева."""
    holder = QWidget(parent)
    row = QHBoxLayout(holder)
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(first, 1 if stretch else 0)
    for widget in more:
        row.addWidget(widget)
    if not stretch:
        row.addStretch(1)
    return holder


def _flag(value):
    return value in (True, "true")


class RecognizeTool(ClassTool):
    """Распознавание участка у окна глобуса."""

    dialog_class = RecognizeDialog
    shapes_attr = "recognize_shapes"
    vectorize = True

    def __init__(self, window):
        super().__init__(window)
        self.pending = None  # подбор, которого ждёт «Построить»
        self.found_rgb = None  # цвета снимка последнего «Построить»
        self.similar_base = None  # (объекты, похожесть) похожих областей
        self.lines = {}  # осевые линии {группа: [ломаные в клетках]}
        self.notes = []  # замечания к строке итога
        self.season_meta = []  # [(год, роли, каналов)] снимков ряда
        self.repick_timer = QTimer(self)
        self.repick_timer.setSingleShot(True)
        self.repick_timer.setInterval(REPICK_PAUSE)
        self.repick_timer.timeout.connect(self.repick)

    def tool_title(self):
        return tr("Распознавание")

    def open_here(self, lat, lon, task=None):
        """Окно для точки, task - задача, которую поставить (действия
        строки «Поиск» прежних окон)."""
        dialog = super().open_here(lat, lon)
        if task is not None:
            found = dialog.task.findData(task)
            if found >= 0 and dialog.allowed(task):
                dialog.task.setCurrentIndex(found)
        if not getattr(dialog, "_limit_linked", False):
            dialog.limit.valueChanged.connect(
                lambda _: self.repick_timer.start())
            dialog._limit_linked = True
        return dialog

    def _want_index(self):
        """Указатель зоны - только у AlphaEarth."""
        if self.dialog is not None and self.dialog.source_key() == "":
            super()._want_index()

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
        if dialog.picker.busy() or dialog.season_picker.busy():
            dialog.status.setText(tr("Снимки ещё загружаются."))
            return
        task, key = dialog.task_key(), dialog.source_key()
        if not dialog.allowed(task):
            dialog.status.setText(tr(
                "Правилам задачи нужен снимок с ближним ИК и красным или "
                "SWIR - снимки Sentinel-2 участка или снимок окна "
                "«Космоснимки»."))
            return
        if self.used_rows() is None:
            dialog.status.setText(self.too_few_text())
            return
        if task == SIMILAR_TASK and not dialog.rows[0].rings:
            dialog.status.setText(tr("Обведите образец на глобусе."))
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        if key == SHOTS and not dialog.picker.fit(dialog.area.ring):
            self._wait(dialog.picker)
            return
        if key == SHOTS and dialog.raster() is None:
            dialog.status.setText(tr(
                "Нет летнего снимка. Щелчок по строке «Лето» - другая дата "
                "или снимок из проекта."))
            return
        if task == FALLOW_TASK:
            dialog._take_seasons()
            if not dialog.season_layers() and self.pending is None:
                self._wait(dialog.season_picker)
                dialog.season_picker.search(dialog.area.ring)
                return
        if task in LINE_TASKS \
                and not ot.usable(raster_roles(dialog.raster())[0]):
            dialog.status.setText(tr(
                "У летнего снимка не узнать ближний ИК и красный или SWIR - "
                "правилам задачи нужен снимок окна «Космоснимки»."))
            return
        self.notes = []
        self.lines = {}
        self.similar_base = None
        super().build()
        if self.job is None:
            return
        if task == COLORS_TASK:
            head = [tr("цвета снимка, цветов {n}",
                       n=dialog.color_count.value())]
        elif task == SIMILAR_TASK:
            head = [tr("похожие на образец")]
        elif task:
            head = [tr("задача «{task}»", task=dialog.task.currentText())]
        else:
            head = []
        self.settings = head + list(self.settings)

    def _wait(self, picker):
        """«Построить» ждёт подбора снимков и идёт дальше сам."""
        if self.pending is None:
            self.pending = picker
            picker.done.connect(self._shots_done)

    def _shots_done(self):
        dialog, picker = self.dialog, self.pending
        if picker is None or dialog is None:
            return
        self.pending = None
        picker.done.disconnect(self._shots_done)
        if dialog.isVisible() and dialog.raster() is not None:
            self.build()

    def rules_job(self):
        """Классы задачи: правилами, цветами снимка или похожестью на
        образец; с образцами - ближайшими образцами: до TASK_SAMPLES
        клеток каждого класса правил плюс образцы пользователя. Без
        задачи - None."""
        dialog = self.dialog
        scenario = dialog.task_key()
        if not scenario:
            return None
        layer = dialog.raster()
        roles = raster_roles(layer)[0] if layer is not None else None
        roles = roles or []
        snow = dialog.snow()
        snow_roles = raster_roles(snow)[0] if snow is not None else None
        rows = self.used_rows()
        colors = scenario == COLORS_TASK
        if colors:
            codes = colors_codes(rows)
        elif scenario == FALLOW_TASK:
            codes = [[fallow.ROWS.index(row.kind)]
                     if getattr(row, "kind", None) else [] for row in rows]
        else:
            codes = [[ot.KIND_ORDER.index(row.kind)]
                     if getattr(row, "kind", None) else [] for row in rows]
        count = dialog.color_count.value()
        first = len(roles) or None
        meta = list(self.season_meta)
        lines = dialog.lines.isChecked() and scenario in LINE_TASKS
        width = dialog.line_width.value()
        rings = [list(r) for r in dialog.rows[0].rings] \
            if scenario == SIMILAR_TASK else []
        limit = dialog.limit.value() / 100.0
        drawing = dialog.source_key() != ""
        params = (dialog.split_scale.value(),
                  dialog.split_weight.value() / 100.0,
                  dialog.split_least.value())
        self.found_rgb = None

        def run(grid, inside, samples, labels, place):
            top = first or grid.shape[0]
            good = inside & np.isfinite(grid[:top]).all(axis=0)
            if scenario == SIMILAR_TASK:
                return self._similar(grid, inside, place, rings, limit,
                                     drawing, params)
            regions = None
            if colors:
                cells, centers = tracing.ranked_colors(grid[:top], good,
                                                       count)
                self.found_rgb = tracing.display_colors(centers)
            elif scenario == FALLOW_TASK:
                cells, parts, summer, scenes = fallow.field_cells(
                    grid, roles, good, meta)
                regions = (parts, summer) if parts is not None else None
                self.notes.append(tr(
                    "Снимков весны и осени {count}.", count=scenes)
                    if scenes else tr("Снимки весны и осени не легли на "
                                      "участок, классы - по летнему."))
            else:
                more = snow_roles if grid.shape[0] > top else None
                found = ot.summer_regions(grid, roles, more, good, scenario)
                cells = np.full(good.shape, -1, dtype=np.int64)
                if found is not None:
                    regions = found
                    parts, kinds = found
                    table = np.array([ot.KIND_ORDER.index(k) for k in kinds]
                                     + [-1], dtype=np.int64)
                    cells[:] = table[np.where(parts >= 0, parts, len(kinds))]
                    cells[~good] = -1
            stop_point(self)
            if lines and regions is not None:
                self.lines = find_lines(regions[0], regions[1], place[3],
                                        width)
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
                place_ = np.flatnonzero((out.ravel() == n) & usable)
                if not len(place_):
                    continue
                take = place_[np.linspace(
                    0, len(place_) - 1, min(TASK_SAMPLES, len(place_)))
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

    def _similar(self, grid, inside, place, rings, limit, drawing, params):
        """Похожие на образец: объекты участка (core/segments.py),
        похожесть каждого на объекты под контурами образцов. Класс 0 -
        похоже, 1 - остальное. Рабочий поток."""
        index, x0, y0, step = place
        shape = grid.shape[1:]
        if segments.too_big(*shape):
            return None
        scale, weight, least = params
        cells = int((rasterclass.usable(grid) & inside).sum())
        parts = segments.segment(
            grid, inside, segments.site_scale(scale, cells), weight, least,
            progress=lambda _: stop_point(self))
        stop_point(self)
        if int(parts.max()) < 1:
            return None
        table = segments.table(grid, parts)
        if drawing:  # рисунок - у снимка, не у эмбеддингов
            table = np.concatenate((table, segments.pattern(grid, parts)))
        found = [similar.sample_rows(
            table, parts, aef.ring_mask(index, x0, y0, step, shape, ring))
            for ring in rings]
        if not any(len(f) for f in found):
            self.notes.append(tr("В контурах образцов нет объектов "
                                 "участка."))
            return None
        score = similar.scores(table, segments.areas(parts),
                               np.concatenate(found), weight, grid.shape[0])
        if score is None:
            return None
        self.similar_base = (parts, score)
        return similar_classes(parts, score, limit)

    def repick(self):
        """Новый порог похожести - без расчёта, многоугольники считаются
        заново по OK."""
        dialog, result = self.dialog, self.result
        if self.similar_base is None or result is None or dialog is None \
                or dialog.task_key() != SIMILAR_TASK:
            return
        parts, score = self.similar_base
        result["classes"] = similar_classes(parts, score,
                                            dialog.limit.value() / 100.0)
        result.pop("shapes", None)
        self._status(result["classes"])
        self.show(keep=True)

    def more_bands(self, box, side):
        """Каналы снимка со снегом или снимков весны и осени на сетке
        летнего."""
        dialog = self.dialog
        if dialog.task_key() == FALLOW_TASK:
            return self._season_bands(box, side)
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

    def _season_bands(self, box, side):
        """Снимки весны и осени на сетке летнего: каналы за каналами
        летнего. Снимок, который не лёг на сетку, - пустые каналы."""
        rows, self.season_meta = [], []
        for year, _, layer in self.dialog.season_layers():
            roles, _ = raster_roles(layer)
            if not roles or "red" not in roles or "nir" not in roles \
                    or not layer.crs().isValid():
                continue
            rows.append((layer.source().split("|")[0], layer.crs().toWkt()))
            self.season_meta.append((year, roles, layer.bandCount()))
        if not rows:
            return None
        meta = list(self.season_meta)

        def add(index, found):
            x0, y0, step, grid = found
            parts = [grid]
            for (path, wkt), (_, _, bands) in zip(rows, meta):
                other = read_raster(path, wkt, index, box, side, step)
                if isinstance(other, str) \
                        or other[3].shape[1:] != grid.shape[1:]:
                    other = (0, 0, 0, np.full((bands,) + grid.shape[1:],
                                              np.nan, dtype=grid.dtype))
                parts.append(other[3][:bands])
            return x0, y0, step, np.concatenate(parts)

        key = tuple(layer.id() for _, _, layer in self.dialog
                    .season_layers())
        return ("seasons",) + key, add

    def _built(self, out, key, box, year, colors, names, *rest, **more):
        """Цвета снимка - строкам классов, замечания задачи - в строку
        итога."""
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
        dialog = self.dialog
        if self.result is None or dialog is None:
            return
        notes = list(self.notes)
        if self.lines:
            km = sum(linear.length_m(p, self.result["step"])
                     for paths in self.lines.values() for p in paths) / 1e3
            notes.append(tr("Линий {km} км, слой - по OK.",
                            km="{:.1f}".format(km)))
        elif dialog.lines.isChecked() and dialog.task_key() in LINE_TASKS:
            notes.append(tr("Линейных объектов не найдено."))
        if notes:
            dialog.status.setText(dialog.status.text() + " "
                                  + " ".join(notes))

    def _status(self, classes):
        """Строка итога похожих областей после смены порога."""
        step = self.result["step"]
        found = int((classes == 0).sum())
        total = max(int((classes >= 0).sum()), 1)
        self.dialog.status.setText(tr(
            "Похоже на образец {area} га, {share} % участка.",
            area=hectares(found * step * step / 1e4),
            share="{:.0f}".format(100.0 * found / total)))

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
        row = dialog.rows[0] if dialog.task_key() == SIMILAR_TASK \
            else dialog.active()
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

    # --- выгрузка -------------------------------------------------------

    def export(self, path=None):
        """Растр классов и многоугольники классов в подгруппу расчёта,
        рядом - контрольные точки, контуры образцов и линии."""
        result = self.result
        if result is None:
            return None
        dialog = self.dialog
        tag = result["year"] or "raster"
        path = path or result_path("classes_{}".format(tag))
        if not write_classes(path, result):
            dialog.status.setText(tr("Растр не записан в «{path}».",
                                     path=path))
            return None
        group = self.session.group_for(result["ring"])
        title = titled(tr("Распознавание {source}", source=result["label"]),
                       result["settings"])
        layer = add_classes(path, title, result, group)
        if layer is not None:
            layer.setOpacity(dialog.alpha.value() / 100.0)
            set_abstract(layer, class_abstract(result))
        show_layer(self.window, layer)
        self._export_polygons(tag, title, group)
        self._export_points(tag, result["label"], group)
        self._export_rings()
        if self.lines:
            self._export_lines(group)
        dialog.status.setText(tr("Классы растром и многоугольниками "
                                 "в проекте."))
        return path

    def _export_polygons(self, tag, title, group):
        """Многоугольники классов: объекты деления или сглаженные области
        классов (tracing.class_shapes), поля cls, name, color и area_ha."""
        result = self.result
        hexes = ["#%02x%02x%02x" % tuple(c[:3]) for c in result["colors"]]
        values = [(n + 1, tuple(rgb[:3]), name) for n, (rgb, name) in
                  enumerate(zip(result["colors"], result["names"]))]
        if result.get("parts") is not None:
            path = result_path("objects_{}".format(tag), ".gpkg")
            if not write_objects(path, result):
                return None
            layer = add_vector(self.window, path, "objects", title, group,
                               result["colors"][0], classes=("class", values))
        else:
            if result.get("shapes") is None:
                found = tracing.class_shapes(result["classes"],
                                             self.dialog.least_cells())
                result.update(shapes=found["shapes"],
                              shape_kinds=found["kinds"])
            if not result["shapes"]:
                return None
            path = result_path("areas_{}".format(tag), ".gpkg")
            data = dict(result, kinds=result["shape_kinds"], hexes=hexes)
            if not write_traced(path, data):
                return None
            layer = add_vector(self.window, path, "traced", title, group,
                               (0, 0, 0), width=0.0, classes=("cls", values))
            if layer is not None:
                _stroke_as_fill(layer)
        if layer is not None:
            set_abstract(layer, class_abstract(result))
            set_credit(layer, result)
        return layer

    def _export_lines(self, group):
        result = self.result
        path = result_path("lines", ".gpkg")
        if not write_lines(path, result, self.lines):
            return None
        values = [(key, ot.LINE_COLORS[key], line_name(key))
                  for key in self.lines]
        title = "{} {}".format(tr("Линии"), result["raster"] or "")
        return add_vector(self.window, path, "lines",
                          titled(title, result["settings"]), group,
                          (255, 255, 255), width=0.6,
                          classes=("kind", values))

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
        if self.pending is not None:
            self.pending.done.disconnect(self._shots_done)
            self.pending = None
        self.dialog.stop_pickers()
        self.dialog.sample.stop()
        self.repick_timer.stop()
        super()._closed(code)

    def close(self):
        if self.dialog is not None:
            self.dialog.stop_pickers()
        self.repick_timer.stop()
        super().close()


def hectares(value):
    """Площадь в гектарах для строки итога: крупная - целыми."""
    return "{:.0f}".format(value) if value >= 100.0 else "{:.3g}".format(value)


def similar_classes(parts, score, limit):
    """Классы клеток похожих областей: 0 - объект похож на образец не
    меньше limit, 1 - остальное, -1 вне объектов."""
    picked = np.where(np.asarray(score) >= limit, 0, 1)
    return np.where(parts >= 0, picked[np.maximum(parts, 0)], -1)


def find_lines(parts, regions, step, width):
    """Осевые линии узких частей почвы, воды и растительности
    (core/linear.py): {группа: [ломаные в клетках]}. width - ширина
    линии в метрах."""
    out = {}
    least = linear.LENGTH / step
    for group, mask in ot.line_masks(parts, regions).items():
        found = linear.lines(mask, width / step, least)
        if found:
            out[group] = found
    return out


__all__ = ["RecognizeTool"]
