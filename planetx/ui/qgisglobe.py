# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Мост к встроенному глобусу QGIS: вид туда и обратно.

Режим глобуса трёхмерных видов QGIS появился в 3.44. Вид с именем
VIEW_NAME заводится один раз, камера ставится по позе PlanetX, обратно
берутся точка взгляда, расстояние, азимут и наклон. Перед вызовами
грузится модуль qgis._3d: без него QGIS падает, когда sip переводит
Qgs3DMapCanvas в объект Python.
"""
import importlib

import numpy as np
from qgis.core import Qgis, QgsProject
from qgis.utils import iface

from ..core import ellipsoid
from ..i18n import tr

VIEW_NAME = "PlanetX"
MIN_VERSION = 34400


def available():
    """В этом QGIS есть глобус трёхмерных видов."""
    if Qgis.versionInt() < MIN_VERSION or not hasattr(Qgis, "SceneMode") \
            or not hasattr(iface, "createNewMapCanvas3D"):
        return False
    try:
        importlib.import_module("qgis._3d")
    except ImportError:
        return False
    return True


def _canvases():
    """Вид глобуса: сначала свой, потом любой другой."""
    found = [canvas for canvas in iface.mapCanvases3D()
             if canvas.mapSettings().sceneMode() == Qgis.SceneMode.Globe]
    found.sort(key=lambda c: c.objectName() != VIEW_NAME)
    return found


def _refused(window, text):
    window.panel.set_answer(text)
    return None


def open_view(window):
    """Открыть глобус QGIS с камерой вида PlanetX. Вернуть вид или None."""
    if not available():
        return _refused(window, tr(
            "Глобус трёхмерных видов есть в QGIS с версии 3.44."))
    if not window.planet.earth or window.view.sky_view is not None:
        return _refused(window, tr("Глобус QGIS показывает только Землю."))
    if not QgsProject.instance().mapLayers():
        return _refused(window, tr(
            "Глобус QGIS не открывается в пустом проекте. Добавьте слой."))
    found = _canvases()
    canvas = found[0] if found else iface.createNewMapCanvas3D(
        VIEW_NAME, Qgis.SceneMode.Globe)
    if canvas is None:
        return _refused(window, tr(
            "QGIS не открыл глобус. Причина - в полосе сообщений QGIS."))
    pose = window.view.navigator.pose
    control = canvas.cameraController()
    control.resetGlobe(pose.distance, pose.lat, pose.lon)
    control.globeUpdatePitchAngle(pose.tilt)
    # Угол поворота QGIS идёт против азимута.
    control.globeUpdateHeadingAngle(-pose.heading)
    return canvas


def read_pose(canvas):
    """Широта, долгота, расстояние, азимут и наклон глобуса QGIS."""
    control = canvas.cameraController()
    point = control.lookingAtMapPoint()
    lat, lon, _ = ellipsoid.ecef_to_geodetic(
        np.array((point.x(), point.y(), point.z()), dtype=np.float64))
    pose = control.cameraPose()
    return (float(lat), float(lon), pose.distanceFromCenterPoint(),
            -pose.headingAngle() % 360.0, pose.pitchAngle())


def take_view(window):
    """Перелёт PlanetX к виду глобуса QGIS. Вернуть True, если он есть."""
    if not available():
        return bool(_refused(window, tr(
            "Глобус трёхмерных видов есть в QGIS с версии 3.44.")))
    if not window.planet.earth:
        return bool(_refused(window, tr(
            "Глобус QGIS показывает только Землю.")))
    found = _canvases()
    if not found:
        return bool(_refused(window, tr("Глобус QGIS не открыт.")))
    window.view.fly_pose(*read_pose(found[0]))
    return True
