# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Приёмка фазы 0: четыре проверки подряд и таблица итогов.

Запуск через мост в два вызова. Весь прогон занимает 2-3 минуты,
окно глобуса всё это время должно быть видно на экране:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_phase0.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_phase0.py")["report"]()

Шаги идут по таймеру, главный поток QGIS между ними свободен:

1. qgis_open.py - окно открывается, контекст 3.3 Core, дыр нет
2. qgis_bench.py - вращение, не меньше 55 кадров в любую секунду
3. qgis_descent.py - спуск до улиц Перми, 0 дыр на всех кадрах
4. qgis_flight.py - перелёт, отклонение скорости не больше 5 %

Подробные отчёты шагов собираются и печатаются вторым вызовом.
"""
import contextlib
import io
import os
import time

import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

TOOLS = os.path.dirname(os.path.abspath(__file__)) \
    if "__file__" in globals() else r"C:\Dev\planetx\tools"
OPEN_WAIT = 20.0  # секунд на загрузку уровней 0-2 при открытии окна


def _script(name):
    import runpy
    return runpy.run_path(os.path.join(TOOLS, name))


def _quiet(function):
    """Вызов с перехватом печати. Возвращает результат и текст."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = function()
    return result, buffer.getvalue()


class Acceptance(QObject):

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.results = {}
        self.texts = {}
        self.step = None
        self.started = time.monotonic()
        self.step_started = self.started
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.steps = [
            ("open", "qgis_open.py", self._open_done),
            ("bench", "qgis_bench.py",
             lambda: self.plugin._bench.done),
            ("descent", "qgis_descent.py",
             lambda: self.plugin._descent.phase == "готово"),
            ("flight", "qgis_flight.py",
             lambda: self.plugin._flight_watch.done),
        ]
        self.index = -1
        self._next()
        self.timer.start(500)

    def _open_done(self):
        window = self.plugin.window
        if window is None:
            return False
        waited = time.monotonic() - self.step_started
        ready = window.view.ready() and window.loader.busy() == 0
        return ready or waited > OPEN_WAIT

    def _next(self):
        self.index += 1
        if self.index >= len(self.steps):
            self.timer.stop()
            self.step = "готово"
            return
        name, script, _ = self.steps[self.index]
        self.step = name
        self.step_started = time.monotonic()
        _, text = _quiet(_script(script)["start"])
        self.texts[name + " start"] = text
        if name == "open":
            window = self.plugin.window
            window.showNormal()
            window.raise_()
            window.activateWindow()

    def _tick(self):
        if self.step == "готово":
            return
        name, script, done = self.steps[self.index]
        if not done():
            return
        result, text = _quiet(_script(script)["report"])
        self.results[name] = result
        self.texts[name] = text
        self._next()


HANG_LOG = os.path.join(os.environ.get("TEMP", "."), "planetx_hang.txt")
HANG_AFTER = 20  # секунд без отклика главного потока до записи стеков


class HangWatch(QObject):
    """Запись стеков всех потоков Python, если главный поток встал.

    faulthandler пишет из своего потока и без GIL. Таймер главного
    потока каждые 5 с откладывает запись. Встал главный поток - через
    HANG_AFTER секунд в HANG_LOG ложатся стеки.
    """

    def __init__(self):
        import faulthandler
        super().__init__()
        self.faulthandler = faulthandler
        self.file = open(HANG_LOG, "w", encoding="utf-8")
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._arm)
        self.timer.start(5000)
        self._arm()

    def _arm(self):
        self.faulthandler.cancel_dump_traceback_later()
        self.faulthandler.dump_traceback_later(HANG_AFTER, repeat=False,
                                               file=self.file)

    def stop(self):
        self.timer.stop()
        self.faulthandler.cancel_dump_traceback_later()
        self.file.close()


def start():
    plugin = qgis.utils.plugins["planetx"]
    old = getattr(plugin, "_hang_watch", None)
    if old is not None:
        old.stop()
    plugin._hang_watch = HangWatch()
    plugin._acceptance = Acceptance(plugin)
    print("приёмка фазы 0 запущена, шаг:", plugin._acceptance.step)
    print("стеки при зависании пишутся в", HANG_LOG)


def _row(name, value, limit, ok):
    print("| %-34s | %-30s | %-24s | %-9s |"
          % (name, value, limit, "да" if ok else "НЕТ"))


def report():
    plugin = qgis.utils.plugins["planetx"]
    run = plugin._acceptance
    if run.step != "готово":
        print("идёт шаг %s, %.0f с от начала"
              % (run.step, time.monotonic() - run.started))
        return
    watch = getattr(plugin, "_hang_watch", None)
    if watch is not None:
        watch.stop()
        plugin._hang_watch = None
    for name in ("open", "bench", "descent", "flight"):
        print("==== %s" % name)
        print(run.texts.get(name, "").rstrip())
    r = run.results
    print("")
    print("| %-34s | %-30s | %-24s | %-9s |"
          % ("Критерий", "Измерено", "Порог", "Выполнен"))
    o = r["open"]
    _row("Окно открывается из QGIS",
         "%s %s, тайлов %d, дыр %d" % (o["gl"], o["profile"].split(".")[-1],
                                       o["drawn"], o["holes"]),
         "3.3 Core, дыр 0",
         o["gl"] == (3, 3) and "Core" in o["profile"] and o["drawn"] > 0
         and o["holes"] == 0)
    b = r["bench"]
    _row("Вращение не ниже 55 кадров в с",
         "не меньше %d в любую с, пропусков %d" % (b["min_window"],
                                                   b["drops"]),
         "не меньше 55", b["min_window"] >= 55 and b["valid"])
    d = r["descent"]
    _row("Спуск до улиц Перми без дыр",
         "дыр %d, щелей до %d, уровень %d" % (d["holes"], d["gaps"],
                                             d["level"]),
         "дыр 0", d["holes"] == 0 and d["valid"])
    f = r["flight"]
    _row("Плавный перелёт",
         "отклонение %.2f %%, пропусков %d" % (100 * f["deviation"],
                                              f["drops"]),
         "отклонение до 5 %", f["deviation"] <= 0.05)
    errors = getattr(plugin, "_open_errors", [])
    print("")
    print("ошибок Python за приёмку: %d, проба журнала дошла: %s"
          % (len(errors), getattr(plugin, "_open_probe", False)))
    print("длительность приёмки %.0f с" % (time.monotonic() - run.started))
