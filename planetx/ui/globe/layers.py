# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Слои проекта на глобусе: векторная основа, наложение, исторические карты,
время слоёв, магнитные полюса, геоид, магнитные аномалии, подписи источников и
связь с проектом.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import html
import math
import os
import re
import time
from functools import partial

import numpy as np
from qgis.core import QgsApplication, QgsProject, QgsSettings
from qgis.PyQt.QtCore import QEvent
from qgis.PyQt.QtGui import QImage
from qgis.PyQt.QtWidgets import QInputDialog, QMessageBox

from ... import journal
from ...core import (basemap, cadastre, clouds, fields, geoid, geomag,
                     platemotion, sun, tomography,
                     temperature, when, oldmaps, deposits as deposits_core,
                     mining, cables as cables_core, rumsey as rumsey_core,
                     plants as plants_core, fires as fires_core, crust, plates,
                     volcanoes as volcanoes_core, faults as faults_core,
                     geology, iscgem, quakes, slabs, themes, tilemaps,
                     satellites as satellites_core,
                     trains as trains_core, vessels as vessels_core,
                     aircraft as aircraft_core)
from ...core import sources as datasources
from ...core import tileoverlays, wikipedia
from ...core.features import Shape
from ...core.coords import FORMATS as COORD_FORMATS
from ...core.geocode import link_zoom
from ...core.sync import ground_size
from ...core.mipmap import mip_chain
from ..flow import CURRENTS_ATTRIBUTION
from ..overpass import brief_error
from ...i18n import tr
from ...net.loader import TileLoader
from ...net.overlay import (LINE_GROUPS, RAIL_FROM, RAILWAYS, label_kinds,
                            railway_layer, LayerOverlay, fetch_bytes,
                            fetch_json, openfreemap_layer, set_line_groups)
from ...qt_compat import enum
from ...render.view import start_keys
from ..identify import Group
from ..legend import class_names, class_titles, field_titles
from ..layer_labels import range_key
from ..project import (AUTO_REFRESH, FOLLOW, map_layers, layer_group,
                       read_flag, read_grids, read_map_years,
                       read_pointclouds, read_zlayers, read_ztrue,
                       visible_on_map,
                       write_flag, write_map_years, write_pointclouds,
                       write_shown)
from ..sources import SourcesDialog
from ..properties import PropertiesDialog
from ..pointcloud import class_names as cloud_class_names, cloud_ids
from ...core import pointcloud as cloud_core
from ..subsurface import subsurface_ids
from ..weather import field_attribution
from ..track import date_range, layer_span, timed_layer
from ...core.places import Place as MarkPlace
from .base import (AUTO_DEFAULT, COORDS_KEY, CREDIT_LINK, DATA_DIR, DECL_EAST,
                   DECL_LABEL_POINTS, DECL_WEST, DECL_WIDTH, DECL_ZERO,
                   DECL_ZERO_WIDTH, GEOID_SCALE_KEY,
                   MAGNETIC_ATTRIBUTION, MARGIN, NEW_SHOWN_KEY, POLE_COLORS,
                   POLE_WIDTH, REFRESH_DELAY, SELECTION_DELAY, SKY_ATTRIBUTION,
                   TILE_SIZE, attribution_html, imagery_preparer,
                   label_languages, link_html, places_decoder, prepare_field,
                   prepare_geology, prepare_tilemap)


def field_texts():
    """Карта значений: ключ - (группа окна «Объекты», строка, единица,
    строки пояснений)."""
    return {
        "emag": (tr("Магнитная аномалия"), tr("Аномалия поля"), tr("нТл"),
                 [(tr("Высота сетки"), tr("4 км над эллипсоидом")),
                  (tr("Набор"), "EMAG2v3, NOAA NCEI")]),
        "seafloor_age": (tr("Океаническое дно"), tr("Возраст коры"),
                         tr("млн лет"),
                         [(tr("Набор"), "Seton et al. 2020, EarthByte")]),
        "gravity": (tr("Сила тяжести"), tr("Аномалия в свободном воздухе"),
                    tr("мГал"),
                    [(tr("Набор"), "XGM2019e, Zingerle et al. 2020")]),
        "bouguer": (tr("Сила тяжести"), tr("Аномалия Буге"), tr("мГал"),
                    [(tr("Набор"), "XGM2019e, ETOPO 2022"),
                     (tr("Плотность породы"), "2670 кг/м³")]),
        "heatflow": (tr("Тепловой поток"), tr("Поток тепла"),
                     tr("мВт/м²"),
                     [(tr("Набор"), "IHFC 2024, Petrunin et al. 2026")]),
    }


