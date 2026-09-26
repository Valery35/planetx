# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Приёмка наложения границ и дорог поверх космоснимков, фаза 2.

Запуск через мост в два вызова, окно глобуса должно быть видно:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_overlay.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_overlay.py")["report"]()

Шаги по таймеру:

1. окно открывается заново, подложка Esri World Imagery, наложение
   включено
2. qgis_descent.py - спуск из космоса до улиц Перми, дыры на всех
   кадрах
3. камера переходит в новое место, где наложения ещё нет, и стоит
   COVER_WAIT секунд. За это время мерится paintGL, потом считается
   доля нарисованных тайлов со своей картинкой наложения. Счётчик дыр
   здесь выключен: он ждёт ответа видеокарты дважды за кадр, и это
   ожидание попадало во время paintGL на спуске
4. qgis_bench.py - вращение, кадров в любую секунду

Подложка и флажок наложения, выбранные до приёмки, в конце
возвращаются.
"""
import contextlib
import io
import os
import time

import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

TOOLS = os.path.dirname(os.path.abspath(__file__)) \
    if "__file__" in globals() else r"C:\Dev\planetx\tools"
IMAGERY = "Esri World Imagery"
OPEN_WAIT = 20.0
COVER_WAIT = 10.0
# Новое место для шага 3: Екатеринбург, 20 км, наклон 50°.
COVER_POSE = (56.838, 60.605, 20000.0, 0.0, 50.0)
MIN_COVER = 0.95
MAX_PAINT_MS = 12.0


def _script(name):
    import runpy
    return runpy.run_path(os.path.join(TOOLS, name))


def _quiet(function):
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = function()
    return result, buffer.getvalue()


def coverage(view):
    """Доля нарисованных тайлов со своей картинкой наложения."""
    drawn = view.selection.draw if view.selection else []
    if not drawn:
        return 0.0, 0
    # Пустая картинка - тоже своя: линий на тайле нет.
    own = sum(1 for key in drawn if view._overlay_ready(key))
    return own / len(drawn), len(drawn)


class Acceptance(QObject):

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.results = {}
        self.texts = {}
        self.saved = None
        self.started = time.monotonic()
        self.step_started = self.started
        self.paint = []
        self.steps = [
            ("open", self._open, self._open_done, lambda: None),
            ("descent", lambda: _script("qgis_descent.py")["start"](),
             lambda: self.plugin._descent.phase == "готово",
             self._descent_report),
            ("cover", self._cover, self._cover_done, self._cover_report),
            ("bench", lambda: _script("qgis_bench.py")["start"](),
             lambda: self.plugin._bench.done,
             lambda: _script("qgis_bench.py")["report"]()),
        ]
        self.index = -1
        self.step = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self._next()
        self.timer.start(500)

    def _open(self):
        _script("qgis_open.py")["start"]()
        window = self.plugin.window
        names = [s.name for s in window.sources]
        self.saved = (window.basemap_index(),
                      window.borders_on())
        if IMAGERY not in names:
            raise RuntimeError("нет подключения " + IMAGERY)
        window.choose_basemap(names.index(IMAGERY))
        window.set_borders(True)
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def _open_done(self):
        window = self.plugin.window
        waited = time.monotonic() - self.step_started
        ready = window.view.ready() and window.overlay is not None
        return ready or waited > OPEN_WAIT

    def _descent_report(self):
        return _script("qgis_descent.py")["report"]()

    def _cover(self):
        from planetx.core.navigation import Pose
        view = self.plugin.window.view
        lat, lon, distance, heading, tilt = COVER_POSE
        store = view.store
        view.navigator.set_pose(Pose(lat, lon, distance, heading, tilt,
                                     store.height_at(lat, lon),
                                     store.height_at))
        view.frame_times.clear()
        view.sections.clear()
        self.cover_started = time.monotonic()

    def _cover_done(self):
        view = self.plugin.window.view
        view.update()
        if time.monotonic() - self.cover_started < COVER_WAIT:
            return False
        self.paint = sorted(view.frame_times)
        self.sections = list(view.sections)
        return True

    def _cover_report(self):
        window = self.plugin.window
        share, drawn = coverage(window.view)
        overlay = window.overlay
        times = sorted(overlay.render_times.values())
        print("тайлов в кадре %d, со своей картинкой наложения %.1f %%"
              % (drawn, 100.0 * share))
        print("пустых картинок %d, в видеокарте %d"
              % (len(window.view.overlay_empty), len(window.view.overlays)))
        print("отрисовок наложения %d, медиана %.0f мс, наибольшая %.0f мс"
              % (len(times), 1000 * times[len(times) // 2],
                 1000 * times[-1]))
        print("ошибка наложения: %s" % (window.overlay_error or "нет"))
        from planetx.core.overlay import window as overlay_window
        view = window.view
        sel = view.selection
        missing = [k for k in sel.draw if not view._overlay_ready(k)]
        temporary = [k for k in missing
                     if (k[0] + 1, 2 * k[1], 2 * k[2]) in sel.keep]
        shown = [k for k in missing
                 if overlay_window(k, view._overlay_ready)]
        print("без своей картинки %d: временных родителей %d, с частью "
              "картинки предка %d, подложка ещё грузится: %s"
              % (len(missing), len(temporary), len(shown),
                 "да" if view.pending or window.loader.busy() else "нет"))
        print("кадров за шаг %d" % len(self.paint))
        # thread_time в Windows растёт шагами по 15.6 мс, верна только
        # сумма по сотням кадров.
        cpu = sum(s["cpu"] for s in self.sections)
        print("процессорное время потока - %.0f %% от общего времени кадров"
              % (100.0 * cpu / max(1e-9, sum(self.paint))))
        for name in ("upload", "terrain", "select", "heights", "loader",
                     "draw", "evict"):
            values = sorted(s[name] for s in self.sections)
            print("  %-7s медиана %.2f мс, 95-й процентиль %.2f мс"
                  % (name, 1000 * values[len(values) // 2],
                     1000 * values[int(0.95 * len(values))]))
        return {"share": share, "drawn": drawn}

    def _next(self):
        self.index += 1
        if self.index >= len(self.steps):
            self.timer.stop()
            window = self.plugin.window
            if self.saved is not None:
                window.choose_basemap(self.saved[0])
                window.set_borders(self.saved[1])
            self.step = "готово"
            return
        name, begin, _, _ = self.steps[self.index]
        self.step = name
        self.step_started = time.monotonic()
        _, self.texts[name + " start"] = _quiet(begin)

    def _tick(self):
        if self.step == "готово":
            return
        name, _, done, report = self.steps[self.index]
        if not done():
            return
        self.results[name], self.texts[name] = _quiet(report)
        self._next()


def start():
    plugin = qgis.utils.plugins["planetx"]
    plugin._overlay_run = Acceptance(plugin)
    print("приёмка наложения запущена, шаг:", plugin._overlay_run.step)


def _row(name, value, limit, ok):
    print("| %-30s | %-40s | %-20s | %-8s |"
          % (name, value, limit, "да" if ok else "НЕТ"))


def report():
    plugin = qgis.utils.plugins["planetx"]
    run = plugin._overlay_run
    if run.step != "готово":
        print("идёт шаг %s, %.0f с от начала"
              % (run.step, time.monotonic() - run.started))
        return
    for name in ("descent", "cover", "bench"):
        print("==== %s" % name)
        print(run.texts.get(name, "").rstrip())
    r = run.results
    paint = run.paint
    p95 = 1000 * paint[int(len(paint) * 0.95)] if paint else float("nan")
    print("")
    print("| %-30s | %-40s | %-20s | %-8s |"
          % ("Критерий", "Измерено", "Порог", "Выполнен"))
    d = r["descent"]
    _row("Спуск без дыр", "дыр %d, кадров %d" % (d["holes"], d["frames"]),
         "дыр 0", d["holes"] == 0 and d["valid"])
    c = r["cover"]
    _row("Наложение догоняет",
         "%.1f %% из %d тайлов" % (100 * c["share"], c["drawn"]),
         "не меньше %.0f %%" % (100 * MIN_COVER), c["share"] >= MIN_COVER)
    b = r["bench"]
    _row("Вращение с наложением",
         "не меньше %d в любую с" % b["min_window"], "не меньше 55",
         b["min_window"] >= 55 and b["valid"])
    _row("paintGL при загрузке", "95-й процентиль %.1f мс" % p95,
         "не больше %.0f мс" % MAX_PAINT_MS, p95 <= MAX_PAINT_MS)
    errors = getattr(plugin, "_open_errors", [])
    print("")
    print("ошибок Python: %d, проба журнала дошла: %s"
          % (len(errors), getattr(plugin, "_open_probe", False)))
    for line in sorted(set(errors))[:5]:
        print("  ", line)
    print("ошибок OpenGL: %s" % (dict(plugin.window.view.gl_errors) or 0))
    print("длительность %.0f с" % (time.monotonic() - run.started))
