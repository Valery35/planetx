# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Выбранное состояние окна: подложка, строки «Слоёв», раздел «На глобусе» с
непрозрачностью и выгрузкой.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import html
import datetime
import math
import os
import time

import numpy as np
from qgis.core import QgsProject, QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox
from qgis.utils import iface

from ... import journal
from ...core import (basemap, clouds, fields, geology, temperature,
                     flow as flow_core, quakes, themes, tilemaps)
from ...core.sync import ground_size, view_box, inside as in_box
from ..flow import CURRENTS_ATTRIBUTION
from ...i18n import is_russian, tr
from ...net.overlay import VECTOR_GROUPS, fetch_bytes
from ...qt_compat import enum
from ..tilesource import TileSourceDialog
from ..nasamaps import ANY_BODY, RELIEF_BODY, layer_names, map_names
from .. import export as layer_export
from ..weather import field_attribution, field_valid_text
from .base import (ACCEPTED_KEY, ACTIVE_ORDER, BASEMAP_KEY, EARTH_EXTRAS,
                   EXTRA_KEY, FLOW_LAYERS, GIBS_FADES, LANGUAGE_KEY, LINES_KEY,
                   OPACITY_KEY, PICTURE_LAYERS, POINT_LAYERS, QGIS_LAYERS,
                   READY_KEY, SURFACE_EXTRAS, SYNC_KEY, all_sources,
                   settings_list)


