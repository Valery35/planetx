# -*- coding: utf-8 -*-
# PlanetX - трёхмерный глобус для QGIS.
# Copyright (C) 2026 ООО «Информ++». Лицензия GNU GPL версии 3.
"""Википедия рядом: подписи статей, карточка статьи, «Объясни это».

Часть окна глобуса GlobeWindow (ui/window.py). Ядро - core/wikipedia.py,
загрузка по тайлам вида - ui/wikipedia.py."""
import html
import json
import time

import numpy as np
from qgis.PyQt.QtCore import Qt

from ...core import wikipedia
from ...core.ellipsoid import ecef_to_geodetic, geodetic_to_ecef
from ...core.features import Shape
from ...core.places import Place as MarkPlace, identity
from ...i18n import tr, ui_language
from ...net.overlay import fetch_bytes
from ...qt_compat import enum
from ..assistant import current_provider, ready
from ..identify import Group
from ..placecard import ArticleCard, Card, article_question
from .base import IDENTIFY_PIXELS

# Номер подписи статьи - номер страницы плюс сдвиг, чтобы не совпасть
# с номерами пунктов векторной основы. Номер положительный: подпись
# проверяется на видимость за рельефом и проявляется, как пункты основы.
WIKI_ID = 10 ** 12
# Перелёт к статье: расстояние, м, и наклон, градусы. Выбор помощника.
ARTICLE_DISTANCE = 2500.0
ARTICLE_TILT = 45.0
# Строки «Слоёв», которые помощнику о месте ничего не говорят.
QUIET_LAYERS = ("stars", "air", "wiki")


