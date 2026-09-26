# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Приёмка фазы 1: рельеф, космоснимки, атмосфера. Таблица итогов.

Запуск через мост в два вызова. Прогон занимает 3-5 минут, окно
глобуса всё это время должно быть видно на экране:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_phase1.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_phase1.py")["report"]()

Шаги идут по таймеру, главный поток QGIS между ними свободен:

1. qgis_open.py - окно открывается, подложка OpenStreetMap
2. qgis_bench.py - вращение с рельефом и атмосферой
3. горы - спуск к Эльбрусу с наклоном до 60°, ожидание загрузки,
   высота вершины, потом низкий полёт через вершину с наклоном 80°.
   Каждый кадр считает дыры и зазор глаза над рельефом.
4. космоснимки - смена подложки на Esri World Imagery над Пермью,
   дыры на всех кадрах до конца замены, подпись источника
5. атмосфера - снимок из космоса и снимок у Эльбруса с наклоном 80°

Подложка, выбранная до приёмки, в конце возвращается. Снимки
кладутся в папку временных файлов.
"""
import contextlib
import io
import math
import os
import tempfile
import time

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import QObject, QTimer

TOOLS = os.path.dirname(os.path.abspath(__file__)) \
    if "__file__" in globals() else r"C:\Dev\planetx\tools"
SHOTS = tempfile.gettempdir()
OPEN_WAIT = 20.0  # секунд на загрузку уровней 0-2 при открытии окна

# Вершина Эльбруса по данным Terrarium уровня 12, замер 26 сентября 2026
# года. Эталон высоты - 5642 м, критерий в doc/PLAN_PHASE1.md.
ELBRUS = (43.34778, 42.44001)
ELBRUS_HEIGHT = 5642.0
HEIGHT_TOLERANCE = 60.0
SEARCH_RADIUS = 1000.0  # метров вокруг вершины
SEARCH_STEP = 20.0
MIN_HEIGHT_LEVEL = 12
MIN_CLEARANCE = 50.0

DESCENT = 20.0  # секунд спуска
DESCENT_FROM = 2.0e6
DESCENT_TO = 1500.0
DESCENT_TILT = 60.0
SETTLE_MAX = 90.0
LOW = 12.0  # секунд низкого полёта
LOW_SPAN = 0.05  # градусов широты в каждую сторону от вершины
LOW_DISTANCE = 400.0
LOW_TILT = 80.0

PERM = (58.0105, 56.2294)
IMAGERY = "Esri World Imagery"
IMAGERY_POSE = dict(distance=6000.0, heading=30.0, tilt=60.0)
IMAGERY_MAX = 60.0
SHOT_WAIT_MAX = 30.0
SPACE_DISTANCE = 2.0e7
SKY_DISTANCE = 2000.0
SKY_TILT = 80.0
A = 6378137.0


def _script(name):
    import runpy
    return runpy.run_path(os.path.join(TOOLS, name))


def _quiet(function):
    """Вызов с перехватом печати. Возвращает результат и текст."""
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        result = function()
    return result, buffer.getvalue()


def _pose(view, lat, lon, distance, heading=0.0, tilt=0.0):
    """Поза с точкой взгляда на рельефе."""
    from planetx.core.navigation import Pose
    store = view.store
    return Pose(lat, lon, distance, heading, tilt,
                store.height_at(lat, lon), store.height_at)


def _clearance(view):
    from planetx.core.ellipsoid import ecef_to_geodetic
    lat, lon, h = ecef_to_geodetic(view.camera.eye)
    return float(h) - view.store.height_at(float(lat), float(lon))


def _idle(window):
    view = window.view
    return (window.loader.busy() == 0 and window.terrain_loader.busy() == 0
            and not view.pending and not view.building and not view.built
            and not view.stale)


def _height_level(store, lat, lon):
    """Уровень самого точного тайла высот в точке или -1."""
    from planetx.core.tiling import lonlat_to_tile
    for z in range(15, -1, -1):
        if (z,) + tuple(lonlat_to_tile(lat, lon, z)) in store.tiles:
            return z
    return -1


def summit(store):
    """Наибольшая высота в круге SEARCH_RADIUS вокруг ELBRUS."""
    lat0, lon0 = ELBRUS
    per_lat = 111320.0
    per_lon = per_lat * math.cos(math.radians(lat0))
    steps = int(SEARCH_RADIUS / SEARCH_STEP)
    best = (-1e9, lat0, lon0)
    for i in range(-steps, steps + 1):
        for j in range(-steps, steps + 1):
            dy, dx = i * SEARCH_STEP, j * SEARCH_STEP
            if dx * dx + dy * dy > SEARCH_RADIUS ** 2:
                continue
            lat, lon = lat0 + dy / per_lat, lon0 + dx / per_lon
            height = store.height_at(lat, lon)
            if height > best[0]:
                best = (height, lat, lon)
    height, lat, lon = best
    return {"height": height, "lat": lat, "lon": lon,
            "level": _height_level(store, lat, lon)}


class Watched(QObject):
    """Шаг, который идёт по кадрам. Следит, что кадры не встали."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.t0 = time.perf_counter()
        self.last_frame = self.t0
        self.hidden = 0
        self.done = False
        self.view.navigator.stop()
        self.view.frameSwapped.connect(self._frame)
        self.watchdog = QTimer(self)
        self.watchdog.timeout.connect(self._watch)
        self.watchdog.start(250)

    def _watch(self):
        if self.done:
            self.watchdog.stop()
            return
        now = time.perf_counter()
        if now - self.last_frame > 0.5:
            handle = self.view.window().windowHandle()
            if not (handle and handle.isExposed()):
                self.hidden += 1
            self.last_frame = now
            self.view.update()

    def _frame(self):
        now = time.perf_counter()
        self.last_frame = now
        self.frame(now - self.t0)
        if not self.done:
            self.view.update()

    def finish(self):
        self.view.frameSwapped.disconnect(self._frame)
        self.view.hole_check = False
        self.done = True


