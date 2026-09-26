# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка: снятый слой не мелькает при отдалении после «Обновить».

Запускается через мост в два вызова, окно глобуса открыто, камера над
слоем, слой отмечен и применён, его картинки загружены:

import runpy; runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_stale.py",
                             init_globals={"LAYER_ID": "..."})
затем, через 5 с, печать builtins.planetx_stale.

Сценарий снимает отметку слоя без записи в проект, жмёт «Обновить»
и отдаляет камеру по таймеру. Каждый кадр считаются тайлы, которые
рисуют картинку прежнего наложения, хотя в момент обновления
на экране их не было. Такие тайлы и показывают снятый слой.
"""
import builtins

import qgis.utils
from qgis.PyQt.QtCore import QTimer

STEPS = 40  # шагов отдаления
FACTOR = 1.08  # во столько раз растёт расстояние за шаг
PERIOD = 60  # мс между шагами

window = qgis.utils.plugins["planetx"].window
view = window.view
result = {"frames": 0, "flash_frames": 0, "flash_tiles": 0, "done": False}
builtins.planetx_stale = result
before = set(view.selection.draw)


# Прежние картинки наложения: на момент запуска все картинки в памяти.
# Текстуры берутся из запаса повторно, поэтому прежней считается
# текстура, которая всё ещё стоит у своего тайла, а тайл новой
# картинки не получал.
old = {id(texture): key for key, texture in view.overlays.items()}
replaced = set()
original = view._overlay_items
original_add = view.add_overlay


def added(key, levels, extra=None):
    replaced.add(key)
    original_add(key, levels, extra)


def is_old(texture):
    key = old.get(id(texture))
    return key is not None and key not in replaced \
        and view.overlays.get(key) is texture


def recorded(sel, now):
    """То же, что _overlay_items вида, плюс счёт мелькания."""
    items = original(sel, now)
    count = sum(1 for key, (texture, _) in zip(sel.draw, items)
                if key not in before and is_old(texture))
    result["frames"] += 1
    if count:
        result["flash_frames"] += 1
        result["flash_tiles"] = max(result["flash_tiles"], count)
    return items


def frame():
    pass


window._shown.discard(LAYER_ID)  # noqa: F821, задаётся при запуске
window.refresh()
if globals().get("OLD_BEHAVIOUR"):
    # Подмена на прежнее поведение для проверки сторожа: прежние
    # картинки годны все.
    view.overlay_stale = set(view.overlays) | view.overlay_empty
    view._prune_overlays = False
view._overlay_items = recorded
view.overlay.loaded.disconnect(view.add_overlay)
view.overlay.loaded.connect(added)
view.frameSwapped.connect(frame)
steps = [0]


def step():
    steps[0] += 1
    pose = view.navigator.pose.copy()
    pose.distance *= FACTOR
    view.navigator.set_pose(pose)
    view.update()
    if steps[0] >= STEPS:
        timer.stop()
        view.frameSwapped.disconnect(frame)
        del view._overlay_items
        # Прежние картинки тайлов, ушедших с экрана, в памяти не остаются.
        result["stale_left"] = len(view.overlay_stale - set(
            view.selection.draw))
        result["done"] = True


timer = QTimer(window)
timer.timeout.connect(step)
timer.start(PERIOD)
builtins.planetx_stale_timer = timer
