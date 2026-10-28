# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Источники данных Земли: рельеф и основа, глубины, разрез Земли, плиты,
палеогеография, пожары, месторождения, землетрясения.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import html
import os
import zipfile
import time

import numpy as np
from qgis.core import QgsApplication, QgsProject, QgsSettings
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.utils import iface

from ... import journal
from ...core import (basemap, geoid, paleo, dem as dem_model,
                     deposits as deposits_core, fires as fires_core, crust,
                     cutaway, iscgem, quakes, slabs,
                     sources as datasources, tomography)
from ...core.sync import ground_size, view_box
from ...core.terrain import MAX_LEVEL as TERRAIN_MAX
from ...i18n import tr
from ...net.gdalnet import executor
from ...net.overlay import (OPENFREEMAP_ATTRIBUTION, fetch_bytes, fetch_mirror,
                            fetch_json)
from ...render.view import start_keys
from ..inset import DeepSource, DemSource, warm as warm_gdal
from .. import export as layer_export
from ..deposits import deposits_path, parse_deposits
from ..overpass import brief_error
from ..tomo import parse_tomo
from .base import (DATA_DIR, DEPOSIT_POLL, SEA_KEY, SHADOWS_KEY,
                   STRETCH_KEY, TOMO_KEY,
                   TERRAIN_ATTRIBUTION, TERRAIN_MIRRORS, all_sources,
                   link_html)


def crust_surface_names():
    """Названия поверхностей crust.SURFACES по ключам."""
    return {"sediments_upper": tr("кровля верхних осадков"),
            "sediments_middle": tr("кровля средних осадков"),
            "sediments_lower": tr("кровля нижних осадков"),
            "crust_upper": tr("кровля верхней коры"),
            "crust_middle": tr("кровля средней коры"),
            "crust_lower": tr("кровля нижней коры"),
            "moho": tr("Мохо")}


# Раскраска отметок поверхности коры от глубокой к высокой, выбор
# помощника.
DEPTH_COLORS = ((40, 50, 120), (60, 130, 190), (150, 205, 200),
                (235, 225, 160), (190, 120, 60))


def _depth_stops(path):
    """Раскраска растра отметок по его наименьшему и наибольшему
    значению, у плоской поверхности - пустая."""
    from osgeo import gdal
    data = gdal.Open(path)
    values = data.GetRasterBand(1).ReadAsArray().astype(np.float64)
    data = None
    values = values[values != layer_export.NODATA]
    if not values.size or values.max() - values.min() < 1.0:
        return None
    low, high = float(values.min()), float(values.max())
    steps = len(DEPTH_COLORS) - 1
    return [(low + (high - low) * n / steps, color)
            for n, color in enumerate(DEPTH_COLORS)]


