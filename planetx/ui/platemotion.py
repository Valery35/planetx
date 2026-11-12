# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Скорости плит NNR-MORVEL56 (core/platemotion.py), файл
data/plate_motion.json. Стрелки - свои линии глобуса у вида, числа мм/год -
надписи. Строка реестра каталога (core/rows.py) и исполнитель.
"""
import os
import time

from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import platemotion as motion_core
from ..core.features import Shape
from ..core.places import Place as MarkPlace
from ..core.rows import Row
from ..i18n import tr

KEY = "platemotion"
DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data", "plate_motion.json")
# Стрелки: цвет и толщина, выбор помощника, утверждает автор.
COLOR = (255, 225, 60, 235)
WIDTH = 1.8
# Номера надписей чисел стрелок, отрицательные - свои метки глобуса.
MARK_BASE = -700000


class MotionTool(QObject):
    """Модель скоростей, читается при первом включении, стрелки у вида."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.model = None
        self.arrows = []
        self.numbers = []
        self.key = None

    shown_key = None

    def on(self):
        # Зовётся и при создании окна, до чтения строк «Слоёв».
        window = self.window
        return window.planet.earth \
            and bool(getattr(window, "extras", {}).get(KEY)) \
            and window.view.sky_view is None and self.model is not None

    def turn(self, key, on):
        window = self.window
        if on and self.model is None:
            try:
                with open(DATA, encoding="utf-8") as fh:
                    self.model = motion_core.read(fh.read())
            except (OSError, ValueError, KeyError) as error:
                journal.note("platemotion: {}".format(error))
                window.message = (tr("Скорости плит не прочитаны: {error}",
                                     error=str(error)), time.monotonic())
                window._show_state()
                return False
        self.key = None
        self.view_changed()
        return True

    def view_changed(self):
        """Стрелки строятся заново, когда меняется шаг узлов или вид
        уходит на шаг, как сетка координат."""
        window = self.window
        if not self.on():
            if self.arrows or self.numbers:
                self.arrows = []
                self.numbers = []
                self.key = None
                window._set_geo_marks()
                window._refresh_shapes()
            return
        pose = window.view.navigator.pose
        width = window._view_width()
        step = motion_core.step_for(width)
        key = (step, round(pose.lat / step), round(pose.lon / step))
        if key == self.key:
            return
        self.key = key
        arrows = []
        numbers = []
        for n, (lat, lon, speed, _, lines) in enumerate(
                motion_core.arrows(self.model, pose.lat, pose.lon, width)):
            for line in lines:
                arrows.append(Shape("line", line, color=COLOR, width=WIDTH))
            numbers.append(MarkPlace(MARK_BASE - n, "{:.0f}".format(speed),
                                     "grid", 1, lat, lon))
        self.arrows = arrows
        self.numbers = numbers
        window._set_geo_marks()
        window._refresh_shapes()

    def shapes(self):
        return list(self.arrows)

    def marks(self):
        return list(self.numbers)

    def place_values(self, lat, lon):
        """Строки скорости плиты группы «Место» окна «Объекты» или []."""
        if not self.on():
            return []
        found = self.model.velocity(lat, lon)
        if found is None:
            return []
        code, east, north = found
        speed, azimuth = motion_core.speed_azimuth(east, north)
        return [(tr("Плита"), "{} ({})".format(self.model.names[code], code)),
                (tr("Скорость плиты"), tr("{value} мм/год",
                                          value="{:.1f}".format(speed))),
                (tr("Направление"), "{:.0f}°".format(azimuth))]

    def credits(self):
        return [motion_core.ATTRIBUTION] if self.on() else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "seismic", lambda: (tr("Скорости плит"), tr(
        "Стрелки движения литосферных плит по модели NNR-MORVEL56 - "
        "скорость относительно среднего движения всех плит. Длина "
        "стрелки растёт со скоростью, число у её начала - мм/год. "
        "Тихоокеанская плита идёт на северо-запад около 70 мм/год, "
        "Евразийская - около 25. Окно «Объекты» показывает плиту, "
        "скорость и направление в точке.")), MotionTool,
        source="NNR-MORVEL56", colors=((255, 225, 60), (60, 60, 60)),
        words=("скорости плит", "движение плит", "дрейф",
               "дрейф континентов", "morvel", "plate motion"),
        after="faults"),
)