class LayersMixin:
    """Часть окна глобуса GlobeWindow."""

    # Переход выбранного состояния на глобус.

    def _changed(self):
        """Выбранное состояние изменилось."""
        if getattr(self, "tracks", None) is not None:
            self.tracks.set_visible(self._shown)
        self._sync_properties()
        self._show_layers()
        if self.auto_refresh:
            self.refresh_timer.start(REFRESH_DELAY)
        else:
            self._mark_dirty(self._pending())

    def _pending(self):
        """Есть ли выбранное, что ещё не видно на глобусе. У Марса
        и Луны подложка своя, земные подложка и слои ждут Земли."""
        if not self.planet.earth:
            return False
        return (self.source is not self._earth_source()
                or self._relief_target() != self.view.store.scale
                or self._overlay_layers() != self._applied_layers
                or self._layers_stale)

    def refresh(self):
        """Показать на глобусе выбранные подложку, рельеф и слои. У Марса
        и Луны подложка своя, она остаётся."""
        self.refresh_timer.stop()
        if self.planet.earth:
            self._switch_basemap(self._earth_source())
        self.view.set_relief(self._relief_target())
        self._update_water()
        self.subsurface.relief_changed()
        self._place_quakes()
        self._place_fires()
        self._place_deposits()
        self._apply_vector(force=True)
        self._mark_dirty(False)
        self._show_attribution()

    def _apply_vector(self, force=False):
        """Показать выбранную векторную основу и отмеченные слои.

        force=False - как при флажке в панели «Слои»: слои проекта
        остаются прежними до кнопки «Обновить».
        """
        if force and self.planet.earth and hasattr(self, "subsurface"):
            # Геологические слои - в 3D, как обычные слои глобуса.
            self.subsurface.sync_project(self._shown_in_order(),
                                         restyle=self._layers_stale)
        if force and hasattr(self, "extruder"):
            # Выдавленные слои - только на Земле, sync это проверяет.
            self.extruder.sync(self._shown_in_order())
        if hasattr(self, "pointclouds"):
            # Облака точек - точками в 3D, только на Земле.
            self.pointclouds.sync(self._shown_in_order()
                                  if self.planet.earth else [])
        layers = self._overlay_layers() if force else self._applied_layers
        if layers is None:
            layers = self._overlay_layers()
        lines = self._groups & set(LINE_GROUPS)
        old_lines = (self._applied_groups or set()) & set(LINE_GROUPS)
        self._applied_groups = set(self._groups)
        if self._groups and self.ofm_layer is None \
                and self._tilejson is None:
            self._tilejson = fetch_json(self._vector_choice(),
                                        self._tilejson_done)
        self.view.label_kinds = label_kinds(self._groups) \
            if self.planet.earth else set()
        self.view.update()
        # Наложение перерисовывается, только если сменились линии
        # или слои. Надписи пунктов рисует вид. Изменённые слои проекта
        # переходят на глобус только по кнопке «Обновить».
        stale = self._layers_stale and force
        if lines != old_lines or layers != self._applied_layers \
                or stale or self.overlay is None and layers:
            self._applied_layers = layers
            if force:
                self._layers_stale = False
            if self.ofm_layer is not None:
                set_line_groups(self.ofm_layer, lines)
            self._update_overlay(keep=True)
            # Подписи слоёв - заново: сменились слои или их данные.
            self._update_layer_labels(force=True)
            # Охват времени слоёв на шкале мог смениться.
            self._update_data_marks()
        self._show_attribution()

    def _switch_basemap(self, source, coarse=False):
        if source is self.source:
            return
        journal.note("basemap {}".format(source.name))
        # Прежняя подложка держится на экране, пока не придут новые
        # тайлы, и растворяется.
        self.view.crossfade(lambda: self.view.load_missing == 0)
        old = self.loader
        old.abort()
        old.deleteLater()
        self.errors.clear()
        self.source = source
        self._start_loader()
        self.view.change_source(source.max_level, coarse=coarse)
        if self.extras.get("contours") \
                and self._palette_for(source) != self._contour_palette:
            # Подложка сменилась со снимка на карту или обратно.
            self._set_contours(self._surface_source())
        # Уровни 0-2 просятся сразу. Вид не рисует кадр, пока их нет,
        # и сам их не попросит. Без этого смена подложки до прихода
        # уровней 0-2 оставляла окно пустым, нашлось 26 сентября 2026.
        self.loader.want_many((key, -key[0]) for key in start_keys())
        # Отметка подосновы в открытом каталоге «Добавить данные».
        gallery = getattr(self, "gallery", None)
        if gallery is not None and gallery.isVisible():
            gallery.refresh()

    # Наложение.

    # Облака точек (ui/pointcloud.py).

    def set_pointcloud_style(self, layer_id, data):
        """Цвет, размер точки или классы облака из меню слоя: запись
        проекта и показ."""
        styles = read_pointclouds()
        styles[layer_id] = cloud_core.style(data)
        write_pointclouds(styles)
        self.pointclouds.set_style(layer_id, styles[layer_id])
        self._pointclouds_seen()

    def _pointclouds_seen(self):
        """Меню слоя и шкала облака по встреченным классам и цвету."""
        manager = self.pointclouds
        self.panel.pointcloud_classes = {
            e.layer_id: set(e.seen) for e in manager.entries.values()}
        self.panel.pointcloud_styles = read_pointclouds()
        found = None
        for entry in manager.entries.values():
            by_class = entry.mode == "class" \
                or entry.mode == "rgb" and entry.has_rgb is False
            if by_class and entry.seen:
                names = cloud_class_names()
                shown = sorted(entry.seen if entry.classes is None
                               else entry.seen & entry.classes)
                found = (tr("Классы облака «{name}»", name=entry.name),
                         [(cloud_core.CLASS_COLORS.get(
                             c, cloud_core.OTHER_COLOR),
                           names.get(c, tr("Класс {code}", code=c)))
                          for c in shown], tr("Щелчок - точка облака"))
                break
            if entry.mode == "height" and entry.cloud is not None:
                low = entry.cloud.zmin * entry.zfactor
                high = entry.cloud.zmax * entry.zfactor
                found = (tr("Высоты облака «{name}»", name=entry.name),
                         [(rgb, tr("{value} м", value="{:.0f}".format(
                             low + (high - low) * share)))
                          for share, rgb in reversed(
                              cloud_core.HEIGHT_STOPS)], "")
                break
        if found is not None:
            self.cloud_legend.set_rows(*found)
        self.cloud_legend.setVisible(found is not None)
        self._place_attribution()

    def _overlay_layers(self):
        """Номера отмеченных слоёв проекта в порядке карты, кроме
        геологических - те идут в подземное (_apply_vector)."""
        shown = self._shown_in_order()
        under = subsurface_ids(shown) | set(cloud_ids(shown))
        # Слой-трек рисует трек, его точки картинкой не нужны.
        tracks = getattr(self, "tracks", None)
        if tracks is not None:
            under |= set(tracks.settings)
        return [i for i in shown if i not in under]

    # Исторические карты по годам.

    def _map_moment(self):
        """Момент шкалы для исторических карт - правый бегунок, None - шкала
        закрыта, видны все карты."""
        span = getattr(self, "_time_range", None)
        if span is None or not math.isfinite(span[1]):
            return None
        return span[1]

    def _map_layer_entries(self):
        """Растры проекта с годом карты на глобусе: (номер, группа,
        секунды)."""
        years = getattr(self, "_map_years", {})
        applied = set(getattr(self, "_applied_layers", None) or ())
        return [(i, layer_group(i), when.parse(oldmaps.year_time(y)[0]))
                for i, y in years.items() if i in applied]

    def _map_ground_entries(self):
        """Картинки на поверхности с моментом времени: (ключ, папка,
        секунды)."""
        entries = []
        for item in self.myplaces.overlays:
            at = oldmaps.start(item.time) if item.kind == "ground" \
                else None
            if at is not None and item.visible \
                    and item.body == self.planet.key:
                entries.append((item.key, item.folder, at))
        return entries

    def _maps_hidden(self):
        """Номера растров-карт, скрытых правилом «последняя карта
        не позже момента». Запоминается для слежения за шкалой."""
        entries = self._map_layer_entries()
        seen = oldmaps.shown(entries, self._map_moment())
        hidden = frozenset(i for i, _, _ in entries if i not in seen)
        self._applied_maps = hidden
        return hidden

    def _map_moments(self):
        """Моменты всех карт с годом на глобусе - для охвата и шагов
        шкалы."""
        return [at for _, _, at in self._map_layer_entries()
                + self._map_ground_entries()]

    def _map_step(self, moment, delta):
        """Шаг шкалы ◂ ▸ по годам карт."""
        return oldmaps.step(self._map_moments(), moment, delta)

    def edit_map_year(self, layer_id):
        """Пункт «Год карты…» меню растра."""
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return
        years = read_map_years()
        year = years.get(layer_id)
        current = "" if year is None else str(year if year > 0
                                                else year - 1)
        while True:
            text, ok = QInputDialog.getText(
                self, tr("Год карты"),
                tr("Год карты «{name}». Пустое поле - карта без года, "
                   "год до н. э. - со знаком минус.", name=layer.name()),
                text=current)
            if not ok:
                return
            try:
                year = oldmaps.parse_year(text)
            except ValueError:
                current = text
                QMessageBox.warning(self, tr("Год карты"),
                                    tr("Год - целое число, например 1890."))
                continue
            break
        if year is None:
            years.pop(layer_id, None)
        else:
            years[layer_id] = year
        write_map_years(years)
        self._read_map_years()
        if year is not None:
            # Шкала открывается на годе карты.
            self._show_time(oldmaps.year_time(year))

    def _read_map_years(self):
        """Годы карт из проекта, охват шкалы и наложение заново."""
        self._map_years = read_map_years()
        self._update_timebar()
        self._update_overlay(keep=True)

    def _shown_in_order(self):
        return [layer.id() for layer in map_layers()
                if layer.id() in self._shown]

    # Время слоёв проекта и треков.

    def _temporal_layers(self):
        """Слои проекта на глобусе с действующими временными свойствами
        QGIS."""
        project = QgsProject.instance()
        layers = (project.mapLayer(layer_id) for layer_id
                  in getattr(self, "_applied_layers", None) or ())
        return [layer for layer in layers if timed_layer(layer)]

    def _layer_range(self):
        """Промежуток шкалы времени для слоёв со временем,
        QgsDateTimeRange. None - шкала закрыта или таких слоёв нет,
        тогда слои рисуются целиком, как и метки."""
        span = getattr(self, "_time_range", None)
        if span is None or not self.planet.earth \
                or not self._temporal_layers():
            return None
        return date_range(*span)

    def _maps_changed(self):
        """Сменился ли набор видимых растров-карт с прошлой сборки."""
        entries = self._map_layer_entries()
        if not entries:
            return bool(self._applied_maps)
        seen = oldmaps.shown(entries, self._map_moment())
        return frozenset(i for i, _, _ in entries if i not in seen) \
            != self._applied_maps

    def _apply_layer_time(self):
        """Картинки и подписи слоёв со временем заново, если промежуток
        шкалы для них сменился."""
        self._apply_map_compare()
        if range_key(self._layer_range()) == self._applied_time \
                and not self._maps_changed():
            return
        self._update_overlay(keep=True)
        self._update_layer_labels(force=True)

    def _update_data_marks(self):
        """Охват времени треков и слоёв проекта со временем на шкале.
        Охват слоя просматривает его поля, поэтому он считается при
        смене треков и слоёв, а не при движении шкалы."""
        spans = [self.tracks.data_span()] if hasattr(self, "tracks") \
            else []
        spans += [layer_span(layer) for layer in self._temporal_layers()]
        self._data_marks = [when.stamp(when.text(t))
                            for span in spans if span is not None
                            for t in span]
        self._update_timebar()

    def _follow_time(self):
        """Треки и слои проекта за шкалой времени: треки - к правому
        бегунку сразу, слои - после паузы в движении бегунков."""
        span = self._time_range
        hi = span[1] if span is not None and math.isfinite(span[1]) \
            else None
        if hasattr(self, "tracks"):
            self.tracks.set_time(hi)
        if range_key(self._layer_range()) != self._applied_time \
                or self._maps_changed():
            self._layer_time_timer.start()
        if hasattr(self, "satellite_manager"):
            self.satellite_manager.time_changed()
        if self._magnetic_on():
            self._refresh_shapes()

    # Магнитные полюса и поле IGRF (core/geomag.py).

    def _poles_on(self):
        return bool(getattr(self, "extras", {}).get("magpoles")) \
            and getattr(self, "planet", None) is not None \
            and self.planet.earth and self.geomag is not None

    def _decl_on(self):
        return bool(getattr(self, "extras", {}).get("magdecl")) \
            and getattr(self, "planet", None) is not None \
            and self.planet.earth and self.geomag is not None

    def _magnetic_on(self):
        """Полюса или линии склонения: шкала времени, подпись, пересчёт
        по году."""
        return self._poles_on() or self._decl_on()

    def _load_geomag(self):
        """Модель поля и таблицы полюсов из файлов модуля, один раз."""
        if self.geomag is not None:
            return True
        try:
            with open(os.path.join(DATA_DIR, "igrf14coeffs.txt"),
                      encoding="ascii") as fh:
                model = geomag.parse_igrf(fh.read())
            with open(os.path.join(DATA_DIR, "magnetic_poles.json"),
                      encoding="utf-8") as fh:
                poles = geomag.parse_poles(fh.read())
            self.geomag = (geomag.Combined(model, self._read_gufm()), poles)
        except (OSError, ValueError, KeyError) as error:
            journal.note("magnetic poles: {}".format(error))
            self.message = (tr("Магнитные полюса не прочитаны."),
                            time.monotonic())
            self._show_state()
            return False
        return True

    @staticmethod
    def _gufm_path():
        return os.path.join(QgsApplication.qgisSettingsDirPath(), "PlanetX",
                            "gufm1.txt")

    def _read_gufm(self):
        """gufm1 из файла профиля или None - его ещё не скачивали."""
        try:
            with open(self._gufm_path(), encoding="ascii") as fh:
                return geomag.parse_gufm(fh.read())
        except (OSError, ValueError) as error:
            if os.path.exists(self._gufm_path()):
                journal.note("gufm1: {}".format(error))
            return None

    def _want_gufm(self, year):
        """Поле до 1900 года - модель gufm1: файл скачивается один раз
        с сайта авторов в профиль QGIS, как группы спутников."""
        if self.geomag is None or year >= self.geomag[0].igrf.first \
                or self.geomag[0].gufm is not None \
                or getattr(self, "_gufm_reply", None) is not None \
                or getattr(self, "_gufm_failed", False):
            return
        self._gufm_reply = fetch_bytes(geomag.GUFM_URL, self._gufm_done)

    def _gufm_done(self, data, error):
        self._gufm_reply = None
        model = None
        if data is not None:
            try:
                model = geomag.parse_gufm(bytes(data).decode("ascii"))
                os.makedirs(os.path.dirname(self._gufm_path()),
                            exist_ok=True)
                with open(self._gufm_path(), "wb") as fh:
                    fh.write(bytes(data))
            except (ValueError, UnicodeDecodeError, OSError) as problem:
                error = str(problem)
        if model is None:
            self._gufm_failed = True
            journal.note("gufm1: {}".format(error))
            self.message = (tr("Поле до 1900 года не загружено: {error}",
                               error=brief_error(error or "")),
                            time.monotonic())
            self._show_state()
            return
        self.geomag[0].gufm = model
        self._decl_cache = None
        self._refresh_shapes()
        self._refresh_identified()
        self._show_attribution()

    def _set_magdecl(self, on):
        """Строка «Линии склонения»: изогоны поля на год шкалы времени,
        шкала открывается сама, как у полюсов."""
        if on and not self._load_geomag():
            return
        self._decl_cache = None
        self._open_magnetic_time(on)

    def _set_poles(self, on):
        """Строка «Магнитные полюса»: полюса на момент шкалы времени и их
        след с 1590 года. Файлы модуля читаются при первом включении,
        шкала открывается сама."""
        if on and not self._load_geomag():
            return
        self._open_magnetic_time(on)

    def _open_magnetic_time(self, on):
        self._mark_gallery()
        self._update_timebar()
        if on and self.planet.earth and self.timebar.known \
                and not self.timebar.shown():
            self.timebar.open_bar()
            self.toolbar.set_time_shown(True)
            self._time_range = self.timebar.range()
        self._refresh_shapes()
        self._show_attribution()

    def magnetic_year(self):
        """Год с дробью для полюсов и поля: правый бегунок открытой
        шкалы времени, без неё - часы компьютера."""
        span = getattr(self, "_time_range", None)
        if span is not None and math.isfinite(span[1]):
            return geomag.year_of(span[1])
        return geomag.year_of(time.time())

    def _magnetic_start(self):
        """Год левого бегунка - начало следа полюсов. None - шкала
        закрыта или с одним бегунком, след идёт с 1590 года."""
        span = getattr(self, "_time_range", None)
        if span is None or not math.isfinite(span[0]) \
                or self.timebar.track.point:
            return None
        return geomag.year_of(span[0])

    def _decl_shapes(self):
        """Линии равного склонения на год шкалы и подписи значений
        (view.geo_marks). Линии считаются заново при смене целого года
        - поле за год меняется на доли градуса, расчёт около 0.2 с."""
        if not self._decl_on():
            if self._decl_marks:
                self._decl_marks = []
                self._set_geo_marks()
            return []
        model, _ = self.geomag
        year = int(math.floor(self.magnetic_year()))
        self._want_gufm(year)
        cache = getattr(self, "_decl_cache", None)
        if cache is None or cache[0] != year:
            # До 1900 года - gufm1, пока его нет - линий нет. После конца
            # IGRF - линии её последнего года.
            year_in = min(year, model.last)
            coeffs = model.at(year_in)
            if coeffs is None:
                self._decl_marks = []
                self._set_geo_marks()
                return []
            lines = geomag.isogonic_lines(*geomag.declination_grid(
                coeffs, model.nmax_at(year_in)))
            cache = self._decl_cache = (year, lines)
        shapes = []
        marks = []
        for n, (level, points) in enumerate(cache[1]):
            if level == 0.0:
                color, width = DECL_ZERO, DECL_ZERO_WIDTH
            else:
                color = DECL_EAST if level > 0 else DECL_WEST
                width = DECL_WIDTH
            shapes.append(Shape("line", points, color=color, width=width))
            if len(points) >= DECL_LABEL_POINTS:
                lat, lon = points[len(points) // 2]
                text = "0°" if level == 0.0 else "{:+.0f}°".format(level)
                marks.append(MarkPlace(-600000 - n, text, "grid", 1,
                                       lat, lon))
        self._decl_marks = marks
        self._set_geo_marks()
        return shapes

    def _set_geo_marks(self):
        """Подписи геофизики на виде: линии склонения и скорости плит."""
        self.view.geo_marks = list(getattr(self, "_decl_marks", [])) \
            + list(getattr(self, "_motion_marks", []))
        self.view.update()

    def _pole_shapes(self):
        """След и точка каждого полюса на год шкалы, след - от левого
        бегунка до правого. Линии склонения - тоже здесь."""
        shapes = self._decl_shapes()
        if not self._poles_on():
            return shapes
        model, poles = self.geomag
        year = self.magnetic_year()
        start = self._magnetic_start()
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

    # Геоид EGM2008 (core/geoid.py).

    def _geoid_on(self):
        return bool(getattr(self, "extras", {}).get("geoid")) \
            and getattr(self, "planet", None) is not None \
            and self.planet.earth

    def _set_geoid(self, on):
        """Строка «Геоид»: высоты Земли - тайлы геоида с масштабом
        geoid.SCALE, вода не рисуется - половина геоида ниже нуля.
        Выключение возвращает рельеф, масштаб и глубины морей."""
        self._geoid_look()
        self._body_terrain(self.planet)
        self.view.reset_heights()
        self.view.set_relief(self._relief_target())
        self._update_water()
        self._place_quakes()
        self._place_fires()
        self._place_deposits()
        self._mark_gallery()
        self._show_attribution()
        self.view.update()

    def geoid_scale(self):
        """Масштаб режима «Геоид» - настройка ползунка меню «⋯» его
        строки, по умолчанию geoid.SCALE."""
        value = QgsSettings().value(GEOID_SCALE_KEY, geoid.SCALE,
                                    type=float)
        return min(geoid.SCALES[-1], max(geoid.SCALES[0], float(value)))

    def set_geoid_scale(self, scale):
        """Ползунок масштаба геоида: высоты растягиваются заново сразу,
        разрез Земли следует за поверхностью."""
        QgsSettings().setValue(GEOID_SCALE_KEY, float(scale))
        self.panel.geoid_scale = self.geoid_scale()
        if self._geoid_on():
            self.view.set_relief(self._relief_target())
            self.view.update()

    def _geoid_look(self):
        """Вода и дымка поверхности - их нет в режиме геоида. Половина
        геоида ниже нуля, а поверхность опущена на сотни километров,
        воздух над ней заливал впадины белым."""
        geoid = self._geoid_on()
        self.view.sea_floor = self.sea_depths and self.planet.earth \
            and not geoid
        self.view.surface_air = not geoid
        # Разрез Земли тянется к «измятой» поверхности.
        self.view.wedge_lift = geoid

    # Карты значений геофизики (core/fields.py): магнитные аномалии,
    # возраст дна, сила тяжести, тепловой поток. Один слой вида «emag».

    def _set_field(self, key, on):
        """Строка карты значений: тайлы planetx-terrain, раскраска
        в рабочем потоке, шкала. Включение снимает прежнюю карту."""
        field = fields.FIELDS[key]
        if on:
            for other in fields.KEYS + ("geology",) + tilemaps.KEYS:
                if other != key and self.extras.get(other):
                    self.set_extra(other, False)
        elif self._field_shown != key:
            # Слой вида занят другой картой.
            return
        on = on and self.planet.earth
        self._drop_field()
        if on:
            self.view.gibs["emag"].max_level = field.max_level
            source = basemap.Source(key, self.field_urls[key],
                                    field.max_level, field.attribution,
                                    builtin=True)
            made = (source, partial(prepare_field, key))
        else:
            made = None
        self._field_shown = key if on else None
        self._set_gibs("emag", on, made=made, cache=True)
        self.field_legend.set_field(field)
        self.field_legend.setVisible(on)
        self._mark_gallery()

    def _ask_field(self, lat, lon):
        """Значение карты под щелчком: тайл глубшего уровня из кэша или
        сети, пиксель точки."""
        self._drop_field()
        key = self._field_shown
        if key is None or not self.planet.earth:
            return
        field = fields.FIELDS[key]
        (x, y), (column, row) = fields.pixel_of(lat, lon, field.max_level)
        url = self.field_urls[key].format(z=field.max_level, x=x, y=y)
        point = (lat, lon)
        self._field_value = (key, point, None, "")
        self._field_reply = fetch_bytes(
            url, lambda data, error: self._field_arrived(
                key, point, column, row, data, error))

    def _drop_field(self):
        reply, self._field_reply = self._field_reply, None
        self._field_value = None
        if reply is not None:
            reply.abort()

    def _field_arrived(self, key, point, column, row, data, error):
        state = self._field_value
        if state is None or state[:2] != (key, point):
            return
        self._field_reply = None
        value = None
        if data is not None:
            image = QImage.fromData(data)
            if not image.isNull():
                color = image.pixelColor(column, row)
                value = fields.value_at(fields.FIELDS[key], [[(
                    color.red(), color.green(), color.blue())]], 0, 0)
            error = "" if not image.isNull() else tr("тайл не прочитан")
        self._field_value = (key, point, value, "" if value is not None
                             else error or tr("нет данных"))
        self._refresh_identified()

    def _identify_field(self):
        """Группа карты значений окна «Объекты»."""
        state = self._field_value
        if state is None:
            return []
        key, _, value, error = state
        group, title, unit, notes = field_texts()[key]
        if value is None and not error:
            values = [(tr("Значение"), tr("загрузка…"))]
        elif value is None:
            values = [(tr("Значение"), error)]
        else:
            digits = fields.FIELDS[key].digits
            sign = "+" if fields.FIELDS[key].stops[0][0] < 0 else ""
            number = "{:" + sign + "." + str(digits) + "f}"
            values = [(tr("Значение"), "{} {}".format(
                number.format(value), unit))] + notes
        return [(Group(group), [(title, values, None)])]

    # Геологическая карта Macrostrat (core/geology.py) - тот же слой вида
    # «emag», что у карт значений, на глобусе одна такая карта.

    def _geology_shown(self):
        return bool(getattr(self, "extras", {}).get("geology")) \
            and getattr(self, "planet", None) is not None \
            and self.planet.earth

    def _set_geology(self, on):
        """Строка «Геологическая карта»: тайлы Macrostrat, щелчок даёт
        породу. Включение снимает карту значений."""
        if on:
            for other in fields.KEYS + tilemaps.KEYS:
                if self.extras.get(other):
                    self.set_extra(other, False)
        elif self._field_shown is not None \
                or self._tilemap_shown is not None:
            # Слой вида занят другой картой.
            self._drop_geology()
            return
        on = on and self.planet.earth
        self._drop_geology()
        made = None
        if on:
            self.view.gibs["emag"].max_level = geology.MAX_LEVEL
            source = basemap.Source("Macrostrat", geology.TILES,
                                    geology.MAX_LEVEL, geology.ATTRIBUTION,
                                    builtin=True)
            made = (source, prepare_geology)
        self._set_gibs("emag", on, made=made, cache=True)
        self.field_legend.setVisible(False)
        self._place_attribution()
        self._mark_gallery()

    def _ask_geology(self, lat, lon):
        """Порода под щелчком: запрос map_query Macrostrat на уровне
        карты вида."""
        self._drop_geology()
        if not self._geology_shown():
            return
        pose = self.view.navigator.pose
        width, _ = ground_size(pose.distance, self.view.camera.fov_y,
                               self.view.camera.aspect)
        self._geology_value = ((lat, lon), None, "")
        self._send_geology(lat, lon, link_zoom(lat, width))

    def _send_geology(self, lat, lon, z):
        point = (lat, lon)
        self._geology_reply = fetch_bytes(
            geology.query_url(lat, lon, z),
            lambda data, error: self._geology_arrived(point, z, data,
                                                      error))

    def _drop_geology(self):
        reply, self._geology_reply = self._geology_reply, None
        self._geology_value = None
        if reply is not None:
            reply.abort()

    def _geology_arrived(self, point, z, data, error):
        state = self._geology_value
        if state is None or state[0] != point:
            return  # ответ снятого или прежнего запроса
        self._geology_reply = None
        units = None
        if data is not None:
            try:
                units = geology.parse_query(bytes(data))
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        if units == [] and geology.coarser(z) is not None:
            # Глубже карты места ответ пуст - та же точка мельче.
            self._send_geology(point[0], point[1], geology.coarser(z))
            return
        self._geology_value = (point, units, error or "")
        self._refresh_identified()

    def _identify_geology(self):
        """Группа «Геология» окна «Объекты»."""
        state = self._geology_value
        if state is None:
            return []
        (lat, lon), units, error = state
        if units is None and not error:
            features = [(tr("Запрос к Macrostrat…"), [], None)]
        elif units is None:
            features = [(tr("Macrostrat не ответил"),
                         [(tr("Ошибка"), error)], None)]
        elif not units:
            features = [(tr("Карта в точке пуста"), [], None)]
        else:
            features = []
            for unit in units:
                names, ages = geology.age_text(unit)
                values = []
                if names:
                    values.append((tr("Возраст"), names))
                if ages:
                    values.append((tr("Возраст, млн лет"), ages))
                for label, key in ((tr("Литология"), "lith"),
                                   (tr("Свита"), "strat_name"),
                                   (tr("Описание"), "descrip"),
                                   (tr("Примечание"), "comments")):
                    if unit[key]:
                        values.append((label, unit[key]))
                source = ", ".join(v for v in (
                    unit["source"], unit["authors"], unit["year"]) if v)
                if source:
                    values.append((tr("Карта"), source))
                if unit["url"]:
                    values.append((tr("Ссылка на карту"), unit["url"]))
                values.append((tr("Страница Macrostrat"),
                               geology.page_url(lat, lon)))
                features.append((unit["name"] or unit["lith"]
                                 or tr("Без названия"), values, None))
        return [(Group(tr("Геология")), features)]

    # Карты картинками (core/tilemaps.py) - литология GLiM, воды JRC,
    # почвы SoilGrids. Тот же слой вида «emag», на глобусе одна карта.

    def _set_tilemap(self, key, on):
        """Строка карты картинками: тайлы службы или planetx-terrain,
        цвет «нет данных» прозрачен, шкала. Включение снимает прежнюю
        карту слоя вида."""
        tmap = tilemaps.MAPS[key]
        if on:
            for other in fields.KEYS + ("geology",) + tilemaps.KEYS:
                if other != key and self.extras.get(other):
                    self.set_extra(other, False)
        elif self._tilemap_shown != key:
            return  # слой вида занят другой картой
        on = on and self.planet.earth
        self._drop_tilemap()
        made = None
        if on:
            self.view.gibs["emag"].max_level = tmap.max_level
            if tmap.coarse:
                source = basemap.SplitSource(
                    key, self.tilemap_urls[key], self.tilemap_coarse[key],
                    tmap.split, tmap.max_level, tmap.attribution,
                    builtin=True)
            else:
                kind = basemap.WmsSource if tmap.wms else basemap.Source
                source = kind(key, self.tilemap_urls[key], tmap.max_level,
                              tmap.attribution, builtin=True)
            made = (source, partial(prepare_tilemap, key))
        self._tilemap_shown = key if on else None
        self._set_gibs("emag", on, made=made, cache=True)
        ramp = on and tmap.stops is not None
        if ramp:
            self.field_legend.set_field(tmap)
        self.field_legend.setVisible(ramp)
        if on and tmap.classes:
            self.class_legend.set_map(tmap)
        self.class_legend.setVisible(bool(on and tmap.classes))
        self._place_attribution()
        self._mark_gallery()

    def _ask_tilemap(self, lat, lon):
        """Значение карты под щелчком: запрос GetFeatureInfo службы или
        пиксель тайла глубшего уровня из кэша или сети."""
        self._drop_tilemap()
        key = self._tilemap_shown
        if key is None or not self.planet.earth:
            return
        tmap = tilemaps.MAPS[key]
        point = (lat, lon)
        self._tilemap_value = (key, point, None, "")
        url = tilemaps.query_url(tmap, lat, lon)
        if url is not None:
            self._tilemap_reply = fetch_bytes(
                url, lambda data, error: self._tilemap_arrived(
                    key, point, None, data, error))
            return
        (x, y), pixel = fields.pixel_of(lat, lon, tmap.max_level)
        url = self.tilemap_urls[key].format(z=tmap.max_level, x=x, y=y)
        self._tilemap_reply = fetch_bytes(
            url, lambda data, error: self._tilemap_arrived(
                key, point, pixel, data, error))

    def _drop_tilemap(self):
        reply, self._tilemap_reply = self._tilemap_reply, None
        self._tilemap_value = None
        if reply is not None:
            reply.abort()

    def _tilemap_arrived(self, key, point, pixel, data, error):
        state = self._tilemap_value
        if state is None or state[:2] != (key, point):
            return
        self._tilemap_reply = None
        tmap = tilemaps.MAPS[key]
        value = None
        if data is not None and pixel is None:
            value = tilemaps.parse_query(tmap, bytes(data))
            error = ""
        elif data is not None:
            image = QImage.fromData(data)
            if image.isNull():
                error = tr("тайл не прочитан")
            else:
                color = image.pixelColor(*pixel)
                value = tilemaps.value_of(tmap, (
                    color.red(), color.green(), color.blue(),
                    color.alpha()))
                error = ""
        elif error and "404" in str(error):
            error = ""  # тайла нет - на месте пусто
        self._tilemap_value = (key, point, value,
                               "" if value is not None
                               else error or tr("нет данных"))
        self._refresh_identified()

    def _identify_tilemap(self):
        """Группа карты картинками окна «Объекты»."""
        state = self._tilemap_value
        if state is None:
            return []
        key, _, value, error = state
        tmap = tilemaps.MAPS[key]
        title = (class_titles() if tmap.classes else field_titles()).get(
            key, key)
        if value is None and not error:
            values = [(tr("Значение"), tr("загрузка…"))]
        elif value is None:
            values = [(tr("Значение"), error)]
        elif tmap.classes:
            values = [(tr("Класс"), class_names().get(value, value))]
        else:
            number = "{:." + str(tmap.digits) + "f}"
            values = [(tr("Значение"), "{} {}".format(
                number.format(value), tmap.unit).strip())]
        group = {"glim": tr("Литология"), "water_occurrence": tr("Вода"),
                 "worldcover": tr("Покрытие земель"),
                 "water_transitions": tr("Вода")}.get(key, tr("Почва"))
        return [(Group(group), [(title, values, None)])]

    def _identify_magnetic(self, lat, lon):
        """Группа «Магнитное поле» окна «Объекты»: поле IGRF-14 в точке
        на год шкалы."""
        if not self._magnetic_on():
            return []
        model, _ = self.geomag
        year = self.magnetic_year()
        self._want_gufm(year)
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

    def time_span(self):
        """Промежуток времени треков для записи тура: открытая шкала,
        иначе охват треков. None - треков нет."""
        span = self._time_range
        if span is not None and all(math.isfinite(v) for v in span):
            return span
        return self.tracks.data_span()

    def _start_loader(self):
        """Загрузчик выбранной подложки и её подпись."""
        self.loader = TileLoader(self.source, parent=self,
                                 prepare=imagery_preparer(self.view.store),
                                 size=TILE_SIZE, fill=True)
        self.loader.loaded.connect(self._loaded)
        self.loader.failed.connect(self._failed)
        self.view.loader = self.loader
        self._show_attribution()

    def _show_attribution(self):
        if self.view.sky_view is not None:
            credits = [link_html(*credit) for credit in SKY_ATTRIBUTION]
            self._set_credits(credits, len(credits))
            return
        parts = [attribution_html(self.source)]
        # Подложка и рельеф - целиком, их условия просят полную подпись.
        kept = 1
        if "cadastre" in self.gibs_loaders:
            parts.append(link_html(*cadastre.ATTRIBUTION))
        if self._magnetic_on():
            parts.append(link_html(*MAGNETIC_ATTRIBUTION))
            if self.geomag[0].gufm is not None:
                parts.append(link_html(*geomag.GUFM_ATTRIBUTION))
        if self._motion_on():
            parts.append(link_html(*platemotion.ATTRIBUTION))
        if "emag" in self.gibs_loaders and self._field_shown:
            parts.append(link_html(
                *fields.FIELDS[self._field_shown].attribution))
        elif "emag" in self.gibs_loaders and self._geology_shown():
            parts.append(link_html(*geology.ATTRIBUTION))
        elif "emag" in self.gibs_loaders and self._tilemap_shown:
            parts.append(link_html(
                *tilemaps.MAPS[self._tilemap_shown].attribution))
        if self._geoid_on():
            parts.append(link_html(*geoid.ATTRIBUTION))
        if self.planet.earth and (
                self._applied_groups and self.ofm_layer is not None
                or self.buildings_loader is not None):
            parts.append(self._vector_credit())
        if self.view.store.scale or "slope" in self.gibs_loaders:
            parts.insert(1, self._terrain_credit() if self.planet.earth
                         else html.escape(self.planet.terrain[3])
                         if self.planet.terrain
                         and self.terrain_loader is not None else "")
            kept = 2
        if "clouds" in self.gibs_loaders:
            parts.append(link_html(*clouds.ATTRIBUTION))
        if "theme" in self.gibs_loaders:
            parts.append(link_html(*(
                field_attribution(self.theme_key)
                if themes.is_weather(self.theme_key)
                else themes.BY_KEY[self.theme_key].attribution
                if self.theme_key in themes.BY_KEY
                else themes.ATTRIBUTION)))
        if "lights" in self.gibs_loaders:
            parts.append(link_html(*sun.LIGHTS_ATTRIBUTION))
        if "sea" in self.gibs_loaders:
            parts.append(link_html(*temperature.ATTRIBUTION))
        if self.view.quakes.events:
            parts.append(link_html(*quakes.ATTRIBUTION))
        if self.view.history.events:
            parts.append(link_html(*iscgem.ATTRIBUTION))
        if self.view.fires.fires is not None:
            parts.append(link_html(*fires_core.ATTRIBUTION))
        if self.view.deposits.data is not None:
            parts.append(link_html(*deposits_core.ATTRIBUTION))
        if self.view.osm_mines.data is not None \
                or (self.infra_lines is not None
                    and self.extras.get("infra_osm")):
            parts.append(link_html(*mining.OSM_ATTRIBUTION))
        if self.view.plants.data is not None:
            parts.append(link_html(*plants_core.ATTRIBUTION))
        if self.view.volcanoes.data is not None:
            parts.append(link_html(*volcanoes_core.ATTRIBUTION))
        if self.view.wiki_marks:
            parts.append(link_html(*wikipedia.ATTRIBUTION))
        if self.planet.earth and getattr(self, "extras", {}).get("mining") \
                and self.mining_layer is not None:
            parts.append(link_html(*mining.POLYGONS_ATTRIBUTION))
        manager = getattr(self, "satellite_manager", None)
        if manager is not None and manager.on and manager.count():
            parts.append(link_html(*satellites_core.ATTRIBUTION))
        manager = getattr(self, "train_manager", None)
        if manager is not None and manager.on and manager.count() \
                and self.planet.earth:
            parts.append(link_html(*trains_core.ATTRIBUTION))
        for name, core_module in (("vessel_manager", vessels_core),
                                  ("aircraft_manager", aircraft_core)):
            manager = getattr(self, name, None)
            if manager is not None and manager.on and manager.count() \
                    and self.planet.earth:
                parts.append(link_html(*core_module.ATTRIBUTION))
        if self.planet.earth and getattr(self, "extras", {}).get("plates") \
                and self.plates_data is not None:
            parts.append(link_html(*plates.ATTRIBUTION))
        if self.planet.earth and getattr(self, "extras", {}).get("faults") \
                and getattr(self, "fault_layer", None) is not None:
            parts.append(link_html(*faults_core.ATTRIBUTION))
        if self.planet.earth and self._rumsey_shown():
            parts.append(link_html(*rumsey_core.ATTRIBUTION))
        if self.planet.earth \
                and getattr(self, "extras", {}).get("currents") \
                and getattr(self, "flow", None) is not None \
                and self.flow.fields["currents"] is not None:
            parts.append(link_html(*CURRENTS_ATTRIBUTION))
        if self.planet.earth \
                and getattr(self, "extras", {}).get("cables") \
                and getattr(self, "cable_layer", None) is not None:
            parts.append(link_html(*cables_core.ATTRIBUTION))
        for key, overlay in tileoverlays.OVERLAYS.items():
            if self.planet.earth \
                    and getattr(self, "extras", {}).get(key) \
                    and key in getattr(self, "tile_layers", {}):
                parts.append(link_html(overlay.attribution,
                                       overlay.terms))
        if self.view.wedge_slabs:
            parts.append(link_html(*slabs.ATTRIBUTION))
        if self.view.wedge is not None and self.crust is not None:
            parts.append(link_html(*crust.CITATION))
        if self.view.wedge is not None and self.view.wedge_tomo is not None:
            parts.append(link_html(*tomography.ATTRIBUTION))
        self._set_credits(parts, kept)

    def _set_credits(self, parts, kept):
        """Подпись источников на карте - короткие названия одной строкой
        без ссылок (core.sources.short_credits), щелчок открывает окно
        «Источники данных». Решение автора от 16 октября 2026 года.
        parts - подписи разметкой, первые kept остаются целиком."""
        texts = [html.unescape(re.sub("<[^>]+>", "", part))
                 for part in parts]
        text = " · ".join(datasources.short_credits(texts, kept))
        self.attribution.setText(CREDIT_LINK.format(html.escape(text))
                                 if text else "")
        self._place_attribution()

    def _place_attribution(self):
        # Справа внизу - PlanetX, левее - подпись источников.
        self.brand.adjustSize()
        self.brand.move(self.view.width() - self.brand.width() - MARGIN,
                        self.view.height() - self.brand.height() - MARGIN)
        self.attribution.adjustSize()
        self.attribution.setVisible(bool(self.attribution.text()))
        self.attribution.move(
            max(MARGIN, self.brand.x() - self.attribution.width()
                - MARGIN // 2),
            self.view.height() - self.attribution.height() - MARGIN)
        bar = self.toolbar.geometry()
        self.spinner.move(bar.right() + MARGIN,
                          bar.center().y() - self.spinner.height() // 2)
        # Шкала времени - под панелью значков, как в Google Earth.
        self.timebar.anchor = lambda: (bar.left(), bar.bottom() + MARGIN)
        self.timebar._place()
        # Шкалы слоёв - одной панелью в левом нижнем углу. Узкий вид:
        # над подписью. Ползунок палеогеографии - над панелью.
        panel = getattr(self, "legend_panel", None)
        if panel is None:
            return
        bottom = self.view.height() - MARGIN
        if self.attribution.x() < MARGIN + max(panel.width(),
                                               self.paleo_bar.width()):
            bottom = self.attribution.y() - MARGIN // 2
        panel.move(MARGIN, bottom - panel.height())
        if panel.isVisible():
            bottom = panel.y() - MARGIN // 2
        self.paleo_bar.move(MARGIN, bottom - self.paleo_bar.height())

    def eventFilter(self, watched, event):
        if watched is self.view and event.type() == enum(
                QEvent, "Type", "Resize"):
            self._place_attribution()
            if hasattr(self, "screen_overlays"):
                self.screen_overlays.place()
        return super().eventFilter(watched, event)

    def _tilejson_done(self, data, error):
        self._tilejson = None
        tiles = (data or {}).get("tiles") or []
        if not tiles:
            self.overlay_error = error or "TileJSON"
            self._show_state()
            return
        self.overlay_error = ""
        max_zoom = int(data.get("maxzoom", 14))
        self.ofm_layer = openfreemap_layer(tiles[0], max_zoom,
                                           self._applied_groups or ())
        self.rail_layer = railway_layer(tiles[0], max_zoom)
        # Названия пунктов - из тех же векторных тайлов, свой загрузчик.
        self._places_source = basemap.Source("OpenFreeMap", tiles[0],
                                             max_zoom)
        self._ofm_source = basemap.Source("OpenFreeMap", tiles[0], max_zoom)
        self._start_place_loader()
        # TileJSON просят и здания без векторной основы. Тогда наложение
        # не пересобирается, картинки слоёв проекта остаются.
        if self._applied_groups:
            self._update_overlay()
        if self.extras.get("buildings") and self.buildings_loader is None:
            self._set_buildings(True)
        self._show_attribution()

    def _start_place_loader(self):
        """Загрузчик пунктов на выбранном языке, пункты с нуля."""
        old = self.place_loader
        if old is not None:
            old.abort()
            old.deleteLater()
        self.place_loader = TileLoader(
            self._places_source, parent=self,
            decode=places_decoder(label_languages(self._language)))
        self.place_loader.loaded.connect(
            lambda key, found, extra: self.view.add_places(key, found))
        self.view.reset_places(self._places_source.max_level)
        self.view.place_loader = self.place_loader

    def _update_overlay(self, keep=False):
        """Собрать наложение заново из действующих источников.

        Сверху отмеченные слои проекта в порядке карты QGIS, под ними
        векторная основа. keep=True - прежние картинки видны, пока их
        не заменят новые, так обновление после правки не мигает.
        """
        # Тайлы суперналожений - под картинками на поверхности.
        supers = getattr(self, "superoverlays", None)
        layers, min_levels = self._overlay_stack(
            self._maps_hidden(), list(getattr(self, "_ground_rasters", []))
            + (supers.rasters if supers is not None else []))
        if self.overlay is not None:
            self.overlay.abort()
            self.overlay.deleteLater()
            self.overlay = None
        time_range = self._layer_range()
        self._applied_time = range_key(time_range)
        if layers:
            self.overlay = LayerOverlay(layers, parent=self,
                                        min_levels=min_levels,
                                        time_range=time_range)
            self.overlay.loaded.connect(self.view.add_overlay)
        self.view.set_overlay(self.overlay,
                              keep=keep and self.overlay is not None)
        self._apply_map_compare()

    def _overlay_stack(self, hidden, grounds):
        """Слои наложения сверху вниз и наименьшие уровни слоёв. hidden -
        скрытые растры-карты, grounds - растры картинок на поверхности."""
        project = QgsProject.instance()
        # Исторические карты с годом - только последняя на момент шкалы.
        layers = [project.mapLayer(layer_id)
                  for layer_id in self._applied_layers or ()
                  if layer_id not in hidden]
        layers = [layer for layer in layers if layer is not None]
        groups = self._applied_groups or set()
        if not self.planet.earth:
            # Слои проекта и векторная основа - земные.
            layers, groups = [], set()
        # Наложение собирается и при создании окна, до строк «Слоёв».
        if self.planet.earth and getattr(self, "extras", {}).get("plates") \
                and self.plate_layer is not None:
            # Границы плит - над векторной основой.
            self.plate_layer.setOpacity(self._layer_opacity("plates"))
            layers.append(self.plate_layer)
        if self.planet.earth and getattr(self, "extras", {}).get("faults") \
                and getattr(self, "fault_layer", None) is not None:
            # Разломы - над границами плит.
            self.fault_layer.setOpacity(self._layer_opacity("faults"))
            layers.insert(len(layers) - 1 if layers and layers[-1]
                          is getattr(self, "plate_layer", None)
                          else len(layers), self.fault_layer)
        if self.planet.earth and getattr(self, "extras", {}).get("mining") \
                and getattr(self, "mining_layer", None) is not None:
            self.mining_layer.setOpacity(self._layer_opacity("mining"))
            layers.append(self.mining_layer)
        if self.planet.earth \
                and getattr(self, "rumsey_footprints", None) is not None:
            layers.append(self.rumsey_footprints)
        if self.planet.earth \
                and getattr(self, "extras", {}).get("infra_osm") \
                and getattr(self, "infra_lines", None) is not None:
            for layer in (self.infra_points, self.infra_lines):
                layer.setOpacity(self._layer_opacity("infra_osm"))
                layers.append(layer)
        if self.planet.earth and getattr(self, "extras", {}).get("cables") \
                and getattr(self, "cable_layer", None) is not None:
            self.cable_layer.setOpacity(self._layer_opacity("cables"))
            layers.append(self.cable_layer)
        # Наложения тайлов - над векторной основой, под линиями выше.
        for key, layer in getattr(self, "tile_layers", {}).items():
            if self.planet.earth \
                    and getattr(self, "extras", {}).get(key):
                layer.setOpacity(self._layer_opacity(key))
                layers.append(layer)
        if groups & set(LINE_GROUPS) and self.ofm_layer is not None:
            layers.append(self.ofm_layer)
        min_levels = {}
        if RAILWAYS in groups and self.rail_layer is not None:
            layers.append(self.rail_layer)
            min_levels[self.rail_layer.id()] = RAIL_FROM
        # Картинки на поверхности - под всеми, сразу над снимком.
        layers += list(grounds)
        return layers, min_levels

    # Шторка исторических карт.

    def _map_compare_start(self):
        """Шторка карт: слева карта прошлого года карт, справа - карта
        момента шкалы. До первой карты слева нет ни одной карты."""
        moments = self._map_moments()
        if self._map_compare_at is None:
            moment = self._map_moment()
            if moment is None:
                moment = max(moments)
            before = oldmaps.step(moments, moment, -1)
            self._map_compare_at = before if before is not None \
                else min(moments) - oldmaps.YEAR
        self.view.swipe = self.swipe_bar.share
        self.view.swipe_maps = True
        self.swipe_bar.set_shown(True)
        self._map_compare_key = None
        self._apply_map_compare()

    def _map_compare_off(self):
        if self._map_compare_at is None \
                and self.map_compare_overlay is None:
            return
        self._map_compare_at = None
        self._map_compare_key = None
        self.view.swipe = None
        self.view.swipe_maps = False
        self.swipe_bar.set_shown(False)
        if self.map_compare_overlay is not None:
            self.map_compare_overlay.abort()
            self.map_compare_overlay.deleteLater()
            self.map_compare_overlay = None
        self.view.set_gibs("compare", False)
        self.compare_grounds.clear()

    def _map_compare_step(self, delta):
        """Шаг года левой части шторки карт."""
        moments = self._map_moments()
        if not moments:
            return
        at = oldmaps.step(moments, self._map_compare_at, delta)
        if at is None and delta < 0 \
                and self._map_compare_at >= min(moments):
            at = min(moments) - oldmaps.YEAR
        if at is not None:
            self._map_compare_at = at
            self._apply_map_compare()

    def _apply_map_compare(self):
        """Наложение левой части шторки карт: те же слои с картами на
        её момент. Собирается заново, только если сменился состав."""
        at = getattr(self, "_map_compare_at", None)
        if at is None:
            return
        entries = self._map_layer_entries()
        seen = oldmaps.shown(entries, at)
        hidden = frozenset(i for i, _, _ in entries if i not in seen)
        maps = oldmaps.shown(self._map_ground_entries(), at)
        grounds = []
        for item in self.myplaces.overlays:
            if item.kind != "ground" or not item.visible \
                    or item.body != self.planet.key \
                    or self.view.sky_view is not None:
                continue
            if oldmaps.start(item.time) is not None:
                if item.key not in maps:
                    continue
            elif not self._time_ok(item):
                continue
            token, overlay, data = self._overlay_edit(item)
            grounds.append((token, item.fid, item.name, overlay, data))
        rasters = self.compare_grounds.layers(grounds)
        key = (hidden, tuple(layer.id() for layer in rasters),
               tuple(self._applied_layers or ()),
               range_key(self._layer_range()))
        moment = self._map_moment()
        self.swipe_bar.set_days(
            oldmaps.year_label(at),
            oldmaps.year_label(moment) if moment is not None else "")
        if key == self._map_compare_key:
            return
        self._map_compare_key = key
        layers, min_levels = self._overlay_stack(hidden, rasters)
        old = self.map_compare_overlay
        if old is not None:
            old.abort()
            old.deleteLater()
        self.map_compare_overlay = LayerOverlay(
            layers, parent=self, min_levels=min_levels,
            time_range=self._layer_range())
        self.map_compare_overlay.loaded.connect(
            lambda key, levels, extra: self.view.add_gibs(
                "compare", key, levels if levels is not None
                else self._clear_levels()))
        self.view.gibs["compare"].max_level = basemap.MAX_LEVEL
        self.view.set_gibs("compare", True, self.map_compare_overlay,
                           keep=old is not None)

    def _clear_levels(self):
        """Мипмапы пустой картинки тайла - для пустого тайла наложения
        левой части шторки."""
        if getattr(self, "_clear_mips", None) is None:
            self._clear_mips = mip_chain(
                np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8))
        return self._clear_mips
    def _show_layers(self):
        self.panel.set_layers(map_layers(), self._shown)

    def set_layer_opacity(self, layer_id, opacity):
        """Прозрачность слоя QGIS из меню глобуса.

        Меняется сам слой, карта перерисуется. Глобус обновляется сразу,
        без кнопки «Обновить»: прозрачность двигают здесь и смотрят
        здесь же. Таймер собирает движения ползунка в одно обновление.
        """
        layer = QgsProject.instance().mapLayer(layer_id)
        if layer is None:
            return
        layer.setOpacity(opacity)
        layer.triggerRepaint()
        if layer_id in self.shown_layers():
            self._layers_stale = True
            self.refresh_timer.start(REFRESH_DELAY)

    def _project_changed(self):
        """Слои проекта изменились: обновить сразу или зажечь кнопку.

        Новый слой попадает на глобус, если так задано в свойствах вида.
        По умолчанию его отмечают в списке.
        """
        layers = map_layers()
        if self.tracks.settings:
            # Точки трека могли измениться.
            self.tracks.reload()
        added = [layer.id() for layer in layers
                 if layer.id() not in self._known]
        self._known = {layer.id() for layer in layers}
        if added and self.new_shown and not self.follow:
            self._shown |= set(added)
            write_shown(self._shown)
        # Перерисовка слоя меняет глобус, только если слой на нём:
        # в наложении или в подземной модели из слоёв проекта.
        if self._applied_layers or self.subsurface.from_project():
            self._layers_stale = True
        self._changed()

    def _legend_changed(self):
        """Видимость в дереве слоёв QGIS сменилась."""
        if not self.follow:
            return
        self._shown = {layer.id() for layer in map_layers()
                       if visible_on_map(layer)}
        self._changed()

    def set_follow(self, on):
        """Режим «как на карте QGIS»: видимость слоёв на глобусе - из
        дерева слоёв QGIS. Флажок хранится в проекте."""
        self.follow = bool(on)
        write_flag(FOLLOW, self.follow)
        if self.follow:
            self._legend_changed()
        else:
            write_shown(self._shown)
            self._changed()

    def set_new_shown(self, on):
        """Новые слои проекта сразу на глобус. Настройка QGIS."""
        self.new_shown = bool(on)
        QgsSettings().setValue(NEW_SHOWN_KEY, self.new_shown)
        self._sync_properties()

    def _selection_changed(self, layer_id):
        if layer_id in (self._applied_layers or ()):
            self._selection_timer.start(SELECTION_DELAY)

    def _selection_redraw(self):
        if self.overlay is not None:
            self._update_overlay(keep=True)

    def _project_reloaded(self):
        """Открыт другой проект: его настройки глобуса."""
        self.auto_refresh = read_flag(AUTO_REFRESH, AUTO_DEFAULT)
        self.toolbar.set_auto(self.auto_refresh)
        self._read_shown()
        self.tracks.visible = set(self._shown)
        self.tracks.load()
        self.subsurface.project_reloaded()
        self._load_insets()
        self._read_map_years()
        self.panel.grid_ids = set(read_grids())
        self.panel.zlayer_ids = set(read_zlayers())
        self.panel.ztrue_ids = set(read_ztrue())
        self._refresh_relief()

    def _mark_dirty(self, dirty):
        self.dirty = dirty
        self.toolbar.set_dirty(dirty)
        self._show_state()

    def _set_auto(self, on):
        self.auto_refresh = bool(on)
        write_flag(AUTO_REFRESH, on)
        self.toolbar.set_auto(self.auto_refresh)
        if on and self.dirty:
            self.refresh()

    def set_coords(self, fmt):
        """Формат координат строки состояния и окна «Объекты»."""
        if fmt not in COORD_FORMATS:
            return
        self.coords = fmt
        QgsSettings().setValue(COORDS_KEY, fmt)
        self._cursor_text = ""
        self._update_cursor()
        self._sync_properties()

    def _sync_properties(self):
        if self.properties is not None:
            self.properties.set_state(self.state())

    def _show_properties(self):
        if self.properties is None:
            self.properties = PropertiesDialog(
                self.sources, self.state(), self)
            self.properties.auto_changed.connect(self._set_auto)
            self.properties.basemap_chosen.connect(self.choose_basemap)
            self.properties.scale_changed.connect(self.set_relief_scale)
            self.properties.language_chosen.connect(self.set_label_language)
            self.properties.sync_chosen.connect(self.set_sync_direction)
            self.properties.follow_changed.connect(self.set_follow)
            self.properties.new_shown_changed.connect(self.set_new_shown)
            self.properties.coords_chosen.connect(self.set_coords)
            self.properties.ui_theme_chosen.connect(self.set_ui_theme)
            self.properties.sea_changed.connect(self.set_sea_depths)
            self.properties.assistant_requested.connect(self.open_assistant)
            self.properties.assistant_settings_requested.connect(
                lambda: self._assistant().open_settings())
            self.properties.history_clear_requested.connect(
                self.clear_search_history)
            self.properties.sources_requested.connect(self.open_sources)
            self.properties.subsurface_requested.connect(
                self.subsurface.open_dialog)
        self.properties.show()
        self.properties.raise_()
        self.properties.activateWindow()

    def open_sources(self):
        """Окно «Источники данных», одно на окно глобуса."""
        dialog = getattr(self, "sources_dialog", None)
        if dialog is None:
            dialog = self.sources_dialog = SourcesDialog(self, self)
            dialog.changed.connect(self.sources_changed)
        else:
            dialog.rebuild()
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
