# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Замер поворота глобуса со своими объектами. Запускается при старте
QGIS в отдельном профиле.

    qgis.bat --profiles-path %TEMP%\\planetx_stress --code
        tools\\qgis_turn.py

Файл KML или KMZ из PLANETX_KMZ открывается в «Мои метки», камера
встаёт над ним и поворачивается по таймеру TURN секунд. Пишутся
промежутки между кадрами и вызовы дольше SLOW: сборка и отрисовка
своих объектов, кадр. Итог в %TEMP%\\planetx_turn.json. В конце
открытая папка удаляется.
"""
import functools
import json
import os
import sys
import time

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
TEMP = os.environ.get("TEMP", ".")
OUT = os.path.join(TEMP, "planetx_turn.json")
SLOW = 0.005
GAP = 0.040
TURN = 12.0

from qgis.core import QgsApplication, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

calls = []
frames = []
state = {}

FRAME_BUDGET = 55  # кадров в любом окне 1 с, критерий AGENTS.md


def worst_second(frames):
    """Наименьшее количество кадров в окне 1 с, окно от каждого кадра."""
    worst = None
    j = 0
    for i, start in enumerate(frames):
        while j < len(frames) and frames[j] < start + 1.0:
            j += 1
        if frames[-1] - start >= 1.0:
            count = j - i
            worst = count if worst is None else min(worst, count)
    return worst



def timed(owner, name, label):
    original = getattr(owner, name)

    @functools.wraps(original)
    def wrapper(*args, **kwargs):
        started = time.perf_counter()
        try:
            return original(*args, **kwargs)
        finally:
            spent = time.perf_counter() - started
            if spent > SLOW:
                calls.append((started, round(spent * 1000, 1), label))
    setattr(owner, name, wrapper)


def start():
    from planetx.render import features, view
    for cls, names in ((features.Features, ("_update", "draw")),
                       (view.GlobeView, ("_render",))):
        for name in names:
            timed(cls, name, "%s.%s" % (cls.__name__, name))
    from planetx.plugin import PlanetXPlugin
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    state["plugin"] = plugin
    window = plugin.window
    window.showNormal()
    view = window.view
    view.changed.connect(lambda: frames.append(time.perf_counter()))
    path = os.environ.get("PLANETX_KMZ")
    if path:
        state["key"] = window.import_kml(None, path)
    else:
        # Сравнение без своих объектов: камера над Афганистаном.
        from planetx.core.navigation import Pose
        window.view.navigator.set_pose(Pose(33.9, 66.0, 1.5e6))
    shapes = window.myplaces.shapes()
    state["vertices"] = sum(len(s.points) for s in shapes)
    state["shapes"] = len(shapes)
    QTimer.singleShot(8000, guarded(turn))


def turn():
    window = state["plugin"].window
    nav = window.view.navigator
    if state.get("key"):
        # Цена флажка: файл перечитывается, объекты создаются заново.
        store = window.myplaces
        place = store.places_in(state["key"])[0]
        started = time.perf_counter()
        store.set_visible(place.key, False)
        window.view.repaint()
        store.set_visible(place.key, True)
        window.view.repaint()
        state["toggle_ms"] = round((time.perf_counter() - started) * 500, 1)
    state["t0"] = time.perf_counter()
    # Как поворот средней кнопкой: вид считает камеру движущейся.
    window.view.turning = (0.0, 0.0)
    timer = QTimer()
    state["timer"] = timer

    def step():
        nav.turn(0.6, 0.0)
        window.view.update()
        if time.perf_counter() - state["t0"] > TURN:
            timer.stop()
            window.view.turning = None
            guarded(finish)()
    timer.timeout.connect(step)
    timer.start(16)


def finish():
    t0 = state["t0"]
    ft = [f for f in frames if f >= t0]
    intervals = sorted(b - a for a, b in zip(ft, ft[1:]))
    totals = {}
    for s, ms, label in calls:
        if s >= t0:
            total, count, worst = totals.get(label, (0.0, 0, 0.0))
            totals[label] = (round(total + ms, 1), count + 1,
                             max(worst, ms))
    view = state["plugin"].window.view
    result = {
        "shapes": state["shapes"], "vertices": state["vertices"],
        "toggle_ms": state.get("toggle_ms"),
        "built_vertices": sum(len(item.index.get("lines", (0, 0)))
                              and item.index["lines"][1] // 2
                              for item in view.features.buffers if item),
        "frames": len(ft),
        "fps": round(len(ft) / TURN, 1),
        "median_ms": round(1000 * intervals[len(intervals) // 2], 1)
        if intervals else None,
        "p95_ms": round(1000 * intervals[int(len(intervals) * 0.95)], 1)
        if intervals else None,
        "gaps": sum(1 for x in intervals if x > GAP),
        "worst_second": worst_second(ft),
        "budget": "пройден" if (worst_second(ft) or 0) >= FRAME_BUDGET
        else "нарушен",
        "calls": totals}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    window = state["plugin"].window
    if state.get("key"):
        window.myplaces.remove(state["key"])
    state["plugin"].unload()
    QgsProject.instance().clear()
    QgsApplication.instance().exit(0)


def guarded(function):
    """Ошибка шага пишется в итог, QGIS закрывается, окно ошибки
    не ждёт человека."""
    def run():
        try:
            function()
        except (AttributeError, KeyError, NameError, OSError, TypeError,
                ValueError, ImportError):
            import traceback
            with open(OUT, "w", encoding="utf-8") as fh:
                json.dump({"error": traceback.format_exc()}, fh,
                          ensure_ascii=False)
            QgsProject.instance().clear()
            QgsApplication.instance().exit(1)
    return run


QTimer.singleShot(3000, guarded(start))
