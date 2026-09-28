# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Проверка шага 0.8: навигация мышью в окне глобуса.

События мыши посылаются в сам виджет, мышь пользователя не трогается.
Запуск через мост в два вызова, окно должно быть открыто:

    import runpy
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_nav.py")["start"]()
    runpy.run_path(r"C:\\Dev\\planetx\\tools\\qgis_nav.py")["report"]()

Первый вызов хватает Землю и тянет её, бросает с инерцией, делает три
щелчка колеса к точке и наклоняет вид средней кнопкой. Второй вызов
печатает итоги после того, как инерция и плавное приближение
отработали в цикле событий.
"""
import time

import numpy as np
import qgis.utils
from qgis.PyQt.QtCore import QEvent, QPoint, QPointF, Qt
from qgis.PyQt.QtGui import QMouseEvent, QWheelEvent
from qgis.PyQt.QtWidgets import QApplication

# runpy.run_path даёт новое пространство имён на каждый вызов, поэтому
# состояние между вызовами хранится на объекте плагина.
STATE = qgis.utils.plugins["planetx"].__dict__.setdefault("_nav_check", {})


def _enum(owner, scope, name):
    return getattr(getattr(owner, scope, owner), name)


LEFT = _enum(Qt, "MouseButton", "LeftButton")
MIDDLE = _enum(Qt, "MouseButton", "MiddleButton")
NONE = _enum(Qt, "MouseButton", "NoButton")
NOMOD = _enum(Qt, "KeyboardModifier", "NoModifier")


def _mouse(view, kind, x, y, button, buttons):
    local = QPointF(x, y)
    global_ = QPointF(view.mapToGlobal(QPoint(int(x), int(y))))
    event = QMouseEvent(_enum(QEvent, "Type", kind), local, global_,
                        button, buttons, NOMOD)
    QApplication.sendEvent(view, event)


def _wheel(view, x, y, notches):
    local = QPointF(x, y)
    global_ = QPointF(view.mapToGlobal(QPoint(int(x), int(y))))
    event = QWheelEvent(local, global_, QPoint(0, 0),
                        QPoint(0, int(120 * notches)), NONE, NOMOD,
                        _enum(Qt, "ScrollPhase", "NoScrollPhase"), False)
    QApplication.sendEvent(view, event)


def _device(view, x, y):
    ratio = view.devicePixelRatioF()
    return np.array([x * ratio, y * ratio])


def start():
    from planetx.core import navigation as nav

    view = qgis.utils.plugins["planetx"].window.view
    cam = view.camera
    view.navigator.stop()
    cx, cy = view.width() / 2.0, view.height() / 2.0

    # Захват и перетаскивание, пять шагов по 16 мс.
    x, y = cx + 50, cy + 30
    _mouse(view, "MouseButtonPress", x, y, LEFT, LEFT)
    grab = view.navigator.grab
    errors = []
    for i in range(1, 6):
        time.sleep(0.016)
        x, y = cx + 50 + 20 * i, cy + 30 - 8 * i
        _mouse(view, "MouseMove", x, y, NONE, LEFT)
        got = nav.pixel_at(cam, cam.eye, cam.rotation, grab)
        errors.append(float(np.linalg.norm(got - _device(view, x, y))))
    _mouse(view, "MouseButtonRelease", x, y, LEFT, NONE)
    STATE["grab_errors"] = errors
    STATE["inertia_started"] = view.navigator.inertia is not None
    STATE["release_pose"] = (view.navigator.pose.lat, view.navigator.pose.lon)
    STATE["frame_at_release"] = view.frame
    STATE["t_release"] = time.monotonic()
    print("захват: ошибка положения под курсором, пикселей, по шагам",
          [round(e, 4) for e in errors])
    print("инерция началась:", STATE["inertia_started"])


def zoom_and_turn():
    """Колесо и наклон, после того как инерция кончилась."""
    from planetx.core import navigation as nav

    view = qgis.utils.plugins["planetx"].window.view
    cam = view.camera
    cx, cy = view.width() / 2.0, view.height() / 2.0
    x, y = cx - 60, cy + 20
    point = nav.ground_under(cam, *_device(view, x, y))
    STATE["wheel"] = (x, y, point, view.navigator.pose.distance)
    _wheel(view, x, y, 3)
    print("три щелчка колеса к точке", (x, y))


def turn():
    view = qgis.utils.plugins["planetx"].window.view
    cx, cy = view.width() / 2.0, view.height() / 2.0
    before = (view.navigator.pose.heading, view.navigator.pose.tilt)
    _mouse(view, "MouseButtonPress", cx, cy, MIDDLE, MIDDLE)
    _mouse(view, "MouseMove", cx + 40, cy - 80, NONE, MIDDLE)
    _mouse(view, "MouseButtonRelease", cx + 40, cy - 80, MIDDLE, NONE)
    after = (view.navigator.pose.heading, view.navigator.pose.tilt)
    print("азимут и наклон до", before, "после", after)


def report():
    from planetx.core import navigation as nav

    view = qgis.utils.plugins["planetx"].window.view
    cam = view.camera
    pose = view.navigator.pose
    if STATE.get("release_pose"):
        lat0, lon0 = STATE["release_pose"]
        print("инерция: кадров после отпускания %d, сдвиг точки взгляда "
              "%.3f° по широте и %.3f° по долготе, идёт ли ещё: %s"
              % (view.frame - STATE["frame_at_release"], pose.lat - lat0,
                 pose.lon - lon0, view.navigator.inertia is not None))
    if STATE.get("wheel"):
        x, y, point, d0 = STATE["wheel"]
        got = nav.pixel_at(cam, cam.eye, cam.rotation, point)
        print("колесо: расстояние %.0f -> %.0f м, отношение %.4f "
              "(ожидается %.4f), точка под курсором сдвинулась на %.4f "
              "пикселя" % (d0, pose.distance, pose.distance / d0, 0.8 ** 3,
                           np.linalg.norm(got - _device(view, x, y))))
    print("крен:", nav.roll(cam, pose))
    print("высота камеры %.0f м, тайлов в кадре %d, уровни %s"
          % (view.altitude(), view.drawn,
             dict(sorted(view.drawn_levels.items()))))
