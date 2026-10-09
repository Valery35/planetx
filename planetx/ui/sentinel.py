# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Окно «Снимки Sentinel-2»: сцены участка, каналы и индексы в проект.

Участок - точка с квадратом стороной side или метка «Моих меток»
(многоугольник, путь - по рамке точек). Поиск - STAC API Earth Search
запросом через QgsNetworkAccessManager (net/overlay.post_json), страницы
по ссылке next. Облачность над участком считается по маске SCL каждой
сцены в рабочих потоках, по CLOUD_WORKERS сразу, список дополняется по
мере расчёта. Превью - участок в естественных цветах по обзорным
уровням COG. Выдача - сочетания каналов и индексы
(core/sentinel.py): обрезка по участку в GeoTIFF отражениями float32
или вся сцена ссылкой VRT на файлы в сети (только сочетания). Слои
ложатся в группу дня внутри группы «Sentinel-2» вверху дерева,
растяжение - по процентилям 2-98 снимка, индексы - шкалой цветов.

GDAL в рабочих потоках: перед первым вызовом он зовётся в главном
потоке (inset.warm), в потоке ошибки гасятся, параметры сети - свои
у потока. FutureWarning osgeo в рабочем потоке роняет QGIS, см.
AGENTS.md.
"""
import os
from concurrent.futures import ThreadPoolExecutor

import numpy as np
from qgis.core import (QgsColorRampShader, QgsContrastEnhancement,
                       QgsMultiBandColorRenderer, QgsProject, QgsRasterLayer,
                       QgsRasterShader, QgsSingleBandPseudoColorRenderer)
from qgis.PyQt.QtCore import QDate, Qt, QTimer
from qgis.PyQt.QtGui import QColor, QImage, QPixmap
from qgis.PyQt.QtWidgets import (QCheckBox, QComboBox, QDateEdit, QDialog,
                                 QDialogButtonBox, QDoubleSpinBox,
                                 QFileDialog, QGridLayout, QHBoxLayout,
                                 QLabel, QListWidget, QListWidgetItem,
                                 QPushButton, QSpinBox, QTreeWidget,
                                 QTreeWidgetItem, QVBoxLayout)

from ..core import sentinel as s2
from ..i18n import tr
from ..net.loader import USER_AGENT
from ..net.overlay import post_json
from ..qt_compat import enum
from .inset import warm as warm_gdal

POLL = 200  # мс между проверками заданий рабочих потоков
CLOUD_WORKERS = 4  # сцен, у которых маска облаков читается сразу
BAND_WORKERS = 4  # каналов сцены, читаемых сразу
PREVIEW = 256  # пикселей стороны превью участка
SIDE_DEFAULT = 3.0  # км, сторона участка точки
SCENE_CLOUD_DEFAULT = 80  # %, облачность сцены в поиске
AREA_CLOUD_DEFAULT = 10  # %, облачность над участком в списке
DEFAULT_PRODUCTS = ("natural", "infrared", "ndvi")
# Растяжение сочетания ссылкой без скачивания - отражение по каналам.
LINK_RANGE = {"natural": (0.0, 0.25)}
LINK_RANGE_OTHER = (0.0, 0.45)
SCENE_ROLE = enum(Qt, "ItemDataRole", "UserRole")
GROUP = "Sentinel-2"
STRETCH = enum(QgsContrastEnhancement, "ContrastEnhancementAlgorithm",
               "StretchToMinimumMaximum")


def titles():
    """Названия продуктов окна и слоёв."""
    return {"natural": tr("Естественные цвета (B4 B3 B2)"),
            "infrared": tr("Ложные цвета, ближний ИК (B8 B4 B3)"),
            "agriculture": tr("Сельское хозяйство (B11 B8 B2)"),
            "swir": tr("Коротковолновый ИК (B12 B8A B4)"),
            "geology": tr("Геология (B12 B11 B2)"),
            "urban": tr("Застройка (B12 B11 B4)"),
            "ndvi": tr("NDVI - растительность"),
            "ndwi": tr("NDWI - открытая вода"),
            "ndmi": tr("NDMI - влажность растительности"),
            "nbr": tr("NBR - гари"),
            "ndsi": tr("NDSI - снег")}


def warm():
    """Первые вызовы GDAL в главном потоке, см. описание модуля."""
    warm_gdal()


def _thread_gdal():
    """Параметры GDAL рабочего потока: заголовок, без списка папки."""
    from osgeo import gdal
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_USERAGENT", USER_AGENT)
    gdal.SetThreadLocalConfigOption("GDAL_DISABLE_READDIR_ON_OPEN",
                                    "EMPTY_DIR")
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_MULTIRANGE", "YES")
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_MAX_RETRY", "2")
    return gdal


def read_window(href, box, res=None, size=None, nearest=False, count=1):
    """Окно файла в сети по рамке box системы файла: шаг res или
    размер size (столбцы, строки). Рабочий поток. Массив или None."""
    gdal = _thread_gdal()
    options = {"format": "MEM", "outputBounds": box,
               "resampleAlg": "near" if nearest else "bilinear"}
    if size is not None:
        options["width"], options["height"] = size
    else:
        options["xRes"] = options["yRes"] = res
    gdal.PushErrorHandler("CPLQuietErrorHandler")
    try:
        try:
            ds = gdal.Warp("", "/vsicurl/" + href, **options)
        except RuntimeError:
            ds = None
        if ds is None:
            return None
        if count == 1:
            out = ds.GetRasterBand(1).ReadAsArray()
        else:
            out = ds.ReadAsArray()
        ds = None
    finally:
        gdal.PopErrorHandler()
    return out


def scene_cloud(scene, ring):
    """Облачность над участком по маске SCL: (номер сцены, облачность,
    доля с данными) или (номер, None, None), если маска не прочитана."""
    try:
        xy = s2.ring_utm(ring, scene.epsg)
    except ValueError:
        return scene.id, None, None
    box = s2.bounds(xy, 20.0)
    scl = read_window(scene.assets["scl"].href, box, 20.0, nearest=True)
    if scl is None:
        return scene.id, None, None
    cloud, valid = s2.cloud_share(scl, s2.mask(xy, box, 20.0))
    return scene.id, cloud, valid


def preview(scene, ring):
    """Участок в естественных цветах, не больше PREVIEW пикселей по
    стороне: массив (3, строки, столбцы) uint8 или None."""
    asset = scene.assets.get("visual")
    if asset is None:
        return None
    xy = s2.ring_utm(ring, scene.epsg)
    box = s2.bounds(xy, 10.0)
    width, height = box[2] - box[0], box[3] - box[1]
    scale = PREVIEW / max(width, height)
    size = (max(int(width * scale), 1), max(int(height * scale), 1))
    return read_window(asset.href, box, size=size, count=3)


def build(scene, ring, products, folder, clear_clouds):
    """Продукты сцены по участку в GeoTIFF: список (продукт, путь,
    пределы растяжения по каналам). Рабочий поток."""
    gdal = _thread_gdal()
    xy = s2.ring_utm(ring, scene.epsg)
    res = s2.step_for(xy)
    box = s2.bounds(xy, res)
    keys = s2.needed(products)
    if clear_clouds:
        keys = keys + ["scl"]
    with ThreadPoolExecutor(max_workers=BAND_WORKERS) as pool:
        raw = dict(zip(keys, pool.map(
            lambda k: read_window(scene.assets[k].href, box, res,
                                  nearest=(k == "scl")), keys)))
    missing = [k for k, v in raw.items() if v is None]
    if missing:
        raise OSError(", ".join(missing))
    inside = s2.mask(xy, box, res)
    if clear_clouds:
        inside &= ~np.isin(raw.pop("scl"), s2.SCL_CLOUDY + s2.SCL_EMPTY)
    bands = {k: s2.reflectance(v, scene.assets[k]) for k, v in raw.items()}
    for values in bands.values():
        values[~inside] = np.nan
    os.makedirs(folder, exist_ok=True)
    out = []
    for name in products:
        values = s2.product(name, bands)
        path = os.path.join(folder, s2.file_name(scene, name) + ".tif")
        _write(gdal, path, values, box, res, scene.epsg)
        if name in s2.COMPOSITES:
            ranges = [s2.stretch(band) for band in values]
        else:
            ranges = [s2.INDICES[name][1]]
        out.append((name, path, ranges))
    return out


def _write(gdal, path, values, box, res, epsg):
    """Массив (каналы, строки, столбцы) или (строки, столбцы) float32
    в GeoTIFF с рамкой box и шагом res, нет данных - NaN."""
    from osgeo import osr
    values = values if values.ndim == 3 else values[None]
    driver = gdal.GetDriverByName("GTiff")
    ds = driver.Create(path, values.shape[2], values.shape[1],
                       values.shape[0], gdal.GDT_Float32,
                       options=["COMPRESS=DEFLATE", "PREDICTOR=3",
                                "TILED=YES"])
    ds.SetGeoTransform((box[0], res, 0.0, box[3], 0.0, -res))
    srs = osr.SpatialReference()
    srs.ImportFromEPSG(int(epsg))
    ds.SetProjection(srs.ExportToWkt())
    for n, band in enumerate(values, start=1):
        target = ds.GetRasterBand(n)
        target.SetNoDataValue(float("nan"))
        target.WriteArray(band)
    ds.FlushCache()
    ds = None


def build_links(scene, products, folder):
    """Сочетания всей сцены ссылкой VRT на файлы в сети: список
    (продукт, путь, пределы растяжения в значениях файла)."""
    gdal = _thread_gdal()
    os.makedirs(folder, exist_ok=True)
    out = []
    for name in products:
        if name not in s2.COMPOSITES:
            continue
        keys = s2.COMPOSITES[name]
        path = os.path.join(folder, s2.file_name(scene, name) + ".vrt")
        gdal.PushErrorHandler("CPLQuietErrorHandler")
        try:
            try:
                ds = gdal.BuildVRT(path, ["/vsicurl/" + scene.assets[k].href
                                          for k in keys],
                                   separate=True, resolution="highest")
            except RuntimeError:
                ds = None
            if ds is None:
                raise OSError(name)
            ds = None
        finally:
            gdal.PopErrorHandler()
        lo, hi = LINK_RANGE.get(name, LINK_RANGE_OTHER)
        ranges = []
        for key in keys:
            asset = scene.assets[key]
            ranges.append(((lo - asset.offset) / asset.scale,
                           (hi - asset.offset) / asset.scale))
        out.append((name, path, ranges))
    return out


def style_composite(layer, ranges):
    """Сочетание трёх каналов с растяжением ranges."""
    provider = layer.dataProvider()
    renderer = QgsMultiBandColorRenderer(provider, 1, 2, 3)
    kind = provider.dataType(1)
    setters = (renderer.setRedContrastEnhancement,
               renderer.setGreenContrastEnhancement,
               renderer.setBlueContrastEnhancement)
    for setter, (lo, hi) in zip(setters, ranges):
        contrast = QgsContrastEnhancement(kind)
        contrast.setMinimumValue(lo)
        contrast.setMaximumValue(hi)
        contrast.setContrastEnhancementAlgorithm(STRETCH)
        setter(contrast)
    layer.setRenderer(renderer)


def style_index(layer, name):
    """Индекс шкалой цветов core.sentinel.INDICES."""
    _, (lo, hi), stops = s2.INDICES[name]
    ramp = QgsColorRampShader(lo, hi)
    ramp.setColorRampItemList([
        QgsColorRampShader.ColorRampItem(value, QColor(*rgb),
                                         "{:g}".format(value))
        for value, rgb in stops])
    shader = QgsRasterShader()
    shader.setRasterShaderFunction(ramp)
    renderer = QgsSingleBandPseudoColorRenderer(layer.dataProvider(), 1,
                                                shader)
    renderer.setClassificationMin(lo)
    renderer.setClassificationMax(hi)
    layer.setRenderer(renderer)


class SentinelDialog(QDialog):
    """Окно снимков Sentinel-2 участка. window - окно глобуса."""

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window = window
        self.setWindowTitle(tr("Снимки Sentinel-2"))
        self.setModal(False)
        self.point = None  # (широта, долгота) или None
        self.ring = None  # кольцо участка (широта, долгота)
        self.area_name = ""
        self.scenes = []
        self.clouds = {}  # номер сцены - (облачность, доля с данными)
        self.generation = 0
        self.reply = None
        self.preview_job = None
        self.build_job = None
        self.cloud_jobs = []
        self.pool = None
        self.timer = QTimer(self)
        self.timer.setInterval(POLL)
        self.timer.timeout.connect(self._poll)
        self._layout()

    def _layout(self):
        self.where = QLabel(self)
        self.where.setWordWrap(True)
        self.side = QDoubleSpinBox(self)
        self.side.setRange(0.2, 100.0)
        self.side.setDecimals(1)
        self.side.setSuffix(tr(" км"))
        self.side.setValue(SIDE_DEFAULT)
        self.side.setToolTip(tr(
            "Сторона квадрата участка вокруг точки. По участку считается "
            "облачность и обрезаются снимки. Больше участок - дольше "
            "загрузка каналов."))
        self.side_label = QLabel(tr("Сторона участка"), self)
        today = QDate.currentDate()
        self.start = QDateEdit(today.addYears(-1), self)
        self.end = QDateEdit(today, self)
        for edit in (self.start, self.end):
            edit.setCalendarPopup(True)
            edit.setDisplayFormat("yyyy-MM-dd")
        self.start.setToolTip(tr("Первый день съёмки в поиске."))
        self.end.setToolTip(tr("Последний день съёмки в поиске."))
        self.scene_cloud = QSpinBox(self)
        self.scene_cloud.setRange(0, 100)
        self.scene_cloud.setSuffix(" %")
        self.scene_cloud.setValue(SCENE_CLOUD_DEFAULT)
        self.scene_cloud.setToolTip(tr(
            "Наибольшая облачность всей сцены 110 × 110 км по оценке ESA. "
            "Это отсев до расчёта облачности над участком. Сцена с облаками "
            "бывает чистой над участком."))
        self.area_cloud = QSpinBox(self)
        self.area_cloud.setRange(0, 100)
        self.area_cloud.setSuffix(" %")
        self.area_cloud.setValue(AREA_CLOUD_DEFAULT)
        self.area_cloud.setToolTip(tr(
            "Наибольшая доля облаков и их теней над участком по маске "
            "классов сцены. Сцены облачнее в списке скрыты."))
        self.area_cloud.valueChanged.connect(self._filter)
        find = QPushButton(tr("Найти"), self)
        find.clicked.connect(lambda _=False: self.search())
        grid = QGridLayout()
        grid.addWidget(self.side_label, 0, 0)
        grid.addWidget(self.side, 0, 1)
        grid.addWidget(QLabel(tr("Съёмка с"), self), 1, 0)
        grid.addWidget(self.start, 1, 1)
        grid.addWidget(QLabel(tr("по"), self), 1, 2)
        grid.addWidget(self.end, 1, 3)
        grid.addWidget(QLabel(tr("Облачность сцены до"), self), 2, 0)
        grid.addWidget(self.scene_cloud, 2, 1)
        grid.addWidget(QLabel(tr("над участком до"), self), 2, 2)
        grid.addWidget(self.area_cloud, 2, 3)
        grid.addWidget(find, 2, 4)
        self.list = QTreeWidget(self)
        self.list.setRootIsDecorated(False)
        self.list.setHeaderLabels([tr("Дата, UTC"), tr("Над участком"),
                                   tr("Сцена"), tr("Солнце"), tr("Тайл")])
        self.list.currentItemChanged.connect(self._chosen)
        self.list.itemDoubleClicked.connect(lambda *a: self.add())
        self.preview = QLabel(self)
        self.preview.setFixedSize(PREVIEW, PREVIEW)
        self.preview.setAlignment(enum(Qt, "AlignmentFlag", "AlignCenter"))
        middle = QHBoxLayout()
        middle.addWidget(self.list, 1)
        middle.addWidget(self.preview)
        self.products = QListWidget(self)
        names = titles()
        for key in s2.PRODUCTS:
            item = QListWidgetItem(names[key])
            item.setData(SCENE_ROLE, key)
            item.setFlags(item.flags()
                          | enum(Qt, "ItemFlag", "ItemIsUserCheckable"))
            item.setCheckState(enum(Qt, "CheckState", "Checked")
                               if key in DEFAULT_PRODUCTS else
                               enum(Qt, "CheckState", "Unchecked"))
            self.products.addItem(item)
        self.products.setMaximumHeight(130)
        self.products.setToolTip(tr(
            "Сочетания каналов - картинка из трёх каналов отражения, "
            "индексы - нормированная разность двух каналов со шкалой "
            "цветов. Каждый отмеченный продукт ложится своим слоем."))
        self.clear = QCheckBox(tr("Облака и тени - пусто"), self)
        self.clear.setChecked(True)
        self.clear.setToolTip(tr(
            "Пиксели облаков, их теней и перистых облаков по маске "
            "классов сцены остаются пустыми, индексы по ним не "
            "считаются."))
        self.mode = QComboBox(self)
        self.mode.addItem(tr("Обрезка по участку, GeoTIFF"), "clip")
        self.mode.addItem(tr("Вся сцена по ссылке, без скачивания"), "link")
        self.mode.setToolTip(tr(
            "Обрезка загружает только участок, значения - отражение, "
            "файлы годятся для расчётов. Ссылка показывает всю сцену "
            "110 × 110 км из сети, данные загружаются при показе, "
            "индексы так не строятся."))
        self.folder = os.path.join(QgsProject.instance().homePath()
                                   or os.path.expanduser("~"), "sentinel")
        self.folder_label = QLabel(self)
        self.folder_label.setWordWrap(True)
        choose = QPushButton(tr("Папка…"), self)
        choose.clicked.connect(lambda _=False: self._choose_folder())
        out_row = QHBoxLayout()
        out_row.addWidget(self.mode)
        out_row.addWidget(self.clear)
        out_row.addStretch(1)
        folder_row = QHBoxLayout()
        folder_row.addWidget(self.folder_label, 1)
        folder_row.addWidget(choose)
        self.status = QLabel(self)
        self.status.setWordWrap(True)
        credit = QLabel(tr(
            "Copernicus Sentinel-2 L2A (ESA), файлы и каталог Earth Search "
            "Element 84 на AWS. Слои несут подпись «Contains modified "
            "Copernicus Sentinel data» с годом снимка."), self)
        credit.setWordWrap(True)
        self.add_button = QPushButton(tr("В проект QGIS"), self)
        self.add_button.setToolTip(tr(
            "Отмеченные продукты выбранной сцены - слоями проекта в группу "
            "дня внутри группы «Sentinel-2». Слои видны на карте и на "
            "глобусе."))
        self.add_button.setEnabled(False)
        self.add_button.clicked.connect(lambda _=False: self.add())
        buttons = QDialogButtonBox(
            enum(QDialogButtonBox, "StandardButton", "Close"), self)
        buttons.rejected.connect(self.close)
        buttons.addButton(self.add_button,
                          enum(QDialogButtonBox, "ButtonRole", "ActionRole"))
        layout = QVBoxLayout(self)
        layout.addWidget(self.where)
        layout.addLayout(grid)
        layout.addLayout(middle, 1)
        layout.addWidget(self.products)
        layout.addLayout(out_row)
        layout.addLayout(folder_row)
        layout.addWidget(self.status)
        layout.addWidget(credit)
        layout.addWidget(buttons)
        self._show_folder()
        self.resize(760, 640)

    # Участок.

    def show_point(self, lat, lon):
        """Участок - квадрат вокруг точки, сразу поиск."""
        self.point = (lat, lon)
        self.area_name = tr("Точка {lat}, {lon}", lat="{:.5f}".format(lat),
                            lon="{:.5f}".format(lon))
        self._area_changed(True)

    def show_place(self, place):
        """Участок - метка «Моих меток»: многоугольник своим контуром,
        путь - рамкой точек, точка - квадратом."""
        points = list(place.shape.points)
        if place.kind == "point" or len(points) < 2:
            self.show_point(*points[0])
            self.area_name = place.name or self.area_name
            self.where.setText(self.area_name)
            return
        self.point = None
        if place.kind == "polygon" and len(points) >= 3:
            self.ring = points
        else:
            lats = [p[0] for p in points]
            lons = [p[1] for p in points]
            self.ring = [(min(lats), min(lons)), (min(lats), max(lons)),
                         (max(lats), max(lons)), (max(lats), min(lons))]
        self.area_name = place.name or tr("Метка")
        self._area_changed(False)

    def _area_changed(self, point):
        self.side.setVisible(point)
        self.side_label.setVisible(point)
        self.where.setText(tr("Участок: {name}", name=self.area_name))
        self.search()

    def _current_ring(self):
        if self.point is not None:
            return s2.square(self.point[0], self.point[1],
                             self.side.value() * 1000.0)
        return self.ring

    def _choose_folder(self):
        path = QFileDialog.getExistingDirectory(
            self, tr("Папка снимков"), self.folder)
        if path:
            self.folder = path
            self._show_folder()

    def _show_folder(self):
        self.folder_label.setText(tr("Папка файлов: {path}",
                                     path=self.folder))

    # Поиск.

    def search(self):
        """Новый поиск: сцены участка за промежуток дат."""
        ring = self._current_ring()
        if ring is None:
            return
        self.ring_used = ring
        self.generation += 1
        self._stop_jobs()
        self.scenes = []
        self.clouds = {}
        self.list.clear()
        self.preview.clear()
        self.add_button.setEnabled(False)
        body = s2.search_body(
            s2.geojson(ring), self.start.date().toString("yyyy-MM-dd"),
            self.end.date().toString("yyyy-MM-dd"),
            self.scene_cloud.value())
        self.status.setText(tr("Поиск сцен…"))
        self._ask(body, self.generation)

    def _ask(self, body, generation):
        self.reply = post_json(
            s2.SEARCH, {"Content-Type": "application/json",
                        "Accept": "application/geo+json"}, body,
            lambda data, error, g=generation: self._page(data, error, g))

    def _page(self, data, error, generation):
        self.reply = None
        if generation != self.generation:
            return
        if data is None or error:
            self.status.setText(tr("Каталог не ответил: {error}",
                                   error=error or "-"))
            return
        scenes, following = s2.parse_page(data)
        self.scenes += scenes
        for s in scenes:
            self._row(s)
        if following and len(self.scenes) < s2.MAX_SCENES:
            self._ask(following, generation)
            return
        self.status.setText(tr(
            "Найдено сцен {count}, считается облачность над участком…",
            count=len(self.scenes)))
        self._start_clouds(generation)

    def _row(self, s):
        item = QTreeWidgetItem([s.when, "…", "{:.0f} %".format(s.cloud),
                                "{:.0f}°".format(s.sun)
                                if s.sun is not None else "-", s.tile])
        item.setData(0, SCENE_ROLE, s.id)
        self.list.addTopLevelItem(item)

    def _start_clouds(self, generation):
        warm()
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=CLOUD_WORKERS)
        ring = self.ring_used
        self.cloud_jobs = [(generation, self.pool.submit(scene_cloud, s,
                                                         ring))
                           for s in self.scenes]
        self.timer.start()

    def _poll(self):
        counting = bool(self.cloud_jobs)
        pending = []
        for generation, job in self.cloud_jobs:
            if not job.done():
                pending.append((generation, job))
                continue
            if generation != self.generation:
                continue
            try:
                number, cloud, valid = job.result()
            except (RuntimeError, ValueError, OSError):
                # Сцена остаётся с «…» в столбце облачности.
                number = None
            if number is not None:
                self.clouds[number] = (cloud, valid)
                self._mark(number)
        self.cloud_jobs = pending
        if self.preview_job is not None and self.preview_job[1].done():
            self._preview_done()
        if self.build_job is not None and self.build_job[1].done():
            self._built()
        if not self.cloud_jobs and self.preview_job is None \
                and self.build_job is None:
            self.timer.stop()
        if counting and not pending:
            self._summary()

    def _mark(self, number):
        for n in range(self.list.topLevelItemCount()):
            item = self.list.topLevelItem(n)
            if item.data(0, SCENE_ROLE) != number:
                continue
            cloud, valid = self.clouds[number]
            if cloud is None:
                item.setText(1, "?")
            elif valid < 50.0:
                item.setText(1, tr("{cloud} %, данных {valid} %",
                                   cloud="{:.0f}".format(cloud),
                                   valid="{:.0f}".format(valid)))
            else:
                item.setText(1, "{:.0f} %".format(cloud))
            self._filter_item(item)
            if self.list.currentItem() is None and not item.isHidden():
                self.list.setCurrentItem(item)

    def _filter_item(self, item):
        cloud, valid = self.clouds.get(item.data(0, SCENE_ROLE),
                                       (None, None))
        hidden = cloud is not None and (cloud > self.area_cloud.value()
                                        or valid < 50.0)
        item.setHidden(bool(hidden))

    def _filter(self, *args):
        for n in range(self.list.topLevelItemCount()):
            self._filter_item(self.list.topLevelItem(n))
        if self.scenes and not self.cloud_jobs:
            self._summary()

    def _summary(self):
        shown = sum(not self.list.topLevelItem(n).isHidden()
                    for n in range(self.list.topLevelItemCount()))
        self.status.setText(tr(
            "Сцен {total}, над участком не облачнее {cloud} % - {count}.",
            total=len(self.scenes), cloud=self.area_cloud.value(),
            count=shown))

    def _scene(self, item):
        number = item.data(0, SCENE_ROLE) if item is not None else None
        return next((s for s in self.scenes if s.id == number), None)

    def _chosen(self, item, previous=None):
        s = self._scene(item)
        self.add_button.setEnabled(s is not None)
        self.preview.clear()
        if s is None:
            return
        warm()
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=CLOUD_WORKERS)
        self.preview_job = (s.id, self.pool.submit(preview, s,
                                                   self.ring_used))
        self.timer.start()

    def _preview_done(self):
        number, job = self.preview_job
        self.preview_job = None
        current = self._scene(self.list.currentItem())
        try:
            rgb = job.result()
        except (RuntimeError, ValueError, OSError):
            rgb = None
        if rgb is None or current is None or current.id != number:
            return
        rgb = np.ascontiguousarray(np.transpose(rgb[:3], (1, 2, 0)))
        height, width = rgb.shape[:2]
        image = QImage(rgb.data, width, height, 3 * width,
                       enum(QImage, "Format", "Format_RGB888")).copy()
        self.preview.setPixmap(QPixmap.fromImage(image).scaled(
            PREVIEW, PREVIEW, enum(Qt, "AspectRatioMode", "KeepAspectRatio"),
            enum(Qt, "TransformationMode", "SmoothTransformation")))

    # Выдача.

    def chosen_products(self):
        out = []
        for n in range(self.products.count()):
            item = self.products.item(n)
            if item.checkState() == enum(Qt, "CheckState", "Checked"):
                out.append(item.data(SCENE_ROLE))
        return out

    def add(self, folder=None):
        """Отмеченные продукты выбранной сцены в проект. Расчёт - в
        рабочем потоке, слои - по готовности."""
        s = self._scene(self.list.currentItem())
        products = self.chosen_products()
        if s is None or self.build_job is not None:
            return
        if not products:
            self.status.setText(tr("Не отмечено ни одного продукта."))
            return
        folder = folder or self.folder
        warm()
        if self.pool is None:
            self.pool = ThreadPoolExecutor(max_workers=CLOUD_WORKERS)
        if self.mode.currentData() == "link":
            job = self.pool.submit(build_links, s, products, folder)
        else:
            job = self.pool.submit(build, s, self.ring_used, products,
                                   folder, self.clear.isChecked())
        self.build_job = (s, job)
        self.add_button.setEnabled(False)
        self.status.setText(tr("Загрузка каналов сцены {when}…",
                               when=s.when))
        self.timer.start()

    def _built(self):
        s, job = self.build_job
        self.build_job = None
        self.add_button.setEnabled(True)
        try:
            made = job.result()
        except (RuntimeError, ValueError, OSError) as error:
            self.status.setText(tr("Снимок не загружен: {error}",
                                   error=str(error)))
            return
        if not made:
            self.status.setText(tr(
                "Ссылкой ложатся только сочетания каналов, индексы - "
                "обрезкой по участку."))
            return
        layers = self.add_layers(s, made)
        self.status.setText(tr("В проект добавлено слоёв {count}: {path}",
                               count=len(layers),
                               path=os.path.dirname(made[0][1])))

    def add_layers(self, s, made):
        """Слои продуктов в группу дня внутри группы «Sentinel-2»."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        top = root.findGroup(GROUP) or root.insertGroup(0, GROUP)
        name = "{} {}".format(s.when[:10], s.tile)
        day = top.findGroup(name) or top.insertGroup(0, name)
        names = titles()
        layers = []
        for product, path, ranges in made:
            layer = QgsRasterLayer(path, "{} - {}".format(
                names[product], s.when[:10]), "gdal")
            if not layer.isValid():
                continue
            if product in s2.COMPOSITES:
                style_composite(layer, ranges)
            else:
                style_index(layer, product)
            metadata = layer.metadata()
            metadata.setRights([s2.credit(s)])
            layer.setMetadata(metadata)
            project.addMapLayer(layer, False)
            day.addLayer(layer)
            self.window.set_layer_shown(layer.id(), True)
            layers.append(layer)
        return layers

    def _stop_jobs(self):
        if self.reply is not None:
            reply, self.reply = self.reply, None
            reply.abort()
        for _, job in self.cloud_jobs:
            job.cancel()
        self.cloud_jobs = []

    def closeEvent(self, event):
        self.timer.stop()
        self.generation += 1
        self._stop_jobs()
        if self.pool is not None:
            self.pool.shutdown(wait=False, cancel_futures=True)
            self.pool = None
        self.preview_job = None
        self.build_job = None
        super().closeEvent(event)

