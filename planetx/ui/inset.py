# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Врезка своего рельефа: растры высот проекта в высоты глобуса.

Подготовка идёт в главном потоке при включении слоя: растр через GDAL
пересчитывается в EPSG:3857 в файл профиля с уровнями обзора, рядом
пишется вес края (core.inset.edge_weight по расстоянию до края данных).
Выборка на тайл высот идёт в рабочем потоке загрузчика: окно тайла
из обоих файлов по 256 пикселей, слияние core.inset.merge.

FutureWarning модуля osgeo о режиме исключений выдаётся один раз на
процесс. warm() вызывает GDAL в главном потоке до первой выборки:
предупреждение в рабочем потоке роняет QGIS, см. AGENTS.md.
"""
import hashlib
import os
import threading
from collections import OrderedDict
from concurrent.futures import TimeoutError

import numpy as np
from qgis.core import QgsApplication

from ..core import basemap, dem, inset
from ..net.gdalnet import executor, thread_gdal
from ..core.terrain import (MAX_LEVEL, SIZE, HeightTile, ancestor, decode,
                            resample)

WEIGHT_SIDE = 2048  # пикселей на сторону растра веса края, не больше
NODATA = float("nan")


def folder():
    """Папка подготовленных растров в профиле QGIS."""
    path = os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                        "insets")
    os.makedirs(path, exist_ok=True)
    return path


def warm():
    """Первый вызов GDAL в главном потоке, см. описание модуля."""
    from osgeo import gdal
    source = gdal.GetDriverByName("MEM").Create("", 1, 1, 1,
                                                gdal.GDT_Float32)
    gdal.Translate("", source, format="MEM")


class DeepSource(basemap.Source):
    """Источник высот, у которого тайл глубже max_level - адрес предка
    уровня max_level. Тайл врезки уровня 16-17 пересчитывается из него
    в рабочем потоке (terrain_prepare)."""

    __slots__ = ()

    def tile_url(self, z, x, y):
        if z > self.max_level:
            z, x, y = ancestor((z, x, y), self.max_level)
        return basemap.tile_url(self.url, z, x, y)


class Entry:
    """Подготовленный растр врезки: файлы высот и веса в EPSG:3857,
    рамка, уровень высот, название слоя."""

    __slots__ = ("layer_id", "name", "path", "weight", "bounds", "level")

    def __init__(self, layer_id, name, path, weight, bounds, level):
        self.layer_id = layer_id
        self.name = name
        self.path = path
        self.weight = weight
        self.bounds = bounds
        self.level = level

    def box(self):
        """Рамка в долях мира с уровнем, для HeightStore.deep."""
        return inset.shares(*self.bounds) + (self.level,)


def _stamp(source):
    """Имя файла по источнику и его времени изменения: правка файла
    съёмки даёт новую подготовку."""
    path = source.split("|")[0]
    try:
        info = os.stat(path)
        mark = "{}:{}:{}".format(source, info.st_mtime_ns, info.st_size)
    except OSError:
        mark = source
    return hashlib.sha256(mark.encode("utf-8")).hexdigest()[:16]


def prepare(layer):
    """Растр слоя QGIS в Entry или текст ошибки. Главный поток."""
    from osgeo import gdal
    warm()
    if layer.providerType() != "gdal":
        return "provider"
    source = layer.source()
    base = os.path.join(folder(), _stamp(source))
    path, weight = base + ".tif", base + "_w.tif"
    if not (os.path.exists(path) and os.path.exists(weight)):
        src = gdal.Open(source)
        if src is None:
            return "open"
        band = src.GetRasterBand(1)
        nodata = band.GetNoDataValue()
        out = gdal.Warp(path, src, format="GTiff", dstSRS="EPSG:3857",
                        outputType=gdal.GDT_Float32, resampleAlg="bilinear",
                        srcNodata=nodata, dstNodata=NODATA,
                        creationOptions=["TILED=YES", "COMPRESS=DEFLATE",
                                         "PREDICTOR=3", "BIGTIFF=IF_SAFER"])
        src = None
        if out is None:
            return "warp"
        factors = []
        side = max(out.RasterXSize, out.RasterYSize)
        while side > SIZE:
            factors.append(2 ** (len(factors) + 1))
            side //= 2
        if factors:
            out.BuildOverviews("AVERAGE", factors)
        out = None
        if not _write_weight(path, weight):
            return "weight"
    data = gdal.Open(path)
    if data is None:
        return "open"
    x0, dx, _, y0, _, dy = data.GetGeoTransform()
    bounds = (x0, y0 + dy * data.RasterYSize, x0 + dx * data.RasterXSize, y0)
    level = inset.level_for(abs(dx))
    data = None
    return Entry(layer.id(), layer.name(), path, weight, bounds, level)


def _write_weight(path, weight):
    """Вес края по расстоянию до края данных: маска на сетке не крупнее
    WEIGHT_SIDE, рамка из нулей вокруг - край растра тоже край."""
    from osgeo import gdal
    data = gdal.Open(path)
    if data is None:
        return False
    width, height = data.RasterXSize, data.RasterYSize
    step = max(1.0, max(width, height) / float(WEIGHT_SIDE))
    cols = max(1, int(round(width / step)))
    rows = max(1, int(round(height / step)))
    small = gdal.Translate("", data, format="MEM", width=cols, height=rows,
                           resampleAlg="nearest")
    x0, dx, _, y0, _, dy = data.GetGeoTransform()
    data = None
    if small is None:
        return False
    heights = small.GetRasterBand(1).ReadAsArray()
    small = None
    sx = dx * width / cols
    sy = dy * height / rows
    mask = np.zeros((rows + 2, cols + 2), dtype=np.uint8)
    mask[1:-1, 1:-1] = np.isfinite(heights)
    mem = gdal.GetDriverByName("MEM")
    grid = (x0 - sx, sx, 0.0, y0 - sy, 0.0, sy)
    marks = mem.Create("", cols + 2, rows + 2, 1, gdal.GDT_Byte)
    marks.SetGeoTransform(grid)
    marks.GetRasterBand(1).WriteArray(mask)
    near = mem.Create("", cols + 2, rows + 2, 1, gdal.GDT_Float32)
    near.SetGeoTransform(grid)
    gdal.ComputeProximity(marks.GetRasterBand(1), near.GetRasterBand(1),
                          ["VALUES=0", "DISTUNITS=GEO"])
    distance = near.GetRasterBand(1).ReadAsArray()
    west, south, east, north = x0, y0 + dy * height, x0 + dx * width, y0
    band = inset.band_width(west, south, east, north)
    out = gdal.GetDriverByName("GTiff").Create(
        weight, cols + 2, rows + 2, 1, gdal.GDT_Float32,
        ["TILED=YES", "COMPRESS=DEFLATE"])
    if out is None:
        return False
    out.SetGeoTransform(grid)
    out.SetProjection(marks.GetProjection() or _webmercator())
    out.GetRasterBand(1).WriteArray(inset.edge_weight(distance, band))
    out = None
    return True


def _webmercator():
    from osgeo import osr
    ref = osr.SpatialReference()
    ref.ImportFromEPSG(3857)
    return ref.ExportToWkt()


def _window(path, bounds):
    """Окно рамки bounds (EPSG:3857) из файла path, 256 × 256 float32,
    по центрам пикселей тайла. Рабочий поток."""
    from osgeo import gdal
    west, south, east, north = bounds
    out = gdal.Translate("", path, format="MEM", projWin=[west, north,
                                                          east, south],
                         width=SIZE, height=SIZE, resampleAlg="bilinear",
                         outputType=gdal.GDT_Float32)
    if out is None:
        return None
    array = out.GetRasterBand(1).ReadAsArray()
    out = None
    return array


class DemSource:
    """Модель рельефа 30 м поверх Terrarium (core/dem.py): окно тайла
    из файлов в сети через GDAL. Читает постоянный пул «dem»
    (net/gdalnet.py), рабочий поток загрузчика ждёт его ответа.

    Открытые файлы помнит каждый поток пула, файлы, которых нет
    (Copernicus над морем отвечает 404), - общий список."""

    WORKERS = 6  # тайлов, читаемых сразу
    KEEP = 24  # открытых файлов на поток
    WAIT = 120.0  # с ожидания окна, дальше тайл остаётся Terrarium
    WINDOWS = 160  # прочитанных окон в памяти, по 256 КБ

    def __init__(self, kind):
        self.kind = kind
        self.absent = set()
        self.local = threading.local()
        self.lock = threading.Lock()
        self.jobs = OrderedDict()  # ключ уровня до READ_LEVEL -> задача
        self.errors = 0  # окон, не прочитанных из-за сети
        self.last_error = ""  # текст последней ошибки, для журнала

    def merge(self, key, heights):
        """Высоты тайла key с моделью. Рабочий поток загрузчика. Глубже
        dem.READ_LEVEL окно - пересчёт окна предка: пиксель тайла
        уровня 12 уже около 30 м, новые чтения сети не нужны."""
        if key[0] < dem.MIN_LEVEL:
            return heights
        read = key if key[0] <= dem.READ_LEVEL \
            else ancestor(key, dem.READ_LEVEL)
        try:
            window = self._job(read).result(timeout=self.WAIT)
        except TimeoutError:
            self.errors += 1
            return heights
        except OSError:
            return heights
        if window is None:
            return heights
        if read != key:
            window = resample(HeightTile(*read, window, 0.0, 0.0), key)
        return dem.merge(heights, window)

    def _job(self, key):
        """Задача чтения окна key, одна на ключ: тайлы-дети ждут одну
        и ту же."""
        with self.lock:
            job = self.jobs.get(key)
            if job is not None and not (job.done() and job.exception()):
                self.jobs.move_to_end(key)
                return job
            job = executor("dem", self.WORKERS).submit(self.window, key)
            self.jobs[key] = job
            while len(self.jobs) > self.WINDOWS:
                self.jobs.popitem(last=False)
            return job

    def _urls(self, key):
        if self.kind == dem.GEDTM:
            return [dem.GEDTM_URL]
        west, south, east, north = dem.tile_degrees(*key)
        return [dem.copernicus_url(lat, lon) for lat, lon in
                dem.copernicus_cells(west, south, east, north)]

    def _open(self, gdal, url):
        cache = getattr(self.local, "files", None)
        if cache is None:
            cache = self.local.files = {}
        if url in cache:
            cache[url] = cache.pop(url)
            return cache[url]
        if url in self.absent:
            return None
        try:
            data = gdal.Open("/vsicurl/" + url)
        except RuntimeError as error:
            if "404" in str(error):
                self.absent.add(url)
                return None
            # Сеть: задача кончается ошибкой, окно прочитается заново
            # при следующей просьбе (_job).
            self.errors += 1
            self.last_error = str(error)
            raise OSError(str(error)) from error
        if data is None:
            # Без режима исключений GDAL ошибка - в последнем сообщении.
            message = gdal.GetLastErrorMsg()
            if "404" in message:
                self.absent.add(url)
                return None
            self.errors += 1
            self.last_error = message
            raise OSError(message)
        cache[url] = data
        while len(cache) > self.KEEP:
            cache.pop(next(iter(cache)))
        return data

    def window(self, key):
        """Окно тайла key, 256 × 256 float32, NaN без данных, или None.
        Поток пула «dem»."""
        gdal = thread_gdal()
        gdal.PushErrorHandler("CPLQuietErrorHandler")
        try:
            files = [d for d in (self._open(gdal, url)
                                 for url in self._urls(key))
                     if d is not None]
            if not files:
                return None
            try:
                out = gdal.Warp("", files, format="MEM",
                                dstSRS="EPSG:3857",
                                outputBounds=dem.tile_meters(*key),
                                width=SIZE, height=SIZE,
                                resampleAlg="bilinear",
                                outputType=gdal.GDT_Float32,
                                dstNodata=NODATA)
            except RuntimeError as error:
                self.last_error = str(error)
                out = None
            if out is None:
                self.errors += 1
                raise OSError(self.last_error or "warp")
            array = out.GetRasterBand(1).ReadAsArray()
            out = None
            return array
        finally:
            gdal.PopErrorHandler()


def apply(entries, key, heights):
    """Высоты тайла key с врезками entries: нижние в проекте первыми,
    верхняя последней. Модель рельефа DemSource стоит первой. Рабочий
    поток."""
    bounds = inset.tile_bounds(*key)
    for entry in entries:
        if isinstance(entry, DemSource):
            heights = entry.merge(key, heights)
            continue
        if not inset.overlaps(entry.bounds, *bounds):
            continue
        dem = _window(entry.path, bounds)
        weight = _window(entry.weight, bounds)
        if dem is None or weight is None:
            continue
        heights = inset.merge(heights, dem, weight)
    return heights


def terrain_prepare(entries, floor, encoding="terrarium"):
    """Подготовка тайла высот в рабочем потоке: высоты в записи encoding
    (core.terrain.decode), у тайла глубже MAX_LEVEL - пересчёт из
    предка, затем врезки entries. entries - кортеж, главный поток его
    не меняет, а заменяет."""
    def make(key, rgba):
        z, x, y = key
        heights = decode(rgba, floor, encoding)
        if z > MAX_LEVEL:
            parent = ancestor(key, MAX_LEVEL)
            heights = resample(HeightTile(*parent, heights, 0.0, 0.0), key)
        if entries:
            heights = apply(entries, key, heights)
        return HeightTile(z, x, y, heights, float(np.nanmin(heights)),
                          float(np.nanmax(heights)))
    return make
