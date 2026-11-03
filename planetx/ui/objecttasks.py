# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Выделение объектов» подменю «Анализ участка».

Типовые задачи поверх трассировки (ui/tracing.py), выбор автора от
3 ноября 2026 года (вариант Б по мысли Василия Швалёва). Задача ставит
настройки трассировки, после «Построить» цвета называются и сливаются
по правилам core/objecttasks.py, почва среди хвои отделяется рубками.
Таблица классов, OK и слой - как у трассировки, сама трассировка не
меняется. Правила работают только по снимку с известными каналами -
файлу окна «Космоснимки».
"""
import os

import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QFormLayout,
                                 QHBoxLayout, QLabel, QListWidget,
                                 QListWidgetItem, QPushButton, QSpinBox,
                                 QWidget)

from ..core import classnames, linear
from ..core import objecttasks as ot
from ..i18n import tr
from ..qt_compat import enum
from .aefclass import BASEMAP, project_rasters, read_raster
from . import s2finder
from .inset import warm
from .results import add_vector, result_path, titled
from .s2finder import SceneFinder
from .tracing import TraceDialog, TraceTool, raster_roles

SETTINGS = "PlanetX/objects/"
SUMMER = range(5, 10)  # месяцы, когда хвоя и листва различаются лучше


_ROLES = {}  # {слой: (источник, роли, день)} - подписи файла читаются раз


def layer_roles(layer):
    """Роли каналов и день съёмки растра проекта, с памятью по источнику."""
    known = _ROLES.get(layer.id())
    if known is None or known[0] != layer.source():
        roles, _ = raster_roles(layer)
        stem = os.path.splitext(os.path.basename(
            layer.source().split("|")[0]))[0]
        known = (layer.source(), roles, ot.day_of(stem))
        _ROLES[layer.id()] = known
    return known[1], known[2]


def suitable_rasters(need_red_or_swir=True):
    """Растры проекта, годные для правил: ближний ИК и, если нужно,
    красный или SWIR."""
    out = []
    for layer in project_rasters():
        roles, _ = layer_roles(layer)
        if roles and "nir" in roles and (
                not need_red_or_swir or ot.usable(roles)):
            out.append(layer)
    return out


class TaskSource(QComboBox):
    """Список «Источник» окна задач: только подходящие снимки проекта.
    Заполняется при открытии списка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.refill()

    def refill(self):
        chosen = self.currentData()
        self.blockSignals(True)
        self.clear()
        for layer in suitable_rasters():
            self.addItem(layer.name(), layer.id())
        if not self.count():
            self.addItem(tr("В проекте нет подходящего снимка"), "")
        self.setCurrentIndex(max(0, self.findData(chosen)))
        self.blockSignals(False)
        if self.currentData() != chosen:
            self.currentIndexChanged.emit(self.currentIndex())

    def showPopup(self):
        self.refill()
        super().showPopup()


class SecondBox(QComboBox):
    """Список «Второй снимок»: «Нет» и снимки проекта с ближним ИК,
    кроме выбранного источником."""

    def __init__(self, source, parent=None):
        super().__init__(parent)
        self.source = source
        self.refill()

    def refill(self):
        chosen = self.currentData()
        self.blockSignals(True)
        self.clear()
        self.addItem(tr("Нет"), "")
        for layer in suitable_rasters(False):
            if layer.id() != self.source.currentData():
                self.addItem(layer.name(), layer.id())
        self.setCurrentIndex(max(0, self.findData(chosen)))
        self.blockSignals(False)

    def showPopup(self):
        self.refill()
        super().showPopup()


def scenario_names():
    """Задачи списка: (ключ, название, подсказка)."""
    return (
        ("forest", tr("Леса и рубки"), tr(
            "Хвойный лес, лиственный лес и травы, рубки и гари, открытая "
            "почва, вода. Рубка - открытая почва, вокруг которой в полосе "
            "трёх клеток не меньше четверти - хвойный лес.")),
        ("fields", tr("Поля"), tr(
            "Растительность, открытая почва и пашня, рубки, вода. Поля "
            "остаются отдельными многоугольниками, наименьшая область "
            "крупнее.")),
        ("water", tr("Вода"), tr("Вода и всё остальное - суша.")),
    )


