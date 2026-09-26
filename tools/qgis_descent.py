# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка шага 0.10: спуск из космоса до улиц Перми без дыр.

Запуск через мост в два вызова, окно глобуса должно быть видно:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_descent.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_descent.py")["report"]()

Камера за DURATION секунд спускается с 20 000 км до 300 м над эспланадой,
расстояние убывает по экспоненте. Потом камера стоит, пока не кончится
загрузка тайлов, но не дольше SETTLE_MAX секунд. Каждый кадр считает
на видеокарте два числа (render/view.py, _count_holes):

- щели - пиксели Земли, не закрытые тайлами, до подстилки
- дыры - пиксели Земли, где не нарисовано ничего, после подстилки

Критерий - 0 дыр на всех кадрах. Щели называются числом. В конце
снимается кадр в обычном режиме, его смотрит человек.
"""
import os
import tempfile
import time

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

ESPLANADE = (58.0105, 56.2294)
START = 2.0e7
FINISH = 300.0
DURATION = 20.0
SETTLE_MAX = 90.0
SHOT = os.path.join(tempfile.gettempdir(), "planetx_descent.png")


class Descent(QObject):

    def __init__(self, view):
        super().__init__(view)
        from planetx.core.navigation import Pose
        self.view = view
        self.pose = Pose(ESPLANADE[0], ESPLANADE[1], START)
        self.t0 = time.perf_counter()
        self.rows = []
        self.phase = "спуск"
        self.settled_at = None
        self.last_frame = self.t0
        self.stalls = []
        view.navigator.stop()
        view.hole_counts = []
        view.hole_check = True
        view.frameSwapped.connect(self._frame)
        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self._watch)
        self.watchdog.start(250)
        self._move(0.0)
        view.update()

    def _move(self, t):
        share = min(1.0, t / DURATION)
        self.pose.distance = START * (FINISH / START) ** share
        self.view.navigator.set_pose(self.pose)

    def _watch(self):
        if self.phase == "готово":
            self.watchdog.stop()
            return
        now = time.perf_counter()
        if now - self.last_frame > 0.5:
            handle = self.view.window().windowHandle()
            self.stalls.append((now - self.t0,
                                bool(handle and handle.isExposed())))
            self.last_frame = now
            self.view.update()

    def _frame(self):
        now = time.perf_counter()
        self.last_frame = now
        t = now - self.t0
        view = self.view
        if view.hole_counts:
            frame, gaps, holes = view.hole_counts[-1]
            levels = view.drawn_levels
            self.rows.append((t, view.altitude(), gaps, holes,
                              max(levels) if levels else 0))
        loader_idle = view.loader.busy() == 0 and not view.pending
        if self.phase == "спуск" and t >= DURATION:
            self.phase = "ожидание"
        if self.phase == "ожидание" and (loader_idle
                                         or t >= DURATION + SETTLE_MAX):
            self.settled_at = t
            self.loaded = loader_idle
            self._finish()
            return
        self._move(t)
        view.update()

    def _finish(self):
        view = self.view
        view.frameSwapped.disconnect(self._frame)
        view.hole_check = False
        self.phase = "готово"
        image = view.grabFramebuffer()
        image.save(SHOT)


def start():
    plugin = qgis.utils.plugins["planetx"]
    if plugin.window is None:
        plugin.run()
    window = plugin.window
    window.showNormal()
    window.raise_()
    window.activateWindow()
    plugin._descent = Descent(window.view)
    print("спуск запущен: %.0f с спуска, потом ожидание загрузки"
          % DURATION)


def report():
    plugin = qgis.utils.plugins["planetx"]
    run = plugin._descent
    view = run.view
    if run.phase != "готово":
        print("идёт: %s, %.1f с, кадров %d, высота %.0f м"
              % (run.phase, time.perf_counter() - run.t0, len(run.rows),
                 view.altitude()))
        return
    rows = np.array(run.rows)
    t, alt, gaps, holes, level = rows.T
    descent = t <= DURATION
    print("кадров: спуск %d, ожидание %d, ожидание кончилось на %.1f с, "
          "загрузка %s" % (descent.sum(), (~descent).sum(), run.settled_at,
                           "кончилась" if run.loaded else "НЕ кончилась"))
    hidden = [s for s, exposed in run.stalls if not exposed]
    if hidden:
        print("ПРОВЕРКА НЕДЕЙСТВИТЕЛЬНА: окно было закрыто %d раз"
              % len(hidden))
    print("ДЫРЫ, пиксели без изображения: наибольшее за кадр %d, кадров "
          "с дырами %d из %d" % (holes.max(), (holes > 0).sum(), len(rows)))
    print("щели под подстилкой: наибольшее за кадр %d, кадров со щелями "
          "%d, медиана по таким кадрам %d"
          % (gaps.max(), (gaps > 0).sum(),
             int(np.median(gaps[gaps > 0])) if (gaps > 0).any() else 0))
    for low, high in ((1e6, 3e7), (1e5, 1e6), (1e4, 1e5), (1e3, 1e4),
                      (0, 1e3)):
        band = (alt >= low) & (alt < high)
        if band.any():
            print("  высота %8.0f-%8.0f м: кадров %4d, щелей наибольшее %5d,"
                  " дыр наибольшее %d, уровни до %d"
                  % (low, high, band.sum(), gaps[band].max(),
                     holes[band].max(), level[band].max()))
    from planetx.core import ellipsoid as el, navigation as nav
    from planetx.core import tiling as tl
    cam = view.camera
    point = nav.ground_under(cam, cam.width / 2, cam.height / 2)
    lat, lon, _ = el.ecef_to_geodetic(point)
    centre = [k for k in view.selection.draw
              if tl.lonlat_to_tile(float(lat), float(lon), k[0]) == k[1:]]
    print("в конце: высота %.0f м, тайл в центре окна %s"
          % (view.altitude(), centre))
    print("снимок:", SHOT)
    print("ошибок OpenGL:", dict(view.gl_errors) or 0)
    errors = getattr(plugin, "_open_errors", None)
    if errors is not None:
        print("ошибок Python с открытия окна: %d, проба дошла: %s"
              % (len(errors), getattr(plugin, "_open_probe", False)))
    return {"holes": int(holes.max()), "gaps": int(gaps.max()),
            "frames": len(rows), "level": int(level.max()),
            "valid": not hidden}
