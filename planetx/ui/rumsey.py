# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Карты Рамсея» и сборка привязанной карты (core/rumsey.py).

Пункт «Исторические карты Рамсея…» меню на глобусе открывает список
карт у вида. Каталог берётся из planetx-terrain через зеркала
(TERRAIN_MIRRORS окна) или из локальной копии (base). Выбранная карта
собирается из кусков IIIF не больше MAX_SIDE пикселей, поле вне обрезки
становится прозрачным, привязка - gdal.Translate с опорными точками
и gdal.Warp способом Рамсея в рабочем потоке пула «rumsey». Итог -
GeoTIFF в профиле QGIS, PlanetX/rumsey/<номер>.tif, слой с годом карты
в группе «Карты Рамсея» вверху проекта.
"""
import json
import os
import time

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import (QObject, QPointF, Qt, QTimer, QUrl,
                              pyqtSignal)
from qgis.PyQt.QtGui import (QColor, QDesktopServices, QImage, QPainter,
                             QPolygonF)
from qgis.PyQt.QtWidgets import (QCheckBox, QDialog, QHBoxLayout, QLabel,
                                 QLineEdit, QPushButton, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout)

from .. import journal
from ..core import rumsey as core
from ..i18n import tr
from ..net.gdalnet import executor, thread_gdal
from ..net.overlay import fetch_bytes, fetch_mirror
from ..qt_compat import enum

PARALLEL = 4  # кусков IIIF одновременно
SORT_ROLE = 0x0101  # ключ сортировки строки по столбцу
POLL = 200  # мс между проверками привязки


def rumsey_folder():
    folder = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                          "rumsey")
    os.makedirs(folder, exist_ok=True)
    return folder


def georeference(png, tif, points, method):
    """Изображение png с альфой - GeoTIFF tif в EPSG:4326 по опорным
    точкам (x, y, долгота, широта) способом method. Рабочий поток."""
    gdal = thread_gdal()
    gdal.UseExceptions()
    gcps = [gdal.GCP(lon, lat, 0.0, x, y) for x, y, lon, lat in points]
    vrt = "/vsimem/planetx_rumsey_{}.vrt".format(os.path.basename(tif))
    source = gdal.Translate(vrt, png, format="VRT", GCPs=gcps,
                            outputSRS="EPSG:4326")
    options = core.warp_options(method, len(points))
    result = gdal.Warp(tif, source, format="GTiff", dstSRS="EPSG:4326",
                       resampleAlg="bilinear", srcAlpha=True, dstAlpha=True,
                       creationOptions=["COMPRESS=DEFLATE", "TILED=YES"],
                       **options)
    ok = result is not None
    result = None
    source = None
    gdal.Unlink(vrt)
    return ok


class RumseyLoader(QObject):
    """Каталог и сборка карт. done(путь, номер) - карта привязана,
    failed(текст), progress(текст)."""

    done = pyqtSignal(str, int)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)
    catalogue_ready = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.base = None  # своя папка каталога, file:// - для проверки
        self.catalogue = None
        self.cells = {}
        self.replies = {}
        self.job = None
        self.poll = QTimer(self)
        self.poll.setInterval(POLL)
        self.poll.timeout.connect(self._poll)

    def _fetch(self, path, done):
        if self.base:
            return fetch_bytes(self.base + path, lambda d, e: done(d, e))
        from .window import TERRAIN_MIRRORS
        return fetch_mirror(TERRAIN_MIRRORS, path,
                            lambda d, e, base: done(d, e))

    def want_catalogue(self):
        if self.catalogue is not None or "index" in self.replies:
            return
        self.replies["index"] = self._fetch(core.INDEX_PATH,
                                            self._index_done)

    def _index_done(self, data, error):
        self.replies.pop("index", None)
        if data is None:
            journal.note("rumsey index: {}".format(error))
            self.failed.emit(tr("Каталог карт Рамсея не загрузился, "
                                "проверьте сеть."))
            return
        self.catalogue = core.Catalogue.from_text(bytes(data).decode(
            "utf-8"))
        self.catalogue_ready.emit()

    # Сборка карты.

    def build(self, row):
        """Собрать карту строки row указателя."""
        if self.job is not None:
            return
        cat = self.catalogue
        number = int(cat.number[row])
        self.job = {"row": row, "number": number, "pieces": {},
                    "started": time.monotonic()}
        tif = os.path.join(rumsey_folder(), "{}.tif".format(number))
        if os.path.exists(tif):
            job, self.job = self.job, None
            self.done.emit(tif, job["row"])
            return
        cell = cat.cell[row]
        if cell in self.cells:
            self._have_cell(cell)
            return
        self.progress.emit(tr("Загрузка сведений о карте…"))
        self.replies["cell"] = self._fetch(
            core.CELL_PATH.format(cell=cell),
            lambda data, error, cell=cell: self._cell_done(cell, data,
                                                           error))

    def _cell_done(self, cell, data, error):
        self.replies.pop("cell", None)
        if self.job is None:
            return
        if data is None:
            self._fail("rumsey cell {}: {}".format(cell, error))
            return
        self.cells[cell] = json.loads(bytes(data).decode("utf-8"))
        self._have_cell(cell)

    def _have_cell(self, cell):
        record = self.cells[cell].get(str(self.job["number"]))
        if record is None:
            self._fail("rumsey: no record {}".format(self.job["number"]))
            return
        self.job["record"] = record
        self.job["service"] = core.image_url(record["i"])
        self.progress.emit(tr("Загрузка изображения карты…"))
        self.replies["info"] = fetch_bytes(self.job["service"] + "/info.json",
                                           self._info_done)

    def _info_done(self, data, error):
        self.replies.pop("info", None)
        if self.job is None:
            return
        try:
            info = json.loads(bytes(data).decode("utf-8")) if data else None
        except ValueError:
            info = None
        if not info:
            self._fail("rumsey info: {}".format(error))
            return
        factors = []
        for tile in info.get("tiles") or ():
            factors += tile.get("scaleFactors") or []
        factor, w, h, pieces = core.tile_plan(
            int(info["width"]), int(info["height"]), factors or [1])
        self.job.update(factor=factor, width=w, height=h, todo=list(pieces),
                        total=len(pieces))
        self.job["image"] = QImage(w, h, enum(QImage, "Format",
                                              "Format_ARGB32"))
        self.job["image"].fill(QColor(0, 0, 0, 0))
        self._pump()

    def _pump(self):
        job = self.job
        if job is None:
            return
        while job["todo"] and len(job["pieces"]) < PARALLEL:
            piece = job["todo"].pop(0)
            url = core.piece_url(job["service"], piece)
            job["pieces"][piece] = fetch_bytes(
                url, lambda data, error, piece=piece: self._piece_done(
                    piece, data, error))
        if not job["todo"] and not job["pieces"]:
            self._assemble()

    def _piece_done(self, piece, data, error):
        job = self.job
        if job is None or piece not in job["pieces"]:
            return
        job["pieces"].pop(piece)
        image = QImage.fromData(bytes(data)) if data else QImage()
        if image.isNull():
            self._fail("rumsey piece: {}".format(error))
            return
        painter = QPainter(job["image"])
        painter.drawImage(piece[4], piece[5], image)
        painter.end()
        done = job["total"] - len(job["todo"]) - len(job["pieces"])
        self.progress.emit(tr("Загрузка изображения карты: {done} из "
                              "{total}", done=done, total=job["total"]))
        self._pump()

    def _assemble(self):
        """Поле вне обрезки прозрачно, PNG и привязка в рабочем потоке."""
        job = self.job
        record = job["record"]
        factor = job["factor"]
        image = job["image"]
        if len(record.get("k") or ()) >= 3:
            mask = QImage(image.size(), enum(QImage, "Format",
                                             "Format_ARGB32"))
            mask.fill(QColor(0, 0, 0, 0))
            painter = QPainter(mask)
            painter.setRenderHint(enum(QPainter, "RenderHint",
                                       "Antialiasing"))
            painter.setPen(enum(Qt, "PenStyle", "NoPen"))
            painter.setBrush(QColor(0, 0, 0, 255))
            painter.drawPolygon(QPolygonF([QPointF(x / factor, y / factor)
                                           for x, y in record["k"]]))
            painter.end()
            painter = QPainter(image)
            painter.setCompositionMode(enum(
                QPainter, "CompositionMode",
                "CompositionMode_DestinationIn"))
            painter.drawImage(0, 0, mask)
            painter.end()
        folder = rumsey_folder()
        png = os.path.join(folder, "{}.png".format(job["number"]))
        tif = os.path.join(folder, "{}.tif".format(job["number"]))
        image.save(png, "PNG")
        job["image"] = None
        job["tif"] = tif
        self.progress.emit(tr("Привязка карты…"))
        job["future"] = executor("rumsey", 1).submit(
            georeference, png, tif,
            core.scaled_points(record["g"], factor), record.get("m", ""))
        self.poll.start()

    def _poll(self):
        job = self.job
        if job is None or "future" not in job:
            self.poll.stop()
            return
        future = job["future"]
        if not future.done():
            return
        self.poll.stop()
        try:
            ok = future.result()
        except (RuntimeError, ValueError, OSError) as error:
            ok = False
            journal.note("rumsey warp: {}".format(error))
        png = os.path.join(rumsey_folder(), "{}.png".format(job["number"]))
        if os.path.exists(png):
            os.remove(png)
        if not ok:
            self._fail("rumsey warp failed {}".format(job["number"]))
            return
        self.job = None
        journal.note("rumsey {} in {:.1f} s".format(
            job["number"], time.monotonic() - job["started"]))
        self.done.emit(job["tif"], job["row"])

    def _fail(self, note):
        journal.note(note)
        self.cancel()
        self.failed.emit(tr("Карта не собрана, подробности - в журнале "
                            "работы."))

    def cancel(self):
        job, self.job = self.job, None
        if job is not None:
            for reply in list(job.get("pieces", {}).values()):
                reply.abort()
        for key in ("cell", "info"):
            reply = self.replies.pop(key, None)
            if reply is not None:
                reply.abort()


class SortItem(QTreeWidgetItem):
    """Строка списка карт: сортировка по году и масштабу - числом,
    карта без года или масштаба - в конце."""

    def __lt__(self, other):
        column = self.treeWidget().sortColumn() if self.treeWidget() \
            else 0
        return self.data(column, SORT_ROLE) < other.data(column, SORT_ROLE)


class RumseyDialog(QDialog):
    """Список карт Рамсея у вида и загрузка выбранной в проект."""

    def __init__(self, window):
        super().__init__(window)
        self.globe = window
        self.loader = window.rumsey_loader
        self.setWindowTitle(tr("Карты Рамсея"))
        self.rows = []
        self.view = None
        self.place = QLabel(self)
        self.place.setWordWrap(True)
        self.filter = QLineEdit(self)
        self.filter.setPlaceholderText(tr("Год или название"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._fill)
        self.everywhere = QCheckBox(tr("По всему каталогу"), self)
        self.everywhere.setToolTip(tr(
            "Искать по названию и году среди всех карт коллекции, а не "
            "только у вида. Кнопка «Показать на глобусе» перелетает к "
            "выбранной карте."))
        self.everywhere.toggled.connect(self._fill)
        self.list = QTreeWidget(self)
        self.list.setHeaderLabels([tr("Год"), tr("Карта"), tr("Масштаб")])
        self.list.setRootIsDecorated(False)
        self.list.setColumnWidth(0, 60)
        self.list.setColumnWidth(1, 380)
        # Список - по годам, щелчок по заголовку меняет порядок. Просьба
        # автора от 11 октября 2026 года «отсортируй по датам».
        self.list.setSortingEnabled(True)
        self.list.sortByColumn(0, enum(Qt, "SortOrder", "AscendingOrder"))
        self.list.itemDoubleClicked.connect(lambda *a: self._load())
        self.list.currentItemChanged.connect(
            lambda *a: self._show_footprints())
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        note = QLabel(tr(
            "Карты коллекции Дэвида Рамсея, привязка - по его опорным "
            "точкам. Изображения - CC BY-NC-SA 3.0: только для "
            "некоммерческого использования, с указанием источника."), self)
        note.setWordWrap(True)
        self.load_button = QPushButton(tr("В проект QGIS"), self)
        self.load_button.setToolTip(tr(
            "Карта собирается из изображения коллекции, привязывается "
            "и ложится в группу «Карты Рамсея» с годом карты. Год ставит "
            "карту на шкалу времени."))
        self.load_button.clicked.connect(self._load)
        show = QPushButton(tr("Показать на глобусе"), self)
        show.setToolTip(tr("Перелёт к рамке выбранной карты."))
        show.clicked.connect(self._fly)
        page = QPushButton(tr("Страница карты"), self)
        page.setToolTip(tr("Страница карты на сайте коллекции в браузере."))
        page.clicked.connect(self._page)
        buttons = QHBoxLayout()
        buttons.addWidget(self.load_button)
        buttons.addWidget(show)
        buttons.addWidget(page)
        buttons.addStretch(1)
        layout = QVBoxLayout(self)
        layout.addWidget(self.place)
        filters = QHBoxLayout()
        filters.addWidget(self.filter, 1)
        filters.addWidget(self.everywhere)
        layout.addLayout(filters)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.status)
        layout.addLayout(buttons)
        layout.addWidget(note)
        self.resize(620, 520)
        self.loader.catalogue_ready.connect(self._fill)
        self.loader.progress.connect(self.status.setText)
        self.loader.failed.connect(self._failed)
        self.loader.done.connect(self._built)

    def show_view(self, lat, lon, box):
        self.view = (lat, lon, box)
        self.loader.want_catalogue()
        if self.loader.catalogue is None:
            self.status.setText(tr("Загрузка каталога карт…"))
        self._fill()

    def _fill(self, *args):
        cat = self.loader.catalogue
        self.list.setSortingEnabled(False)
        self.list.clear()
        if cat is None or self.view is None:
            return
        lat, lon, box = self.view
        text = self.filter.text().strip().lower()
        if self.everywhere.isChecked():
            self.rows = core.search(cat, text)
            text = ""
        else:
            self.rows = core.covering(cat, lat, lon, box)
        shown = 0
        for row in self.rows:
            year = cat.year[row]
            title = cat.title[row]
            line = "{} {}".format(year or "", title).lower()
            if text and text not in line:
                continue
            scale = cat.scale[row]
            item = SortItem(self.list, [
                core.year_text(year), title,
                "1:{:,}".format(scale).replace(",", " ") if scale else ""])
            item.setData(0, enum(Qt, "ItemDataRole", "UserRole"), row)
            missing = 1 << 40
            item.setData(0, SORT_ROLE, year if year is not None
                         else missing)
            item.setData(1, SORT_ROLE, title.lower())
            item.setData(2, SORT_ROLE, scale if scale else missing)
            item.setToolTip(1, title)
            shown += 1
        self.list.setSortingEnabled(True)
        self._show_footprints()
        self.place.setText(tr("Карт у вида: {count}, по годам. Щелчок "
                              "по заголовку столбца меняет порядок.",
                              count=shown))
        if self.loader.job is None:
            self.status.setText("")

    def _selected(self):
        item = self.list.currentItem()
        if item is None:
            return None
        return item.data(0, enum(Qt, "ItemDataRole", "UserRole"))

    def _load(self):
        row = self._selected()
        if row is None:
            return
        self.load_button.setEnabled(False)
        self.loader.build(row)

    def _shown_rows(self):
        role = enum(Qt, "ItemDataRole", "UserRole")
        return [self.list.topLevelItem(n).data(0, role)
                for n in range(self.list.topLevelItemCount())]

    def _show_footprints(self):
        """Рамки карт списка на глобусе, выбранная - ярче."""
        cat = self.loader.catalogue
        if cat is None or not self.isVisible():
            return
        rows = self._shown_rows()[:core.LIST_MAX]
        selected = self._selected()
        self.globe.set_rumsey_footprints(
            [tuple(cat.box[r]) for r in rows],
            None if selected is None else tuple(cat.box[selected]))

    def _fly(self):
        row = self._selected()
        if row is None:
            return
        box = self.loader.catalogue.box[row]
        self.globe.view.fly_pose(
            (box[1] + box[3]) / 2.0, (box[0] + box[2]) / 2.0,
            core.fly_distance(box), 0.0, 0.0)

    def _page(self):
        row = self._selected()
        if row is None:
            return
        cell = self.loader.cells.get(self.loader.catalogue.cell[row], {})
        record = cell.get(str(int(self.loader.catalogue.number[row])))
        url = record["u"] if record else "https://www.davidrumsey.com"
        QDesktopServices.openUrl(QUrl(url))

    def _failed(self, text):
        self.status.setText(text)
        self.load_button.setEnabled(True)

    def _built(self, path, row):
        self.load_button.setEnabled(True)
        cat = self.loader.catalogue
        self.globe.add_rumsey_map(path, cat.year[row], cat.title[row])
        self.status.setText(tr("Карта в проекте: {title}.",
                               title=cat.title[row]))

    def closeEvent(self, event):
        self.loader.cancel()
        self.globe.set_rumsey_footprints([], None)
        self.load_button.setEnabled(True)
        super().closeEvent(event)
