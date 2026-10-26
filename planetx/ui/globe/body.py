# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Тело глобуса и вид неба.

Часть окна глобуса GlobeWindow (ui/window.py)."""
from qgis.core import QgsSettings
from qgis.PyQt.QtCore import Qt

from ... import journal
from ...core import basemap, deepsky, ellipsoid
from ...core.navigation import Pose
from ...core.planets import planet_by_key
from ...core.skyview import SkyView
from ...net.overlay import label_kinds
from ...i18n import tr
from ...qt_compat import enum
from ...render.view import start_keys
from ..assistant import current_provider, ready
from ..placecard import Card, DeepSkyCard, deep_question
from ..project import FOLLOW, legend_shown, map_layers, read_flag, read_shown
from .base import (CONSTELLATIONS_KEY, DEEPSKY_KEY, EARTH_EXTRAS,
                   SKY_IMAGERY_KEY)


class BodyMixin:
    """Часть окна глобуса GlobeWindow."""

    # Тело глобуса.

    def set_body(self, key):
        self._set_body(key)
        self._update_polar()

    def _set_body(self, key):
        """Земля, Марс или Луна. Размеры тела, подложка, воздух,
        земные слои и вид - всё сразу. Камера встаёт над домашней
        точкой тела."""
        journal.note("set_body {}".format(key))
        if key == "sky":
            self.show_sky()
            return
        if self.view.sky_view is not None:
            self._leave_sky()
        planet = planet_by_key(key)
        self.toolbar.set_body(planet.key)
        if planet is self.planet:
            return
        self.planet = planet
        # Видимость, инсоляция и подземное считались по высотам
        # прежнего тела.
        self._clear_viewshed()
        self._clear_insolation()
        self.subsurface.clear()
        self.view.extruded.clear()
        # Разрез вниз - земной: кора, плиты и очаги есть только у Земли.
        if self.section_dialog is not None:
            self.section_dialog.close()
        ellipsoid.set_body(planet.body)
        if planet.earth:
            source = self._earth_source()
        else:
            name, url, top, text, link = planet.imagery
            # Снимки тел лежат в S3: отсутствующий тайл - ответ 403.
            source = basemap.Source(name, url, top, (text, link),
                                    builtin=True, missing=(403, 404))
        old = self.loader
        old.abort()
        old.deleteLater()
        self.errors.clear()
        self.source = source
        self._start_loader()
        self.view.change_body(source.max_level, planet.air)
        self.loader.want_many((key, -key[0]) for key in start_keys())
        # Вода над впадинами - только у Земли.
        self._geoid_look()
        self._body_terrain(planet)
        self.view.set_relief(self._relief_target())
        self._update_water()
        self.view.reset_places(self.source.max_level)
        self.view.label_kinds = label_kinds(self._groups) \
            if planet.earth else set()
        self._update_overlay()
        self._update_layer_labels(force=True)
        for extra in EARTH_EXTRAS:
            self._apply_extra(extra, self.extras.get(extra, False))
        self._show_theme()
        self._set_surface()
        if not planet.earth:
            # Отжатые кнопки сами выключают синхронизацию и опрос.
            self.toolbar.sync.setChecked(False)
            self.toolbar.identify.setChecked(False)
        self.toolbar.sync.setEnabled(planet.earth)
        self.toolbar.identify.setEnabled(planet.earth)
        self.panel.set_earth(planet.earth,
                             relief=planet.terrain is not None)
        self._mark_gallery()
        self._fill_basemaps()
        self._update_relief_menu()
        self._grid_key = None
        self._update_grid()
        self._refresh_shapes()
        lat, lon, distance = planet.home
        navigator = self.view.navigator
        navigator.stop()
        navigator.set_pose(Pose(lat, lon, distance, 0.0, 0.0))
        self._show_attribution()
        self.view.update()

    # Вид неба.

    def _globe_buttons(self):
        """Значки, которым нужна поверхность тела."""
        bar = self.toolbar
        return (bar.ruler_button, bar.sync, bar.identify)

    def body_key(self):
        """Ключ того, что на экране: тело глобуса или "sky"."""
        return "sky" if self.view.sky_view is not None else self.planet.key

    def sky_moment(self):
        """Момент светил неба: конец открытой шкалы времени, иначе
        None - часы компьютера."""
        return self.sun_time() if self.timebar.shown() else None

    def show_sky(self, ra=None, dec=None, fov=None):
        """Вид звёздного неба из центра небесной сферы. ra, dec, fov -
        взгляд в градусах, None - прежний взгляд или начальный."""
        view = self.view
        if view.sky_view is None:
            # Поза глобуса вернётся при выходе: в небе навигатор
            # ведёт взгляд на небо, core.skyview.pose_of.
            self._globe_pose = view.navigator.pose
            view.sky_view = self._sky_state or SkyView()
            for dialog in (self.ruler_dialog, self.place_dialog):
                if dialog is not None and dialog.isVisible():
                    dialog.close()
            view.navigator.stop()
        if ra is not None:
            view.sky_view.set(ra, dec, fov)
        view.sync_sky_pose()
        view.sky_time = self.sky_moment()
        self.toolbar.set_body("sky")
        self.navpad.hide()
        self.legend.hide()
        self.slope_legend.hide()
        self.insolation_legend.hide()
        self.quake_legend.hide()
        self.fire_legend.hide()
        self.deposit_legend.hide()
        self.cutaway_legend.hide()
        self.theme_legend.hide()
        self.paleo_bar.hide()
        self.view.plain_base = False
        for button in self._globe_buttons():
            button.setEnabled(False)
        self._show_attribution()
        self.sky_labels.sync()
        self._update_timebar()
        view.update()

    def set_constellations(self, on):
        """Линии и названия созвездий на небе."""
        self.view.show_constellations = bool(on)
        QgsSettings().setValue(CONSTELLATIONS_KEY, bool(on))
        self.toolbar.constellations.setChecked(bool(on))
        self.view.update()

    def set_deepsky(self, on):
        """Подписи объектов глубокого неба (core/deepsky.py)."""
        self.view.show_deepsky = bool(on)
        QgsSettings().setValue(DEEPSKY_KEY, bool(on))
        self.toolbar.deepsky.setChecked(bool(on))
        self.view.update()

    def open_deep_card(self, number):
        """Карточка объекта глубокого неба в панели справа. Окно свойств
        в панели главнее, как у карточки метки."""
        held = self.side.dialog
        if held is not None and not isinstance(held, Card):
            return
        obj = self.sky_labels.deep[number]
        card = DeepSkyCard(number, obj, self.sky_labels.language,
                           ready(current_provider()), self)
        card.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        card.explain.connect(self.explain_deep)
        card.fly.connect(self.fly_deep)
        self._place_card = card
        card.finished.connect(lambda *a, c=card: self._card_closed(c))
        self.side.host(card)

    def fly_deep(self, number):
        """Перелёт взгляда к объекту глубокого неба."""
        obj = self.sky_labels.deep[number]
        if self.view.sky_view is None:
            self.show_sky(obj.ra, obj.dec, deepsky.fov_for(obj))
        else:
            self.view.fly_sky(obj.ra, obj.dec, deepsky.fov_for(obj))

    def explain_deep(self, number):
        """«Объясни это» карточки объекта неба."""
        card = getattr(self, "_place_card", None)
        question = deep_question(self.sky_labels.deep[number],
                                 self.sky_labels.language)
        if self._assistant().ask(question):
            self._explaining = card
            if card is not None:
                card.show_answer(tr("Помощник думает…"))
        elif card is not None:
            card.show_answer(tr("Помощник занят прежним вопросом или не "
                                "подключён."))

    def set_sky_imagery(self, on):
        """Снимки неба при приближении (core.hips.LAYERS)."""
        self.sky_surveys.set_on(on)
        QgsSettings().setValue(SKY_IMAGERY_KEY, bool(on))
        self.toolbar.imagery.setChecked(bool(on))
        self._show_attribution()
        self.view.update()

    def _leave_sky(self):
        view = self.view
        self._sky_state = view.sky_view
        view.sky_view = None
        view.navigator.stop()
        if getattr(self, "_globe_pose", None) is not None:
            view.navigator.set_pose(self._globe_pose)
        self.navpad.show()
        for button in self._globe_buttons():
            button.setEnabled(True)
        self.toolbar.sync.setEnabled(self.planet.earth)
        self.toolbar.identify.setEnabled(self.planet.earth)
        self.legend.setVisible(bool(self.extras.get("temperature"))
                               and self.planet.earth)
        self.insolation_legend.setVisible(
            self.insolation_result is not None)
        self._quake_legend_state()
        self.fire_legend.setVisible(self.extras.get("fires", False)
                                    and self.planet.earth)
        self.deposit_legend.setVisible(self._deposit_legend_on())
        self.plant_legend.setVisible(bool(self.extras.get("plants"))
                                     and self.planet.earth)
        self.volcano_legend.setVisible(bool(self.extras.get("volcanoes"))
                                       and self.planet.earth)
        self.infra_legend.setVisible(bool(self.extras.get("infra_osm"))
                                     and self.planet.earth)
        self.fault_legend.setVisible(bool(self.extras.get("faults"))
                                     and self.planet.earth)
        self.cutaway_legend.setVisible(bool(self.extras.get("cutaway"))
                                       and self.planet.earth)
        self.paleo_bar.setVisible(self._paleo_on())
        self.view.plain_base = self._paleo_on()
        self._update_timebar()
        self._show_theme()
        self._set_surface()
        self.toolbar.set_body(self.planet.key)
        self._show_attribution()
        self.sky_labels.sync()
        view.update()

    def _read_shown(self):
        """Отметки слоёв из проекта.

        В проекте без записи не отмечен ни один слой, решение автора
        от 27 сентября 2026 года. Раньше отмечались слои, видимые на карте.
        """
        layers = map_layers()
        self.follow = read_flag(FOLLOW, False)
        if self.follow:
            self._shown = legend_shown(layers)
            self._known = {layer.id() for layer in layers}
            return
        shown = read_shown()
        self._shown = shown if shown is not None else set()
        self._known = {layer.id() for layer in layers}
