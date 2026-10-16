# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""«Мои метки» на глобусе, шкала времени, поток по путям, сцена и демо.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import math
import os
import time

import numpy as np
from urllib.parse import quote
from qgis.core import QgsApplication, QgsProject, QgsRasterLayer
from qgis.PyQt.QtCore import QTimer
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox

from ... import journal
from ...core import (demofiles, ellipsoid, when, oldmaps, pathflow, region,
                     fires as fires_core, quakes, themes, opacity)
from ...core.ellipsoid import geodetic_to_ecef
from ...core.features import grown, has_alts
from ...core.skydata import direction as sky_direction
from ...core.scene import EXTENSION, SceneError, read_scene, write_scene
from ...i18n import tr
from ...net.overlay import fetch_bytes
from ..myplaces import OverlayItem, Place
from ..project import (read_bathymetry, read_insets, read_map_years,
                       set_visible_on_map, write_bathymetry, write_map_years,
                       write_shown)
from ..subsurface import add_to_project
from ..record import RecordDialog
from ..scene import apply as apply_scene, capture as capture_scene
from ..track import TrackDialog
from .base import (BRIENZ_LEVEL, DEMO_QUAKE_BAND, FLOW_LIFT, FLOW_REACH,
                   FLOW_TICK, FLOW_WIDER, OPACITY_DELAY, PLUGIN_DIR,
                   POLE_FIRST, REGION_MOVE, moscow_maps)


