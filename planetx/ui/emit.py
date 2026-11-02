# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Минеральные карты EMIT: окно «Минералы EMIT» подменю «Анализ
участка».

Просьба автора от 2 ноября 2026 года. Сцены участка - каталог NASA CMR
(core/emit.py), файл сцены - netCDF4 по ключу Earthdata (тот же, что
у ASTER после 2006 года), скачивается один раз в PlanetX/emit профиля.
Чтение - многомерный интерфейс GDAL в рабочем потоке, полоса съёмки
переводится на сетку широт и долгот по таблице GLT и на сетку участка
в UTM ближайшим соседом. Классы - минералы выбранной группы, показ
и подгруппа расчёта - как у классификации (ui/aefclass.py).
"""
import json
import os

import numpy as np
from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QDate, QObject, Qt, QTimer, pyqtSignal
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (QComboBox, QDateEdit, QDialog,
                                 QDialogButtonBox, QFormLayout, QHBoxLayout,
                                 QLabel, QListWidget, QListWidgetItem,
                                 QPushButton, QSpinBox, QVBoxLayout)

from ..core import aef, emit
from ..i18n import tr
from ..net.overlay import fetch_bytes, resolve_redirect
from ..qt_compat import enum
from .aef import _poll_job, _run_job, stop_point, write_utm
from .aefclass import LAYER, ClassTiles, add_classes, write_classes
from .area import Area
from .export import add_raster
from .inset import warm
from .results import Session, accepted, built_text, keep_buttons, \
    result_path, show_layer
from .sentinel import EARTHDATA_KEY, earthdata_token
from .similar import aef_level
from .viewshed import fit_status

SETTINGS = "PlanetX/emit/"
SIDE = 10.0  # км, участок по умолчанию
MOST_SIDE = 200.0  # км, наибольшая сторона участка
OPACITY = 0.7
PREVIEW = 220  # пикселей, картинка сцены
# Шкала глубины полосы поглощения в проекте: малая - светлее.
DEPTH_STOPS = [(0.0, (255, 255, 204)), (0.1, (253, 141, 60)),
               (0.25, (189, 0, 38)), (0.5, (60, 0, 30))]


def folder():
    path = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        "emit")
    os.makedirs(path, exist_ok=True)
    return path


def group_names():
    return ((1, tr("Группа 1 - железистые минералы, 0.4-1.3 мкм")),
            (2, tr("Группа 2 - глины, слюда, карбонаты, сульфаты, "
                   "2.0-2.5 мкм")))


def _maybe(group, name):
    """Массив группы или None: при включённых исключениях GDAL
    отсутствие массива - RuntimeError."""
    try:
        return group.OpenMDArray(name)
    except RuntimeError:
        return None


def _array(group, name):
    array = _maybe(group, name)
    if array is None:
        raise KeyError(name)
    return array


def _text(array):
    """Строки или числа одномерного массива GDAL."""
    try:
        values = array.Read()
    except (RuntimeError, TypeError):
        values = None
    if isinstance(values, (list, tuple)):
        return [v.decode() if isinstance(v, bytes) else str(v)
                for v in values]
    return [str(v) for v in np.asarray(array.ReadAsArray()).ravel()]


def _attribute(group, name):
    attribute = group.GetAttribute(name)
    if attribute is None:
        return None
    return attribute.Read()


def read_file(path, number):
    """Файл EMIT L2B MIN: (номера минералов, глубина) группы number на
    сетке широт и долгот по GLT, геопреобразование и названия
    минералов группы {номер: название}. Рабочий поток. Ошибка чтения -
    OSError."""
    from osgeo import gdal
    data = gdal.OpenEx(path, gdal.OF_MULTIDIM_RASTER)
    if data is None:
        raise OSError("unreadable")
    root = data.GetRootGroup()
    try:
        ids = _array(root, "group_{}_mineral_id".format(number)) \
            .ReadAsArray()
        depth = _array(root, "group_{}_band_depth".format(number)) \
            .ReadAsArray()
        location = root.OpenGroup("location")
        glt_x = _array(location, "glt_x").ReadAsArray()
        glt_y = _array(location, "glt_y").ReadAsArray()
        transform = _attribute(root, "geotransform")
        if transform is not None and len(transform) == 6:
            transform = tuple(float(v) for v in transform)
        else:
            transform = emit.fit_transform(
                glt_x, glt_y, _array(location, "lat").ReadAsArray(),
                _array(location, "lon").ReadAsArray())
        try:
            meta = root.OpenGroup("mineral_metadata")
        except RuntimeError:
            meta = None
        names = {}
        if meta is not None:
            index = [int(float(v)) for v in _text(_array(meta, "index"))]
            kinds = [int(float(v)) for v in _text(_array(meta, "group"))]
            files = _text(_array(meta, "name"))
            sample = _maybe(meta, "sample_name")
            samples = _text(sample) if sample is not None else None
            names = emit.names_of(index, kinds, files, samples) \
                .get(number, {})
    except (KeyError, AttributeError, RuntimeError, ValueError) as error:
        raise OSError(str(error)) from error
    if not emit.fit_ok(transform):
        raise OSError("geotransform")
    fill = -9999
    ids = ids.astype(np.int32)
    ids[ids == fill] = -1
    depth = depth.astype(np.float32)
    depth[depth <= fill + 1] = np.nan
    covered = emit.ortho(np.ones(ids.shape, dtype=np.float32), glt_x,
                         glt_y)
    return (emit.ortho(ids, glt_x, glt_y, fill=-1),
            emit.ortho(depth, glt_x, glt_y), covered, transform, names)


def to_site(ids, depth, covered, transform, index, box):
    """Номера, глубина и покрытие сценой на сетке участка в UTM с шагом
    emit.STEP, ближайшим соседом: (x0, y0, шаг, номера, глубина, клетки
    под сценой) или None."""
    from osgeo import gdal, osr
    rows, cols = ids.shape
    mem = gdal.GetDriverByName("MEM").Create("", cols, rows, 3,
                                             gdal.GDT_Float32)
    mem.SetGeoTransform(transform)
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(4326)
    mem.SetProjection(srs.ExportToWkt())
    for n, values in enumerate((np.where(ids >= 0, ids, np.nan),
                                np.where(ids >= 0, depth, np.nan),
                                covered)):
        band = mem.GetRasterBand(n + 1)
        band.SetNoDataValue(float("nan"))
        band.WriteArray(np.asarray(values, dtype=np.float32))
    utm = osr.SpatialReference()
    utm.ImportFromEPSG((32700 if index.south else 32600) + index.number)
    step = emit.STEP
    x0, y0, width, height = aef.grid_frame(index, box, step)
    out = gdal.Warp("", mem, format="MEM", dstSRS=utm.ExportToWkt(),
                    outputBounds=(x0, y0 - height * step,
                                  x0 + width * step, y0),
                    width=width, height=height, resampleAlg="near",
                    srcNodata="nan", dstNodata="nan",
                    outputType=gdal.GDT_Float32)
    if out is None:
        return None
    grid_ids = out.GetRasterBand(1).ReadAsArray()
    grid_depth = out.GetRasterBand(2).ReadAsArray()
    seen = np.isfinite(out.GetRasterBand(3).ReadAsArray())
    good = np.isfinite(grid_ids)
    whole = np.full(grid_ids.shape, -1, dtype=np.int32)
    whole[good] = grid_ids[good].astype(np.int32)
    return x0, y0, step, whole, grid_depth, seen


class EmitDialog(QDialog):
    """Окно «Минералы EMIT»."""

    build = pyqtSignal()
    search = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.setWindowTitle(tr("Минералы EMIT"))
        self.point = None
        self.scenes = []
        settings = QgsSettings()
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        self.area = Area(window, self, SIDE, MOST_SIDE, SETTINGS + "side")
        today = QDate.currentDate()
        self.start = QDateEdit(self)
        self.start.setCalendarPopup(True)
        self.start.setDisplayFormat("yyyy-MM-dd")
        self.start.setMinimumDate(QDate.fromString(emit.FIRST_DAY,
                                                   "yyyy-MM-dd"))
        self.start.setDate(QDate.fromString(emit.FIRST_DAY, "yyyy-MM-dd"))
        self.end = QDateEdit(self)
        self.end.setCalendarPopup(True)
        self.end.setDisplayFormat("yyyy-MM-dd")
        self.end.setDate(today)
        self.cloud = QSpinBox(self)
        self.cloud.setRange(0, 100)
        self.cloud.setSuffix(" %")
        self.cloud.setValue(int(settings.value(SETTINGS + "cloud", 30)))
        self.cloud.setToolTip(tr(
            "Наибольшая облачность сцены по каталогу NASA. Облака "
            "закрывают минералы, клетки под ними остаются без класса."))
        find = QPushButton(tr("Найти сцены"), self)
        find.clicked.connect(self.search)
        dates = QHBoxLayout()
        dates.addWidget(self.start)
        dates.addWidget(QLabel("-", self))
        dates.addWidget(self.end)
        dates.addWidget(find)
        self.list = QListWidget(self)
        self.list.setMinimumHeight(120)
        self.list.setToolTip(tr(
            "Сцены EMIT над участком, новые первыми: дата, облачность, доля "
            "участка под сценой."))
        self.preview = QLabel(self)
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setAlignment(enum(Qt, "AlignmentFlag", "AlignCenter"))
        self.group = QComboBox(self)
        for number, name in group_names():
            self.group.addItem(name, number)
        self.group.setCurrentIndex(max(0, self.group.findData(
            int(settings.value(SETTINGS + "group", 2)))))
        self.group.setToolTip(tr(
            "Группа 1 - полосы поглощения железа в видимом и ближнем "
            "инфракрасном диапазоне, группа 2 - полосы связей Al-OH, "
            "Mg-OH и карбонатов в коротковолновом инфракрасном. В одной "
            "клетке бывают минералы обеих групп."))
        self.group.currentIndexChanged.connect(self._remember)
        form = QFormLayout()
        form.addRow(tr("Участок"), self.area.widget)
        form.addRow(tr("Даты"), dates)
        form.addRow(tr("Облачность до"), self.cloud)
        form.addRow(tr("Сцены"), self.list)
        form.addRow("", self.preview)
        form.addRow(tr("Группа"), self.group)
        hint = QLabel(tr(
            "Карты минералов NASA по снимкам спектрометра EMIT на МКС, "
            "пиксель 60 м, засушливые области с 2022 года. Файлы сцен "
            "NASA отдаёт по ключу Earthdata."), self)
        hint.setWordWrap(True)
        buttons = QDialogButtonBox(self)
        run = QPushButton(tr("Построить"), self)
        run.setDefault(True)
        run.setToolTip(tr(
            "Загружает файл выбранной сцены (один раз) и раскрашивает "
            "участок минералами выбранной группы."))
        run.clicked.connect(self.build)
        buttons.addButton(run, enum(QDialogButtonBox, "ButtonRole",
                                    "ActionRole"))
        self.to_project = keep_buttons(self, buttons)
        layout = QVBoxLayout(self)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.status)
        layout.addWidget(buttons)
        fit_status(self, layout)
        self.cloud.valueChanged.connect(lambda _: self._remember())
        self.to_project.setEnabled(False)

    def _remember(self):
        settings = QgsSettings()
        settings.setValue(SETTINGS + "cloud", self.cloud.value())
        settings.setValue(SETTINGS + "group", self.group.currentData())

    def scene(self):
        item = self.list.currentItem()
        if item is None:
            return None
        n = item.data(enum(Qt, "ItemDataRole", "UserRole"))
        return self.scenes[n] if 0 <= n < len(self.scenes) else None

    def set_scenes(self, scenes):
        self.scenes = scenes
        self.list.clear()
        for n, s in enumerate(scenes):
            item = QListWidgetItem(tr(
                "{when}, облачность {cloud} %, участка {share} %",
                when=s["when"][:16], cloud="{:.0f}".format(s["cloud"]),
                share="{:.0f}".format(100.0 * s["share"])))
            item.setData(enum(Qt, "ItemDataRole", "UserRole"), n)
            item.setToolTip(s["id"])
            self.list.addItem(item)
        if scenes:
            self.list.setCurrentRow(0)


class EmitTool(QObject):
    """Минеральные карты EMIT у окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.dialog = None
        self.tiles = None
        self.result = None
        self.job = None
        self.replies = []
        self.request = 0
        self.timer = QTimer(self)
        self.timer.setInterval(100)
        self.timer.timeout.connect(lambda: _poll_job(self))
        self.session = Session(window, tr("Минералы EMIT"))
        # Адрес каталога, адрес хранилища: шаги проверки ставят свои.
        self.search_url = emit.cmr_url

    def open_here(self, lat, lon):
        dialog = self.dialog
        if dialog is None:
            dialog = EmitDialog(self.window)
            dialog.build.connect(self.build)
            dialog.search.connect(self.search)
            dialog.finished.connect(self._closed)
            dialog.list.currentRowChanged.connect(lambda _: self._preview())
            dialog.area.changed.connect(self._shares)
            self.dialog = dialog
        dialog.point = (lat, lon)
        dialog.status.setText("")
        dialog.show()
        dialog.raise_()
        dialog.area.open_at(lat, lon)
        self.window._refresh_shapes()
        self.search()
        return dialog

    def _closed(self, code=0):
        if accepted(code) and self.result is not None:
            self.export()
        self.clear()
        self.session.reset()
        self.replies = []
        self.dialog.area.end()

    # --- сцены ----------------------------------------------------------

    def search(self):
        dialog = self.dialog
        if dialog is None or dialog.area.check():
            if dialog is not None:
                dialog.status.setText(dialog.area.check())
            return
        self.request += 1
        request = self.request
        ring = list(dialog.area.ring)
        start = dialog.start.date().toString("yyyy-MM-dd")
        end = dialog.end.date().toString("yyyy-MM-dd")
        answers = {}
        dialog.set_scenes([])
        dialog.status.setText(tr("Поиск сцен EMIT…"))
        self.replies = []
        for collection, version in emit.COLLECTIONS:
            url = self.search_url(ring, start, end, dialog.cloud.value(),
                                  collection)
            self.replies.append(fetch_bytes(
                url, lambda data, error, v=version:
                self._found(request, v, data, error, answers),
                prefer_cache=False))

    def _found(self, request, version, data, error, answers):
        if request != self.request or self.dialog is None:
            return
        try:
            parsed = json.loads(data.decode("utf-8")) if data else None
        except ValueError:
            parsed = None
        answers[version] = emit.parse_cmr(parsed, version) \
            if parsed is not None else None
        if parsed is None:
            answers.setdefault("error", error or "-")
        if len(answers) - ("error" in answers) < len(emit.COLLECTIONS):
            return
        lists = [answers.get(v) or [] for _, v in emit.COLLECTIONS]
        scenes = emit.merge(lists)
        self._shares(scenes)
        dialog = self.dialog
        if scenes:
            dialog.status.setText(tr("Сцен над участком: {n}.",
                                     n=len(scenes)))
        elif "error" in answers:
            dialog.status.setText(tr("Каталог NASA не ответил: {error}",
                                     error=answers["error"]))
        else:
            dialog.status.setText(tr(
                "Над участком сцен EMIT нет. EMIT снимает засушливые "
                "области - пустыни, полупустыни, степи."))

    def _shares(self, scenes=None):
        dialog = self.dialog
        if dialog is None:
            return
        scenes = dialog.scenes if scenes is None else scenes
        ring = list(dialog.area.ring)
        for s in scenes:
            s["share"] = emit.coverage(s["polygon"], ring)
        scenes = [s for s in scenes if s["share"] > 0.0]
        dialog.set_scenes(scenes)

    def _preview(self):
        dialog = self.dialog
        if dialog is None:
            return
        dialog.preview.clear()
        s = dialog.scene()
        if s is None or not s.get("preview"):
            return
        self.replies.append(fetch_bytes(
            s["preview"], lambda data, error, scene=s:
            self._picture(scene, data)))

    def _picture(self, scene, data):
        dialog = self.dialog
        if dialog is None or dialog.scene() is not scene or not data:
            return
        picture = QPixmap()
        if picture.loadFromData(data):
            dialog.preview.setPixmap(picture.scaled(
                PREVIEW, PREVIEW,
                enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
                enum(Qt, "TransformationMode", "SmoothTransformation")))

    # --- файл и расчёт --------------------------------------------------

    def build(self):
        dialog = self.dialog
        if dialog is None or self.job is not None:
            return
        problem = dialog.area.check()
        if problem:
            dialog.status.setText(problem)
            return
        s = dialog.scene()
        if s is None:
            dialog.status.setText(tr("Выберите сцену в списке."))
            return
        path = os.path.join(folder(), s["url"].rsplit("/", 1)[-1])
        if os.path.isfile(path) and os.path.getsize(path) > 0:
            self._compute(s, path)
            return
        token = earthdata_token(dialog)
        if not token:
            dialog.status.setText(tr("Без ключа Earthdata файлы NASA "
                                     "не загружаются."))
            return
        dialog.status.setText(tr("Адрес файла NASA…"))
        self.replies.append(resolve_redirect(
            s["url"], {"Authorization": "Bearer " + token},
            lambda url, error: self._signed(s, path, url, error)))

    def _signed(self, scene, path, url, error):
        dialog = self.dialog
        if dialog is None or dialog.scene() is not scene:
            return
        if url is None or emit.LOGIN_HOST in url:
            if url is not None:
                QgsSettings().remove(EARTHDATA_KEY)
                dialog.status.setText(tr(
                    "Ключ Earthdata не принят - устарел или неверен. "
                    "При следующей загрузке окно спросит новый."))
            else:
                dialog.status.setText(tr("Файл NASA не получен: {error}",
                                         error=error or "-"))
            return
        dialog.status.setText(tr("Загрузка файла сцены {when}…",
                                 when=scene["when"][:16]))
        self.replies.append(fetch_bytes(
            url, lambda data, err: self._loaded(scene, path, data, err),
            prefer_cache=False))

    def _loaded(self, scene, path, data, error):
        dialog = self.dialog
        if dialog is None:
            return
        if not data:
            dialog.status.setText(tr("Файл NASA не получен: {error}",
                                     error=error or "-"))
            return
        part = path + ".part"
        with open(part, "wb") as fh:
            fh.write(data)
        os.replace(part, path)
        if dialog.scene() is scene:
            self._compute(scene, path)

    def _compute(self, scene, path):
        dialog = self.dialog
        ring = list(dialog.area.ring)
        box = dialog.area.box()
        number = dialog.group.currentData()
        lat, lon = dialog.point
        zone = aef.zone_of(lon, lat)
        warm()

        def work():
            index = aef.ZoneIndex(zone, [])
            try:
                ids, depth, covered, transform, names = read_file(
                    path, number)
            except OSError:
                return {"problem": "file"}
            stop_point(self)
            grid = to_site(ids, depth, covered, transform, index, box)
            if grid is None:
                return {"problem": "file"}
            x0, y0, step, grid_ids, grid_depth, seen = grid
            inside = aef.ring_mask(index, x0, y0, step, grid_ids.shape,
                                   ring)
            if not (inside & seen).any():
                return {"problem": "outside"}
            kinds, kept = emit.classes(grid_ids, grid_depth, inside)
            depth_out = np.where(inside, grid_depth, np.nan) \
                .astype(np.float32)
            return {"index": index, "x0": x0, "y0": y0, "step": step,
                    "kinds": kinds, "kept": kept, "names": names,
                    "depth": depth_out,
                    "cells": int((inside & seen).sum())}

        dialog.status.setText(tr("Минералы сцены {when}…",
                                 when=scene["when"][:16]))
        _run_job(self, work, lambda out: self._built(
            out, scene, box, ring, number), tr("Минералы EMIT"))

    def _built(self, out, scene, box, ring, number):
        dialog = self.dialog
        if dialog is None:
            return
        if out.get("problem"):
            dialog.status.setText(
                tr("Файл сцены не прочитан.") if out["problem"] == "file"
                else tr("Участок вне сцены."))
            return
        kept, names = out["kept"], out["names"]
        if not kept:
            self.clear()
            dialog.status.setText(
                tr("Минералов этой группы на участке не найдено.") + " "
                + built_text())
            return
        labels = [names.get(m, str(m)) if m >= 0 else tr("Прочие")
                  for m in kept]
        label = tr("{when}, группа {group}", when=scene["when"][:10],
                   group=number)
        self.result = {"index": out["index"], "x0": out["x0"],
                       "y0": out["y0"], "step": out["step"],
                       "classes": out["kinds"], "depth": out["depth"],
                       "box": box, "ring": ring,
                       "colors": [emit.color(m) for m in kept],
                       "names": labels, "raster": scene["id"],
                       "label": label, "year": None, "credit": emit.CREDIT}
        parts = ["{} {:.0f}%".format(labels[n], 100.0 * share)
                 for n, share in emit.shares(out["kinds"], len(kept))[:6]]
        found = int((out["kinds"] >= 0).sum())
        cells = max(out["cells"], 1)
        if parts:
            text = tr("Минералы: {list}. Клеток с минералом {share} % "
                      "участка, {area} км².", list=", ".join(parts),
                      share="{:.0f}".format(100.0 * found / cells),
                      area="{:.1f}".format(emit.area_km2(found)))
        else:
            text = tr("Минералов этой группы на участке не найдено.")
        dialog.status.setText(text + " " + built_text())
        dialog.to_project.setEnabled(bool(found))
        self.show()

    # --- показ ----------------------------------------------------------

    def show(self):
        window = self.window
        result = self.result
        self._drop_tiles()
        if result is None:
            return
        window.class_tool.clear()  # слой вида один
        window.similar_tool.clear()
        window.spectral_tool.clear()
        window.earthwork.clear()
        window._show_viewshed(None)
        tiles = ClassTiles(result, parent=self)
        tiles.loaded.connect(lambda key, rgba, levels:
                             window.view.add_gibs(LAYER, key, levels))
        self.tiles = tiles
        layer = window.view.gibs[LAYER]
        layer.max_level = aef_level(result)
        layer.empty.clear()
        window.view.set_gibs(LAYER, True, tiles)
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
        """Минералы и глубина полосы растрами в подгруппу расчёта."""
        result = self.result
        if result is None:
            return None
        path = path or result_path("emit_minerals")
        if not write_classes(path, result):
            self.dialog.status.setText(tr("Растр не записан в «{path}».",
                                          path=path))
            return None
        group = self.session.group_for(result["ring"])
        layer = add_classes(path, tr("Минералы EMIT {name}",
                                     name=result["label"]), result, group)
        if layer is not None:
            layer.setOpacity(OPACITY)
        show_layer(self.window, layer)
        depth_path = result_path("emit_depth")
        if write_utm(depth_path, result["index"], result["x0"],
                     result["y0"], result["step"], result["depth"]):
            add_raster(depth_path, tr("Глубина полосы поглощения EMIT"),
                       DEPTH_STOPS, group=group, abstract=emit.CREDIT)
        self.dialog.status.setText(tr("Минералы и глубина полосы в "
                                      "проекте."))
        return path

    def close(self):
        self.timer.stop()
        self._drop_tiles()
        self.replies = []
        if self.dialog is not None:
            self.dialog.close()
