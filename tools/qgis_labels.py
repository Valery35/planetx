# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Замер: цена надписей пунктов при повороте над Пермью.

Запуск через мост в два вызова, окно глобуса открыто и видно:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_labels.py")["start"](
        places=True)
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_labels.py")["report"]()

Камера висит в 60 км от Перми с наклоном 55° и качается по азимуту
на ±40° с периодом 5 с. Первые WARMUP секунд грузятся тайлы и не
считаются, следующие MEASURE секунд меряются. Отчёт: время отбора
и отрисовки надписей, 95-й процентиль paintGL, наименьшее количество
кадров в окне 1 с, количество надписей.
"""
import builtins
import math
import time

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import QTimer

PERM = (58.0, 56.23)
DISTANCE = 60000.0
TILT = 55.0
SWING = 40.0
PERIOD = 5.0
WARMUP = 8.0
MEASURE = 10.0


def start(places=True):
    from planetx.core.navigation import Pose
    window = qgis.utils.plugins["planetx"].window
    window.showNormal()
    window.raise_()
    window.activateWindow()
    view = window.view
    store = view.store
    saved = set(view.label_kinds)
    view.label_kinds = saved if places else set()
    labels = view.labels
    state = {"label": [], "swaps": [], "counts": [], "done": False,
             "places": places}
    builtins.planetx_labels = state
    original = labels.draw
    started = time.monotonic()

    def timed(*args, **kwargs):
        t = time.perf_counter()
        count = original(*args, **kwargs)
        if time.monotonic() - started > WARMUP:
            state["label"].append(time.perf_counter() - t)
            state["counts"].append(count)
        return count

    labels.draw = timed

    def swapped():
        if time.monotonic() - started > WARMUP:
            state["swaps"].append(time.perf_counter())

    view.frameSwapped.connect(swapped)
    height = store.height_at(*PERM)

    def step():
        t = time.monotonic() - started
        if t > WARMUP + MEASURE:
            timer.stop()
            view.frameSwapped.disconnect(swapped)
            del labels.draw
            view.label_kinds = saved
            state["paint"] = list(view.frame_times)
            state["done"] = True
            return
        heading = SWING * math.sin(t * 2.0 * math.pi / PERIOD)
        view.navigator.set_pose(Pose(PERM[0], PERM[1], DISTANCE, heading,
                                     TILT, height, store.height_at))
        view.update()

    timer = QTimer(window)
    timer.timeout.connect(step)
    timer.start(5)
    state["timer"] = timer


def report():
    state = builtins.planetx_labels
    if not state["done"]:
        print("замер ещё идёт")
        return
    swaps = np.array(state["swaps"])
    worst = min(((swaps >= t) & (swaps < t + 1.0)).sum()
                for t in np.arange(swaps[0], swaps[-1] - 1.0, 0.05))
    paint = np.array(state["paint"]) * 1000.0
    print("надписи:", "да" if state["places"] else "нет")
    print("кадров за замер:", len(swaps))
    print("худшая секунда, кадров:", worst)
    print("paintGL, мс: медиана %.2f, 95%% %.2f" % (
        np.median(paint), np.percentile(paint, 95)))
    if state["label"]:
        label = np.array(state["label"]) * 1000.0
        print("надписи, мс: медиана %.2f, 95%% %.2f" % (
            np.median(label), np.percentile(label, 95)))
        print("надписей в кадре: медиана %d" % np.median(state["counts"]))