class Mountains(Watched):
    """Спуск к Эльбрусу, ожидание загрузки, высота, низкий полёт."""

    def __init__(self, window):
        super().__init__(window)
        self.phase = "спуск"
        self.rows = []
        self.height = None
        self.loaded = False
        self.phase_at = 0.0
        self.view.hole_counts = []
        self.view.hole_check = True
        self._move(0.0)

    def _move(self, t):
        view = self.view
        lat, lon = ELBRUS
        if self.phase == "спуск":
            share = min(1.0, t / DESCENT)
            pose = _pose(view, lat, lon,
                         DESCENT_FROM * (DESCENT_TO / DESCENT_FROM) ** share,
                         90.0 * share, DESCENT_TILT * share)
        elif self.phase == "ожидание":
            pose = _pose(view, lat, lon, DESCENT_TO, 90.0, DESCENT_TILT)
        else:
            share = min(1.0, (t - self.phase_at) / LOW)
            pose = _pose(view, lat + LOW_SPAN * (2.0 * share - 1.0), lon,
                         LOW_DISTANCE, 0.0, LOW_TILT)
        view.navigator.set_pose(pose)

    def frame(self, t):
        view = self.view
        if view.hole_counts:
            _, gaps, holes = view.hole_counts[-1]
            self.rows.append((t, self.phase, gaps, holes, _clearance(view),
                              view.altitude()))
        if self.phase == "спуск" and t >= DESCENT:
            self.phase, self.phase_at = "ожидание", t
        elif self.phase == "ожидание" and (
                _idle(self.window) or t - self.phase_at > SETTLE_MAX):
            self.loaded = _idle(self.window)
            self.height = summit(view.store)
            view.grabFramebuffer().save(
                os.path.join(SHOTS, "planetx_phase1_mountains.png"))
            self.phase, self.phase_at = "низкий полёт", t
        elif self.phase == "низкий полёт" and t - self.phase_at >= LOW:
            self.finish()
            return
        self._move(t)

    def result(self):
        rows = self.rows
        phases = {}
        for _, phase, gaps, holes, clearance, _ in rows:
            item = phases.setdefault(phase, [0, 0, 0, 1e9])
            item[0] += 1
            item[1] = max(item[1], gaps)
            item[2] = max(item[2], holes)
            item[3] = min(item[3], clearance)
        for phase, (frames, gaps, holes, clearance) in phases.items():
            print("%-13s кадров %4d, щелей до %5d, дыр до %d, зазор "
                  "глаза над рельефом не меньше %.1f м"
                  % (phase, frames, gaps, holes, clearance))
        s = self.height
        print("загрузка к замеру высоты %s"
              % ("кончилась" if self.loaded else "НЕ кончилась"))
        print("наибольшая высота в %.0f м от вершины: %.0f м в %.5f, %.5f, "
              "уровень высот %d" % (SEARCH_RADIUS, s["height"], s["lat"],
                                    s["lon"], s["level"]))
        print("окно было закрыто: %d раз" % self.hidden)
        return {
            "holes": max(r[3] for r in rows),
            "gaps": max(r[2] for r in rows),
            "clearance": min(r[4] for r in rows),
            "frames": len(rows),
            "summit": s,
            "valid": self.hidden == 0,
        }


