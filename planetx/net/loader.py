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
import os
import time
from collections import OrderedDict

import numpy as np
from qgis.core import (QgsApplication, QgsAuthCertUtils,
                       QgsNetworkAccessManager)
from qgis.PyQt.QtCore import (QByteArray, QObject, QRunnable, Qt,
                              QThreadPool, QTimer, QUrl, pyqtSignal)
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtNetwork import (QNetworkAccessManager, QNetworkReply,
                                 QNetworkRequest, QSsl, QSslCertificate)

from ..core import basemap, cadastre, sources
from ..core.placeholder import (MAX_FILL_DEPTH, ancestor, crop_window,
                                is_placeholder)
from ..core.tile_queue import TileQueue
from ..meta import plugin_version
from ..qt_compat import enum, enum_int

TERRARIUM_URL = sources.TERRAIN_URL  # адрес по умолчанию, core/sources.py
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

_manager = None


class _Manager(QgsNetworkAccessManager):
    """Свой менеджер запросов PlanetX в главном потоке.

    QgsNetworkAccessManager заменяет User-Agent любого запроса своим.
    Прежде заголовок PlanetX ставил обработчик setRequestPreprocessor,
    но QGIS зовёт обработчики для каждого запроса любого потока, и
    обработчик на Python тащил GIL в потоки отрисовки QGIS. 10 октября
    2026 года QGIS 3.36 с ним висел на слоях XYZ проекта, см. AGENTS.md.
    Здесь createRequest ставит заголовок, сертификаты QGIS и предел
    ожидания сам и отдаёт запрос Qt мимо обработки QGIS. Прокси
    и общий дисковый кэш - из setupDefaultProxyAndCache, как у
    менеджеров потоков QGIS.
    """

    def createRequest(self, operation, request, data=None):
        request = QNetworkRequest(request)
        request.setRawHeader(b"User-Agent", USER_AGENT.encode())
        if not request.transferTimeout():
            request.setTransferTimeout(QgsNetworkAccessManager.timeout())
        _trusted_cas(request)
        return QNetworkAccessManager.createRequest(self, operation, request,
                                                   data)


def _trusted_cas(request):
    """Сертификаты центров, которым доверяет QGIS, - как в
    QgsNetworkAccessManager::createRequest. К запросам на свои узлы
    (HOST_CAS) добавляются вложенные в модуль сертификаты, только
    к ним и только в запросах PlanetX."""
    if request.url().scheme().lower() != "https":
        return
    config = request.sslConfiguration()
    cas = list(config.caCertificates())
    auth = QgsApplication.authManager()
    if auth is not None and not auth.isDisabled():
        cas = QgsAuthCertUtils.casMerge(auth.trustedCaCertsCache(), cas)
    host = request.url().host().lower()
    for suffix, name in HOST_CAS.items():
        if host == suffix or host.endswith("." + suffix):
            cas = list(cas) + _bundled_ca(name)
    config.setCaCertificates(cas)
    request.setSslConfiguration(config)


# Узел - файл сертификата в planetx/data. Корневой сертификат
# Минцифры для НСПД Росреестра, core/cadastre.py. Решение автора от
# 13 октября 2026 года - сертификат в модуле, в систему и в QGIS он
# не ставится.
HOST_CAS = {cadastre.HOST: cadastre.CA_FILE}
_bundled = {}


def _bundled_ca(name):
    """Сертификаты из файла PEM модуля, читаются один раз."""
    if name not in _bundled:
        path = os.path.join(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))), "data", name)
        try:
            with open(path, "rb") as fh:
                data = fh.read()
        except OSError:
            data = b""
        _bundled[name] = list(QSslCertificate.fromData(
            QByteArray(data), enum(QSsl, "EncodingFormat", "Pem")))
    return _bundled[name]


def _ssl_errors(reply, errors):
    """Ошибки SSL запросов PlanetX - в журнал работы. Решение о запросе
    остаётся за Qt - сертификат без доверия запрос обрывает."""
    from .. import journal
    journal.ssl_errors(reply.url().toString(), errors)


def network():
    """Менеджер запросов PlanetX, один на модуль, в главном потоке."""
    global _manager
    if _manager is None:
        _manager = _Manager()
        # Связь с главным менеджером QGIS (ошибки SSL, пароль прокси) -
        # прямая. По умолчанию она BlockingQueuedConnection, она для
        # менеджеров рабочих потоков. Менеджер в главном потоке ждал бы
        # сам себя, 11 октября 2026 года QGIS 4 так висел на ошибке SSL.
        _manager.setupDefaultProxyAndCache(
            enum(Qt, "ConnectionType", "DirectConnection"))
        _manager.sslErrors.connect(_ssl_errors)
    return _manager


