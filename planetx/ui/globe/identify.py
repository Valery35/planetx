# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Определение объектов щелчком, участки кадастра, ИИ-помощник.

Часть окна глобуса GlobeWindow (ui/window.py)."""
import time

import numpy as np
from qgis.core import QgsProject, QgsRectangle, QgsVectorLayer
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QMessageBox
from qgis.utils import iface

from ... import journal
from ...core import (basemap, cadastre, when, assistant as assistant_core,
                     deposits as deposits_core, mining, pick, quakes)
from ...core.ellipsoid import ecef_to_geodetic
from ...core.features import Shape
from ...core.navigation import focal, ground_under
from ...core.planets import PLANETS
from ...core.skyview import ra_dec_of
from ...core.kml import KmlError, read_kml, write_kml
from ...i18n import tr
from ...net.overlay import VECTOR_GROUPS, fetch_bytes
from ...qt_compat import enum
from ..identify import Group, IdentifyDialog, identify, point_text
from ..assistant import (AssistantDialog, current_provider, ready,
                         search_enabled)
from .. import projectread
from ..legend import deposit_group_names, mine_kind_names
from ..manualcard import load_index
from ..myplaces import Place
from ..placecard import (Card, FeatureCard, PlaceCard, explain_question,
                         feature_question)
from ..tilesource import save_connection
from .base import (EXTRA_DEFAULTS, IDENTIFY_PIXELS, PARCEL_COLOR, PARCEL_FILL,
                   all_sources, distance_text, parcel_labels)

# Очагов у щелчка в окне «Объекты» не больше: каталог ISC-GEM даёт
# десятки событий в одной точке. Выбор помощника.
QUAKES_NEAR = 20


class IdentifyMixin:
    """Часть окна глобуса GlobeWindow."""

    # Определение объектов.

    def _set_identify(self, on):
        self.identifying = bool(on)
        self._tool_cursor()

    def _tool_cursor(self):
        """Перекрестие, пока щелчок по глобусу что-то ставит или ищет."""
        self.view.set_tool_cursor(self.identifying or self._ruler_open()
                                  or self._place_open())

    def _clicked(self, px, py):
        """Щелчок по глобусу: точка линейки или опрос объектов под ней."""
        tool = self.ruler if self._ruler_open() \
            else self.drawer if self._place_open() else None
        sky = self.view.sky_view
        if sky is not None:
            # На небе щелчок ставит точку новой метки: склонение
            # и прямое восхождение под курсором.
            if tool is self.drawer:
                cam = self.view.camera
                ra, dec = ra_dec_of(sky.direction_at(px, py, cam.width,
                                                     cam.height))
                tool.add(dec, ra - 360.0 if ra > 180.0 else ra)
            elif tool is None:
                # Щелчок по подписи объекта глубокого неба - карточка.
                number = self.sky_labels.object_at(px, py)
                if number is not None:
                    self.open_deep_card(number)
            return
        if tool is not None:
            if tool is self.ruler and tool.spatial():
                found = self._surface(px, py)
                if found is not None:
                    tool.add(*found)
                return
            found = self._ground(px, py)
            if found is not None:
                tool.add(found[0], found[1])
            return
        for area in self.areas:
            if area.taking():
                # Участок окна анализа рисуется - щелчок ставит вершину.
                found = self._ground(px, py)
                if found is not None:
                    area.add(found[0], found[1])
                return
        if self.class_tool.taking():
            # Окно «Классификация» открыто - щелчок ставит вершину участка
            # или точку класса, по точке класса - убирает её.
            found = self._ground(px, py)
            if found is not None:
                self.class_tool.click(px, py, found[0], found[1])
            return
        if not self.identifying:
            place = self._place_under(px, py)
            if place is not None:
                self.open_place_card(place)
                return
            found = self._article_under(px, py)
            if found is not None:
                self.open_article_card(*found)
                return
            if not self._point_under(px, py):
                found = self._feature_under(px, py)
                if found is not None:
                    self.open_feature_card(*found)
                return
        self.identify_here(px, py)

    def _click_point(self, px, py):
        """Точка поверхности под пикселем кадра и допуск опроса в метрах:
        (широта, долгота, допуск) или None."""
        camera = self.view.camera
        point = ground_under(camera, px, py,
                             self.view.navigator.pose.terrain)
        if point is None:
            return None
        lat, lon, _ = (float(v) for v in ecef_to_geodetic(point))
        metres = float(((point - camera.eye) ** 2).sum()) ** 0.5 \
            / focal(camera)
        return lat, lon, IDENTIFY_PIXELS * self.view.devicePixelRatioF() \
            * metres

    def _place_under(self, px, py):
        """Видимая метка «Моих меток» под пикселем кадра или None."""
        found = self._click_point(px, py)
        if found is None:
            return None
        places = self._places_at(*found)
        return places[0] if places else None

    def open_place_card(self, place):
        """Карточка метки в панели справа (ui/placecard.py). Окно
        свойств в панели главнее - щелчок мимо его вершин не должен
        отменять правку."""
        held = self.side.dialog
        if held is not None and not isinstance(held, Card):
            return
        card = PlaceCard(place, ready(current_provider()), self)
        card.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        card.explain.connect(self.explain_place)
        card.fly.connect(lambda key: self._card_place(key,
                                                      self.fly_to_place))
        card.properties.connect(lambda key: self._card_place(
            key, self._open_place_properties))
        self._place_card = card
        card.finished.connect(lambda *a, c=card: self._card_closed(c))
        self.side.host(card)

    def _card_place(self, key, action):
        place = self.myplaces.find(key)
        if isinstance(place, Place):
            action(place)

    def _card_closed(self, card):
        if getattr(self, "_place_card", None) is card:
            self._place_card = None

    def explain_place(self, key):
        """«Объясни это» карточки: вопрос о метке помощнику. Ответ -
        под строкой «Поиск» и в карточке."""
        place = self.myplaces.find(key)
        if not isinstance(place, Place):
            return
        kinds = {"point": tr("Метка"), "line": tr("Путь"),
                 "polygon": tr("Многоугольник")}
        question = explain_question(place, kinds.get(place.shape.kind,
                                                     tr("Метка")),
                                    self._explain_layers())
        card = getattr(self, "_place_card", None)
        if self._assistant().ask(question):
            self._explaining = card
            if card is not None:
                card.show_answer(tr("Помощник думает…"))
        elif card is not None:
            card.show_answer(tr("Помощник занят прежним вопросом или не "
                                "подключён."))

    def _feature_under(self, px, py):
        """Объект отмеченного векторного слоя проекта под пикселем кадра:
        (слой, название, поля, номер, широта, долгота) или None. Растры
        карточки не дают - их значения есть в режиме опроса."""
        if not self.planet.earth or self.view.sky_view is not None:
            return None
        found = self._click_point(px, py)
        if found is None:
            return None
        project = QgsProject.instance()
        layers = [project.mapLayer(i) for i in self._applied_layers or ()]
        layers = [layer for layer in layers
                  if isinstance(layer, QgsVectorLayer)]
        for layer, features in identify(layers, *found):
            title, values, fid = features[0]
            return layer, title, values, fid, found[0], found[1]
        return None

    def open_feature_card(self, layer, title, values, fid, lat, lon):
        """Карточка объекта слоя проекта в панели справа. Окно свойств
        в панели главнее, как у карточки метки."""
        held = self.side.dialog
        if held is not None and not isinstance(held, Card):
            return
        card = FeatureCard(layer.id(), fid, layer.name(), title, values,
                           (lat, lon), ready(current_provider()), self)
        card.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        card.explain.connect(lambda key, c=card: self.explain_feature(c))
        card.fly.connect(lambda key: self._fly_feature(*key))
        card.select.connect(lambda key: self._select_feature(*key))
        self._place_card = card
        card.finished.connect(lambda *a, c=card: self._card_closed(c))
        self.side.host(card)

    def _feature_of(self, layer_id, fid):
        layer = QgsProject.instance().mapLayer(layer_id)
        if not isinstance(layer, QgsVectorLayer):
            return None, None
        feature = layer.getFeature(fid)
        return layer, feature if feature.isValid() else None

    def _fly_feature(self, layer_id, fid):
        layer, feature = self._feature_of(layer_id, fid)
        if feature is not None and not feature.geometry().isEmpty():
            self._fly_extent(feature.geometry().boundingBox(), layer.crs())

    def _select_feature(self, layer_id, fid):
        layer, feature = self._feature_of(layer_id, fid)
        if feature is not None:
            layer.selectByIds([fid])

    def explain_feature(self, card):
        """«Объясни это» карточки объекта слоя проекта."""
        question = feature_question(card.layer_name, card.title,
                                    card.values, *card.point,
                                    layers=self._explain_layers())
        if self._assistant().ask(question):
            self._explaining = card
            card.show_answer(tr("Помощник думает…"))
        else:
            card.show_answer(tr("Помощник занят прежним вопросом или не "
                                "подключён."))

    def _point_under(self, px, py):
        """Есть ли под курсором точка месторождения, очага землетрясения,
        пожара или спутника. Щелчок по такой точке открывает окно
        «Объекты» и без режима опроса - замечание автора от 11 октября
        2026 года «клик по точкам ничего не даёт»."""
        return bool(self._identify_deposits(px, py)
                    or self._identify_deposits(px, py, osm=True)
                    or self._identify_plants(px, py)
                    or self._identify_volcanoes(px, py)
                    or self._infra_under(px, py)
                    or self._infra_under(px, py, faults=True)
                    or self._identify_quakes(px, py)
                    or self._identify_fires(px, py)
                    or self._identify_satellites(px, py)
                    or self._identify_trains(px, py)
                    or self._identify_live(px, py))

    def _infra_under(self, px, py, faults=False):
        """Линия или подстанция OSM под пикселем кадра, с faults -
        активный разлом."""
        if faults:
            if not (self.extras.get("faults") and self.planet.earth
                    and self.faults_data is not None):
                return []
        elif not (self.extras.get("infra_osm") and self.planet.earth
                  and self.infra_lines is not None):
            return []
        camera = self.view.camera
        point = ground_under(camera, px, py,
                             self.view.navigator.pose.terrain)
        if point is None:
            return []
        lat, lon, _ = (float(v) for v in ecef_to_geodetic(point))
        metres = float(((point - camera.eye) ** 2).sum()) ** 0.5 \
            / focal(camera)
        tolerance = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * metres
        if faults:
            return self._identify_faults(lat, lon, tolerance)
        return self._identify_infra(lat, lon, tolerance)

    def identify_here(self, px, py):
        """Опрос объектов под пикселем кадра: окно «Объекты». Его зовут
        щелчок в режиме «Определить объекты» и пункт «Получить сведения»
        меню на глобусе."""
        view = self.view
        camera = view.camera
        point = ground_under(camera, px, py, view.navigator.pose.terrain)
        if point is None:
            # Спутник на фоне неба опрашивается и без поверхности.
            found = self._identify_satellites(px, py)
            if found:
                self._identify_at = None
                if self.identified is None:
                    self.identified = IdentifyDialog(self)
                self.identified.show_result(found[0][1][0][0], found)
            return
        lat, lon, h = (float(v) for v in ecef_to_geodetic(point))
        # Метров на пиксель кадра в точке щелчка.
        metres = float(((point - camera.eye) ** 2).sum()) ** 0.5 \
            / focal(camera)
        tolerance = IDENTIFY_PIXELS * view.devicePixelRatioF() * metres
        project = QgsProject.instance()
        layers = [project.mapLayer(i) for i in self._applied_layers or ()]
        found = identify([layer for layer in layers if layer is not None],
                         lat, lon, tolerance)
        scale = view.store.scale
        height = h / scale if scale else None
        self._mark("{:.5f}, {:.5f}".format(lat, lon), lat, lon)
        self._identify_at = (lat, lon, height, tolerance, px, py, found)
        # Точка облака под курсором - один раз на щелчок, окно
        # уточняется по приходу других сведений без нового запроса.
        self._cloud_hits = self.pointclouds.identify(
            camera, px, py, IDENTIFY_PIXELS * view.devicePixelRatioF())
        self._ask_parcels(lat, lon)
        self._ask_field(lat, lon)
        self._ask_geology(lat, lon)
        self._ask_tilemap(lat, lon)
        self._ask_wayback(lat, lon)
        self._show_identified()

    # Сведения об участках кадастра Росреестра (core/cadastre.py).

    def _ask_parcels(self, lat, lon):
        """Запрос сведений об участках под щелчком, когда показан
        кадастр. Один запрос на щелчок, прежний снимается."""
        self._drop_parcels()
        if not (self.extras.get("cadastre") and self.planet.earth):
            return
        point = (lat, lon)
        self._parcels = (point, None, "")
        self._parcel_reply = fetch_bytes(
            cadastre.info_url(lat, lon),
            lambda data, error: self._parcels_arrived(point, data, error),
            fresh=True, headers={"Referer": cadastre.REFERER})

    def _drop_parcels(self):
        """Снять запрос, сведения и подсветку участков."""
        reply = getattr(self, "_parcel_reply", None)
        self._parcel_reply = None
        self._parcels = None
        if reply is not None:
            reply.abort()
        if getattr(self, "parcel_shapes", None):
            self.parcel_shapes = []
            self._refresh_shapes()

    def _parcels_arrived(self, point, data, error):
        state = getattr(self, "_parcels", None)
        if state is None or state[0] != point:
            return  # ответ снятого или прежнего запроса
        self._parcel_reply = None
        parcels = None
        if data is not None:
            try:
                parcels = cadastre.parse_info(data)
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        self._parcels = (point, parcels, error or "")
        self.parcel_shapes = [
            Shape("polygon", ring, color=PARCEL_COLOR, width=3.0,
                  fill=PARCEL_FILL)
            for parcel in parcels or () for ring in parcel["rings"]]
        self._refresh_shapes()
        self._refresh_identified()

    def _identify_parcels(self):
        """Группа «Кадастр Росреестра» окна «Объекты»."""
        state = getattr(self, "_parcels", None)
        if state is None:
            return []
        (lat, lon), parcels, error = state
        if parcels is None and not error:
            features = [(tr("Запрос к НСПД…"), [], None)]
        elif parcels is None:
            features = [(tr("НСПД не ответила"), [(tr("Ошибка"), error)],
                         None)]
        elif not parcels:
            features = [(tr("Участков под точкой нет"), [], None)]
        else:
            link = cadastre.map_link(lat, lon)
            labels = parcel_labels()
            features = [(tr("Земельный участок {number}",
                            number=p["number"]),
                         [(labels.get(key, key), value)
                          for key, value in p["values"]]
                         + [(tr("Карта НСПД"), link)], None)
                        for p in parcels]
        return [(Group(tr("Кадастр Росреестра")), features)]

    def _show_identified(self):
        """Окно «Объекты» по последнему щелчку: слои проекта, «Мои
        метки», очаги землетрясений, место. Зовётся и по приходу коры
        и плит, тогда место уточняется."""
        args = getattr(self, "_identify_at", None)
        if args is None:
            return
        lat, lon, height, tolerance, px, py, found = args
        groups = list(found)
        for name, values in getattr(self, "_cloud_hits", ()):
            groups.append((Group(tr("Облако точек «{name}»", name=name)),
                           [(tr("Точка облака"), values, None)]))
        groups += self._identify_parcels()
        groups += self._identify_places(lat, lon, tolerance)
        groups += self._identify_quakes(px, py)
        groups += self._identify_fires(px, py)
        groups += self._identify_deposits(px, py)
        groups += self._identify_deposits(px, py, osm=True)
        groups += self._identify_mining(lat, lon)
        groups += self._identify_plants(px, py)
        groups += self._identify_volcanoes(px, py)
        groups += self._identify_wiki(px, py)
        groups += self._identify_infra(lat, lon, tolerance)
        groups = self._identify_satellites(px, py) \
            + self._identify_trains(px, py) \
            + self._identify_live(px, py) + groups
        under = self.subsurface.identify(
            px, py, IDENTIFY_PIXELS * self.view.devicePixelRatioF())
        if under:
            groups.append((Group(tr("Подземное")), under))
        groups += self._identify_plates(lat, lon, tolerance)
        groups += self._identify_faults(lat, lon, tolerance)
        groups += self._identify_cables(lat, lon, tolerance)
        groups += self._identify_magnetic(lat, lon)
        groups += self._identify_field()
        groups += self._identify_geology()
        groups += self._identify_tilemap()
        groups += self._identify_wayback()
        groups += self._identify_site(lat, lon, height)
        if self.identified is None:
            self.identified = IdentifyDialog(self)
        # Высота геоида не высота места - строка точки её не пишет.
        self.identified.show_result(
            point_text(lat, lon, None if self._geoid_on() else height,
                       fmt=self.coords), groups)

    # ИИ-помощник: контекст вида и инструменты (core/assistant.py).

    def _assistant(self):
        """Окно «Помощник», одно на окно глобуса, создаётся скрытым."""
        if self.assistant_dialog is None:
            dialog = AssistantDialog(self.assistant_tool,
                                     self.assistant_context, self,
                                     describe=self._assistant_describe)
            dialog.said.connect(self._assistant_said)
            dialog.busy_changed.connect(self._assistant_busy)
            dialog.generated.connect(self._places_made)
            dialog.progress.connect(self._assistant_progress)
            self.assistant_dialog = dialog
        return self.assistant_dialog

    def open_assistant(self):
        """Окно «Помощник», немодальное."""
        dialog = self._assistant()
        dialog.show()
        dialog.raise_()

    def ask_assistant(self, text):
        """Просьба из строки поиска. Ложь, если пользователь это
        выключил, ключа API нет или прежний ответ ещё ждётся - тогда
        запрос идёт поиском места."""
        if not search_enabled() or not ready(current_provider()):
            return False
        return self._assistant().ask(text)

    def make_places(self, text):
        """Метки по описанию одним запросом к модели, кнопка у строки
        поиска. Документ KML сразу ложится папкой в «Мои метки»
        (_places_made), нажатие кнопки - согласие на запись."""
        if not text.strip():
            self.message = (tr("Опишите в строке «Поиск», какие метки "
                               "создать."), time.monotonic())
            self._show_state()
            return False
        self.panel.set_answer("")
        return self._assistant().generate(text)

    def _places_made(self, kml):
        """Документ модели - в «Мои метки» новой папкой, камера к ней."""
        dialog = self.assistant_dialog
        try:
            tree = read_kml(str(kml).encode("utf-8"), tr("Помощник"))
        except KmlError as error:
            dialog.say_note(tr("KML модели не разобран: {error}",
                           error=str(error)))
            return
        count = len(tree.places())
        if not count:
            dialog.say_note(tr("В документе KML нет меток."))
            return
        key = self.myplaces.import_tree(tree, body=self.body_key())
        self.assistant_folder = key
        self.made_folder = key
        self.panel.select_place(key)
        folder = self.myplaces.find(key)
        if folder is not None:
            self.fly_to_folder(folder)
        self._show_made_time(key)
        dialog.say_note(tr("В «Мои метки» записано меток: {count}.",
                       count=count))
        timed = sum(1 for p in tree.places() if p.time)
        answer = tr("Создана папка «{name}», меток {count}, со временем "
                    "{timed}.", name=tree.name or tr("Помощник"),
                    count=count, timed=timed)
        if dialog.partial:
            # Документ неполон: остановка, обрыв или предел длины.
            answer += " " + dialog.partial
        self.panel.set_answer(answer, undo=True)

    def _show_made_time(self, key):
        """Шкала времени на даты созданных меток: открывается, если
        у меток папки есть время, промежуток - от первой до последней
        даты. Просьба автора от 4 октября 2026 года."""
        extent = when.extent([p.time for p in self.myplaces.places_in(key)])
        if extent is None or not self.timebar.known:
            return
        if not self.timebar.shown():
            self.timebar.open_bar()
            self.toolbar.set_time_shown(True)
        self.timebar.set_range(*extent)

    def undo_made_places(self):
        """Ссылка «Отменить» под строкой поиска: созданная папка
        удаляется из «Моих меток»."""
        key = getattr(self, "made_folder", None)
        self.made_folder = None
        if key is None or self.myplaces.find(key) is None:
            self.panel.set_answer("")
            return
        self.myplaces.remove(key)
        self.panel.set_answer(tr("Созданные метки удалены."))

    def _assistant_said(self, who, text):
        """Реплики разговора под строкой поиска. Вопрос пользователя
        там не повторяется, он уже в строке."""
        # Документ, который предложила модель, ждёт подтверждения. Он
        # виден под строкой со ссылкой «Записать». 4 октября 2026 года
        # предложение стояло в скрытом окне «Помощник», под строкой был
        # только рассказ модели о документе, меток на глобусе не было.
        dialog = self.assistant_dialog
        waiting = dialog is not None and dialog.pending is not None
        card = getattr(self, "_explaining", None)
        if card is not None and who in ("assistant", "note"):
            # Ответ на «Объясни это» - и в карточку метки, если она ещё
            # открыта.
            self._explaining = None
            if card is getattr(self, "_place_card", None):
                card.show_answer(text)
        if waiting:
            text = dialog.proposal_text.text() + "\n" + text
        if who == "assistant" or who == "note":
            self.panel.set_answer(text, accept=waiting)
        elif who == "tool":
            self.panel.set_answer(tr("Помощник думает…") + "\n" + text,
                                  accept=waiting)

    def accept_proposed(self):
        """Ссылка «Записать в «Мои метки»» под строкой поиска."""
        if self.assistant_dialog is not None \
                and self.assistant_dialog.pending is not None:
            self.assistant_dialog._accept_place()

    def _assistant_busy(self, busy):
        self._set_busy("assistant", busy)
        if busy and not self.panel.answer.isVisible():
            self.panel.set_answer(tr("Помощник думает…"),
                                  stop=self._assistant().stream is not None)

    def _assistant_progress(self, count):
        """Метки идут потоком: счёт пришедших и ссылка «Остановить»."""
        self.panel.set_answer(
            tr("Помощник создаёт метки, получено {count}.", count=count),
            stop=True)

    def stop_making(self):
        """Ссылка «Остановить»: поток ответа обрывается, пришедшие
        целиком метки записываются."""
        if self.assistant_dialog is not None:
            self.assistant_dialog.stop_generation()

    def _layer_keys(self):
        """Ключи строк раздела «Слои», которые может включать помощник."""
        return ["relief"] + list(EXTRA_DEFAULTS) + list(VECTOR_GROUPS)

    def assistant_context(self):
        """Что уходит в модель с запросом: точка взгляда, тело,
        включённые строки, сектор разреза. Названия слоёв проекта
        и меток с запросом не уходят, решение автора от 3 октября 2026
        года. Слои проекта модель читает инструментами по разрешению
        пользователя, решение автора от 25 октября 2026 года."""
        pose = self.view.navigator.pose
        on = (["relief"] if self._relief else []) \
            + [k for k, v in self.extras.items() if v] \
            + sorted(self._groups)
        wedge = self.view.wedge
        return {
            "view": {"lat": round(pose.lat, 4), "lon": round(pose.lon, 4),
                     "distance_km": round(pose.distance / 1000.0, 1),
                     "heading": round(pose.heading, 1),
                     "tilt": round(pose.tilt, 1)},
            "body": "sky" if self.view.sky_view is not None
            else self.planet.key,
            "body_keys": ["sky"] + [p.key for p in PLANETS],
            "layers_on": on, "layer_keys": self._layer_keys(),
            "cutaway": [round(v, 2) for v in wedge] if wedge else None,
            "selected_places": len(self.panel.list.selected_keys()),
            "utc": when.text(time.time())}

    def assistant_tool(self, call):
        """Исполнить вызов инструмента модели, ответ - текст для модели.
        Ошибка в аргументах - тоже ответ, модель может исправиться."""
        handler = getattr(self, "_tool_" + call.name, None)
        if handler is None:
            return tr("Нет такого инструмента: {name}.", name=call.name)
        try:
            return handler(**call.args)
        except (TypeError, ValueError, KeyError, IndexError) as error:
            return tr("Ошибка в аргументах {name}: {error}",
                      name=call.name, error=str(error))

    def _tool_fly_to(self, lat, lon, distance_km=500.0):
        self._fly_to(float(lat), float(lon), float(distance_km) * 1000.0)
        return tr("Перелёт к {lat:.3f}, {lon:.3f}.", lat=float(lat),
                  lon=float(lon))

    def _tool_search_place(self, query):
        self.place.setText(str(query))
        # Поиск помощника не возвращается к помощнику, иначе запрос
        # без найденного места пошёл бы по кругу.
        self.fly(str(query), assistant=False)
        return tr("Поиск запущен: {query}.", query=query)

    def _tool_set_body(self, body):
        if body != "sky" and body not in [p.key for p in PLANETS]:
            return tr("Неизвестное тело: {body}.", body=body)
        self.set_body(body)
        return tr("Тело: {body}.", body=body)

    def _tool_set_layer(self, key, on):
        on = bool(on)
        if key == "relief":
            self.set_relief(on)
        elif key in EXTRA_DEFAULTS:
            self.set_extra(key, on)
        elif key in VECTOR_GROUPS:
            self.set_line_group(key, on)
        else:
            return tr("Неизвестная строка: {key}.", key=key)
        return tr("Строка {key}: {state}.", key=key,
                  state=tr("включена") if on else tr("выключена"))

    def _tool_list_actions(self):
        return assistant_core.actions_text(
            assistant_core.assistant_actions(self._search_actions()))

    def _tool_run_action(self, key):
        """Действие строки «Поиск» по ключу. Список строится заново:
        после прежнего действия состав и состояния могли смениться."""
        allowed = assistant_core.assistant_actions(self._search_actions())
        found = [a for a in allowed if a.key == str(key)]
        if not found:
            return tr("Нет такого действия: {key}. Ключ берётся из "
                      "list_actions.", key=key)
        item = found[0]
        journal.note("assistant action {}".format(item.key))
        self._actions[item.key]()
        return tr("Выполнено: {title} - {note}.", title=item.text,
                  note=item.note)

    def _assistant_describe(self, call):
        """Вопрос о разрешении вызова для окна «Помощник»."""
        return projectread.describe(call, self._search_actions())

    def _tool_search_docs(self, query):
        return assistant_core.search_docs_text(load_index(), str(query))

    def _tool_read_doc(self, anchor, offset=0,
                       limit=assistant_core.DOC_LINES):
        return assistant_core.read_doc_text(load_index(), anchor, offset,
                                            limit)

    def _tool_list_project_layers(self):
        journal.note("assistant reads project layers")
        return projectread.layers_text()

    def _tool_read_features(self, layer, where="", fields=None, limit=50,
                            geometry=False):
        journal.note("assistant reads features")
        return projectread.features_text(projectread.find_layer(layer),
                                         where, fields, limit,
                                         bool(geometry))

    def _tool_set_opacity(self, key, value):
        key = str(key)
        value = min(1.0, max(0.0, float(value)))
        rows = dict((row[0], row[2]) for row in self._active_rows())
        if key not in rows:
            return tr("Слоя {key} нет среди включённых.", key=key)
        if rows[key] is None:
            return tr("У слоя {key} непрозрачность не меняется.", key=key)
        self._active_opacity(key, value)
        self._update_active()
        return tr("Непрозрачность {key}: {value:.2f}.", key=key,
                  value=value)

    def _tool_set_time(self, start="", end=""):
        if not start and not end:
            self.toolbar.set_time_shown(False)
            self._time_toggled(False)
            return tr("Шкала времени закрыта.")
        if not self.timebar.known:
            return tr("Шкалы времени нет: у видимых меток и событий нет "
                      "времени.")
        lo = when.parse(start) if start else float("-inf")
        hi = when.parse(end) if end else float("inf")
        if lo is None or hi is None:
            return tr("Даты не разобраны: {start} - {end}.", start=start,
                      end=end)
        self.toolbar.set_time_shown(True)
        self._time_toggled(True)
        self.timebar.set_range(lo, hi)
        return tr("Шкала времени: {start} - {end}.", start=start, end=end)

    def _tool_earth_cutaway(self, west=None, east=None, south=0.0,
                            north=90.0, off=False):
        if off:
            self.set_extra("cutaway", False)
            return tr("Разрез Земли убран.")
        if not self.planet.earth:
            return tr("Разрез Земли есть только у Земли.")
        if not self.extras.get("cutaway"):
            self.set_extra("cutaway", True)
        if west is not None and east is not None:
            self.set_wedge_box(west, east, south, north)
        wedge = self.view.wedge
        return tr("Сектор: {wedge}.", wedge=", ".join(
            "{:.1f}".format(v) for v in wedge))

    def _tool_section_down(self, points, depth_km=700.0):
        pts = [(float(p[0]), float(p[1])) for p in points]
        if len(pts) < 2:
            return tr("Для разреза нужны хотя бы две точки.")
        self._open_section(tr("Разрез помощника"), pts)
        dialog = self.section_dialog
        best = min(range(dialog.depth_box.count()), key=lambda i: abs(
            dialog.depth_box.itemData(i) - float(depth_km)))
        dialog.depth_box.setCurrentIndex(best)
        found = dialog.chart.section
        if found is None:
            return tr("Разрез не построен.")
        return tr("Разрез открыт: длина {length:.0f} км, глубина "
                  "{depth:.0f} км, очагов в полосе {count}.",
                  length=float(found.distance[-1]), depth=found.depth,
                  count=len(found.quakes))

    def _tool_point_info(self, lat, lon):
        lat, lon = float(lat), float(lon)
        height = float(self._true_heights(np.array([lat]),
                                          np.array([lon]))[0])
        groups = self._identify_site(lat, lon, height)
        if not groups:
            return tr("Сведений о точке нет.")
        values = groups[0][1][0][1]
        return "; ".join("{}: {}".format(k, v) for k, v in values)

    def _tool_quakes_summary(self, south, north, west, east):
        if not self.quake_events:
            self._want_quakes()
            return tr("Сводка землетрясений загружается, повтори запрос "
                      "через несколько секунд.")
        return assistant_core.quakes_text(
            self.quake_events, (float(south), float(north), float(west),
                                float(east)))

    def _tool_add_basemap(self, ready="", url="", name=""):
        """Подложка от помощника. Готовый источник - через окно
        предупреждения, как из меню. Свой адрес пользователь
        подтверждает окном вопроса, потом он ложится подключением XYZ
        QGIS, как из окна «Новый источник тайлов»."""
        ready = str(ready or "").strip()
        if ready:
            if basemap.ready_entry(ready) is None:
                return tr("Нет готового источника {key}.", key=ready)
            if self.add_ready_source(ready):
                return tr("Подложка поставлена: {name}.",
                          name=self.source.name)
            return tr("Пользователь отказался от подложки.")
        url = str(url or "").strip()
        name = str(name or "").strip() or tr("Подложка помощника")
        if not basemap.valid_url(url) or not url.startswith(
                ("https://", "http://")):
            return tr("Адрес не годится: нужен шаблон http или https "
                      "с {z}, {x} и {y} или {q}.")
        answer = QMessageBox.question(
            self, tr("Подложка от помощника"),
            tr("Помощник предлагает подложку «{name}»:\n{url}\n\nУсловия "
               "использования сервиса проверяете вы. Добавить?",
               name=name, url=url))
        if answer != enum(QMessageBox, "StandardButton", "Yes"):
            return tr("Пользователь отказался от подложки.")
        taken = {s.name for s in self.sources}
        if name in taken:
            name = tr("{name} (PlanetX)", name=name)
        save_connection(name, url, basemap.DEFAULT_MAX, "")
        self.sources = all_sources()
        names = [s.name for s in self.sources]
        if iface is not None and hasattr(iface, "reloadConnections"):
            iface.reloadConnections()
        if name in names:
            self._panel_basemap(names.index(name))
        return tr("Подложка поставлена: {name}.", name=name)

    def _tool_add_kml(self, kml):
        # Модель оборачивает документ текстом, оградой Markdown, прологом
        # с чужой кодировкой - снимается так же, как у ответа текстом.
        kml = assistant_core.extract_kml(str(kml)) or str(kml)
        try:
            tree = read_kml(kml.encode("utf-8"), tr("Помощник"))
        except KmlError as error:
            return tr("KML не разобран: {error}. Исправь документ.",
                      error=str(error))
        count = len(tree.places())
        if not count:
            return tr("В документе KML нет меток.")

        def write():
            # Ключ новой папки - для перелёта и для проверки.
            self.assistant_folder = self.myplaces.import_tree(tree)
            self._show_made_time(self.assistant_folder)
            return tr("В «Мои метки» записано меток: {count}.",
                      count=count)
        self.assistant_dialog.propose(
            tr("Помощник предлагает папку «{name}», меток {count}.",
               name=tree.name or tr("Помощник"), count=count), write)
        return tr("Документ показан пользователю, меток {count}. Запись - "
                  "после его подтверждения.", count=count)

    def _tool_get_kml(self):
        pose = self.view.navigator.pose
        out = [assistant_core.look_at_kml(pose.lat, pose.lon, pose.distance,
                                          pose.heading, pose.tilt)]
        keys = self.panel.list.selected_keys()
        if keys:
            out.append(write_kml(self.myplaces.export_keys(keys)))
        else:
            out.append(tr("Выделенных меток нет."))
        return "\n".join(out)

    def _places_at(self, lat, lon, tolerance):
        """Видимые «Мои метки» под щелчком, ближние первыми."""
        places = [p for p in self.myplaces.places
                  if p.visible and self._time_ok(p) and not p.tour
                  and p.body == self.planet.key and p.shape.points
                  and p.key not in self._region_hidden]
        hits = pick.picked([(p.shape.kind, p.shape.points,
                             getattr(p.shape, "holes", None))
                            for p in places], lat, lon, tolerance)
        return [places[n] for n in hits]

    def _identify_places(self, lat, lon, tolerance):
        """Видимые «Мои метки» под щелчком."""
        hits = self._places_at(lat, lon, tolerance)
        kinds = {"point": tr("Метка"), "line": tr("Путь"),
                 "polygon": tr("Многоугольник")}
        features = []
        for p in hits:
            shape = p.shape
            values = [(tr("Тип"), kinds.get(shape.kind, shape.kind))]
            if shape.kind == "point":
                a, b = shape.points[0]
                values.append((tr("Координаты"), "{:.5f}, {:.5f}".format(
                    a, b)))
            elif shape.kind == "line":
                values.append((tr("Длина"), distance_text(
                    pick.path_length(shape.points))))
            else:
                values.append((tr("Периметр"), distance_text(
                    pick.path_length(shape.points, closed=True))))
            if p.measure:
                values.append((tr("Измерение"), p.measure))
            if p.description:
                values.append((tr("Описание"), p.description))
            values += list(getattr(p, "data", None) or ())
            features.append((shape.name or tr("Без названия"), values, None))
        return [(Group(tr("Мои метки")), features)] if features else []

    def _identify_quakes(self, px, py):
        """Очаги землетрясений у точки щелчка на экране - сводки USGS
        и исторические (ISC-GEM), по группе на слой."""
        out = []
        for layer, title in ((self.view.quakes, tr("Землетрясения")),
                             (self.view.history,
                              tr("Исторические землетрясения"))):
            out += self._quakes_near(layer, title, px, py)
        return out

    def _quakes_near(self, layer, title, px, py):
        """Очаги слоя layer у точки щелчка, не больше QUAKES_NEAR
        ближайших."""
        if not layer.events:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        shown = quakes.facing(eye, layer.epicenter, layer.lats, layer.lons) \
            & quakes.in_window(layer.times, layer.window)
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        best = np.full(len(layer.events), np.inf)
        for points in (layer.focus, layer.epicenter):
            pixels, front = self.view.camera.project(points)
            gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
            best = np.minimum(best, np.where(front, gap, np.inf))
        found = np.nonzero((best <= radius) & shown)[0]
        found = found[np.argsort(best[found])][:QUAKES_NEAR]
        features = []
        for n in found:
            q = layer.events[int(n)]
            values = [(tr("Магнитуда"), "{:.1f}".format(q.mag)),
                      (tr("Глубина очага"), tr("{value} км", value=(
                          "{:.0f}".format(q.depth))))]
            if q.time is not None:
                values.append((tr("Время, UTC"), when.text(q.time)))
            if q.url:
                values.append((tr("Страница USGS"), q.url))
            features.append((q.place or "M {:.1f}".format(q.mag), values,
                             None))
        return [(Group(title), features)] if features else []

    def _identify_satellites(self, px, py):
        """Спутник у точки щелчка на экране, группа окна «Объекты»."""
        found = self.satellite_manager.identify(px, py)
        features = [(name, values, None) for name, values in found]
        return [(Group(tr("Спутники")), features)] if features else []

    def _identify_trains(self, px, py):
        """Поезда у точки щелчка на экране, группа окна «Объекты»."""
        found = self.train_manager.identify(px, py)
        features = [(name, values, None) for name, values in found]
        return [(Group(tr("Поезда")), features)] if features else []

    def _identify_live(self, px, py):
        """Суда и самолёты у точки щелчка, группы окна «Объекты»."""
        out = []
        for title, manager in ((tr("Суда"), self.vessel_manager),
                               (tr("Самолёты"), self.aircraft_manager)):
            features = [(name, values, None)
                        for name, values in manager.identify(px, py)]
            if features:
                out.append((Group(title), features))
        return out

    def _identify_fires(self, px, py):
        """Очаги пожаров у точки щелчка на экране, не больше 20."""
        layer = self.view.fires
        data = layer.fires
        if data is None:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        shown = quakes.facing(eye, layer.focus, layer.lats, layer.lons) \
            & quakes.in_window(layer.times, layer.window)
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        pixels, front = self.view.camera.project(layer.focus)
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        near = np.nonzero(front & shown & (gap <= radius))[0]
        near = near[np.argsort(gap[near])][:20]
        features = []
        for n in near:
            n = int(n)
            values = [(tr("Мощность излучения"), tr(
                "{value} МВт", value="{:.1f}".format(data.frp[n])))]
            if not np.isnan(data.time[n]):
                values.append((tr("Время снимка, UTC"),
                               when.text(float(data.time[n]))))
            if data.confidence[n]:
                values.append((tr("Достоверность"), data.confidence[n]))
            values.append((tr("Снимок"), tr("ночной") if data.night[n]
                           else tr("дневной")))
            features.append(("{:.4f}, {:.4f}".format(data.lat[n],
                                                     data.lon[n]),
                             values, None))
        return [(Group(tr("Пожары")), features)] if features else []

    def _identify_deposits(self, px, py, osm=False):
        """Месторождения у точки щелчка на экране, не больше 20. osm -
        шахты и карьеры OpenStreetMap."""
        layer = self.view.osm_mines if osm else self.view.deposits
        data = layer.data
        if data is None:
            return []
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        seen = layer.visible(eye)
        if not len(seen):
            return []
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        pixels, front = self.view.camera.project(layer.focus[seen])
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        near = np.nonzero(front & (gap <= radius))[0]
        near = near[np.argsort(gap[near])][:20]
        names = deposit_group_names()
        keys = [g[0] for g in deposits_core.GROUPS] + ["other"]
        features = []
        for n in near:
            record = int(layer.order[seen[n]])
            name, country, commodities, kind, status, number, operator, \
                capacity, precision, osm_id = \
                (data.text(record) + [""] * 10)[:10]
            if osm:
                kind = mine_kind_names().get(kind, kind)
            values = [(tr("Полезные ископаемые"), commodities),
                      (tr("Группа"), names[keys[int(data.group[record])]])]
            if kind:
                values.append((tr("Тип"), kind))
            if status:
                values.append((tr("Стадия или модель"), status))
            if operator:
                values.append((tr("Оператор"), operator))
            if capacity:
                values.append((tr("Мощность (год сведений)"), capacity))
            if country:
                values.append((tr("Страна"), country))
            if precision == "A":
                values.append((tr("Место"), tr("примерное, по району")))
            source = "OpenStreetMap" if osm else tr(
                "Крупные месторождения мира, USGS OFR 2005-1294") \
                if data.major[record] else tr(
                    "Рудники и заводы мира, USGS mineral operations") \
                if data.facility[record] else "USGS MRDS"
            values.append((tr("Набор"), source))
            if osm_id:
                values.append((tr("Объект OpenStreetMap"),
                               mining.OSM_PAGE.format(*osm_id.split("/"))))
            if number:
                values.append((tr("Запись USGS"),
                               deposits_core.MRDS_PAGE.format(number)))
            features.append((name or "{:.4f}, {:.4f}".format(
                data.lat[record], data.lon[record]), values, None))
        title = tr("Шахты и карьеры OSM") if osm else tr("Месторождения")
        return [(Group(title), features)] if features else []

    def _identify_mining(self, lat, lon):
        """Контур горной разработки под точкой щелчка."""
        layer = self.mining_layer
        if layer is None or not self.extras.get("mining") \
                or not self.planet.earth:
            return []
        from qgis.core import QgsFeatureRequest, QgsGeometry, QgsPointXY
        point = QgsGeometry.fromPointXY(QgsPointXY(lon, lat))
        step = 0.0005
        request = QgsFeatureRequest().setFilterRect(QgsRectangle(
            lon - step, lat - step, lon + step, lat + step))
        features = []
        for feature in layer.getFeatures(request):
            if not feature.geometry().intersects(point):
                continue
            values = [(tr("Страна"), str(feature["COUNTRY_NAME"] or "")),
                      (tr("Площадь"), tr("{value} км²", value="{:.2f}".format(
                          float(feature["AREA"] or 0.0)))),
                      (tr("Набор"), "Maus et al. 2022, PANGAEA")]
            features.append((tr("Горная разработка"), values, None))
        return [(Group(tr("Горные разработки")), features)] \
            if features else []