class Imagery(Watched):
    """Смена подложки на космоснимки над Пермью."""

    def __init__(self, window):
        super().__init__(window)
        self.rows = []
        self.missing = IMAGERY not in [s.name for s in window.sources]
        if self.missing:
            self.finish()
            return
        view = self.view
        view.navigator.set_pose(_pose(view, *PERM, **IMAGERY_POSE))
        view.hole_counts = []
        view.hole_check = True
        self.before = window.attribution.text()
        names = [s.name for s in window.sources]
        window.choose_basemap(names.index(IMAGERY))
        window.refresh()

    def frame(self, t):
        view = self.view
        if view.hole_counts:
            self.rows.append(view.hole_counts[-1][1:])
        if _idle(self.window) or t > IMAGERY_MAX:
            self.loaded = _idle(self.window)
            view.grabFramebuffer().save(
                os.path.join(SHOTS, "planetx_phase1_imagery.png"))
            self.finish()

    def result(self):
        if self.missing:
            print("подключения %s в QGIS нет, шаг пропущен" % IMAGERY)
            return {"missing": True}
        window = self.window
        after = window.attribution.text()
        holes = max(r[1] for r in self.rows)
        print("подложка %s, кадров %d, дыр до %d, щелей до %d"
              % (window.source.name, len(self.rows), holes,
                 max(r[0] for r in self.rows)))
        print("замена %s, тайлов прежней подложки осталось %d"
              % ("кончилась" if self.loaded else "НЕ кончилась",
                 len(self.view.stale)))
        print("ошибок загрузки %d, одновременно запросов до %d"
              % (len(window.errors), window.loader.max_seen))
        print("подпись до:", self.before)
        print("подпись после:", after)
        return {"missing": False, "holes": holes, "frames": len(self.rows),
                "errors": len(window.errors), "loaded": self.loaded,
                "attribution": after != self.before and "Esri" in after,
                "valid": self.hidden == 0}


def _rgba(view):
    from planetx.net.loader import image_to_rgba
    return image_to_rgba(view.grabFramebuffer())


