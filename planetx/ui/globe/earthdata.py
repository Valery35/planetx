# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Источники данных Земли: рельеф и основа, глубины, разрез Земли, плиты,
палеогеография, пожары, месторождения, землетрясения.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import html
import os
import time

import numpy as np
from qgis.core import QgsApplication, QgsProject, QgsSettings
from qgis.PyQt.QtWidgets import QFileDialog
from qgis.utils import iface

from ... import journal
from ...core import (basemap, dem as dem_model,
                     crust,
                     cutaway, slabs,
                     sources as datasources)
from ...core.sync import ground_size, view_box
from ...core.terrain import MAX_LEVEL as TERRAIN_MAX
from ...i18n import tr
from ...net.overlay import (OPENFREEMAP_ATTRIBUTION, fetch_bytes, fetch_mirror,
                            fetch_json)
from ..inset import DeepSource, DemSource, warm as warm_gdal
from .. import export as layer_export
from .base import (DATA_DIR, SEA_KEY,
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
        if self._heights_replaced():
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
            self._row_hook("vector_changed")
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
        self.view.sea_floor = on and not self._heights_replaced()
        if not self.planet.earth:
            return
        self._body_terrain(self.planet)
        self.view.reset_heights()
        # Уклон и экспозиция тоже считают дно.
        self._set_surface()

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
            journal.note("CRUST1.0 не загружена: {}".format(
                self.crust_error))
        self._refresh_identified()
        # Шкала и грани разреза Земли - у исполнителя строки.
        self._row_hook("crust_changed")
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
        self._row_hook("slabs_changed")
        self._refresh_section()
        self._refresh_identified()

    def _refresh_identified(self):
        """Окно «Объекты» открыто - место в нём уточняется."""
        if self.identified is not None and self.identified.isVisible():
            self._show_identified()

    def _depth_map(self):
        """Глубины на экране очагов: при разрезе Земли - с растяжением
        коры, иначе None."""
        gain = self.view.wedge_gain
        if self.view.wedge is None or gain == 1.0:
            return None
        return lambda depth: cutaway.stretch(depth, gain)

    def _earth_source(self):
        """Подложка Земли: подложка строки реестра с base_source
        (карта возраста палеогеографии), иначе выбранная в группе
        «Основа»."""
        for tool in getattr(self, "row_tools", {}).values():
            if hasattr(tool, "base_source"):
                found = tool.base_source()
                if found is not None:
                    return found
        return self.sources[self._basemap]

    def _flat_relief(self):
        """Выключила ли рельеф строка реестра (палеогеография)."""
        return any(tool.flat_relief()
                   for tool in getattr(self, "row_tools", {}).values()
                   if hasattr(tool, "flat_relief"))

    def _count_pending(self):
        """Ждущие ответы зон плит - в счётчик загрузки вида, его
        показывает значок загрузки."""
        self.view.data_pending = len(self._slab_replies)

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
        found = self._row_hook("terrain_source") if planet.earth else None
        if found is not None:
            # Высоты строки реестра (геоид): без врезок и пола.
            source, top = found
            self.view.store.max_level = top
            self.view.store.deep = []
            self._start_terrain(source, None)
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