def close_network():
    """Отпустить менеджер. Вызывается при выгрузке плагина."""
    global _manager
    if _manager is not None:
        _manager.deleteLater()
        _manager = None

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
    if not data:
        # Ответ 204 без тела - тайла нет, он прозрачный. Так отвечает
        # мозаика Planetary Computer над морем (карта WorldCover).
        side = size or 256
        return np.zeros((side, side, 4), np.uint8)
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
                 fill=False, crop=None, assemble=None):
        super().__init__()
        self.key = key
        self.data = data
        self.sink = sink
        self.prepare = prepare
        self.size = size
        self.decode = decode
        self.fill = fill  # узнавать заглушку вместо снимка
        self.crop = crop  # окно в картинке предка
        # Тайл из частей (Source.parts): data - список байтов частей,
        # assemble(картинки) собирает из них тайл.
        self.assemble = assemble

    def run(self):
        with np.errstate(all="ignore"):
            extra = None
            if self.assemble is not None:
                images = [decode_png(d) for d in self.data]
                rgba = None if any(i is None for i in images) \
                    else self.assemble(images)
                if rgba is not None and self.prepare is not None:
                    extra = self.prepare(self.key, rgba)
            elif self.decode is not None:
                # Не картинка: ответ разбирает decode(key, байты).
                rgba = self.decode(self.key, self.data)
            else:
                rgba = decode_png(self.data, self.size, self.crop)
                if self.fill and self.crop is None and is_placeholder(rgba):
                    rgba = MISSING
                elif rgba is not None and self.prepare is not None:
                    extra = self.prepare(self.key, rgba)
        self.sink.done.emit(self.key, rgba, extra)


class _Parts:
    """Запросы частей одного тайла (Source.parts) и пришедшие байты."""

    def __init__(self, count):
        self.replies = []  # ждущие ответа, пришедшие отсюда убираются
        self.data = [None] * count

    def cancel(self):
        """Снять ждущие запросы частей, сигналы по ним не приходят."""
        for reply in self.replies:
            reply.finished.disconnect()
            reply.abort()
            reply.deleteLater()
        self.replies = []


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
        self.stopped = False
        # Сведения для проверочных скриптов.
        self.max_seen = 0
        self.started = []
        self.from_cache = {}
        self.aborted = []
        self.last_user_agent = ""

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
            if isinstance(reply, _Parts):
                reply.cancel()
            elif reply is not None:
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
        if self.source.gap:
            # Своя пауза источника: служба кадастра отвечает отказом
            # на частые запросы подряд, core/cadastre.py.
            wait = max(wait, self.last_start + self.source.gap
                       - time.monotonic())
        if wait > 0.0:
            if self.queue.waiting and not self.pump_timer.isActive():
                self.pump_timer.start(int(wait * 1000) + 1)
            return
        key = self.queue.next()
        if key is None:
            return
        z, x, y = key
        parts = self.source.parts(z, x, y)
        if parts:
            group = _Parts(len(parts))
            for n, url in enumerate(parts):
                reply = network().get(self._request_url(url))
                group.replies.append(reply)
                reply.finished.connect(
                    lambda key=key, group=group, n=n, reply=reply:
                    self._part(key, group, n, reply))
            self.replies[key] = group
        else:
            reply = network().get(self._request(z, x, y))
            self.replies[key] = reply
            reply.finished.connect(
                lambda key=key, reply=reply: self._finished(key, reply))
        self.last_start = time.monotonic()
        Throttle.started()
        self.started.append(key)
        self.max_seen = max(self.max_seen, len(self.replies))
        if self.queue.waiting and not self.pump_timer.isActive():
            self.pump_timer.start(int(Throttle.gap() * 1000) + 1)

    def _request(self, z, x, y):
        return self._request_url(self.source.tile_url(z, x, y))

    def _request_url(self, url):
        source = self.source
        request = QNetworkRequest(QUrl(url))
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
                now = time.monotonic()
                self.queue.done(key, ok=False, now=now)
                status = reply.attribute(HTTP_STATUS)
                # Отказ сервера, а не «тайла нет» - на зеркало, если есть.
                if status not in (400, 401, 403, 404, 410) \
                        and self.source.next_mirror(now):
                    from .. import journal
                    journal.note("tiles {}: mirror {}".format(
                        self.source.name, self.source.mirror))
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

    def _part(self, key, group, n, reply):
        """Пришла часть тайла из нескольких картинок (Source.parts).
        Тайл раскодируется, когда пришли все части. Отказ любой части -
        отказ тайла, вырезки из предка у таких источников нет."""
        if reply in group.replies:
            group.replies.remove(reply)
        if self.replies.get(key) is not group:
            reply.deleteLater()
            return
        if reply.error() != NO_ERROR:
            self.replies.pop(key, None)
            group.cancel()
            self.queue.done(key, ok=False, now=time.monotonic())
            self.failed.emit(key, reply.errorString())
            reply.deleteLater()
        else:
            group.data[n] = bytes(reply.readAll())
            reply.deleteLater()
            if all(d is not None for d in group.data):
                self.replies.pop(key, None)
                self.queue.done(key, ok=True)
                self.decoding[key] = True
                z, x, y = key
                self.pool.start(_DecodeTask(
                    key, list(group.data), self.sink, self.prepare,
                    self.size, assemble=lambda images, s=self.source,
                    z=z, x=x, y=y: s.assemble(z, x, y, images)))
        self._pump()
        self._check_idle()

    def _decoded(self, key, rgba, extra):
        if self.stopped:
            # Ответ рабочего потока, поставленный в очередь до abort:
            # снятие связи его не отменяет. Без этого тайл прежней
            # подложки приходил новой - карта возраста 0 вставала
            # на место возраста 100, 5 октября 2026 года.
            return
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
        """Снять всё. Сигналы по снятым запросам не приходят. Повторный
        вызов ничего не делает: связь sink.done уже снята."""
        if self.stopped:
            return
        self.stopped = True
        self.pump_timer.stop()
        self.retain([])
        self.sink.done.disconnect()
        self.pool.clear()
        self.pool.waitForDone(1000)
