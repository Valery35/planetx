# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Поиск падения QGIS 4 после поиска места. Запускается при старте QGIS.

    qgis.bat --profiles-path %TEMP%\\planetx_stress --code
        tools\\qgis_crash_search.py

Профиль отдельный, QGIS пользователя не трогается. Вариант задаёт
переменная PLANETX_SCENARIO:

- full - щелчок с опросом и поиск по названию, как у автора
  27 сентября 2026 года;
- nomark - то же, но метка на глобусе не ставится;
- nosearch - щелчки и метки без сетевого поиска;
- fetch - только запросы к Nominatim без окна глобуса.

Шаги и стек при падении пишутся в %TEMP%\\planetx_stress.txt. Запросы
к Nominatim идут с разными словами, раз в STEP мс, в пределах правил
сервиса. В конце QGIS закрывается.
"""
import faulthandler
import os
import sys

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
LOG = open(os.path.join(os.environ.get("TEMP", "."), "planetx_stress.txt"),
           "w", encoding="utf-8")
faulthandler.enable(LOG, all_threads=True)

from qgis.core import QgsApplication  # noqa: E402
from qgis.PyQt.QtCore import QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

SCENARIO = os.environ.get("PLANETX_SCENARIO", "full")
STEP = 2500  # мс между шагами
QUERIES = ["Кунгур", "59.593416, 56.806003, высота 207 м", "Соликамск",
           "Чусовой", "Эльбрус", "Губаха", "Березники", "Лысьва",
           "Кудымкар", "Оса", "Чайковский", "Верещагино"]
state = {"n": 0}


def mark(text):
    LOG.write(text + "\n")
    LOG.flush()


def open_globe():
    project = os.environ.get("PLANETX_PROJECT")
    if project:
        # Проект только читается, сценарий его не сохраняет.
        from qgis.core import QgsProject
        mark("project %s" % QgsProject.instance().read(project))
    from planetx.plugin import PlanetXPlugin
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    # Перезагрузки модуля, как у tools/qgis_reload.py: выгрузка, снятие
    # модулей из sys.modules, новый импорт.
    for n in range(int(os.environ.get("PLANETX_RELOADS", "0"))):
        plugin.unload()
        for name in [m for m in sys.modules
                     if m == "planetx" or m.startswith("planetx.")]:
            del sys.modules[name]
        from planetx.plugin import PlanetXPlugin
        plugin = PlanetXPlugin(iface)
        plugin.initGui()
        plugin.run()
        mark("reloaded %d" % n)
    state["plugin"] = plugin
    window = plugin.window
    window.showNormal()
    if SCENARIO == "nomark":
        window._mark = lambda *args: None
    if os.environ.get("PLANETX_GROUPS") == "1":
        from planetx.net.overlay import VECTOR_GROUPS
        window.set_line_groups(set(VECTOR_GROUPS))
    window.toolbar.identify.setChecked(True)
    mark("opened " + SCENARIO)


def fetch_step(n):
    from planetx.core.geocode import search_url
    from planetx.net.overlay import fetch_json
    state.setdefault("replies", []).append(fetch_json(
        search_url(QUERIES[n], "ru"),
        lambda data, error, n=n: mark("answer %d %s" % (
            n, len(data) if data is not None else error))))


def step():
    n = state["n"]
    if n >= len(QUERIES):
        mark("done")
        if "plugin" in state:
            state["plugin"].unload()
        QgsApplication.instance().exit(0)
        return
    state["n"] = n + 1
    mark("step %d" % n)
    if SCENARIO == "fetch":
        fetch_step(n)
    else:
        window = state["plugin"].window
        cam = window.view.camera
        window.view.clicked.emit(cam.width * 0.4, cam.height * 0.6)
        mark("clicked %d" % n)
        if SCENARIO != "nosearch":
            window.place.setText(QUERIES[n])
            window.place.returnPressed.emit()
            mark("searched %d" % n)
    QTimer.singleShot(STEP, step)


def exit_only():
    """Вариант exit: проект, глобус по PLANETX_GLOBE, выход."""
    project = os.environ.get("PLANETX_PROJECT")
    if project:
        mark("path %r exists %s" % (project, os.path.exists(project)))
        from qgis.core import QgsProject
        mark("project %s" % QgsProject.instance().read(project))
    if os.environ.get("PLANETX_GLOBE", "1") == "1":
        open_globe()
    mark("waiting")

    def leave():
        if os.environ.get("PLANETX_UNLOAD", "1") == "1" and "plugin" in state:
            state["plugin"].unload()
            mark("unloaded")
        mark("exit")
        QgsApplication.instance().exit(0)
    QTimer.singleShot(10000, leave)


if SCENARIO == "exit":
    QTimer.singleShot(3000, exit_only)
elif SCENARIO == "fetch":
    QTimer.singleShot(3000, step)
else:
    QTimer.singleShot(3000, open_globe)
    QTimer.singleShot(8000, step)
