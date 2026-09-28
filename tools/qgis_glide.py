# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Замер пауз при проезде тура вдоль пути. Запускается при старте QGIS.

    qgis.bat --profiles-path %TEMP%\\planetx_stress --code
        tools\\qgis_glide.py

Путь 40 км над местом PLACE, тайлов там нет в кэше профиля. Место
задаётся переменной PLANETX_GLIDE="широта,долгота", иначе Казань. Во время
проезда пишутся моменты кадров и вызовы главного потока дольше
SLOW секунд: загрузчики тайлов, картинки слоёв, кадр, сборка сеток.
Паузы - промежутки между кадрами дольше GAP. Итог в
%TEMP%\\planetx_glide.json. QGIS пользователя не трогается.
"""
import functools
import json
import os
import sys
import time

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
TEMP = os.environ.get("TEMP", ".")
OUT = os.path.join(TEMP, "planetx_glide.json")
SLOW = 0.005
GAP = 0.040
RUN = 45.0

from qgis.core import QgsApplication, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

calls = []

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

frames = []
slow_frames = []  # участки медленных кадров
result_info = {}
state = {}


def timed(owner, name, label):
    """Обернуть метод owner.name: вызовы дольше SLOW идут в calls."""
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


def instrument():
    from planetx.net import loader, overlay
    from planetx.render import view, labels
    from planetx.ui import window
    for cls, names in (
            (loader.TileLoader, ("_pump", "_finished", "_decoded",
                                 "want_many", "retain", "_fill")),
            (overlay.LayerOverlay, ("_pump", "_finished", "_prepared",
                                    "want_many", "retain")),
            (view.GlobeView, ("_render", "_built", "add_image",
                              "add_heights", "add_places",
                              "add_overlay")),
            (labels.Labels, ("draw",)),
            (window.GlobeWindow, ("_show_state",))):
        for name in names:
            if hasattr(cls, name):
                timed(cls, name, "%s.%s" % (cls.__name__, name))


def start():
    instrument()
    from planetx.plugin import PlanetXPlugin
    from planetx.core.navigation import Pose
    from planetx.core.tour import PathStop
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    state["plugin"] = plugin
    window = plugin.window
    window.showNormal()
    view = window.view
    if os.environ.get("PLANETX_OLD"):
        # Сравнение с прежним поведением: загрузчики без общего отсчёта,
        # в движении кадр грузит столько же текстур, сколько в покое.
        view.on_motion = None
        upload, overlays = view._upload, view._upload_overlays
        view._upload = lambda budget, *a: upload(max(budget, 3))
        view._upload_overlays = lambda *a: overlays()

    if os.environ.get("PLANETX_NOAIR"):
        view.atmosphere = False  # сравнение: без неба и дымки
    result_info["size"] = [view.camera.width, view.camera.height]

    def frame():
        frames.append(time.perf_counter())
        a, b = view.paint_span
        if b - a > 0.015 and view.sections:
            slow_frames.append({k: round(v * 1000, 1) if isinstance(
                v, float) else v for k, v in view.sections[-1].items()})
    view.changed.connect(frame)
    nav = view.navigator
    nav.stop()
    lat, lon = (float(v) for v in os.environ.get(
        "PLANETX_GLIDE", "55.70,49.00").split(","))
    nav.set_pose(Pose(lat + 0.09, lon + 0.12, 40000.0))

    def go():
        path = PathStop("Путь", [(lat, lon), (lat + 0.18, lon),
                                 (lat + 0.18, lon + 0.32)])
        window.tour.start([path])
        state["t0"] = time.perf_counter()
        state["glide_from"] = window.tour.tour.glides[0]
        state["glide_to"] = window.tour.tour.arrivals[0]
        QTimer.singleShot(int(RUN * 1000), finish)
    QTimer.singleShot(6000, go)


def finish():
    t0 = state["t0"]
    glide_start = t0 + state["glide_from"]
    # Только сам проезд: после него кадры идут лишь по приходу тайлов.
    glide_end = t0 + state["glide_to"]
    ft = [f for f in frames if glide_start <= f <= glide_end]
    gaps = []
    for a, b in zip(ft, ft[1:]):
        if b - a > GAP:
            inside = [(round((s - t0) * 1000), ms, label)
                      for s, ms, label in calls if a <= s < b]
            gaps.append({"at_ms": round((a - t0) * 1000),
                         "gap_ms": round((b - a) * 1000, 1),
                         "calls": inside})
    totals = {}
    for s, ms, label in calls:
        if glide_start <= s <= glide_end:
            total, count, worst = totals.get(label, (0.0, 0, 0.0))
            totals[label] = (round(total + ms, 1), count + 1,
                             max(worst, ms))
    intervals = sorted(b - a for a, b in zip(ft, ft[1:]))
    result = {
        "glide_s": round(glide_end - glide_start, 1),
        "info": result_info,
        "frames": len(ft),
        "worst_second": worst_second(ft),
        "budget": "пройден" if (worst_second(ft) or 0) >= FRAME_BUDGET
        else "нарушен",
        "median_ms": round(1000 * intervals[len(intervals) // 2], 1)
        if intervals else None,
        "p95_ms": round(1000 * intervals[int(len(intervals) * 0.95)], 1)
        if intervals else None,
        "gaps": len(gaps), "worst": sorted(
            gaps, key=lambda g: -g["gap_ms"])[:15],
        "slow_calls": totals,
        "slow_frames": sorted(slow_frames, key=lambda s: -sum(
            s.get(k, 0) for k in ("upload", "terrain", "select", "heights",
                                  "loader", "draw", "evict")))[:12]}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    state["plugin"].unload()
    QgsProject.instance().clear()
    QgsApplication.instance().exit(0)


QTimer.singleShot(3000, start)