class Atmosphere(Watched):
    """Снимок из космоса и снимок у горизонта."""

    def __init__(self, window):
        super().__init__(window)
        self.shots = {}
        self.queue = [
            ("космос", lambda v: _pose(v, *PERM, SPACE_DISTANCE)),
            ("небо", lambda v: _pose(v, ELBRUS[0] - 0.1, ELBRUS[1],
                                     SKY_DISTANCE, 0.0, SKY_TILT)),
        ]
        self._next(0.0)

    def _next(self, t):
        name, make = self.queue.pop(0)
        self.name, self.shot_at = name, t
        self.view.navigator.set_pose(make(self.view))

    def frame(self, t):
        if not (_idle(self.window) or t - self.shot_at > SHOT_WAIT_MAX):
            return
        rgba = _rgba(self.view)
        self.shots[self.name] = (rgba, self.view.camera.eye.copy())
        from qgis.PyQt.QtGui import QImage
        h, w = rgba.shape[:2]
        QImage(rgba.tobytes(), w, h, 4 * w,
               QImage.Format.Format_RGBA8888).save(
            os.path.join(SHOTS, "planetx_phase1_%s.png"
                         % ("space" if self.name == "космос" else "sky")))
        if self.queue:
            self._next(t)
        else:
            self.finish()

    def result(self):
        rgba, eye = self.shots["космос"]
        h, w = rgba.shape[:2]
        fov = math.radians(self.view.camera.fov_y)
        angle = math.asin(A / float(np.linalg.norm(eye)))
        radius = math.tan(angle) / math.tan(fov / 2.0) * h / 2.0

        def ring(scale):
            out = []
            for a in np.linspace(0.0, 2.0 * math.pi, 360, endpoint=False):
                x = int(round(w / 2 + scale * radius * math.cos(a)))
                y = int(round(h / 2 + scale * radius * math.sin(a)))
                if 0 <= x < w and 0 <= y < h:
                    out.append(rgba[y, x, :3])
            return np.median(np.array(out, dtype=float), axis=0)

        halo = ring(1.01)
        space = ring(1.3)
        print("радиус диска %.0f пикселей" % radius)
        print("гало в 1 %% радиуса за краем диска, медиана RGB: %s"
              % halo.round().astype(int).tolist())
        print("космос в 30 %% радиуса за краем, медиана RGB: %s"
              % space.round().astype(int).tolist())
        sky_rgba, _ = self.shots["небо"]
        top = sky_rgba[:sky_rgba.shape[0] // 20, :, :3].reshape(-1, 3)
        sky = np.median(top.astype(float), axis=0)
        print("небо у верхнего края кадра с наклоном %.0f°, медиана RGB: %s"
              % (SKY_TILT, sky.round().astype(int).tolist()))
        return {
            "halo": bool(halo[2] >= 100 and halo[2] > halo[0] + 20),
            "space": bool(space.max() <= 10),
            "sky": bool(sky[2] >= 150 and sky[2] > sky[0] + 40),
            "halo_rgb": halo, "sky_rgb": sky,
            "valid": self.hidden == 0,
        }


class Acceptance(QObject):

    def __init__(self, plugin):
        super().__init__()
        self.plugin = plugin
        self.results = {}
        self.texts = {}
        self.step = None
        self.basemap = None
        self.started = time.monotonic()
        self.step_started = self.started
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._tick)
        self.steps = [
            ("open", self._open_start, self._open_done, self._open_report),
            ("bench", lambda: _script("qgis_bench.py")["start"](),
             lambda: self.plugin._bench.done,
             lambda: _script("qgis_bench.py")["report"]()),
            ("mountains", lambda: self._own(Mountains), self._own_done,
             self._own_report),
            ("imagery", lambda: self._own(Imagery), self._own_done,
             self._own_report),
            ("atmosphere", lambda: self._own(Atmosphere), self._own_done,
             self._own_report),
        ]
        self.index = -1
        self._next()
        self.timer.start(500)

    def _open_start(self):
        _script("qgis_open.py")["start"]()
        window = self.plugin.window
        self.basemap = window.basemap_index()
        # Шаг открытия меряется на OpenStreetMap, как в фазе 0.
        names = [source.name for source in window.sources]
        window.choose_basemap(names.index("OpenStreetMap"))
        window.refresh()
        window.showNormal()
        window.raise_()
        window.activateWindow()

    def _open_done(self):
        window = self.plugin.window
        waited = time.monotonic() - self.step_started
        ready = window.view.ready() and window.loader.busy() == 0
        return ready or waited > OPEN_WAIT

    def _open_report(self):
        return _script("qgis_open.py")["report"]()

    def _own(self, kind):
        self.current = kind(self.plugin.window)

    def _own_done(self):
        return self.current.done

    def _own_report(self):
        return self.current.result()

    def _next(self):
        self.index += 1
        if self.index >= len(self.steps):
            self.timer.stop()
            window = self.plugin.window
            if self.basemap is not None:
                window.choose_basemap(self.basemap)
                window.refresh()
            self.step = "готово"
            return
        name, begin, _, _ = self.steps[self.index]
        self.step = name
        self.step_started = time.monotonic()
        _, text = _quiet(begin)
        self.texts[name + " start"] = text

    def _tick(self):
        if self.step == "готово":
            return
        name, _, done, report = self.steps[self.index]
        if not done():
            return
        result, text = _quiet(report)
        self.results[name] = result
        self.texts[name] = text
        self._next()


