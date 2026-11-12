# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Координатная сетка (core/graticule.py): параллели и меридианы
с подписями, экватор, тропики и полярные круги, есть у всех тел.
Строка реестра каталога (core/rows.py) и исполнитель.
"""
import math

from qgis.PyQt.QtCore import QObject

from ..core import graticule
from ..core.features import Shape
from ..core.places import Place as MarkPlace
from ..core.rows import Row
from ..i18n import tr

KEY = "grid"
GRID_COLOR = (220, 220, 220, 255)
GRID_WIDTH = 1.0
CIRCLE_COLOR = (255, 230, 0, 255)  # экватор, тропики, полярные круги


def circle_names():
    return {"equator": tr("Экватор"),
            "cancer": tr("Тропик Рака"),
            "capricorn": tr("Тропик Козерога"),
            "arctic": tr("Северный полярный круг"),
            "antarctic": tr("Южный полярный круг")}


def grid_text(kind, value, step):
    """Подпись линии сетки с полушарием."""
    angle = graticule.angle_text(value, step)
    if kind == "lat":
        if abs(value) < 1e-9:
            return angle
        return tr("{angle} с. ш.", angle=angle) if value > 0 \
            else tr("{angle} ю. ш.", angle=angle)
    value = graticule.normal_lon(value)
    if abs(value) < 1e-9 or abs(abs(value) - 180.0) < 1e-9:
        return graticule.angle_text(abs(value), step)
    return tr("{angle} в. д.", angle=angle) if value > 0 \
        else tr("{angle} з. д.", angle=angle)


class GridTool(QObject):
    """Сетка строится заново, только когда меняется шаг или точка
    взгляда уходит на шаг, а не каждый кадр."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.lines = []
        self.key = None

    shown_key = None

    def turn(self, key, on):
        self.key = None
        self.view_changed()
        return True

    def body_changed(self):
        self.key = None
        self.view_changed()

    def view_changed(self):
        window = self.window
        view = window.view
        if not getattr(window, "extras", {}).get(KEY):
            if self.lines or view.grid_marks:
                self.lines = []
                view.grid_marks = []
                self.key = None
                window._refresh_shapes()
            return
        pose = view.navigator.pose
        width = 2.0 * pose.distance * math.tan(
            math.radians(view.camera.fov_y) / 2.0)
        key = graticule.key(pose.lat, pose.lon, width)
        if key == self.key:
            return
        self.key = key
        step, found = graticule.lines(pose.lat, pose.lon, width)
        self.lines = [Shape("line", points, color=GRID_COLOR,
                            width=GRID_WIDTH) for _, _, points in found]
        self.lines += [
            Shape("line", points, color=CIRCLE_COLOR, width=GRID_WIDTH)
            for _, _, points in graticule.circles(pose.lat, pose.lon,
                                                  width)]
        marks = []
        for n, (lat, lon, kind, value) in enumerate(
                graticule.labels(pose.lat, pose.lon, width)):
            marks.append(MarkPlace(-100000 - n, grid_text(kind, value, step),
                                   "grid", 1, lat, graticule.normal_lon(lon)))
        names = circle_names()
        for n, (lat, lon, name) in enumerate(
                graticule.circle_labels(pose.lat, pose.lon, width)):
            marks.append(MarkPlace(-200000 - n, names[name], "circle", 1,
                                   lat, graticule.normal_lon(lon)))
        view.grid_marks = marks
        window._refresh_shapes()

    def shapes(self):
        return list(self.lines)

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "map", lambda: (tr("Координатная сетка"), tr(
        "Параллели и меридианы с подписями градусов, экватор, "
        "тропики и полярные круги. Шаг сетки меняется с высотой "
        "камеры.")), GridTool, colors=((250, 220, 60), (230, 230, 230)),
        words=("сетка", "градусы", "экватор", "graticule", "grid"),
        earth=False),
)
