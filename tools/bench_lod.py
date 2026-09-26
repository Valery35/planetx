# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Стенд скорости выбора тайлов без QGIS.

    $PY tools/bench_lod.py

Виды камеры те же, что в тестах, плюс наклонный вид над рельефом,
как у Перми с 25 км при наклоне 55°. Рельеф синтетический: слой высот
до 3 км толщиной в пятую часть ширины тайла. Кэш границ тайлов
прогрет, как во втором и следующих кадрах. Печатает время одного
выбора в миллисекундах, медиану по повторам, и количество узлов.
"""
import math
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "planetx", "core"))

import camera as cm  # noqa: E402
import lod  # noqa: E402

PERM = (58.0105, 56.2294)
SIZE = dict(width=3200, height=1800)
REPEAT = 15


def layer(key):
    width = 40075016.0 * math.cos(math.radians(58.0)) / (1 << key[0])
    thickness = min(3000.0, 0.2 * width)
    return (500.0, 500.0 + thickness)


def half_ready(key):
    return key[0] <= 2 or hash(key) % 2 == 0


CASES = (
    ("космос", cm.Camera.look_at(*PERM, 2.0e7, **SIZE), None),
    ("2000 км", cm.Camera.look_at(*PERM, 2.0e6, **SIZE), None),
    ("2 км, наклон 70°", cm.Camera.look_at(*PERM, 2000.0, heading=30.0,
                                          tilt=70.0, **SIZE), None),
    ("25 км, наклон 55°, рельеф",
     cm.Camera.look_at(*PERM, 25000.0, heading=20.0, tilt=55.0, h=500.0,
                       **SIZE), layer),
    ("400 м, наклон 80°, рельеф",
     cm.Camera.look_at(*PERM, 400.0, tilt=80.0, h=500.0, **SIZE), layer),
)


def run():
    for name, cam, heights in CASES:
        for label, ready in (("всё готово", lambda k: True),
                             ("половина", half_ready)):
            lod.select(cam, ready, heights=heights)
            times = []
            for _ in range(REPEAT):
                started = time.perf_counter()
                sel = lod.select(cam, ready, heights=heights)
                times.append(time.perf_counter() - started)
            print("%-28s %-11s %6.2f мс, узлов %4d, в кадре %4d"
                  % (name, label, 1000 * statistics.median(times),
                     sel.visited, len(sel.draw)))


if __name__ == "__main__":
    run()
