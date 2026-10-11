# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выбор сервера среди зеркал одной службы по их состоянию. Расчёт
без Qt.

Просьба автора от 11 октября 2026 года - «система запросов с разных
адресов, как в nginx, только наоборот». Балансировщик nginx раздаёт
запросы клиентов своим серверам и выводит из списка отказавшие. Здесь
то же делает клиент: запрос идёт на зеркало без отказов с наименьшим
временем ответа, отказавшее зеркало ждёт паузу и возвращается само.

- Быстрый отказ (ответ ошибкой быстрее QUICK) - сервер сломан, пауза
  BROKEN, с каждым отказом подряд вдвое, не больше BROKEN_MAX.
- Медленный отказ (504, обрыв по сроку) - сервер занят, пауза BUSY,
  вдвое, не больше BUSY_MAX.
- Успех снимает паузу и счёт отказов, время ответа сглаживается
  (SMOOTH).
- Между запросами к одному серверу не меньше gap секунд - правило
  вежливости службы.
- Неизвестное время ответа - по порядку в списке, первым идёт главный
  сервер службы.
Величины - выбор помощника, утверждает автор.
"""
QUICK = 2.0  # с, отказ быстрее - сервер сломан
BROKEN = 300.0  # с паузы сломанного сервера
BROKEN_MAX = 3600.0
BUSY = 30.0  # с паузы занятого сервера
BUSY_MAX = 120.0
SMOOTH = 0.3  # доля нового замера в сглаженном времени ответа
UNKNOWN = 1000.0  # с, условное время сервера без ответов, плюс номер


class Mirror:
    """Состояние одного зеркала."""

    def __init__(self, url, rank):
        self.url = url
        self.rank = rank
        self.latency = None
        self.failures = 0
        self.down_until = 0.0
        self.last = -1e9  # момент последнего запроса

    def score(self):
        if self.latency is None:
            return UNKNOWN + self.rank
        return self.latency


class Mirrors:
    """Зеркала одной службы. Время - секунды монотонных часов, его
    передаёт вызывающий."""

    def __init__(self, urls, gap=0.0):
        self.mirrors = [Mirror(url, n) for n, url in enumerate(urls)]
        self.gap = gap

    def _get(self, url):
        return next(m for m in self.mirrors if m.url == url)

    def pick(self, now):
        """(адрес, ожидание в секундах). Ожидание 0 - запрос можно слать
        сразу. Если все зеркала на паузе - то, что вернётся первым."""
        def ready_at(m):
            return max(m.down_until, m.last + self.gap)
        live = [m for m in self.mirrors if m.down_until <= now]
        if live:
            best = min(live, key=lambda m: (m.score(), m.rank))
        else:
            best = min(self.mirrors, key=lambda m: (ready_at(m), m.rank))
        return best.url, max(0.0, ready_at(best) - now)

    def sent(self, url, now):
        mirror = self._get(url)
        mirror.last = now

    def ok(self, url, seconds):
        m = self._get(url)
        m.failures = 0
        m.down_until = 0.0
        m.latency = seconds if m.latency is None \
            else (1.0 - SMOOTH) * m.latency + SMOOTH * seconds

    def failed(self, url, seconds, now):
        """Отказ после seconds секунд ожидания. Возвращает паузу."""
        m = self._get(url)
        m.failures += 1
        if seconds < QUICK:
            pause = min(BROKEN * 2.0 ** (m.failures - 1), BROKEN_MAX)
        else:
            pause = min(BUSY * 2.0 ** (m.failures - 1), BUSY_MAX)
        m.down_until = now + pause
        return pause

    def describe(self, now):
        """Строка состояния зеркал для журнала, без путей адресов."""
        parts = []
        for m in self.mirrors:
            host = m.url.split("//")[-1].split("/")[0]
            state = "ok" if m.down_until <= now else "down {:.0f} s".format(
                m.down_until - now)
            latency = "?" if m.latency is None else "{:.1f} s".format(
                m.latency)
            parts.append("{} {} {}".format(host, state, latency))
        return ", ".join(parts)
