# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Википедия рядом: подписи статей, карточка статьи, «Объясни это».

Строка реестра каталога (core/rows.py) и исполнитель. Ядро -
core/wikipedia.py, загрузка по тайлам вида - ui/wikipedia.py."""
import html
import json
import time

import numpy as np
from qgis.PyQt.QtCore import QObject, Qt, QTimer

from ..core import wikipedia
from ..core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ..core.features import Shape
from ..core.places import Place as MarkPlace, identity
from ..core.rows import Row
from ..i18n import tr, ui_language
from ..net.overlay import fetch_bytes
from ..qt_compat import enum
from .assistant import current_provider, ready
from .identify import Group
from .placecard import ArticleCard, Card, article_question
from .wikipedia import WikiArticles

KEY = "wiki"
# Номер подписи статьи - номер страницы плюс сдвиг, чтобы не совпасть
# с номерами пунктов векторной основы. Номер положительный: подпись
# проверяется на видимость за рельефом и проявляется, как пункты основы.
WIKI_ID = 10 ** 12
# Перелёт к статье: расстояние, м, и наклон, градусы. Выбор помощника.
ARTICLE_DISTANCE = 2500.0
ARTICLE_TILT = 45.0


class WikiTool(QObject):
    """Статьи у точки взгляда ниже core.wikipedia.MAX_ALTITUDE."""

    def __init__(self, window):
        # ui/globe/base.py читает реестр, поэтому импорт - здесь.
        from .globe.base import OSM_PAUSE
        super().__init__(window)
        self.window = window
        self.articles = WikiArticles(window.view, self.place, self.failed)
        self.summary_reply = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(OSM_PAUSE)
        self.timer.timeout.connect(self.want)

    shown_key = None

    def on(self):
        window = self.window
        return bool(getattr(window, "extras", {}).get(KEY)) \
            and window.planet.earth and window.view.sky_view is None

    def turn(self, key, on):
        if not on:
            self.articles.stop()
        self.place()
        if on:
            self.want()
        return True

    def view_changed(self):
        if self.on():
            self.timer.start()

    def want(self):
        if not self.on():
            return
        view = self.window.view
        pose = view.navigator.pose
        eye = np.asarray(view.camera.eye, dtype=np.float64)
        altitude = float(ecef_to_geodetic(eye)[2])
        self.articles.want(pose.lat, pose.lon, altitude, ui_language())
        self.place()

    def place(self):
        """Подписи статей: важные и ближние к точке взгляда первыми."""
        window = self.window
        view = window.view
        if not self.on():
            marks = []
        else:
            pose = view.navigator.pose
            marks = [MarkPlace(WIKI_ID + a.pageid, a.title, "wiki", a.rank,
                               a.lat, a.lon)
                     for a in wikipedia.order(self.articles.articles(),
                                              pose.lat, pose.lon)]
        if marks != view.wiki_marks:
            view.wiki_marks = marks
            window._show_attribution()
            view.update()

    def failed(self):
        window = self.window
        window.message = (tr("Википедия не ответила, повтор через 30 с."),
                          time.monotonic())
        window._show_state()

    def near(self, px, py, limit=10):
        """Статьи у пикселя кадра, ближние первыми. Подписанные на
        экране главнее неподписанных: щелчок по надписи берёт её."""
        from .globe.base import IDENTIFY_PIXELS
        view = self.window.view
        marks = view.wiki_marks
        if not marks or not self.on():
            return []
        lats = np.array([m.lat for m in marks])
        lons = np.array([m.lon for m in marks])
        heights = view.label_heights(lats, lons) \
            if view.store.scale else np.zeros(len(marks))
        points = geodetic_to_ecef(lats, lons, heights)
        pixels, front = view.camera.project(points)
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        radius = IDENTIFY_PIXELS * view.devicePixelRatioF() * 2.0
        shown = view.labels.shown
        near = [n for n in np.nonzero(front & (gap <= radius))[0]]
        near.sort(key=lambda n: (identity(marks[n]) not in shown, gap[n]))
        lang = self.articles.lang
        return [(wikipedia.Article(marks[n].id - WIKI_ID, marks[n].name,
                                   marks[n].lat, marks[n].lon,
                                   marks[n].rank), lang)
                for n in near[:limit]]

    def card_under(self, px, py):
        """Карточка статьи под пикселем кадра: функция открытия или
        None. Щелчок по подписи статьи открывает её карточку."""
        found = self.near(px, py, limit=1)
        if not found:
            return None
        return lambda: self.open_card(*found[0])

    def open_card(self, article, lang):
        """Карточка статьи в панели справа. Окно свойств в панели
        главнее, как у карточки метки."""
        window = self.window
        held = window.side.dialog
        if held is not None and not isinstance(held, Card):
            return
        card = ArticleCard(article, wikipedia.page_url(lang, article.title),
                           ready(current_provider()), window)
        card.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        card.explain.connect(self.explain)
        card.fly.connect(lambda a: window._fly_to(
            a.lat, a.lon, ARTICLE_DISTANCE, 0.0, ARTICLE_TILT))
        card.keep.connect(lambda a, c=card: self.keep(c))
        window._place_card = card
        card.finished.connect(lambda *a, c=card: window._card_closed(c))
        window.side.host(card)
        # fetch_bytes, а не fetch_json: служба отвечает переадресацией
        # на каноническое имя статьи, Qt 5 идёт по ней только по просьбе.
        self.summary_reply = fetch_bytes(
            wikipedia.summary_url(lang, article.title),
            lambda data, error, c=card: self.summary_arrived(c, data, error))

    def summary_arrived(self, card, data, error):
        self.summary_reply = None
        if card is not getattr(self.window, "_place_card", None):
            return  # карточку уже закрыли или сменили
        text = ""
        if data is not None:
            try:
                text = wikipedia.parse_summary(json.loads(data))
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        card.set_extract(text, error)

    def explain(self, article):
        """«Объясни это» карточки статьи: вопрос помощнику с первым
        абзацем статьи."""
        window = self.window
        card = getattr(window, "_place_card", None)
        extract = card.extract if isinstance(card, ArticleCard) \
            and card.article == article else ""
        question = article_question(article.title, extract, article.lat,
                                    article.lon, window._explain_layers())
        if window._assistant().ask(question):
            window._explaining = card
            if card is not None:
                card.show_answer(tr("Помощник думает…"))
        elif card is not None:
            card.show_answer(tr("Помощник занят прежним вопросом или не "
                                "подключён."))

    def keep(self, card):
        """Метка в точке статьи в «Моих метках»: первый абзац и ссылка
        на статью в описании."""
        window = self.window
        article = card.article
        key = window.myplaces.add(Shape("point", [(article.lat, article.lon)],
                                        name=article.title))
        window.myplaces.update(key, {"description": (
            '<p>{}</p><p><a href="{}">{}</a></p>'.format(
                html.escape(card.extract or ""),
                html.escape(card.link, quote=True),
                html.escape(tr("Статья в Википедии"))))})
        window.message = (tr("Метка «{name}» записана в «Мои метки».",
                             name=article.title), time.monotonic())
        window._show_state()

    def pixel_groups(self, px, py):
        """Группа «Википедия» окна «Объекты»: статьи у щелчка."""
        features = [(article.title,
                     [(tr("Статья"), wikipedia.page_url(lang,
                                                        article.title))],
                     None)
                    for article, lang in self.near(px, py)]
        return [(Group(tr("Википедия")), features)] if features else []

    def credits(self):
        return [wikipedia.ATTRIBUTION] if self.window.view.wiki_marks \
            else []

    def identify(self, lat, lon, tolerance=0.0):
        return []

    def credit(self):
        return None

    def close(self):
        self.timer.stop()
        self.articles.stop()
        reply, self.summary_reply = self.summary_reply, None
        if reply is not None:
            reply.abort()


ROWS = (
    Row(KEY, "wiki", lambda: (tr("Википедия рядом"), tr(
        "Статьи Википедии с координатами - города, памятники, реки, "
        "вершины - подписями с голубым кружком. Статьи просятся, "
        "когда камера ниже 40 км, на языке интерфейса QGIS. Щелчок "
        "по подписи открывает карточку статьи - первый абзац, ссылку "
        "на статью и кнопку «Объясни это». Тексты Википедии - "
        "CC BY-SA 4.0.")), WikiTool,
        source="Wikipedia",
        colors=((45, 110, 205), (245, 245, 245), (205, 228, 255)),
        words=("википедия", "энциклопедия", "статьи",
               "достопримечательности", "wikipedia", "encyclopedia",
               "articles", "landmarks"),
        after="aspect"),
)
