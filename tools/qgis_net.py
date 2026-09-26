# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка шага 0.6: загрузчик тайлов.

Запускается через мост в два вызова:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_net.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_net.py")["report"]()

Набор - 50 тайлов уровня 12 вокруг Перми, приоритет убывает от центра.
Четыре прохода идут друг за другом:

1. весь набор, порядок запросов и не больше двух одновременно
2. весь набор повторно, все ответы из кэша
3. весь набор, потом оставить 5 старших, приходят ровно 5
4. весь набор, потом оставить 5 младших, два активных запроса снимаются
"""
import math
import time

import qgis.utils

PERM = (58.0105, 56.2294)
LEVEL = 12


def tile_set():
    from planetx.core.tiling import lonlat_to_tile
    cx, cy = lonlat_to_tile(*PERM, LEVEL)
    keys = [(LEVEL, cx + dx, cy + dy)
            for dy in range(-3, 4) for dx in range(-3, 4)]
    keys.append((LEVEL, cx + 4, cy))
    return [(key, -math.hypot(key[1] - cx, key[2] - cy)) for key in keys]


class Check:
    """Проходы идут по сигналам загрузчика, главный поток свободен."""

    def __init__(self):
        from planetx.net.loader import TileLoader
        self.items = tile_set()
        self.loader = TileLoader()
        self.loader.loaded.connect(self._got)
        self.loader.failed.connect(self._fail)
        self.loader.idle.connect(self._maybe_done)
        self.passes = []
        self.stage = 0
        self.t0 = time.monotonic()
        self._next()

    def _reset(self):
        self.loader.started.clear()
        self.loader.from_cache.clear()
        self.loader.aborted.clear()
        self.loader.max_seen = 0
        self.got = []
        self.errors = []
        self.t0 = time.monotonic()

    def _next(self):
        self.stage += 1
        self._reset()
        ordered = [k for k, _ in sorted(self.items, key=lambda i: -i[1])]
        if self.stage in (1, 2):
            self.loader.want_many(self.items)
        elif self.stage == 3:
            self.loader.want_many(self.items)
            self.loader.retain(ordered[:5])
        elif self.stage == 4:
            self.loader.want_many(self.items)
            self.loader.retain(ordered[-5:])
        else:
            return
        self._maybe_done()

    def _got(self, key, rgba, extra):
        self.got.append((key, rgba.shape))
        self._maybe_done()

    def _fail(self, key, error):
        self.errors.append((key, error))
        self._maybe_done()

    def _maybe_done(self):
        if self.stage > 4 or self.loader.busy():
            return
        loader = self.loader
        self.passes.append({
            "stage": self.stage,
            "seconds": round(time.monotonic() - self.t0, 2),
            "started": list(loader.started),
            "max_parallel": loader.max_seen,
            "loaded": len(self.got),
            "shapes": sorted({s for _, s in self.got}),
            "from_cache": sum(loader.from_cache.values()),
            "aborted": list(loader.aborted),
            "errors": list(self.errors),
        })
        self._next()


def start():
    plugin = qgis.utils.plugins["planetx"]
    plugin._net_check = Check()
    print("проверка загрузчика запущена")


def report():
    check = qgis.utils.plugins["planetx"]._net_check
    ordered = [k for k, _ in sorted(check.items, key=lambda i: -i[1])]
    print("проходов завершено: %d из 4" % len(check.passes))
    for p in check.passes:
        print("проход %d: %.2f с, запросов %d, одновременно до %d, "
              "получено %d, из кэша %d, снято %d, ошибок %d, размер %s"
              % (p["stage"], p["seconds"], len(p["started"]),
                 p["max_parallel"], p["loaded"], p["from_cache"],
                 len(p["aborted"]), len(p["errors"]), p["shapes"]))
        if p["errors"]:
            print("  ошибки:", p["errors"][:3])
    if check.passes:
        first = check.passes[0]["started"]
        print("порядок прохода 1 совпадает с приоритетом:",
              first == ordered)
    print("User-Agent:", check.loader.last_user_agent)
