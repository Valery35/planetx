# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Части файла в сети для рабочих потоков - запросом Range через менеджер
сети модуля в главном потоке.

Рабочий поток (чтение COG, core/cog.py) зовёт fetch и ждёт. Запрос ставит
мост в главном потоке сигналом с очередью, ответ будит поток. Так файлы
рельефа идут через прокси и настройки сети QGIS, а не через curl GDAL
с его завершающимися потоками, см. core/cog.py.

Ответ на часть файла в дисковый кэш QGIS не пишется и из него не берётся:
кэш знает адрес без Range и отдал бы чужую часть.
"""
import threading

from qgis.PyQt.QtCore import QObject, QUrl, pyqtSignal
from qgis.PyQt.QtNetwork import QNetworkRequest

from .loader import (ALWAYS_NETWORK, CACHE_CONTROL, CACHE_SAVE, HTTP_STATUS,
                     MARK, NO_ERROR, REDIRECT, SAFE_REDIRECT, network)

TIMEOUT = 60.0  # с ожидания одной части


class Missing(OSError):
    """Файла нет на сервере (404, у Copernicus над морем - 403).
    status - код ответа: у файлов с ключом SAS 403 - истёкший ключ."""

    def __init__(self, text, status=None):
        super().__init__(text)
        self.status = status


class _Bridge(QObject):
    ask = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.ask.connect(self._ask)
        self.replies = set()

    def _ask(self, job):
        request = QNetworkRequest(QUrl(job["url"]))
        request.setAttribute(MARK, True)
        request.setAttribute(REDIRECT, SAFE_REDIRECT)
        request.setAttribute(CACHE_CONTROL, ALWAYS_NETWORK)
        request.setAttribute(CACHE_SAVE, False)
        start, length = job["start"], job["length"]
        request.setRawHeader(b"Range", "bytes={}-{}".format(
            start, start + length - 1).encode("ascii"))
        reply = network().get(request)
        self.replies.add(reply)

        def finished():
            self.replies.discard(reply)
            status = reply.attribute(HTTP_STATUS)
            if reply.error() != NO_ERROR:
                job["status"] = status
                job["error"] = reply.errorString()
            else:
                data = bytes(reply.readAll())
                # Сервер без поддержки Range отдаёт файл целиком.
                job["data"] = data if status == 206 \
                    else data[start:start + length]
            reply.deleteLater()
            job["event"].set()

        reply.finished.connect(finished)


_BRIDGE = []


def bridge():
    """Мост, создаётся в главном потоке до первого запроса из потока."""
    if not _BRIDGE:
        _BRIDGE.append(_Bridge())
    return _BRIDGE[0]


def fetch(url, start, length, timeout=TIMEOUT):
    """Байты start..start+length файла url. Рабочий поток, ждёт ответа.
    Missing - файла нет, OSError - прочие отказы и срок."""
    job = {"url": url, "start": int(start), "length": int(length),
           "event": threading.Event()}
    bridge().ask.emit(job)
    if not job["event"].wait(timeout):
        raise OSError("timeout: " + url)
    if "data" in job:
        return job["data"]
    if job.get("status") in (403, 404):
        raise Missing(job["error"], job["status"])
    raise OSError(job.get("error") or "network")
