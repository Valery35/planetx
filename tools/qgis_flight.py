# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка шага 0.11: перелёт к введённым координатам.

Запуск через мост в два вызова, окно глобуса должно быть видно:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_flight.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_flight.py")["report"]()

Камера ставится над Москвой на 3 км. В поле координат вводится
эспланада Перми, дальше вызывается то же, что по Enter. Каждый кадр
записываются поза и время шага навигатора. По ним считается скорость
в метрике статьи van Wijk и Nuij, ds² = (ρ²·du² + dw²/ρ²) / w².
Критерий - отклонение скорости от средней не больше 5 %. Рядом
печатаются частота кадров и дыры за перелёт.
"""
import math
import time

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import QObject

MOSCOW = (55.7558, 37.6173)
TARGET = "58.0105, 56.2294"
LIMIT = 0.05


class Watch(QObject):

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.rows = []
        self.swaps = []
        self.before = []
        self.after = []
        self.flight = None
        self.done = False
        self.last_frame = None
        self.view.hole_counts = []
        self.view.hole_check = True
        self.view.frameSwapped.connect(self._frame)

    def _frame(self):
        view = self.view
        nav = view.navigator
        # frameSwapped приходит и тогда, когда Qt пересобирает окно без
        # нового paintGL, например после обновления строки состояния.
        # Такие сигналы повторяют прошлый кадр и не считаются.
        if view.frame == self.last_frame:
            return
        self.last_frame = view.frame
        now = time.perf_counter()
        span = getattr(view, "paint_span", None)
        if span is not None and self.swaps:
            self.before.append(span[0] - self.swaps[-1])
            self.after.append(now - span[1])
        self.swaps.append(now)
        if nav.flight is not None:
            self.flight = nav.flight
        if self.flight is None:
            return
        pose = nav.pose
        holes = view.hole_counts[-1][2] if view.hole_counts else 0
        self.rows.append((view.step_time - self.flight[0], pose.lat,
                          pose.lon, pose.distance, holes))
        if nav.flight is None:
            self.done = True
            view.hole_check = False
            view.frameSwapped.disconnect(self._frame)


def start():
    from planetx.core.navigation import Pose
    plugin = qgis.utils.plugins["planetx"]
    if plugin.window is None:
        plugin.run()
    window = plugin.window
    window.showNormal()
    window.raise_()
    window.activateWindow()
    window.view.navigator.set_pose(Pose(MOSCOW[0], MOSCOW[1], 3000.0))
    plugin._flight_watch = Watch(window)
    window.place.setText(TARGET)
    window.fly()
    flight = window.view.navigator.flight[1]
    print("перелёт запущен: длина пути S = %.2f, время %.2f с"
          % (flight.path.length, flight.duration))


def _unit(lat, lon):
    la, lo = np.radians(lat), np.radians(lon)
    return np.stack([np.cos(la) * np.cos(lo), np.cos(la) * np.sin(lo),
                     np.sin(la)], axis=-1)


def report():
    from planetx.core.flight import RHO
    from planetx.core.ellipsoid import A
    plugin = qgis.utils.plugins["planetx"]
    watch = plugin._flight_watch
    if not watch.done:
        print("перелёт идёт, кадров %d" % len(watch.rows))
        return
    view = watch.view
    start_time, flight = watch.flight
    rows = np.array(watch.rows)
    t, lat, lon, dist, holes = rows.T
    scale = 2.0 * math.tan(math.radians(view.camera.fov_y) / 2.0)
    start = _unit(flight.start.lat, flight.start.lon)
    points = _unit(lat, lon)
    u = A * np.arctan2(np.linalg.norm(np.cross(start, points), axis=1),
                       points @ start)
    w = dist * scale
    # Последний кадр ставит позу в конец пути точно, его шаг не считается.
    inside = t < flight.duration
    t, u, w = t[inside], u[inside], w[inside]
    fresh = np.concatenate([[True], np.diff(t) > 0])
    t, u, w = t[fresh], u[fresh], w[fresh]
    du, dw, dt = np.diff(u), np.diff(w), np.diff(t)
    ds = np.sqrt(RHO * RHO * du * du + dw * dw / (RHO * RHO)) \
        / np.sqrt(w[1:] * w[:-1])
    speed = ds / dt
    expected = flight.path.length / flight.duration
    deviation = np.abs(speed / expected - 1.0)
    print("кадров перелёта %d, время %.2f с, длина пути S = %.2f"
          % (len(rows), flight.duration, flight.path.length))
    print("скорость в метрике статьи: ожидается %.3f, медиана %.3f, "
          "наибольшее отклонение %.2f %%"
          % (expected, np.median(speed), 100 * deviation.max()))
    print("критерий плавности, отклонение не больше %.0f %%: %s"
          % (100 * LIMIT, "выполнен" if deviation.max() <= LIMIT
             else "НЕ выполнен"))
    top = dist.max()
    print("наибольшее расстояние на пути %.0f км" % (top / 1000))
    end = view.navigator.pose
    print("в конце: %.6f, %.6f, расстояние %.0f м, азимут %.1f, наклон %.1f"
          % (end.lat, end.lon, end.distance, end.heading, end.tilt))
    swaps = np.array(watch.swaps)
    iv = np.diff(swaps) * 1000
    print("кадров в секунду в среднем %.1f, пропусков такта (от 25 мс) %d "
          "из %d" % ((len(swaps) - 1) / (swaps[-1] - swaps[0]),
                     int((iv >= 25).sum()), len(iv)))
    print("дыр за перелёт: наибольшее за кадр %d" % holes.max())
    if watch.before:
        gaps = iv[:len(watch.before)] >= 25
        before = np.array(watch.before) * 1000
        after = np.array(watch.after) * 1000
        print("до paintGL, мс: медиана %.1f, у пропусков медиана %.1f"
              % (np.median(before), np.median(before[gaps])
                 if gaps.any() else 0.0))
        print("после paintGL, мс: медиана %.1f, у пропусков медиана %.1f"
              % (np.median(after), np.median(after[gaps])
                 if gaps.any() else 0.0))
    recent = list(view.sections)[-len(rows):]
    for name in ("upload", "select", "loader", "draw"):
        values = np.array([s[name] for s in recent]) * 1000
        print("  %-7s медиана %.2f мс, 95-й процентиль %.2f мс"
              % (name, np.median(values), np.percentile(values, 95)))
    print("ошибок OpenGL:", dict(view.gl_errors) or 0)
    errors = getattr(plugin, "_open_errors", None)
    if errors is not None:
        print("ошибок Python с открытия окна: %d, проба дошла: %s"
              % (len(errors), getattr(plugin, "_open_probe", False)))
    return {"deviation": float(deviation.max()),
            "drops": int((iv >= 25).sum()), "frames": len(iv),
            "holes": int(holes.max()),
            "end": (end.lat, end.lon, end.distance)}
