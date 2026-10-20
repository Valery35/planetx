# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Новая метка и действия меню на глобусе, окна у точки, полный экран.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import math
import os
import time

from qgis.core import QgsProject, QgsRasterLayer, QgsRectangle, QgsSettings
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QKeySequence
from qgis.PyQt.QtWidgets import QApplication

from ... import journal
from ...core import oldmaps, weather as weather_core
from ...core.flight import Spin
from ...core.geocode import (SEARCH_INTERVAL, link_zoom, parse_reverse,
                             reverse_url)
from ...core.sync import ground_size, view_box
from ...core.placetree import numbered_name
from ...core.places import Place as MarkPlace
from ...i18n import tr
from ...net.overlay import fetch_json
from ...qt_compat import QAction, enum
from ..themes import theme_names
from ..draw import PlaceDialog
from .. import globemenu
from ..project import (read_map_years, set_visible_on_map, write_map_years,
                       write_shown)
from ..sheets import SheetsDialog
from ..menulinks import MenuLinksDialog, open_link
from ..weather import (LEVEL as WEATHER_LEVEL, value_text, field_valid_text,
                       units_text as weather_units)
from .base import SIDEBAR_KEY


class ActionsMixin:
    """Часть окна глобуса GlobeWindow."""

    # Новая метка.

    def _place_open(self):
        return self.place_dialog is not None and self.place_dialog.isVisible()

    def _open_place(self, mode=None):
        """Окно «Новая метка». mode - вид объекта из меню значка
        (point, path, polygon, circle), без него - прежняя вкладка."""
        if self._ruler_open():
            self.ruler_dialog.close()
        if self.place_dialog is None:
            self.place_dialog = PlaceDialog(self.drawer, self._draw_name,
                                            self)
            self.place_dialog.save_requested.connect(self._save_place)
            self.place_dialog.style_changed.connect(self._refresh_shapes)
            self.place_dialog.finished.connect(self._place_closed)
        if mode:
            self.place_dialog.set_mode(mode)
        self.place_dialog.show()
        self.place_dialog.raise_()
        self.view.vertex_tool = self.draw_vertices
        self.handles.tool = self.draw_vertices
        self._refresh_shapes()
        self._tool_cursor()

    def _place_closed(self, *args):
        self.view.vertex_tool = self.wedge_corners \
            if self.view.wedge is not None else None
        self.drawer.clear()
        self._refresh_shapes()
        self._tool_cursor()
        self.handles.sync()

    def _save_place(self):
        shape = self.place_dialog.shape(rubber=False)
        if shape is None:
            return
        self.myplaces.add(shape, folder=self.panel.current_folder(),
                          body=self.body_key())
        self.place_dialog.name.clear()
        self.place_dialog.reset_name()
        self.drawer.clear()

    def new_name(self, base):
        """Название новой метки с номером, как «Моя метка 3»."""
        return numbered_name(base, [p.name for p in
                                    self.myplaces.places_in(None)])

    def _draw_name(self, mode):
        bases = {"point": tr("Моя метка"), "path": tr("Мой путь"),
                 "polygon": tr("Мой многоугольник"),
                 "circle": tr("Мой круг")}
        return self.new_name(bases[mode])

    def add_place_here(self, lat, lon):
        """«Добавить метку здесь» меню глобуса: окно «Новая метка»
        с точкой под курсором."""
        self._open_place()
        self.place_dialog.tabs.setCurrentIndex(0)
        self.drawer.clear()
        self.drawer.add(lat, lon)

    def route_point(self, lat, lon, name, end):
        """Начало (end=False) или конец маршрута из меню на глобусе."""
        if end:
            self.route_manager.set_target(lat, lon, name)
        else:
            self.route_manager.set_origin(lat, lon, name)

    def _route_done(self, key):
        """Маршрут лёг в «Мои метки»: перелёт к нему."""
        for place in self.myplaces.places:
            if place.key == key:
                self.fly_to_place(place)
                return

    def what_here(self, px, py):
        """«Что здесь?» меню на глобусе: окно «Объекты» и адрес места
        от Nominatim обратным запросом. Запрос - только по этому пункту
        и не чаще раза в SEARCH_INTERVAL, правила Nominatim."""
        self.identify_here(px, py)
        at = getattr(self, "_identify_at", None)
        if at is None or not self.planet.earth:
            return
        key = (round(at[0], 6), round(at[1], 6), self._search_language())
        self._address_key = key
        if key in self._addresses:
            self._show_identified()
            return
        self._address_timer.start(max(0, int(
            (SEARCH_INTERVAL - (time.monotonic() - self._search_at))
            * 1000)))
        self._show_identified()

    def _send_address(self):
        key = getattr(self, "_address_key", None)
        if key is None or key in self._addresses:
            return
        if self._search_reply is not None or \
                self._address_reply is not None:
            self._address_timer.start(int(SEARCH_INTERVAL * 1000))
            return
        self._search_at = time.monotonic()
        self._address_reply = fetch_json(
            reverse_url(*key),
            lambda data, error, key=key: self._address_done(key, data,
                                                            error))

    def _address_done(self, key, data, error):
        self._address_reply = None
        if data is None:
            self._addresses[key] = tr("не получен: {error}", error=error)
        else:
            self._addresses[key] = parse_reverse(data) or tr("нет")
        if key == getattr(self, "_address_key", None):
            self._show_identified()

    def _address_value(self, lat, lon):
        """Строка «Адрес» группы «Место» или None, если адрес не
        просили для этой точки."""
        key = getattr(self, "_address_key", None)
        if key is None or (round(lat, 6), round(lon, 6)) != key[:2]:
            return None
        return self._addresses.get(key, tr("загружается"))

    def measure_from(self, lat, lon):
        """«Измерить расстояние» меню на глобусе: линейка с первой
        точкой здесь."""
        self._open_ruler()
        self.ruler.clear()
        self.ruler.add(lat, lon)
        self._refresh_shapes()

    def _view_width(self):
        """Ширина видимой полосы в метрах - масштаб ссылок на место."""
        pose = self.view.navigator.pose
        return 2.0 * pose.distance * math.tan(
            math.radians(self.view.camera.fov_y) / 2.0)

    def open_menu_link(self, template, lat, lon):
        """Свой пункт меню на глобусе: адрес точки - браузеру."""
        open_link(template, lat, lon, link_zoom(lat, self._view_width()))

    def edit_menu_links(self):
        """Окно «Свои пункты меню»."""
        dialog = MenuLinksDialog(self)
        dialog.exec()
        return dialog

    def _show_weather_tiles(self, tiles, field, grid):
        """Поле прогноза на месте темы, шкала и подпись поля. Прежние
        картинки видны, пока их не заменят новые."""
        old = self.gibs_loaders.pop("theme", None)
        if old is not None:
            old.abort()
            old.deleteLater()
        self.gibs_loaders["theme"] = tiles
        self.view.gibs["theme"].max_level = WEATHER_LEVEL
        self.view.set_gibs("theme", True, tiles, keep=True)
        name = theme_names()[self.theme_key][0]
        units = weather_units(field)
        scale = dict(weather_core.legend(field), units=units)
        self.theme_legend.set_theme(tr(
            "{name}, {units} · {time} UTC", name=name, units=units,
            time=field_valid_text(field, grid)), scale)
        self.theme_legend.show()
        self._place_attribution()
        self._show_attribution()
        self._value_field = (field, grid)
        self._value_key = None
        self._update_values()
        self.flow.set_wind(grid.vectors)
        if getattr(self, "_theme_open_time", False) and self.timebar.known:
            # Выбранное поле открывает шкалу на нынешнем моменте.
            self._theme_open_time = False
            if not self.timebar.shown():
                self.timebar.open_bar()
                self.toolbar.set_time_shown(True)
            now = time.time()
            self.timebar.set_range(now, now)
            self._time_range = self.timebar.range()

    def _update_values(self):
        """Числа поля прогноза поверх раскраски, просьба автора от
        8 октября 2026 года. Узлы - core.weather.value_points, значения -
        из поля на глобусе, новых запросов в сеть нет. Строятся заново,
        только когда меняется шаг узлов или вид уходит на шаг."""
        shown = getattr(self, "_value_field", None)
        if shown is None or self.view.sky_view is not None:
            if self.view.value_marks:
                self.view.value_marks = []
                self._value_key = None
                self.view.update()
            return
        field, grid = shown
        pose = self.view.navigator.pose
        width = self._view_width()
        key = (id(grid),) + weather_core.value_key(pose.lat, pose.lon,
                                                   width)
        if key == self._value_key:
            return
        self._value_key = key
        self.view.value_marks = [
            MarkPlace(-500000 - n, value_text(field, value), "value", 1,
                      lat, lon)
            for n, (lat, lon, value) in enumerate(weather_core.value_marks(
                grid, field, pose.lat, pose.lon, width))]
        self.view.update()

    def _weather_changed(self):
        if self.weather.error:
            self.message = (self.weather.error, time.monotonic())
            self._show_state()

    def copy_sheet(self, number):
        """Номер листа из подменю «Номенклатура листа» в буфер обмена."""
        QApplication.clipboard().setText(number)
        self.message = (tr("Скопировано: {number}", number=number),
                        time.monotonic())
        self._show_state()

    def sheets_here(self, lat, lon):
        """«Номенклатура листа» меню на глобусе: номера листов карт
        в точке. Окно одно, новая точка заменяет прежнюю."""
        dialog = getattr(self, "sheets_dialog", None)
        if dialog is None:
            dialog = SheetsDialog(self, self.coords)
            self.sheets_dialog = dialog
        dialog.coords = self.coords
        dialog.show_point(lat, lon)
        dialog.show()
        dialog.raise_()
        return dialog

    def sentinel_here(self, lat, lon, mission=None):
        """«Космоснимки здесь…» меню на глобусе: сцены участка
        вокруг точки. Окно одно, новый участок заменяет прежний. mission -
        спутник окна, у пункта «Ранние снимки Landsat здесь…» - mss,
        у «Снимков ASTER здесь…» - aster."""
        dialog = self._sentinel_dialog()
        if mission:
            dialog.use_mission(mission)
        dialog.show_point(lat, lon, self._view_width())
        return dialog

    def etomesto_here(self, lat, lon):
        """«Старые карты «Это Место» здесь…» меню на глобусе: каталог
        карт сайта etomesto.com у точки. Окно одно, новая точка
        заменяет прежнюю."""
        from ..etomesto import EtomestoDialog
        dialog = getattr(self, "etomesto_dialog", None)
        if dialog is None:
            dialog = EtomestoDialog(self)
            self.etomesto_dialog = dialog
        dialog.show_point(lat, lon)
        dialog.show()
        dialog.raise_()
        return dialog

    def rumsey_here(self, lat, lon):
        """«Исторические карты Рамсея здесь…» меню на глобусе: карты коллекции
        у вида. Окно одно, новый вид заменяет прежний."""
        from ..rumsey import RumseyDialog
        dialog = getattr(self, "rumsey_dialog", None)
        if dialog is None:
            dialog = RumseyDialog(self)
            self.rumsey_dialog = dialog
        pose = self.view.navigator.pose
        camera = self.view.camera
        width, height = ground_size(pose.distance, camera.fov_y,
                                    camera.aspect)
        dialog.show_view(lat, lon, view_box(lat, lon, width, height, 1.0))
        dialog.show()
        dialog.raise_()
        return dialog

    def set_rumsey_footprints(self, boxes, selected):
        """Рамки карт окна «Карты Рамсея» на глобусе: слой в памяти
        в наложении, выбранная карта - отдельной яркой рамкой. Пустой
        список убирает рамки."""
        from qgis.core import (QgsFeature, QgsFillSymbol, QgsGeometry,
                               QgsRuleBasedRenderer, QgsVectorLayer)
        layer = None
        if boxes or selected is not None:
            layer = QgsVectorLayer("Polygon?crs=EPSG:4326&field=sel:integer",
                                   "PlanetX rumsey", "memory")
            features = []
            for n, box in enumerate(list(boxes) + (
                    [selected] if selected is not None else [])):
                feature = QgsFeature(layer.fields())
                feature.setGeometry(QgsGeometry.fromRect(QgsRectangle(
                    box[0], box[1], box[2], box[3])))
                feature.setAttributes([1 if n == len(boxes) else 0])
                features.append(feature)
            layer.dataProvider().addFeatures(features)
            plain = QgsFillSymbol.createSimple({
                "color": "0,0,0,0", "outline_color": "200,120,40,170",
                "outline_width": "1.2", "outline_width_unit": "Pixel"})
            bright = QgsFillSymbol.createSimple({
                "color": "255,200,60,40", "outline_color": "255,210,40,255",
                "outline_width": "3", "outline_width_unit": "Pixel"})
            root = QgsRuleBasedRenderer.Rule(None)
            root.appendChild(QgsRuleBasedRenderer.Rule(plain, 0, 0,
                                                       '"sel" = 0'))
            root.appendChild(QgsRuleBasedRenderer.Rule(bright, 0, 0,
                                                       '"sel" = 1'))
            layer.setRenderer(QgsRuleBasedRenderer(root))
        self.rumsey_footprints = layer
        self._update_overlay(keep=True)

    def _rumsey_shown(self):
        """Видна ли на глобусе карта Рамсея: слой из папки PlanetX/rumsey
        профиля среди показанных слоёв проекта."""
        project = QgsProject.instance()
        for layer_id in getattr(self, "_applied_layers", None) or ():
            layer = project.mapLayer(layer_id)
            if layer is not None and "rumsey" in os.path.normcase(
                    layer.source()).replace("\\", "/").split("/"):
                return True
        return False

    def add_rumsey_map(self, path, year, title):
        """Привязанная карта Рамсея слоем в группе «Карты Рамсея» вверху
        проекта, с годом карты, отмечена на глобусе. Тот же файл заново
        не добавляется."""
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        group_title = tr("Карты Рамсея")
        group = root.findGroup(group_title)
        if group is None:
            group = root.insertGroup(0, group_title)
        for node in group.findLayers():
            if os.path.normcase(node.layer().source()) == \
                    os.path.normcase(path):
                return node.layerId()
        name = "{} {}".format(year, title) if year is not None else title
        layer = QgsRasterLayer(path, name[:100], "gdal")
        if not layer.isValid():
            return None
        meta = layer.metadata()
        meta.setRights([tr("David Rumsey Map Collection, CC BY-NC-SA 3.0, "
                           "некоммерческое использование")])
        layer.setMetadata(meta)
        project.addMapLayer(layer, False)
        group.addLayer(layer)
        years = read_map_years()
        if year is not None:
            years[layer.id()] = year
        write_map_years(years)
        self._map_years = years
        self._shown.add(layer.id())
        if self.follow:
            set_visible_on_map(layer.id(), True)
        write_shown(self._shown)
        self._show_layers()
        self.refresh()
        if year is not None:
            self._show_time(oldmaps.year_time(year))
        return layer.id()

    def sentinel_place(self, place):
        """«Космоснимки…» меню метки: участок - метка."""
        dialog = self._sentinel_dialog()
        dialog.show_place(place, self._view_width())
        return dialog

    def _sentinel_dialog(self):
        from ..sentinel import SentinelDialog
        dialog = getattr(self, "sentinel_dialog", None)
        if dialog is None:
            dialog = SentinelDialog(self, self)
            self.sentinel_dialog = dialog
        dialog.show()
        dialog.raise_()
        return dialog

    def spin_here(self, lat, lon):
        """«Вращаться вокруг» меню на глобусе."""
        navigator = self.view.navigator
        navigator.start_flight(Spin(navigator.pose, lat, lon,
                                    fov_y=self.view.camera.fov_y),
                               time.monotonic())
        self.view.setFocus()
        self.view.update()

    def _globe_menu(self, px, py):
        """Щелчок правой кнопкой по глобусу без сдвига."""
        globemenu.show(self, px, py)

    def _window_key(self, keys, slot):
        """Клавиша окна - действие без пункта меню, как Ctrl+K."""
        action = QAction(self)
        action.setShortcut(QKeySequence(keys))
        action.setShortcutContext(
            enum(Qt, "ShortcutContext", "WindowShortcut"))
        action.triggered.connect(slot)
        self.addAction(action)
        return action

    def is_fullscreen(self):
        return self._windowed is not None

    def toggle_fullscreen(self):
        """Вид глобуса во весь экран для показа и обратно. Панели,
        панель значков и значок загрузки прячутся, органы навигации,
        шкала времени, тур, шкалы слоёв и подписи источников остаются.
        Выход возвращает прежнее окно и панели."""
        if self._windowed is None:
            self._windowed = {
                "maximized": self.isMaximized(),
                "geometry": self.saveGeometry(),
                "panel": self.panel.isVisible(),
                "sizes": self.splitter.sizes()}
            self.panel.hide()
            self.side.hide()
            self.toolbar.hide()
            self.spinner.hide()
            self._full_escape.setEnabled(True)
            self.showFullScreen()
            self.message = (tr("Во весь экран. Выход - Esc или F11."),
                            time.monotonic())
            self._show_state()
            journal.note("fullscreen on")
        else:
            state, self._windowed = self._windowed, None
            self._full_escape.setEnabled(False)
            self.showNormal()
            self.restoreGeometry(state["geometry"])
            if state["maximized"]:
                self.showMaximized()
            self.panel.setVisible(state["panel"])
            # Пустая панель свойств остаётся скрытой.
            self.side.setVisible(self.side.dialog is not None)
            self.splitter.setSizes(state["sizes"])
            self.toolbar.show()
            self.spinner.set_state(self.view.load_missing,
                                   self.view.load_stalled)
            journal.note("fullscreen off")
        self.view.setFocus()

    def set_sidebar(self, shown):
        """Показать или скрыть левую панель, вид занимает её место."""
        self.panel.setVisible(bool(shown))
        self.toolbar.set_sidebar(bool(shown))
        QgsSettings().setValue(SIDEBAR_KEY, bool(shown))
