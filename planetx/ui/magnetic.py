# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Магнитные полюса и линии склонения (core/geomag.py): полюса и их след
на год шкалы времени, изогоны поля, поле в точке. Модель IGRF-14
и таблицы полюсов - файлы модуля, gufm1 до 1900 года - файл профиля.
Строки реестра каталога (core/rows.py) и исполнитель.
"""
import math
import os
import time

from qgis.core import QgsApplication
from qgis.PyQt.QtCore import QObject

from .. import journal
from ..core import geomag
from ..core.features import Shape
from ..core.places import Place as MarkPlace
from ..core.rows import Row
from ..i18n import tr

POLES, DECL = "magpoles", "magdecl"
DATA = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "data")
# Магнитные полюса: цвета следа и точки. Выбор помощника, утверждает
# автор.
POLE_COLORS = {"north": (235, 70, 60, 255), "south": (70, 130, 235, 255)}
POLE_WIDTH = 2.0
# Линии склонения: восточное - красные, западное - синие, агона -
# зелёная толще. Подпись - у линии не короче LABEL_POINTS точек.
# Выбор помощника, утверждает автор.
DECL_EAST = (215, 70, 60, 220)
DECL_WEST = (60, 110, 215, 220)
DECL_ZERO = (40, 170, 70, 255)
DECL_WIDTH = 1.4
DECL_ZERO_WIDTH = 2.6
LABEL_POINTS = 8
FIRST = "1590-01-01"  # первый год таблицы NOAA
ATTRIBUTION = ("IGRF-14 IAGA, NOAA NCEI",
               "https://www.ncei.noaa.gov/products/"
               "wandering-geomagnetic-poles")
# Номера надписей значений склонения, отрицательные - свои метки.
MARK_BASE = -600000


class MagneticTool(QObject):
    """Модель поля и таблицы полюсов, читаются при первом включении."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.geomag = None  # (модель IGRF и gufm1, таблицы полюсов)
        self.cache = None  # (год, изогоны)
        self.decl_marks = []
        self.gufm_reply = None
        self.gufm_failed = False

    shown_key = None

    def _row_on(self, key):
        window = self.window
        return bool(getattr(window, "extras", {}).get(key)) \
            and getattr(window, "planet", None) is not None \
            and window.planet.earth and self.geomag is not None

    def poles_on(self):
        return self._row_on(POLES)

    def decl_on(self):
        return self._row_on(DECL)

    def on(self):
        """Полюса или линии склонения: шкала времени, подпись, пересчёт
        по году."""
        return self.poles_on() or self.decl_on()

    def turn(self, key, on):
        """Полюса на момент шкалы и их след с 1590 года, изогоны на год
        шкалы. Шкала времени открывается сама."""
        if on and not self._load():
            return False
        if key == DECL:
            self.cache = None
        window = self.window
        window._update_timebar()
        if on and window.planet.earth and window.timebar.known \
                and not window.timebar.shown():
            window.timebar.open_bar()
            window.toolbar.set_time_shown(True)
            window._time_range = window.timebar.range()
        window._refresh_shapes()
        return True

    def _load(self):
        """Модель поля и таблицы полюсов из файлов модуля, один раз."""
        if self.geomag is not None:
            return True
        try:
            with open(os.path.join(DATA, "igrf14coeffs.txt"),
                      encoding="ascii") as fh:
                model = geomag.parse_igrf(fh.read())
            with open(os.path.join(DATA, "magnetic_poles.json"),
                      encoding="utf-8") as fh:
                poles = geomag.parse_poles(fh.read())
            self.geomag = (geomag.Combined(model, self._read_gufm()), poles)
        except (OSError, ValueError, KeyError) as error:
            journal.note("magnetic poles: {}".format(error))
            window = self.window
            window.message = (tr("Магнитные полюса не прочитаны."),
                              time.monotonic())
            window._show_state()
            return False
        return True

    @staticmethod
    def gufm_path():
        return os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                            "gufm1.txt")

    def _read_gufm(self):
        """gufm1 из файла профиля или None - его ещё не скачивали."""
        try:
            with open(self.gufm_path(), encoding="ascii") as fh:
                return geomag.parse_gufm(fh.read())
        except (OSError, ValueError) as error:
            if os.path.exists(self.gufm_path()):
                journal.note("gufm1: {}".format(error))
            return None

    def want_gufm(self, year):
        """Поле до 1900 года - модель gufm1: файл скачивается один раз
        с сайта авторов в профиль QGIS, как группы спутников."""
        from ..net.overlay import fetch_bytes
        if self.geomag is None or year >= self.geomag[0].igrf.first \
                or self.geomag[0].gufm is not None \
                or self.gufm_reply is not None or self.gufm_failed:
            return
        self.gufm_reply = fetch_bytes(geomag.GUFM_URL, self._gufm_done)

    def _gufm_done(self, data, error):
        from .overpass import brief_error
        self.gufm_reply = None
        model = None
        if data is not None:
            try:
                model = geomag.parse_gufm(bytes(data).decode("ascii"))
                os.makedirs(os.path.dirname(self.gufm_path()),
                            exist_ok=True)
                with open(self.gufm_path(), "wb") as fh:
                    fh.write(bytes(data))
            except (ValueError, UnicodeDecodeError, OSError) as problem:
                error = str(problem)
        window = self.window
        if model is None:
            self.gufm_failed = True
            journal.note("gufm1: {}".format(error))
            window.message = (tr("Поле до 1900 года не загружено: {error}",
                                 error=brief_error(error or "")),
                              time.monotonic())
            window._show_state()
            return
        self.geomag[0].gufm = model
        self.cache = None
        window._refresh_shapes()
        window._refresh_identified()
        window._show_attribution()

    def year(self):
        """Год с дробью для полюсов и поля: правый бегунок открытой
        шкалы времени, без неё - часы компьютера."""
        span = getattr(self.window, "_time_range", None)
        if span is not None and math.isfinite(span[1]):
            return geomag.year_of(span[1])
        return geomag.year_of(time.time())

    def start(self):
        """Год левого бегунка - начало следа полюсов. None - шкала
        закрыта или с одним бегунком, след идёт с 1590 года."""
        window = self.window
        span = getattr(window, "_time_range", None)
        if span is None or not math.isfinite(span[0]) \
                or window.timebar.track.point:
            return None
        return geomag.year_of(span[0])

    def _decl_shapes(self):
        """Линии равного склонения на год шкалы и подписи значений.
        Линии считаются заново при смене целого года - поле за год
        меняется на доли градуса, расчёт около 0.2 с."""
        if not self.decl_on():
            if self.decl_marks:
                self.decl_marks = []
                self.window._set_geo_marks()
            return []
        model, _ = self.geomag
        year = int(math.floor(self.year()))
        self.want_gufm(year)
        if self.cache is None or self.cache[0] != year:
            # До 1900 года - gufm1, пока его нет - линий нет. После конца
            # IGRF - линии её последнего года.
            year_in = min(year, model.last)
            coeffs = model.at(year_in)
            if coeffs is None:
                self.decl_marks = []
                self.window._set_geo_marks()
                return []
            lines = geomag.isogonic_lines(*geomag.declination_grid(
                coeffs, model.nmax_at(year_in)))
            self.cache = (year, lines)
        shapes = []
        marks = []
        for n, (level, points) in enumerate(self.cache[1]):
            if level == 0.0:
                color, width = DECL_ZERO, DECL_ZERO_WIDTH
            else:
                color = DECL_EAST if level > 0 else DECL_WEST
                width = DECL_WIDTH
            shapes.append(Shape("line", points, color=color, width=width))
            if len(points) >= LABEL_POINTS:
                lat, lon = points[len(points) // 2]
                text = "0°" if level == 0.0 else "{:+.0f}°".format(level)
                marks.append(MarkPlace(MARK_BASE - n, text, "grid", 1,
                                       lat, lon))
        self.decl_marks = marks
        self.window._set_geo_marks()
        return shapes

    def shapes(self):
        """След и точка каждого полюса на год шкалы, след - от левого
        бегунка до правого. Линии склонения - тоже здесь."""
        shapes = self._decl_shapes()
        if not self.poles_on():
            return shapes
        model, poles = self.geomag
        year = self.year()
        start = self.start()
        names = {"north": tr("Северный магнитный полюс, {year}"),
                 "south": tr("Южный магнитный полюс, {year}")}
        for key in ("north", "south"):
            track = poles[key]
            year_in = min(max(year, track[0][0]), model.last)
            point = geomag.pole(model, track, year_in)
            path = geomag.trail(track, year_in, start)
            if point is not None:
                path.append(point)
            color = POLE_COLORS[key]
            if len(path) > 1:
                shapes.append(Shape("line", path, color=color,
                                    width=POLE_WIDTH))
            if point is not None:
                shapes.append(Shape("point", [point], color=color,
                                    name=names[key].format(
                                        year=int(year_in))))
        return shapes

    def marks(self):
        return list(self.decl_marks)

    def time_changed(self):
        if self.on():
            self.window._refresh_shapes()

    def time_marks(self):
        """Охват шкалы времени: полюса - с 1590 года по сегодня."""
        from ..core import when
        if not self.on():
            return []
        return [when.stamp(FIRST), when.stamp(when.text(time.time()))]

    def credits(self):
        if not self.on():
            return []
        parts = [ATTRIBUTION]
        if self.geomag[0].gufm is not None:
            parts.append(geomag.GUFM_ATTRIBUTION)
        return parts

    def identify(self, lat, lon, tolerance=0.0):
        """Группа «Магнитное поле» окна «Объекты»: поле в точке на год
        шкалы."""
        from .identify import Group
        if not self.on():
            return []
        model, _ = self.geomag
        year = self.year()
        self.want_gufm(year)
        found = geomag.field(model, lat, lon, year)
        if found is None:
            values = [(tr("Год"), str(int(year))),
                      (tr("Модель"), tr("gufm1 с 1590 года, IGRF-14 с 1900 "
                                        "по 2030 год"))]
        else:
            name = "gufm1" if model.part(year) is model.gufm else "IGRF-14"
            values = [
                (tr("Год"), str(int(year))),
                (tr("Склонение"), "{:+.1f}°".format(found["declination"])),
                (tr("Наклонение"), "{:+.1f}°".format(found["inclination"])),
                (tr("Полная напряжённость"),
                 tr("{value} нТл", value="{:.0f}".format(found["total"]))),
                (tr("Горизонтальная составляющая"),
                 tr("{value} нТл", value="{:.0f}".format(
                     found["horizontal"]))),
                (tr("Модель"), name)]
        return [(Group(tr("Магнитное поле")),
                 [(tr("Поле в точке"), values, None)])]

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(POLES, "geophysics", lambda: (tr("Магнитные полюса"), tr(
        "Северный и южный магнитные полюса - точки, где стрелка "
        "компаса стоит отвесно, - на год шкалы времени и их путь "
        "с 1590 года по данным NOAA NCEI. Шкала открывается сама, "
        "бегунок ведёт полюса по годам. Щелчок по глобусу в режиме "
        "«Определить объекты» показывает склонение, наклонение "
        "и напряжённость поля в точке на тот же год по моделям "
        "gufm1 и IGRF-14, с 1590 по 2030 год.")), MagneticTool,
        source="NOAA NCEI, IGRF-14",
        colors=((235, 70, 60), (70, 130, 235)),
        words=("магнитный полюс", "магнитные полюса", "компас",
               "геомагнетизм", "igrf", "magnetic pole", "compass"),
        after="volcanoes"),
    Row(DECL, "geophysics", lambda: (tr("Линии склонения"), tr(
        "Линии равного магнитного склонения - угла между стрелкой "
        "компаса и направлением на север - через 10° на год шкалы "
        "времени по моделям IGRF-14 с 1900 года и gufm1 с 1590 "
        "года, gufm1 скачивается при первом показе. Красные - "
        "склонение восточное, синие - западное, зелёная - нулевое. "
        "У магнитных полюсов линии сходятся.")), MagneticTool,
        source="IGRF-14",
        colors=((215, 70, 60), (40, 170, 70), (60, 110, 215)),
        words=("склонение", "изогоны", "линии склонения", "агона",
               "магнитное склонение", "declination", "isogonic"),
        after=POLES),
)
