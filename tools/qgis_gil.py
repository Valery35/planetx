# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка версии про GIL: хвост отрисовки при занятом потоке Python.

Запуск через мост в два вызова:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_gil.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_gil.py")["report"]()

Камера качается над Пермью, как в qgis_bench.py, но без загрузки:
кадры рисуются по готовым тайлам. Три отрезка по PART секунд:
тихо, с фоновым потоком, который гоняет чистый Python, и снова тихо.
Если хвост участков draw и select растёт только во втором отрезке,
главный поток ждёт GIL.
"""
import math
import statistics
import threading
import time

import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

PART = 8.0
SECTIONS = ("select", "draw")


def _spin(stop):
    """Чистый Python без вызовов C, GIL отпускается только по интервалу."""
    total = 0
    while not stop.is_set():
        for i in range(10000):
            total += i * i
    return total


class GilCheck(QObject):

    def __init__(self, view):
        super().__init__(view)
        from planetx.core.navigation import Pose
        self.Pose = Pose
        self.view = view
        self.rows = {0: [], 1: [], 2: []}
        self.part = 0
        self.t0 = time.monotonic()
        self.stop = threading.Event()
        self.thread = None
        self.done = False
        view.frameSwapped.connect(self._frame)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._move)
        self.timer.start(0)

    def _move(self):
        t = time.monotonic() - self.t0
        part = int(t // PART)
        if part != self.part:
            self.part = part
            if part == 1:
                self.thread = threading.Thread(target=_spin,
                                               args=(self.stop,))
                self.thread.start()
            elif part == 2:
                self.stop.set()
                self.thread.join()
            elif part >= 3:
                self.timer.stop()
                self.view.frameSwapped.disconnect(self._frame)
                self.done = True
                return
        lon = 56.2294 + 0.3 * math.sin(t)
        self.view.navigator.set_pose(self.Pose(58.0105, lon, 30000.0,
                                               0.0, 45.0))
        self.view.update()

    def _frame(self):
        if self.part in self.rows and self.view.sections:
            self.rows[self.part].append(dict(self.view.sections[-1]))


def start():
    plugin = qgis.utils.plugins["planetx"]
    plugin._gil = GilCheck(plugin.window.view)
    print("проверка запущена, %.0f с" % (3 * PART))


def report():
    run = qgis.utils.plugins["planetx"]._gil
    if not run.done:
        print("идёт отрезок %d" % run.part)
        return
    names = ("тихо", "поток Python", "снова тихо")
    for part, rows in run.rows.items():
        line = [names[part], "кадров %d" % len(rows)]
        for name in SECTIONS:
            values = sorted(row[name] for row in rows)
            line.append("%s медиана %.2f, 95%% %.2f, наиб %.2f мс" % (
                name, 1000 * statistics.median(values),
                1000 * values[int(0.95 * len(values))],
                1000 * values[-1]))
        print(" | ".join(line))
