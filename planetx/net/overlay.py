# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Наложение: слои QGIS, нарисованные в картинки тайлов глобуса.

Картинку тайла рисует QgsMapRendererParallelJob в EPSG:3857
по границам тайла Web Mercator. Задание считает в потоках QGIS,
главный поток только запускает его и забирает картинку. Картинка
в массив с премноженной альфой и мипмапы - в своём пуле потоков,
как у загрузчика тайлов.

Устройство то же, что у TileLoader в net/loader.py: want_many, retain,
busy, сигналы loaded, failed и idle. Окно глобуса работает с обоими
одинаково.

Первый источник - векторные тайлы OpenFreeMap. Адрес тайлов меняется
с каждой сборкой планеты, поэтому он берётся из TileJSON. Стиль свой,
только линии. Подписей нет: в картинке тайла они поворачивались бы
вместе с Землёй.
"""
import json
import time

import numpy as np
from qgis.core import (Qgis, QgsCoordinateReferenceSystem,
                       QgsExpressionContext, QgsExpressionContextUtils,
                       QgsLineSymbol, QgsProject,
                       QgsMapRendererParallelJob, QgsMapSettings,
                       QgsNetworkAccessManager, QgsRectangle,
                       QgsVectorTileBasicRenderer,
                       QgsVectorTileBasicRendererStyle, QgsVectorTileLayer,
                       QgsWkbTypes)
from qgis.PyQt.QtCore import (QObject, QRunnable, QSize, QThreadPool, QTimer,
                              QUrl, pyqtSignal)
from qgis.PyQt.QtGui import QColor, QImage
from qgis.PyQt.QtNetwork import QNetworkRequest

from ..core.mipmap import mip_chain
from ..core.overlay import mercator_bounds
from ..core.tile_queue import TileQueue
from ..qt_compat import enum
from .loader import CACHE_CONTROL, MARK, NO_ERROR, PREFER_CACHE

TILE_SIZE = 256
MAX_JOBS = 6  # отрисовок одновременно, считает QGIS в своих потоках
# Подготовка картинки - Python и NumPy, она держит GIL. Один поток
# делит GIL с главным меньше двух, а успевает сотни картинок в секунду.
PREPARE_THREADS = 1
START_GAP = 0.015  # секунд между запусками заданий, как у загрузчика

OPENFREEMAP_TILEJSON = "https://tiles.openfreemap.org/planet"
OPENFREEMAP_ATTRIBUTION = (
    "OpenFreeMap © OpenMapTiles, © OpenStreetMap contributors",
    "https://openfreemap.org/")

LINE = QgsWkbTypes.GeometryType.LineGeometry
PREMULTIPLIED = enum(QImage, "Format", "Format_RGBA8888_Premultiplied")

# Группы линий векторной основы, их включают по отдельности.
BORDERS, RIVERS, ROADS = "borders", "rivers", "roads"
LINE_GROUPS = (BORDERS, RIVERS, ROADS)

# Стиль линий: группа, слой схемы OpenMapTiles, условие, цвет RGBA,
# толщина в пикселях картинки тайла, наименьший уровень.
LINE_STYLES = (
    (BORDERS, "boundary", '"admin_level" = 2 AND "maritime" = 0',
     "255,220,0,255", 2.0, 0),
    (BORDERS, "boundary", '"admin_level" = 4 AND "maritime" = 0',
     "255,220,0,190", 1.0, 4),
    (RIVERS, "waterway", "\"class\" = 'river'", "120,190,255,220", 1.2, 8),
    (ROADS, "transportation",
     "\"class\" IN ('motorway', 'trunk', 'primary')",
     "255,255,255,210", 1.2, 6),
    (ROADS, "transportation",
     "\"class\" IN ('secondary', 'tertiary', 'minor', 'service')",
     "255,255,255,150", 0.8, 12),
)


def openfreemap_layer(tiles_url, max_zoom=14, groups=LINE_GROUPS):
    """Слой векторных тайлов OpenFreeMap со стилем из линий."""
    uri = "type=xyz&url={}&zmin=0&zmax={}".format(tiles_url, max_zoom)
    layer = QgsVectorTileLayer(uri, "OpenFreeMap")
    set_line_groups(layer, groups)
    return layer


def set_line_groups(layer, groups):
    """Оставить в стиле слоя OpenFreeMap только линии групп groups."""
    styles = []
    for index, (group, source, expression, color, width, zmin) in \
            enumerate(LINE_STYLES):
        if group not in groups:
            continue
        style = QgsVectorTileBasicRendererStyle(
            "line {}".format(index), source, LINE)
        style.setSymbol(QgsLineSymbol.createSimple({
            "color": color, "width": str(width), "width_unit": "Pixel",
            "capstyle": "round", "joinstyle": "round"}))
        style.setFilterExpression(expression)
        style.setMinZoomLevel(zmin)
        styles.append(style)
    renderer = QgsVectorTileBasicRenderer()
    renderer.setStyles(styles)
    layer.setRenderer(renderer)


def fetch_json(url, done):
    """Асинхронно получить JSON и вызвать done(данные или None, ошибка).

    Запрос идёт через QgsNetworkAccessManager с меткой PlanetX, как
    запросы тайлов. Возвращает ответ, его нужно держать до конца.
    """
    request = QNetworkRequest(QUrl(url))
    request.setAttribute(MARK, True)
    request.setAttribute(CACHE_CONTROL, PREFER_CACHE)
    reply = QgsNetworkAccessManager.instance().get(request)

    def finished():
        if reply.error() != NO_ERROR:
            done(None, reply.errorString())
        else:
            try:
                done(json.loads(bytes(reply.readAll())), "")
            except ValueError as error:
                done(None, str(error))
        reply.deleteLater()

    reply.finished.connect(finished)
    return reply


class _Prepared(QObject):
    """Живёт в главном потоке. Сигнал из рабочего потока идёт очередью."""

    done = pyqtSignal(object, object)


class _PrepareTask(QRunnable):
    """Картинка в массив с премноженной альфой и мипмапы.

    Только QImage и NumPy, без OpenGL. Предупреждения NumPy гасятся,
    предупреждение Python в рабочем потоке роняет QGIS. Картинка без
    единого непрозрачного пикселя идёт как None: в лесу и в поле линий
    на тайле часто нет, мипмапы и загрузка в видеокарту ему не нужны.
    """

    def __init__(self, key, image, sink):
        super().__init__()
        self.key = key
        self.image = image
        self.sink = sink

    def run(self):
        with np.errstate(all="ignore"):
            image = self.image
            if image.format() != PREMULTIPLIED:
                image = image.convertToFormat(PREMULTIPLIED)
            ptr = image.constBits()
            ptr.setsize(image.sizeInBytes())
            rows = np.frombuffer(ptr, dtype=np.uint8).reshape(
                image.height(), image.bytesPerLine())
            rgba = rows[:, :image.width() * 4].reshape(
                image.height(), image.width(), 4)
            levels = mip_chain(rgba.copy()) if rgba[..., 3].any() else None
        self.sink.done.emit(self.key, levels)


class LayerOverlay(QObject):
    """Картинки тайлов из слоёв QGIS.

    loaded несёт ключ, уровни мипмапов и None, как у TileLoader.
    Уровни None - картинка пустая.
    """

    loaded = pyqtSignal(object, object, object)
    failed = pyqtSignal(object, str)
    idle = pyqtSignal()

    def __init__(self, layers, parent=None):
        super().__init__(parent)
        self.layers = list(layers)
        self.crs = QgsCoordinateReferenceSystem("EPSG:3857")
        self.queue = TileQueue(max_active=MAX_JOBS)
        self.jobs = {}
        # Задания, которые уже не нужны, но ещё живы. Отпустить объект
        # задания, пока в нём работают потоки QGIS или идёт рассылка
        # его сигнала, значит уронить QGIS. Они отпускаются в следующем
        # проходе цикла событий после своего сигнала finished.
        self.retired = set()
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(PREPARE_THREADS)
        self.sink = _Prepared(self)
        self.sink.done.connect(self._prepared)
        self.preparing = {}
        self.last_start = 0.0
        self.pump_timer = QTimer(self)
        self.pump_timer.setSingleShot(True)
        self.pump_timer.timeout.connect(self._pump)
        # Сведения для проверочных скриптов: время отрисовки по ключам.
        self.render_times = {}
        self.started_at = {}

    def want_many(self, items):
        now = time.monotonic()
        for key, priority in items:
            self.queue.want(key, priority, now=now)
        self._later()

    def retain(self, keys):
        for key in self.queue.retain(keys):
            job = self.jobs.pop(key, None)
            if job is not None:
                job.finished.disconnect()
                job.finished.connect(lambda job=job: self._retire(job))
                self.retired.add(job)
                job.cancelWithoutBlocking()
            self.queue.done(key, ok=True)
        self._later()

    def _later(self):
        """Запустить запросы после текущего кадра.

        want_many и retain зовутся из paintGL. Запуск запроса стоит
        главному потоку до нескольких миллисекунд. Между кадрами у него
        есть время простоя, кадр от запуска не удлиняется.
        """
        if not self.pump_timer.isActive():
            self.pump_timer.start(0)

    def busy(self):
        return len(self.queue) + len(self.preparing)

    def _settings(self, key):
        settings = QgsMapSettings()
        settings.setLayers(self.layers)
        settings.setDestinationCrs(self.crs)
        settings.setExtent(QgsRectangle(*mercator_bounds(*key)))
        settings.setOutputSize(QSize(TILE_SIZE, TILE_SIZE))
        settings.setOutputDpi(96)
        settings.setBackgroundColor(QColor(0, 0, 0, 0))
        # Картинка сразу в формате текстуры, перевод в рабочем потоке
        # не нужен.
        settings.setOutputImageFormat(PREMULTIPLIED)
        settings.setFlag(Qgis.MapSettingsFlag.DrawLabeling, False)
        settings.setFlag(Qgis.MapSettingsFlag.Antialiasing, True)
        # Знаки и линии без обрезки на стыках соседних тайлов.
        settings.setFlag(Qgis.MapSettingsFlag.RenderMapTile, True)
        # Слои проекта в своих системах координат и со стилями на
        # выражениях: преобразования и переменные берутся из проекта.
        project = QgsProject.instance()
        settings.setTransformContext(project.transformContext())
        context = QgsExpressionContext()
        context.appendScope(QgsExpressionContextUtils.globalScope())
        context.appendScope(QgsExpressionContextUtils.projectScope(project))
        settings.setExpressionContext(context)
        return settings

    def _pump(self):
        wait = self.last_start + START_GAP - time.monotonic()
        if wait > 0.0:
            if self.queue.waiting and not self.pump_timer.isActive():
                self.pump_timer.start(int(wait * 1000) + 1)
            return
        key = self.queue.next()
        if key is None:
            return
        job = QgsMapRendererParallelJob(self._settings(key))
        job.finished.connect(lambda key=key, job=job: self._finished(key, job))
        self.jobs[key] = job
        self.started_at[key] = time.perf_counter()
        job.start()
        self.last_start = time.monotonic()
        if self.queue.waiting and not self.pump_timer.isActive():
            self.pump_timer.start(int(START_GAP * 1000) + 1)

    def _retire(self, job):
        QTimer.singleShot(0, lambda: self.retired.discard(job))

    def _finished(self, key, job):
        if self.jobs.get(key) is not job:
            return
        del self.jobs[key]
        self.retired.add(job)
        self._retire(job)
        self.render_times[key] = time.perf_counter() - \
            self.started_at.pop(key, time.perf_counter())
        errors = job.errors()
        if errors:
            self.queue.done(key, ok=False, now=time.monotonic())
            self.failed.emit(key, errors[0].message)
        else:
            self.queue.done(key, ok=True)
            self.preparing[key] = True
            self.pool.start(_PrepareTask(key, job.renderedImage(),
                                         self.sink))
        self._pump()
        self._check_idle()

    def _prepared(self, key, levels):
        self.preparing.pop(key, None)
        self.loaded.emit(key, levels, None)
        self._check_idle()

    def _check_idle(self):
        if not self.busy():
            self.idle.emit()

    def abort(self):
        """Снять всё. Сигналы по снятым заданиям не приходят."""
        self.pump_timer.stop()
        for job in list(self.jobs.values()):
            job.finished.disconnect()
            job.cancel()
        self.jobs.clear()
        for job in list(self.retired):
            job.cancel()
        self.retired.clear()
        self.retain([])
        self.sink.done.disconnect()
        self.pool.clear()
        self.pool.waitForDone(1000)