class EarthDataMixin:
    """Часть окна глобуса GlobeWindow."""

    # Источники данных.

    def _terrain_choice(self):
        """Адрес и запись высот рельефа Земли: свой из окна «Источники
        данных» или Terrarium."""
        settings = QgsSettings()
        return datasources.terrain(
            settings.value(datasources.TERRAIN_KEY, "") or "",
            settings.value(datasources.ENCODING_KEY, "") or "")

    def _make_dem(self):
        """Модель рельефа 30 м по выбору окна «Источники данных» или
        None - только тайлы высот."""
        kind = dem_model.choice(QgsSettings().value(datasources.DEM_KEY, ""))
        if kind == dem_model.TERRARIUM:
            return None
        # Первый вызов GDAL - в главном потоке, см. ui/inset.py.
        warm_gdal()
        return DemSource(kind)

    def _make_sea(self):
        """Глубины GEBCO по выбору окна «Источники данных» или None -
        дно из тайлов высот."""
        kind = dem_model.sea_choice(
            QgsSettings().value(datasources.SEA_DEM_KEY, ""))
        if kind == dem_model.TERRARIUM:
            return None
        warm_gdal()
        return DemSource(kind)

    def _sea_model(self):
        """Глубины GEBCO, когда они нужны: глубины морей включены, вне
        режима геоида."""
        sea = getattr(self, "sea_dem", None)
        if sea is None or not getattr(self, "sea_depths", True):
            return None
        if self._geoid_on():
            return None
        return sea

    def _height_entries(self):
        """Что ложится на тайлы высот Земли: модель рельефа суши, глубины
        GEBCO, потом врезки своего рельефа."""
        model = getattr(self, "dem", None)
        sea = self._sea_model()
        return tuple(m for m in (model, sea) if m is not None) \
            + tuple(self.insets)

    def _terrain_credit(self):
        url = self._terrain_choice()[0]
        if url == datasources.TERRAIN_URL:
            credit = TERRAIN_ATTRIBUTION
        else:
            text = QgsSettings().value(datasources.TERRAIN_CREDIT_KEY,
                                       "") or ""
            credit = html.escape(text or tr("Рельеф: свой источник"))
        model = getattr(self, "dem", None)
        if model is not None:
            credit += " · " + link_html(*dem_model.ATTRIBUTION[model.kind])
        sea = self._sea_model()
        if sea is not None:
            credit += " · " + link_html(*dem_model.ATTRIBUTION[sea.kind])
        return credit

    def _vector_choice(self):
        """Адрес TileJSON векторной основы: свой или OpenFreeMap."""
        return datasources.vector(
            QgsSettings().value(datasources.VECTOR_KEY, "") or "")

    def _vector_credit(self):
        if self._vector_choice() == datasources.VECTOR_TILEJSON:
            return link_html(*OPENFREEMAP_ATTRIBUTION)
        text = QgsSettings().value(datasources.VECTOR_CREDIT_KEY, "") or ""
        return html.escape(text or tr("Основа: свой источник"))

    def sources_changed(self, what):
        """Окно «Источники данных» сменило адрес: "terrain" - рельеф
        заново, "vector" - векторная основа, надписи и здания заново,
        "basemaps" - список подложек."""
        if what == "terrain":
            self.dem = self._make_dem()
            self.sea_dem = self._make_sea()
            self._refresh_relief()
            self._update_relief_menu()
        elif what == "vector":
            if self.buildings_loader is not None:
                self.buildings_loader.abort()
                self.buildings_loader.deleteLater()
                self.buildings_loader = None
            self.ofm_layer = None
            self.rail_layer = None
            self._ofm_source = None
            self._tilejson = fetch_json(self._vector_choice(),
                                        self._tilejson_done)
        elif what == "basemaps":
            name = self.sources[self._basemap].name
            self.sources = all_sources()
            names = [s.name for s in self.sources]
            if self.properties is not None:
                self.properties.close()
                self.properties = None
            if iface is not None and hasattr(iface, "reloadConnections"):
                iface.reloadConnections()
            self._panel_basemap(names.index(name) if name in names else 0)
        self._show_attribution()
        self.view.update()

    def _earth_floor(self):
        """Пол высот Земли: 0 - отрицательные высоты обнуляются, как
        прежде, None - с дном океана они остаются."""
        return None if self.sea_depths else 0.0

    def set_sea_depths(self, on):
        """Глубины морей и океанов флажком окна свойств вида."""
        self.sea_depths = bool(on)
        QgsSettings().setValue(SEA_KEY, self.sea_depths)
        self._set_sea_floor(self.sea_depths and self.planet.earth)
        self._sync_properties()
        self._update_relief_menu()

    def set_relief_model(self, kind):
        """Высоты суши из меню строки «Рельеф»: только тайлы высот или
        модель 30 м, как в окне «Источники данных»."""
        QgsSettings().setValue(datasources.DEM_KEY, dem_model.choice(kind))
        self.sources_changed("terrain")

    def set_sea_model(self, kind):
        """Глубины морей из меню строки «Рельеф»: тайлы высот или GEBCO,
        как в окне «Источники данных»."""
        QgsSettings().setValue(datasources.SEA_DEM_KEY,
                               dem_model.sea_choice(kind))
        self.sources_changed("terrain")

    def _update_relief_menu(self):
        """Меню строки «Рельеф»: выбор высот суши и глубины морей есть
        только у Земли."""
        panel = getattr(self, "panel", None)
        planet = getattr(self, "planet", None)
        if panel is None or planet is None:
            return
        if not planet.earth:
            panel.set_relief_menu([], "", False)
            return
        from ..sources import dem_titles, sea_titles
        titles = dem_titles()
        own = self._terrain_choice()[0] != datasources.TERRAIN_URL
        short = {dem_model.TERRARIUM: tr("свой источник") if own
                 else "Terrarium",
                 dem_model.COPERNICUS: tr("Copernicus 30 м"),
                 dem_model.GEDTM: "GEDTM30", dem_model.ALOS: "AW3D30",
                 dem_model.NASADEM: "NASADEM",
                 dem_model.USGS: tr("3DEP 10 м")}
        models = [(key, titles[key], short[key]) for key in dem_model.CHOICES]
        kind = dem_model.choice(QgsSettings().value(datasources.DEM_KEY, ""))
        seas = sea_titles()
        sea = dem_model.sea_choice(
            QgsSettings().value(datasources.SEA_DEM_KEY, ""))
        panel.set_relief_menu(models, kind, getattr(self, "sea_depths", True),
                              [(key, seas[key])
                               for key in dem_model.SEA_CHOICES], sea)

    def _set_sea_floor(self, on):
        """Глубины морей и океанов: высоты Земли заново, с впадинами
        ниже нуля или без них, и вода над ними."""
        # В режиме геоида воды нет, высоты - геоид, а не дно.
        self.view.sea_floor = on and not self._geoid_on()
        if not self.planet.earth:
            return
        self._body_terrain(self.planet)
        self.view.reset_heights()
        # Уклон и экспозиция тоже считают дно.
        self._set_surface()

    def _set_cutaway(self, on):
        """Разрез Земли строкой раздела «Слои»: сектор под точкой
        взгляда в момент включения."""
        self.cutaway_legend.setVisible(on)
        self._place_attribution()
        if not on:
            self.view.set_wedge(None)
            if self.view.vertex_tool is self.wedge_corners:
                self.view.vertex_tool = None
            self._update_tool_marks()
            self._wedge_gain_changed()
            self._show_slabs()
            return
        if self.view.wedge is None:
            pose = self.view.navigator.pose
            self.view.set_wedge(cutaway.wedge_at(pose.lat, pose.lon),
                                self.crust)
            self._wedge_gain_changed()
            self._want_slabs()
        if self.view.vertex_tool is None:
            self.view.vertex_tool = self.wedge_corners
        self._update_tool_marks()
        # Модель, не пришедшая раньше, просится снова при включении.
        if self.crust is None and self._crust_reply is None:
            self.crust_error = None
        self._want_crust()
        if self.panel.cutaway_tomo:
            self.set_cutaway_tomo(True)
        self._show_attribution()

    def set_wedge_box(self, west, east, south, north):
        """Сектор разреза Земли по границам в градусах, при включённой
        строке «Разрез Земли». Так его ставят помощник и сцена."""
        if not self.planet.earth or not self.extras.get("cutaway"):
            return False
        self.view.set_wedge(cutaway.make_wedge(west, east, south, north),
                            self.crust)
        self._wedge_gain_changed()
        self._want_slabs()
        self._update_tool_marks()
        return True

    def _wedge_gain_changed(self):
        """Растяжение коры сменилось: очаги и шкала оболочек следом."""
        self.cutaway_legend.set_gain(self.view.wedge_gain)
        self._place_attribution()
        if self.view.quakes.events:
            self._place_quakes()

    def cutaway_stretch(self):
        """Растягивать ли кору разреза издалека - настройка пункта меню
        строки «Разрез Земли», по умолчанию да."""
        return QgsSettings().value(STRETCH_KEY, True, type=bool)

    def set_cutaway_stretch(self, on):
        """Пункт «Растягивать кору»: грани, плиты и очаги заново."""
        QgsSettings().setValue(STRETCH_KEY, bool(on))
        self.panel.cutaway_stretch = bool(on)
        self.view.set_wedge_stretch(on)
        self._wedge_gain_changed()

    def sun_shadows(self):
        """Тени в кадре при строке «Солнце» - настройка пункта «Тени»
        её меню, по умолчанию да (render/shadowmap.py)."""
        return QgsSettings().value(SHADOWS_KEY, True, type=bool)

    def set_sun_shadows(self, on):
        QgsSettings().setValue(SHADOWS_KEY, bool(on))
        self.panel.sun_shadows = bool(on)
        self.view.shadows = bool(on)
        self.view.update()

    # Томография мантии на гранях разреза (core/tomography.py).

    def cutaway_tomo(self):
        """Раскрашивать ли мантию разреза томографией - настройка пункта
        меню строки «Разрез Земли», по умолчанию нет."""
        return QgsSettings().value(TOMO_KEY, False, type=bool)

    @staticmethod
    def _tomo_path():
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, "seisglob2.npz")

    def set_cutaway_tomo(self, on):
        """Пункт «Томография мантии»: модель из файла профиля, иначе
        скачивается файл netCDF около 28 МБ, разбор - в рабочем потоке."""
        QgsSettings().setValue(TOMO_KEY, bool(on))
        self.panel.cutaway_tomo = bool(on)
        if on and self.tomo is None and os.path.exists(self._tomo_path()):
            try:
                self.tomo = tomography.load(self._tomo_path())
            except (OSError, ValueError, KeyError) as error:
                journal.note("tomography file: {}".format(error))
        if on and self.tomo is None:
            self._want_tomo()
        self._show_tomo()

    def _show_tomo(self):
        on = bool(self.panel.cutaway_tomo) and self.tomo is not None
        self.view.set_wedge_tomo(self.tomo if on else None)
        self.cutaway_legend.set_tomo(on)
        self._place_attribution()
        self._show_attribution()

    def _want_tomo(self):
        if self._tomo_reply is not None or self._tomo_job is not None:
            return
        self._tomo_reply = fetch_bytes(tomography.URL, self._tomo_arrived)
        self.view.data_pending += 1
        self.message = (tr("Загрузка томографии SEISGLOB2, около 28 МБ…"),
                        time.monotonic())
        self._show_state()

    def _tomo_arrived(self, data, error):
        self.view.data_pending = max(0, self.view.data_pending - 1)
        self._tomo_reply = None
        if data is None:
            journal.note("tomography: {}".format(brief_error(error)))
            self.message = (tr("Томография не загрузилась: {error}",
                               error=brief_error(error or "")),
                            time.monotonic())
            self._show_state()
            return
        nc = self._tomo_path() + ".nc"
        try:
            with open(nc, "wb") as fh:
                fh.write(bytes(data))
        except OSError as problem:
            journal.note("tomography write: {}".format(problem))
            return
        # Первый вызов GDAL - в главном потоке: предупреждение osgeo
        # о режиме исключений в рабочем потоке роняло бы QGIS.
        warm_gdal()
        self._tomo_job = executor("deposits", 1).submit(
            parse_tomo, nc, self._tomo_path())
        self.view.data_pending += 1
        QTimer.singleShot(DEPOSIT_POLL, self._tomo_poll)

    def _tomo_poll(self):
        job = self._tomo_job
        if job is None:
            return
        if not job.done():
            QTimer.singleShot(DEPOSIT_POLL, self._tomo_poll)
            return
        self._tomo_job = None
        self.view.data_pending = max(0, self.view.data_pending - 1)
        try:
            self.tomo = job.result()
        except (OSError, ValueError, KeyError, RuntimeError) as error:
            journal.note("tomography parse: {}".format(error))
            self.message = (tr("Томография не разобрана."),
                            time.monotonic())
            self._show_state()
            return
        self._show_tomo()

    def _crust_done(self, data, error, saved=False):
        self._crust_reply = None
        self.crust_error = error
        if data is not None:
            try:
                self.crust = crust.from_archive(data)
            except crust.CrustError as problem:
                self.crust_error = str(problem)
            if self.crust is not None and not saved:
                self._save_crust(data)
        if self.crust is None:
            # Без модели кора - слой PREM постоянной толщины, причина -
            # в шкале и журнале. Замечание пользователя от 15 октября
            # 2026 года - «мощность коры в модели постоянная?».
            reason = brief_error(self.crust_error or "")
            self.cutaway_legend.set_missing(reason or tr("нет ответа"))
            journal.note("CRUST1.0 не загружена: {}".format(
                self.crust_error))
        else:
            self.cutaway_legend.set_missing("")
        self._refresh_identified()
        self.cutaway_legend.set_crust(
            self.crust is not None,
            self.crust is not None and self.crust.vp is not None)
        self._place_attribution()
        if self.crust is not None and self.view.wedge is not None:
            self.view.set_wedge(self.view.wedge, self.crust)
        self._show_attribution()
        self._refresh_section()
        folder = getattr(self, "_crust_export", None)
        if folder:
            self._crust_export = None
            if self.crust is not None:
                self.crust_to_project(folder)

    @staticmethod
    def _crust_path():
        """Архив модели коры в профиле QGIS. Его можно положить туда
        вручную, если сайт UCSD не отвечает, - вопрос пользователя Ивана
        от 16 октября 2026 года."""
        return os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                            crust.FILE)

    def _save_crust(self, data):
        """Копия скачанного архива в профиль: следующий сеанс не ходит
        в сеть, даже когда кэш QGIS очищен."""
        path = self._crust_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".part", "wb") as fh:
                fh.write(data)
            os.replace(path + ".part", path)
        except OSError as problem:
            journal.note("CRUST1.0 не записана: {}".format(problem))

    def _want_crust(self):
        """Модель коры CRUST1.0: не распространяется с модулем. Сначала
        архив в профиле QGIS (скачанный прежде или положенный вручную),
        иначе запрос к сайту UCSD, ответ записывается в профиль."""
        if self.crust is not None or self._crust_reply is not None \
                or self.crust_error:
            return
        path = self._crust_path()
        if os.path.isfile(path):
            try:
                with open(path, "rb") as fh:
                    data = fh.read()
            except OSError as problem:
                journal.note("CRUST1.0 не прочитана: {}".format(problem))
            else:
                self._crust_done(data, None, saved=True)
                if self.crust is not None:
                    return
                self.crust_error = ""
        self._crust_reply = fetch_bytes(crust.URL, self._crust_done)

    def crust_to_project(self, folder=None):
        """Пункт «Кора CRUST1.0 в проект QGIS…»: кровли трёх слоёв
        осадков, трёх слоёв коры и Мохо в рамке вида - GeoTIFF отметок
        в метрах в папке folder, слои - группой в проект. Без модели она
        просится, выгрузка идёт по её приходу. Возвращает количество
        записанных поверхностей или None."""
        if folder is None:
            folder = QFileDialog.getExistingDirectory(
                self, tr("Кора CRUST1.0 в проект QGIS"),
                QgsProject.instance().homePath() or os.path.expanduser("~"))
        if not folder:
            return None
        if self.crust is None:
            # Выгрузку делает _crust_done по приходу модели, в том числе
            # сразу, когда архив лежит в профиле.
            self._crust_export = folder
            self.crust_error = ""
            self._want_crust()
            if self.crust is None:
                self.message = (tr("Модель коры загружается, поверхности "
                                   "будут записаны по её приходу."),
                                time.monotonic())
                self._show_state()
            return None
        self._crust_export = None
        pose = self.view.navigator.pose
        camera = self.view.camera
        width, height = ground_size(pose.distance, camera.fov_y,
                                    camera.aspect)
        box = view_box(pose.lat, pose.lon, width, height)
        names = crust_surface_names()
        group = tr("PlanetX - кора CRUST1.0")
        written = 0
        for key, values in self.crust.surfaces():
            path = os.path.join(folder, "crust1_{}.tif".format(key))
            count = layer_export.write_grid(
                path, [values], crust.GRID_WEST, crust.GRID_NORTH,
                crust.GRID_STEP, box)
            if count is None:
                break
            if layer_export.add_raster(
                    path, "CRUST1.0 - " + names[key],
                    _depth_stops(path), crust.CITATION[0], group) is None:
                break
            written += 1
        if written == len(crust.SURFACES):
            text = tr("В проект добавлено поверхностей коры {count}.",
                      count=written)
        else:
            text = tr("Поверхности коры не записаны в «{path}».",
                      path=folder)
        self.message = (text, time.monotonic())
        self._show_state()
        return written

    def _read_slab_index(self):
        if self.slab_index is None:
            with open(os.path.join(DATA_DIR, "slab2_index.json"),
                      encoding="utf-8") as fh:
                self.slab_index = slabs.read_index(fh.read())
        return self.slab_index

    def _want_slabs(self):
        """Зоны плит Slab2, которых касается разрез: пришедшие - на
        грани, недостающие - в запрос. Указатель зон лежит в модуле."""
        wedge = self.view.wedge
        if wedge is None:
            return
        codes = slabs.touched(self._read_slab_index(),
                              *cutaway.arc_points(wedge))
        self._slab_codes = codes
        self._request_slabs(codes)
        self._show_slabs()

    def _request_slabs(self, codes):
        """Файлы зон плит, которых ещё нет, - в запрос. Ждущие запросы
        входят в счётчик загрузки вида, его показывает значок."""
        for code in codes:
            if code in self.slab_zones or code in self._slab_replies \
                    or code in self.slab_errors:
                continue
            if self.slab_base:
                self._slab_replies[code] = fetch_bytes(
                    slabs.url_of(code, self.slab_base),
                    lambda data, error, code=code: self._slab_done(
                        code, data, error))
            else:
                self._slab_replies[code] = fetch_mirror(
                    TERRAIN_MIRRORS, slabs.PATH.format(code=code),
                    lambda data, error, base, code=code: self._slab_done(
                        code, data, error))
        self._count_pending()
        self.view.update()

    def _slab_done(self, code, data, error):
        self._slab_replies.pop(code, None)
        self._count_pending()
        if data is None:
            self.slab_errors[code] = error
        else:
            try:
                self.slab_zones[code] = slabs.load(data, code)
            except slabs.SlabError as problem:
                self.slab_errors[code] = str(problem)
        self._show_slabs()
        self._refresh_section()
        self._refresh_identified()

    def _refresh_identified(self):
        """Окно «Объекты» открыто - место в нём уточняется."""
        if self.identified is not None and self.identified.isVisible():
            self._show_identified()

    def _show_slabs(self):
        """Пришедшие зоны разреза - на грани, подпись источника и строка
        шкалы оболочек следом."""
        codes = self._slab_codes
        zones = [self.slab_zones[c] for c in codes if c in self.slab_zones] \
            if self.view.wedge is not None else []
        self.view.set_wedge_slabs(zones)
        self.cutaway_legend.set_slabs(bool(zones))
        self._place_attribution()
        self._show_attribution()

    def _depth_map(self):
        """Глубины на экране очагов: при разрезе Земли - с растяжением
        коры, иначе None."""
        gain = self.view.wedge_gain
        if self.view.wedge is None or gain == 1.0:
            return None
        return lambda depth: cutaway.stretch(depth, gain)

    def _paleo_on(self):
        return bool(self.extras.get("paleo")) and self.planet.earth \
            and self.view.sky_view is None

    def _set_paleo(self, on):
        """Палеогеография строкой раздела «Слои»: ползунок возраста,
        гладкая основа и берега материков на этот возраст."""
        shown = self._paleo_on()
        self.paleo_bar.setVisible(shown)
        self.view.plain_base = shown
        if self._relief_target() != self.view.store.scale:
            self.view.set_relief(self._relief_target())
            self._update_water()
            self._place_quakes()
            self._place_fires()
            self._place_deposits()
        self._place_attribution()
        if not shown:
            self.paleo_bar.stop()
            if self.planet.earth:
                self._switch_basemap(self._earth_source())
            self._show_attribution()
            return
        self._paleo_age(self.paleo_bar.age())

    def _paleo_age(self, age):
        """Карта возраста age млн лет - подложка. Уровни 0-2 прежнего
        возраста стоят на экране, пока не придут новые, глубокие тайлы
        снимаются сразу (change_source, coarse): кадр не смешивает два
        возраста, новый встаёт грубым и уточняется."""
        self.paleo_age = age
        if self._paleo_on():
            self._switch_basemap(self._earth_source(), coarse=True)

    def _paleo_source(self, age):
        """Источник тайлов карты возраста age, один на возраст: смена
        источника сравнивается по тождеству."""
        url = self.paleo_url.format(age=age, z="{z}", x="{x}", y="{y}")
        found = self._paleo_sources.get(url)
        if found is None:
            found = basemap.Source(tr("{age} млн лет назад", age=age), url,
                                   paleo.MAX_LEVEL, paleo.ATTRIBUTION,
                                   builtin=True, missing=(404,))
            self._paleo_sources[url] = found
        return found

    def _earth_source(self):
        """Подложка Земли: карта возраста в палеогеографии, иначе
        выбранная в группе «Основа»."""
        if self._paleo_on():
            return self._paleo_source(self.paleo_age)
        return self.sources[self._basemap]

    def _paleo_ready(self):
        """Показан ли нынешний возраст: уровни 0-2 его карты на экране
        и ни одного тайла прежней карты в кадре. Показ ждёт этого, иначе
        шаги обгоняют загрузку."""
        view = self.view
        keep = view.selection.keep if view.selection else ()
        return all(key in view.textures and key not in view.stale
                   for key in start_keys()) \
            and not any(key in view.stale for key in keep)

    def _count_pending(self):
        """Ждущие ответы зон плит - в счётчик загрузки вида, его
        показывает значок загрузки."""
        self.view.data_pending = len(self._slab_replies)

    def _quake_legend_state(self):
        """Шкала глубины очагов - при очагах на Земле."""
        on = (self.extras.get("quakes", False)
              or self.extras.get("iscgem", False)) and self.planet.earth \
            and self.view.sky_view is None
        self.quake_legend.setVisible(on)
        self._place_attribution()

    def _set_fires(self, on):
        """Пожары - строка группы «Планета огня» в общем выборе тем.
        Сводка NASA FIRMS за 24 часа загружается при каждом включении.
        Включённые пожары снимают тему."""
        if on and (self.theme_key or self.extras.get("temperature")):
            self.set_theme("fires")
        self._mark_gallery()
        self.fire_legend.setVisible(on and self.planet.earth
                                    and self.view.sky_view is None)
        self._place_attribution()
        if not on:
            if self._fire_reply is not None:
                self._fire_reply.abort()
            self._fire_reply = None
            self._place_fires()
            self._place_deposits()
            return
        if self._fire_reply is None:
            self._fire_reply = fetch_bytes(fires_core.FEED, self._fires_done,
                                           prefer_cache=False)
            self.view.data_pending += 1

    def _fires_done(self, data, error):
        if self._fire_reply is not None:
            self.view.data_pending = max(0, self.view.data_pending - 1)
        self._fire_reply = None
        if data is not None:
            self.fire_data = fires_core.parse(data.decode("utf-8",
                                                          "replace"))
        else:
            self.message = (tr("Сводка пожаров не загрузилась: {error}",
                               error=error), time.monotonic())
            self._show_state()
        self._place_fires()
        self._place_deposits()

    def _set_deposits(self, on):
        """Месторождения USGS - строка витрины. Первое включение
        скачивает архивы MRDS и крупных месторождений мира, разбор идёт
        в рабочем потоке, итог ложится файлом в профиль
        (core/deposits.py). Дальше файл читается без сети."""
        self._mark_gallery()
        self.deposit_legend.setVisible(self._deposit_legend_on())
        if not on:
            for reply in list(self._deposit_replies.values()):
                reply.abort()
            self._deposit_replies.clear()
            self._place_deposits()
            return
        if self.deposit_data is None:
            path = deposits_path()
            if os.path.exists(path):
                try:
                    self.deposit_data = deposits_core.load(path)
                except (OSError, ValueError, KeyError) as error:
                    journal.note("deposits file: {}".format(error))
        if self.deposit_data is not None:
            self._place_deposits()
            return
        if self._deposit_replies or self._deposit_job is not None:
            return
        self._deposit_bytes = {}
        for key, url in (("mrds", deposits_core.MRDS_URL),
                         ("major", deposits_core.MAJOR_URL),
                         ("minfac", deposits_core.MINFAC_URL)):
            self._deposit_replies[key] = fetch_bytes(
                url, lambda data, error, key=key:
                self._deposit_arrived(key, data, error))
            self.view.data_pending += 1
        self.message = (tr("Загрузка месторождений USGS, около 25 МБ…"),
                        time.monotonic())
        self._show_state()

    def _deposit_arrived(self, key, data, error):
        if self._deposit_replies.pop(key, None) is not None:
            self.view.data_pending = max(0, self.view.data_pending - 1)
        if data is None:
            for reply in list(self._deposit_replies.values()):
                reply.abort()
            self._deposit_replies.clear()
            self.message = (tr("Месторождения не загрузились: {error}",
                               error=error), time.monotonic())
            self._show_state()
            return
        self._deposit_bytes[key] = bytes(data)
        if self._deposit_replies:
            return
        mrds = self._deposit_bytes.pop("mrds", None)
        major = self._deposit_bytes.pop("major", None)
        minfac = self._deposit_bytes.pop("minfac", None)
        self._deposit_job = executor("deposits", 1).submit(
            parse_deposits, mrds, major, minfac, deposits_path())
        self.view.data_pending += 1
        QTimer.singleShot(DEPOSIT_POLL, self._deposit_poll)

    def _deposit_poll(self):
        job = self._deposit_job
        if job is None:
            return
        if not job.done():
            QTimer.singleShot(DEPOSIT_POLL, self._deposit_poll)
            return
        self._deposit_job = None
        self.view.data_pending = max(0, self.view.data_pending - 1)
        try:
            self.deposit_data = job.result()
        except (OSError, ValueError, KeyError, StopIteration,
                zipfile.BadZipFile) as error:
            self.message = (tr("Месторождения не разобраны: {error}",
                               error=error), time.monotonic())
            self._show_state()
            return
        self._place_deposits()

    def _place_deposits(self):
        """Месторождения на глобус по нынешнему масштабу рельефа."""
        on = self.extras.get("deposits", False) and self.planet.earth
        self.view.deposits.set_deposits(
            self.deposit_data if on else None, self.view.store.scale,
            self._surface_ground)
        self._show_attribution()
        self.view.update()

    def _place_fires(self):
        """Очаги на глобус по нынешнему масштабу рельефа."""
        on = self.extras.get("fires", False) and self.planet.earth
        self.view.fires.set_fires(self.fire_data if on else None,
                                  self.view.store.scale,
                                  self._surface_ground)
        self._update_timebar()
        self._time_quakes()
        self._show_attribution()
        self.view.update()

    def _set_quakes(self, on):
        """Землетрясения строкой раздела «Слои». Сводка USGS
        загружается при каждом включении, кэш QGIS отдаёт её только
        по заголовкам сервера."""
        if not on:
            if self._quake_reply is not None:
                self._quake_reply.abort()
            self._quake_reply = None
            self.view.quakes.set_events([], 0.0, None)
            self._update_timebar()
            self._quake_legend_state()
            self._show_attribution()
            self.view.update()
            return
        self._quake_legend_state()
        self._want_quakes()

    def _want_quakes(self):
        """Сводка землетрясений USGS, если её запроса ещё нет."""
        if self._quake_reply is None:
            self._quake_reply = fetch_json(quakes.FEED, self._quakes_done,
                                           prefer_cache=False)

    def _quakes_done(self, data, error):
        self._quake_reply = None
        self.quake_error = error
        if data is not None:
            self.quake_events = quakes.parse(data)
        self._place_quakes()
        self._refresh_section()

    def _place_quakes(self):
        """События на глобус по нынешнему масштабу рельефа. Эпицентр
        стоит на рельефе из хранилища высот, грубом вдали от вида."""
        on = self.extras.get("quakes", False) and self.planet.earth
        events = self.quake_events if on else []
        # При разрезе Земли очаги растягиваются по глубине, как кора.
        self.view.quakes.set_events(events, self.view.store.scale,
                                    self._surface_ground, self._depth_map())
        on = self.extras.get("iscgem", False) and self.planet.earth
        self.view.history.set_events(
            (self.history_events or []) if on else [],
            self.view.store.scale, self._surface_ground, self._depth_map())
        self._update_timebar()
        self._time_quakes()
        self._show_attribution()
        self.view.update()

    # Исторические землетрясения - каталог ISC-GEM (core/iscgem.py).

    def _history_path(self):
        folder = os.path.join(QgsApplication.qgisSettingsDirPath(),
                              "PlanetX")
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, iscgem.FILE)

    def _set_history(self, on):
        """Строка «Исторические землетрясения». Первое включение собирает
        каталог запросами ComCat по промежуткам лет, около 74 тысяч
        событий, итог - файл профиля. Файл старше iscgem.REFETCH_DAYS
        собирается заново."""
        self._mark_gallery()
        self._quake_legend_state()
        if not on:
            if self._history_reply is not None:
                reply, self._history_reply = self._history_reply, None
                reply.abort()
                self.view.data_pending = max(0, self.view.data_pending - 1)
            self._place_quakes()
            return
        path = self._history_path()
        if self.history_events is None and os.path.exists(path):
            try:
                self.history_events = iscgem.load(path)
            except (OSError, ValueError, KeyError) as error:
                journal.note("iscgem file: {}".format(error))
            age = (time.time() - os.path.getmtime(path)) / 86400.0
            if age > iscgem.REFETCH_DAYS and self._history_reply is None:
                self._history_fetch(quiet=True)
        if self.history_events is not None:
            self._place_quakes()
            return
        if self._history_reply is None:
            self._history_fetch()

    def _history_fetch(self, quiet=False):
        self._history_parts = []
        self._history_queue = iscgem.periods(time.gmtime().tm_year)
        self._history_quiet = quiet
        self.view.data_pending += 1
        self._history_next()

    def _history_next(self):
        start, end = self._history_queue[0]
        if not self._history_quiet:
            self.message = (tr("Загрузка землетрясений ISC-GEM, {year}…",
                               year=start[:4]), time.monotonic())
            self._show_state()
        self._history_reply = fetch_bytes(iscgem.query_url(start, end),
                                          self._history_arrived)

    def _history_arrived(self, data, error):
        if self._history_reply is None:
            return  # снят выключением строки
        self._history_reply = None
        if data is None:
            self.view.data_pending = max(0, self.view.data_pending - 1)
            journal.note("iscgem: {}".format(brief_error(error or "")))
            if not self._history_quiet:
                self.message = (tr("Каталог ISC-GEM не загрузился, "
                                   "проверьте сеть и включите строку "
                                   "снова."), time.monotonic())
                self._show_state()
            return
        self._history_parts.extend(iscgem.parse(bytes(data)))
        self._history_queue.pop(0)
        if self._history_queue:
            self._history_next()
            return
        self.view.data_pending = max(0, self.view.data_pending - 1)
        found = self._history_parts
        self._history_parts = []
        try:
            iscgem.save(found, self._history_path())
        except OSError as problem:
            journal.note("iscgem save: {}".format(problem))
        self.history_events = found
        if not self._history_quiet:
            self.message = (tr("Исторических землетрясений {count}.",
                               count=len(found)), time.monotonic())
            self._show_state()
        self._place_quakes()

    def _surface_ground(self, lats, lons):
        """Высоты нарисованной поверхности: с дном океана - дно."""
        return self._true_heights(lats, lons)

    def _surface_heights(self, lats, lons):
        """Высоты поверхности для видимости и инсоляции: с дном океана
        над водой - уровень моря, а не дно."""
        heights = self._true_heights(lats, lons)
        if self.view.sea_floor:
            heights = np.maximum(heights, 0.0)
        return heights

    def _body_terrain(self, planet):
        """Высоты тела: Terrarium у Земли, архив у Марса и Луны.
        Архив тела скачивается, когда рельеф включён."""
        if planet.earth and self._geoid_on():
            # Режим геоида: высоты - тайлы геоида, без врезок и пола.
            self.view.store.max_level = geoid.MAX_LEVEL
            self.view.store.deep = []
            self._start_terrain(basemap.Source(
                "EGM2008", self.geoid_url, geoid.MAX_LEVEL, builtin=True),
                None)
            return
        if planet.earth:
            self.view.store.max_level = TERRAIN_MAX
            self._start_terrain(DeepSource(
                "Terrarium", self._terrain_choice()[0], TERRAIN_MAX),
                self._earth_floor())
            return
        self.view.store.deep = []
        self._start_terrain(None, None)
        if planet.terrain is None:
            return
        name, url, level, _ = planet.terrain
        self.view.store.max_level = level
        # Впадины тел ниже нуля остаются, пол не ставится.
        self._start_terrain(basemap.Source(name, url, level,
                                           builtin=True), None)
