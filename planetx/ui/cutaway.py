# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Разрез Земли (core/cutaway.py) - сектор под точкой взгляда с гранями
оболочек PREM, корой CRUST1.0, плитами Slab2 и томографией мантии
SEISGLOB2 (core/tomography.py). Строка реестра (core/rows.py)
и исполнитель: сектор и его углы, растяжение коры, томография, шкала
оболочек, подпись источников. Модель коры и файлы зон плит загружает
окно - их берут и окна «Разрез» и «Объекты», о приходе окно говорит
крючками crust_changed и slabs_changed.
"""
import os
import time

import numpy as np
from qgis.core import QgsApplication, QgsSettings
from qgis.PyQt.QtCore import QObject, QTimer

from .. import journal
from ..core import crust, cutaway, slabs, tomography
from ..core.ellipsoid import geodetic_to_ecef
from ..core.measure import nearest_vertex
from ..core.rows import Row
from ..i18n import tr

KEY = "cutaway"
# Растягивать ли кору разреза издалека, по умолчанию да.
STRETCH_KEY = "PlanetX/cutaway_stretch"
# Раскрашивать ли мантию разреза томографией, по умолчанию нет.
TOMO_KEY = "PlanetX/cutaway_tomo"
TOMO_POLL = 300  # мс между проверками разбора томографии


class WedgeCorners:
    """Угловые точки разреза Земли, которые тянутся мышью (render/view.py,
    vertex_tool), просьба автора от 2 октября 2026 года. Угол меняет
    свою долготу и свою широту сектора (core.cutaway.move_corner)."""

    def __init__(self, tool):
        self.tool = tool
        self.window = tool.window
        self.index = None

    def points(self):
        """Углы сектора без повторов: у полюса два угла совпадают."""
        wedge = self.window.view.wedge
        if wedge is None:
            return []
        out = []
        for n, (lat, lon) in enumerate(cutaway.corners(wedge)):
            if abs(lat) >= 90.0 and n in (1, 3):
                continue
            out.append((n, lat, lon))
        return out

    def grab(self, px, py):
        from .measure import GRAB_PIXELS
        view = self.window.view
        points = self.points()
        if not points:
            return False
        # Ручка - там, где нарисован кружок угла: на поверхности, как
        # подпись (GlobeView.label_height). С эллипсоида в режиме
        # «Геоид» точка захвата уходила от кружка на сотни километров,
        # замечание автора от 15 октября 2026 года.
        xyz = geodetic_to_ecef(np.array([p[1] for p in points]),
                               np.array([p[2] for p in points]),
                               np.array([view.label_height(p[1], p[2])
                                         for p in points]))
        pixels, front = view.camera.project(xyz)
        found = nearest_vertex(pixels, front, px, py,
                               GRAB_PIXELS * view.devicePixelRatioF())
        self.index = None if found is None else points[found][0]
        return self.index is not None

    def move(self, px, py):
        window = self.window
        found = window._ground(px, py)
        wedge = window.view.wedge
        if found is None or self.index is None or wedge is None:
            return
        window.view.set_wedge(cutaway.move_corner(wedge, self.index,
                                                  *found), window.crust)
        window._update_tool_marks()

    def drop(self):
        self.index = None
        # Зоны плит - по новому сектору, когда угол отпущен.
        self.tool.want_slabs()


class CutawayTool(QObject):
    """Сектор разреза Земли, его углы, шкала оболочек и томография."""

    shown_key = None

    def __init__(self, window):
        from .legend import CutawayLegend
        super().__init__(window)
        self.window = window
        self.legend = CutawayLegend(window.view)
        self.legend.hide()
        # Шкала оболочек - под шкалой пластов, как прежде.
        window.legend_panel.add(self.legend, before=window.quake_legend)
        self.corners = WedgeCorners(self)
        self.slab_codes = []  # зоны плит, которых касается сектор
        self.tomo = None
        self.tomo_reply = None
        self.tomo_job = None
        view = window.view
        view.wedge_gain_changed.connect(self.gain_changed)
        panel = window.panel
        panel.cutaway_stretch = self.stretch()
        view.wedge_stretch = panel.cutaway_stretch
        panel.cutaway_stretch_changed.connect(self.set_stretch)
        panel.cutaway_tomo = self.tomo_wanted()
        panel.cutaway_tomo_changed.connect(self.set_tomo)

    # Строка.

    def turn(self, key, on):
        """Сектор под точкой взгляда в момент включения."""
        window = self.window
        view = window.view
        self.legend.setVisible(on)
        window._place_attribution()
        if not on:
            view.set_wedge(None)
            if view.vertex_tool is self.corners:
                view.vertex_tool = None
            window._update_tool_marks()
            self.gain_changed()
            self.show_slabs()
            return True
        if view.wedge is None:
            pose = view.navigator.pose
            view.set_wedge(cutaway.wedge_at(pose.lat, pose.lon),
                           window.crust)
            self.gain_changed()
            self.want_slabs()
        if view.vertex_tool is None:
            view.vertex_tool = self.corners
        window._update_tool_marks()
        # Модель, не пришедшая раньше, просится снова при включении.
        if window.crust is None and window._crust_reply is None:
            window.crust_error = None
        window._want_crust()
        if window.panel.cutaway_tomo:
            self.set_tomo(True)
        window._show_attribution()
        return True

    def set_box(self, west, east, south, north):
        """Сектор по границам в градусах при включённой строке. Так его
        ставят помощник, сцена и вид метки."""
        window = self.window
        if not window.planet.earth or not window.extras.get(KEY):
            return False
        window.view.set_wedge(cutaway.make_wedge(west, east, south, north),
                              window.crust)
        self.gain_changed()
        self.want_slabs()
        window._update_tool_marks()
        return True

    def vertex_tool(self):
        """Ручки вида без других инструментов - углы сектора."""
        return self.corners if self.window.view.wedge is not None else None

    def tool_marks(self):
        """Подписи углов сектора - широта и долгота, видны, пока угол
        тянут."""
        from ..core.places import Place as MarkPlace
        return [MarkPlace(-420000 - n, "{:.0f}°, {:.0f}°".format(lat, lon),
                          "mark", 1, lat, lon)
                for n, lat, lon in self.corners.points()]

    def sync_legend(self):
        window = self.window
        self.legend.setVisible(bool(window.extras.get(KEY))
                               and window.planet.earth
                               and window.view.sky_view is None)

    def gain_changed(self):
        """Растяжение коры сменилось: очаги и шкала оболочек следом."""
        window = self.window
        self.legend.set_gain(window.view.wedge_gain)
        window._place_attribution()
        for tool in window.row_tools.values():
            if hasattr(tool, "wedge_changed"):
                tool.wedge_changed()

    # Растяжение коры.

    @staticmethod
    def stretch():
        """Растягивать ли кору разреза издалека - пункт меню строки,
        по умолчанию да."""
        return QgsSettings().value(STRETCH_KEY, True, type=bool)

    def set_stretch(self, on):
        """Пункт «Растягивать кору»: грани, плиты и очаги заново."""
        window = self.window
        QgsSettings().setValue(STRETCH_KEY, bool(on))
        window.panel.cutaway_stretch = bool(on)
        window.view.set_wedge_stretch(on)
        self.gain_changed()

    # Кора и плиты, которые загружает окно.

    def crust_changed(self):
        """Модель коры пришла или не пришла: шкала и грани следом."""
        window = self.window
        if window.crust is None:
            # Без модели кора - слой PREM постоянной толщины, причина -
            # в шкале и журнале. Замечание пользователя от 15 октября
            # 2026 года - «мощность коры в модели постоянная?».
            from .overpass import brief_error
            reason = brief_error(window.crust_error or "")
            self.legend.set_missing(reason or tr("нет ответа"))
        else:
            self.legend.set_missing("")
        self.legend.set_crust(
            window.crust is not None,
            window.crust is not None and window.crust.vp is not None)
        window._place_attribution()
        view = window.view
        if window.crust is not None and view.wedge is not None:
            view.set_wedge(view.wedge, window.crust)

    def want_slabs(self):
        """Зоны плит Slab2, которых касается разрез: пришедшие - на
        грани, недостающие - в запрос. Указатель зон лежит в модуле."""
        window = self.window
        wedge = window.view.wedge
        if wedge is None:
            return
        self.slab_codes = slabs.touched(window._read_slab_index(),
                                        *cutaway.arc_points(wedge))
        window._request_slabs(self.slab_codes)
        self.show_slabs()

    def slabs_changed(self):
        self.show_slabs()

    def show_slabs(self):
        """Пришедшие зоны разреза - на грани, подпись источника и строка
        шкалы оболочек следом."""
        window = self.window
        zones = [window.slab_zones[c] for c in self.slab_codes
                 if c in window.slab_zones] \
            if window.view.wedge is not None else []
        window.view.set_wedge_slabs(zones)
        self.legend.set_slabs(bool(zones))
        window._place_attribution()
        window._show_attribution()

    # Томография мантии на гранях разреза (core/tomography.py).

    @staticmethod
    def tomo_wanted():
        """Раскрашивать ли мантию разреза томографией - пункт меню
        строки, по умолчанию нет."""
        return QgsSettings().value(TOMO_KEY, False, type=bool)

    @staticmethod
    def tomo_path():
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "seisglob2.npz")

    def set_tomo(self, on):
        """Пункт «Томография мантии»: модель из файла профиля, иначе
        скачивается файл netCDF около 28 МБ, разбор - в рабочем потоке."""
        QgsSettings().setValue(TOMO_KEY, bool(on))
        self.window.panel.cutaway_tomo = bool(on)
        if on and self.tomo is None and os.path.exists(self.tomo_path()):
            try:
                self.tomo = tomography.load(self.tomo_path())
            except (OSError, ValueError, KeyError) as error:
                journal.note("tomography file: {}".format(error))
        if on and self.tomo is None:
            self._want_tomo()
        self.show_tomo()

    def show_tomo(self):
        window = self.window
        on = bool(window.panel.cutaway_tomo) and self.tomo is not None
        window.view.set_wedge_tomo(self.tomo if on else None)
        self.legend.set_tomo(on)
        window._place_attribution()
        window._show_attribution()

    def _want_tomo(self):
        from ..net.overlay import fetch_bytes
        window = self.window
        if self.tomo_reply is not None or self.tomo_job is not None:
            return
        self.tomo_reply = fetch_bytes(tomography.URL, self._tomo_arrived)
        window.view.data_pending += 1
        window.message = (tr("Загрузка томографии SEISGLOB2, около 28 МБ…"),
                          time.monotonic())
        window._show_state()

    def _tomo_arrived(self, data, error):
        from ..net.gdalnet import executor
        from .inset import warm as warm_gdal
        from .overpass import brief_error
        from .tomo import parse_tomo
        window = self.window
        window.view.data_pending = max(0, window.view.data_pending - 1)
        self.tomo_reply = None
        if data is None:
            journal.note("tomography: {}".format(brief_error(error)))
            window.message = (tr("Томография не загрузилась: {error}",
                                 error=brief_error(error or "")),
                              time.monotonic())
            window._show_state()
            return
        nc = self.tomo_path() + ".nc"
        try:
            with open(nc, "wb") as fh:
                fh.write(bytes(data))
        except OSError as problem:
            journal.note("tomography write: {}".format(problem))
            return
        # Первый вызов GDAL - в главном потоке: предупреждение osgeo
        # о режиме исключений в рабочем потоке роняло бы QGIS.
        warm_gdal()
        self.tomo_job = executor("deposits", 1).submit(
            parse_tomo, nc, self.tomo_path())
        window.view.data_pending += 1
        QTimer.singleShot(TOMO_POLL, self._tomo_poll)

    def _tomo_poll(self):
        window = self.window
        job = self.tomo_job
        if job is None:
            return
        if not job.done():
            QTimer.singleShot(TOMO_POLL, self._tomo_poll)
            return
        self.tomo_job = None
        window.view.data_pending = max(0, window.view.data_pending - 1)
        try:
            self.tomo = job.result()
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            journal.note("tomography parse: {}".format(error))
            window.message = (tr("Томография не разобрана."),
                              time.monotonic())
            window._show_state()
            return
        self.show_tomo()

    # Подпись, каталог.

    def credits(self):
        view = self.window.view
        out = []
        if view.wedge_slabs:
            out.append(slabs.ATTRIBUTION)
        if view.wedge is not None and self.window.crust is not None:
            out.append(crust.CITATION)
        if view.wedge is not None and view.wedge_tomo is not None:
            out.append(tomography.ATTRIBUTION)
        return out

    @staticmethod
    def thumb(key, tile, base):
        """Превью каталога: сектор с оболочками."""
        from .nasamaps import cutaway_image
        return cutaway_image()

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        pass


ROWS = (
    Row(KEY, "geology", lambda: (tr("Разрез Земли"), tr(
        "Вынимает из Земли сектор под точкой взгляда - "
        "четверть полушария шириной 90° по долготе. На его "
        "гранях видны кора, мантия и ядро по радиусам "
        "модели PREM. Где грань проходит через зону "
        "субдукции, на ней видна погружающаяся плита. "
        "Углы сектора тянутся мышью. Сектор ставится заново "
        "при каждом включении строки.")), CutawayTool,
        source="PREM, CRUST1.0, Slab2",
        words=("разрез земли", "недра", "ядро", "мантия", "кора",
               "cutaway", "core", "mantle"), after="geology"),
)
