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
"""
import numpy as np
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QObject, pyqtSignal
from qgis.PyQt.QtWidgets import (QAbstractItemView, QHeaderView, QMenu,
                                 QTableWidget, QTableWidgetItem)

from ..i18n import tr
from ..qt_compat import enum
from . import s2finder
from .aefclass import AUTO, ClassDialog, ClassTool, read_raster
from .objecttasks import (WHOLE_COVER, cover_share, layer_roles,
                          suitable_rasters)
from .s2finder import SceneFinder
from .tracing import raster_roles

SIDE_MOST = 20.0  # км, наибольшая сторона участка - загрузка по участку
CHOICES = 12  # дат в меню строки
# Строки таблицы: ключ, месяцы по порядку предпочтения. Снег - март
# и апрель, как у второго снимка «Выделения объектов».
ROWS = (("summer", s2finder.SUMMER), ("snow", (3, 4)))


def row_name(key):
    return {"summer": tr("Лето"), "snow": tr("Март - апрель, снег")}[key]


def day_text(day):
    """«2025-07-21» - «21.07.2025»."""
    return "{}.{}.{}".format(day[8:10], day[5:7], day[:4]) if day else ""


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

    def tool_title(self):
        return tr("Распознавание")

    def _want_index(self):
        """Указатель AlphaEarth окну не нужен."""

    def build(self):
        """«Построить»: сначала условия - участок, классы и точки, потом
        подбор и загрузка снимков, потом классы."""
        dialog = self.dialog
        if dialog is None or dialog.point is None or self.job is not None:
            return
        if dialog.picker.busy():
            dialog.status.setText(tr("Снимки ещё загружаются."))
            return
        rows = [row for row in dialog.rows if row.points]
        if len(rows) < 2 or any(len(row.points) < 3 for row in rows):
            dialog.status.setText(tr(
                "Нужно хотя бы два класса по три точки."))
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
        super().build()

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

    def _closed(self, code=0):
        if self.pending:
            self.pending = False
            self.dialog.picker.done.disconnect(self._shots_done)
        self.dialog.picker.stop()
        super()._closed(code)

    def close(self):
        if self.dialog is not None:
            self.dialog.picker.stop()
        super().close()


__all__ = ["RecognizeTool"]