class WikiMixin:
    """Часть окна глобуса GlobeWindow."""

    def _wiki_on(self):
        return bool(getattr(self, "extras", {}).get("wiki")) \
            and self.planet.earth and self.view.sky_view is None

    def _set_wiki(self, on):
        """Строка «Википедия рядом»: статьи у точки взгляда ниже
        core.wikipedia.MAX_ALTITUDE."""
        self._mark_gallery()
        if not on:
            self.wiki_articles.stop()
        self._place_wiki()
        if on:
            self._want_wiki()

    def _wiki_view_changed(self):
        if self._wiki_on():
            self._wiki_timer.start()

    def _want_wiki(self):
        if not self._wiki_on():
            return
        pose = self.view.navigator.pose
        eye = np.asarray(self.view.camera.eye, dtype=np.float64)
        altitude = float(ecef_to_geodetic(eye)[2])
        self.wiki_articles.want(pose.lat, pose.lon, altitude, ui_language())
        self._place_wiki()

    def _place_wiki(self):
        """Подписи статей: важные и ближние к точке взгляда первыми."""
        if not self._wiki_on():
            marks = []
        else:
            pose = self.view.navigator.pose
            marks = [MarkPlace(WIKI_ID + a.pageid, a.title, "wiki", a.rank,
                               a.lat, a.lon)
                     for a in wikipedia.order(self.wiki_articles.articles(),
                                              pose.lat, pose.lon)]
        if marks != self.view.wiki_marks:
            self.view.wiki_marks = marks
            self._show_attribution()
            self.view.update()

    def _wiki_failed(self):
        self.message = (tr("Википедия не ответила, повтор через 30 с."),
                        time.monotonic())
        self._show_state()

    def _articles_near(self, px, py, limit=10):
        """Статьи у пикселя кадра, ближние первыми. Подписанные на
        экране главнее неподписанных: щелчок по надписи берёт её."""
        marks = self.view.wiki_marks
        if not marks or not self._wiki_on():
            return []
        lats = np.array([m.lat for m in marks])
        lons = np.array([m.lon for m in marks])
        heights = self.view.label_heights(lats, lons) \
            if self.view.store.scale else np.zeros(len(marks))
        points = geodetic_to_ecef(lats, lons, heights)
        pixels, front = self.view.camera.project(points)
        gap = np.hypot(pixels[:, 0] - px, pixels[:, 1] - py)
        radius = IDENTIFY_PIXELS * self.view.devicePixelRatioF() * 2.0
        shown = self.view.labels.shown
        near = [n for n in np.nonzero(front & (gap <= radius))[0]]
        near.sort(key=lambda n: (identity(marks[n]) not in shown, gap[n]))
        lang = self.wiki_articles.lang
        return [(wikipedia.Article(marks[n].id - WIKI_ID, marks[n].name,
                                   marks[n].lat, marks[n].lon,
                                   marks[n].rank), lang)
                for n in near[:limit]]

    def _article_under(self, px, py):
        found = self._articles_near(px, py, limit=1)
        return found[0] if found else None

    def open_article_card(self, article, lang):
        """Карточка статьи в панели справа. Окно свойств в панели
        главнее, как у карточки метки."""
        held = self.side.dialog
        if held is not None and not isinstance(held, Card):
            return
        card = ArticleCard(article, wikipedia.page_url(lang, article.title),
                           ready(current_provider()), self)
        card.setAttribute(enum(Qt, "WidgetAttribute", "WA_DeleteOnClose"))
        card.explain.connect(self.explain_article)
        card.fly.connect(lambda a: self._fly_to(
            a.lat, a.lon, ARTICLE_DISTANCE, 0.0, ARTICLE_TILT))
        card.keep.connect(lambda a, c=card: self.keep_article(c))
        self._place_card = card
        card.finished.connect(lambda *a, c=card: self._card_closed(c))
        self.side.host(card)
        # fetch_bytes, а не fetch_json: служба отвечает переадресацией
        # на каноническое имя статьи, Qt 5 идёт по ней только по просьбе.
        self._summary_reply = fetch_bytes(
            wikipedia.summary_url(lang, article.title),
            lambda data, error, c=card: self._summary_arrived(c, data,
                                                              error))

    def _summary_arrived(self, card, data, error):
        self._summary_reply = None
        if card is not getattr(self, "_place_card", None):
            return  # карточку уже закрыли или сменили
        text = ""
        if data is not None:
            try:
                text = wikipedia.parse_summary(json.loads(data))
            except (ValueError, UnicodeDecodeError) as problem:
                error = str(problem)
        card.set_extract(text, error)

    def _explain_layers(self):
        """Названия включённых строк «Слоёв» глобуса для вопроса
        помощнику. Слои проекта не уходят."""
        return [row[1] for row in self._active_rows()
                if row[4] and row[0] not in QUIET_LAYERS]

    def explain_article(self, article):
        """«Объясни это» карточки статьи: вопрос помощнику с первым
        абзацем статьи."""
        card = getattr(self, "_place_card", None)
        extract = card.extract if isinstance(card, ArticleCard) \
            and card.article == article else ""
        question = article_question(article.title, extract, article.lat,
                                    article.lon, self._explain_layers())
        if self._assistant().ask(question):
            self._explaining = card
            if card is not None:
                card.show_answer(tr("Помощник думает…"))
        elif card is not None:
            card.show_answer(tr("Помощник занят прежним вопросом или не "
                                "подключён."))

    def keep_article(self, card):
        """Метка в точке статьи в «Моих метках»: первый абзац и ссылка
        на статью в описании."""
        article = card.article
        key = self.myplaces.add(Shape("point", [(article.lat, article.lon)],
                                      name=article.title))
        self.myplaces.update(key, {"description": (
            '<p>{}</p><p><a href="{}">{}</a></p>'.format(
                html.escape(card.extract or ""),
                html.escape(card.link, quote=True),
                html.escape(tr("Статья в Википедии"))))})
        self.message = (tr("Метка «{name}» записана в «Мои метки».",
                           name=article.title), time.monotonic())
        self._show_state()

    def _identify_wiki(self, px, py):
        """Группа «Википедия» окна «Объекты»: статьи у щелчка."""
        features = [(article.title,
                     [(tr("Статья"), wikipedia.page_url(lang,
                                                        article.title))],
                     None)
                    for article, lang in self._articles_near(px, py)]
        return [(Group(tr("Википедия")), features)] if features else []
