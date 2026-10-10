# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Чтение файлов в сети через GDAL (/vsicurl) в рабочих потоках.

Потоки, которые читают сеть через GDAL, живут всё время работы QGIS.
Поток, читавший файлы в сети, при завершении закрывает соединения curl
внутри DllMain под блокировкой загрузчика Windows и ждёт служебные
потоки curl, а им для выхода нужна та же блокировка. 10 октября 2026
года так навсегда повис QGIS автора при загрузке Landsat - дамп
процесса-сторожа показал рабочий поток в curl_multi_cleanup внутри
LdrShutdownThread, потоки curl и новые потоки в ожидании блокировки
загрузчика, главный поток - в старте нового потока. Пулы на каждую
загрузку завершали потоки после каждой сцены, постоянные пулы их не
завершают.
"""
from concurrent.futures import ThreadPoolExecutor

from .loader import USER_AGENT

HTTP_TIMEOUT = 60  # с на запрос GDAL к файлу в сети
HTTP_CONNECT = 15  # с на соединение

_EXECUTORS = {}


def executor(name, workers):
    """Пул рабочих потоков name, один на всё время работы QGIS."""
    pool = _EXECUTORS.get(name)
    if pool is None:
        pool = _EXECUTORS[name] = ThreadPoolExecutor(
            max_workers=workers, thread_name_prefix="planetx-" + name)
    return pool


def thread_gdal():
    """Параметры GDAL рабочего потока: заголовок, без списка папки,
    пределы времени - зависший запрос кончается ошибкой."""
    from osgeo import gdal
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_USERAGENT", USER_AGENT)
    gdal.SetThreadLocalConfigOption("GDAL_DISABLE_READDIR_ON_OPEN",
                                    "EMPTY_DIR")
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_MULTIRANGE", "YES")
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_MAX_RETRY", "2")
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_TIMEOUT", str(HTTP_TIMEOUT))
    gdal.SetThreadLocalConfigOption("GDAL_HTTP_CONNECTTIMEOUT",
                                    str(HTTP_CONNECT))
    return gdal


def close_connections(gdal):
    """Соединения curl закрываются здесь, вне DllMain: при выходе QGIS
    поток завершится без работы curl под блокировкой загрузчика."""
    gdal.VSICurlClearCache()
