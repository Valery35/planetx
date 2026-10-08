# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Снимки Sentinel-2»: сцены тайла в точке и слой проекта.

Пункт «Снимок Sentinel-2 здесь…» меню на глобусе. Расчёт - core/
sentinel.py. Каталог GeoParquet читает драйвер Parquet GDAL из QGIS
в рабочем потоке: открытие годового файла 4.7 ГБ по сети - около 10 с,
отбор тайла - 3-5 с, главный поток всё это время свободен. Превью
сцены - JPEG через QgsNetworkAccessManager. Выбранная сцена ложится
слоем проекта по ссылке /vsicurl/ на COG true color в группу
«Sentinel-2» вверху дерева и отмечается на глобусе. Файл сцены тоже
открывается сначала в рабочем потоке: заголовок COG попадает в кэш
GDAL, и слой создаётся в главном потоке без ожидания сети.

Перед первым вызовом в потоке GDAL и OGR зовутся в главном потоке
(inset.warm): FutureWarning osgeo в рабочем потоке роняет QGIS, см.
AGENTS.md.
"""
import datetime
from concurrent.futures import ThreadPoolExecutor

from qgis.core import QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import Qt, QTimer
from qgis.PyQt.QtGui import QPixmap
from qgis.PyQt.QtWidgets import (QComboBox, QDialog, QDialogButtonBox,
                                 QHBoxLayout, QLabel, QListWidget,
                                 QListWidgetItem, QPushButton, QSpinBox,
                                 QVBoxLayout)

from ..core import sentinel
from ..i18n import tr
from ..net.loader import USER_AGENT
from ..net.overlay import fetch_bytes
from ..qt_compat import enum
from .inset import warm as warm_gdal

POLL = 200  # мс между проверками задания рабочего потока
CLOUD_DEFAULT = 30  # %, облачность по умолчанию, выбор помощника
PREVIEW = 300  # пикселей стороны превью
FILES_AT_ONCE = 4  # файлов каталога читается сразу
SCENE_ROLE = enum(Qt, "ItemDataRole", "UserRole")


def warm():
    """Первые вызовы GDAL и OGR в главном потоке, см. описание
    модуля."""
    from osgeo import ogr
    warm_gdal()
    ogr.GetDriverByName("Memory").CreateDataSource("warm")


def read_scenes(files, tile):
    """Сцены тайла из файлов каталога, файлы - параллельно по
    FILES_AT_ONCE. Рабочие потоки. Возвращает (сцены, открыто файлов,
    ошибка GDAL годового файла или пустая строка)."""
    with ThreadPoolExecutor(max_workers=FILES_AT_ONCE) as pool:
        parts = list(pool.map(lambda url: read_file(url, tile), files))
    return ([s for part, _, _ in parts for s in part],
            sum(opened for _, opened, _ in parts), parts[0][2])


def read_file(url, tile):
    """Сцены тайла из одного файла каталога. Файла хвоста может не
    быть - он пропускается без сообщения в журнал."""
    from osgeo import gdal, ogr
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_USERAGENT", USER_AGENT)
    gdal.SetThreadLocalConfigOption("GDAL_DISABLE_READDIR_ON_OPEN",
                                    "EMPTY_DIR")
    out = []
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    gdal.ErrorReset()
    try:
        try:
            # В QGIS 4 у GDAL включены исключения, у 3.36 - нет.
            ds = ogr.Open("/vsicurl/" + url)
        except RuntimeError:
            ds = None
        if ds is None:
            return out, 0, gdal.GetLastErrorMsg()
        layer = ds.GetLayer(0)
        defn = layer.GetLayerDefn()
        names = [defn.GetFieldDefn(i).GetName()
                 for i in range(defn.GetFieldCount())]
        keep = set(sentinel.FIELDS) | {"_tile"}
        layer.SetIgnoredFields([n for n in names if n not in keep])
        layer.SetAttributeFilter(sentinel.tile_filter(tile))
        for feature in layer:
            row = {n: feature.GetField(n) for n in sentinel.FIELDS
                   if n in names}
            s = sentinel.scene(row, tile)
            if s is not None:
                out.append(s)
        ds = None
    finally:
        gdal.PopErrorHandler()
    return out, 1, ""


def open_scene(url):
    """Заголовок COG сцены в кэш GDAL. Рабочий поток. True - открылся."""
    from osgeo import gdal
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_USERAGENT", USER_AGENT)
    gdal.SetThreadLocalConfigOption("GDAL_DISABLE_READDIR_ON_OPEN",
                                    "EMPTY_DIR")
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            ds = gdal.Open("/vsicurl/" + url)
        except RuntimeError:
            ds = None
        ok = ds is not None and ds.RasterCount >= 3
        ds = None
    finally:
        gdal.PopErrorHandler()
    return ok


class SentinelDialog(QDialog):
    """Окно сцен Sentinel-2 одной точки. window - окно глобуса."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setWindowTitle(tr("Снимки Sentinel-2"))
        self.setModal(False)
        self.tile = None
        self.pool = None
        self.job = None
        self.job_kind = ""
        self.scenes = []
        self.preview_reply = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)

        self.where = QLabel(self)
        self.year = QComboBox(self)
        self.year.setToolTip(tr(
            "Год съёмки. Каталог по году - один файл, его чтение по сети "
            "идёт 10-20 секунд."))
        self.cloud = QSpinBox(self)
        self.cloud.setRange(0, 100)
        self.cloud.setSuffix(" %")
        self.cloud.setValue(CLOUD_DEFAULT)
        self.cloud.setToolTip(tr(
            "Наибольшая облачность сцены по оценке ESA. Меньше - меньше "
            "сцен в списке и чище снимки."))
        self.cloud.valueChanged.connect(self._fill)
        find = QPushButton(tr("Найти"), self)
        find.clicked.connect(lambda _=False: self.search())
        row = QHBoxLayout()
        row.addWidget(QLabel(tr("Год"), self))
        row.addWidget(self.year)
        row.addWidget(QLabel(tr("Облачность до"), self))
        row.addWidget(self.cloud)
        row.addWidget(find)
        row.addStretch(1)
        self.list = QListWidget(self)
        self.list.currentItemChanged.connect(self._chosen)
        self.list.itemDoubleClicked.connect(lambda item: self.add())
        self.preview = QLabel(self)
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setAlignment(enum(Qt, "AlignmentFlag", "AlignCenter"))
        middle = QHBoxLayout()
        middle.addWidget(self.list, 1)
        middle.addWidget(self.preview)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        credit = QLabel(tr(
            "Снимки Copernicus Sentinel-2 (ESA), файлы Element 84 на AWS, "
            "каталог s2-stac-geoparquet Taylor Geospatial."), self)
        credit.setWordWrap(True)
        self.add_button = QPushButton(tr("В проект QGIS"), self)
        self.add_button.setToolTip(tr(
            "Сцена в естественных цветах, 10 м, ложится слоем проекта по "
            "ссылке на файл в сети в группу «Sentinel-2». Слой виден на карте "
            "и на глобусе, данные загружаются при показе."))
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(lambda _=False: self.add())
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        buttons.addButton(self.add_button,
                          enum(QDialogButtonBox, "ButtonRole",
                               "ActionRole"))
        layout = QVBoxLayout(self)
        layout.addWidget(self.where)
        layout.addLayout(row)
        layout.addLayout(middle, 1)
        layout.addWidget(self.status)
        layout.addWidget(credit)
        layout.addWidget(buttons)

    def show_point(self, lat, lon):
        """Новая точка: тайл, годы и поиск за последний год."""
        tile = sentinel.tile_of(lat, lon)
        self.tile = tile
        now = datetime.datetime.now(datetime.timezone.utc)
        self.year.blockSignals(True)
        self.year.clear()
        for year in range(now.year, sentinel.FIRST_YEAR - 1, -1):
            self.year.addItem(str(year), year)
        self.year.blockSignals(False)
        self.where.setText(tr("Тайл {tile}, точка {lat}, {lon}",
                              tile=tile or "-",
                              lat="{:.5f}".format(lat),
                              lon="{:.5f}".format(lon)))
        self.scenes = []
        self._fill()
        if tile is None:
            self.status.setText(tr("Вне зон UTM снимков Sentinel-2 нет."))
            return
        self.search()

    def search(self):
        if self.tile is None:
            return
        if self.job is not None and not self.job.done():
            self.status.setText(tr("Каталог ещё читается."))
            return
        now = datetime.datetime.now(datetime.timezone.utc)
        year = self.year.currentData() or now.year
        files = sentinel.year_files(year, now.year, now.month)
        warm()
        self._start("scenes", read_scenes, files, self.tile)
        self.status.setText(tr("Чтение каталога сцен {year} года…",
                               year=str(year)))

    def _start(self, kind, func, *args):
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=1)
        self.job_kind = kind
        self.job = self.pool.submit(func, *args)
        self.timer.start()

    def _poll(self):
        job = self.job
        if job is None or not job.done():
            return
        self.timer.stop()
        self.job = None
        try:
            value = job.result()
        except (RuntimeError, ValueError, OSError) as error:
            self.status.setText(tr("Каталог не прочитан: {error}",
                                   error=str(error)))
            return
        if self.job_kind == "scenes":
            scenes, opened, error = value
            self.scenes = scenes
            self._fill()
            if not opened and "arrow" in error.lower():
                # Arrow GDAL 3.8 из QGIS 3.36 файлы каталога не читает,
                # проверено 9 октября 2026 года, GDAL 3.13 читает.
                from osgeo import gdal
                self.status.setText(tr(
                    "GDAL {version} этого QGIS не читает файлы каталога, "
                    "они читаются в QGIS 4.", version=gdal.__version__))
            elif not opened:
                self.status.setText(tr("Каталог не ответил. {error}",
                                       error=error))
        else:
            self._added(*value)

    def _fill(self):
        self.list.clear()
        shown = sentinel.choose(self.scenes, self.cloud.value())
        for s in shown:
            item = QListWidgetItem(tr("{when} UTC, облачность {cloud} %",
                                      when=s.when,
                                      cloud="{:.0f}".format(s.cloud)))
            item.setData(SCENE_ROLE, s)
            self.list.addItem(item)
        if self.scenes:
            self.status.setText(tr(
                "Сцен за год {total}, не облачнее {cloud} % - {count}.",
                total=str(len(self.scenes)), cloud=str(self.cloud.value()),
                count=str(len(shown))))
        if shown:
            self.list.setCurrentRow(0)
        else:
            self.preview.clear()
            self.add_button.setEnabled(False)

    def _chosen(self, item, previous):
        s = item.data(SCENE_ROLE) if item is not None else None
        self.add_button.setEnabled(s is not None)
        self.preview.clear()
        if self.preview_reply is not None:
            reply, self.preview_reply = self.preview_reply, None
            reply.abort()
        if s is None or not s.thumbnail:
            return
        self.preview_reply = fetch_bytes(
            s.thumbnail, lambda data, error, s=s: self._preview(s, data))

    def _preview(self, s, data):
        self.preview_reply = None
        item = self.list.currentItem()
        if item is None or item.data(SCENE_ROLE) != s or not data:
            return
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.preview.setPixmap(pixmap.scaled(
                PREVIEW, PREVIEW,
                enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
                enum(Qt, "TransformationMode", "SmoothTransformation")))

    def add(self):
        """Выбранная сцена - слоем проекта, файл открывается сначала
        в рабочем потоке."""
        item = self.list.currentItem()
        s = item.data(SCENE_ROLE) if item is not None else None
        if s is None or (self.job is not None and not self.job.done()):
            return
        warm()
        self._start("layer", lambda s=s: (s, open_scene(s.visual)))
        self.status.setText(tr("Открытие файла сцены…"))

    def _added(self, s, ok):
        if not ok:
            self.status.setText(tr("Файл сцены не открылся: {url}",
                                   url=s.visual))
            return
        layer = QgsRasterLayer("/vsicurl/" + s.visual,
                               sentinel.layer_name(s), "gdal")
        if not layer.isValid():
            self.status.setText(tr("Файл сцены не открылся: {url}",
                                   url=s.visual))
            return
        # Край сцены вне снимка - нули true color, они прозрачны.
        provider = layer.dataProvider()
        for band in (1, 2, 3):
            provider.setNoDataValue(band, 0)
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group = root.findGroup("Sentinel-2")
        if group is None:
            group = root.insertGroup(0, "Sentinel-2")
        project.addMapLayer(layer, False)
        group.insertLayer(0, layer)
        self.window.set_layer_shown(layer.id(), True)
        self.status.setText(tr("Слой «{name}» в проекте.",
                               name=layer.name()))

    def closeEvent(self, event):
        self.timer.stop()
        if self.preview_reply is not None:
            reply, self.preview_reply = self.preview_reply, None
            reply.abort()
        if self.pool is not None:
            self.pool.shutdown(wait=False)
            self.pool = None
        self.job = None
        super().closeEvent(event)
