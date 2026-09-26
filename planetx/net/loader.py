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
import configparser
import os
import time

import numpy as np
from qgis.core import QgsNetworkAccessManager
from qgis.PyQt.QtCore import (QObject, QRunnable, QThreadPool, QTimer,
                              QUrl, pyqtSignal)
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtNetwork import QNetworkReply, QNetworkRequest

from ..core.tile_queue import TileQueue
from ..qt_compat import enum, enum_int

OSM_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
MAX_PARALLEL = 2
DECODE_THREADS = 2
START_GAP = 0.015  # секунд между запусками запросов, около кадра
# Метка запросов PlanetX, пользовательский атрибут запроса Qt.
MARK = QNetworkRequest.Attribute(
    enum_int(enum(QNetworkRequest, "Attribute", "User")) + 71)
FROM_CACHE = enum(QNetworkRequest, "Attribute", "SourceIsFromCacheAttribute")
CACHE_CONTROL = enum(QNetworkRequest, "Attribute",
                     "CacheLoadControlAttribute")
PREFER_CACHE = enum(QNetworkRequest, "CacheLoadControl", "PreferCache")
NO_ERROR = enum(QNetworkReply, "NetworkError", "NoError")


def plugin_version():
    meta = configparser.ConfigParser()
    meta.read(os.path.join(os.path.dirname(os.path.dirname(__file__)),
                           "metadata.txt"), encoding="utf-8")
    return meta.get("general", "version", fallback="0")


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


def decode_png(data):
    """Байты PNG в массив RGBA или None, если картинка не читается.

    Вызывается в рабочем потоке. QImage в рабочем потоке допустим,
    в отличие от QPixmap.
    """
    image = QImage.fromData(data)
    if image.isNull():
        return None
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

    def __init__(self, key, data, sink, prepare):
        super().__init__()
        self.key = key
        self.data = data
        self.sink = sink
        self.prepare = prepare

    def run(self):
        with np.errstate(all="ignore"):
            rgba = decode_png(self.data)
            extra = None
            if rgba is not None and self.prepare is not None:
                extra = self.prepare(self.key, rgba)
        self.sink.done.emit(self.key, rgba, extra)


class TileLoader(QObject):
    """Загрузка тайлов одного источника.

    want просит тайл с приоритетом, retain снимает всё, что не входит
    в набор нужных. Сигнал loaded несёт ключ, массив RGBA и результат
    prepare(key, rgba), сигнал failed - ключ и текст ошибки. prepare
    выполняется в рабочем потоке и не должна трогать Qt и OpenGL.
    """

    loaded = pyqtSignal(object, object, object)
    failed = pyqtSignal(object, str)
    # Очередь опустела, все ответы разобраны.
    idle = pyqtSignal()

    def __init__(self, url=OSM_URL, max_parallel=MAX_PARALLEL, parent=None,
                 prepare=None):
        super().__init__(parent)
        self.url = url
        self.prepare = prepare
        self.queue = TileQueue(max_active=max_parallel)
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
        self._pump()

    def retain(self, keys):
        """Снять ожидающие и активные запросы вне набора keys."""
        for key in self.queue.retain(keys):
            reply = self.replies.pop(key, None)
            if reply is not None:
                reply.finished.disconnect()
                reply.abort()
                reply.deleteLater()
            self.queue.done(key, ok=True)
            self.aborted.append(key)
        self._pump()

    def busy(self):
        return len(self.queue) + len(self.decoding)

    def _pump(self):
        """Запустить один запрос, если прошло START_GAP с прошлого.

        Остальные ждут таймера. Так get() главного потока не идут
        пачкой и не съедают кадр.
        """
        wait = self.last_start + START_GAP - time.monotonic()
        if wait > 0.0:
            if self.queue.waiting and not self.pump_timer.isActive():
                self.pump_timer.start(int(wait * 1000) + 1)
            return
        key = self.queue.next()
        if key is None:
            return
        z, x, y = key
        request = QNetworkRequest(QUrl(self.url.format(z=z, x=x, y=y)))
        request.setAttribute(MARK, True)
        request.setAttribute(CACHE_CONTROL, PREFER_CACHE)
        reply = QgsNetworkAccessManager.instance().get(request)
        self.last_start = time.monotonic()
        self.replies[key] = reply
        reply.finished.connect(
            lambda key=key, reply=reply: self._finished(key, reply))
        self.started.append(key)
        self.max_seen = max(self.max_seen, len(self.replies))
        if self.queue.waiting and not self.pump_timer.isActive():
            self.pump_timer.start(int(START_GAP * 1000) + 1)

    def _finished(self, key, reply):
        self.replies.pop(key, None)
        self.last_user_agent = bytes(
            reply.request().rawHeader(b"User-Agent")).decode()
        if reply.error() != NO_ERROR:
            self.queue.done(key, ok=False, now=time.monotonic())
            self.failed.emit(key, reply.errorString())
        else:
            self.queue.done(key, ok=True)
            self.from_cache[key] = bool(reply.attribute(FROM_CACHE))
            self.decoding[key] = True
            self.pool.start(_DecodeTask(key, bytes(reply.readAll()),
                                        self.sink, self.prepare))
        reply.deleteLater()
        self._pump()
        self._check_idle()

    def _decoded(self, key, rgba, extra):
        self.decoding.pop(key, None)
        if rgba is None:
            self.failed.emit(key, "PNG")
        else:
            self.loaded.emit(key, rgba, extra)
        self._check_idle()

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