def kind_name(kind):
    return {ot.WATER: tr("Вода"), ot.CONIFER: tr("Хвойный лес"),
            ot.BROADLEAF: tr("Лиственный лес и травы"),
            ot.VEGETATION: tr("Растительность"),
            ot.SOIL: tr("Открытая почва"), ot.CLEARING: tr("Рубки и гари"),
            ot.SNOW: tr("Снег и лёд"), ot.OTHER: tr("Прочее")}[kind]


class TaskDialog(TraceDialog):
    """Окно «Выделение объектов». На виду - задача, снимок, второй снимок,
    участок и линейные объекты, тонкие настройки свёрнуты под
    «Дополнительно» - просьба автора от 3 ноября 2026 года «система
    громоздкая, упрости». Списки снимков - только подходящие, кнопки
    «Найти снимок» ищут сцены Sentinel-2 участка сами (ui/s2finder.py)."""

    source_class = TaskSource

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Выделение объектов"))
        settings = QgsSettings()
        self.task = QComboBox(self)
        for key, name, tip in scenario_names():
            self.task.addItem(name, key)
            self.task.setItemData(self.task.count() - 1, tip,
                                  enum(Qt, "ItemDataRole", "ToolTipRole"))
        self.task.setToolTip(tr(
            "Типовая задача ставит количество цветов и наименьшую область "
            "и после «Построить» называет классы по отражению снимка."))
        self.about = QLabel(self)
        self.about.setWordWrap(True)
        self.source.setToolTip(tr(
            "Снимок Sentinel-2 или Landsat окна «Космоснимки» - сочетание "
            "каналов или «Все каналы сцены». В списке только снимки, у "
            "которых окно узнало по подписям ближний ИК и красный или "
            "SWIR."))
        self.note = QLabel(self)
        self.note.setWordWrap(True)
        self.find = QPushButton(tr("Найти снимок"), self)
        self.find.setToolTip(tr(
            "Летние снимки Sentinel-2 участка за три года, облачность над "
            "участком до 5 %. Двойной щелчок по снимку загружает сочетание "
            "«Сельское хозяйство» (B11 B8 B2) и ставит его источником."))
        self.second = SecondBox(self.source, self)
        self.second.setToolTip(tr(
            "Снимок того же места другого сезона, лучше со снегом. Его "
            "каналы ложатся на ту же сетку участка и идут в раскладку на "
            "цвета вместе с первыми. На снегу хвоя - то, что осталось "
            "тёмным, без снега - то, у чего ближний ИК почти не изменился."))
        self.find_second = QPushButton(tr("Найти"), self)
        self.find_second.setToolTip(tr(
            "Снимки Sentinel-2 участка в марте и апреле за три года, пока "
            "лежит снег. На снегу хвоя тёмная, голый лиственный лес и поля "
            "светлые. Двойной щелчок загружает снимок и ставит его "
            "вторым."))
        self.scenes = QListWidget(self)
        self.scenes.setVisible(False)
        self.scenes.setMaximumHeight(130)
        self.scenes.setToolTip(tr("Двойной щелчок загружает снимок."))
        self.lines = QCheckBox(tr("Линейные объекты"), self)
        self.lines.setChecked(settings.value(SETTINGS + "lines", False)
                              in (True, "true"))
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
        self.more = QCheckBox(tr("Дополнительно"), self)
        self.more.setToolTip(tr(
            "Тонкие настройки: пиксель, цвета, сглаживание, наименьшая "
            "область, скругление углов, ширина линий. Задача ставит их "
            "сама."))
        self.more.setChecked(settings.value(SETTINGS + "more", False)
                             in (True, "true"))
        top = QFormLayout()
        top.addRow(tr("Задача"), self.task)
        top.addRow("", self.about)
        self.layout().insertLayout(0, top)
        form = self.form
        form.insertRow(1, "", self._row(self.note, self.find))
        form.insertRow(2, "", self.scenes)
        form.insertRow(3, tr("Второй снимок"),
                       self._row(self.second, self.find_second))
        bottom = QFormLayout()
        bottom.addRow("", self.lines)
        bottom.addRow(tr("Ширина линий до"), self.line_width)
        bottom.addRow("", self.more)
        self.layout().insertLayout(2, bottom)
        self.bottom = bottom
        self.finder = SceneFinder(self)
        self.finder.found.connect(self._found)
        self.finder.status.connect(self.status.setText)
        self.finder.loaded.connect(self._loaded)
        self.find_for = "source"
        self.find.clicked.connect(lambda: self._find("source"))
        self.find_second.clicked.connect(lambda: self._find("second"))
        self.scenes.itemDoubleClicked.connect(self._load)
        self.source.currentIndexChanged.connect(lambda _: self._note())
        self.lines.toggled.connect(lambda _: self._remember_lines())
        self.line_width.valueChanged.connect(lambda _: self._remember_lines())
        self.more.toggled.connect(lambda _: self._show_more())
        self._remember_lines()
        chosen = settings.value(SETTINGS + "task", "forest")
        self.task.setCurrentIndex(max(0, self.task.findData(chosen)))
        self.task.currentIndexChanged.connect(lambda _: self._task())
        self._task(first=True)
        self._note()

    def _row(self, *widgets):
        holder = QWidget(self)
        row = QHBoxLayout(holder)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(widgets[0], 1)
        for widget in widgets[1:]:
            row.addWidget(widget)
        return holder

    def scenario(self):
        return self.task.currentData()

    def _show_more(self):
        """Тонкие настройки видны с флажком «Дополнительно»."""
        on = self.more.isChecked()
        for form, widget in ((self.form, self.level),
                             (self.form, self.volume),
                             (self.form, self.colors),
                             (self.form, self.smooth),
                             (self.form, self.least),
                             (self.form, self.corner),
                             (self.bottom, self.line_width)):
            widget.setVisible(on)
            label = form.labelForField(widget)
            if label is not None:
                label.setVisible(on)
        QgsSettings().setValue(SETTINGS + "more", on)

    def _note(self):
        """Строка под «Источником»: подходит ли снимок и что окно узнало."""
        layer = self.raster()
        if layer is None:
            self.note.setText(tr(
                "В проекте нет снимка с ближним ИК и красным или SWIR. "
                "«Найти снимок» найдёт летний снимок Sentinel-2 участка."))
            return
        roles, day = layer_roles(layer)
        names = ", ".join(classnames.ROLE_NAMES.get(r, r)
                          for r in ot.role_names(roles))
        text = tr("Подходит. Каналы - {names}.", names=names)
        if day:
            text += " " + tr("Снимок {day}.", day=day)
            if int(day[5:7]) not in SUMMER:
                text += " " + tr("Снимок не летний, хвоя и листва "
                                 "различаются хуже.")
        self.note.setText(text)

    def _find(self, target):
        """Поиск сцен Sentinel-2 участка: летних для источника, другого
        сезона для второго снимка."""
        problem = self.area.check()
        if problem:
            self.status.setText(problem)
            return
        self.find_for = target
        self.scenes.clear()
        self.scenes.setVisible(False)
        self.finder.search(self.area.ring, s2finder.SUMMER
                           if target == "source" else s2finder.OFF_SEASON)

    def _found(self, found):
        self.scenes.clear()
        for scene, cloud, valid in found:
            item = QListWidgetItem(tr(
                "{day} - облачность над участком {cloud} %, данных "
                "{valid} %", day=scene.when[:10],
                cloud="{:.0f}".format(cloud), valid="{:.0f}".format(valid)))
            item.setData(enum(Qt, "ItemDataRole", "UserRole"), scene)
            self.scenes.addItem(item)
        self.scenes.setVisible(bool(found))

    def _load(self, item):
        scene = item.data(enum(Qt, "ItemDataRole", "UserRole"))
        if scene is not None and not self.finder.busy():
            self.finder.load(scene, self.area.ring)

    def _loaded(self, layer):
        """Загруженный снимок встаёт источником или вторым снимком."""
        if self.find_for == "second":
            self.second.refill()
            self.second.setCurrentIndex(self.second.findData(layer.id()))
            self.status.setText(tr("Второй снимок загружен: {name}.",
                                   name=layer.name()))
        else:
            self.source.refill()
            self.source.setCurrentIndex(self.source.findData(layer.id()))
            self.status.setText(tr("Снимок загружен и стоит источником: "
                                   "{name}.", name=layer.name()))
        self.scenes.setVisible(False)

    def _remember_lines(self):
        self.line_width.setEnabled(self.lines.isChecked())
        settings = QgsSettings()
        settings.setValue(SETTINGS + "lines", self.lines.isChecked())
        settings.setValue(SETTINGS + "line_width", self.line_width.value())

    def second_raster(self):
        """Второй снимок, None - «Нет» или слоя уже нет."""
        return QgsProject.instance().mapLayer(self.second.currentData()
                                              or "")

    def showEvent(self, event):
        super().showEvent(event)
        self._show_more()
        self._note()

    def _task(self, first=False):
        key = self.scenario()
        self.about.setText(dict((k, t) for k, _, t in scenario_names())[key])
        QgsSettings().setValue(SETTINGS + "task", key)
        if first:
            return
        spec = ot.SCENARIOS[key]
        self.colors.setValue(spec["colors"])
        self.smooth.setValue(spec["smooth"])
        self.least.setValue(spec["least"])


