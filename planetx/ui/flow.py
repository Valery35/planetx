# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Струйки ветра и течений на глобусе (core/flow.py, render/flow.py).

Ветер - поле U, V на 10 м карты «Ветер» прогноза GFS (ui/weather.py),
струйки белые поверх раскраски скорости. Течения - строка «Течения»
витрины: геострофические течения NOAA CoastWatch по спутниковой
альтиметрии, сутки, сетка 0.25°, выборка через 0.5° (ERDDAP
nesdisSSH1day, около 4 МБ netCDF), струйки цветом скорости. Файл
читает GDAL в главном потоке.

Шаг частиц - таймер TICK, пока поле есть, окно видно и вид не небо.
Рамка частиц - вид с запасом (core.sync.view_box). При смене высоты
вида больше чем вдвое частицы рождаются заново в новой рамке, при
сдвиге рамка меняется, а частицы уходят из прежней сами.
"""
import math
import uuid

from qgis.PyQt.QtCore import QObject, QTimer, pyqtSignal

from .. import journal
from ..core import flow as core
from ..core.ellipsoid import ecef_to_geodetic
from ..core.sync import ground_size, view_box
from ..i18n import tr
from ..net.overlay import fetch_bytes

TICK = 40  # мс между шагами частиц
COUNTS = {"wind": 5000, "currents": 4000}
# Типичная скорость поля, м/с: она проходит долю core.flow.SHARE
# ширины вида за секунду.
TYPICAL = {"wind": 10.0, "currents": 0.3}
DISK_FROM = 3.0e6  # м высоты глаза, выше рамка - видимый диск
RESET_ZOOM = 2.0  # во сколько раз сменилась ширина вида - частицы заново
CURRENTS_URL = (
    "https://coastwatch.pfeg.noaa.gov/erddap/griddap/nesdisSSH1day.nc?"
    "ugos%5B(last)%5D%5B(-89.875):2:(89.875)%5D%5B(-179.875):2:(179.875)%5D,"
    "vgos%5B(last)%5D%5B(-89.875):2:(89.875)%5D%5B(-179.875):2:(179.875)%5D")
CURRENTS_ATTRIBUTION = ("Currents: NOAA CoastWatch, NESDIS SSH",
                        "https://coastwatch.pfeg.noaa.gov/erddap/griddap/"
                        "nesdisSSH1day.html")


def read_currents(data):
    """VectorGrid течений и день данных из netCDF ERDDAP или None."""
    from osgeo import gdal
    path = "/vsimem/planetx_currents_{}.nc".format(uuid.uuid4().hex)
    gdal.FileFromMemBuffer(path, bytes(data))
    try:
        bands, geo, day = [], None, ""
        for name in ("ugos", "vgos"):
            dataset = gdal.Open('NETCDF:"{}":{}'.format(path, name))
            if dataset is None:
                return None
            bands.append(dataset.GetRasterBand(1).ReadAsArray())
            geo = dataset.GetGeoTransform()
            day = (dataset.GetMetadataItem("NC_GLOBAL#time_coverage_end")
                   or "")[:10]
            dataset = None
        if any(band is None for band in bands):
            return None
        grid = core.VectorGrid(bands[0], bands[1], geo[0] + geo[1] / 2.0,
                               geo[3] + geo[5] / 2.0, abs(geo[1]))
        return grid, day
    finally:
        gdal.Unlink(path)


class FlowManager(QObject):
    """Поля и частицы струек окна глобуса. changed - пришли течения или
    ошибка."""

    changed = pyqtSignal()

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.view = window.view
        self.fields = {"wind": None, "currents": None}
        self.particles = {}
        self.widths = {}
        self.currents_day = ""
        self.currents_reply = None
        self.error = ""
        self.timer = QTimer(self)
        self.timer.setInterval(TICK)
        self.timer.timeout.connect(self._tick)

    def lines(self, kind):
        return self.view.flows[kind]

    # Поля.

    def set_wind(self, grid):
        """Поле ветра (VectorGrid) или None - струйки ветра сняты."""
        self._set_field("wind", grid)

    def set_currents(self, on):
        """Строка «Течения»: поле просится один раз за сеанс QGIS."""
        if not on:
            if self.currents_reply is not None:
                reply, self.currents_reply = self.currents_reply, None
                reply.abort()
                self.view.data_pending = max(0, self.view.data_pending - 1)
            self._set_field("currents", None, keep=True)
            return
        if self.fields["currents"] is not None:
            self._start("currents")
            return
        if self.currents_reply is not None:
            return
        self.view.data_pending += 1
        self.currents_reply = fetch_bytes(CURRENTS_URL, self._currents_done,
                                          prefer_cache=False)

    def _currents_done(self, data, error):
        if self.currents_reply is None:
            return  # снято выключением строки
        self.currents_reply = None
        self.view.data_pending = max(0, self.view.data_pending - 1)
        found = read_currents(data) if data else None
        if found is None:
            journal.note("currents: {}".format(error or "unreadable"))
            self.error = tr("Течения не загрузились, проверьте сеть "
                            "и включите строку снова.")
            self.changed.emit()
            return
        grid, self.currents_day = found
        self.error = ""
        self.fields["currents"] = grid
        if self.window.extras.get("currents"):
            self._start("currents")
        self.changed.emit()

    def _set_field(self, kind, grid, keep=False):
        if not keep:
            self.fields[kind] = grid
        if grid is None:
            self.particles.pop(kind, None)
            self.widths.pop(kind, None)
            self.lines(kind).clear()
            if not self.particles:
                self.timer.stop()
            self.view.update()
            return
        self._start(kind)

    def _start(self, kind):
        if kind not in self.particles:
            self.particles[kind] = core.Particles(COUNTS[kind])
        self.timer.start()

    # Шаг.

    def _box(self):
        view = self.view
        pose = view.navigator.pose
        width, height = ground_size(pose.distance, view.camera.fov_y,
                                    view.camera.aspect)
        # Высоко над Землёй рамка - по видимому диску: угол от точки
        # под глазом до горизонта, иначе частицы уходили бы на обратную
        # сторону шара.
        eye_h = float(ecef_to_geodetic(view.camera.eye)[2])
        if eye_h > DISK_FROM:
            reach = 2.0 * core.RADIUS * math.acos(
                core.RADIUS / (core.RADIUS + eye_h))
            return view_box(pose.lat, pose.lon, reach, reach, 1.0), width
        return view_box(pose.lat, pose.lon, width, height), width

    def _tick(self):
        window = self.window
        if not self.particles or not window.isVisible() \
                or not window.planet.earth or self.view.sky_view is not None:
            return
        # Шаг постоянный: пропуск таймера под нагрузкой замедляет показ,
        # а не рвёт следы длинными скачками.
        dt = TICK / 1000.0
        box, width = self._box()
        for kind, particles in self.particles.items():
            field = self.fields.get(kind)
            if field is None:
                continue
            old = self.widths.get(kind)
            if particles.box is None or old is None \
                    or max(width / old, old / width) > RESET_ZOOM:
                particles.reset(box)
                self.widths[kind] = width
            else:
                particles.box = box
            particles.step(field, dt,
                           core.metres_per_mps(min(width, 2.0e7),
                                               TYPICAL[kind]))
            self.lines(kind).advance(particles, window._surface_ground,
                                     self.view.store.scale)
        self.view.update()

    def close(self):
        self.timer.stop()
        if self.currents_reply is not None:
            reply, self.currents_reply = self.currents_reply, None
            reply.abort()
