# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Меню по правой кнопке на глобусе.

Щелчок правой кнопкой без сдвига открывает меню под курсором. Состав
зависит от того, что под ним: вершина рисуемого объекта, сохранённая
метка или просто поверхность. Перетаскивание правой кнопкой по-прежнему
приближает, двойной щелчок отдаляет.
"""
import numpy as np
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QCursor
from qgis.PyQt.QtWidgets import QApplication, QMenu

from ..core import editing
from ..core.ellipsoid import geodetic_to_ecef
from ..core.features import has_alts
from ..i18n import tr
from ..qt_compat import enum

HIT_PIXELS = 8.0  # логических пикселей до линии или контура
POINT_PIXELS = 14.0  # до значка точечной метки
KIND_MODE = {"point": "point", "line": "path", "polygon": "polygon"}
MAX_POINTS = 20000  # вершин у метки, с которыми она ещё ищется щелчком


def editable(place):
    """Можно ли править форму метки на глобусе: не тур и не 3D-объект."""
    return not place.tour and not has_alts(place.shape) \
        and place.kind in KIND_MODE


def place_under(window, px, py):
    """Видимая метка текущего тела под пикселем кадра или None. Точки
    и линии старше многоугольников, верхняя в списке старше нижней."""
    view = window.view
    ratio = view.devicePixelRatioF()
    best = None
    for place in window.myplaces.places:
        shape = place.shape
        if not place.visible or place.tour or not window._time_ok(place) \
                or place.body != window.planet.key \
                or not shape.points or len(shape.points) > MAX_POINTS:
            continue
        lats = np.array([p[0] for p in shape.points])
        lons = np.array([p[1] for p in shape.points])
        heights = np.asarray(shape.alts, dtype=np.float64) \
            if has_alts(shape) else view.store.heights_at(lats, lons)
        pixels, front = view.camera.project(
            geodetic_to_ecef(lats, lons, heights))
        radius = (POINT_PIXELS if place.kind == "point" else HIT_PIXELS) \
            * ratio
        if not editing.hit(place.kind, np.asarray(pixels).reshape(-1, 2),
                           front, px, py, radius):
            continue
        if place.kind != "polygon":
            return place
        if best is None:
            best = place
    return best


def show(window, px, py):
    """Собрать и показать меню для пикселя кадра (px, py)."""
    view = window.view
    if view.sky_view is not None:
        return
    menu = QMenu(window)
    menu.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
    drawer = window.drawer
    drawing = window._place_open() and bool(drawer.points)
    if drawing:
        found = window.draw_vertices.under(px, py)
        if found is not None and found[0] == editing.VERTEX:
            menu.addAction(tr("Удалить вершину")).triggered.connect(
                lambda *a, i=found[1]: drawer.remove(i))
        if drawer.mode != "point":
            if drawer.finished:
                menu.addAction(tr("Продолжить рисование")) \
                    .triggered.connect(lambda *a: drawer.resume())
            else:
                menu.addAction(tr("Завершить рисование")) \
                    .triggered.connect(lambda *a: drawer.finish())
        save = menu.addAction(tr("Сохранить"))
        save.setEnabled(drawer.shape(rubber=False) is not None)
        save.triggered.connect(lambda *a: window._save_place())
        menu.addAction(tr("Очистить")).triggered.connect(
            lambda *a: drawer.clear())
    else:
        place = place_under(window, px, py)
        if place is not None:
            title = menu.addAction(place.name or tr("Без названия"))
            title.setEnabled(False)
            menu.addAction(tr("Свойства…")).triggered.connect(
                lambda *a, p=place: window._open_place_properties(p))
    ground = window._ground(px, py)
    if ground is not None:
        lat, lon = ground
        if not menu.isEmpty():
            menu.addSeparator()
        if not drawing:
            menu.addAction(tr("Добавить метку здесь")).triggered.connect(
                lambda *a: window.add_place_here(lat, lon))
        menu.addAction(tr("Переместиться сюда")).triggered.connect(
            lambda *a: fly_here(view, lat, lon))
        menu.addAction(tr("Скопировать координаты")).triggered.connect(
            lambda *a: QApplication.clipboard().setText(
                "{:.6f}, {:.6f}".format(lat, lon)))
    if menu.isEmpty():
        menu.deleteLater()
        return
    menu.popup(QCursor.pos())


def fly_here(view, lat, lon):
    """Перелёт к точке с прежними высотой, азимутом и наклоном."""
    pose = view.navigator.pose
    view.fly_pose(lat, lon, pose.distance, pose.heading, pose.tilt)
