# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Картинки руководства в отдельном QGIS. Запускается при старте QGIS.

    set PLANETX_LANG=ru
    qgis.bat --profiles-path %TEMP%\\planetx_stress --code
        tools\\qgis_figures.py

Язык модуля задаёт PLANETX_LANG (ru или en). Картинки ложатся
в doc/figures/<язык>: окно глобуса над Пермью, угол с инструментами
управления, окна «Свойства вида» и свойств метки, 3D-здания в центре
Перми. Глобус ждёт загрузки
тайлов, но не дольше WAIT секунд. Свои метки сценарий ставит
в отдельную папку и в конце удаляет. QGIS пользователя не трогается,
в конце QGIS закрывается.
"""
import faulthandler
import json
import os
import sys
import time

ROOT = r"C:\Dev\planetx"
sys.path.insert(0, ROOT)
TEMP = os.environ.get("TEMP", ".")
LANG = os.environ.get("PLANETX_LANG", "ru")
OUT_DIR = os.path.join(ROOT, "doc", "figures", LANG)
CRASH = open(os.path.join(TEMP, "planetx_figures_crash.txt"), "w",
             encoding="utf-8")
faulthandler.enable(CRASH, all_threads=True)

from qgis.core import QgsApplication, QgsProject  # noqa: E402
from qgis.PyQt.QtCore import QTimer  # noqa: E402
from qgis.utils import iface  # noqa: E402

WAIT = 60.0  # секунд на загрузку тайлов вида
BUILDINGS_WAIT = 120.0  # секунд на загрузку зданий
JPEG_WIDTH = 1400  # ширина снимка окна в руководстве
result = {"lang": LANG, "files": [], "errors": []}
state = {}


def save(image, name, jpeg=False):
    path = os.path.join(OUT_DIR, name)
    if jpeg:
        from qgis.PyQt.QtCore import Qt
        image = image.scaledToWidth(
            JPEG_WIDTH, getattr(getattr(Qt, "TransformationMode", Qt),
                                "SmoothTransformation"))
        image.save(path, "JPG", 85)
    else:
        image.save(path, "PNG")
    result["files"].append([name, image.width(), image.height()])


def finish():
    with open(os.path.join(TEMP, "planetx_figures.json"), "w",
              encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=1)
    if "places" in state:
        state["window"].myplaces.remove(state["places"])
    if "plugin" in state:
        state["plugin"].unload()
    QgsProject.instance().clear()
    QgsApplication.instance().exit(0)


def start():
    os.makedirs(OUT_DIR, exist_ok=True)
    from planetx import i18n
    i18n.set_language(LANG)
    from planetx.core.features import Shape
    from planetx.core.navigation import Pose
    from planetx.plugin import PlanetXPlugin
    plugin = PlanetXPlugin(iface)
    plugin.initGui()
    plugin.run()
    window = plugin.window
    state["plugin"] = plugin
    state["window"] = window
    window.showNormal()
    window.resize(1600, 930)
    from planetx.net.overlay import BORDERS, PLACES, ROADS
    window.set_line_groups(set(window.state()["groups"])
                           | {BORDERS, PLACES, ROADS})
    store = window.myplaces
    ru = LANG == "ru"
    folder = store.add_folder("Пермь" if ru else "Perm")
    state["places"] = folder
    store.add(Shape("point", [(58.0105, 56.2294)],
                    name="Моя метка 1" if ru else "My placemark 1",
                    height=300.0, extrude=True), folder=folder)
    store.add(Shape("line", [(58.02, 56.10), (58.05, 56.20), (58.03, 56.32)],
                    color=(255, 214, 0, 255), width=3.0,
                    name="Мой путь 1" if ru else "My path 1"),
              folder=folder)
    window.panel.select_place(folder)
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.0, 56.22, 22000.0, 20.0, 55.0))
    window.navpad.near = True  # органы целиком, как у курсора
    state["started"] = time.monotonic()
    QTimer.singleShot(3000, wait_tiles)


def wait_tiles():
    view = state["window"].view
    view._heartbeat()
    spent = time.monotonic() - state["started"]
    if view.load_missing and spent < WAIT:
        QTimer.singleShot(1000, wait_tiles)
        return
    result["load_missing"] = view.load_missing
    result["seconds"] = round(spent, 1)
    QTimer.singleShot(1500, shoot)


def shoot():
    window = state["window"]
    try:
        image = window.grab().toImage()
        save(image, "window.jpg", jpeg=True)
        view = window.view
        pad = window.navpad
        ratio = image.width() / float(window.width())
        corner = pad.mapTo(window, pad.rect().topLeft())
        margin = 16
        crop = image.copy(int((corner.x() - margin) * ratio),
                          int((corner.y() - margin) * ratio),
                          int((pad.width() + 2 * margin) * ratio),
                          int((pad.height() + 2 * margin) * ratio))
        save(crop, "navpad.png")
        # Свойства вида снимаются с умолчанием, органы у угла вида.
        pad.near = False
        window._show_properties()
        dialog = window.properties
        QgsApplication.processEvents()
        save(dialog.grab().toImage(), "properties.png")
        dialog.close()
        path = [p for p in window.myplaces.places
                if p.shape.kind == "line"
                and p.folder == state["places"]][0]
        window._open_place_properties(path)
        props = window.prop_dialogs[path.key]
        QgsApplication.processEvents()
        save(props.grab().toImage(), "placeprops.png")
        props.reject()
        view.update()
    except (AttributeError, IndexError, KeyError, RuntimeError,
            TypeError) as error:
        result["errors"].append(repr(error))
        QTimer.singleShot(500, finish)
        return
    QTimer.singleShot(500, buildings_start)


def buildings_start():
    # 3D-здания в центре Перми с 1.5 км, наклон 60°.
    from planetx.core.navigation import Pose
    window = state["window"]
    window.navpad.near = False
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(58.0105, 56.2294, 1500.0, 30.0, 60.0))
    window.set_extra("buildings", True)
    state["started"] = time.monotonic()
    QTimer.singleShot(3000, buildings_wait)


def buildings_wait():
    window = state["window"]
    view = window.view
    view._heartbeat()
    spent = time.monotonic() - state["started"]
    if view.load_missing and spent < BUILDINGS_WAIT:
        QTimer.singleShot(1000, buildings_wait)
        return
    result["buildings_missing"] = view.load_missing
    result["buildings_drawn"] = view.buildings.drawn
    save(view.grabFramebuffer(), "buildings.jpg", jpeg=True)
    window.set_extra("buildings", False)
    QTimer.singleShot(500, profile_start)


def profile_start():
    # Линейка и профиль высот пути через Эльбрус.
    from planetx.core.navigation import Pose
    window = state["window"]
    nav = window.view.navigator
    nav.stop()
    nav.set_pose(Pose(43.35, 42.445, 30000.0, 0.0, 40.0))
    window._open_ruler()
    window.ruler_dialog.tabs.setCurrentIndex(1)
    for lat, lon in ((43.31, 42.40), (43.3499, 42.4453), (43.39, 42.49)):
        window.ruler.add(lat, lon)
    state["started"] = time.monotonic()
    QTimer.singleShot(2000, profile_wait)


def profile_wait():
    window = state["window"]
    ready = window.ruler.values(rubber=False)["ground_ready"]
    if not ready and time.monotonic() - state["started"] < WAIT:
        QTimer.singleShot(1000, profile_wait)
        return
    result["profile_ready"] = ready
    save(window.ruler_dialog.grab().toImage(), "ruler.png")
    window._ruler_profile()
    dialog = window.profile_dialog
    QgsApplication.processEvents()
    save(dialog.grab().toImage(), "profile.png")
    dialog.close()
    window.ruler_dialog.close()
    QTimer.singleShot(500, demo_start)


def demo_start():
    # Демо «Пермь» со шкалой времени на середину прогулки.
    window = state["window"]
    # Метки сценария картинок в кадре демо не нужны.
    store = window.myplaces
    store.set_visible_many({key: False for key in store.with_contents(
        [state["places"]])})
    state["demo"] = window.open_demo()
    state["started"] = time.monotonic()
    QTimer.singleShot(3000, demo_wait)


def demo_wait():
    import calendar
    window = state["window"]
    view = window.view
    view._heartbeat()
    spent = time.monotonic() - state["started"]
    busy = view.navigator.flight is not None or view.load_missing
    if busy and spent < BUILDINGS_WAIT:
        QTimer.singleShot(1000, demo_wait)
        return
    result["demo_missing"] = view.load_missing
    lo = calendar.timegm((2026, 9, 30, 6, 30, 0))
    window.timebar.set_range(lo, lo + 5400.0)
    QgsApplication.processEvents()
    view.repaint()
    save(window.grab().toImage(), "demo.jpg", jpeg=True)
    if state.get("demo"):
        window.myplaces.remove(state["demo"])
    window.set_extra("buildings", False)
    QTimer.singleShot(500, finish)


QTimer.singleShot(3000, start)
