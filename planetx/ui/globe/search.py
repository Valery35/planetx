# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Загрузка, перелёты, поиск места и строка «Поиск».

Часть окна глобуса GlobeWindow (ui/window.py)."""
import time

from qgis.core import QgsSettings
from qgis.PyQt.QtCore import Qt

from ... import journal
from ...core.coords import parse_point
from ...core.flight import fit_view
from ...core.geocode import (SEARCH_INTERVAL, normalize, parse_places,
                             place_text, search_url)
from ...core import (assistant as assistant_core, deepsky, searchbar,
                     skydata)
from ...core.places import Place as MarkPlace
from ...core.searchbar import Suggestion
from ...i18n import tr, ui_language
from ...net.overlay import fetch_bytes, fetch_json
from ...qt_compat import enum
from .. import commands as commands_ui
from ..assistant import current_provider, ready, search_enabled
from ..manualcard import ManualCard, load_index
from ..placecard import Card
from .base import (CURSOR_PERIOD, FLIGHT_DISTANCE, HISTORY_KEY,
                   SEARCH_MAX_DISTANCE, SEARCH_MIN_DISTANCE, STATUS_PERIOD,
                   label_languages)


class SearchMixin:
    """Часть окна глобуса GlobeWindow."""

    # Загрузка.

    def _heights(self, key, rgba, tile):
        self.terrain_errors.pop(key, None)
        self.view.add_heights(tile)
        self._heights_arrived()

    def _loaded(self, key, rgba, prepared):
        self.errors.pop(key, None)
        mesh, levels, level, scale = prepared
        # Сетка, собранная до смены масштаба рельефа, пересобирается.
        if scale != self.view.store.scale:
            level = -1
        self.view.add_image(key, levels, mesh, level)
        # Пока уровни 0-2 не готовы, полных кадров нет и сигнала changed
        # тоже. Строка загрузки обновляется отсюда, с тем же ограничением.
        self._frame_done()

    def _failed(self, key, error):
        self.errors[key] = error
        self._show_state()

    def _frame_done(self):
        """После кадра строка обновляется не чаще STATUS_PERIOD.

        setText на каждом кадре перерисовывает строку и отнимает время
        у цикла событий. Замер 26 сентября 2026 года показал до 22 мс
        между кадром и следующим paintGL.
        """
        now = time.monotonic()
        # Под неподвижным курсором при движении камеры точка другая.
        if getattr(self, "_hover", None) is not None \
                and not self._cursor_timer.isActive():
            self._cursor_timer.start(CURSOR_PERIOD)
        if now - self._shown_at >= STATUS_PERIOD:
            self._shown_at = now
            self._show_state()

    # Перелёты.

    def fly(self, text=None, assistant=True):
        """Поиск из поля ввода: координаты - перелёт, точное название
        своей метки, на небе звезды или созвездия - перелёт к ним без
        запроса в сеть, просьба словами - помощнику, иначе Nominatim.
        assistant=False - поиск запустил сам помощник, к нему запрос
        не возвращается и в историю запросов не идёт."""
        text = self.place.text() if text is None else text
        if assistant:
            self._remember_search(text)
        target = parse_point(text)
        if target is not None:
            self.panel.set_found([])
            self._found = []
            self._mark(normalize(text), *target)
            distance = min(self.view.navigator.pose.distance,
                           FLIGHT_DISTANCE)
            self._fly_to(target[0], target[1], distance)
            return
        query = normalize(text)
        if not assistant:
            self._tool_queries.add(query)
        else:
            self._tool_queries.discard(query)
            self.panel.set_answer("")
        # Свои метки ищутся только по Enter пользователя. Поиск помощника
        # к ним не ведёт: точка взгляда уходит в модель, а места меток
        # в неё не идут, решение автора от 3 октября 2026 года.
        own = self._exact_match(text) if assistant else None
        if own is not None:
            self._fly_suggestion(own)
            return
        # Название действия целиком - «течения», «линейка» - выполняет
        # его, как подсказка (ui/commands.py).
        action = self._exact_action(text) if assistant else None
        if action is not None:
            self.run_action(action)
            return
        # Объект неба вне каталога ищет служба имён Sesame CDS.
        # Просьба словами по-прежнему уходит помощнику.
        if query and self.view.sky_view is not None \
                and not assistant_core.is_request(query):
            self._sky_search(query)
            return
        # Просьба словами уходит помощнику, название места - Nominatim.
        # Вне Земли Nominatim не работает, туда идёт любой запрос.
        if query and assistant and (assistant_core.is_request(query)
                                    or not self.planet.earth) \
                and self.ask_assistant(query):
            return
        if query and not self.planet.earth:
            # Поиск по названию - Nominatim, он знает только Землю.
            self.message = (tr("Поиск по названию есть только у Земли. "
                               "Координаты вводятся числами."),
                            time.monotonic())
            self._show_state()
            return
        if query:
            self._search(query)

    # Поиск места по названию. Правила Nominatim: запрос только по Enter,
    # не чаще раза в SEARCH_INTERVAL, ответы запоминаются до закрытия
    # окна, заголовок PlanetX ставит обработчик запросов загрузчика.

    def _search_language(self):
        languages = label_languages(self._language)
        return languages[0] if languages else None

    def _search(self, query):
        key = (query, self._search_language())
        if key in self._searched:
            self._show_found(key, self._searched[key])
            return
        self._search_key = key
        self.message = (tr("Поиск: {text}", text=query), time.monotonic())
        self._show_state()
        self._set_busy("search", True)
        wait = SEARCH_INTERVAL - (time.monotonic() - self._search_at)
        self._search_timer.start(max(0, int(wait * 1000)))

    def _send_search(self):
        if self._search_reply is not None:
            # Прежний запрос ещё идёт, новый ждёт его.
            self._search_timer.start(int(SEARCH_INTERVAL * 1000))
            return
        key = self._search_key
        self._search_at = time.monotonic()
        self._search_reply = fetch_json(
            search_url(*key),
            lambda data, error: self._search_done(key, data, error))

    def _sky_search(self, query):
        """Объект неба по имени через Sesame CDS, ответ - перелёт
        взгляда. Запрос один за раз, прежний снимается."""
        reply = getattr(self, "_sesame_reply", None)
        if reply is not None:
            reply.abort()
        self.message = (tr("Поиск на небе: {text}", text=query),
                        time.monotonic())
        self._show_state()
        self._set_busy("search", True)
        self._sesame_reply = fetch_bytes(
            deepsky.sesame_url(query),
            lambda data, error: self._sky_found(query, data, error))

    def _sky_found(self, query, data, error):
        self._sesame_reply = None
        self._set_busy("search", False)
        found = None
        if data is not None:
            found = deepsky.parse_sesame(bytes(data).decode("utf-8",
                                                            "replace"))
        if found is None:
            self.message = (tr("На небе не найдено: {text}", text=query)
                            if data is not None else
                            tr("Поиск не удался: {error}", error=error),
                            time.monotonic())
            self._show_state()
            return
        ra, dec, name = found
        self.message = (tr("Найдено: {name}", name=name or query),
                        time.monotonic())
        self._show_state()
        if self.view.sky_view is not None:
            self.view.fly_sky(ra, dec, deepsky.FOV_UNKNOWN)

    def _set_busy(self, reason, on):
        """Значок ожидания у строки «Поиск». reason - чего ждём,
        значок гаснет, когда не ждём ничего."""
        if on:
            self._busy.add(reason)
        else:
            self._busy.discard(reason)
        tip = tr("Помощник ждёт ответ модели.") \
            if "assistant" in self._busy else tr("Идёт поиск места.")
        self.panel.set_busy(bool(self._busy), tip if self._busy else "")

    def _search_done(self, key, data, error):
        self._search_reply = None
        # Следующий запрос может ждать своей очереди по таймеру.
        self._set_busy("search", self._search_timer.isActive())
        if data is None:
            self.message = (tr("Поиск не удался: {error}", error=error),
                            time.monotonic())
            self._show_state()
            return
        places = parse_places(data)
        self._searched[key] = places
        if key == self._search_key:
            self._show_found(key, places)

    def _show_found(self, key, places):
        """Перелёт к первому найденному месту, остальные - списком."""
        self._found = places
        self.panel.set_found([place_text(p) for p in places]
                             if len(places) > 1 else [])
        if not places:
            # Место не нашлось. Тема вроде «Путешествия Колумба» -
            # метки одним запросом, как кнопка помощника, вопрос -
            # разговор. В разговоре метки появляются, только если модель
            # вызовет add_kml. 4 октября 2026 года бесплатная модель
            # на «Путешествия Колумба» описала документ текстом, и меток
            # не было.
            if key[0] not in self._tool_queries:
                if not assistant_core.is_request(key[0]) \
                        and search_enabled() \
                        and ready(current_provider()) \
                        and self.make_places(key[0]):
                    return
                if self.ask_assistant(key[0]):
                    return
            self.message = (tr("Ничего не найдено: {text}", text=key[0]),
                            time.monotonic())
            if assistant_core.is_request(key[0]) and search_enabled() \
                    and not ready(current_provider()):
                self.message = (tr("Ключа API нет, просьба не отправлена. "
                                   "Ключ вводится в окне «Настройки "
                                   "помощника»."),
                                time.monotonic())
            self._show_state()
            return
        self.message = ("", 0.0)
        self._show_state()
        self._fly_place(places[0])
        # Тема вроде «Первая мировая война» находит места с этими словами
        # в названии. Рядом - ссылка на метки помощника по теме, просьба
        # автора от 4 октября 2026 года.
        if key[0] not in self._tool_queries and search_enabled() \
                and ready(current_provider()):
            self.panel.set_answer(tr("Найдены места с этим названием."),
                                  make=key[0])

    def fly_place(self, index):
        """Перелёт к месту из списка найденных."""
        if 0 <= index < len(self._found):
            self._fly_place(self._found[index])

    def clear_search(self):
        """Поле поиска очищено: списка и метки больше нет."""
        self._found = []
        self._search_key = None
        # Ждущий запрос Nominatim снимается: с пустым ключом
        # _send_search упал бы на search_url(*None).
        self._search_timer.stop()
        self._set_busy("search", False)
        self.view.set_search_mark(None)

    # Строка «Поиск»: подсказки при вводе, история запросов, точное
    # название своей метки или объекта неба (core/searchbar.py). Nominatim
    # при вводе не спрашивается, его правила запрещают автодополнение.

    def search_history(self):
        """Прежние запросы строки «Поиск» из профиля QGIS, от новых
        к старым."""
        saved = QgsSettings().value(HISTORY_KEY, []) or []
        # Список из одной строки настройки возвращают строкой.
        if isinstance(saved, str):
            saved = [saved]
        elif not isinstance(saved, (list, tuple)):
            saved = []
        return [str(text) for text in saved
                if str(text).strip()][:searchbar.HISTORY]

    def _remember_search(self, text):
        """Запрос по Enter встаёт в начало истории."""
        history = self.search_history()
        updated = searchbar.remember(history, text)
        if updated != history:
            QgsSettings().setValue(HISTORY_KEY, updated)

    def clear_search_history(self):
        """Пункт «Очистить историю поиска» меню кнопки помощника:
        прежние запросы стираются из профиля."""
        QgsSettings().remove(HISTORY_KEY)
        self.panel.hide_hints()
        self.message = (tr("История поиска очищена."), time.monotonic())
        self._show_state()

    def _search_places(self):
        """Метки для строки «Поиск»: ключ, название, широта и долгота
        меток тела на экране, на небе - меток неба. Метки без названия
        или геометрии и записанные туры не идут."""
        body = self.body_key()
        out = []
        for place in self.myplaces.places:
            points = place.shape.points
            if place.body == body and not place.tour and points \
                    and (place.name or "").strip():
                out.append((place.key, place.name, points[0][0],
                            points[0][1]))
        return out

    def _search_sky(self):
        """Звёзды и созвездия для строки «Поиск», вне неба их нет.
        Файл неба читается один раз."""
        if self.view.sky_view is None:
            return []
        if self._sky_objects is None:
            language = "ru" if ui_language() == "ru" else "en"
            self._sky_objects = searchbar.sky_objects(
                skydata.load(), language, self.sky_labels.deep)
        return self._sky_objects

    def _search_actions(self):
        """Действия модуля для подсказок (ui/commands.py). Функции
        запоминаются до следующего списка. В виде неба действий нет."""
        if self.view.sky_view is not None:
            self._actions = {}
            return []
        items, self._actions = commands_ui.build(self)
        return items

    def search_suggestions(self, text):
        """Подсказки строки «Поиск» к тексту, их спрашивает панель при
        вводе. Пустой текст - включённые слои и карты, потом прежние
        запросы."""
        actions = self._search_actions()
        if not str(text).strip():
            on = [a for a in actions
                  if a.key.split(":")[0] in ("layer", "map")
                  and a.note in (tr("выключить"), tr("убрать карту"))]
            history = searchbar.suggestions("", history=self.search_history())
            return (on + history)[:searchbar.LIMIT]
        found = searchbar.suggestions(
            text, self._search_places(), self.search_history(),
            self._search_sky(), searchbar.LIMIT + searchbar.HISTORY,
            actions=actions)
        manual = self._manual_hints(text)
        return searchbar.drop_repeats(found)[
            :searchbar.LIMIT - len(manual)] + manual

    def _manual_hints(self, text):
        """Разделы руководства к тексту строки - в конце подсказок,
        им всегда есть место."""
        index = load_index()
        return [Suggestion("manual", index.items[n][0], n, None, None, None,
                           index.snippet(n, text))
                for n in index.search(text)]

    def open_manual(self, number, query=""):
        """Раздел руководства в панели справа. Окно свойств в панели
        главнее, как у карточек меток."""
        held = self.side.dialog
        if held is not None and not isinstance(held, Card):
            return
        card = ManualCard(load_index(), number, query, self)
        card.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        self._place_card = card
        card.finished.connect(lambda *a, c=card: self._card_closed(c))
        self.side.host(card)

    def focus_search(self):
        """Ctrl+K: боковая панель видна, курсор в строке «Поиск», текст
        выделен, подсказки открыты."""
        if self.panel.isHidden():
            self.set_sidebar(True)
        self.place.setFocus()
        self.place.selectAll()
        self.panel.show_hints(self.place.text())

    def _exact_match(self, text):
        """Своя метка, а на небе звезда или созвездие, чьё название
        совпадает с text целиком. Из нескольких берётся первая, метки
        идут раньше объектов неба. Без совпадения - None."""
        places = self._search_places()
        sky = self._search_sky()
        found = searchbar.exact(text, searchbar.suggestions(
            text, places, sky=sky, limit=len(places) + len(sky) + 1))
        return found[0] if found else None

    def _exact_action(self, text):
        """Действие, чьё название или слово совпадает с text целиком.
        Демо по Enter не открываются - «Пермь» остаётся поиском места."""
        found = [a for a in searchbar.exact(text, self._search_actions())
                 if not a.key.startswith("demo:")]
        return found[0] if found else None

    def run_action(self, item):
        """Выполнить действие подсказки. Строка «Поиск» пустеет."""
        func = self._actions.get(item.key)
        if func is None:
            return
        journal.note("action {}".format(item.key))
        self.place.clear()
        self.panel.hide_hints()
        func()

    def choose_suggestion(self, item):
        """Выбрана подсказка строки «Поиск». Действие выполняется,
        прежний запрос идёт в строку и ищется заново, к метке и объекту
        неба начинается перелёт."""
        if item.kind == "action":
            self.run_action(item)
            return
        if item.kind == "manual":
            self.panel.hide_hints()
            self.open_manual(item.key, self.place.text())
            return
        self.place.setText(item.text)
        if item.kind == "history":
            self.fly(item.text)
        else:
            self._fly_suggestion(item)

    def _fly_suggestion(self, item):
        """Перелёт к своей метке или объекту неба. Прежний поиск по
        названию снимается: списка найденных мест, метки поиска
        и ждущего запроса больше нет."""
        self._search_timer.stop()
        self.panel.set_found([])
        self.clear_search()
        if item.kind == "place":
            place = self.myplaces.find(item.key)
            if place is not None:
                self.fly_to_place(place)
                self.panel.select_place(item.key)
            return
        # Долгота подсказки неба - прямое восхождение от -180° до 180°.
        ra = item.lon % 360.0
        if self.view.sky_view is None:
            self.show_sky(ra, item.lat, item.fov)
        else:
            # Плавный перелёт взгляда, как двойной щелчок по небу.
            self.view.fly_sky(ra, item.lat, item.fov)
        if item.kind == "deepsky":
            self.open_deep_card(item.key)
        self.view.setFocus()

    def _mark(self, name, lat, lon):
        """Временная метка на месте, как у Google Earth. Одна на окно."""
        self.view.set_search_mark(MarkPlace(-1, name, "search", 0, lat, lon))

    def _fly_place(self, place):
        """Метка и камера над местом, охват места целиком в кадре."""
        self._mark(place.name, place.lat, place.lon)
        distance = SEARCH_MIN_DISTANCE
        if place.box is not None:
            camera = self.view.camera
            distance = min(max(fit_view(*place.box, camera.fov_y,
                                        camera.aspect)[2],
                               SEARCH_MIN_DISTANCE), SEARCH_MAX_DISTANCE)
        self._fly_to(place.lat, place.lon, distance)

    def fly_to_layer(self, layer):
        """Перелёт к охвату слоя, камера смотрит отвесно."""
        self._fly_extent(layer.extent(), layer.crs())