class StateMixin:
    """Часть окна глобуса GlobeWindow."""

    # Выбранное состояние. Его же меняют проверочные скрипты, на глобус
    # оно переходит по refresh.

    def basemap_index(self):
        return self._basemap

    def line_groups(self):
        """Включённые группы линий векторной основы."""
        return set(self._groups)

    def shown_layers(self):
        """Номера слоёв проекта, отмеченных в списке глобуса."""
        return set(self._shown)

    def relief_on(self):
        return self._relief

    def relief_scale(self):
        return self._scale

    def state(self):
        """Состояние для окна свойств."""
        return {"basemap": self._basemap, "groups": self._groups,
                "relief": self._relief, "scale": self._scale,
                "language": self._language, "sync": self.sync.direction,
                "follow": self.follow, "new_shown": self.new_shown,
                "auto": self.auto_refresh, "coords": self.coords,
                "sea": self.sea_depths}

    def set_sync_direction(self, way):
        """Кто за кем следует при синхронизации с картой."""
        self.sync.set_direction(way)
        QgsSettings().setValue(SYNC_KEY, way)

    def set_label_language(self, code):
        """Язык подписей, сразу, без кнопки «Обновить».

        Пункты разбираются из векторных тайлов заново, на новом языке.
        Тайлы берутся из кэша QGIS.
        """
        self._language = code
        QgsSettings().setValue(LANGUAGE_KEY, code)
        self._sync_properties()
        if self._places_source is not None:
            self._start_place_loader()

    def choose_basemap(self, index):
        self._basemap = index
        QgsSettings().setValue(BASEMAP_KEY, self.sources[index].name)
        self._fill_basemaps()
        self._changed()

    def _fill_basemaps(self):
        """Группа «Основа» панели: источники Земли или снимки тела."""
        if self.planet.earth:
            names = [tr("{name} - пример", name=s.name) if s.example
                     else s.name for s in self.sources]
            self.panel.set_basemaps(names, self._basemap)
        else:
            self.panel.set_basemaps([], 0, own=self.planet.imagery[0])

    def _panel_basemap(self, index):
        """Подложка выбрана в панели - сразу на глобус, как флажки
        раздела «Слои»."""
        self.choose_basemap(index)
        self._sync_properties()
        self.refresh()

    def add_tile_source(self):
        """Окно «Новый источник тайлов». Источник ложится подключением
        XYZ QGIS и сразу становится подложкой."""
        pose = self.view.navigator.pose
        dialog = TileSourceDialog(self, (pose.lat, pose.lon))
        if not dialog.exec():
            return
        self.sources = all_sources()
        names = [s.name for s in self.sources]
        index = names.index(dialog.saved_name) \
            if dialog.saved_name in names else self._basemap
        if self.properties is not None:
            # Список подложек окна свойств строится при открытии.
            self.properties.close()
            self.properties = None
        if iface is not None and hasattr(iface, "reloadConnections"):
            iface.reloadConnections()
        self._panel_basemap(index)

    def add_ready_source(self, key, ask=True):
        """Готовый источник меню «Основа» (basemap.READY) - подложкой.
        У источника с предупреждением окно сначала спрашивает согласие,
        принятое запоминается. ask=False - согласие уже получено
        (предложение помощника). Истина - подложка поставлена."""
        row = basemap.ready_entry(key)
        if row is None:
            return False
        source = basemap.ready_source(key, is_russian())
        accepted = settings_list(ACCEPTED_KEY)
        if row[7] and key not in accepted:
            if ask and not self._accept_terms(source.name, row[6]):
                return False
            QgsSettings().setValue(ACCEPTED_KEY, accepted + [key])
        chosen = settings_list(READY_KEY)
        if key not in chosen:
            QgsSettings().setValue(READY_KEY, chosen + [key])
        self.sources = all_sources()
        names = [s.name for s in self.sources]
        if self.properties is not None:
            self.properties.close()
            self.properties = None
        self._panel_basemap(names.index(source.name))
        return True

    def remove_ready_source(self, key):
        """Убрать готовый источник из списка подложек."""
        QgsSettings().setValue(READY_KEY, [
            k for k in settings_list(READY_KEY) if k != key])

    def _accept_terms(self, name, terms):
        """Окно предупреждения перед источником без разрешения на такой
        доступ. Истина - пользователь согласился."""
        box = QMessageBox(self)
        box.setIcon(enum(QMessageBox, "Icon", "Warning"))
        box.setWindowTitle(tr("Условия источника"))
        box.setTextFormat(enum(Qt, "TextFormat", "RichText"))
        box.setText(tr(
            "{name} - сервис, условия которого не разрешают брать его "
            "карты и снимки в сторонних программах по прямому адресу "
            "тайлов. Источник добавляется по вашему решению, "
            "ответственность за его использование несёте вы.<br><br>"
            "Условия сервиса: {terms}",
            name=html.escape(name),
            terms='<a href="{0}">{0}</a>'.format(html.escape(terms))))
        add = box.addButton(tr("Добавить"),
                            enum(QMessageBox, "ButtonRole", "AcceptRole"))
        box.addButton(enum(QMessageBox, "StandardButton", "Cancel"))
        box.exec()
        return box.clickedButton() is add

    def set_line_groups(self, groups):
        """Включить группы векторной основы, остальные выключить.

        Как в Google Earth, флажки панели «Слои» срабатывают сразу,
        без кнопки «Обновить». Решение автора от 27 сентября 2026 года.
        """
        self._groups = set(groups) & set(VECTOR_GROUPS)
        journal.note("line_groups {}".format(
            ",".join(sorted(self._groups)) or "-"))
        settings = QgsSettings()
        for group in VECTOR_GROUPS:
            settings.setValue(LINES_KEY.format(group), group in self._groups)
        self.panel.set_geo(self._groups, self._relief)
        self._apply_vector()

    def set_line_group(self, group, on):
        groups = set(self._groups)
        if on:
            groups.add(group)
        else:
            groups.discard(group)
        self.set_line_groups(groups)

    def set_extra(self, key, on):
        """Сетка, звёзды или облака флажком раздела «Слои», сразу."""
        if key in SURFACE_EXTRAS and on:
            # Уклон и экспозиция занимают один слой: вторая строка гаснет.
            other = SURFACE_EXTRAS[1 - SURFACE_EXTRAS.index(key)]
            self.extras[other] = False
            QgsSettings().setValue(EXTRA_KEY + other, False)
            self.panel.set_extras({other: False})
        self.extras[key] = bool(on)
        journal.note("set_extra {} {}".format(key, bool(on)))
        QgsSettings().setValue(EXTRA_KEY + key, bool(on))
        self.panel.set_extras({key: bool(on)})
        self._apply_extra(key, bool(on))
        # Слои неба, недр и рельефа включаются и в витрине.
        self._mark_gallery()

    def _apply_extra(self, key, on):
        if key in EARTH_EXTRAS and not self.planet.earth:
            # Облака, температура, здания и солнце - земные. Флажок
            # помнится и действует после возврата на Землю.
            on = False
        if key == "grid":
            self._grid_key = None
            self._update_grid()
        elif key == "stars":
            self.view.set_stars(on)
            if on:
                self._load_sky()
        elif key == "air":
            # Небо, гало и дымка над поверхностью, просьба автора от
            # 14 октября 2026 года. Без воздуха фон - чёрный космос.
            self.view.atmosphere = on
            self.view.update()
        elif key == "clouds":
            self._set_gibs("clouds", on)
        elif key == "temperature":
            if on and (self.theme_key or self.extras.get("fires")):
                self.set_theme("temperature")
            self._mark_gallery()
            self._set_gibs("sea", on)
            self._set_gibs("land", on)
            self.legend.setVisible(on)
            self._place_attribution()
        elif key == "buildings":
            self._set_buildings(on)
        elif key == "sun":
            self._update_sun()
            self._update_timebar()
        elif key in SURFACE_EXTRAS or key == "contours":
            self._set_surface()
        elif key == "quakes":
            self._set_quakes(on)
        elif key == "fires":
            self._set_fires(on)
        elif key == "deposits":
            self._set_deposits(on)
        elif key == "mining":
            self._set_mining(on)
        elif key == "osm_mines":
            self._set_osm_mines(on)
        elif key == "plants":
            self._set_plants(on)
        elif key == "volcanoes":
            self._set_volcanoes(on)
        elif key == "infra_osm":
            self._set_infra(on)
        elif key == "cables":
            self._set_cables(on)
        elif key == "currents":
            self._set_currents(on)
        elif key == "cadastre":
            self._set_gibs("cadastre", on and self.planet.earth, cache=True)
            if not on:
                self._drop_parcels()
        elif key == "cutaway":
            self._set_cutaway(on)
        elif key == "paleo":
            self._set_paleo(on)
        elif key == "plates":
            self._set_plates(on)
        elif key == "faults":
            self._set_faults(on)
        elif key == "geology":
            self._set_geology(on)
        elif key in tilemaps.MAPS:
            self._set_tilemap(key, on)
        elif key == "iscgem":
            self._set_history(on)
        elif key == "magpoles":
            self._set_poles(on)
        elif key == "magdecl":
            self._set_magdecl(on)
        elif key == "platemotion":
            self._set_platemotion(on)
        elif key in fields.FIELDS:
            self._set_field(key, on)
        elif key == "geoid":
            self._set_geoid(on)
        elif key == "satellites":
            self.satellite_manager.set_on(on)
            self._update_timebar()

    # Раздел «На глобусе»: включённые слои, непрозрачность, выгрузка.

    def _active_rows(self):
        """Строки раздела «На глобусе»: (ключ, название, непрозрачность
        или None, можно ли в проект QGIS)."""
        extras = getattr(self, "extras", {})
        planet = getattr(self, "planet", None)
        earth = planet is None or planet.earth
        names = layer_names()
        maps = map_names()
        rows = []
        parked = getattr(self, "_parked", {})
        for key in ACTIVE_ORDER:
            on = bool(extras.get(key))
            if not on and key not in parked:
                continue
            if not earth and key not in ANY_BODY + RELIEF_BODY + (
                    "contours", "grid"):
                continue
            title = (names.get(key) or maps.get(key) or (key,))[0]
            rows.append((key, title, self._row_opacity(key),
                         key in POINT_LAYERS or key in QGIS_LAYERS
                         or key in PICTURE_LAYERS or key == "geology"
                         or key in tilemaps.MAPS, on))
        theme = getattr(self, "theme_key", "") or parked.get("map", "")
        if theme and earth and theme in maps:
            rows.append(("map", maps[theme][0], self._row_opacity("map"),
                         True, bool(getattr(self, "theme_key", ""))))
        return rows

    def _row_opacity(self, key):
        if key in POINT_LAYERS or key in GIBS_FADES or key in QGIS_LAYERS \
                or key in FLOW_LAYERS:
            return self._layer_opacity(key)
        return None

    def _update_active(self):
        panel = getattr(self, "panel", None)
        if panel is not None and hasattr(panel, "set_active"):
            panel.set_active(self._active_rows())

    def _layer_opacity(self, key):
        return min(1.0, max(0.0, float(QgsSettings().value(
            OPACITY_KEY + key, 1.0, type=float))))

    def _active_off(self, key):
        """«Убрать с глобуса» строки «На глобусе»: слой выключен, строки
        больше нет."""
        self._parked.pop(key, None)
        if key == "map" or key in themes.EXCLUSIVE:
            self.set_theme("")
        else:
            self.set_extra(key, False)
        self._update_active()

    def _active_toggle(self, key, on):
        """Флажок строки «На глобусе»: слой выключен или включён снова,
        строка остаётся."""
        if on:
            theme = self._parked.pop(key, None)
            if key == "map":
                self.set_theme(theme or "")
            elif key in themes.EXCLUSIVE:
                self.set_theme(key)
            else:
                self.set_extra(key, True)
            return
        if key == "map":
            self._parked["map"] = self.theme_key
            self.set_theme("")
        elif key in themes.EXCLUSIVE:
            self._parked[key] = key
            self.set_theme("")
        else:
            self._parked[key] = key
            self.set_extra(key, False)

    def _active_opacity(self, key, value):
        QgsSettings().setValue(OPACITY_KEY + key, float(value))
        self._apply_layer_opacity(key)

    def _apply_layer_opacity(self, key):
        value = self._layer_opacity(key)
        if key in POINT_LAYERS:
            getattr(self.view, POINT_LAYERS[key]).opacity = value
        if key in FLOW_LAYERS:
            self.view.flows[FLOW_LAYERS[key]].opacity = value
        for name in GIBS_FADES.get(key, ()):
            self.view.gibs[name].fade = 1.0 - value
        if key in QGIS_LAYERS:
            for layer in self._qgis_layers(key):
                layer.setOpacity(value)
            if self.extras.get(key):
                self._opacity_overlay.start()
        self.view.update()

    def _qgis_layers(self, key):
        """Слои QGIS строки key, которые уже собраны."""
        found = {"plates": [getattr(self, "plate_layer", None)],
                 "faults": [getattr(self, "fault_layer", None)],
                 "mining": [getattr(self, "mining_layer", None)],
                 "infra_osm": [getattr(self, "infra_lines", None),
                               getattr(self, "infra_points", None)],
                 "cables": [getattr(self, "cable_layer", None)]}
        return [layer for layer in found.get(key, ()) if layer is not None]

    def active_export(self, key, path=None):
        """«В проект QGIS…» строки «На глобусе»: объекты слоя в рамке
        вида слоем GeoPackage в группу «PlanetX - слои глобуса». path -
        файл, без него - окно выбора."""
        title = (layer_names().get(key) or map_names().get(key)
                 or (key,))[0]
        if key == "map":
            title = map_names().get(self.theme_key, (title,))[0]
        if key == "geology" or key in tilemaps.MAPS:
            # Карты картинками - слоем тайлов или WMS, без файла.
            count = self._export_geology(title) if key == "geology" \
                else self._export_tilemap(key, title)
            self.message = (tr("В проект добавлен слой «{title}».",
                               title=title) if count else
                            tr("Слой «{title}» не добавлен.", title=title),
                            time.monotonic())
            self._show_state()
            return count
        if path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, tr("В проект QGIS"),
                os.path.join(QgsProject.instance().homePath()
                             or os.path.expanduser("~"), key + ".gpkg"),
                tr("GeoPackage (*.gpkg)"))
        if not path:
            return None
        pose = self.view.navigator.pose
        camera = self.view.camera
        width, height = ground_size(pose.distance, camera.fov_y,
                                    camera.aspect)
        box = view_box(pose.lat, pose.lon, width, height)
        if key in POINT_LAYERS:
            count = self._export_points(key, title, path, box)
        elif key in QGIS_LAYERS:
            count = self._export_qgis(key, title, path, box)
        else:
            count = self._export_picture(key, title, path, box)
            if count == "wait":
                return None
        if count is None:
            text = tr("Слой «{title}» не записан в «{path}».", title=title,
                      path=path)
        else:
            text = tr("В проект добавлено объектов {count}: {title}.",
                      count=count, title=title)
        self.message = (text, time.monotonic())
        self._show_state()
        return count

    def _export_points(self, key, title, path, box):
        layer = getattr(self.view, POINT_LAYERS[key])
        if not len(layer.focus):
            return 0
        keep = in_box(layer.lats, layer.lons, box)
        if key in ("quakes", "fires", "iscgem"):
            keep &= quakes.in_window(layer.times, layer.window)
        index = np.nonzero(keep)[0]
        fields, rows = self._point_rows(key, layer, index)
        count = layer_export.write_points(
            path, key, layer.lats[index], layer.lons[index],
            layer.colors[index] * 255.0, layer.sizes[index], fields, rows)
        if count is None or layer_export.add_points(path, key, title) is None:
            return None
        return count

    def _point_rows(self, key, layer, index):
        """Поля и значения точек index слоя вида key."""
        def stamp(seconds):
            if seconds is None or not math.isfinite(seconds):
                return ""
            # fromtimestamp на Windows не берёт время до 1970 года.
            epoch = datetime.datetime(1970, 1, 1,
                                      tzinfo=datetime.timezone.utc)
            return (epoch + datetime.timedelta(seconds=seconds)).strftime(
                "%Y-%m-%d %H:%M")
        if key in ("deposits", "osm_mines"):
            fields = [(name, "str") for name in (
                "name", "country", "commodities", "type", "status",
                "record", "operator", "capacity", "precision", "osm")]
            rows = [(layer.data.text(int(layer.order[n])) + [""] * 10)[:10]
                    for n in index]
        elif key == "plants":
            fields = [(name, "str") for name in (
                "name", "country", "fuel", "year", "owner",
                "source")] + [("capacity_mw", "real")]
            rows = [(layer.data.text(int(layer.order[n])) + [""] * 6)[:6]
                    + [float(layer.data.capacity[layer.order[n]])]
                    for n in index]
        elif key == "volcanoes":
            fields = [(name, "str") for name in (
                "number", "name", "type", "country", "setting",
                "evidence")] + [("elevation_m", "real"),
                                ("last_eruption", "real")]
            rows = [(layer.data.text(int(layer.order[n])) + [""] * 6)[:6]
                    + [float(layer.data.elevation[layer.order[n]]),
                       float(layer.data.last[layer.order[n]])]
                    for n in index]
        elif key in ("quakes", "iscgem"):
            fields = [("place", "str"), ("mag", "real"),
                      ("depth_km", "real"), ("time", "str"), ("url", "str")]
            rows = [(q.place, q.mag, q.depth, stamp(q.time), q.url)
                    for q in (layer.events[n] for n in index)]
        else:
            fires = layer.fires
            fields = [("frp_mw", "real"), ("time", "str"),
                      ("confidence", "str")]
            rows = [(float(fires.frp[n]), stamp(float(fires.time[n])),
                     fires.confidence[n]) for n in index]
        return fields, rows

    def _export_picture(self, key, title, path, box):
        """Раскраска вида в проект. Поля погоды и течения - числа сетки
        GeoTIFF со шкалой, темы NASA, облака и температура - картинка
        WMS GIBS по рамке вида на тот же день, ответ приходит позже
        («wait»)."""
        if key == "currents":
            grid = self.flow.fields["currents"]
            if grid is None:
                return None
            speed = np.hypot(grid.u, grid.v)
            count = layer_export.write_grid(
                path, [speed, grid.u, grid.v], grid.west, grid.north,
                grid.step, box)
            if count is None or layer_export.add_raster(
                    path, "{} {}".format(title, self.flow.currents_day),
                    flow_core.CURRENT_STOPS,
                    CURRENTS_ATTRIBUTION[0]) is None:
                return None
            return count
        if key == "map" and themes.is_weather(self.theme_key):
            shown = getattr(self, "_value_field", None)
            if shown is None:
                return None
            field, grid = shown
            bands = [grid.values]
            if grid.vectors is not None:
                bands += [grid.vectors.u, grid.vectors.v]
            count = layer_export.write_grid(path, bands, grid.west,
                                            grid.north, grid.step, box)
            stamp = field_valid_text(field, grid)
            if count is None or layer_export.add_raster(
                    path, "{} {}".format(title, stamp),
                    [(v, c) for v, c in field.ramp],
                    field_attribution(self.theme_key)[0]) is None:
                return None
            return count
        if key == "map":
            theme = themes.BY_KEY.get(self.theme_key)
            if theme is None:
                return None
            jobs = [(theme.layer, self.theme_day, path)]
        elif key == "clouds":
            jobs = [(clouds.LAYER, clouds.image_date(time.time()), path)]
        else:
            stem = os.path.splitext(path)[0]
            jobs = [(temperature.SEA, None, stem + "_sea.tif"),
                    (temperature.LAND, None, stem + "_land.tif")]
        self._picture_jobs = getattr(self, "_picture_jobs", [])
        for layer, day, out in jobs:
            url, _, _ = themes.wms_url(layer, box, day)
            name = "{} {}".format(title, str(day)[:10]) if day else title
            self._picture_jobs.append(fetch_bytes(
                url, lambda data, error, out=out, name=name, box=box:
                self._picture_done(data, error, out, name, box)))
        self.message = (tr("Загрузка картинки «{title}»…", title=title),
                        time.monotonic())
        self._show_state()
        return "wait"

    def _picture_done(self, data, error, path, name, box):
        ok = bool(data) and layer_export.write_picture(path, data, box) \
            and layer_export.add_raster(
                path, name, rights="NASA GIBS") is not None
        if not ok:
            journal.note("picture {}: {}".format(name, error or "unreadable"))
            text = tr("Слой «{title}» не записан в «{path}».", title=name,
                      path=path)
        else:
            text = tr("В проект добавлена картинка: {title}.", title=name)
        self.message = (text, time.monotonic())
        self._show_state()

    def _export_geology(self, title):
        """Геологическая карта Macrostrat в проект слоем тайлов XYZ, файл
        не пишется."""
        layer = layer_export.add_xyz(geology.TILES, title, geology.MAX_LEVEL,
                                     geology.ATTRIBUTION[0])
        return None if layer is None else 1

    def _export_tilemap(self, key, title):
        """Карта картинками (core/tilemaps.py) в проект слоем тайлов XYZ
        или WMS службы, файл не пишется."""
        tmap = tilemaps.MAPS[key]
        if tmap.wms:
            layer = layer_export.add_wms(tmap.wms[0], tmap.wms[1], title,
                                         tmap.attribution[0])
        else:
            layer = layer_export.add_xyz(self.tilemap_urls[key], title,
                                         tmap.max_level, tmap.attribution[0])
        return None if layer is None else 1

    def _export_qgis(self, key, title, path, box):
        if key == "plates":
            parts = [("plates", self.plate_layer, title)]
        elif key == "faults":
            parts = [("faults", self.fault_layer, title)]
        elif key == "mining":
            parts = [("mining", self.mining_layer, title)]
        elif key == "cables":
            parts = [("cables", self.cable_layer, title)]
        else:
            parts = [("lines", self.infra_lines, title),
                     ("substations", self.infra_points,
                      title + " - " + tr("подстанции"))]
        total = 0
        for n, (name, source, layer_title) in enumerate(parts):
            if source is None:
                return None
            count = layer_export.write_layer(path, name, source, box,
                                             first=n == 0)
            if count is None or layer_export.add_styled(
                    path, name, layer_title, source) is None:
                return None
            total += count
        return total

    def _clock_on(self):
        """Нужны ли часы глобуса: Солнце или спутники на Земле, вид
        неба. Тогда шкала времени открывается и без данных."""
        view = getattr(self, "view", None)
        if view is not None and view.sky_view is not None:
            return True
        extras = getattr(self, "extras", {})
        planet = getattr(self, "planet", None)
        earth = planet is None or planet.earth
        return earth and bool(extras.get("sun")
                              or extras.get("satellites"))

    def satellite_span(self):
        """Момент спутников, секунды UTC: правый бегунок открытой шкалы
        времени или None - часы компьютера."""
        span = getattr(self, "_time_range", None)
        if span is not None and math.isfinite(span[1]):
            return span[1]
        return None
