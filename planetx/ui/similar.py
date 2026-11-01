# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Похожие области: окно «Похожие области» подменю «Анализ участка».

Просьба автора от 1 ноября 2026 года - указывать не точку, а область,
и находить похожие по цвету и текстуре. Источник, участок, объекты
и показ - те же, что у классификации (ui/aefclass.py). Щелчки по глобусу
обводят образец, щелчок по его первой вершине замыкает контур, образцов
может быть несколько. Ползунок «Похожесть» меняет выборку без расчёта,
ядро - core/similar.py. OK записывает найденное многоугольниками.
"""
import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDialog,
                                 QDialogButtonBox, QFormLayout, QHBoxLayout,
                                 QLabel, QPushButton, QSlider, QSpinBox,
                                 QVBoxLayout)

from ..core import aef, rasterclass, segments, similar
from ..core.features import Shape
from ..i18n import tr
from ..qt_compat import enum
from .aef import _poll_job, _run_job, index_of, open_cog, stop_point, \
    zstd_ready
from .aefclass import (AUTO, CLASS_SIDE, LAYER, RASTER_SIDE, ClassTiles,
                       SourceBox, _flag, problem_text, read_raster,
                       write_objects)
from .area import Area
from .inset import warm
from .results import (Session, accepted, add_vector, built_text,
                      keep_buttons, result_path, write_vector)
from .viewshed import fit_status

SETTINGS = "PlanetX/similar/"
# Цвета и непрозрачность - выбор помощника.
FOUND_COLOR = (255, 120, 30)
SAMPLE_COLOR = (255, 230, 60, 255)
OPACITY = 0.6
PAUSE = 150  # мс, новая выборка после паузы ползунка


class Sample(Area):
    """Контуры образцов: вершины рисуются, как у участка, замкнутый контур
    уходит в rings. Участка окон анализа не трогает."""

    shared = False

    def __init__(self, window, dialog, site):
        super().__init__(window, dialog, 1.0, RASTER_SIDE)
        self.site = site
        self.rings = []
        self.widget.hide()

    def start(self):
        self.ring = []
        self.drawing = True
        self.begin()

    def edited(self):
        if self.closed():
            self.rings.append(list(self.ring))
            self.ring = []
            self.changed.emit()
            self.site.begin()
        self.window._refresh_shapes()
        self.window.handles.sync()

    def forget(self):
        self.rings = []
        self.ring = []
        self.drawing = False
        self.changed.emit()
        self.site.begin()
        self.window._refresh_shapes()

    def shapes(self):
        if not self.visible():
            return []
        out = [Shape("polygon", list(ring), color=SAMPLE_COLOR, width=2.0)
               for ring in self.rings]
        if len(self.ring) >= 2:
            out.append(Shape("line", list(self.ring), color=SAMPLE_COLOR,
                             width=2.0))
        return out


class SimilarDialog(QDialog):
    """Окно «Похожие области». Сигналы build, limit_changed - порог
    или слияние. OK записывает найденное в проект QGIS, «Отмена» убирает
    его (ui/results.py)."""

    build = pyqtSignal()
    limit_changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Похожие области"))
        self.point = None
        settings = QgsSettings()
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.source = SourceBox(self)
        self.source.setToolTip(tr(
            "Откуда берутся цвет и текстура. Эмбеддинги AlphaEarth "
            "загружаются из сети, у растра проекта каждый канал - признак."))
        self.area = Area(window, self, 3.0, CLASS_SIDE, SETTINGS + "side")
        self.sample = Sample(window, self, self.area)
        self.year = QComboBox(self)
        for year in aef.YEARS:
            self.year.addItem(str(year), year)
        self.year.setCurrentIndex(self.year.findData(int(settings.value(
            SETTINGS + "year", aef.YEARS[-1]))))
        self.year.setToolTip(tr(
            "Год векторов AlphaEarth. Образец обводится по снимку глобуса, "
            "он может быть другого года."))
        self.level = QComboBox(self)
        self.level.addItem(tr("Авто"), AUTO)
        for level, pixel in aef.DETAIL_LEVELS:
            self.level.addItem(tr("{pixel} м", pixel=pixel), level)
        self.level.setCurrentIndex(max(0, self.level.findData(int(
            settings.value(SETTINGS + "pixel", AUTO)))))
        self.level.setToolTip(tr(
            "Пиксель сетки участка. «Авто» берёт пиксель растра или, "
            "у AlphaEarth, пиксель с наименьшей загрузкой."))
        self.scale = QSpinBox(self)
        self.scale.setRange(1, 500)
        self.scale.setValue(int(settings.value(SETTINGS + "scale",
                                               segments.SCALE)))
        self.scale.setToolTip(tr(
            "Допустимая разнородность объекта. Чем больше, тем крупнее "
            "объекты и тем больше несхожего они объединяют. Масштаб "
            "отнесён к участку, поэтому смена пикселя размер объектов "
            "почти не меняет."))
        self.weight = QSpinBox(self)
        self.weight.setRange(0, 100)
        self.weight.setSuffix(" %")
        self.weight.setValue(int(settings.value(SETTINGS + "weight",
                                                100 * segments.WEIGHT)))
        self.weight.setToolTip(tr(
            "Доля текстуры в делении на объекты и в сравнении с образцом, "
            "остальное - цвет."))
        self.least = QSpinBox(self)
        self.least.setRange(1, 100000)
        self.least.setValue(int(settings.value(SETTINGS + "least",
                                               segments.LEAST)))
        self.least.setToolTip(tr(
            "Объект меньше этого количества клеток сливается с самым "
            "похожим соседом."))
        self.limit = QSlider(enum(Qt, "Orientation", "Horizontal"), self)
        self.limit.setRange(1, 99)
        self.limit.setValue(int(settings.value(SETTINGS + "limit",
                                               similar.LIMIT)))
        self.limit.setToolTip(tr(
            "Насколько объект должен походить на образец. Выборка меняется "
            "сразу, расчёт заново не идёт. Вправо - только очень похожие, "
            "влево - шире."))
        self.limit_label = QLabel(self)
        self.limit_label.setMinimumWidth(40)
        self.join = QCheckBox(tr("Сливать соседние найденные объекты"), self)
        self.join.setChecked(_flag(settings.value(SETTINGS + "join", True)))
        self.join.setToolTip(tr(
            "Соседние найденные объекты становятся одной областью. Без "
            "флажка каждый объект остаётся отдельным многоугольником."))
        self.samples = QLabel(self)
        forget = QPushButton(tr("Убрать образцы"), self)
        forget.setToolTip(tr("Убрать все контуры образцов."))
        forget.clicked.connect(self.sample.forget)
        hint = QLabel(tr(
            "Щелчками по глобусу обведите образец, щелчок по первой вершине "
            "замыкает контур. Образцов может быть несколько."), self)
        hint.setWordWrap(True)
        limit_row = QHBoxLayout()
        limit_row.addWidget(self.limit, 1)
        limit_row.addWidget(self.limit_label)
        sample_row = QHBoxLayout()
        sample_row.addWidget(self.samples, 1)
        sample_row.addWidget(forget)
        form = QFormLayout()
        form.addRow(tr("Источник"), self.source)
        form.addRow(tr("Год"), self.year)
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Пиксель"), self.level)
        form.addRow(tr("Масштаб объектов"), self.scale)
        form.addRow(tr("Доля текстуры"), self.weight)
        form.addRow(tr("Наименьший объект, клеток"), self.least)
        form.addRow(tr("Образцы"), sample_row)
        form.addRow(tr("Похожесть"), limit_row)
        form.addRow("", self.join)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Участок делится на объекты, каждый объект сравнивается "
            "с образцами по цвету и текстуре."))
        run.clicked.connect(self.build)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(hint)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        self.source.currentIndexChanged.connect(lambda _: self._source())
        for box in (self.year, self.level):
            box.currentIndexChanged.connect(lambda _: self._remember())
        for box in (self.scale, self.weight, self.least):
            box.valueChanged.connect(lambda _: self._remember())
        self.limit.valueChanged.connect(lambda _: self._limit())
        self.join.toggled.connect(lambda _: self._limit())
        self.sample.changed.connect(self._samples_text)
        self._source()
        self._limit_text()
        self._samples_text()
        self.to_project.setEnabled(False)

    def raster_id(self):
        return self.source.currentData() or ""

    def raster(self):
        return QgsProject.instance().mapLayer(self.raster_id())

    def _source(self):
        self.year.setEnabled(not self.raster_id())
        self.area.set_most(RASTER_SIDE if self.raster_id() else CLASS_SIDE)

    def _samples_text(self):
        self.samples.setText(tr("Контуров: {n}",
                                n=len(self.sample.rings)))

    def _limit_text(self):
        self.limit_label.setText("{} %".format(self.limit.value()))

    def _limit(self):
        self._limit_text()
        self._remember()
        self.limit_changed.emit()

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "year", self.year.currentData())
        settings.setValue(SETTINGS + "pixel", self.level.currentData())
        settings.setValue(SETTINGS + "scale", self.scale.value())
        settings.setValue(SETTINGS + "weight", self.weight.value())
        settings.setValue(SETTINGS + "least", self.least.value())
        settings.setValue(SETTINGS + "limit", self.limit.value())
        settings.setValue(SETTINGS + "join", self.join.isChecked())


class SimilarTool(QObject):
    """Поиск похожих областей у окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.base = None  # расчёт: объекты, таблица, похожесть, сетка
        self.result = None  # выборка по порогу: показ и запись
        self.grid = None  # (ключ участка, сетка)
        self.pieces = None  # (ключ участка и настроек, объекты)
        self.job = None
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(lambda: _poll_job(self))
        self.pause = QTimer(self)
        self.pause.setSingleShot(True)
        self.pause.setInterval(PAUSE)
        self.pause.timeout.connect(self.apply)
        self.session = Session(window, tr("Похожие области"))

    def open_here(self, lat, lon):
        dialog = self.dialog
        if dialog is None:
            dialog = SimilarDialog(self.window)
            dialog.build.connect(self.build)
            dialog.limit_changed.connect(self.pause.start)
            dialog.finished.connect(self._closed)
            self.dialog = dialog
        dialog.source.refill()
        dialog.point = (lat, lon)
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        self.window._refresh_shapes()
        return dialog

    def _closed(self, code=0):
        if accepted(code) and self.result is not None:
            self.export()
        self.clear()
        self.session.reset()
        dialog = self.dialog
        dialog.sample.ring = []
        dialog.sample.drawing = False
        dialog.area.end()

    def taking(self):
        """Окно открыто, участок не рисуется: щелчок - вершина образца."""
        dialog = self.dialog
        return dialog is not None and dialog.isVisible() \
            and not dialog.area.drawing

    def click(self, lat, lon):
        sample = self.dialog.sample
        sample.start()
        sample.add(lat, lon)

    # --- расчёт ---------------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or dialog.point is None or self.job is not None:
            return
        layer = dialog.raster()
        if dialog.raster_id() and layer is None:
            dialog.status.setText(tr("Растра больше нет в проекте."))
            return
        if layer is None and not zstd_ready():
            dialog.status.setText(tr(
                "Нет библиотеки zstd, файлы AlphaEarth не прочитать."))
            return
        rings = list(dialog.sample.rings)
        if not rings:
            dialog.status.setText(tr("Обведите образец на глобусе."))
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        ring = list(dialog.area.ring)
        box = dialog.area.box()
        side = dialog.area.size()
        year = dialog.year.currentData()
        level = dialog.level.currentData()
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        weight = dialog.weight.value() / 100.0
        scale, least = dialog.scale.value(), dialog.least.value()
        if layer is not None:
            crs = layer.crs()
            if not crs.isValid():
                dialog.status.setText(tr(
                    "У растра не задана система координат."))
                return
            warm()
            path, wkt, name = layer.source(), crs.toWkt(), layer.name()
            pixel = None if level == AUTO else float(
                dict(aef.DETAIL_LEVELS)[level])
            key = (layer.id(), path, box, pixel)
        else:
            name = None
            key = (box, year, level)
        cached = self.grid if self.grid and self.grid[0] == key else None
        split_key = (key, tuple(ring), scale, weight, least)
        ready = self.pieces[1] if self.pieces \
            and self.pieces[0] == split_key else None

        def count(done, total):
            stop_point(self)

        def fetch():
            if layer is not None:
                index = aef.ZoneIndex(zone, [])
                found = cached[1] if cached else read_raster(
                    path, wkt, index, box, side, pixel)
                return index, found, None if isinstance(found, str) \
                    else found[3]
            index = index_of(zone)
            if index is None:
                return None, None, None
            pick = aef.auto_level(index, box, side) if level == AUTO \
                else level
            found = cached[1] if cached else aef.vectors(
                open_cog, index, box, pick, year, progress=count)
            if found is None:
                return None, None, None
            return index, found, aef.LUT[found[3].astype(np.int16) + 128]

        def work():
            index, found, values = fetch()
            if found is None:
                return None
            if isinstance(found, str):
                return {"problem": found}
            stop_point(self)
            x0, y0, step, _ = found
            shape = values.shape[1:]
            inside = aef.ring_mask(index, x0, y0, step, shape, ring)
            share = rasterclass.covered(values, inside)
            if share <= 0.0:
                return {"problem": "outside", "found": found}
            if segments.too_big(*shape):
                return {"problem": "pieces", "found": found}
            parts = ready
            if parts is None:
                cells = int((rasterclass.usable(values) & inside).sum())
                parts = segments.segment(
                    values, inside, segments.site_scale(scale, cells),
                    weight, least, progress=lambda _: stop_point(self))
            stop_point(self)
            if int(parts.max()) < 1:
                return {"problem": "whole", "found": found, "parts": parts}
            table = segments.table(values, parts)
            rows = [similar.sample_rows(
                table, parts,
                aef.ring_mask(index, x0, y0, step, shape, sample))
                for sample in rings]
            lost = sum(1 for row in rows if not len(row))
            if lost == len(rows):
                return {"problem": "samples", "found": found, "parts": parts}
            score = similar.scores(table, segments.areas(parts),
                                   np.concatenate(rows), weight)
            if score is None:
                return {"problem": "flat", "found": found, "parts": parts}
            return {"index": index, "found": found, "parts": parts,
                    "values": values, "score": score, "lost": lost,
                    "cells": int((parts >= 0).sum())}

        dialog.status.setText(tr("Ищутся похожие объекты…"))
        _run_job(self, work, lambda out: self._built(
            out, key, split_key, box, year, name, rings, ring),
            tr("Похожие области"))

    def _built(self, out, key, split_key, box, year, raster, rings, ring):
        dialog = self.dialog
        if out is None:
            dialog.status.setText(tr("Для участка нет данных."))
            return
        if out.get("found") is not None:
            self.grid = (key, out["found"])
        if out.get("parts") is not None:
            self.pieces = (split_key, out["parts"])
        if out.get("problem"):
            dialog.status.setText(tr(
                "В контурах образцов нет объектов участка.")
                if out["problem"] == "samples"
                else problem_text(out["problem"]))
            return
        x0, y0, step, _ = out["found"]
        self.base = {"index": out["index"], "x0": x0, "y0": y0, "step": step,
                     "parts": out["parts"], "values": out["values"],
                     "score": out["score"], "lost": out["lost"],
                     "cells": out["cells"], "box": box, "year": year,
                     "raster": raster, "label": raster or str(year),
                     "ring": ring, "samples": rings}
        self.apply()

    def apply(self):
        """Выборка по порогу и слиянию окна: без расчёта."""
        base, dialog = self.base, self.dialog
        if base is None or dialog is None:
            return
        shown, mean = similar.pick(base["parts"], base["score"],
                                   dialog.limit.value() / 100.0,
                                   dialog.join.isChecked())
        self.result = dict(base, parts=shown, similar=mean,
                           classes=np.where(shown >= 0, 0, -1),
                           kinds=np.zeros(len(mean), dtype=np.int32),
                           colors=[FOUND_COLOR],
                           names=[tr("Похожие области")])
        step = base["step"]
        cells = int((shown >= 0).sum())
        hectares = cells * step * step / 1e4
        text = tr("Найдено объектов {n}, {area} га, {share} % участка.",
                  n=len(mean), area="{:.3g}".format(hectares),
                  share="{:.0f}".format(100.0 * cells / max(base["cells"],
                                                            1)))
        if base["lost"]:
            text += " " + tr("Контуров вне объектов участка: {n}.",
                             n=base["lost"])
        dialog.status.setText(text + " " + built_text())
        dialog.to_project.setEnabled(len(mean) > 0)
        self.show()

    # --- показ ----------------------------------------------------------

    def show(self):
        window = self.window
        result = self.result
        keep = self.tiles is not None
        self._drop_tiles()
        if result is None:
            return
        if not keep:
            # Смена порога - поверх прежних картинок, без мигания.
            window.class_tool.clear()
            window._show_viewshed(None)
        tiles = ClassTiles(result, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             window.view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        layer = window.view.gibs[LAYER]
        layer.max_level = aef_level(result)
        layer.empty.clear()
        window.view.set_gibs(LAYER, True, tiles, keep=keep)
        layer.fade = 1.0 - OPACITY
        window.view.update()

    def _drop_tiles(self):
        if self.tiles is not None:
            self.window.view.gibs[LAYER].fade = 0.0
            self.tiles.abort()
            self.tiles.deleteLater()
            self.tiles = None

    def drop(self):
        """Слой вида занимает другой инструмент."""
        self._drop_tiles()
        self.base = None
        self.result = None
        if self.dialog is not None:
            self.dialog.to_project.setEnabled(False)

    def clear(self):
        shown = self.tiles is not None
        self.drop()
        if shown:
            self.window.view.set_gibs(LAYER, False)

    # --- выгрузка -------------------------------------------------------

    def export(self, path=None):
        """Найденное многоугольниками GeoPackage в подгруппу расчёта: поле
        similar - похожесть в процентах, рядом контуры образцов."""
        result = self.result
        if result is None or not len(result["similar"]):
            return None
        tag = result["year"] or "raster"
        path = path or result_path("similar_{}".format(tag), ".gpkg")
        data = dict(result, table=segments.table(result["values"],
                                                 result["parts"]))
        if not write_objects(path, data):
            self.dialog.status.setText(tr("Слой не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        layer = add_vector(self.window, path, "objects",
                           tr("Похожие области {year}", year=result["label"]),
                           group, FOUND_COLOR, width=0.4,
                           fill=FOUND_COLOR + (150,))
        if layer is not None and result["raster"] is None:
            meta = layer.metadata()
            meta.setRights([aef.CREDIT])
            layer.setMetadata(meta)
        samples = result_path("similar_samples_{}".format(tag), ".gpkg")
        if write_vector(samples, "samples", "polygon",
                        [(ring, {}) for ring in result["samples"]], []):
            add_vector(self.window, samples, "samples", tr("Образцы"), group,
                       SAMPLE_COLOR, width=0.6, fill=(255, 255, 255, 0))
        return path

    def close(self):
        self.timer.stop()
        self.pause.stop()
        self._drop_tiles()
        if self.dialog is not None:
            self.dialog.close()


def aef_level(result):
    """Глубина тайлов слоя вида по шагу сетки."""
    import math
    lat = (result["box"][1] + result["box"][3]) / 2.0
    pixel = 2 * math.pi * 6378137.0 * math.cos(math.radians(lat)) / 256
    return max(1, min(18, int(math.ceil(math.log2(pixel / result["step"])))))