class PlacesMixin:
    """Часть окна глобуса GlobeWindow."""

    # «Мои метки».

    @staticmethod
    def _item_colors(item):
        """Цвета объекта для ползунка непрозрачности: линия или значок
        и заливка у метки, цвет у картинки, None у папки."""
        if isinstance(item, OverlayItem):
            return [item.overlay.color, None]
        if isinstance(item, Place):
            return [item.shape.color, item.shape.fill]
        return None

    def _opacity_selection(self, keys):
        """Выделение сменилось: цвета выделенных объектов и содержимого
        выделенных папок снимаются, ползунок встаёт на их
        непрозрачность."""
        if self._opacity_timer.isActive():
            self._opacity_timer.stop()
            self._apply_opacity()
        items = []
        for key in self.myplaces.with_contents(keys):
            colors = self._item_colors(self.myplaces.find(key))
            if colors is not None:
                items.append((key, colors))
        self._opacity_items = items
        self._opacity_base = opacity.selection_opacity(
            [colors for _, colors in items])
        self._opacity_value = self._opacity_base
        self.panel.set_opacity(self._opacity_base if items else None)

    def _opacity_moved(self, value):
        self._opacity_value = value
        self._opacity_timer.start(OPACITY_DELAY)

    def _apply_opacity(self):
        """Новая непрозрачность выделения - в «Мои метки»."""
        if not self._opacity_items:
            return
        self.myplaces.set_colors({
            key: tuple(opacity.scaled(colors, self._opacity_base,
                                      self._opacity_value))
            for key, colors in self._opacity_items})

    def _places_changed(self):
        self.panel.set_places(self.myplaces.tree())
        # Метки, по которым режется подземная модель, могли измениться.
        if hasattr(self, "subsurface"):
            self.subsurface.places_changed()
        self._update_timebar()
        self._refresh_shapes()

    def _update_timebar(self):
        """Охват шкалы времени по видимым меткам со временем."""
        times = [p.time for p in self.myplaces.places if p.visible]
        # Землетрясения на шкале - моменты первого и последнего события.
        quake_span = quakes.span(self.view.quakes.events) \
            if hasattr(self, "view") else None
        if quake_span is not None:
            times += [when.stamp(when.text(t)) for t in quake_span]
        # Пожары - так же, первый и последний снимок сводки.
        fire = self.view.fires.fires if hasattr(self, "view") else None
        fire_span = fires_core.span(fire) if fire is not None else None
        if fire_span is not None:
            times += [when.stamp(when.text(t)) for t in fire_span]
        # Тема NASA на шкале - первый и последний день её ряда.
        weather_on = getattr(self, "theme_key", "") \
            and self._theme_on() and themes.is_weather(self.theme_key)
        theme_span = self.weather.span() if weather_on \
            else themes.span(self._theme_domains.get(self.theme_key)) \
            if getattr(self, "theme_key", "") and self._theme_on() else None
        if theme_span is not None:
            times += [when.stamp(when.text(t)) for t in theme_span]
        # Течения - ряд дней NOAA с 2017 года.
        flow = getattr(self, "flow", None)
        if flow is not None and self.extras.get("currents") \
                and flow.currents_span() is not None:
            times += [when.stamp(when.text(t))
                      for t in flow.currents_span()]
        # Магнитные полюса - с 1590 года по сегодня.
        if self._magnetic_on():
            times += [when.stamp(POLE_FIRST),
                      when.stamp(when.text(time.time()))]
        # Треки и слои проекта со временем - их охват.
        times += getattr(self, "_data_marks", [])
        # Исторические карты с годом - от первой до последней.
        if hasattr(self, "_map_years"):
            times += [when.stamp(when.text(t)) for t in self._map_moments()]
        extent = when.extent(times)
        self.timebar.set_clock(self._clock_on())
        if extent is None and getattr(self, "theme_key", "") \
                and self._theme_on() \
                and (self.weather.span() is None if weather_on
                     else self.theme_key not in self._theme_domains):
            # Ряд новой темы ещё грузится: шкала остаётся как есть,
            # иначе она закрывалась бы на время загрузки.
            return
        self.timebar.set_extent(extent)
        # Панель значков заводится позже первого чтения меток.
        toolbar = getattr(self, "toolbar", None)
        if toolbar is not None:
            toolbar.set_time_available(self.timebar.known)
        self._time_range = self.timebar.range() \
            if self.timebar.shown() else None
        if hasattr(self, "extras") and hasattr(self, "_theme_timer"):
            self._time_mode()
        if hasattr(self, "_layer_time_timer"):
            self._follow_time()

    def _time_bar_closed(self):
        """Шкалу закрыли кнопкой ⏹ на ней самой."""
        self.toolbar.set_time_shown(False)
        self._time_toggled(False)

    def _time_toggled(self, on):
        """Кнопка шкалы. Закрытая шкала метки не скрывает."""
        if on:
            self.timebar.open_bar()
        else:
            self.timebar.close_bar()
        self._time_range = self.timebar.range() \
            if self.timebar.shown() else None
        self._follow_time()
        self._refresh_shapes()
        self._update_sun()
        self._time_quakes()
        self._theme_timer.start()

    def _time_quakes(self):
        """Землетрясения и пожары в промежутке шкалы времени."""
        self.view.quakes.window = self._time_range
        self.view.fires.window = self._time_range
        self.view.update()

    def _time_changed(self, lo, hi):
        self._time_range = (lo, hi)
        self._follow_time()
        self._time_quakes()
        self._refresh_shapes()
        self._update_sun()
        self._theme_timer.start()
        self.flow.set_moment(self.theme_moment())
        if self.view.sky_view is not None:
            self.view.sky_time = self.sky_moment()
            self.view.update()

    def _regions_changed(self):
        """Метки с Region у себя или у папок над ними, после правки
        «Моих меток»."""
        folders = {f.key: f for f in self.myplaces.folders}
        items = []
        for place in self.myplaces.places:
            chain = [place.region] if place.region is not None else []
            folder, seen = folders.get(place.folder), set()
            while folder is not None and folder.key not in seen:
                seen.add(folder.key)
                if folder.region is not None:
                    chain.append(folder.region)
                folder = folders.get(folder.parent)
            if chain:
                items.append((place.key, chain))
        self._region_items = items
        self._region_eye = None
        self._update_regions()

    def _update_regions(self):
        """Метки, скрытые Region по расстоянию от глаза. Пересчёт идёт,
        когда глаз ушёл на REGION_MOVE расстояния до точки взгляда."""
        items = self._region_items
        if not items:
            if self._region_hidden:
                self._region_hidden = frozenset()
                self._refresh_shapes()
            return
        eye = np.array(self.view.camera.eye, dtype=np.float64)
        reach = REGION_MOVE * self.view.navigator.pose.distance
        if self._region_eye is not None \
                and np.linalg.norm(eye - self._region_eye) < reach:
            return
        self._region_eye = eye
        hidden = frozenset(key for key, chain in items
                           if not all(region.active(r, eye)
                                      for r in chain))
        if hidden != self._region_hidden:
            self._region_hidden = hidden
            self._refresh_shapes()

    def _time_ok(self, place):
        """Попадает ли время метки в промежуток шкалы."""
        span = self._time_range
        return span is None or when.visible(place.time, *span)

    def _map_grounds(self):
        """Ключи картинок на поверхности с моментом времени, видных
        по правилу «последняя карта не позже момента»."""
        return oldmaps.shown(self._map_ground_entries(), self._map_moment())

    def _overlay_time_ok(self, item, maps):
        """Видно ли наложение в момент шкалы. Картинка на поверхности
        с моментом - историческая карта, видна последняя в папке, прочие -
        в промежутке шкалы, как метки."""
        if item.kind == "ground" and oldmaps.start(item.time) is not None:
            return item.key in maps
        return self._time_ok(item)

    def _timed_shape(self, place):
        """Объект метки в момент шкалы времени. Путь с промежутком
        времени растёт от начала к концу, пока по нему идёт правый
        бегунок шкалы."""
        shape = self.previews.get(place.key, place.shape)
        span = self._time_range
        if span is None or shape.kind != "line":
            return shape
        return grown(shape, when.share(place.time, span[1]))

    def _stop_reached(self, stop):
        """Тур полетел к остановке: её время и её слои. Слои включаются
        в начале перелёта, чтобы данные успели прийти к прилёту."""
        self._show_time(stop.time)
        self._apply_view_layers(getattr(stop, "layers", None))

    def _apply_view_layers(self, layers):
        """Строки «Слоёв» вида метки: включить и выключить, как при
        снимке вида. Строки, которых нет у окна, пропускаются."""
        for key, on in (layers or {}).items():
            if key in self.extras and bool(self.extras[key]) != on:
                self.set_extra(key, on)

    def _show_time(self, time):
        """Шкала на время вида или метки, как у Google Earth. Закрытая
        шкала при этом открывается - у вида есть дата."""
        span = when.interval(time)
        if span is None or not self.timebar.known:
            return
        if not self.timebar.shown():
            self.timebar.open_bar()
            self.toolbar.set_time_shown(True)
        self.timebar.set_range(*span)

    def _refresh_shapes(self):
        """На глобусе видимые «Мои метки», треки и фигура открытой
        линейки."""
        # Метка с открытым окном свойств показывается с правками окна.
        shapes = [self._timed_shape(p)
                  for p in self.myplaces.places
                  if p.visible and self._time_ok(p)
                  and (not p.tour or p.key in self.previews)
                  and p.body == self.planet.key
                  and p.key not in self._region_hidden]
        # Метки неба подписывает слой подписей неба.
        # Точка метки неба - (склонение, прямое восхождение), как
        # (широта, долгота) у меток глобуса.
        sky = [(p.shape.points[0], p.shape.name)
               for p in self.myplaces.places
               if p.visible and self._time_ok(p) and p.body == "sky"
               and p.shape.points and not p.tour]
        if self.view.sky_view is not None and self._place_open():
            shape = self.place_dialog.shape()
            if shape is not None and shape.points:
                sky.append((shape.points[0], shape.name))
        self.view.sky_places = [
            (sky_direction(point[1] % 360.0, point[0]), name)
            for point, name in sky]
        if getattr(self, "tracks", None) is not None and self.planet.earth:
            shapes += self.tracks.shapes()
        if getattr(self, "satellite_manager", None) is not None \
                and self.planet.earth:
            shapes += self.satellite_manager.shapes()
        shapes += getattr(self, "grid_shapes", [])
        shapes += getattr(self, "parcel_shapes", [])
        shapes += self._pole_shapes()
        shapes += getattr(self, "motion_shapes", [])
        if self._ruler_open():
            shape = self.ruler.shape()
            if shape is not None:
                shapes.append(shape)
        elif self._place_open():
            shape = self.place_dialog.shape()
            if shape is not None:
                shapes.append(shape)
        shapes += [self.previews[key] for key in
                   getattr(self, "overlay_dialogs", {})
                   if key in self.previews]
        self.view.set_shapes([self._drawn_shape(s) for s in shapes])
        self._set_flow_paths([s for s in shapes if s.kind == "line"
                              and getattr(s, "flow", False)
                              and len(s.points) > 1 and s.alts is None])
        self._refresh_overlays()

    # Поток по путям (core/pathflow.py).

    def _set_flow_paths(self, shapes):
        """Пути с потоком на глобусе. Сгущённый путь помнится по точкам,
        таймер штрихов идёт, пока такие пути есть."""
        cache = getattr(self, "_flow_cache", {})
        kept = {}
        paths = []
        for shape in shapes:
            key = tuple(tuple(p) for p in shape.points)
            path = cache.get(key) or kept.get(key)
            if path is None:
                # Пути из одной точки отсеяны в _refresh_shapes.
                path = pathflow.Path(shape.points)
            kept[key] = path
            paths.append((path, shape.color, shape.width,
                          float(shape.height or 0.0)))
        self._flow_cache = kept
        self._flow_paths = paths
        timer = getattr(self, "_flow_timer", None)
        if timer is None:
            timer = self._flow_timer = QTimer(self)
            timer.setInterval(FLOW_TICK)
            timer.timeout.connect(self._tick_flow)
        if paths and not timer.isActive():
            timer.start()
        elif not paths:
            timer.stop()
        self._tick_flow()

    def _tick_flow(self):
        """Штрихи потока на этот момент: шаг - доля ширины вида, только
        у точки взгляда, по рельефу."""
        paths = getattr(self, "_flow_paths", [])
        if not paths:
            self.view.path_flow.clear()
            self.view.update()
            return
        width = self._view_width()
        spacing = pathflow.spacing_for(width)
        phase = pathflow.phase_at(time.monotonic())
        pose = self.view.navigator.pose
        reach = math.degrees(FLOW_REACH * width / ellipsoid.A)
        near = (pose.lat, pose.lon, reach)
        store = self.view.store
        groups = []
        count = 0
        for path, color, line_width, height in paths:
            lats, lons = pathflow.dashes(path, spacing, phase, near=near)
            if not len(lats):
                continue
            lats, lons = lats[:pathflow.DASH_LIMIT - count], \
                lons[:pathflow.DASH_LIMIT - count]
            count += len(lats)
            ground = np.asarray(store.heights_at(lats.ravel(),
                                                 lons.ravel()))
            if self.view.sea_floor:
                ground = np.maximum(ground, 0.0)
            xyz = geodetic_to_ecef(lats.ravel(), lons.ravel(),
                                   ground + height + FLOW_LIFT)
            groups.append((np.asarray(xyz).reshape(lats.shape + (3,)),
                           pathflow.dash_color(color),
                           float(line_width) + FLOW_WIDER))
            if count >= pathflow.DASH_LIMIT:
                break
        self.view.path_flow.set_groups(groups)
        self.view.update()

    def _drawn_shape(self, shape):
        """3D-объект так, как он стоит на поднятом рельефе: к настоящей
        высоте точки добавлен подъём рельефа под ней."""
        scale = self.view.store.scale
        if not has_alts(shape) or not scale or scale == 1.0:
            return shape
        lat = np.array([p[0] for p in shape.points])
        lon = np.array([p[1] for p in shape.points])
        drawn = np.asarray(self.view.store.heights_at(lat, lon))
        alts = np.asarray(shape.alts, dtype=np.float64) + drawn \
            - drawn / scale
        return shape._replace(alts=tuple(float(a) for a in alts))

    # Сцена.

    def record_tour(self, folder=None, mode="frames", size=(0, 0)):
        """Записать показанный тур: кадры PNG в папку folder или видео
        MP4 в файл folder (mode «video»). Без folder - окно выбора
        записи, потом папки или файла. Возвращает True, если запись
        началась."""
        if self.recorder.active or not self.tour.stops:
            return False
        if folder is None:
            dialog = RecordDialog(self)
            if not dialog.exec():
                return False
            mode, size = dialog.choice()
            if mode == "video":
                folder, _ = QFileDialog.getSaveFileName(
                    self, tr("Видео тура"), "tour.mp4",
                    tr("Видео MP4 (*.mp4)"))
            else:
                folder = QFileDialog.getExistingDirectory(
                    self, tr("Папка для кадров тура"))
            if not folder:
                return False
        self.tour.pause_for_record()
        return self.recorder.start(self.tour.stops,
                                   self.tour.bar.pause.value(), folder,
                                   mode, size)

    def _recorded(self, ok, text):
        self.message = (text, time.monotonic())
        self.tour._show()
        self._show_state()

    def save_scene(self, path=None):
        """Сцена в файл. Метки и тур - выбранная папка «Моих меток»."""
        folder = self.panel.current_folder()
        if path is None:
            name = self.myplaces.find(folder).name if folder else "PlanetX"
            path, _ = QFileDialog.getSaveFileName(
                self, tr("Сохранить сцену"), (name or "PlanetX") + EXTENSION,
                tr("Сцена PlanetX (*{ext})", ext=EXTENSION))
        if not path:
            return False
        name = os.path.splitext(os.path.basename(path))[0]
        scene, kml = capture_scene(self, folder, name)
        try:
            with open(path, "wb") as fh:
                fh.write(write_scene(scene, kml))
        except OSError as error:
            QMessageBox.warning(self, tr("Сохранить сцену"), tr(
                "Файл не записан: {error}", error=str(error)))
            return False
        self.message = (tr("Сцена сохранена: {path}", path=path),
                        time.monotonic())
        self._show_state()
        return True

    def share_view(self, path=None, show=True):
        """Страница HTML вида, ui/share.py."""
        from ..share import share_view
        path = share_view(self, path, show)
        if path:
            self.message = (tr("Страница записана: {path}", path=path),
                            time.monotonic())
            self._show_state()
        return path

    def open_demo(self, name="perm"):
        """Демо из папки модуля, tools/make_demo.py: perm, bocachica,
        japan, subsurface, vegas, aral, mars, jezero, moon, sky. У
        subsurface после
        сцены строится подземное из planetx/demo/subsurface. У japan
        открывается окно «Разрез» по первому пути папки демо без тура."""
        journal.note("open_demo {}".format(name))
        demo = os.path.join(PLUGIN_DIR,
                            "demo")
        # Крупные файлы демо - в выпуске GitHub, core/demofiles.py.
        folders = self._demo_folders()
        need = demofiles.missing(name, folders)
        if need:
            self._fetch_demo(name, need)
            return None
        scene = demofiles.locate(name + EXTENSION, folders) \
            if name + EXTENSION in demofiles.FILES \
            else os.path.join(demo, name + EXTENSION)
        key = self.open_scene(scene)
        if name == "japan" and key is not None:
            lines = [p for p in self.myplaces.places_in(key)
                     if p.shape.kind == "line" and not p.tour]
            if lines:
                self._open_section(lines[0].name, lines[0].shape.points)
                # За 30 суток очаги у этой линии лежат в 100-155 км от неё,
                # полоса демо шире умолчания. Выбор помощника.
                self.section_dialog.band.setValue(DEMO_QUAKE_BAND)
        # Подземные демо кладут данные в проект QGIS группой обычных
        # слоёв, глобус показывает их в 3D по флажкам «Слоёв проекта».
        # Решение автора от 4 октября 2026 года.
        if name == "subsurface":
            folder = os.path.join(demo, "subsurface")
            self.subsurface_layers(
                tr("Пермские отложения"),
                os.path.join(folder, "perm_subsurface.gpkg"),
                ("collar", "interval", "survey", "beds", "sections", "cut",
                 "images"),
                sorted(os.path.join(folder, f) for f in os.listdir(folder)
                       if f.startswith("roof_") and f.endswith(".tif")),
                opacity=0.6, cut=True)
        if name == "vegas":
            # Тоннели на 12 м под улицами видны сквозь полупрозрачную
            # поверхность. Непрозрачность 0.5 - выбор помощника.
            self.subsurface_layers(
                tr("Тоннели Vegas Loop"),
                os.path.join(demo, "vegas", "vegas_loop.gpkg"),
                ("tunnels",), (), opacity=0.5, cut=False)
        if name == "quarry":
            # Съёмка карьера - растр проекта, рельеф глобуса через меню
            # слоя. Растр на глобусе картинкой не показывается.
            layer_id = self._demo_raster(
                tr("Карьер, свой рельеф"), tr("Карьер, съёмка 1 м"),
                demofiles.locate("quarry/quarry_dem.tif", folders))
            if layer_id is not None:
                self.set_insets(read_insets() + [layer_id])
        if name in ("quarry", "brienz", "models") and self.theme_key:
            # Демо своего рельефа - без карты витрины поверх снимка.
            self.set_theme("")
        if name == "brienz":
            # Дно озера swissBATHY3D - отметки дна, вода на уровне озера.
            layer_id = self._demo_raster(
                tr("Бриенцское озеро, своя батиметрия"),
                tr("Бриенцское озеро, дно"),
                demofiles.locate("brienz/brienzersee_bed.tif", folders))
            if layer_id is not None:
                lakes = read_bathymetry()
                lakes[layer_id] = ("bed", BRIENZ_LEVEL)
                write_bathymetry(lakes)
                self.set_insets(read_insets() + [layer_id])
        if name == "moscow":
            self._demo_maps(tr("Москва, исторические карты"), moscow_maps())
        return key

    def _demo_folders(self):
        """Где искать крупные файлы демо: папка модуля (рабочая копия),
        потом профиль QGIS. demo_local False - только профиль, так шаг
        проверки заставляет демо скачивать файлы."""
        module = os.path.join(PLUGIN_DIR,
                              "demo")
        cache = os.path.join(QgsApplication.qgisSettingsDirPath(),
                             "PlanetX", "demo")
        return ([module] if getattr(self, "demo_local", True) else []) \
            + [cache]

    def _fetch_demo(self, name, paths):
        """Скачать файлы демо name в профиль и открыть демо по приходу
        всех. Одна загрузка за раз, повторный щелчок её не дублирует."""
        if getattr(self, "_demo_replies", None):
            return
        self._demo_replies = {}
        self._demo_errors = []
        size = demofiles.total_size(paths) / 1e6
        self.message = (tr("Загрузка файлов демо с GitHub, {size} МБ…",
                           size="{:.1f}".format(size)), time.monotonic())
        self._show_state()
        for path in paths:
            self._demo_replies[path] = fetch_bytes(
                demofiles.url(path),
                lambda data, error, p=path: self._demo_arrived(
                    name, p, data, error))

    def _demo_arrived(self, name, path, data, error):
        replies = getattr(self, "_demo_replies", None)
        if not replies or path not in replies:
            return
        del replies[path]
        if data is not None and len(data) == demofiles.FILES[path]:
            target = os.path.join(self._demo_folders()[-1],
                                  *path.split("/"))
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with open(target + ".part", "wb") as fh:
                fh.write(data)
            os.replace(target + ".part", target)
        else:
            self._demo_errors.append(error or tr(
                "размер файла {name} не совпал",
                name=path.rsplit("/", 1)[-1]))
        if replies:
            return
        self._demo_replies = None
        if self._demo_errors:
            self.message = (tr("Демо не загружено: {error}",
                               error=self._demo_errors[0]),
                            time.monotonic())
            self._show_state()
            journal.note("demo download failed {}: {}".format(
                name, self._demo_errors[0]))
            return
        self.message = ("", 0.0)
        self.open_demo(name)

    def _demo_maps(self, title, maps):
        """Исторические карты демо - тайлы XYZ в группе title вверху проекта,
        отмечены на глобусе, с годами карт. Прежняя группа с тем же
        названием заменяется. Шкала времени открывается на первой карте."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        old = root.findGroup(title)
        if old is not None:
            for node in old.findLayers():
                project.removeMapLayer(node.layerId())
            root.removeChildNode(old)
        group = root.insertGroup(0, title)
        years = read_map_years()
        for year, name, url in maps:
            layer = QgsRasterLayer(
                "type=xyz&zmin=0&zmax=18&url=" + quote(url, safe=":/"),
                "{} {}".format(name, year), "wms")
            if not layer.isValid():
                continue
            project.addMapLayer(layer, False)
            group.addLayer(layer)
            years[layer.id()] = year
            self._shown.add(layer.id())
            if self.follow:
                set_visible_on_map(layer.id(), True)
        write_shown(self._shown)
        write_map_years(years)
        self._map_years = years
        self._show_layers()
        self.refresh()
        self._show_time(oldmaps.year_time(min(y for y, _, _ in maps)))

    def _demo_raster(self, title, name, path):
        """Растр демо path в группе title вверху проекта. Прежняя группа
        с тем же названием заменяется. Возвращает номер слоя или None."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        old = root.findGroup(title)
        if old is not None:
            for node in old.findLayers():
                project.removeMapLayer(node.layerId())
            root.removeChildNode(old)
        layer = QgsRasterLayer(path, name, "gdal")
        if not layer.isValid():
            return None
        project.addMapLayer(layer, False)
        root.insertGroup(0, title).addLayer(layer)
        return layer.id()

    def subsurface_layers(self, title, path, tables, rasters, opacity, cut):
        """Данные подземного - демо или шаблон - группа title в проекте
        QGIS, слои отмечены на глобусе. Прежняя группа с тем же
        названием заменяется."""
        ids = add_to_project(title, path, tables, rasters)
        for layer_id in ids:
            self._shown.add(layer_id)
            if self.follow:
                set_visible_on_map(layer_id, True)
        write_shown(self._shown)
        self.subsurface.settings = dict(self.subsurface.settings,
                                        opacity=opacity, cut=cut)
        self._show_layers()
        self.refresh()

    def open_scene(self, path=None):
        """Сцена из файла на глобус. Возвращает ключ папки её меток."""
        if path is None:
            path, _ = QFileDialog.getOpenFileName(
                self, tr("Открыть сцену"), "",
                tr("Сцена PlanetX (*{ext})", ext=EXTENSION))
        if not path:
            return None
        try:
            with open(path, "rb") as fh:
                scene, kml = read_scene(fh.read())
        except (OSError, SceneError) as error:
            QMessageBox.warning(self, tr("Открыть сцену"), tr(
                "Файл не прочитан: {error}", error=str(error)))
            return None
        key, missing = apply_scene(self, scene, kml)
        if key is not None:
            self.panel.select_place(key)
        if missing:
            self.message = (tr("Сцена открыта, слои не найдены: {names}",
                               names=", ".join(missing)),
                            time.monotonic())
            self._show_state()
        return key

    def _open_track(self, layer):
        """Окно «Трек» точечного слоя."""
        dialog = TrackDialog(layer, self.tracks.settings.get(layer.id()),
                             self)
        if dialog.exec():
            self.tracks.set_track(layer, None if dialog.removed
                                  else dialog.settings())
