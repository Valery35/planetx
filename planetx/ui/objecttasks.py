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
import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QComboBox, QFormLayout, QLabel

from ..core import objecttasks as ot
from ..i18n import tr
from ..qt_compat import enum
from .aefclass import BASEMAP, project_rasters, read_raster
from .tracing import TraceDialog, TraceTool, raster_roles

SETTINGS = "PlanetX/objects/"
SUMMER = range(5, 10)  # месяцы, когда хвоя и листва различаются лучше


class SecondBox(QComboBox):
    """Список «Второй снимок»: «Нет» и растры проекта, заполняется при
    открытии списка."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.refill()

    def refill(self):
        chosen = self.currentData()
        self.blockSignals(True)
        self.clear()
        self.addItem(tr("Нет"), "")
        for layer in project_rasters():
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
    """Окно «Выделение объектов»: список «Задача» над полями трассировки."""

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Выделение объектов"))
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
        self.need = QLabel(tr(
            "Нужен снимок окна «Космоснимки» - сочетание каналов "
            "или «Все каналы» Sentinel-2 или Landsat: по подписям каналов "
            "окно узнаёт ближний ИК, красный и SWIR. Хвоя от листвы лучше "
            "отделяется на летнем снимке."), self)
        self.need.setWordWrap(True)
        self.second = SecondBox(self)
        self.second.setToolTip(tr(
            "Снимок того же места другой даты, лучше другого сезона, тоже "
            "из окна «Космоснимки». Его каналы ложатся на ту же сетку "
            "участка и идут в раскладку на цвета вместе с первыми. Хвоя "
            "отделяется от листвы и трав по ближнему ИК: у хвои на двух "
            "датах он почти не меняется."))
        form = QFormLayout()
        form.addRow(tr("Задача"), self.task)
        form.addRow("", self.about)
        form.addRow(tr("Второй снимок"), self.second)
        self.layout().insertLayout(0, form)
        self.layout().insertWidget(1, self.need)
        chosen = QgsSettings().value(SETTINGS + "task", "forest")
        self.task.setCurrentIndex(max(0, self.task.findData(chosen)))
        self.task.currentIndexChanged.connect(lambda _: self._task())
        self._task(first=True)

    def scenario(self):
        return self.task.currentData()

    def second_raster(self):
        """Второй снимок, None - «Нет» или слоя уже нет."""
        return QgsProject.instance().mapLayer(self.second.currentData()
                                              or "")

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
                "Правилам нужны каналы снимка, у подложки глобуса их нет. "
                "Возьмите снимок окна «Космоснимки»."))
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
        if self.more_roles is not None:
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
        return target

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
        clearing = self.clearing
        if clearing is None or not len(clearing):
            return
        result = self.result
        kinds = np.array(result["kinds"], dtype=np.int64)
        extra = len(result["colors"])
        kinds[clearing] = extra
        parts = self.base["parts"]
        classes = np.where(parts >= 0, kinds[np.maximum(parts, 0)], -1)
        color = ot.KIND_COLORS[ot.CLEARING]
        result.update(kinds=kinds, classes=classes,
                      colors=result["colors"] + [color],
                      hexes=result["hexes"] + ["#%02x%02x%02x" % color],
                      names=result["names"] + [kind_name(ot.CLEARING)])
