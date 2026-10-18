# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Облака точек слоёв проекта на глобусе.

Облако - слой QGIS (QgsPointCloudLayer) файла COPC, LAS или LAZ,
отмеченный в разделе «Проект QGIS». Своих зависимостей у модуля нет:
точки читает pdal.exe из состава QGIS отдельными процессами (QProcess),
главный поток и интерпретатор их не ждут. LAS и LAZ один раз
переводятся в COPC, копия лежит в профиле PlanetX/pointclouds по
отпечатку файла, исходный файл не меняется. Клетки выбирает ядро
(core.pointcloud.select) в каждом кадре, ответ PDAL - файл LAS без
сжатия, его разбор и вершины - в рабочем потоке, буферы - в кадре
(render/pointcloud.py).

Python-обёртка QGIS 4 не отдаёт точки узла индекса облака
(у QgsPointCloudIndex нет nodeData), а identify провайдера строит
словарь на точку - около 50 мкс на точку в главном потоке. Поэтому
точки идут через PDAL, проверено 18 октября 2026 года.
"""
import hashlib
import os
import shutil
import time

import numpy as np

from qgis.core import (Qgis, QgsApplication, QgsCoordinateReferenceSystem,
                       QgsCoordinateTransform, QgsDoubleRange, QgsGeometry,
                       QgsPointCloudLayer, QgsPointXY, QgsProject,
                       QgsRectangle)
from qgis.PyQt.QtCore import QObject, QProcess, QTimer

from .. import journal
from ..core import lod
from ..core import pointcloud as core
from ..core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ..i18n import tr
from ..net.gdalnet import executor
from .project import read_pointclouds

PARALLEL = 3  # процессов PDAL с клетками одновременно, не больше
POLL = 40  # мс между проверками разбора в рабочем потоке
WORKERS = 2
FOLDER = "pointclouds"


def cache_folder():
    path = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        FOLDER)
    os.makedirs(path, exist_ok=True)
    return path


def pdal_program():
    """pdal из состава QGIS: bin рядом с apps на Windows, иначе PATH."""
    prefix = QgsApplication.prefixPath()
    for path in (os.path.join(prefix, "..", "..", "bin", "pdal.exe"),
                 os.path.join(prefix, "bin", "pdal")):
        if os.path.exists(path):
            return os.path.normpath(path)
    return shutil.which("pdal")


def class_names():
    """Названия классов ASPRS (LAS 1.4, таблица 17)."""
    return {0: tr("Не классифицировано"), 1: tr("Без класса"),
            2: tr("Земля"), 3: tr("Низкая растительность"),
            4: tr("Средняя растительность"),
            5: tr("Высокая растительность"), 6: tr("Здания"),
            7: tr("Низкий шум"), 8: tr("Ключевые точки"), 9: tr("Вода"),
            10: tr("Железная дорога"), 11: tr("Дорожное покрытие"),
            12: tr("Перекрытие"), 13: tr("Провода, защита"),
            14: tr("Провода"), 15: tr("Опоры ЛЭП"),
            16: tr("Провода, соединители"), 17: tr("Мосты"),
            18: tr("Высокий шум")}


def is_cloud(layer):
    return isinstance(layer, QgsPointCloudLayer)


def cloud_ids(layer_ids):
    """Номера облаков точек среди слоёв проекта."""
    project = QgsProject.instance()
    return [i for i in layer_ids if is_cloud(project.mapLayer(i))]


def _fingerprint(path):
    stat = os.stat(path)
    text = "{}|{}|{}".format(os.path.abspath(path), stat.st_size,
                             int(stat.st_mtime))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _parse(path, center, zfactor, mode, zrange, classes):
    """Рабочий поток: файл клетки от PDAL в смещения и цвета."""
    try:
        with open(path, "rb") as handle:
            data = handle.read()
    finally:
        try:
            os.remove(path)
        except OSError:
            journal.note("pointcloud: cell file stays {}".format(path))
    points = core.read_las(data)
    seen = {int(c) for c in np.unique(points.cls)}
    has_rgb = points.rgb is not None
    points = core.keep_classes(points, classes)
    count = len(points.x)
    if not count:
        return 0, None, None, None, seen, has_rgb
    colors = core.colors(points, mode, zrange)
    offsets, heights = core.vertices(points, center, zfactor)
    return count, offsets, heights, colors, seen, has_rgb


def _statistic(name):
    """Номер статистики QgsStatisticalSummary в Qt 5 и Qt 6."""
    from qgis.core import QgsStatisticalSummary
    scoped = getattr(QgsStatisticalSummary, "Statistic", None)
    return getattr(scoped, name, None) if scoped is not None \
        else getattr(QgsStatisticalSummary, name)


def z_range(layer):
    """Отметки низа и верха облака. QGIS 4 отдаёт их индексом, у QGIS 3
    провайдер индекса в Python не отдаёт - статистика метаданных."""
    provider = layer.dataProvider()
    index = getattr(provider, "index", None)
    found = index() if index is not None else None
    if found is not None and hasattr(found, "zMin") and found.isValid():
        return float(found.zMin()), float(found.zMax())
    statistic = getattr(provider, "metadataStatistic", None)
    if statistic is not None:
        try:
            return (float(statistic("Z", _statistic("Min"))),
                    float(statistic("Z", _statistic("Max"))))
        except (TypeError, ValueError) as error:
            journal.note("pointcloud z range: {}".format(error))
    return 0.0, 0.0


class _Entry:
    """Облако на глобусе."""

    def __init__(self, layer):
        self.layer_id = layer.id()
        self.name = layer.name()
        self.path = layer.source().split("|")[0]
        self.copc = None  # файл COPC для PDAL
        self.cloud = None
        crs = layer.crs()
        self.srs = crs.toWkt()
        self.zfactor = core.vertical_factor(crs.toProj())
        self.transform = QgsCoordinateTransform(
            crs, QgsCoordinateReferenceSystem("EPSG:4326"),
            QgsProject.instance())
        self.version = 0
        self.scale = None
        self.mode = "rgb"
        self.classes = None
        self.size = core.POINT_SIZE
        self.seen = set()  # классы, встреченные в пришедших клетках
        self.has_rgb = None  # есть ли цвет RGB в файле, None - неизвестно
        self.layer = None  # слой QGIS файла COPC для опроса
        self.reset()

    def reset(self):
        self.ready = {}  # клетка - точек, клетка в видеокарте
        self.arrived = {}  # клетка - точек, ждёт видеокарты
        self.running = set()
        self.infos = {}

    def to_geo(self, xs, ys):
        lons, lats = [], []
        for x, y in zip(xs, ys):
            p = self.transform.transform(QgsPointXY(float(x), float(y)))
            lons.append(p.x())
            lats.append(p.y())
        return lons, lats

    def info(self, cell):
        found = self.infos.get(cell)
        if found is None:
            found = self.infos[cell] = core.cell_info(
                self.cloud, cell, self.to_geo, self.zfactor, self.scale)
        return found


class PointCloudManager(QObject):
    """Облака точек окна глобуса."""

    def __init__(self, window):
        super().__init__(window)
        self.globe = window
        self.view = window.view
        self.entries = {}  # номер слоя - _Entry
        self.processes = {}  # QProcess - (номер, версия, клетка, файл)
        self.jobs = []  # (будущее, номер, версия, клетка, место)
        self.program = pdal_program()
        self.fetched = 0  # запросов клеток к PDAL за время окна
        self.size = core.POINT_SIZE
        self.view.pointclouds.size = self.size

    # Слои.

    def sync(self, layer_ids):
        """Отмеченные слои проекта: облака из них - на глобус."""
        wanted = set(cloud_ids(layer_ids))
        for layer_id in list(self.entries):
            if layer_id not in wanted:
                self._remove(layer_id)
        project = QgsProject.instance()
        for layer_id in wanted:
            if layer_id not in self.entries:
                self._add(project.mapLayer(layer_id))
        self.view.pointclouds.chooser = self._choose if self.entries \
            else None
        self.globe._pointclouds_seen()
        self.view.update()

    def _add(self, layer):
        entry = _Entry(layer)
        self.entries[entry.layer_id] = entry
        self._style(entry, read_pointclouds().get(entry.layer_id))
        if self.program is None:
            self._say(tr("Облако «{name}» не показано: в составе QGIS нет "
                         "программы PDAL.", name=entry.name))
            return
        if entry.path.lower().endswith(".copc.laz"):
            self._opened(entry, entry.path)
        else:
            self._convert(entry)

    def _remove(self, layer_id):
        self.entries.pop(layer_id, None)
        for process, info in list(self.processes.items()):
            if info[0] == layer_id:
                process.kill()
        self.view.pointclouds.drop(lambda key: key[0] == layer_id)

    def close(self):
        for process in list(self.processes):
            process.kill()
        self.processes.clear()
        self.entries.clear()
        self.view.pointclouds.chooser = None

    def _style(self, entry, data):
        """Настройки слоя; True - точки нужно прочитать заново."""
        style = core.style(data)
        entry.size = style["size"]
        self.view.pointclouds.sizes[entry.layer_id] = entry.size
        changed = (style["mode"], style["classes"]) \
            != (entry.mode, entry.classes)
        entry.mode = style["mode"]
        entry.classes = None if style["classes"] is None \
            else set(style["classes"])
        return changed

    def set_style(self, layer_id, data):
        """Цвет, размер или классы облака из меню слоя."""
        entry = self.entries.get(layer_id)
        if entry is None:
            return
        if self._style(entry, data):
            self.restyle(layer_id)
        self.view.update()

    def restyle(self, layer_id):
        """Цвет или классы сменились: клетки заново."""
        entry = self.entries.get(layer_id)
        if entry is None:
            return
        entry.version += 1
        entry.reset()
        self.view.pointclouds.drop(lambda key: key[0] == layer_id)
        self.view.update()

    # Перевод LAS и LAZ в COPC.

    def _convert(self, entry):
        try:
            stamp = _fingerprint(entry.path)
        except OSError as error:
            self._say(tr("Облако «{name}» не прочитано: {error}",
                         name=entry.name, error=error))
            return
        out = os.path.join(cache_folder(), stamp + ".copc.laz")
        if os.path.exists(out) and os.path.getsize(out) > 0:
            self._opened(entry, out)
            return
        part = os.path.join(cache_folder(), stamp + ".part.laz")
        spec = os.path.join(cache_folder(), stamp + ".json")
        with open(spec, "w", encoding="utf-8") as handle:
            handle.write(core.convert_pipeline(
                entry.path.replace("\\", "/"), part.replace("\\", "/")))
        self._say(tr("Облако «{name}» переводится в COPC, это делается "
                     "один раз.", name=entry.name))
        self._run(entry, "convert", (out, part, spec), ["pipeline", spec])

    def _converted(self, entry, ok, files):
        out, part, spec = files
        for path in (spec,):
            try:
                os.remove(path)
            except OSError:
                journal.note("pointcloud: {} stays".format(path))
        if not ok or not os.path.exists(part):
            self._say(tr("Облако «{name}» не переведено в COPC, подробности "
                         "в журнале работы.", name=entry.name))
            return
        os.replace(part, out)
        self._opened(entry, out)

    def _opened(self, entry, copc):
        """Охват и высоты облака по индексу COPC."""
        layer = QgsPointCloudLayer(copc, entry.name, "copc")
        if not layer.isValid():
            self._say(tr("Облако «{name}» не открылось.", name=entry.name))
            return
        entry.layer = layer
        extent = layer.extent()
        low, high = z_range(layer)
        entry.copc = copc
        entry.cloud = core.Cloud(extent.xMinimum(), extent.yMinimum(),
                                 extent.xMaximum(), extent.yMaximum(),
                                 float(low), float(high),
                                 max(int(layer.pointCount()), 1))
        if layer.crs().isValid():
            entry.srs = layer.crs().toWkt()
        self.view.update()

    # Клетки.

    def _choose(self, camera):
        """Клетки кадра всех облаков, ставит вид в каждом кадре."""
        keys = []
        live = [e for e in self.entries.values() if e.cloud is not None]
        if not live:
            return keys
        frame = lod._Frame(camera, core.POINT_PIXELS)
        budget = core.POINT_BUDGET // len(live)
        blocks = self.view.pointclouds.blocks
        scale = self.view.store.scale
        # Масштаб рельефа ставит шейдер, точки не читаются заново.
        self.view.pointclouds.scale = scale
        for entry in live:
            if entry.scale != scale:
                entry.infos.clear()
                entry.scale = scale
            for cell, count in list(entry.arrived.items()):
                if not count or (entry.layer_id, entry.version, cell) \
                        in blocks:
                    entry.ready[cell] = entry.arrived.pop(cell)
            sel = core.select(entry.cloud, frame, entry.ready, entry.info,
                              budget=budget)
            keys.extend((entry.layer_id, entry.version, cell)
                        for cell in sel.draw)
            for _, cell in sel.want:
                if len(self.processes) >= PARALLEL:
                    break
                if cell in entry.running or cell in entry.arrived:
                    continue
                self._fetch(entry, cell)
        return keys

    def _fetch(self, entry, cell):
        level, ix, iy = cell
        stem = "{}_{}_{}_{}_{}_{}".format(
            _fingerprint(entry.copc), entry.version, level, ix, iy,
            int(time.monotonic() * 1000) % 100000)
        out = os.path.join(cache_folder(), stem + ".las")
        spec = os.path.join(cache_folder(), stem + ".json")
        with open(spec, "w", encoding="utf-8") as handle:
            handle.write(core.pipeline(entry.copc.replace("\\", "/"),
                                       entry.cloud, cell,
                                       out.replace("\\", "/")))
        entry.running.add(cell)
        self.fetched += 1
        self._run(entry, cell, (out, spec), ["pipeline", spec])

    def _run(self, entry, what, files, arguments):
        process = QProcess(self)
        self.processes[process] = (entry.layer_id, entry.version, what,
                                   files)
        process.finished.connect(
            lambda code, status, p=process: self._finished(p, code))
        process.start(self.program, arguments)
        self.view.data_pending += 1

    def _finished(self, process, code):
        info = self.processes.pop(process, None)
        error = bytes(process.readAllStandardError()).decode(
            "utf-8", "replace").strip()
        process.deleteLater()
        if info is None:
            return
        self.view.data_pending = max(0, self.view.data_pending - 1)
        layer_id, version, what, files = info
        entry = self.entries.get(layer_id)
        ok = code == 0
        if not ok:
            journal.note("pointcloud pdal {}: {}".format(code, error[-400:]))
        if what == "convert":
            if entry is not None:
                self._converted(entry, ok, files)
            return
        out, spec = files
        try:
            os.remove(spec)
        except OSError:
            journal.note("pointcloud: {} stays".format(spec))
        if entry is None or entry.version != version:
            self._discard(out)
            return
        if not ok or not os.path.exists(out):
            # Клетка без ответа - пустая, иначе её просили бы снова.
            self._discard(out)
            entry.running.discard(what)
            entry.arrived[what] = 0
            return
        center, up = core.anchor(entry.cloud, what, entry.to_geo)
        info = entry.info(what)
        zf = entry.zfactor
        cloud = entry.cloud
        # Место клетки для вида: центр, нормаль, низ облака и отметки
        # в метрах, горизонтальный радиус - половина диагонали.
        place = (center, up, cloud.zmin * zf,
                 (cloud.zmin * zf, cloud.zmax * zf),
                 info.texel * core.CELL_GRID * 0.75)
        zrange = (cloud.zmin, cloud.zmax)
        job = executor("pointcloud", WORKERS).submit(
            _parse, out, center, zf, entry.mode, zrange, entry.classes)
        self.jobs.append((job, layer_id, version, what, place))
        self.view.data_pending += 1
        QTimer.singleShot(POLL, self._poll)

    def _discard(self, path):
        try:
            if os.path.exists(path):
                os.remove(path)
        except OSError:
            journal.note("pointcloud: {} stays".format(path))

    def _poll(self):
        waiting = []
        for item in self.jobs:
            job, layer_id, version, cell, place = item
            if not job.done():
                waiting.append(item)
                continue
            self.view.data_pending = max(0, self.view.data_pending - 1)
            entry = self.entries.get(layer_id)
            if entry is None or entry.version != version:
                continue
            entry.running.discard(cell)
            try:
                count, offsets, heights, colors, seen, has_rgb = \
                    job.result()
            except (OSError, ValueError) as error:
                journal.note("pointcloud cell {}: {}".format(cell, error))
                entry.arrived[cell] = 0
                continue
            entry.arrived[cell] = count
            if not seen <= entry.seen or entry.has_rgb is None:
                entry.seen |= seen
                entry.has_rgb = bool(entry.has_rgb) or has_rgb
                self.globe._pointclouds_seen()
            if count:
                self.view.pointclouds.add((layer_id, version, cell),
                                          offsets, heights, colors, place)
        self.jobs = waiting
        if waiting:
            QTimer.singleShot(POLL, self._poll)
        self.view.update()

    # Опрос щелчком.

    def identify(self, camera, px, py, pixels):
        """Точки облаков под пикселем (px, py): [(название облака,
        [(подпись, значение)])]. Точка ищется вдоль луча взгляда между
        низом и верхом облака, ближайшая к курсору на экране."""
        origin, direction = camera.ray(px, py)
        found = []
        for entry in self.entries.values():
            if entry.layer is None or entry.cloud is None:
                continue
            try:
                values = self._pick(entry, camera, origin, direction, px,
                                    py, pixels)
            except (RuntimeError, ValueError, KeyError) as error:
                journal.note("pointcloud identify: {}".format(error))
                continue
            if values:
                found.append((entry.name, values))
        return found

    def _reverse(self, entry, lon, lat):
        """Долгота и широта в систему файла."""
        direction = getattr(getattr(Qgis, "TransformDirection", None),
                            "Reverse", None)
        if direction is None:
            direction = QgsCoordinateTransform.ReverseTransform
        p = entry.transform.transform(QgsPointXY(lon, lat), direction)
        return p.x(), p.y()

    def _pick(self, entry, camera, origin, direction, px, py, pixels):
        cloud = entry.cloud
        scale = self.view.store.scale
        low, high = core.display(np.array([cloud.zmin, cloud.zmax]), cloud,
                                 entry.zfactor, scale)
        span = core.ray_span(origin, direction, float(low), float(high))
        if span is None:
            return None
        rect = None
        focal = camera.height / (2.0 * np.tan(np.radians(camera.fov_y) / 2.0))
        for end in span:
            lat, lon, _ = (float(v) for v in ecef_to_geodetic(end))
            reach = pixels * 2.0 * float(np.linalg.norm(end - origin)) / focal
            dlat = reach / 111320.0
            dlon = dlat / max(np.cos(np.radians(lat)), 0.01)
            for a, b in ((lat - dlat, lon - dlon), (lat + dlat, lon + dlon),
                         (lat - dlat, lon + dlon), (lat + dlat, lon - dlon)):
                x, y = self._reverse(entry, b, a)
                box = QgsRectangle(x, y, x, y)
                if rect is None:
                    rect = box
                else:
                    rect.combineExtentWith(box)
        provider = entry.layer.dataProvider()
        rows = provider.identify(core.spacing(cloud),
                                 QgsGeometry.fromRect(rect),
                                 QgsDoubleRange(), core.PICK_LIMIT)
        if entry.classes is not None:
            rows = [r for r in rows
                    if int(r.get("Classification", 0)) in entry.classes]
        if not rows:
            return None
        lats, lons, heights = [], [], []
        for row in rows:
            p = entry.transform.transform(QgsPointXY(float(row["X"]),
                                                     float(row["Y"])))
            lons.append(p.x())
            lats.append(p.y())
            heights.append(float(row["Z"]))
        shown = core.display(np.array(heights), cloud, entry.zfactor, scale)
        xyz = geodetic_to_ecef(np.array(lats), np.array(lons), shown)
        xyz = np.stack(xyz, axis=-1) if isinstance(xyz, tuple) else xyz
        screen, front = camera.project(xyz)
        index = core.pick(screen, front,
                          np.linalg.norm(xyz - origin, axis=1), px, py,
                          max(pixels, core.PICK_PIXELS))
        if index is None:
            return None
        row = rows[index]
        names = class_names()
        code = int(row.get("Classification", 0))
        values = [(tr("Класс"), names.get(code, tr("Класс {code}",
                                                   code=code))),
                  (tr("Отметка"), tr("{value} м", value="{:.2f}".format(
                      heights[index] * entry.zfactor))),
                  (tr("Широта, долгота"), "{:.6f}, {:.6f}".format(
                      lats[index], lons[index]))]
        if "Intensity" in row:
            values.append((tr("Интенсивность"), str(row["Intensity"])))
        if "ReturnNumber" in row:
            values.append((tr("Отражение"), tr(
                "{number} из {count}", number=row["ReturnNumber"],
                count=row.get("NumberOfReturns", "?"))))
        if all(k in row for k in ("Red", "Green", "Blue")):
            rgb = [int(row[k]) for k in ("Red", "Green", "Blue")]
            shift = 8 if max(rgb) > 255 else 0
            values.append((tr("Цвет"), "{}, {}, {}".format(
                *(v >> shift for v in rgb))))
        return values

    def _say(self, text):
        self.globe.message = (text, time.monotonic())
        self.globe._show_state()
