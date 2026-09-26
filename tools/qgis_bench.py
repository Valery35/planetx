# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка шага 0.9: частота кадров при вращении глобуса.

Запуск через мост в два вызова, окно глобуса должно быть открыто:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_bench.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_bench.py")["report"]()

Вид окна 1600×900 логических пикселей. Глобус качается по долготе
на ±30° вокруг Перми с высоты 2000 км, период 5 с. Прогрев идёт, пока
грузятся тайлы, но не меньше WARMUP и не больше WARMUP_MAX секунд,
он не считается. Следующие MEASURE секунд меряются. Отчёт говорит,
кончилась ли загрузка к началу замера.

Интервал кадра берётся между сигналами frameSwapped. В него входят
Python, видеокарта и ожидание вертикальной синхронизации.

Критерий шага - не меньше 55 кадров в любом скользящем окне 1 с.
Отчёт называет и количество пропусков такта, и 95-й процентиль
интервала. Процентиль справочный: интервал между сигналами frameSwapped
дрожит на несколько миллисекунд, когда кадр на экране не пропущен.
"""
import math
import time

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

PERM = (58.0105, 56.2294)
DISTANCE = 2.0e6
SWING = 30.0  # градусов долготы в каждую сторону
PERIOD = 5.0  # секунд на полный размах
WARMUP = 10.0  # прогрев не короче, секунд
WARMUP_MAX = 60.0  # и не длиннее
MEASURE = 10.0
VIEW_SIZE = (1600, 900)
LIMIT_MS = 1000.0 / 55.0
MIN_FPS = 55
# Пропуск такта монитора 60 Гц - интервал около 33 мс. Всё короче 25 мс
# считается дрожанием момента, когда Python получает frameSwapped.
DROP_MS = 25.0


class Bench(QObject):
    """Двигает камеру каждый кадр и пишет время кадров."""

    def __init__(self, view):
        super().__init__(view)
        from planetx.core.navigation import Pose
        self.view = view
        self.pose = Pose(PERM[0], PERM[1], DISTANCE)
        self.t0 = time.perf_counter()
        self.swaps = []
        self.before = []
        self.after = []
        self.python = []
        self.sections = []
        self.done = False
        self.measure_from = None
        self.loaded_before = False
        # Qt не рисует окно, целиком закрытое другими окнами, и цепочка
        # кадров рвётся. Сторож замечает простой и перезапускает её.
        self.last_frame = time.perf_counter()
        self.last_paint = None
        self.stalls = []
        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self._watch)
        self.watchdog.start(250)
        view.navigator.stop()
        view.frameSwapped.connect(self._frame)
        self._move()
        view.update()

    def _watch(self):
        if self.done:
            self.watchdog.stop()
            return
        now = time.perf_counter()
        if now - self.last_frame > 0.5:
            handle = self.view.window().windowHandle()
            exposed = bool(handle and handle.isExposed())
            self.stalls.append((now - self.t0, exposed))
            self.last_frame = now
            self._move()
            self.view.update()

    def _move(self):
        t = time.perf_counter() - self.t0
        self.pose.lon = PERM[1] + SWING * math.sin(2.0 * math.pi * t
                                                   / PERIOD)
        self.view.navigator.set_pose(self.pose)

    def _idle(self):
        loader = self.view.loader
        return (loader is None or loader.busy() == 0) \
            and not self.view.pending

    def _frame(self):
        # frameSwapped без нового paintGL повторяет прошлый кадр.
        if self.view.frame == self.last_paint:
            return
        self.last_paint = self.view.frame
        now = time.perf_counter()
        self.last_frame = now
        t = now - self.t0
        if self.measure_from is None:
            # Прогрев идёт, пока грузятся тайлы, от WARMUP до WARMUP_MAX.
            if t >= WARMUP_MAX or (t >= WARMUP and self._idle()):
                self.measure_from = t
                self.loaded_before = self._idle()
            else:
                self._move()
                self.view.update()
                return
        start = self.measure_from
        if start <= t <= start + MEASURE:
            span = getattr(self.view, "paint_span", None)
            if span is not None and self.swaps:
                # До начала paintGL от прошлого кадра и от конца paintGL
                # до frameSwapped.
                self.before.append(span[0] - self.swaps[-1])
                self.after.append(now - span[1])
            self.swaps.append(now)
            if self.view.frame_times:
                self.python.append(self.view.frame_times[-1])
                self.sections.append(self.view.sections[-1])
        if t > start + MEASURE:
            self.done = True
            self.view.frameSwapped.disconnect(self._frame)
            return
        self._move()
        self.view.update()


def start():
    plugin = qgis.utils.plugins["planetx"]
    if plugin.window is None:
        plugin.run()
    window = plugin.window
    view = window.view
    extra_w = window.width() - view.width()
    extra_h = window.height() - view.height()
    window.resize(VIEW_SIZE[0] + extra_w, VIEW_SIZE[1] + extra_h)
    plugin._bench = Bench(view)
    print("замер запущен: прогрев %.0f с, замер %.0f с" % (WARMUP, MEASURE))


def _pct(values, q):
    return float(np.percentile(np.asarray(values) * 1000.0, q))


def report():
    plugin = qgis.utils.plugins["planetx"]
    bench = plugin._bench
    view = bench.view
    elapsed = time.perf_counter() - bench.t0
    hidden = [t for t, exposed in bench.stalls if not exposed]
    if not bench.done:
        print("замер идёт: %.1f с, прогрев %s" % (
            elapsed, "идёт" if bench.measure_from is None
            else "кончился на %.1f с" % bench.measure_from))
        if hidden:
            print("окно глобуса закрыто другими окнами, кадры не идут. "
                  "Для замера окно должно быть видно на экране.")
        return
    during = [t for t in hidden
              if bench.measure_from <= t <= bench.measure_from + MEASURE]
    if during:
        print("ЗАМЕР НЕДЕЙСТВИТЕЛЕН: окно было закрыто другими окнами "
              "%d раз за время замера" % len(during))
    swaps = np.diff(bench.swaps)
    ratio = view.devicePixelRatioF()
    print("прогрев %.1f с, загрузка к началу замера %s"
          % (bench.measure_from, "кончилась" if bench.loaded_before
             else "НЕ кончилась, замер смешан с загрузкой"))
    print("вид %d×%d логических пикселей, кадр %d×%d"
          % (view.width(), view.height(), view.camera.width,
             view.camera.height))
    print("кадров за замер: %d, в среднем %.1f кадра в секунду"
          % (len(bench.swaps), (len(bench.swaps) - 1) / MEASURE))
    print("интервал кадра, мс: медиана %.2f, 95-й процентиль %.2f, "
          "наибольший %.2f" % (_pct(swaps, 50), _pct(swaps, 95),
                               _pct(swaps, 100)))
    stamps = np.asarray(bench.swaps)
    windows = [int(((stamps >= t) & (stamps < t + 1.0)).sum())
               for t in np.arange(stamps[0], stamps[-1] - 1.0, 0.05)]
    drops = int((swaps * 1000.0 >= DROP_MS).sum())
    print("кадров в скользящем окне 1 с: наименьшее %d, медиана %d"
          % (min(windows), int(np.median(windows))))
    print("пропусков такта (интервал от %.0f мс): %d из %d, %.2f %%"
          % (DROP_MS, drops, len(swaps), 100.0 * drops / len(swaps)))
    print("критерий фазы 0, не меньше %d кадров в любую секунду: %s"
          % (MIN_FPS, "выполнен" if min(windows) >= MIN_FPS
             else "НЕ выполнен"))
    print("справочно, 95-й процентиль интервала не больше %.1f мс: %s"
          % (LIMIT_MS, "да" if _pct(swaps, 95) <= LIMIT_MS else "нет"))
    print("Python в paintGL, мс: медиана %.2f, 95-й процентиль %.2f"
          % (_pct(bench.python, 50), _pct(bench.python, 95)))
    if bench.before:
        print("от прошлого кадра до paintGL, мс: медиана %.2f, 95-й %.2f"
              % (_pct(bench.before, 50), _pct(bench.before, 95)))
        print("от конца paintGL до frameSwapped, мс: медиана %.2f, 95-й %.2f"
              % (_pct(bench.after, 50), _pct(bench.after, 95)))
    for name in ("upload", "select", "loader", "draw", "evict"):
        values = [s[name] for s in bench.sections]
        print("  %-7s медиана %.2f мс, 95-й процентиль %.2f мс"
              % (name, _pct(values, 50), _pct(values, 95)))
    draws = [s["draws"] for s in bench.sections]
    print("вызовов отрисовки на кадр: медиана %d, наибольшее %d"
          % (int(np.median(draws)), max(draws)))
    print("текстур в памяти %d, масштаб экрана %.0f %%"
          % (len(view.textures), ratio * 100))
    print("ошибок OpenGL за время окна:", dict(view.gl_errors) or 0)
    errors = getattr(plugin, "_open_errors", None)
    if errors is not None:
        print("ошибок Python с открытия окна: %d, проба дошла: %s"
              % (len(errors), getattr(plugin, "_open_probe", False)))
    return {"min_window": min(windows), "drops": drops,
            "frames": len(swaps), "p95": _pct(swaps, 95),
            "valid": not during}
