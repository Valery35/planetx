# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Очередь загрузки тайлов: приоритет, отмена, предел запросов.

Очередь не знает про сеть. Она решает, какой тайл просить следующим
и какие запросы снять. Сетью занимается net/loader.py.

Приоритет - число, больший приоритет уходит раньше. Для подложки это
экранная ошибка тайла. При равном приоритете раньше уходит тайл,
который попросили раньше.
"""
from itertools import count

RETRY_AFTER = 30.0  # секунд до повторного запроса после ошибки


class TileQueue:
    """Ожидающие и активные запросы одного источника."""

    def __init__(self, max_active=2, retry_after=RETRY_AFTER):
        self.max_active = max_active
        self.retry_after = retry_after
        self.waiting = {}  # ключ -> (приоритет, порядковый номер)
        self.active = set()
        self.failed_at = {}
        self._order = count()

    def want(self, key, priority, now=0.0):
        """Попросить тайл или поднять его приоритет.

        Активный тайл не трогается. Тайл, запрос которого недавно
        кончился ошибкой, не просится до истечения паузы.
        """
        if key in self.active:
            return False
        failed = self.failed_at.get(key)
        if failed is not None and now - failed < self.retry_after:
            return False
        old = self.waiting.get(key)
        order = old[1] if old is not None else next(self._order)
        self.waiting[key] = (priority, order)
        return True

    def retain(self, keys):
        """Оставить только нужные тайлы.

        Ожидающие тайлы вне набора убираются. Возвращает активные тайлы
        вне набора, их запросы надо снять и потом вызвать done.
        """
        keys = set(keys)
        for key in [k for k in self.waiting if k not in keys]:
            del self.waiting[key]
        return sorted(k for k in self.active if k not in keys)

    def next(self):
        """Следующий тайл для запроса или None, если предел исчерпан."""
        if len(self.active) >= self.max_active or not self.waiting:
            return None
        key = max(self.waiting,
                  key=lambda k: (self.waiting[k][0], -self.waiting[k][1]))
        del self.waiting[key]
        self.active.add(key)
        return key

    def done(self, key, ok=True, now=0.0):
        """Запрос кончился. При ошибке тайл уходит на паузу."""
        self.active.discard(key)
        if ok:
            self.failed_at.pop(key, None)
        else:
            self.failed_at[key] = now

    def __len__(self):
        return len(self.waiting) + len(self.active)