class TaskTool(TraceTool):
    """Выделение объектов участка у окна глобуса."""

    dialog_class = TaskDialog

    def __init__(self, window):
        super().__init__(window)
        self.roles = None
        self.month = None
        self.clearing = None  # номера областей-рубок
        self.notes = []  # замечания правил к строке итога
        self.rules = None  # названия цветов по правилам
        self.more_roles = None  # роли каналов второго снимка
        self.more_name = ""
        self.lines = {}  # осевые линии {группа: [ломаные в клетках]}

    def tool_title(self):
        return tr("Выделение объектов")

    def rule_names(self):
        return self.rules

    def channel_roles(self):
        roles, month = super().channel_roles()
        if self.more_roles is None or roles is None:
            return roles, month
        return list(roles) + [r and r + "@2" for r in self.more_roles], month

    def more_bands(self, box, side):
        """Каналы второго снимка на сетке первого: тот же шаг и рамка."""
        dialog = self.dialog
        self.more_roles = None
        layer = dialog.second_raster()
        if layer is None:
            return None
        if layer.id() == dialog.raster_id():
            dialog.status.setText(tr("Второй снимок совпадает с первым."))
            return False
        roles, _ = raster_roles(layer)
        if not roles or "nir" not in roles:
            dialog.status.setText(tr(
                "У второго снимка не узнать ближний ИК - нужен снимок окна "
                "«Космоснимки» с подписями каналов."))
            return False
        if not layer.crs().isValid():
            dialog.status.setText(tr("У второго снимка не задана система "
                                     "координат."))
            return False
        self.more_roles = roles
        self.more_name = layer.name()
        path, wkt = layer.source().split("|")[0], layer.crs().toWkt()

        def add(index, found):
            x0, y0, step, grid = found
            other = read_raster(path, wkt, index, box, side, step)
            if isinstance(other, str) \
                    or other[3].shape[1:] != grid.shape[1:] \
                    or not np.isfinite(other[3]).any():
                return "second"
            return x0, y0, step, np.concatenate((grid, other[3]))

        return (layer.id(), path), add

    def build(self):
        dialog = self.dialog
        if dialog is None or self.job is not None:
            return
        layer = dialog.raster()
        if dialog.raster_id() == BASEMAP or layer is None:
            dialog.status.setText(tr(
                "Нет снимка. Кнопка «Найти снимок» найдёт и загрузит летний "
                "снимок Sentinel-2 участка."))
            return
        self.roles, self.month = raster_roles(layer)
        if not ot.usable(self.roles):
            dialog.status.setText(tr(
                "У растра не узнать ближний ИК и красный или SWIR - нужен "
                "снимок окна «Космоснимки» с подписями каналов."))
            return
        super().build()

    def prepare(self, out):
        """Названия цветов по видам задачи, цвета одного вида сливаются
        с самым крупным из них, области почвы среди хвои - рубки."""
        base = self.base
        count = len(base["colors"])
        self.clearing = None
        self.notes = []
        self.rules = None
        centers = np.asarray(out["centers"], dtype=np.float64)
        if count == 0 or np.nanmax(centers) > ot.REFLECTANCE_MAX:
            self.notes.append(tr(
                "Значения растра не похожи на отражение, классы не "
                "названы."))
            return [-1] * count
        scenario = self.dialog.scenario()
        first = len(self.roles)
        raw = ot.color_kinds(centers[:, :first], self.roles)
        if self.more_roles is not None:
            raw = ot.two_dates(raw, centers, self.roles, self.more_roles)
        kinds = ot.scenario_kinds(raw, scenario)
        regions = ot.region_kinds(base["parts"], base["kinds"], raw,
                                  scenario)
        self.clearing = np.array([n for n, k in enumerate(regions)
                                  if k == ot.CLEARING], dtype=np.int64)
        parts = np.bincount(
            base["classes"][base["classes"] >= 0].ravel().astype(np.int64),
            minlength=count)[:count]
        target = [-1] * count
        first = {}
        for n in np.argsort(-parts, kind="stable"):
            n = int(n)
            kind = kinds[n]
            if kind in first:
                target[n] = first[kind]
            else:
                first[kind] = n
        base["names"] = [kind_name(k) for k in kinds]
        self.rules = list(base["names"])
        base["colors"] = [ot.KIND_COLORS[k] for k in kinds]
        base["hexes"] = ["#%02x%02x%02x" % c for c in base["colors"]]
        task = self.dialog.task.currentText()
        base["settings"] = [tr("задача «{task}»", task=task)] \
            + ([tr("второй снимок «{name}»", name=self.more_name)]
               if self.more_roles is not None else []) + base["settings"]
        if self.more_roles is not None and ot.winter(
                centers, self.roles, self.more_roles) is not None:
            self.notes.append(tr("Хвоя отделена от листвы по снегу второго "
                                 "снимка."))
        elif self.more_roles is not None:
            self.notes.append(tr("Хвоя отделена от листвы по двум "
                                 "снимкам."))
        elif self.month is not None and self.month not in SUMMER \
                and ot.CONIFER in ot.SCENARIOS[scenario]["kinds"]:
            self.notes.append(tr(
                "Снимок не летний, хвоя и листва различаются хуже."))
        if len(self.clearing):
            cells = int(np.isin(base["parts"], self.clearing).sum())
            self.notes.append(tr("Рубки и гари - {area} га.", area="{:.0f}"
                                 .format(cells * base["step"] ** 2 / 1e4)))
        self.lines = {}
        if self.dialog.lines.isChecked():
            self._find_lines(regions)
        return target

    def _find_lines(self, regions):
        """Осевые линии узких частей почвы, воды и растительности
        (core/linear.py), {группа: [ломаные в клетках]}."""
        base = self.base
        step = base["step"]
        width = self.dialog.line_width.value() / step
        least = linear.LENGTH / step
        for group, mask in ot.line_masks(base["parts"], regions).items():
            found = linear.lines(mask, width, least)
            if found:
                self.lines[group] = found
        km = sum(linear.length_m(p, step) for paths in self.lines.values()
                 for p in paths) / 1000.0
        self.notes.append(tr("Линий {km} км.", km="{:.1f}".format(km))
                          if self.lines else
                          tr("Линейных объектов не найдено."))

    def _built(self, *args, **kwargs):
        self.notes = []
        super()._built(*args, **kwargs)
        if self.result is not None and self.notes:
            self.dialog.status.setText(self.dialog.status.text() + " "
                                       + " ".join(self.notes))

    def _apply_classes(self):
        """Классы таблицы плюс рубки - области почвы среди хвои, отдельным
        классом после классов таблицы."""
        super()._apply_classes()
        result = self.result
        clearing = self.clearing
        if clearing is not None and len(clearing):
            kinds = np.array(result["kinds"], dtype=np.int64)
            kinds[clearing] = len(result["colors"])
            parts = self.base["parts"]
            classes = np.where(parts >= 0, kinds[np.maximum(parts, 0)], -1)
            color = ot.KIND_COLORS[ot.CLEARING]
            result.update(kinds=kinds, classes=classes,
                          colors=result["colors"] + [color],
                          hexes=result["hexes"] + ["#%02x%02x%02x" % color],
                          names=result["names"] + [kind_name(ot.CLEARING)])
        # Линии - только на глобусе поверх классов: области слоя прежние.
        result["areas"] = len(result["colors"])
        lines = getattr(self, "lines", None) or {}
        if lines:
            classes = np.array(result["classes"])
            for group, paths in lines.items():
                cells = linear.cells_of(paths, classes.shape) \
                    & (classes >= 0)
                classes[cells] = len(result["colors"])
                result["colors"] = result["colors"] + [ot.LINE_COLORS[group]]
                result["names"] = result["names"] + [line_name(group)]
            result["classes"] = classes

    def export(self, path=None):
        """Многоугольники, как у трассировки, рядом - линии слоем lines
        с полями kind, name и length_m."""
        result = self.result
        if result is None:
            return None
        count = result.get("areas", len(result["colors"]))
        self.result = dict(result, colors=result["colors"][:count],
                           names=result["names"][:count])
        try:
            done = super().export(path)
        finally:
            self.result = result
        lines = getattr(self, "lines", None) or {}
        if done and lines:
            self._export_lines(lines)
        return done

    def _export_lines(self, lines):
        result = self.result
        path = result_path("lines", ".gpkg")
        if not write_lines(path, result, lines):
            return None
        group = self.session.group_for(result["ring"])
        values = [(group_key, ot.LINE_COLORS[group_key],
                   line_name(group_key)) for group_key in lines]
        title = "{} {}".format(tr("Линии"), result["raster"] or "")
        return add_vector(self.window, path, "lines",
                          titled(title, result["settings"]), group,
                          (255, 255, 255), width=0.6,
                          classes=("kind", values))


