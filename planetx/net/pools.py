# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Общие пулы рабочих потоков модуля и полосы задач в них.

Прежде загрузчик тайлов, наложение слоёв проекта и подписи слоёв
держали каждый свой QThreadPool дочерним объектом. Снятый загрузчик
удалялся deleteLater, и деструктор пула в главном потоке ждал задачи
без срока. 25 октября 2026 года QGIS 3.36.1 так стоял 115 с: задачи
разбора картинок ждали GIL, два потока в ту же минуту завершались под
блокировкой загрузчика Windows (дамп шага assistant_actions_check).

Теперь пулы общие, живут всё время работы QGIS, их потоки не
завершаются (expiryTimeout -1). У владельца - полоса Lane: задача
полосы, снятой stop(), выходит сразу, главный поток ничего не ждёт.
Снятая полоса с работающими задачами держится здесь, пока пул не
освободится, - так её объекты (приёмник сигнала) не удаляются
из рабочего потока.
"""
from qgis.PyQt.QtCore import QThreadPool, QTimer

# Потоков в пуле: разбор тайлов всех загрузчиков, подготовка картинок
# наложения, чтение подписей слоёв. Прежде у каждого загрузчика было 2,
# у наложения 1, у подписей 1. Подготовка картинки наложения держит
# GIL, ей хватает двух потоков на все наложения. Выбор помощника.
SIZES = {"decode": 6, "prepare": 2, "labels": 1}
SWEEP = 500  # мс между проверками снятых полос

_POOLS = {}
_RETIRED = []
_TIMER = []


def pool(name):
    """Общий пул по имени, заводится при первом обращении."""
    found = _POOLS.get(name)
    if found is None:
        found = QThreadPool()
        found.setMaxThreadCount(SIZES[name])
        found.setExpiryTimeout(-1)
        _POOLS[name] = found
    return found


class Lane:
    """Полоса задач одного владельца в общем пуле. keep - объекты,
    которые нужны задачам до конца (приёмник сигнала)."""

    def __init__(self, name, *keep):
        self.pool = pool(name)
        self.alive = True
        self.keep = keep

    def start(self, task):
        task.lane = self
        self.pool.start(task)

    def stop(self):
        """Задачи полосы больше ничего не делают. Без ожидания."""
        if not self.alive:
            return
        self.alive = False
        if self.pool.activeThreadCount():
            _RETIRED.append(self)
            _sweep_later()


def running(task):
    """Жива ли полоса задачи: зовёт задача в рабочем потоке."""
    lane = getattr(task, "lane", None)
    return lane is None or lane.alive


def _sweep_later():
    if not _TIMER:
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(_sweep)
        _TIMER.append(timer)
    if not _TIMER[0].isActive():
        _TIMER[0].start(SWEEP)


def _sweep():
    """Отпустить снятые полосы, у пулов которых нет работы: при всех
    свободных потоках очереди нет, задач со ссылкой на полосу тоже."""
    _RETIRED[:] = [lane for lane in _RETIRED
                   if lane.pool.activeThreadCount()]
    if _RETIRED:
        _sweep_later()