def start():
    plugin = qgis.utils.plugins["planetx"]
    plugin._acceptance1 = Acceptance(plugin)
    print("приёмка фазы 1 запущена, шаг:", plugin._acceptance1.step)


def _row(name, value, limit, ok):
    print("| %-32s | %-42s | %-22s | %-8s |"
          % (name, value, limit, "да" if ok else "НЕТ"))


def report():
    plugin = qgis.utils.plugins["planetx"]
    run = plugin._acceptance1
    if run.step != "готово":
        print("идёт шаг %s, %.0f с от начала"
              % (run.step, time.monotonic() - run.started))
        return
    for name, _, _, _ in run.steps:
        print("==== %s" % name)
        print(run.texts.get(name, "").rstrip())
    r = run.results
    print("")
    print("| %-32s | %-42s | %-22s | %-8s |"
          % ("Критерий", "Измерено", "Порог", "Выполнен"))
    m = r["mountains"]
    s = m["summit"]
    _row("Высота Эльбруса",
         "%.0f м, уровень высот %d" % (s["height"], s["level"]),
         "%.0f ± %.0f м, уровень от %d" % (ELBRUS_HEIGHT, HEIGHT_TOLERANCE,
                                           MIN_HEIGHT_LEVEL),
         abs(s["height"] - ELBRUS_HEIGHT) <= HEIGHT_TOLERANCE
         and s["level"] >= MIN_HEIGHT_LEVEL)
    _row("Спуск к горам без дыр",
         "дыр %d, щелей до %d, кадров %d" % (m["holes"], m["gaps"],
                                             m["frames"]),
         "дыр 0", m["holes"] == 0 and m["valid"])
    _row("Камера не уходит под рельеф",
         "зазор не меньше %.1f м" % m["clearance"],
         "не меньше %.0f м" % MIN_CLEARANCE,
         m["clearance"] >= MIN_CLEARANCE - 0.5)
    b = r["bench"]
    _row("Вращение с рельефом",
         "не меньше %d в любую с, пропусков %d" % (b["min_window"],
                                                   b["drops"]),
         "не меньше 55", b["min_window"] >= 55 and b["valid"])
    i = r["imagery"]
    if i["missing"]:
        _row("Космоснимки", "нет подключения %s" % IMAGERY, "дыр 0",
             False)
    else:
        _row("Космоснимки",
             "дыр %d, ошибок %d, подпись %s" % (
                 i["holes"], i["errors"],
                 "сменилась" if i["attribution"] else "НЕ сменилась"),
             "дыр 0, ошибок 0",
             i["holes"] == 0 and i["errors"] == 0 and i["attribution"]
             and i["loaded"] and i["valid"])
    a = r["atmosphere"]
    _row("Атмосфера",
         "гало %s, космос %s, небо %s" % (
             "есть" if a["halo"] else "НЕТ",
             "чёрный" if a["space"] else "НЕ чёрный",
             "голубое" if a["sky"] else "НЕТ"),
         "гало, небо у горизонта",
         a["halo"] and a["space"] and a["sky"] and a["valid"])
    errors = getattr(plugin, "_open_errors", [])
    view = plugin.window.view
    print("")
    print("ошибок Python за приёмку: %d, проба журнала дошла: %s"
          % (len(errors), getattr(plugin, "_open_probe", False)))
    for line in sorted(set(errors))[:5]:
        print("  ", line)
    print("ошибок OpenGL: %s" % (dict(view.gl_errors) or 0))
    print("снимки: %s" % os.path.join(SHOTS, "planetx_phase1_*.png"))
    print("длительность приёмки %.0f с" % (time.monotonic() - run.started))
