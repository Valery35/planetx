# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка картинок тайлов через QgsNetworkAccessManager.

Запросы асинхронные и идут в главном потоке. Так работают прокси
и дисковый кэш из настроек QGIS. Раскодирование PNG и подготовка тайла
идут в рабочем потоке, в собственном пуле загрузчика. Рабочий поток
не делает сетевых запросов и не ждёт главный поток.

Вызов QgsNetworkAccessManager.get() стоит 2.5-11 мс главного потока
даже для ответа из кэша, замер 26 сентября 2026 года. Пачка таких
вызовов подряд давала пропуски такта монитора. Поэтому новые запросы
уходят не чаще одного за START_GAP.

Запросы из рабочих потоков через QgsBlockingNetworkRequest пробовались
26 сентября 2026 года и повесили QGIS. Не возвращать, см. AGENTS.md.

Правила OSM из AGENTS.md соблюдаются здесь: заголовок User-Agent,
не больше двух запросов одновременно, ответ берётся из кэша, если он
там есть. Порядок запросов и отмену решает очередь
из core/tile_queue.py.
"""
import base64
import time
from collections import OrderedDict

import numpy as np
from qgis.core import QgsApplication, QgsNetworkAccessManager
from qgis.PyQt.QtCore import (QObject, QRunnable, Qt, QThreadPool, QTimer,
                              QUrl, pyqtSignal)
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from ..core import basemap
from ..core.placeholder import (MAX_FILL_DEPTH, ancestor, crop_window,
                                is_placeholder)
from ..core.tile_queue import TileQueue
from ..meta import plugin_version
from ..qt_compat import enum, enum_int

TERRARIUM_URL = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
                 "{z}/{x}/{y}.png")
DECODE_THREADS = 2
START_GAP = 0.015  # секунд между запусками запросов, около кадра
# Пока камера движется, запросы всех загрузчиков и запуски картинок
# слоёв идут не чаще раза в MOVING_GAP на всех вместе. Запуск стоит
# главному потоку 2.5-11 мс. Проезд тура по пути 28 сентября 2026 года
# давал паузы до 105 мс: каждый загрузчик слал свои запросы по своему
# отсчёту, ответ сразу запускал следующий. Движение важнее загрузки,
# решение автора: пусть загрузится не всё, кадр загрузку не ждёт.
MOVING_GAP = 0.05
STALL = 0.2  # секунд просрочки таймера запуска, дальше запуск без него
# Метка запросов PlanetX, пользовательский атрибут запроса Qt.
MARK = QNetworkRequest.Attribute(
    enum_int(enum(QNetworkRequest, "Attribute", "User")) + 71)
FROM_CACHE = enum(QNetworkRequest, "Attribute", "SourceIsFromCacheAttribute")
CACHE_CONTROL = enum(QNetworkRequest, "Attribute",
                     "CacheLoadControlAttribute")
PREFER_CACHE = enum(QNetworkRequest, "CacheLoadControl", "PreferCache")
NO_ERROR = enum(QNetworkReply, "NetworkError", "NoError")
HTTP_STATUS = enum(QNetworkRequest, "Attribute", "HttpStatusCodeAttribute")
# Переадресация. Qt 6 по умолчанию идёт по ней, Qt 5 нет. Файлы
# выпусков GitHub отдаются переадресацией 302, картинка неба в QGIS
# 3.36 не приходила, 29 сентября 2026 года.
REDIRECT = enum(QNetworkRequest, "Attribute", "RedirectPolicyAttribute")
SAFE_REDIRECT = enum(QNetworkRequest, "RedirectPolicy",
                     "NoLessSafeRedirectPolicy")
ALWAYS_NETWORK =enum(QNetworkRequest, "CacheLoadControl", "AlwaysNetwork")
CACHE_SAVE = enum(QNetworkRequest, "Attribute", "CacheSaveControlAttribute")
# Ответ раскодирования для заглушки вместо снимка, см. core/placeholder.
MISSING = "missing"
RECENT_TILES = 256  # байтов тайлов в памяти для вырезки, штук
FILL_PRIORITY = 1.0e9  # предок для вырезки нужнее прочих тайлов


USER_AGENT = "PlanetX/{} (+https://github.com/Valery35/planetx)".format(
    plugin_version())

_preprocessor = None


def _set_user_agent(request):
    """Заголовок PlanetX для запросов с меткой.

    QgsNetworkAccessManager заменяет User-Agent любого запроса своим.
    Обработчик вызывается после этой замены. Он общий для всех запросов
    QGIS, в том числе из рабочих потоков, поэтому трогает только запросы
    с меткой и не порождает ни исключений, ни предупреждений.
    """
    if request.attribute(MARK):
        request.setRawHeader(b"User-Agent", USER_AGENT.encode())


def install_user_agent():
    global _preprocessor
    if _preprocessor is None:
        _preprocessor = QgsNetworkAccessManager.setRequestPreprocessor(
            _set_user_agent)


def remove_user_agent():
    """Снять обработчик. Вызывается при выгрузке плагина."""
    global _preprocessor
    if _preprocessor is not None:
        QgsNetworkAccessManager.removeRequestPreprocessor(_preprocessor)
        _preprocessor = None


def image_to_rgba(image):
    """QImage в массив (h, w, 4) uint8, первая строка - верх картинки."""
    image = image.convertToFormat(
        enum(QImage, "Format", "Format_RGBA8888"))
    w, h = image.width(), image.height()
    ptr = image.constBits()
    ptr.setsize(image.sizeInBytes())
    rows = np.frombuffer(ptr, dtype=np.uint8).reshape(h,
                                                      image.bytesPerLine())
    return rows[:, :w * 4].reshape(h, w, 4).copy()


def decode_png(data, size=None, crop=None):
    """Байты PNG или JPEG в массив RGBA или None, если картинка
    не читается.

    size - сторона тайла в пикселях. Картинка другого размера, например
    тайл 512 для экранов с высокой плотностью, пересчитывается.
    crop - окно (x0, y0, сторона) в картинке стороной size. Окно
    вырезается и увеличивается со сглаживанием до size.
    Вызывается в рабочем потоке. QImage в рабочем потоке допустим,
    в отличие от QPixmap.
    """
    image = QImage.fromData(data)
    if image.isNull():
        return None
    if size and (image.width() != size or image.height() != size):
        image = image.scaled(
            size, size, enum(Qt, "AspectRatioMode", "IgnoreAspectRatio"),
            enum(Qt, "TransformationMode", "SmoothTransformation"))
    if crop is not None:
        x0, y0, side = crop
        full = size or image.width()
        image = image.copy(x0, y0, side, side).scaled(
            full, full, enum(Qt, "AspectRatioMode", "IgnoreAspectRatio"),
            enum(Qt, "TransformationMode", "SmoothTransformation"))
    return image_to_rgba(image)


class _Decoded(QObject):
    """Живёт в главном потоке. Сигнал из рабочего потока идёт очередью."""

    done = pyqtSignal(object, object, object)


class _DecodeTask(QRunnable):
    """Раскодирование PNG и подготовка тайла в рабочем потоке.

    Задача не трогает сеть и ничего не ждёт от главного потока.
    Предупреждения NumPy здесь гасятся явно. Предупреждение Python
    в рабочем потоке роняет QGIS, см. AGENTS.md.
    """

    def __init__(self, key, data, sink, prepare, size, decode=None,
                 fill=False, crop=None):
        super().__init__()
        self.key = key
        self.data = data
        self.sink = sink
        self.prepare = prepare
        self.size = size
        self.decode = decode
        self.fill = fill  # узнавать заглушку вместо снимка
        self.crop = crop  # окно в картинке предка

    def run(self):
        with np.errstate(all="ignore"):
            extra = None
            if self.decode is not None:
                # Не картинка: ответ разбирает decode(key, байты).
                rgba = self.decode(self.key, self.data)
            else:
                rgba = decode_png(self.data, self.size, self.crop)
                if self.fill and self.crop is None and is_placeholder(rgba):
                    rgba = MISSING
                elif rgba is not None and self.prepare is not None:
                    extra = self.prepare(self.key, rgba)
        self.sink.done.emit(self.key, rgba, extra)


class Throttle:
    """Общий отсчёт запусков для всех загрузчиков и картинок слоёв."""

    moving = False
    last = 0.0

    @classmethod
    def wait(cls, own_last):
        """Секунд до разрешённого запуска, 0 и меньше - можно."""
        now = time.monotonic()
        wait = own_last + START_GAP - now
        if cls.moving:
            wait = max(wait, cls.last + MOVING_GAP - now)
        return wait

    @classmethod
    def started(cls):
        cls.last = time.monotonic()

    @classmethod
    def gap(cls):
        return MOVING_GAP if cls.moving else START_GAP


def set_moving(on):
    """Камера движется: запуски реже. Зовёт вид в каждом кадре."""
    Throttle.moving = bool(on)


class TileLoader(QObject):
    """Загрузка тайлов одного источника.

    source - источник из core/basemap.py, по умолчанию OpenStreetMap.
    want просит тайл с приоритетом, retain снимает всё, что не входит
    в набор нужных. Сигнал loaded несёт ключ, массив RGBA и результат
    prepare(key, rgba), сигнал failed - ключ и текст ошибки. prepare
    выполняется в рабочем потоке и не должна трогать Qt и OpenGL.

    decode(key, байты) заменяет раскодирование PNG, например для
    векторных тайлов. Тогда loaded несёт её результат вместо массива.
    None из decode - ошибка разбора.

    fill=True - снимок вместо заглушки. Тайл-заглушка или ответ с кодом
    из source.missing, обычно 404, заменяется вырезкой из ближайшего
    предка с настоящим снимком,
    см. core/placeholder.py. Байты последних RECENT_TILES тайлов
    хранятся для вырезки, недостающего предка загрузчик просит сам.
    """

    loaded = pyqtSignal(object, object, object)
    failed = pyqtSignal(object, str)
    # Очередь опустела, все ответы разобраны.
    idle = pyqtSignal()

    def __init__(self, source=None, parent=None, prepare=None, size=None,
                 decode=None, fill=False, cache=True):
        super().__init__(parent)
        self.source = source or basemap.osm()
        # False - мимо дискового кэша QGIS, для ответов с no-store.
        self.cache = cache
        self.prepare = prepare
        self.size = size
        self.decode = decode
        self.fill = fill
        self.recent = OrderedDict()  # ключ -> байты настоящего снимка
        self.missing = set()  # тайлы без снимка
        self.orphans = {}  # предок -> тайлы, ждущие вырезки из него
        self.filled = 0  # тайлов, заменённых вырезкой из предка
        self.queue = TileQueue(max_active=self.source.parallel)
        self.replies = {}
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(DECODE_THREADS)
        self.sink = _Decoded(self)
        self.sink.done.connect(self._decoded)
        self.decoding = {}
        self.last_start = 0.0
        self.pump_timer = QTimer(self)
        self.pump_timer.setSingleShot(True)
        self.pump_timer.timeout.connect(self._pump)
        # Сведения для проверочных скриптов.
        self.max_seen = 0
        self.started = []
        self.from_cache = {}
        self.aborted = []
        self.last_user_agent = ""
        install_user_agent()

    def want(self, key, priority=0.0):
        self.queue.want(key, priority, now=time.monotonic())
        self._pump()

    def want_many(self, items):
        """Попросить сразу набор пар ключ и приоритет.

        Запросы уходят после того, как весь набор встал в очередь,
        поэтому первыми уходят старшие по приоритету.
        """
        now = time.monotonic()
        for key, priority in items:
            self.queue.want(key, priority, now=now)
        self._later()

    def retain(self, keys):
        """Снять ожидающие и активные запросы вне набора keys.

        Предок, из которого ждёт вырезки нужный тайл, остаётся.
        """
        keys = set(keys)
        for parent in list(self.orphans):
            self.orphans[parent] &= keys
            if self.orphans[parent]:
                keys.add(parent)
            else:
                del self.orphans[parent]
        for key in self.queue.retain(keys):
            reply = self.replies.pop(key, None)
            if reply is not None:
                reply.finished.disconnect()
                reply.abort()
                reply.deleteLater()
            self.queue.done(key, ok=True)
            self.aborted.append(key)
        self._later()

    def _later(self):
        """Запустить запросы после текущего кадра.

        want_many и retain зовутся из paintGL. Запуск запроса стоит
        главному потоку до нескольких миллисекунд. Между кадрами у него
        есть время простоя, кадр от запуска не удлиняется.

        Таймер Qt на Windows бывает просрочен секундами, пока очередь
        событий занята. Загрузка тогда вставала совсем, 28 сентября
        2026 года. Просроченный дольше STALL таймер не ждётся.
        """
        if not self.pump_timer.isActive():
            self.pump_timer.start(0)
        elif self.pump_timer.remainingTime() == 0 \
                and time.monotonic() - self.last_start > STALL:
            self._pump()

    def pump_if_due(self):
        """Запустить запрос, если он ждёт и общий отсчёт разрешает.

        Зовёт вид после каждого показанного кадра. Пока вид
        перерисовывается подряд, очередь сообщений Windows не пустеет,
        и таймер запуска Qt не срабатывает секундами.
        """
        if self.queue.waiting and Throttle.wait(self.last_start) <= 0.0:
            self._pump()

    def busy(self):
        return len(self.queue) + len(self.decoding)

    def _pump(self):
        """Запустить один запрос, если прошло START_GAP с прошлого.

        Остальные ждут таймера. Так get() главного потока не идут
        пачкой и не съедают кадр.
        """
        wait = Throttle.wait(self.last_start)
        if wait > 0.0:
            if self.queue.waiting and not self.pump_timer.isActive():
                self.pump_timer.start(int(wait * 1000) + 1)
            return
        key = self.queue.next()
        if key is None:
            return
        z, x, y = key
        request = self._request(z, x, y)
        reply = QgsNetworkAccessManager.instance().get(request)
        self.last_start = time.monotonic()
        Throttle.started()
        self.replies[key] = reply
        reply.finished.connect(
            lambda key=key, reply=reply: self._finished(key, reply))
        self.started.append(key)
        self.max_seen = max(self.max_seen, len(self.replies))
        if self.queue.waiting and not self.pump_timer.isActive():
            self.pump_timer.start(int(Throttle.gap() * 1000) + 1)

    def _request(self, z, x, y):
        source = self.source
        request = QNetworkRequest(QUrl(source.tile_url(z, x, y)))
        request.setAttribute(MARK, True)
        request.setAttribute(REDIRECT, SAFE_REDIRECT)
        if self.cache:
            request.setAttribute(CACHE_CONTROL, PREFER_CACHE)
        else:
            request.setAttribute(CACHE_CONTROL, ALWAYS_NETWORK)
            request.setAttribute(CACHE_SAVE, False)
        for name, value in source.headers.items():
            request.setRawHeader(name.encode(), value.encode())
        if source.username:
            pair = "{}:{}".format(source.username, source.password)
            request.setRawHeader(b"Authorization", b"Basic "
                                 + base64.b64encode(pair.encode()))
        if source.authcfg:
            # В PyQGIS запрос возвращается вторым значением.
            result = QgsApplication.authManager().updateNetworkRequest(
                request, source.authcfg)
            if isinstance(result, tuple):
                request = result[1]
        return request

    def _finished(self, key, reply):
        self.replies.pop(key, None)
        self.last_user_agent = bytes(
            reply.request().rawHeader(b"User-Agent")).decode()
        if reply.error() != NO_ERROR:
            if self.fill and reply.attribute(HTTP_STATUS) \
                    in self.source.missing:
                # Тайла нет на сервере: как заглушка, снимок из предка.
                self.queue.done(key, ok=True)
                self._missing(key)
            else:
                self.queue.done(key, ok=False, now=time.monotonic())
                self.failed.emit(key, reply.errorString())
        else:
            self.queue.done(key, ok=True)
            self.from_cache[key] = bool(reply.attribute(FROM_CACHE))
            self.decoding[key] = True
            data = bytes(reply.readAll())
            if self.fill:
                self.recent[key] = data
                self.recent.move_to_end(key)
                while len(self.recent) > RECENT_TILES:
                    self.recent.popitem(last=False)
            self.pool.start(_DecodeTask(key, data, self.sink, self.prepare,
                                        self.size, self.decode,
                                        fill=self.fill))
        reply.deleteLater()
        # Ответ сам запускает следующий запрос, общий отсчёт в _pump
        # держит паузу. Одному таймеру загрузку не доверить, см. _later.
        self._pump()
        self._check_idle()

    def _decoded(self, key, rgba, extra):
        self.decoding.pop(key, None)
        if isinstance(rgba, str) and rgba == MISSING:
            self._missing(key)
        elif rgba is None:
            self.failed.emit(key, "PNG" if self.decode is None else "MVT")
        else:
            self.loaded.emit(key, rgba, extra)
            for child in self.orphans.pop(key, ()):
                self._crop(child, key)
        self._check_idle()

    # Снимок вместо заглушки.

    def _missing(self, key):
        """Снимка у тайла нет. Он и ждущие его тайлы ищут предка выше."""
        self.recent.pop(key, None)
        self.missing.add(key)
        for child in self.orphans.pop(key, set()) | {key}:
            self._fill(child)

    def _fill(self, key):
        """Вырезка для key из ближайшего предка с настоящим снимком.

        Предок из памяти режется сразу, иначе он просится с высшим
        приоритетом, и key ждёт его в orphans.
        """
        for depth in range(1, MAX_FILL_DEPTH + 1):
            parent = ancestor(key, depth)
            if parent[0] < 0:
                break
            if parent in self.missing:
                continue
            if parent in self.recent:
                self._crop(key, parent)
            else:
                self.orphans.setdefault(parent, set()).add(key)
                self.queue.want(parent, FILL_PRIORITY, now=time.monotonic())
                self._later()
            return
        self.failed.emit(key, "no imagery")

    def _crop(self, key, parent):
        """Вырезать и увеличить окно key из картинки предка parent."""
        data = self.recent.get(parent)
        if data is None:
            self._fill(key)
            return
        self.recent.move_to_end(parent)
        crop = crop_window(key, key[0] - parent[0], self.size or 256)
        self.decoding[key] = True
        self.filled += 1
        self.pool.start(_DecodeTask(key, data, self.sink, self.prepare,
                                    self.size, crop=crop))

    def _check_idle(self):
        if not self.busy():
            self.idle.emit()

    def abort(self):
        """Снять всё. Сигналы по снятым запросам не приходят."""
        self.pump_timer.stop()
        self.retain([])
        self.sink.done.disconnect()
        self.pool.clear()
        self.pool.waitForDone(1000)
