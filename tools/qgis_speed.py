# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скорость кадра при загрузке нового места, по участкам paintGL.

Запуск через мост в два вызова, окно глобуса должно быть видно:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_speed.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_speed.py")["report"]()

Код внутри вызова моста идёт под трассировщиком и медленнее втрое,
поэтому сценарий идёт по таймеру после возврата из моста.

Камера по очереди переходит в города списка PLACES, в каждом стоит
STAY секунд, пока грузятся подложка, высоты и наложение. Вид 20 км,
наклон 50°. Города чередуются: с наложением и без. Отчёт даёт медиану
и 95-й процентиль paintGL и его участков по каждому режиму.
"""
import statistics

import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

PLACES = [(55.03, 82.92), (54.99, 73.37), (56.01, 92.87), (52.29, 104.3),
          (48.48, 135.08), (43.12, 131.9), (61.25, 73.4), (51.53, 46.03),
          # Второй набор, для замера после правок, пока первый в кэше.
          (57.15, 65.53), (53.35, 83.77), (62.03, 129.73), (46.35, 48.03),
          (56.84, 53.2), (54.63, 39.73), (59.22, 39.89), (50.6, 36.59),
          # Третий набор.
          (64.54, 40.54), (58.6, 49.66), (51.77, 55.1), (53.24, 34.37),
          (57.63, 39.87), (52.6, 39.57), (45.03, 41.97), (42.98, 47.5),
          # Екатеринбург, место шага 3 в qgis_overlay.py, индекс 24.
          (56.838, 60.605)]
STAY = 10.0
DISTANCE = 20000.0
TILT = 50.0
SECTIONS = ("upload", "terrain", "select", "heights", "loader", "draw",
            "evict")


class Speed(QObject):

    def __init__(self, window, places, first=0, reload=False, modes=None):
        super().__init__(window)
        self.reload = reload
        # Режимы отрезков по кругу. Без них - чередование с наложением
        # и без, данные сбрасываются все.
        self.modes = modes
        self.window = window
        self.view = window.view
        self.places = places
        self.index = first - 1
        self.rows = {}
        self.saved = window.borders_on()
        self.done = False
        self.view.frameSwapped.connect(self._frame)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._next)
        self._next()
        self.timer.start(int(STAY * 1000))

    def _reset_overlay(self):
        view = self.view
        if view.overlay is not None:
            view.set_overlay(view.overlay)

    def _reset(self):
        """Сбросить подложку, высоты глубже уровня 2 и наложение.

        Камера стоит, данные грузятся заново из дискового кэша QGIS.
        Нагрузка на рабочие потоки та же, что при загрузке нового
        места, но повторяется от прогона к прогону.
        """
        view = self.view
        view.change_source(view.max_level)
        store = view.store
        store.tiles = {k: t for k, t in store.tiles.items() if k[0] <= 2}
        store._ranges.clear()
        store.version += 1
        view._terrain_wanted = frozenset()
        view._terrain_at = 0.0
        view._nearest_probe = None
        if view.overlay is not None:
            view.set_overlay(view.overlay)

    def _next(self):
        self.index += 1
        if self.index >= len(self.places):
            self.timer.stop()
            self.view.frameSwapped.disconnect(self._frame)
            self.window.set_borders(self.saved)
            self.done = True
            return
        from planetx.core.navigation import Pose
        if self.modes:
            self.mode = self.modes[self.index % len(self.modes)]
            overlay = self.mode != "растр"
        else:
            overlay = self.index % 2 == 0
            self.mode = "с наложением" if overlay else "без наложения"
        self.window.set_borders(overlay)
        lat, lon = self.places[self.index]
        store = self.view.store
        self.view.navigator.set_pose(Pose(lat, lon, DISTANCE, 0.0, TILT,
                                          store.height_at(lat, lon),
                                          store.height_at))
        if self.mode == "вектор":
            self._reset_overlay()
        elif self.reload and self.mode != "прогрев":
            self._reset()
        self.view.update()

    def _frame(self):
        view = self.view
        if not view.sections:
            return
        section = dict(view.sections[-1])
        section["paint"] = view.frame_times[-1]
        if self.mode != "прогрев":
            self.rows.setdefault(self.mode, []).append(section)


def start(first=0, count=None, reload=False, repeat=8, atmosphere=True,
          modes=None):
    """Замер. reload=True - одно место PLACES[first], данные сбрасываются
    repeat раз и грузятся из дискового кэша, повторяемо от прогона
    к прогону. Иначе камера обходит новые места списка.
    """
    plugin = qgis.utils.plugins["planetx"]
    window = plugin.window
    if reload:
        places = [PLACES[first]] * repeat
    else:
        places = PLACES[first:first + count] if count else PLACES[first:]
    window.view.atmosphere = atmosphere
    plugin._speed = Speed(window, places, reload=reload, modes=modes)
    print("замер запущен: %d отрезков по %.0f с" % (len(places), STAY))


def _pct(values, q):
    values = sorted(values)
    return 1000 * values[min(len(values) - 1, int(q * len(values)))]


def report():
    run = qgis.utils.plugins["planetx"]._speed
    if not run.done:
        print("идёт место %d из %d" % (run.index + 1, len(run.places)))
        return None
    out = {}
    for name, rows in run.rows.items():
        if not rows:
            continue
        print("%s, кадров %d" % (name, len(rows)))
        for part in ("paint",) + SECTIONS:
            values = [row[part] for row in rows]
            print("  %-7s медиана %5.2f мс, 95-й процентиль %5.2f мс, "
                  "наибольшее %6.2f мс"
                  % (part, 1000 * statistics.median(values),
                     _pct(values, 0.95), _pct(values, 1.0)))
        out[name] = {part: _pct([row[part] for row in rows], 0.95)
                        for part in ("paint",) + SECTIONS}
    return out
