# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Снимки сезонов задачи «Заросшие поля» окна «Выделение объектов».

Таблица - годы ряда строками, весна и осень столбцами, слово автора от
3 ноября 2026 года «подумай, как это красиво сделать, чтобы приятно
работать было». «Подобрать снимки» один раз ищет сцены Sentinel-2
участка весны и осени за годы ряда (ui/s2finder.py), в каждую пустую
клетку берёт лучшую (core/fallow.py, pick) и грузит её сочетанием «SWIR»
(B12 B8A B4) - в нём красный и ближний ИК для голой почвы. Щелчок по
клетке - другие подходящие даты этого сезона или «Без снимка». Снимки,
что уже есть в проекте, клетки берут сами, загрузки заново нет.
"""
from qgis.core import QgsProject
from qgis.PyQt.QtCore import QDate, QObject, Qt, pyqtSignal
from qgis.PyQt.QtWidgets import (QAbstractItemView, QHeaderView, QMenu,
                                 QTableWidget, QTableWidgetItem)

from ..core import fallow
from ..i18n import tr
from ..qt_compat import enum
from .s2finder import SceneFinder

PRODUCT = "swir"  # B12 B8A B4: красный, ближний ИК и SWIR
SEASONS = (("spring", fallow.SPRING), ("autumn", fallow.AUTUMN))


def season_of(month):
    for name, months in SEASONS:
        if month in months:
            return name
    return None


def short_day(day):
    """«2025-05-29» - «29.05»."""
    return "{}.{}".format(day[8:10], day[5:7])


class SeasonTable(QTableWidget):
    """Годы строками - новые сверху, весна и осень столбцами. В клетке -
    слой проекта (номер слоя), «загрузка…» или пусто. Сигнал picked(год,
    сезон, глобальная точка) - щелчок по клетке."""

    picked = pyqtSignal(int, str, object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.years = []
        self.cells = {}  # {(год, сезон): номер слоя}
        self.loading = None  # (год, сезон), что грузится
        self.setColumnCount(len(SEASONS))
        self.setHorizontalHeaderLabels([tr("Весна"), tr("Осень")])
        self.horizontalHeader().setSectionResizeMode(
            enum(QHeaderView, "ResizeMode", "Stretch"))
        self.setEditTriggers(enum(QAbstractItemView, "EditTrigger",
                                  "NoEditTriggers"))
        self.setSelectionMode(enum(QAbstractItemView, "SelectionMode",
                                   "NoSelection"))
        self.setToolTip(tr(
            "Снимки весны (апрель - май) и осени (сентябрь - октябрь) по "
            "годам. Пашня в это время - голая почва, залежь - старая "
            "трава и кустарник. Щелчок по клетке - другие даты сезона."))
        self.cellClicked.connect(self._clicked)
        self.set_years(fallow.YEARS)

    def set_years(self, count):
        now = QDate.currentDate().year()
        self.years = list(range(now, now - count, -1))
        self.setRowCount(len(self.years))
        self.setVerticalHeaderLabels([str(y) for y in self.years])
        self.refresh()
        height = self.horizontalHeader().height() + 2 * self.frameWidth()
        for row in range(self.rowCount()):
            height += self.rowHeight(row)
        self.setFixedHeight(height)

    def keys(self):
        return [(y, s) for y in self.years for s, _ in SEASONS]

    def layer(self, key):
        return QgsProject.instance().mapLayer(self.cells.get(key) or "")

    def set_layer(self, key, layer_id):
        if layer_id:
            self.cells[key] = layer_id
        else:
            self.cells.pop(key, None)
        self.refresh()

    def chosen(self):
        """[(год, сезон, слой)] клеток со снимком."""
        out = []
        for key in self.keys():
            layer = self.layer(key)
            if layer is not None:
                out.append((key[0], key[1], layer))
        return out

    def take_project(self, layers):
        """Клетки без снимка берут подходящие снимки проекта по дню
        в имени файла. layers - [(слой, день «ГГГГ-ММ-ДД»)]."""
        for layer, day in layers:
            if not day:
                continue
            key = (int(day[:4]), season_of(int(day[5:7])))
            if key[1] and key[0] in self.years \
                    and self.layer(key) is None:
                self.cells[key] = layer.id()
        self.refresh()

    def refresh(self):
        for row, year in enumerate(self.years):
            for column, (season, _) in enumerate(SEASONS):
                key = (year, season)
                layer = self.layer(key)
                if key == self.loading:
                    text, tip = tr("загрузка…"), ""
                elif layer is not None:
                    day = self._day(layer)
                    text = short_day(day) if day else "✓"
                    tip = layer.name()
                else:
                    text, tip = "-", tr("Снимка нет")
                item = QTableWidgetItem(text)
                item.setTextAlignment(enum(Qt, "AlignmentFlag",
                                           "AlignCenter"))
                item.setToolTip(tip)
                self.setItem(row, column, item)

    @staticmethod
    def _day(layer):
        from .objecttasks import layer_roles
        return layer_roles(layer)[1]

    def _clicked(self, row, column):
        rect = self.visualItemRect(self.item(row, column))
        self.picked.emit(self.years[row], SEASONS[column][0],
                         self.viewport().mapToGlobal(rect.bottomLeft()))


class SeasonPicker(QObject):
    """Подбор и загрузка снимков сезонов в таблицу: один поиск на весь ряд,
    потом по снимку в каждую пустую клетку по очереди."""

    status = pyqtSignal(str)
    done = pyqtSignal()

    def __init__(self, table, parent=None):
        super().__init__(parent)
        self.table = table
        self.choices = {}  # {(год, сезон): [(сцена, облачность, данные)]}
        self.queue = []
        self.ring = None
        self.finder = SceneFinder(self)
        self.finder.status.connect(self.status.emit)
        self.finder.found.connect(self._found)
        self.finder.loaded.connect(self._loaded)
        self.finder.failed.connect(self._failed)
        table.picked.connect(self._menu)

    def busy(self):
        return self.finder.busy() or bool(self.queue) \
            or self.table.loading is not None

    def search(self, ring):
        self.ring = list(ring)
        self.queue = []
        months = [m for _, ms in SEASONS for m in ms]
        self.finder.search(self.ring, months, years=len(self.table.years),
                           shown=10000)

    def _found(self, found):
        self.choices = fallow.pick(found)
        self.queue = [(key, self.choices[key][0][0])
                      for key in self.table.keys()
                      if key in self.choices
                      and self.table.layer(key) is None]
        if not self.queue:
            self._report()
            return
        self._next()

    def _next(self):
        if not self.queue:
            self.table.loading = None
            self.table.refresh()
            self._report()
            return
        key, scene = self.queue.pop(0)
        self.table.loading = key
        self.table.refresh()
        self.status.emit(tr("Загрузка снимка {season} {year}: {day}…",
                            season=season_name(key[1]).lower(),
                            year=key[0], day=scene.when[:10]))
        self.finder.load(scene, self.ring, products=(PRODUCT,))

    def _loaded(self, layer):
        key = self.table.loading
        if key is not None:
            self.table.set_layer(key, layer.id())
        self._next()

    def _failed(self):
        self._next()

    def _report(self):
        count = len(self.table.chosen())
        total = len(self.table.keys())
        self.status.emit(tr(
            "Снимков сезонов {count} из {total}. Пустые клетки - сезоны без "
            "чистого снимка над участком, расчёт обходится без них.",
            count=count, total=total) if count else tr(
            "Чистых весенних и осенних снимков над участком не нашлось."))
        self.done.emit()

    def _menu(self, year, season, where):
        """Меню клетки: другие даты сезона и «Без снимка»."""
        if self.busy():
            return
        key = (year, season)
        menu = QMenu(self.table)
        for scene, cloud, _ in self.choices.get(key, [])[:12]:
            action = menu.addAction(tr(
                "{day} - облачность над участком {cloud} %",
                day=scene.when[:10], cloud="{:.0f}".format(cloud)))
            action.triggered.connect(
                lambda _=False, s=scene: self._take(key, s))
        if not self.choices:
            hint = menu.addAction(tr("Сначала «Подобрать снимки»"))
            hint.setEnabled(False)
        menu.addSeparator()
        menu.addAction(tr("Без снимка")).triggered.connect(
            lambda: self.table.set_layer(key, None))
        menu.popup(where)

    def _take(self, key, scene):
        self.queue = [(key, scene)]
        self._next()


def season_name(season):
    return {"spring": tr("Весна"), "autumn": tr("Осень")}[season]