def line_name(group):
    return {"roads": tr("Дороги и просеки"), "water": tr("Реки и каналы"),
            "belts": tr("Лесополосы и просеки")}[group]


def write_lines(path, result, lines):
    """Осевые линии GeoPackage в UTM: поля kind, name, length_m."""
    from osgeo import ogr, osr
    warm()
    index = result["index"]
    srs = osr.SpatialReference()
    srs.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    data = ogr.GetDriverByName("GPKG").CreateDataSource(path)
    if data is None:
        return False
    layer = data.CreateLayer("lines", srs, ogr.wkbLineString)
    for name, kind in (("kind", ogr.OFTString), ("name", ogr.OFTString),
                       ("length_m", ogr.OFTReal)):
        layer.CreateField(ogr.FieldDefn(name, kind))
    x0, y0, step = result["x0"], result["y0"], result["step"]
    defn = layer.GetLayerDefn()
    layer.StartTransaction()
    for group, paths in lines.items():
        for points in paths:
            line = ogr.Geometry(ogr.wkbLineString)
            for x, y in points:
                line.AddPoint_2D(x0 + x * step, y0 - y * step)
            feature = ogr.Feature(defn)
            feature.SetGeometry(line)
            feature.SetField("kind", group)
            feature.SetField("name", line_name(group))
            feature.SetField("length_m", line.Length())
            layer.CreateFeature(feature)
    layer.CommitTransaction()
    data = None
    return True
